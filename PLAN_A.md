# Plan A — ASI Hackathon: Airspace Energy Optimization & Heatmap

## Context

We have a hackathon data bundle (`/Users/repsaj17/AsiHackathon/hackathon_data_bundle`)
describing US air traffic at 11 point-in-time snapshots. The goal is a polished,
interactive web app that (1) **estimates per-flight fuel burn (kg)** as a function of
weather — chiefly **wind** plus **storm avoidance** — (2) aggregates that energy into an
**H3 hexagon heatmap**, and (3) runs an **optimizer** that reduces total system fuel by
adjusting flights (altitude / lateral reroute / departure-time shift) subject to **sector
capacity** and **storm** constraints. Users can click into any individual flight to see
its fuel, wind exposure, route, sectors crossed, and storm encounters, with flights
color-coded by energy cost.

Decisions locked with the user:
- **Deliverable:** both estimate + optimize.
- **Energy metric:** fuel burn in kg (CO₂ = fuel × 3.16 as a derived display value).
- **Stack:** React + deck.gl + MapLibre GL (no Mapbox token needed).
- **Wind source:** Open-Meteo pressure-level winds (free, no key, historical archive).

## What the data gives us (verified)

- `asked_at_<ts>/routes.json` — ~14,700 flights/snapshot. Per flight: `flight_number`,
  `take_off_time`, `scheduled_landing_time`, `origin/destination_airport_icao`,
  `cruise_altitude_ft`, `cruise_speed_kt` (TAS), parallel `lats`/`lons` waypoint arrays,
  `is_airborne`. **Constant-cruise model** (no climb/descent). Unique key =
  `(flight_number, take_off_time, origin_airport_icao)`.
- `asked_at_<ts>/wx/refc|retop/*.npz` — 256×358 float64 grids, equirectangular over
  CONUS (LAT 21.943→55.7765, LON −135→−67.5), 15-min strips ~18h forward. `refc` = dBZ
  (storm where ≥ 40), `retop` = echo-top ft. Flight is impacted where `refc ≥ 40` **and**
  `cruise_altitude_ft < retop`. Mask: refc ≤ −50 nodata, retop < 0 nodata.
- `sectors.geojson` — 712 polygons (356 HIGH ≥35k ft, 356 LOW <35k ft), each with integer
  `capacity`. Partition of CONUS per band → exactly one sector per (point, band).
- **No wind in the bundle** → supplied externally by Open-Meteo.

## Architecture

Two parts: a **Python precompute pipeline** (offline, per snapshot) that emits static
JSON artifacts, and a **React/deck.gl frontend** that loads those artifacts. Precomputing
means the demo has zero live-API dependency and stays fast/robust.

```
AsiHackathon/
  hackathon_data_bundle/        # existing data (read-only)
  pipeline/                     # NEW python
    load.py                     # parse routes.json, wx npz, sectors
    wind.py                     # Open-Meteo fetch + CONUS wind field + along-track lookup
    fuel.py                     # fuel-burn model (kg)
    weather.py                  # storm impact sampling along route
    sectors.py                  # sector occupancy / capacity (shapely)
    h3agg.py                    # bin route segments to H3, aggregate fuel/congestion
    optimize.py                 # min-total-fuel optimizer (altitude/reroute/time)
    build.py                    # orchestrate -> writes web/public/data/<snapshot>/*.json
  web/                          # NEW React + Vite + deck.gl + MapLibre
    src/App.tsx, layers/, panels/, scales.ts
    public/data/<snapshot>/{flights.json, h3.json, sectors.json, summary.json}
```

### Fuel-burn model (`fuel.py`) — energy in kg

Per flight, integrate over consecutive waypoint segments:

1. **Segment geometry:** great-circle distance + initial bearing between waypoints
   (haversine / `pyproj.Geod`).
2. **Ground speed:** TAS = `cruise_speed_kt`. Sample the wind vector at the segment
   (from the wind field, at the pressure level nearest `cruise_altitude_ft`). Along-track
   wind component `w_∥ = |W|·cos(θ_wind − bearing)`; `GS = TAS + w_∥` (tailwind +,
   headwind −). Segment time = dist / GS.
3. **Fuel flow:** since the bundle has no aircraft type, infer a **class** from
   (`cruise_speed_kt`, `cruise_altitude_ft`) → {regional jet, narrowbody, widebody} and
   assign a representative cruise fuel-flow (kg/hr). Reuse **OpenAP** (`pip install openap`)
   for class fuel-flow vs mass/altitude/speed if time permits; otherwise a constant per
   class. Segment fuel = fuel_flow × segment_time.
4. **Storm penalty:** if a segment crosses storm cells (`weather.py`), add a detour/throttle
   penalty (extra distance ~ proportional to impacted length, or a fixed % fuel adder).
5. Flight fuel = Σ segment fuel. Store total kg, per-segment breakdown, headwind/tailwind
   split, storm-impacted distance. CO₂ = fuel × 3.16.

The wind dependence flows entirely through GS → time → fuel, which is the dominant,
defensible "fuel depends on weather/wind" mechanism.

### Wind integration (`wind.py`) — Open-Meteo

- Host: `historical-forecast-api.open-meteo.com/v1/forecast`. No key.
- Params (verify exact spelling against live docs at build time): pressure-level
  `wind_speed_250hPa` / `wind_direction_250hPa` (≈34k ft) and `..._200hPa` (≈39k ft),
  hourly. Pick the level nearest each flight's `cruise_altitude_ft`.
- **Build a CONUS wind field once per snapshot**, not per-waypoint: query a coarse grid
  (~0.75°–1°, a few hundred points; comma-separated multi-location request) at the
  pressure levels of interest for the snapshot hour(s). Cache to disk (JSON/npz).
- Along-track lookup = bilinear interpolation of the cached field at each waypoint;
  pick time bin from the aircraft's position-time (linear along route between
  `take_off_time` and `scheduled_landing_time`).
- Respect ≤10k calls/day; the grid approach keeps us to a handful of calls per snapshot.

### Storm impact (`weather.py`)

- Map waypoint lat/lon → grid `(i,j)` via the documented `pixel_top_left_latlon` inverse.
- Choose the wx strip whose `[valid_from, valid_to)` contains the aircraft's time at that
  point. Impacted if `refc ≥ 40` and `cruise_altitude_ft < retop`. Emit impacted segments
  for both the fuel penalty and the frontend overlay.

### H3 aggregation (`h3agg.py`)

- Densify each route (interpolate points every ~10 nm), map to H3 (`h3-py`, **res 4–5**;
  tune for CONUS cell count). Per cell aggregate: total fuel burned in-cell, flight count,
  mean energy/flight, and a congestion ratio (cell flights vs nearby sector capacity).
- Emit `h3.json`: `[{h3, fuel_kg, n_flights, mean_kg, congestion}]`. Frontend colors via
  `H3HexagonLayer`.

### Sector occupancy (`sectors.py`)

- With shapely, for each flight build a time-parameterized track; sample at fixed time
  steps to get (sector, time-bin) occupancy counts per band. Flag **over-demand**
  (count > capacity). Feeds both the optimizer constraint and an optional sectors overlay.

### Optimizer (`optimize.py`) — minimize total fuel s.t. capacity + storms

Objective: minimize Σ_flights fuel_kg. Levers per flight (discrete candidate set):
- **Altitude:** evaluate fuel at a few cruise levels (different pressure-level winds /
  fuel-flow) → pick min; this is the cheapest big win (wind-optimal altitude).
- **Lateral reroute:** for storm-impacted or congested flights, generate a small set of
  detour candidates (offset waypoints around storm cells / hot sectors) and re-cost.
- **Departure-time shift:** ±N minutes to relieve sector over-demand.

Hackathon-feasible solve (staged, not a monolithic MILP):
1. **Per-flight wind/altitude optimization** ignoring coupling (independent, fast) → big
   aggregate fuel drop; record per-flight savings.
2. **Capacity-repair pass:** detect over-demand sectors; for contributing flights, apply
   the cheapest reroute/time-shift candidate that relieves the sector, greedily, using a
   congestion penalty in the cost. (Optionally formalize as an LP/min-cost assignment if
   time allows — keep the greedy as the reliable fallback.)
3. Emit **before/after**: total fuel, kg saved, %, # over-demand sectors resolved,
   per-flight deltas. Frontend shows a baseline↔optimized toggle.

### Frontend (`web/`) — React + Vite + deck.gl + MapLibre

- Basemap: MapLibre GL with a free style (e.g. CARTO dark) — no token.
- Layers:
  - `H3HexagonLayer` — energy heatmap (`getFillColor` from fuel/congestion via a
    sequential `turbo`/`viridis` scale in `scales.ts`), opacity toggle.
  - `PathLayer` (or `TripsLayer` for animated time) — flights, `getColor` from each
    flight's energy cost, `pickable: true`.
  - `GeoJsonLayer` — sectors overlay (toggle, color by capacity / over-demand).
  - `ScatterplotLayer` — airports.
- Interaction: click a path → side **detail panel** (fuel kg, CO₂, headwind/tailwind
  split, storm-impacted distance, sectors crossed, altitude, baseline vs optimized).
- Controls: snapshot selector, baseline/optimized toggle, layer toggles, color-scale
  legend, a summary header (total fuel, kg & % saved, over-demand sectors resolved).

## Build phases / milestones

1. **Pipeline MVP (no wind):** parse routes, haversine distance, constant fuel-flow →
   `flights.json` + `summary.json`; stub `h3.json`.
2. **Frontend MVP:** Vite app, MapLibre + `PathLayer` colored by fuel + click panel +
   `H3HexagonLayer` from stub. (Parts 1–2 give a demo-able vertical slice fast.)
3. **Wind + storms:** Open-Meteo field, GS-adjusted fuel, storm penalty + overlay.
4. **Sectors + H3 real aggregation.**
5. **Optimizer:** altitude pass, then capacity-repair; baseline/optimized toggle + savings.
6. **Polish:** legend, animation (`TripsLayer`), styling, multi-snapshot selector.

## Reuse / external libs

- Python: `numpy`, `shapely`, `pyproj` (geod), `h3` (h3-py), `requests`, optional
  `openap` (fuel), optional `scipy`/`networkx` (optimizer).
- JS: `deck.gl`, `maplibre-gl`, `react`, `vite`, `d3-scale-chromatic` (color scales),
  `h3-js` (only if doing client-side H3).
- The format docs in `documentation/{routes,wx,sectors}/FILE_FORMAT.md` give exact grid
  math and reading examples — follow them verbatim for the wx grid + sector lookups.

## Verification

- **Pipeline unit checks:** zero-wind fuel ≈ distance/TAS × fuel-flow (sanity vs known
  city-pair fuel, e.g. KDEN–KSFO narrowbody ≈ few thousand kg). Tailwind lowers fuel,
  headwind raises it (assert sign). Storm flag fires on a known refc≥40 cell.
- **Wind field:** spot-check an Open-Meteo grid point against the raw API response.
- **Sectors:** reproduce the doc's Seattle@38k example; verify occupancy never silently
  exceeds the grid (counts plausible vs capacities).
- **Optimizer:** assert total optimized fuel ≤ baseline; assert resolved sectors were
  previously over-demand; show before/after numbers in `summary.json`.
- **Frontend e2e:** `npm run dev`, confirm heatmap renders, a flight is clickable, panel
  shows fuel/wind/storms, baseline↔optimized toggle changes colors and the summary, all
  layer toggles work. (Use the `run`/`verify` skills to launch and screenshot.)

## Open risks

- Open-Meteo exact pressure-level param names & multi-location syntax — confirm against
  live docs in `wind.py` (have a single-point fallback loop if multi-location fails).
- No aircraft type → fuel is class-approximate; we present kg as a consistent relative
  metric (good for ranking/optimization) rather than certified absolute burn.
- H3 resolution & route densification step are perf/legibility trade-offs — tune on the
  ~14.7k-flight snapshot.
- Optimizer coupling: greedy capacity-repair is the reliable target; LP/MILP only if time.

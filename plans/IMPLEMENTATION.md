# Implementation Plan — AirFlow (Plan A on the current structure)

This plan adapts `PLAN_A.md` (fuel-burn estimation, H3 energy heatmap, fuel
optimizer) onto the existing repository layout, with three decisions locked:

1. **Backend:** FastAPI serves results live. The `src/` pipeline computes
   everything; `backend/` exposes it over HTTP. The frontend reads from the API.
2. **Frontend:** combination of **deck.gl + MapLibre** (2D analytical map: H3
   heatmap, flight paths, sectors) **and** **Three.js** (3D CONUS view), toggled
   in the UI.
3. **Wind:** Open-Meteo coarse CONUS field, fetched once per snapshot and cached
   to disk so the demo runs offline after the first fetch.

The top-level folders (`src/`, `backend/`, `frontend/`, `docs/`, `data/`) do not
change. Plan A's `pipeline/*` modules map into `src/`; Plan A's `web/*` maps into
`frontend/`. New files are added inside these existing folders only.

## Module mapping (Plan A -> current structure)

| Plan A module | Lands at | Responsibility |
| --- | --- | --- |
| `pipeline/load.py` | `src/data/ingest.py` | Parse `routes.json.gz`, `sectors.geojson(.gz)`, wx `.npz` into typed structures |
| `pipeline/wind.py` | `src/data/wind.py` | Open-Meteo fetch, CONUS wind field cache, along-track bilinear lookup |
| `pipeline/weather.py` | `src/data/weather.py` | Storm-impact sampling along a route (refc >= 40 and alt < retop) |
| `pipeline/fuel.py` | `src/algorithm/fuel.py` | Per-segment fuel-burn model (kg), wind-adjusted ground speed |
| `pipeline/sectors.py` | `src/algorithm/sectors.py` | Time-parameterized sector occupancy vs capacity, over-demand flags |
| `pipeline/h3agg.py` | `src/algorithm/h3agg.py` | Densify routes, bin to H3, aggregate fuel/congestion per cell |
| `pipeline/optimize.py` | `src/algorithm/optimize.py` | Min-total-fuel optimizer: altitude pass + capacity-repair |
| (grid math helpers) | `src/algorithm/grid.py` | Pixel<->lat/lon, H3 helpers, geod distance/bearing |
| `pipeline/build.py` | `src/build.py` | Orchestrate the pipeline, write artifacts for a snapshot |

Existing empty stubs (`solver.py`) are repurposed; `optimize.py` is the new home
for the optimizer. `solver.py` may be deleted or left as a thin re-export.

## Artifacts

The build step writes one folder per snapshot under a cache dir the backend
serves from:

```
data/artifacts/<snapshot>/
  flights.json    # per-flight: fuel_kg, co2_kg, headwind/tailwind split,
                  #   storm-impacted distance, sectors crossed, route, alt,
                  #   baseline vs optimized
  h3.json         # [{h3, fuel_kg, n_flights, mean_kg, congestion}]
  sectors.json    # per-sector occupancy peak vs capacity, over-demand flags
  summary.json    # totals: fuel baseline/optimized, kg & % saved,
                  #   over-demand sectors resolved, weather conflicts
  wind_cache.npz  # cached Open-Meteo CONUS wind field for the snapshot
```

`data/artifacts/` and the wind cache are gitignored (large, regenerable). The
frontend's deck.gl path can also read these as static files from
`frontend/public/data/<snapshot>/` for a zero-backend fallback demo; the build
step can write to both locations.

## Fuel-burn model (`src/algorithm/fuel.py`)

Per flight, integrate over consecutive waypoint segments:

1. **Segment geometry** — great-circle distance + initial bearing
   (`pyproj.Geod`, WGS84).
2. **Ground speed** — TAS = `cruise_speed_kt`; sample wind at the segment,
   along-track component `w_par = |W| * cos(theta_wind - bearing)`,
   `GS = TAS + w_par`. Segment time = distance / GS.
3. **Fuel flow** — infer aircraft class from (`cruise_speed_kt`,
   `cruise_altitude_ft`) -> {regional jet, narrowbody, widebody}; representative
   cruise fuel-flow (kg/hr) per class. Optional `openap` for class fuel-flow if
   time allows. Segment fuel = fuel_flow * segment_time.
4. **Storm penalty** — segments crossing storm cells get a detour/throttle adder
   (extra distance proportional to impacted length, or a fixed % fuel adder).
5. Flight fuel = sum of segment fuel. Store total kg, per-segment breakdown,
   headwind/tailwind split, storm-impacted distance. CO2 = fuel * 3.16.

## Wind integration (`src/data/wind.py`)

- Host `historical-forecast-api.open-meteo.com/v1/forecast` (no key).
- Pressure-level winds (`wind_speed_250hPa`/`wind_direction_250hPa` ~34k ft,
  `..._200hPa` ~39k ft); pick level nearest each flight's cruise altitude.
- Query a coarse CONUS grid (~0.75-1 deg) once per snapshot, cache to
  `wind_cache.npz`. Along-track lookup = bilinear interpolation; time bin from
  position-time interpolated between takeoff and landing.
- Single-point fallback loop if multi-location request fails. Respect the
  <=10k calls/day budget.

## Storm impact (`src/data/weather.py`)

- Map waypoint lat/lon -> grid `(i, j)` via the documented inverse of
  `pixel_top_left_latlon` (see `docs/DATA.md`).
- Select the wx strip whose `[valid_from, valid_to)` contains the aircraft's
  time at that point. Impacted iff `refc >= 40` and `cruise_altitude_ft < retop`.
- Emit impacted segments for both the fuel penalty and the frontend overlay.

## Sector occupancy (`src/algorithm/sectors.py`)

- Shapely polygons from `sectors.geojson`. Build a time-parameterized track per
  flight (constant cruise model: position interpolated by time between takeoff
  and landing). Sample at fixed time steps to get (sector, time-bin) occupancy
  per band; flag over-demand (count > capacity). Feeds the optimizer constraint
  and the sectors overlay.

## H3 aggregation (`src/algorithm/h3agg.py`)

- Densify each route (~every 10 nm), map points to H3 (`h3-py`, res 4-5; tune
  for CONUS cell count). Per cell aggregate total in-cell fuel, flight count,
  mean fuel/flight, congestion ratio (cell flights vs nearby sector capacity).
  Emit `h3.json`.

## Optimizer (`src/algorithm/optimize.py`)

Objective: minimize total fuel subject to sector capacity + storm constraints.
Staged, not a monolithic MILP:

1. **Per-flight wind/altitude optimization** (independent, fast) — evaluate fuel
   at a few cruise levels, pick the min. Big aggregate drop; record savings.
2. **Capacity-repair pass** — detect over-demand sectors; for contributing
   flights apply the cheapest reroute / time-shift candidate that relieves the
   sector, greedily, with a congestion penalty. (Optional LP/min-cost assignment
   if time; greedy is the reliable fallback.)
3. Emit before/after in `summary.json`.

## Backend (`backend/`) — FastAPI serving artifacts

Loads a snapshot's artifacts and serves them; triggers a build if missing.

| Endpoint | Returns |
| --- | --- |
| `POST /api/solve` | Run/refresh pipeline for a snapshot with given params; returns `summary` |
| `GET /api/flights` | `flights.json` (all flights, baseline + optimized) |
| `GET /api/flight/{id}` | One flight's detail (fuel, wind split, storms, sectors) |
| `GET /api/h3` | `h3.json` energy heatmap cells |
| `GET /api/sectors` | sector geometry + load vs capacity |
| `GET /api/sector_load?t=` | per-sector occupancy vs capacity for a time bin |
| `GET /api/weather?t=` | refc/retop grids for a time window |
| `GET /api/summary` | totals + before/after savings |
| `GET /health` | `{status: ok}` |

CORS open to `FRONTEND_URL`. (Updates `docs/API.md` to add `/api/h3`,
`/api/flight/{id}`, `/api/summary`.)

## Frontend (`frontend/`) — Next.js 14 + deck.gl/MapLibre + Three.js

Kept on Next.js (consistent with existing `README.md`/`docs/FRONTEND.md`);
deck.gl and react-three-fiber both run under Next. Deviates from Plan A's Vite
choice for repo consistency.

- **MapView (deck.gl + MapLibre)** — primary analytical view. MapLibre GL basemap
  (CARTO dark, no token); `H3HexagonLayer` (fuel/congestion color), `PathLayer`/
  `TripsLayer` (flights colored by fuel, pickable), `GeoJsonLayer` (sectors),
  `ScatterplotLayer` (airports).
- **Scene3D (Three.js)** — the existing 3D CONUS view, sectors extruded by band
  and colored by load, animated flight spheres, weather overlay. Toggle 2D<->3D.
- **DetailPanel** — click a flight -> fuel kg, CO2, headwind/tailwind split,
  storm-impacted distance, sectors crossed, altitude, baseline vs optimized.
- **Controls** — snapshot selector, baseline/optimized toggle, layer toggles,
  color-scale legend, summary header (total fuel, kg & % saved, sectors
  resolved).

## Dependencies to add

- **Python** (`requirements.txt`): `pyproj`, `h3`, `requests` (already have
  numpy, pandas, shapely, scipy, networkx, fastapi, uvicorn, matplotlib,
  python-dotenv). Optional: `openap`.
- **Frontend** (`frontend/package.json`, created at scaffold): `next`, `react`,
  `react-dom`, `deck.gl`, `@deck.gl/react`, `@deck.gl/geo-layers`,
  `@deck.gl/layers`, `maplibre-gl`, `react-map-gl`, `three`,
  `@react-three/fiber`, `@react-three/drei`, `d3-scale-chromatic`, `tailwindcss`.
- **Gitignore additions**: `.venv/`, `data/artifacts/`, `frontend/public/data/`.

## Build phases / milestones

1. **Pipeline MVP (no wind):** ingest -> haversine distance -> constant
   fuel-flow -> `flights.json` + `summary.json`; stub `h3.json`.
2. **Frontend MVP:** Next.js app, MapLibre + `PathLayer` colored by fuel + click
   `DetailPanel` + `H3HexagonLayer` from stub. (1-2 = demo-able vertical slice.)
3. **Wind + storms:** Open-Meteo field + cache, GS-adjusted fuel, storm penalty
   + overlay.
4. **Sectors + real H3 aggregation.**
5. **Optimizer:** altitude pass, then capacity-repair; baseline/optimized toggle
   + savings in `summary.json`.
6. **3D + polish:** Three.js Scene3D, legend, `TripsLayer` animation, styling,
   multi-snapshot selector.

## Verification

- **Fuel sanity:** zero-wind fuel ~ distance/TAS * fuel-flow vs a known city-pair
  (KDEN-KSFO narrowbody ~ few thousand kg). Tailwind lowers fuel, headwind raises
  it (assert sign). Storm flag fires on a known refc>=40 cell.
- **Wind field:** spot-check a grid point against the raw Open-Meteo response.
- **Sectors:** reproduce the doc's Seattle@38k example; occupancy counts
  plausible vs capacities.
- **Optimizer:** assert optimized total fuel <= baseline; resolved sectors were
  previously over-demand; before/after in `summary.json`.
- **Frontend e2e:** `make dev`, confirm heatmap renders, a flight is clickable,
  panel shows fuel/wind/storms, baseline<->optimized toggle changes colors and
  summary, layer + 2D/3D toggles work.

## Open risks

- Open-Meteo pressure-level param names / multi-location syntax (single-point
  fallback in `wind.py`).
- No aircraft type -> class-approximate fuel; present kg as a consistent relative
  metric for ranking/optimization, not certified absolute burn.
- H3 resolution + densification are perf/legibility trade-offs; tune on a full
  snapshot (~16.7k flights).
- Optimizer coupling: greedy capacity-repair is the reliable target; LP/MILP only
  if time allows.

## Agent sequence (per docs/AGENTS.md)

```
Phase 0  data-generator      ingest + wind + weather (src/data/*)
Phase 1  airspace-coder      fuel + sectors + h3agg + optimize (src/algorithm/*)
Phase 2  backend-engineer    FastAPI endpoints over artifacts
Phase 3  frontend-engineer + viz-engineer (parallel)  deck.gl/MapLibre + Three.js
Phase 4  demo-polisher       copy, README, before/after story
```

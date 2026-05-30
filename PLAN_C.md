# Plan C — ASI Hackathon: 4D Airspace Decision Support (Improved)

> A successor to Plan A (`PLAN_A.md`, the original) and the "Improved" PDF
> (`ASI_4D_Airspace_Plan_Improved.pdf`). It keeps the PDF's disciplined, demo-safe
> decision-support framing, but resolves the repo's architecture fork, commits to
> **FastAPI**, grounds every number in the real data bundle, and freezes concrete schemas,
> performance budgets, and a wind-caching strategy the earlier plans left vague.

---

## Context

The hackathon bundle describes US air traffic at **11 point-in-time snapshots**
(`hackathon_data_bundle/asked_at_<ts>/`), each with ~**16,687 flights** (Plan A's "14,700"
is stale), **73 fifteen-minute weather strips** per snapshot (`wx/refc`, `wx/retop`), and a
shared **`sectors.geojson`** of **712 polygons** (356 HIGH ≥35k ft, 356 LOW <35k ft, each
with `altitude_from_ft`, `altitude_to_ft`, `capacity`). **No wind is in the bundle** — it
comes from cached Open-Meteo pressure-level fields.

Two prior designs coexist in the repo and **contradict each other**:
- **`docs/` design** (live FastAPI + Next.js/**Three.js**, iterative Dijkstra sector
  routing). `backend/main.py`, `backend/routers/{routing,sectors,weather}.py`,
  `src/algorithm/{grid,solver}.py`, `src/data/{ingest,weather}.py` are scaffolded for it
  but are **all empty 0-byte stubs**. `docs/{ARCHITECTURE,API,ALGORITHM,DATA,FRONTEND}.md`
  are written and detailed.
- **Plan A / the Improved PDF** (Python precompute → static JSON → **React/deck.gl/MapLibre**).
  No code yet.

This plan **reconciles the two**: keep the existing **FastAPI backend** and `docs/API.md`
contract; adopt the **deck.gl/MapLibre** frontend (superior for this geospatial 2.5D view);
mark the **Three.js `docs/FRONTEND.md` as superseded**; keep a **precompute pipeline** as
the source of demo-safe baseline artifacts so the demo never depends on a live solve.

**Intended outcome:** an operator-facing decision loop — *observe → explain → recommend →
compare* — that a judge can drive in 60 seconds: click a high-cost flight, understand the
cause (headwind / storm / sector overload), toggle to a recommended scenario, and see a
credible reduction in estimated fuel proxy, storm exposure, or sector overload.

### Decisions locked
- **Architecture:** FastAPI backend serving precomputed artifacts + a live `POST /api/solve`
  for what-if. Frontend: React + Vite + **deck.gl + MapLibre GL** (no Mapbox token).
- **Energy metric:** **estimated fuel proxy** is the primary, defensible label; interpret
  through **scenario deltas**. **CO₂ = fuel × 3.16** is exposed only as a derived display.
- **Aircraft assumption:** default every flight to a **Boeing 747** (most common type) with
  one representative cruise fuel flow — no per-flight class inference.
- **Must-ship recommendation tier:** **greedy repair loop** over departure-time (±5/10/15 min)
  and altitude (±2,000/4,000 ft) candidates, scored against one system objective. A*/Dijkstra
  lateral reroute is **stretch**.
- **Demo safety:** precompute **baseline + recommended** scenarios to static artifacts.
  Live `/api/solve` is an *enhancement* that gracefully degrades to the frozen artifacts.

---

## 1. Product Story (operator workflow, not a solver demo)

| Step | Operator question | What the app shows |
|------|-------------------|--------------------|
| 1 | What is happening? | Flight trajectories, storms, sector load, fuel-density hotspots for one frozen snapshot + time window. |
| 2 | Why is it costly/risky? | Which flights are exposed to headwinds, convective weather, or overloaded sector-time bins. |
| 3 | What should change? | A small set of operationally legible scenario changes + before/after delta. |

**Framing guardrail:** this is a decision-support *prototype*, not a certified planning
tool. The bundle has no aircraft type, mass, engine, or climb/descent profile — fuel is an
**estimated proxy** read primarily through consistent scenario deltas.

## 2. Design Principles
- Ship a complete vertical slice before adding sophistication.
- Separate **visualization metrics** (H3) from **operational constraints** (sector×time).
- Prefer **explainable** recommendations over opaque optimization claims.
- **Precompute** the baseline + recommended scenarios; never require a live API call for the
  core demo.
- Lock one **frozen showcase snapshot** until the end-to-end flow is stable.

## 3. Success Criteria
A judge clicks a high-cost flight → understands the cause → toggles to the recommended
scenario → immediately sees a credible reduction in estimated fuel proxy, storm exposure,
or sector overload. Everything renders from precomputed artifacts; the live solver is a
bonus, not a dependency.

## 4. Scope Guardrails

| Tier | Definition |
|------|------------|
| **Must ship** | One historical snapshot end-to-end; interactive map; flight detail panel; wind-aware segment model; storm overlay; sector-load overlay; H3 fuel-density map; baseline/recommended toggle; greedy-repair recommendation (time + altitude). |
| **Stretch** | Multi-snapshot selector; animated time slider (`TripsLayer`); OpenAP enrichment; A*/Dijkstra lateral reroutes; live `/api/solve` what-if sliders; candidate-selection MILP/QUBO; Monte-Carlo sensitivity. |
| **Out of scope** | Required live-API dependence during the demo; Kafka/Flink; auth; production DB; certified fuel-burn; nationally optimal tactical routing; Three.js frontend (`docs/FRONTEND.md` superseded). |

## 5. System Architecture

```
hackathon_data_bundle/  +  cached Open-Meteo winds
            │
            ▼
   Python precompute pipeline  (pipeline/ — pure, importable functions)
            │  writes
            ▼
   Static JSON artifacts  (backend/data_cache/<snapshot>/*.json)
            │  served by
            ▼
   FastAPI backend  (backend/ — GET artifacts + POST /api/solve live what-if)
            │  HTTP/JSON
            ▼
   React + Vite + deck.gl + MapLibre frontend  (web/)
            │
            ▼
   Interactive operator demo
```

**Key design move:** the recommendation/fuel/sector logic lives in **pure importable
functions** in `pipeline/`. `build.py` calls them offline to freeze artifacts; the FastAPI
`/api/solve` route calls the *same* functions live. No logic is duplicated, and the live
endpoint can never diverge from the frozen baseline.

**Repo reconciliation tasks**
- Reuse `backend/main.py` + `backend/routers/{routing,sectors,weather}.py` (currently empty)
  per the `docs/API.md` contract below.
- Create `pipeline/` (new): `load.py, wind.py, fuel.py, weather.py, sectors.py, h3agg.py,
  recommend.py, build.py`. Move the intended logic of `src/algorithm/*` and `src/data/*`
  here; delete or leave the `src/` stubs (note them as superseded).
- Create `web/` (new): Vite + React + deck.gl + MapLibre.
- Mark `docs/FRONTEND.md` (Three.js) **superseded** by §9 here; keep `docs/{API,DATA,ALGORITHM}.md`
  as living contracts, updated to match the schemas in §8.

## 6. Data Inputs

| Input | Location | Use |
|-------|----------|-----|
| Routes | `asked_at_<ts>/routes.json` | Flight identity, O/D ICAO, takeoff/landing times, `cruise_altitude_ft`, `cruise_speed_kt` (TAS), `lats`/`lons` waypoints, `is_airborne`. Constant-cruise model. |
| Radar | `asked_at_<ts>/wx/refc|retop/*.npz` | `refc` dBZ, `retop` echo-top ft, 256×358 grids, 15-min strips. Mask: refc ≤ −50 nodata, retop < 0 nodata. |
| Sectors | `hackathon_data_bundle/sectors.geojson` | HIGH/LOW polygons + `capacity`. Capacity applies to **sector occupancy over time**, not to H3 cells. |
| Winds | Cached Open-Meteo pressure-level fields | Wind speed + meteorological direction at selected pressure levels and hours. |

**Showcase snapshot selection (do this first):** scan all 11 snapshots; pick the one that
maximizes a demo-quality score = (fraction of flights storm-exposed) + (count of overloaded
sector-time bins) + (Open-Meteo wind availability for that date). A snapshot with visible
storms *and* sector overload makes the recommendation story land. **Wind caveat:** some
snapshots are dated in 2026; confirm Open-Meteo's historical-forecast archive actually
returns winds for the chosen date, else fall back to the zero-wind path (§9).

## 7. Modeling Separation (keeps the demo defensible)

| Unit | Role | Metrics |
|------|------|---------|
| H3 hexagons | **Visualization** | Fuel density, traffic density, storm-exposure density. |
| Sector × time bin | **Constraint model** | Occupancy, capacity ratio, overload. |
| Flight trajectory | **Recommendation model** | Fuel proxy, wind exposure, storm exposure, candidate changes. |

State of a flight = `(geographic cell, altitude band, time bin)` — lets us distinguish two
aircraft through the same region at different times/altitudes. The simulator *evaluates* a
scenario; the recommendation engine *proposes* a better scenario to evaluate.

## 8. Algorithms & Frozen Contracts

### 8.1 Wind-aware fuel proxy (`pipeline/fuel.py`, `pipeline/wind.py`)
Per route segment: ellipsoidal distance + bearing via `pyproj.Geod`. Sample cached wind near
the segment midpoint at the estimated timestamp; project onto track:
```
along_track_wind = east_wind*sin(track_bearing) + north_wind*cos(track_bearing)
ground_speed     = max(true_airspeed + along_track_wind, 150)          # knots
segment_fuel     = representative_fuel_flow * segment_distance / ground_speed
```
- Meteorological wind direction = direction wind comes *from*; convert to east/north
  carefully and **test the sign**: tailwind must lower travel time, headwind must raise it.
- **Aircraft default: Boeing 747** (most common type assumption) — use a single
  representative cruise fuel flow, no per-flight class inference. OpenAP enrichment (B744
  cruise fuel-flow vs altitude/mass/speed) is a stretch refinement on the same assumption.

  **Engine averaging (justified).** The 747-400 shipped with three engine options whose
  cruise fuel flow is nearly identical — averaging them into one constant is sound, and
  because fuel is a *relative proxy read via before/after deltas*, any constant bias cancels
  in the comparison:

  | Engine | Cruise thrust | Total fuel flow (390 t long-range cruise) |
  |--------|--------------|--------------------------------------------|
  | GE CF6-80C2B1F | 56,700 lbf | 13,144 kg/h |
  | PW PW4056-3 | 56,000 lbf | 13,184 kg/h |
  | RR RB211-524H2 | 58,000–60,600 lbf | 13,328 kg/h |
  | **Average** | — | **≈13,219 kg/h** |

  Spread = 184 kg/h ≈ **1.4%** (σ ≈ 0.6%); RR lags GE/PW by ~1.5%. **Pin
  `representative_fuel_flow`** to the heavy-cruise average **≈13,200 kg/h**, or
  **≈11,000 kg/h** for typical operational cruise weight — the constant is narrated, and the
  ≤1.5% engine deviation is immaterial to relative scenario deltas. Sources:
  [Wikipedia 747-400](https://en.wikipedia.org/wiki/Boeing_747-400),
  [Airliners.net SFC thread](https://www.airliners.net/forum/viewtopic.php?t=738287),
  [FlightDeckFriend fuel burn](https://www.flightdeckfriend.com/ask-a-pilot/how-much-fuel-does-a-jumbo-jet-burn/).

### 8.2 Timing approximation (`pipeline/load.py`)
Do **not** infer timestamp from waypoint index. Use cumulative distance:
```
point_time ≈ takeoff_time + (cumulative_distance / total_distance) * scheduled_duration
```
Optionally recompute after wind-adjusted segment times are known.

### 8.3 Convective exposure (`pipeline/weather.py`)
At each densified point, pick the radar strip covering the timestamp; flag
`storm_exposed = (refc ≥ 40 dBZ) AND (cruise_altitude_ft < retop_ft)`. Keep storm exposure
**separate** from fuel — fuel rises only when an avoidance candidate actually adds
time/distance. Map lat/lon→grid `(i,j)` via the documented inverse in
`hackathon_data_bundle/documentation/wx/FILE_FORMAT.md`; respect nodata masks.

### 8.4 Sector occupancy (`pipeline/sectors.py`)
Sample each trajectory every ~5 min; for each sample find the active HIGH/LOW sector
(shapely) and increment that sector-time bin.
```
sector_load_ratio(s,t) = occupancy(s,t) / capacity(s)
sector_overload(s,t)   = max(0, occupancy(s,t) - capacity(s))
```
Reproduce the Seattle@38k example from `documentation/sectors/FILE_FORMAT.md` as a test.

### 8.5 H3 aggregation (`pipeline/h3agg.py`)
Densify routes (~10 nm), map to H3 (`h3-py`, res 4–5; tune for CONUS cell count). Per cell:
total in-cell fuel, flight count, mean fuel/flight, storm-exposure density.

### 8.6 Recommendation engine (`pipeline/recommend.py`) — **greedy repair loop (must ship)**
Every recommendation answers: *what changed, why it helps, what it saves, what it trades off.*

Candidate classes:
| Candidate | Search space | Why it helps |
|-----------|--------------|--------------|
| Departure-time shift | −15,−10,−5,+5,+10,+15 min | Relieve overloaded sector-time bins / avoid a weather window. |
| Altitude alternative | ±2,000 / ±4,000 ft | Capture better winds or clear an echo-top. |
| Lateral reroute *(stretch)* | A*/Dijkstra, only storm/high-cost flights | Trade a bounded detour for lower risk. |

Objective (weights visible in code, narrated in demo):
```
total_cost = fuel_proxy + λ_storm*storm_risk + λ_overload*sector_overload + λ_change*change_penalty
```
Greedy repair loop: (1) run baseline, find storm-exposed flights + overloaded bins; (2)
generate candidates only for contributing flights; (3) re-score each against the objective;
(4) apply best feasible improvement; (5) update occupancy, repeat until no worthwhile gain
or iteration cap. **Never claim a global optimum.** Solver ladder: rule-based → greedy
(must ship) → A*/Dijkstra (stretch) → MILP/QUBO (only if integration is already stable).

### 8.7 FastAPI contract (`backend/`, aligning `docs/API.md`)
- `GET /health` — liveness.
- `GET /api/snapshots` — list of available snapshots + the frozen showcase id.
- `GET /api/flights?scenario=baseline|recommended` — renderable routes + per-flight metrics.
- `GET /api/sectors` + `GET /api/sector_load?t=<bin>` — geometry + time-binned load ratios.
- `GET /api/weather?t=<iso>` — storm regions/metadata for the strip covering `t`.
- `GET /api/h3?mode=fuel|traffic|storm&scenario=...` — aggregated H3 metrics.
- `GET /api/summary?scenario=...` — system totals + deltas.
- `POST /api/solve` *(stretch)* — `{scenario, λ_storm, λ_overload, λ_change, candidate_classes,
  iterations}` → recommended trajectories + summary, computed live by the *same* pipeline
  functions. Frontend falls back to the frozen `recommended` artifact if this fails/slow.

### 8.8 Frozen JSON / artifact schemas (commit samples before algorithms are done)
```
summary.json          { scenario, totals:{fuel_proxy, co2, storm_exposed_flights,
                        overloaded_bins}, baseline_ref, deltas:{fuel_proxy_pct, ...} }
recommendations.json  [ { flight_key, candidate:{type, value}, reason, before:{...},
                        after:{...}, tradeoff } ]
flights_baseline.json [ { flight_key, flight_number, origin, destination,
                        cruise_altitude_ft, path:[[lon,lat],...], fuel_proxy, co2,
                        headwind_kt, tailwind_kt, storm_exposed_nm, max_refc,
                        sectors_crossed:[...], peak_sector_load } ]
flights_recommended.json   # same shape; modified flights (or full scenario)
h3_<mode>.json        [ { h3, value, n_flights } ]      # mode ∈ fuel|traffic|storm
sectors.json          { type:"FeatureCollection", features:[ {…, properties:{name,
                        capacity, load_by_bin:{t:ratio}} } ] }
storms.json           [ { t_from, t_to, polygons:[...], max_refc } ]
```
`flight_key = (flight_number, take_off_time, origin_airport_icao)`.

## 9. Frontend (`web/`) — React + Vite + deck.gl + MapLibre

Basemap: MapLibre GL with a free style (e.g. CARTO dark, no token). Layers:
| Layer | Purpose |
|-------|---------|
| `PathLayer` | Baseline & recommended routes; `getColor` by fuel proxy; `pickable`. |
| `GeoJsonLayer` (sectors) | Color by `sector_load_ratio` at the selected time. |
| `GeoJsonLayer` (storms) | Convective regions from `storms.json`. |
| `H3HexagonLayer` | Switch fuel / traffic / storm-exposure density. |
| `ScatterplotLayer` | Airports + optional selected-flight waypoints. |

**Flight detail panel:** flight id, O/D, cruise altitude; route distance + fuel proxy (+CO₂);
headwind/tailwind split; storm-exposed distance + max reflectivity; sectors crossed + peak
load; recommended change, expected benefit, operational trade-off.

**Controls:** baseline/recommended toggle, layer toggles, color-scale legend, summary header
(total fuel proxy, % saved, overloaded bins resolved). Snapshot selector + time slider +
live `/api/solve` sliders are stretch.

## 10. Build Order

| Phase | Objective | Milestone |
|-------|-----------|-----------|
| 0 | Validate one frozen snapshot | Known-good parser; one sector lookup; one radar lookup; showcase snapshot chosen. |
| 1 | Vertical slice | FastAPI serves `flights_baseline.json`; map renders routes; one flight clickable; zero-wind fuel proxy visible. |
| 2 | Wind model | Cached pressure-level winds alter ground speed + fuel proxy. |
| 3 | Risk context | Storms + sector overloads render correctly. |
| 4 | Recommendations | Greedy repair loop works end-to-end; recommended artifact + toggle. |
| 5 | Polish | Toggle, legends, summary cards, stable demo branch. Stretch: `/api/solve`, time slider, multi-snapshot. |

## 11. Team Split
- **Pipeline & metrics:** data load, route geometry, cached winds, fuel proxy, artifact gen.
- **Risk & recommendations:** radar exposure, sector occupancy, candidate generation, repair
  loop, optional A*.
- **Backend & API:** FastAPI routes over the shared pipeline functions; `/api/solve`.
- **Frontend & demo UX:** MapLibre/deck.gl layers, controls, detail panel, summary cards.
- **Shared:** freeze schemas early, commit sample JSON, keep a stable presentation branch.

## 12. QA Checklist
- **Geometry:** known route distances plausible; densified tracks preserve endpoints; coords in bounds.
- **Winds:** tailwind lowers time, headwind raises it; direction conversion tested vs a hand calc.
- **Fuel proxy:** zero-wind proxy ≈ distance/TAS × representative fuel flow.
- **Storms:** exposure triggers only when refc ≥40 *and* alt < echo-top; nodata masks respected.
- **Sectors:** occupancy counted by sector × time bin; overload uses capacity, not H3 density.
- **Recommendations:** selected changes improve the objective; trade-offs shown, not hidden.
- **API:** every GET returns the frozen schema; `/api/solve` degrades gracefully; CORS ok.
- **Frontend e2e:** map renders, click panel works, toggle updates paths + heatmap + summary.

## 13. Risk Register
| Risk | Mitigation |
|------|-----------|
| No aircraft type in bundle | Default to **Boeing 747** with a fixed representative fuel flow; label fuel a **proxy**; emphasize relative scenario deltas. |
| Open-Meteo failure / 2026-date archive gap | **Cache winds before the demo**; zero-wind fallback as the safe default. |
| Live `/api/solve` slow/unstable on stage | Precompute baseline + recommended; live solve is optional, degrades to frozen artifacts. |
| Rendering overload (16.7k flights) | Downsample geometry; render airborne / top-N high-cost flights; keep `flights_*.json` payloads lean. |
| Rerouting rabbit hole | Ship time/altitude first; A* only after integration is stable. |
| Solver rabbit hole | Greedy repair loop is the target; MILP/QUBO are stretch. |
| Two-design confusion in repo | This plan reconciles it: FastAPI + deck.gl; Three.js docs superseded; `src/` stubs retired. |

## 14. Demo Script
1. Show the national airspace map with routes, storms, and sector load.
2. Switch on the fuel-density heatmap.
3. Click one high-cost / storm-exposed flight.
4. Explain the headwind, weather, or sector-load cause.
5. Toggle to the recommended scenario.
6. Show the change in fuel proxy, storm exposure, or overloaded sector-time bins.
7. Close: **simulate, explain, recommend, compare.**

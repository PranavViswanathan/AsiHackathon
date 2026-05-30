# ASI Boston Hackathon 2026

Core pipeline for the airspace challenge: *given a day of US flight plans, weather,
and airspace, build something that makes the system better.*

```
routes ──► positions(t) ──► sector + altitude band ──► occupancy vs capacity ──► over-demand
 data        geometry          sectors                   occupancy
```

This repo gives you the reusable foundation every project idea (congestion
heatmaps, weather-aware rerouting, ground-delay optimisation, 4D viz) builds on:
roll every flight forward in time and count how many sit in each airspace sector,
versus that sector's capacity.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The data bundle lives in `data/` (gitignored). Override its location with the
`AIRSPACE_DATA` env var if it's elsewhere.

## Run the demo

```bash
.venv/bin/python scripts/demo_overdemand.py
# options: --scenario 2025-08-21T18:00:00Z  --band HIGH|LOW  --step 15  --out out/x.png
```

Prints the worst sector over-demand breaches and writes a CONUS map colouring each
sector by peak occupancy / capacity, with flight positions overlaid at the busiest
moment.

```bash
.venv/bin/python scripts/demo_weather.py --scenario 2025-08-21T18:00:00Z
```

Joins weather to congestion: ranks over-demand breaches by how many of their
flights are flying through weather (`refc >= 40 dBZ` and below the echo top), and
plots reflectivity + over-demand sectors + weather-blocked flights for the worst
moment. `2025-08-21` is a good example day where storms and congestion collide.

## The `airspace` package

| Module | What it does |
| --- | --- |
| `data.py` | Load scenarios (`load_scenario`) and sectors (`load_sectors`). `Flight`/`Scenario` dataclasses. Handles plain-or-gzipped files transparently. |
| `geometry.py` | `positions_at(flights, t)` — where each *active* flight is at time `t`, via linear-in-time interpolation along its waypoint path (the bundle's constant-cruise model). |
| `sectors.py` | `SectorIndex` — per-band shapely STRtree; `assign(...)` / `assign_flight_positions(...)` map points to the sector that contains them. |
| `occupancy.py` | `occupancy_timeline(scenario, index)` → per-sector counts over a time grid; `.over_demand_events()`, `.peak_per_sector()`, `.series(name)`. |
| `weather.py` | `WeatherForecast` — load the refc/retop strips, `.sample(lats, lons, t)`, `.blocked(lats, lons, alt_ft, t)`; `blocked_flights(scn, wx, t)` returns active flights + a weather-blocked mask. |

```python
from airspace import load_scenario, load_sectors, SectorIndex, occupancy_timeline

scn = load_scenario("2025-07-08T22:00:00Z")
idx = SectorIndex(load_sectors())
tl  = occupancy_timeline(scn, idx, step_minutes=15)

for e in tl.over_demand_events()[:5]:
    print(e)   # {'sector', 'time', 'count', 'capacity', 'overage'}
```

## Data notes / gotchas

- **Altitude bands:** LOW `[0, 35k) ft`, HIGH `[35k, 60k) ft`. A flight is queried
  against the band it cruises in (`Flight.band`).
- **Sector lookup direction:** shapely's `STRtree.query` evaluates the predicate as
  `input.predicate(tree_geom)`, so we use `point.intersects(sector)` — *not*
  `sector.contains(point)` (which silently matches nothing). See `sectors.py`.
- **Timesteps:** default 15-min grid spans first departure → last landing, which
  lines up with the 15-min weather strips.
- **Weather:** all 11 scenarios ship a full HRRR forecast under `data/asked_at_*/wx/`
  (refc + retop, 73 strips each). A point is weather-blocked where `refc >= 40 dBZ`
  **and** flight altitude `<= retop`. Note `STRtree.query` and the grid row/col
  mapping are the two easy things to get backwards — both are handled in the modules.
- Files are already decompressed on disk despite the `.gz` names in the docs; the
  loaders handle both.

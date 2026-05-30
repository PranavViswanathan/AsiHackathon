# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline for the ASI Boston Hackathon 2026 airspace challenge: *given a day of US
flight plans, weather, and airspace, build something that makes the system better.*
The code turns the raw data bundle into per-sector congestion and weather signals.

## Setup & commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # numpy, shapely, matplotlib

.venv/bin/python scripts/demo_overdemand.py         # congestion map for a scenario
.venv/bin/python scripts/demo_weather.py --scenario 2025-08-21T18:00:00Z
```

- **Always run via `.venv/bin/python`** (or activate the venv); deps are not on the system Python.
- Scripts in `scripts/` insert the repo root on `sys.path` themselves, so run them from anywhere. Library code (`from airspace import ...`) only resolves when the repo root is the working dir or on `PYTHONPATH`.
- There is **no test suite** and no lint config. Validation is done by running the demos and eyeballing the `out/*.png` maps and printed breach tables.

## Data layout (gitignored, ~226 MB)

The bundle lives in `data/` and is **gitignored** — never commit it. Override its
location with the `AIRSPACE_DATA` env var. Structure:

- `data/sectors.geojson` — shared; 712 ATC sector polygons.
- `data/asked_at_<ISO>Z/routes.json` — one snapshot of ~14.7k flights.
- `data/asked_at_<ISO>Z/wx/refc/`, `.../retop/` — 73 weather strips each (15-min).

All 11 scenarios ship both routes and full weather. Despite the `.gz` names in the
official docs (`documentation/*/FILE_FORMAT.md`), files on disk are **decompressed**;
loaders sniff the gzip magic bytes and handle either form.

## Architecture

The whole package is one data-flow chain. Each stage is a module under `airspace/`:

```
routes ──► positions(t) ──► sector + altitude band ──► occupancy vs capacity ──► over-demand
data.py     geometry.py        sectors.py                occupancy.py
                                              weather.py ──► refc/retop ──► flights "in weather"
```

- **`data.py`** — `load_scenario(id)` → `Scenario` of `Flight` dataclasses; `load_sectors()`. `Flight.band` ("HIGH" / "LOW") and `Flight.key` (unique identity) live here. `DATA_ROOT` resolves from `AIRSPACE_DATA` or `./data`.
- **`geometry.py`** — `positions_at(flights, t)` reconstructs each flight's lat/lon at time `t`. Relies on the bundle's modelling assumption: **constant cruise altitude/speed, no climb/descent**, so progress is linear in time, mapped onto cumulative distance along the waypoint path.
- **`sectors.py`** — `SectorIndex` keeps **one shapely STRtree per altitude band**; `assign_flight_positions` routes each flight to the band it cruises in. `index.capacity[name]` gives a sector's capacity.
- **`occupancy.py`** — `occupancy_timeline(scenario, index)` → `OccupancyTimeline`. Key methods: `.over_demand_events()` (sorted worst-first), `.peak_per_sector()`, `.series(name)`.
- **`weather.py`** — `WeatherForecast.load(id)`; `.sample(lats, lons, t)`, `.blocked(...)`, and `blocked_flights(scn, wx, t)`. The block rule is **`refc >= 40 dBZ AND flight_altitude <= retop`**.

`scripts/demo_weather.py` shows the intended way to combine layers: take `over_demand_events()`, then for each breach time use `blocked_flights` + `assign_flight_positions` to count weather-blocked flights per sector → "weather-driven over-demand."

## Non-obvious gotchas (these cost real debugging time)

- **STRtree predicate direction.** shapely 2's `STRtree.query(points, predicate=...)` evaluates `input_geom.predicate(tree_geom)`, *not* `tree_geom.predicate(input)`. So sector lookup uses `point.intersects(sector)` — `predicate="contains"` silently matches **nothing**. See `sectors.py`.
- **Altitude bands.** LOW `[0, 35k) ft`, HIGH `[35k, 60k) ft`. The same footprint index exists in both bands (`LOW_042` / `HIGH_042`); always filter by band, and query a flight against the band it actually cruises in.
- **Weather grid orientation.** `(256, 358)` matrix, **row 0 = north, col 0 = west**. `weather.latlon_to_rowcol` inverts the docs' `pixel_top_left_latlon`; getting the lat→row sign backwards is the classic bug. nodata sentinels: `refc <= -50`, `retop < 0` (handled so they never falsely "block").
- **GeoJSON / shapely coordinate order is `(lon, lat)`** = `(x, y)`. Flight data and most code pass `(lat, lon)`; mind the swap at the shapely boundary.
- **Timesteps** default to a 15-min grid, which intentionally lines up with the 15-min weather strips so occupancy and weather can be joined directly.
- **Findings to expect:** weather-driven over-demand is *rare* — most congestion is volume-driven. `2025-08-21` is the example day where storms and congestion actually collide.

## Git

Default branch is `main`; active work has been on `kevin-test`. Commit code only — the `data/`, `.venv/`, and `out/` dirs are gitignored.

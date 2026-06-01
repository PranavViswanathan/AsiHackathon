# AirFlow

Weather-aware fuel and airspace optimization for a full day of US flight plans, built for the ASI Hackathon.

## Overview

AirFlow takes a point-in-time snapshot of US air traffic (~16,687 flights), estimates each flight's fuel burn as a function of aircraft type, altitude, and winds aloft, and then recommends operationally simple changes (cruise altitude, lateral storm detours, small departure shifts) that cut total fuel, keep flights clear of convective weather, and relieve over-demand airspace sectors. The result is an interactive map: flights colored by fuel cost, an H3 energy heatmap, sector load, animated weather radar and flight playback, and a baseline vs optimized comparison with the dollars saved.

The decision loop is: observe (what is happening) -> explain (why a flight is costly or risky) -> recommend (a small set of changes) -> compare (before vs after).

## Docs

- [Architecture](docs/ARCHITECTURE.md) - system design and data flow
- [Data](docs/DATA.md) - data sources, schemas, and the artifact contract
- [Algorithm](docs/ALGORITHM.md) - fuel model, wind, storms, and the optimizer
- [API](docs/API.md) - backend endpoint reference
- [Frontend](docs/FRONTEND.md) - UI components and visualization
- [Agents](docs/AGENTS.md) - Claude Code subagent setup and usage

A running build log lives in [CHECKPOINT.md](CHECKPOINT.md).

## Tech Stack

- Pipeline: Python, NumPy, Shapely, pyproj, h3, OpenAP (fuel), Pillow (radar frames)
- Weather/wind: HRRR reflectivity + echo-top grids from the bundle; winds aloft from Open-Meteo (cached)
- Backend: FastAPI, Uvicorn
- Frontend: Next.js 14, TypeScript, Tailwind CSS, deck.gl + MapLibre GL (2D), Three.js via react-three-fiber (3D), Recharts

## Quick Start

One command builds the data (with winds) and runs both servers:

```
make run-full
```

That runs: install deps -> create .env -> wind build -> export static JSON -> start backend (:8000) and frontend (:3000). Open http://localhost:3000.

Step by step instead:

```
make install            # pip + npm deps
make build-wind         # pipeline with Open-Meteo winds (cached after first run)
make export-web         # write lean static JSON into frontend/public/data/
make frontend           # Next.js dev server on :3000
make backend            # optional: FastAPI on :8000
```

Offline (no network) build, with smaller savings since winds are off: `make build && make export-web`.

Point at a different scenario:

```
make build-wind SCENARIO=asked_at_2025-07-01T21:30:00Z
```

## Data

Scenarios live in `data/hackathon_data_bundle/`. Each scenario contains:

```
routes.json       16,687 US flights with lat/lon waypoints
wx/refc/          composite reflectivity (precipitation) grids, 15-min strips
wx/retop/         storm echo-top altitude grids, 15-min strips
```

Shared across scenarios: `sectors.geojson` (712 synthetic ATC sectors with capacity). See [docs/DATA.md](docs/DATA.md) for schemas and the generated artifact contract.

## Results

Showcase snapshot `asked_at_2025-05-29T21:00:00Z`, wind build:

```
Flights:                16,687
Total fuel (baseline):  72.8M kg  (230M kg CO2)
Fuel saved:             2.44M kg  (3.35%)  =>  ~$2.07M
Over-demand sectors:    169 -> 46
Optimizer changes:      13,264 altitude, 4,758 departure shifts, plus A* storm reroutes
```

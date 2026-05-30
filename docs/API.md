# API Reference

The backend is a FastAPI application (`backend/main.py`) that loads a scenario,
runs the solver on demand, and serves trajectories, sector loads, and weather to
the frontend. Routes are grouped into routers under `backend/routers/`. CORS is
opened to `FRONTEND_URL`. All payloads are JSON.

Base path: `/api` (except `/health`).

## POST /api/solve

Run the routing optimizer over a scenario and return the result.

Request body:

```json
{
  "scenario_dir": "./data/hackathon_data_bundle/asked_at_2025-05-29T21:00:00Z",
  "n_flights": 16687,
  "lambda_sector": 1.0,
  "lambda_weather": 1000.0,
  "iterations": 10
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `scenario_dir` | string | Path to the scenario directory to load |
| `n_flights` | number | Cap on flights to route (subset for speed; full set otherwise) |
| `lambda_sector` | number | Weight on the sector-congestion cost term |
| `lambda_weather` | number | Weight on the weather-penalty cost term |
| `iterations` | number | Number of iterative-Dijkstra passes |

Response:

```json
{
  "trajectories": [
    { "flight_number": "...", "cells": [[lat, lon, alt, t], ...] }
  ],
  "sector_loads": { "HIGH_006": { "0": 12, "1": 18, ... } },
  "history": [ { "iteration": 1, "over_demand": 134 }, ... ],
  "stats": {
    "flights_rerouted": 0,
    "sectors_over_capacity": 0,
    "weather_conflicts": 0,
    "total_deviation": 0.0
  }
}
```

- `trajectories` — final optimized path per flight as a sequence of space-time
  cells.
- `sector_loads` — per-sector flight count keyed by time bin.
- `history` — over-demand count per iteration, for the convergence chart.
- `stats` — summary metrics for the results panel.

## GET /api/sectors

Return all sectors with their geometry and current load versus capacity.

Response:

```json
[
  {
    "name": "HIGH_006",
    "altitude_from_ft": 35000,
    "altitude_to_ft": 60000,
    "capacity": 20,
    "load": 17,
    "geometry": { "type": "Polygon", "coordinates": [ ... ] }
  }
]
```

`load` reflects the most recent solve (peak across time bins, or 0 before any
solve). The frontend uses this to color sectors green/yellow/red.

## GET /api/weather

Return the weather grids for a given time window.

Query parameters:

| Param | Type | Meaning |
| --- | --- | --- |
| `t` | ISO 8601 timestamp | The instant whose 15-minute strip to return |

Example: `GET /api/weather?t=2025-05-29T21:00:00Z`

Response:

```json
{
  "valid_from": "2025-05-29T20:52:30Z",
  "valid_to": "2025-05-29T21:07:30Z",
  "extent": { "lat_max": 55.7765, "lat_min": 21.943, "lon_min": -135.0, "lon_max": -67.5 },
  "shape": [256, 358],
  "refc": [[...]],
  "retop": [[...]]
}
```

`refc` is composite reflectivity in dBZ; `retop` is storm top altitude in feet.
The strip nearest `t` is selected.

## GET /api/flights

Return all flights in the currently loaded scenario.

Response:

```json
[
  {
    "flight_number": "...",
    "take_off_time": "2025-05-29T21:10:00Z",
    "scheduled_landing_time": "2025-05-29T23:40:00Z",
    "origin_airport_icao": "KJFK",
    "destination_airport_icao": "KLAX",
    "cruise_altitude_ft": 37000,
    "cruise_speed_kt": 460,
    "lats": [ ... ],
    "lons": [ ... ],
    "is_airborne": false
  }
]
```

## GET /api/sector_load

Return per-sector flight count versus capacity for a single time window.

Query parameters:

| Param | Type | Meaning |
| --- | --- | --- |
| `t` | number | Time-bin index whose loads to return |

Example: `GET /api/sector_load?t=4`

Response:

```json
[
  { "name": "HIGH_006", "capacity": 20, "load": 23, "over_demand": true },
  { "name": "LOW_112", "capacity": 15, "load": 9,  "over_demand": false }
]
```

`over_demand` is `load > capacity`. Drives the per-timestep sector view.

## GET /health

Liveness probe.

Response:

```json
{ "status": "ok" }
```

# API Reference

The backend is a FastAPI application (`backend/main.py`) that serves the
precomputed per-snapshot artifacts written by `src.build` (`flights.json`,
`summary.json`, `h3.json`) and reads sectors + weather straight from the data
bundle. The active scenario is selected by the `SCENARIO_DIR` environment
variable (`backend/config.py`); artifacts are built on first access if missing.

Routes are grouped into routers under `backend/routers/`. CORS is opened to
`FRONTEND_URL`. All payloads are JSON. Base path: `/api` (except `/health` and
`/`).

> **Status:** flight fuel estimates, the scenario summary, sectors, and weather
> are live. Sector `load`/`over_demand` are `0`/`false` until the Phase 4
> occupancy pass lands, and `h3` is `[]` until the Phase 4 aggregation lands.
> `POST /api/solve` currently (re)runs the pipeline; the optimizer knobs are
> reserved for Phase 5.

## GET /api/flights

All flights in the active scenario with their baseline fuel estimate.

```json
[
  {
    "id": "TEST1_2025-05-29T21:10:00+00:00_KJFK",
    "flight_number": "TEST1",
    "origin": "KJFK",
    "destination": "KLAX",
    "cruise_altitude_ft": 37000.0,
    "cruise_speed_kt": 460.0,
    "is_airborne": false,
    "lats": [40.64, 39.0, 34.0],
    "lons": [-73.78, -90.0, -118.4],
    "aircraft_class": "narrowbody",
    "distance_nm": 2143.5,
    "time_hr": 4.66,
    "fuel_kg": 11650.0,
    "co2_kg": 36814.0,
    "base_fuel_kg": 11540.0,
    "headwind_nm": 820.0,
    "tailwind_nm": 1323.5,
    "mean_along_track_kt": 14.2,
    "storm_nm": 0.0,
    "max_refc_dbz": 0.0,
    "storm_penalty_kg": 0.0
  }
]
```

`id` = `"{flight_number}_{take_off_time}_{origin_airport_icao}"`.

The Phase 3 fields: `base_fuel_kg` is the zero-wind, no-storm reference;
`headwind_nm`/`tailwind_nm` split the route by along-track wind sign;
`mean_along_track_kt` is the distance-weighted along-track wind (+ = tailwind);
`storm_nm`/`max_refc_dbz`/`storm_penalty_kg` describe convective exposure. When
the build runs zero-wind (the default for the backend), the wind fields are 0 and
`fuel_kg` = `base_fuel_kg` + `storm_penalty_kg`.

## GET /api/flight/{id}

One flight's full record (same shape as a `/api/flights` element). The path is
matched greedily, so the `id` (which contains `:` and `+`) can be passed
verbatim. `404` if no flight matches.

## GET /api/h3

The H3 energy heatmap cells: `[{ "h3", "fuel_kg", "n_flights", "mean_kg",
"congestion" }]`. Empty `[]` until the Phase 4 aggregation lands.

## GET /api/summary

Scenario totals (builds artifacts on first call).

```json
{
  "snapshot": "asked_at_2025-05-29T21:00:00Z",
  "asked_at": "2025-05-29T21:00:00+00:00",
  "n_flights": 16687,
  "wind_enabled": false,
  "storms_enabled": true,
  "total_fuel_kg": 63206582.6,
  "total_base_fuel_kg": 63193079.2,
  "wind_delta_fuel_kg": 0.0,
  "total_co2_kg": 199732801.0,
  "total_distance_nm": 11478388.6,
  "total_storm_nm": 15903.0,
  "n_storm_flights": 361,
  "total_storm_penalty_kg": 13503.4,
  "by_class": { "narrowbody": 13248, "regional": 3189, "widebody": 250 }
}
```

`total_base_fuel_kg` is the zero-wind / no-storm total; `wind_delta_fuel_kg` is
the net fuel change from wind alone (0 when winds are disabled). With
`AIRFLOW_WIND=1` / `make build-wind`, `wind_enabled` is `true` and the wind delta
is populated.

## POST /api/solve

(Re)build the active scenario's artifacts and return the summary.

Request body (all fields optional):

| Field | Type | Meaning |
| --- | --- | --- |
| `force_rebuild` | boolean | Rebuild even if artifacts already exist |
| `scenario_dir` | string | Reserved: per-request scenario override |
| `lambda_sector` | number | Reserved for the Phase 5 optimizer |
| `lambda_weather` | number | Reserved for the Phase 5 optimizer |
| `iterations` | number | Reserved for the Phase 5 optimizer |
| `n_flights` | number | Reserved for the Phase 5 optimizer |

Response: the same object as `GET /api/summary`.

## GET /api/sectors

All 712 sectors with geometry and capacity.

```json
[
  {
    "name": "HIGH_006",
    "altitude_from_ft": 35000,
    "altitude_to_ft": 60000,
    "capacity": 20,
    "load": 0,
    "geometry": { "type": "Polygon", "coordinates": [ ... ] }
  }
]
```

`load` is the peak occupancy across time bins once the Phase 4 occupancy pass
exists; `0` before then. The frontend colors sectors green/yellow/red from
`load` vs `capacity`.

## GET /api/sector_load

Per-sector occupancy versus capacity for one time-bin index.

| Param | Type | Meaning |
| --- | --- | --- |
| `t` | number | Time-bin index (default `0`) |

```json
[
  { "name": "HIGH_006", "capacity": 20, "load": 0, "over_demand": false }
]
```

`over_demand` is `load > capacity`.

## GET /api/weather

The refc/retop grids for the 15-minute strip covering an instant.

| Param | Type | Meaning |
| --- | --- | --- |
| `t` | ISO 8601 timestamp | The instant whose strip to return (required) |
| `step` | number | Subsample stride for the grids (default `1`, max `64`) |

Example: `GET /api/weather?t=2025-05-29T21:00:00Z&step=4`

```json
{
  "valid_from": "2025-05-29T20:52:30+00:00",
  "valid_to": "2025-05-29T21:07:30+00:00",
  "extent": { "lat_max": 55.7765, "lat_min": 21.943, "lon_min": -135.0, "lon_max": -67.5 },
  "shape": [64, 90],
  "step": 4,
  "refc": [[ ... ]],
  "retop": [[ ... ]]
}
```

`refc` is composite reflectivity in dBZ (dangerous `>= 40`); `retop` is storm-top
altitude in feet. Nodata cells (refc `<= -50`, retop `< 0`) are returned as
`null`. The strip whose `[valid_from, valid_to)` contains `t` is selected (or the
nearest by midpoint). `400` on an unparseable `t`.

## GET /health

Liveness probe → `{ "status": "ok" }`.

## GET /

Service banner: name, active `scenario`, link to `/docs`, and the endpoint list.

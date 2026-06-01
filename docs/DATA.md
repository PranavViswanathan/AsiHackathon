# Data Reference

AirFlow consumes three artifacts per scenario: a flight schedule, a sector map,
and a stack of weather forecast grids. This document is the authoritative schema
reference for each. All ingestion lives in `src/data/ingest.py`; the weather
query surface lives in `src/data/weather.py`.

## Flight Schema

Source: `routes.json`. The file is an object with metadata (`asked_at`,
`window_start`, `window_end`) and a `flights` array of 16,687 records. Each
flight has the following fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `flight_number` | string | Callsign / identifier for the flight |
| `take_off_time` | ISO 8601 string | Scheduled departure time |
| `scheduled_landing_time` | ISO 8601 string | Scheduled arrival time |
| `origin_airport_icao` | string | 4-letter ICAO of departure airport |
| `destination_airport_icao` | string | 4-letter ICAO of arrival airport |
| `cruise_altitude_ft` | number | Planned cruise altitude in feet |
| `cruise_speed_kt` | number | Planned cruise speed in knots |
| `lats` | number[] | Latitude waypoints of the planned route polyline |
| `lons` | number[] | Longitude waypoints of the planned route polyline |
| `is_airborne` | boolean | Whether the flight is already in the air at the ask time |

`lats` and `lons` are parallel arrays describing the route as an ordered
polyline. Altitude band (HIGH vs LOW) is derived from `cruise_altitude_ft`.

## Sector Schema

Source: `sectors.geojson` (shared across all scenarios). A GeoJSON
FeatureCollection of 712 features. Each feature's `properties`:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Sector id, `HIGH_NNN` or `LOW_NNN` |
| `altitude_from_ft` | number | Lower altitude bound of the sector (inclusive) |
| `altitude_to_ft` | number | Upper altitude bound of the sector (exclusive) |
| `capacity` | number | Max simultaneous flights before over-demand |

`geometry` is a `Polygon` in WGS84 (lon/lat) describing the sector's horizontal
footprint. A flight occupies a sector when its position falls inside the polygon
**and** its cruise altitude falls in the sector's band:

- **HIGH band:** `[35000, 60000)` ft
- **LOW band:** `[0, 35000)` ft

So a single (lat, lon) point can belong to one HIGH sector and one LOW sector;
which one a flight occupies depends on its cruise altitude.

## Weather Schema

Source: `wx/refc/*.npz` and `wx/retop/*.npz`. Each `.npz` holds a single array
under the key `matrix`:

- **shape:** `(256, 358)` — 256 rows (latitude), 358 columns (longitude)
- **dtype:** `float64`

Geographic extent of the grid:

```
LAT_MAX = 55.7765
LAT_MIN = 21.943
LON_MIN = -135.0
LON_MAX = -67.5
```

Two products:

- **refc** — composite reflectivity, in dBZ (precipitation intensity).
  `nodata <= -50`. Treated as **dangerous when `>= 40`** dBZ.
- **retop** — echo / storm top altitude, in feet. `nodata < 0`. A flight is
  **safe when `cruise_alt > retop`** (it overflies the storm top); unsafe
  otherwise.

Filenames encode time: `{based_at}_{valid_from}_{valid_to}.npz`, e.g.
`2025-05-29_21:00:00_2025-05-29_20:52:30_2025-05-29_21:07:30.npz`. There are
**73 files per product** per scenario (73 refc + 73 retop = 146 `.npz`),
delivered as 15-minute strips covering roughly 18 hours forward from the ask
time.

### Pixel Coordinate Formula

For a matrix cell at row `i` (0..ROWS-1) and column `j` (0..COLS-1), with
`ROWS=256` and `COLS=358`:

```
lat = LAT_MAX - i / ROWS * (LAT_MAX - LAT_MIN)
lon = LON_MIN + j / COLS * (LON_MAX - LON_MIN)
```

Row 0 is the northern edge (`LAT_MAX`) and latitude decreases downward; column 0
is the western edge (`LON_MIN`) and longitude increases rightward. Inverting
these formulas maps a (lat, lon) query to the nearest `(i, j)` cell.

## Available Scenarios

Each is a directory under `data/hackathon_data_bundle/` containing its own
`routes.json` and `wx/` tree. `sectors.geojson` is shared at the bundle root.

```
asked_at_2025-05-29T21:00:00Z
asked_at_2025-06-10T17:00:00Z
asked_at_2025-07-01T21:30:00Z
asked_at_2025-07-08T22:00:00Z
asked_at_2025-07-14T22:35:00Z
asked_at_2025-08-13T18:00:00Z
asked_at_2025-08-21T18:00:00Z
asked_at_2025-08-22T18:00:00Z
asked_at_2026-01-13T18:00:00Z
asked_at_2026-03-04T18:00:00Z
asked_at_2026-04-08T18:00:00Z
```

Select a scenario by pointing `SCENARIO_DIR` at one of these directories (see
`.env.example`).

## Generated Artifacts

`src/build.py` writes per-snapshot artifacts to `data/artifacts/<snapshot>/`
(gitignored; regenerable). These are the pipeline's output contract.

| File | Shape | Contents |
| --- | --- | --- |
| `flights.json` | list | per-flight `FuelEstimate` fields (`fuel_kg`, `co2_kg`, `distance_nm`, `time_hr`, `aircraft_class`, `aircraft_type`, `fuel_flow_kg_hr`, headwind/tailwind, `storm_nm`, `max_refc_dbz`) plus optimizer fields (`opt_fuel_kg`, `opt_cruise_altitude_ft`, `opt_departure_shift_min`, `fuel_saved_kg`, `recommended`) |
| `summary.json` | object | totals + `optimization` block (baseline/optimized fuel, fuel saved + pct, sector and storm counts) |
| `h3.json` | list | `{h3, fuel_kg, n_flights, mean_kg, congestion}` per H3 cell (res 4) |
| `sectors.json` | object | per-sector `{band, capacity, peak_load, over_demand, by_bin}` keyed by name |
| `recommendations.json` | list | `{flight_id, reason, before, after, ...}` for each changed flight |
| `wind_cache.npz` | npz | cached Open-Meteo CONUS wind field (only when built with `--wind`) |

## Web Export

`src/export_web.py` writes a lean, browser-ready copy to
`frontend/public/data/<snapshot>/` (the static data the frontend reads):

- `flights_baseline.json` / `flights_recommended.json` - top flights by fuel,
  downsampled, coordinates rounded, route as `path: [[lon, lat], ...]`, with
  baseline + optimized fields and per-flight `cost_saved_usd`.
- `h3_fuel.json` / `h3_traffic.json` - `{hex, value, fuel_kg, n_flights, mean_kg,
  congestion}` (the `value` field is fuel or flight count depending on the file).
- `sectors.json` - GeoJSON; properties merge geometry with occupancy
  (`peak_load`, `over_demand`, `load_by_bin`).
- `summary.json` - the summary with cost fields (`cost_saved_usd`,
  `fuel_price_usd_per_kg`) added.
- `snapshots.json` (at the data root) - the snapshot list and the showcase id.
- `weather/frame_*.png` - radar frames for the timeline (`src/web_animation.py`).

The FastAPI backend serves the `data/artifacts/` versions; the frontend's static
path reads the `frontend/public/data/` versions. Both originate from the same
pipeline. See [API.md](API.md) and [FRONTEND.md](FRONTEND.md).

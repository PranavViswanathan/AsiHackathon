# Architecture

AirFlow is an offline precompute pipeline plus two serving paths. The pipeline
turns a raw scenario into a set of JSON artifacts (per-flight fuel, an H3 energy
heatmap, sector occupancy, and optimizer recommendations). Those artifacts are
served two ways: exported as lean static JSON the frontend reads directly, and
served live by a FastAPI backend. Precomputing keeps the demo fast and robust
(no live solve required), while the API path exists for querying the full
dataset. Each stage has a single responsibility and a clean data contract with
the next.

## Data Flow

```
routes.json + sectors.geojson + wx/{refc,retop}/*.npz   (+ Open-Meteo winds, cached)
        |
src/data/ingest.py      parse flights / scenario
src/data/wind.py        WindField: fetch + cache CONUS winds aloft, along-track lookup
src/data/weather.py     WeatherGrid: refc/retop strips, storm-exposure test
        |
src/algorithm/grid.py     great-circle distance + bearing
src/algorithm/fuel.py     OpenAP fuel-burn estimate (wind + storm aware)
src/algorithm/sectors.py  sector occupancy per (sector, time bin) vs capacity
src/algorithm/h3agg.py    densify routes -> H3 cells -> fuel/traffic per cell
src/algorithm/optimize.py staged optimizer (altitude + A* reroute + departure shift)
src/algorithm/astar.py    lateral storm reroute (minimum-fuel, storm cells forbidden)
        |
src/build.py            orchestrate -> data/artifacts/<snapshot>/
                          flights.json, summary.json, h3.json, sectors.json,
                          recommendations.json, wind_cache.npz
        |
        +--> src/export_web.py    lean static JSON -> frontend/public/data/<snapshot>/
        |    src/web_animation.py weather radar frames (PNG) for the timeline
        |
        +--> backend/ (FastAPI)   serves the artifacts + sectors/weather over HTTP
        |
frontend/   Next.js: deck.gl + MapLibre (2D), Three.js (3D), timeline animation
```

The frontend reads through a swappable data layer (`frontend/src/lib/data/`): it
defaults to the static files and can flip to the API by setting one env var. See
[FRONTEND.md](FRONTEND.md).

## Component Responsibilities

**src/data/ingest.py** - Parses `routes.json[.gz]` into frozen `Flight` records
(origin/destination, cruise altitude and speed, takeoff/landing times, lat/lon
waypoint polyline, airborne flag) and a `Scenario`. The only place that touches
the routes file format.

**src/data/wind.py** - `WindField` wraps a coarse CONUS grid of winds aloft per
pressure level. `fetch_wind_field` pulls it once per snapshot from Open-Meteo and
`load_or_fetch_wind` caches it to `wind_cache.npz`, returning `None` on any
failure so the build degrades cleanly to zero-wind. `along_track_kt` projects the
wind onto a segment's heading (+ tailwind, - headwind).

**src/data/weather.py** - `WeatherGrid` indexes the `wx/refc` and `wx/retop`
15-minute strips, selects the strip covering a sample time, maps lat/lon to a
grid cell, and answers `exposure(lat, lon, alt, t)` = `refc >= 40 dBZ AND
alt < retop`. Fully offline.

**src/algorithm/grid.py** - Great-circle distance (`haversine_nm`), initial
bearing, and route length. The shared geographic vocabulary.

**src/algorithm/fuel.py** - The fuel-burn model. Classifies each flight
(regional/narrowbody/widebody), gets an altitude-aware cruise fuel flow from
OpenAP for a representative type, and integrates fuel over route segments using a
wind-adjusted ground speed plus a storm-exposure penalty. Emits a `FuelEstimate`
(fuel, CO2, time, headwind/tailwind split, storm exposure). See
[ALGORITHM.md](ALGORITHM.md).

**src/algorithm/sectors.py** - Builds a time-parameterized track per flight,
samples it, and counts distinct flights per (sector, time bin) by HIGH/LOW band
via a Shapely STRtree. Emits peak load, over-demand flags, and per-bin load.

**src/algorithm/h3agg.py** - Densifies each route, bins points to H3 cells
(resolution 4), spreads each flight's fuel across the cells it crosses, and
aggregates fuel, flight count, mean, and a congestion ratio per cell.

**src/algorithm/optimize.py + astar.py** - The staged optimizer: an altitude
pass (storm clearance first, then better winds/efficiency), an A* lateral reroute
for flights no altitude can clear, and a greedy departure-time pass to relieve
over-demand sectors. Produces an optimized `FuelEstimate`, recommendations, and a
baseline vs optimized summary.

**src/build.py** - Orchestrates the pipeline for one scenario and writes the
artifacts. Storms are on by default (offline); winds are opt-in via `--wind`
(`AIRFLOW_WIND=1`), optimizer on by default (`--no-optimize` to skip).

**src/export_web.py / src/web_animation.py** - `export_web` writes a lean,
downsampled, browser-friendly copy of the artifacts (paths as `[lon,lat]`,
per-flight cost in USD, H3 fuel/traffic files, sectors with occupancy) into
`frontend/public/data/`. `web_animation` renders the weather radar PNG frames for
the timeline.

**backend/** - FastAPI app (`main.py`) serving the artifacts (`store.py`) and
reading sectors + weather from the bundle (`bundle.py`); config from env
(`config.py`). Endpoints in [API.md](API.md). CORS open to `FRONTEND_URL`.

**frontend/** - Next.js + TypeScript app. deck.gl + MapLibre 2D map (flights by
fuel, H3 heatmap, sectors, animated radar + flight playback), a Three.js 3D view,
filters, a flight detail panel, and a baseline/optimized savings panel. Pure
consumer of the data layer.

## Key Design Decisions

**Precompute to artifacts, serve two ways.** The expensive work (fuel, sectors,
H3, optimization) runs once in `build.py` and is frozen as JSON. The static
export makes the demo instant and dependency-free; the FastAPI path serves the
same data for querying. The recommendation/fuel logic lives in importable
functions so both paths and `POST /api/solve` share one implementation.

**Fuel as a relative proxy.** The bundle has no tail number or mass, so absolute
fuel is an estimate. We read it primarily through before/after deltas, where a
constant bias cancels. OpenAP gives an altitude-dependent burn rate, which is
what makes "climb to a better level" a genuine fuel lever.

**Soft cost, hard constraint for weather.** Storm exposure adds a fuel penalty
(soft) but is also a hard constraint the optimizer must reduce first, via
altitude and then an A* detour that treats storm cells as impassable. Capacity is
the other constraint, relieved by departure-time shifts.

**Staged greedy optimizer, not a monolith.** Altitude -> reroute -> capacity
repair, each bounded and explainable, so every change carries a human-readable
reason and the result is legible rather than a black box.

## Scaling Considerations

The dominant cost is per-flight work over 16,687 flights: a fuel integration and,
in the optimizer, a few candidate altitudes and (for storm-exposed flights) an A*
search on a coarsened (~50 NM) grid confined to each flight's origin-destination
corridor. OpenAP fuel-flow lookups are memoized. Winds are fetched once and
cached. The static export downsamples to the top flights by fuel and rounds
coordinates so browser payloads stay small, while the full dataset remains
available through the pipeline and the API.

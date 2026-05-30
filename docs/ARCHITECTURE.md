# Architecture

AirFlow is a four-stage pipeline: ingest raw scenario data, discretize the
airspace into a space-time grid, solve for sector-load-aware routes, then serve
and visualize the result. Each stage has a single responsibility and a clean
data contract with the next, so any stage can be tested or swapped in isolation.

## Data Flow

```
routes.json + sectors.geojson + wx/*.npz
        |
src/data/ingest.py        (parse flights, sectors, weather)
        |
src/data/weather.py       (WeatherGrid — spatial/temporal lookups)
        |
src/algorithm/grid.py     (lat/lon <-> grid cell mapping)
        |
src/algorithm/solver.py   (sector-load-aware iterative Dijkstra)
        |
backend/main.py           (FastAPI REST API)
        |
frontend/                 (Next.js + Three.js 3D CONUS view)
```

The raw inputs are static files on disk. Ingestion turns them into typed,
in-memory structures. The weather layer wraps the stack of forecast grids
behind a query interface. The grid module defines the coordinate system the
solver reasons in. The solver produces trajectories and a sector-load history.
The backend exposes that result over HTTP, and the frontend renders it.

## Component Responsibilities

**src/data/ingest.py** — Parses the three input artifacts into typed Python
structures. Reads `routes.json` into a list of flight records (origin,
destination, cruise altitude/speed, takeoff/landing times, and the lat/lon
waypoint polyline). Loads `sectors.geojson` into Shapely polygons tagged with
altitude band and capacity. Discovers the `wx/refc` and `wx/retop` `.npz` strips
and hands their file index to the weather layer. This module is the only place
that touches the raw file formats; everything downstream consumes its output.

**src/data/weather.py** — Wraps the forecast grids in a `WeatherGrid` object
that answers "what is the reflectivity / storm top at this lat, lon, and time?".
It owns the pixel-to-geographic coordinate transform and the temporal nearest-
neighbor selection across the 15-minute strips. Lazily loads `.npz` matrices so
the full day of weather never has to sit in memory at once. The solver depends
only on this query surface, not on the file layout.

**src/algorithm/grid.py** — Defines the discrete space-time grid the solver
operates on: the lat/lon binning, the HIGH/LOW altitude bands, and the 15-minute
time bins. Provides bidirectional mapping between continuous (lat, lon, alt,
time) coordinates and discrete grid cells, plus the neighbor topology used to
build the routing graph. This is the shared coordinate vocabulary between the
geographic world and the optimizer.

**src/algorithm/solver.py** — The core optimizer. Builds a weighted graph over
grid cells and runs iterative Dijkstra: each iteration routes every flight along
the current cheapest path, accumulates the resulting per-sector load, then
re-weights the graph so that over-demand sectors and dangerous weather become
expensive. Repeating this drives flights off congested sectors and around
storms while keeping total path deviation small. Emits final trajectories, the
per-timestep sector-load map, and a convergence history.

**backend/main.py + routers/** — A FastAPI application that loads a scenario,
invokes the solver on demand, and serves the result. `routers/routing.py`
exposes the solve endpoint and flight list, `routers/sectors.py` exposes sector
geometry and load, and `routers/weather.py` exposes the forecast grids for a
requested time window. CORS is opened to `FRONTEND_URL`.

**frontend/** — A Next.js + Three.js application. The hero is a 3D CONUS view
with sectors shaded by load, animated flight paths, and a weather overlay. A
control panel drives scenario selection and the solver's cost weights; charts
below show convergence. It is a pure consumer of the backend API.

## Key Design Decisions

**Why iterative Dijkstra.** The true problem — route every flight so that no
sector ever exceeds capacity — is a coupled combinatorial optimization: each
flight's best route depends on where every other flight goes. Solving that
jointly and exactly is intractable at 16,687 flights. Iterative Dijkstra is a
fixed-point relaxation: route each flight independently against a shared,
congestion-priced graph, observe the resulting loads, raise prices on
over-demand sectors, and repeat. It is fast (each iteration is N independent
shortest-path queries), it degrades gracefully (any iteration is a valid
solution), and it converges toward a load-balanced equilibrium without ever
materializing the full joint search space.

**Why sector-based cost.** Capacity is defined per sector, not per grid cell, so
the cost that discourages congestion must be charged at sector granularity. We
price a cell by the load of the sector containing it, using a superlinear term
(`load^2`) so that the marginal cost of adding the Nth flight to an already-busy
sector grows sharply. This makes the solver prefer to spread flights across many
lightly loaded sectors rather than pile them into one, which is exactly the
load-balancing objective.

**Why 15-minute time bins.** The weather forecasts are delivered as 15-minute
strips, so 15 minutes is the natural temporal resolution of the most dynamic
input. Binning sector occupancy to the same cadence lets a sector be over-demand
at 21:00 but fine at 21:15, which is how real ATC flow control thinks. Finer
bins would multiply graph size without adding information the weather can
support; coarser bins would smear away transient congestion peaks that are the
whole point of the optimization.

## Scaling Considerations

The dominant cost is 16,687 shortest-path solves per iteration. We keep this
tractable by: (1) routing on a coarse lat/lon grid rather than raw waypoints, so
each Dijkstra runs on a graph of bounded size; (2) lazily loading weather strips
and caching the active window, so memory stays flat across the day; (3) keeping
each flight's solve independent within an iteration, which makes the inner loop
trivially parallelizable across processes if needed; and (4) bounding iteration
count (typically 5–15) since the load distribution stabilizes quickly. The
sector-load accumulation is an O(path length) scatter per flight, negligible
next to the path search. For the demo we can also cap `n_flights` to route a
representative subset and still surface the same congestion story.

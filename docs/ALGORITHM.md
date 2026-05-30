# Algorithm

AirFlow reroutes a full day of flights so that no airspace sector exceeds its
capacity, every flight stays clear of dangerous weather, and total deviation
from the original plans stays small. This document describes the framing, the
discretization, the cost function, and the iterative solver.

## Problem Framing

Two forces shape every route:

- **Sector capacity is a constraint.** Each sector can hold only `capacity`
  simultaneous flights in a given time bin. Exceeding it is "over-demand" —
  unsafe and the thing we are trying to eliminate. We do not model capacity as a
  hard wall (which can make the problem infeasible); we model it as a steeply
  rising cost so the solver is strongly incentivized to respect it but always
  has a feasible fallback.
- **Weather is a cost.** Flying through heavy precipitation or below a storm top
  is unsafe. We make those cells nearly impassable via a large penalty, so the
  solver routes around them whenever any reasonable detour exists.

The objective is to minimize total path cost across all flights, where cost
trades distance against sector congestion and weather exposure.

## Grid Discretization

The solver does not reason over raw waypoints; it reasons over a discrete
space-time grid (`src/algorithm/grid.py`):

- **Space (lat/lon):** the CONUS extent is binned into a regular lat/lon grid.
  Each cell is a routing node; adjacent cells (including diagonals) are
  connected, forming the movement graph.
- **Altitude bands:** two bands, HIGH `[35000, 60000)` ft and LOW
  `[0, 35000)` ft, matching the sector definition. A flight routes within the
  band implied by its `cruise_altitude_ft`.
- **Time:** 15-minute bins, matching the weather strip cadence. A flight's
  position advances through time bins according to its cruise speed, so sector
  occupancy and weather are always evaluated at the time the flight is actually
  there.

This `(lat_bin, lon_bin, band, time_bin)` tuple is the coordinate the cost
function and sector-load accounting are defined over.

## Cost Function

The weight of moving into a cell is:

```
cost = base_distance
     + lambda_sector  * sector_load^2
     + lambda_weather * weather_penalty
```

- **`base_distance`** — the geographic step length, which anchors the solution
  to short routes and recovers the great-circle-ish path when nothing is in the
  way.
- **`lambda_sector * sector_load^2`** — congestion pricing. `sector_load` is the
  current number of flights routed through the sector containing this cell in
  this time bin. Squaring makes each additional flight in a busy sector
  progressively more expensive, pushing the solver to spread traffic. `lambda_
  sector` tunes how aggressively congestion is avoided versus distance.
- **`lambda_weather * weather_penalty`** — safety pricing (below).

`lambda_sector` and `lambda_weather` are the two knobs exposed to the UI; they
let the operator trade off delay against congestion relief and weather margin.

## Weather: soft penalty + hard constraint

> The cost-function / iterative-Dijkstra framing above is the original design.
> The shipped pipeline implements the fuel-proxy + staged optimizer described
> here. Both parts key on the same **exposure** test: a flight is exposed at a
> point when `refc >= 40 dBZ AND cruise_alt < retop` (read through
> `WeatherGrid.exposure` at the flight's time bin, so it tracks the moving
> weather).

1. **Soft cost penalty.** Each exposed route segment adds a **+15%** fuel-burn
   penalty (`STORM_FUEL_PENALTY` in `src/algorithm/fuel.py`) and accumulates the
   per-flight `storm_nm` (exposed distance). This prices weather into the fuel
   estimate but never forbids anything by itself.

2. **Hard constraint (altitude).** The optimizer's altitude pass
   (`src/algorithm/optimize.py`) treats storm-exposed distance as a hard
   constraint to be minimized **before** fuel: candidate cruise levels are
   compared lexicographically by `(storm_nm, fuel_kg)`, so an exposed flight is
   moved to a storm-free altitude **even when that costs more fuel**.

3. **Hard constraint (lateral A\* reroute).** When no reachable altitude clears
   the storm (echo-top above cruise), a second pass (`src/algorithm/astar.py`)
   reroutes the flight *around* the storm:
   - **Nodes** = cells of the refc/retop grid, downsampled (~50 nm), confined to
     the origin–destination bounding box + margin. A cell's lat/lon is its center.
   - **Edges** = the 8 neighbor cells. **Edge cost** = the same wind-aware fuel
     proxy the simulator uses (`haversine_nm`, `WindField.along_track_kt`,
     `cruise_fuel_flow_kg_hr`). A cell is a **forbidden node** when it is
     storm-exposed at the flight's estimated time there (the hard constraint as a
     graph cut); origin/destination cells are always allowed.
   - **Heuristic** = great-circle distance to the destination × the minimum
     possible fuel-per-nm (`ff / (TAS + 250 kt)`), which never overestimates →
     A\* stays optimal.
   - The detour is re-costed with `estimate_fuel`; adopted only if it actually
     reduces `storm_nm`, and rejected if it exceeds 1.6× the direct distance.

Flights that neither altitude nor a bounded reroute can clear are reported as
`unresolved_storm_flights`. The summary also carries `n_reroutes`,
`storm_flights_before/after`, and `storm_nm_before/after`.

## Iterative Solver Loop

The flights are coupled — one flight's reroute changes the load another flight
sees — so we solve by relaxation rather than jointly:

```
initialize sector_load = 0 everywhere
for iteration in 1..N:
    reset sector_load to 0
    for each flight (independently):
        weight the grid graph using the current sector_load and weather
        path = Dijkstra(origin_cell -> destination_cell)
        record path as this flight's trajectory
        add the flight to sector_load for every (sector, time_bin) it crosses
    record over-demand count for this iteration   # convergence history
```

Each iteration is N independent shortest-path solves against a graph priced by
the **previous** iteration's loads. Over-demand sectors get more expensive, so
flights migrate off them; the load distribution stabilizes after a handful of
iterations (typically 5–15). Every iteration yields a complete, valid set of
trajectories, so the loop can stop early and still return a usable answer.

## QUBO Extension (optional)

Iterative Dijkstra finds a good fixed point but not a provably joint optimum.
An optional refinement frames route selection as a QUBO (Quadratic
Unconstrained Binary Optimization): for each flight, enumerate a small set of
candidate routes and introduce a binary variable per candidate. The linear terms
encode each route's distance and weather cost; the quadratic terms encode the
pairwise sector-sharing penalty between routes that overload the same sector in
the same time bin; a one-hot constraint forces exactly one route per flight.
Minimizing the QUBO (classically or on quantum-inspired annealers) chooses the
joint route assignment that best balances load. This layers on top of the
iterative solver, which supplies the candidate routes.

## Metrics

The solver reports, per run and per iteration where applicable:

- **Sector over-demand count** — number of (sector, time bin) pairs where load
  exceeds capacity. The headline number; should fall across iterations.
- **Weather conflicts** — number of flights whose final trajectory still touches
  a dangerous cell (refc >= 40 with cruise_alt <= retop). Target is zero.
- **Path deviation** — extra distance (or delay) of optimized routes versus the
  original plans, summed and per-flight. The cost we pay for safety and balance;
  kept as low as the constraints allow.

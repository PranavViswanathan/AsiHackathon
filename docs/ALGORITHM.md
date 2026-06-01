# Algorithm

AirFlow estimates each flight's fuel burn, the airspace it loads, and the weather
it hits, then recommends operationally simple changes that cut total fuel, clear
convective weather, and relieve over-demand sectors. This document covers the
fuel model, the weather and sector models, and the staged optimizer.

## Problem Framing

- **Objective: minimize total fuel** across all flights. Fuel is an estimated
  proxy (the bundle has no aircraft type or mass), read primarily through
  before/after deltas, where any constant bias cancels.
- **Weather is a hard constraint.** A flight must not fly through intense
  convection it cannot overfly. Exposure also adds a soft fuel penalty so it
  shows up in the estimate even before a fix is applied.
- **Sector capacity is a constraint.** Each sector holds only `capacity`
  simultaneous flights per time bin; exceeding it is over-demand.

The levers the optimizer may pull are deliberately limited and legible: cruise
altitude, a lateral storm detour, and a small departure-time shift. Route
geometry is otherwise preserved.

## Fuel Model (`src/algorithm/fuel.py`)

Per flight, integrate over consecutive waypoint segments:

```
ground_speed   = max(TAS + along_track_wind, 150)        # knots
segment_time   = segment_distance / ground_speed         # hours
segment_fuel   = fuel_flow(class, altitude, TAS) * segment_time
storm_penalty  = +15% on a storm-exposed segment
fuel_kg        = sum(segment_fuel)        CO2_kg = fuel_kg * 3.16
```

- **Aircraft class** is inferred from cruise speed (`<420 kt` regional,
  `<480` narrowbody, else widebody) and mapped to a representative type
  (E190 / A320 / B789).
- **`fuel_flow`** comes from **OpenAP** for that type at the flight's altitude
  and speed, so it is altitude-dependent (roughly 8 to 10% lower from 31k to
  39k ft). A per-class constant is used if OpenAP is unavailable or out of
  envelope. This altitude dependence is what makes "climb to a better level" a
  real fuel saving, not just a wind effect.
- **Wind** enters only through ground speed (tailwind lowers time and fuel,
  headwind raises it), sampled per segment from the cached field at the pressure
  level nearest cruise altitude.
- **CO2** is a fixed multiple of fuel (3.16 kg CO2 per kg Jet-A).

## Wind (`src/data/wind.py`)

A coarse CONUS grid of winds aloft (per pressure level, per hour) is fetched once
per snapshot from Open-Meteo and cached to `wind_cache.npz`. `along_track_kt`
bilinearly interpolates in space, picks the nearest time and pressure level, and
projects the wind onto a segment's bearing. With no field loaded the model is
zero-wind (ground speed = true airspeed) and byte-for-byte deterministic.

## Weather: soft penalty + hard constraint (`src/data/weather.py`)

A flight is **exposed** at a point when `refc >= 40 dBZ AND cruise_alt < retop`,
evaluated through `WeatherGrid.exposure` at the flight's estimated time there, so
it tracks the moving weather. Exposure both adds the +15% segment fuel penalty
(soft) and is the constraint the optimizer must reduce (hard, below).

## Sector Occupancy (`src/algorithm/sectors.py`)

Each flight gets a time-parameterized track (constant cruise), sampled every few
minutes and binned to 15-minute windows. Distinct flights per (sector, time bin)
are counted by HIGH/LOW band using a Shapely STRtree `within` query. A bin is
over-demand when its count exceeds the sector capacity. Emits peak load,
`over_demand`, and the per-bin series.

## H3 Aggregation (`src/algorithm/h3agg.py`)

Each route is densified (about every 20 NM) and its points binned to H3 cells
(resolution 4). Each flight's fuel is spread across the cells it crosses
(proportional to in-cell distance), and per cell we aggregate total fuel, flight
count, mean fuel per flight, and a congestion ratio (traffic normalized to
[0, 1]). This drives the energy heatmap and is a visualization metric, kept
separate from the sector capacity model.

## Optimizer (`src/algorithm/optimize.py`)

Three greedy, bounded passes. Every applied change records what changed, why, and
the before/after, so the result is explainable.

**1. Altitude pass.** For each candidate flight, try nearby cruise levels
(+/- 2,000 and +/- 4,000 ft, within 28k to 43k). Candidates are compared
lexicographically by `(storm_nm, fuel_kg)`: clear or reduce storm exposure first
(adopted even if it costs fuel), then minimize fuel. With winds on, all flights
are considered (wind-optimal altitude); offline, only storm-exposed flights are
(there is no fuel gradient to chase without winds).

**2. Lateral reroute (A*).** For flights still storm-exposed after the altitude
pass, `astar.reroute` searches a coarsened (~50 NM) weather grid for the
minimum-fuel detour that never enters a storm cell.

```
f(n) = g(n) + h(n)
g(n) = sum over edges of  fuel_flow * edge_distance / ground_speed   # actual fuel
h(n) = greatCircle(n, goal) * fuel_flow / (TAS + 250)                # admissible
```

`g` is the same wind-aware fuel proxy the simulator uses; `h` uses the lowest
possible fuel-per-NM (best-case tailwind) so it never overestimates and A* stays
optimal. Storm-exposed cells are forbidden nodes (the hard constraint as a graph
cut); detours beyond 1.6x the direct distance are rejected. The detour is
re-costed with `estimate_fuel` and adopted only if it actually reduces exposure.

**3. Departure-time capacity repair.** For flights contributing to over-demand
(sector, time bin) pairs, try small shifts (+/- 5, 10, 15 min) and apply the one
that most reduces total over-demand, biggest contributors first, updating
occupancy incrementally. Departure shifts are treated as fuel-neutral.

The optimizer never claims a global optimum; the ladder is rule-based -> greedy
(shipped) with A* for reroutes, MILP/QUBO left as future work.

## Metrics (in `summary.json`)

- **Fuel saved** - `baseline_fuel_kg - optimized_fuel_kg`, absolute and percent,
  plus `cost_saved_usd` and `co2_saved_kg`.
- **Over-demand sectors** - `overloaded_sectors_before -> after`.
- **Storm exposure** - `storm_flights_before/after`, `storm_nm_before/after`,
  `n_reroutes`, and `unresolved_storm_flights` (neither altitude nor a bounded
  reroute could clear them).
- **Changes** - `n_altitude_changes`, `n_departure_changes`.

Showcase snapshot, wind build: fuel saved 2.44M kg (3.35%, ~$2.07M), over-demand
sectors 169 -> 46, 13,264 altitude changes, 4,758 departure shifts.

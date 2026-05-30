"""Staged, explainable fuel/congestion optimizer.

Three passes, all greedy and bounded — no monolithic solver:

1. **Altitude pass** — for each candidate flight, try nearby cruise levels and
   keep the one that minimizes storm exposure first, then fuel (hard storm
   constraint, then better winds / clearing an echo-top).
2. **Lateral reroute (A-star)** — for flights still storm-exposed after the
   altitude pass, search a coarse grid for a detour around the storm
   (`astar.reroute`).
3. **Departure-time capacity repair** — for flights contributing to over-demand
   sector-time bins, try small departure shifts and apply the one that most
   reduces total over-demand. Greedy, one pass, biggest contributors first.

Every applied change records what changed, why, and the before/after, so the
result is legible rather than a black box."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from src.algorithm.astar import reroute
from src.algorithm.fuel import FuelEstimate, estimate_fuel
from src.algorithm.sectors import (
    DEFAULT_BIN_MINUTES,
    DEFAULT_SAMPLE_MINUTES,
    Key,
    capacity_map,
    compute_occupancy,
    n_bins_for,
    overloaded_keys,
)
from src.data.ingest import Scenario
from src.data.weather import WeatherGrid
from src.data.wind import WindField

ALT_CANDIDATES_FT = (-4000, -2000, 2000, 4000)
ALT_MIN_FT, ALT_MAX_FT = 28000.0, 43000.0
DEPARTURE_SHIFTS_MIN = (-15, -10, -5, 5, 10, 15)
MIN_FUEL_GAIN_KG = 1.0  # ignore sub-kg altitude "improvements"
EPS_STORM_NM = 0.5      # ignore sub-half-nm storm "reductions"


@dataclass
class OptimizeResult:
    estimates: list[FuelEstimate]
    altitudes: list[float]
    takeoffs: list[datetime]
    routes: list[tuple[tuple[float, ...], tuple[float, ...]]]
    changes: list[dict]
    summary: dict


def optimize(
    scenario: Scenario,
    baseline: list[FuelEstimate],
    *,
    wind: WindField | None = None,
    weather: WeatherGrid | None = None,
    bands: dict | None = None,
    baseline_counts: dict[Key, int] | None = None,
    sample_minutes: int = DEFAULT_SAMPLE_MINUTES,
    bin_minutes: int = DEFAULT_BIN_MINUTES,
) -> OptimizeResult:
    flights = list(scenario.flights)
    opt_alt = [f.cruise_altitude_ft for f in flights]
    opt_est = list(baseline)
    opt_takeoff = [f.take_off_time for f in flights]
    opt_routes: list[tuple[tuple[float, ...], tuple[float, ...]]] = [(f.lats, f.lons) for f in flights]
    changes: dict[int, dict] = {}

    # -- Stage 1: altitude pass ------------------------------------------
    consider = (
        range(len(flights))
        if wind is not None
        else [i for i, e in enumerate(baseline) if e.storm_nm > 0]
    )
    for i in consider:
        flight, base = flights[i], baseline[i]
        best_est, best_alt = base, flight.cruise_altitude_ft
        for delta in ALT_CANDIDATES_FT:
            cand_alt = flight.cruise_altitude_ft + delta
            if not (ALT_MIN_FT <= cand_alt <= ALT_MAX_FT):
                continue
            cand = estimate_fuel(replace(flight, cruise_altitude_ft=cand_alt), wind=wind, weather=weather)
            # Hard storm constraint first (minimize exposed distance), then fuel:
            # a storm-reducing altitude is adopted even if it costs more fuel; when
            # storm exposure ties, fall back to the usual fuel minimization.
            less_storm = cand.storm_nm < best_est.storm_nm - EPS_STORM_NM
            same_storm_less_fuel = (
                abs(cand.storm_nm - best_est.storm_nm) <= EPS_STORM_NM
                and cand.fuel_kg < best_est.fuel_kg - MIN_FUEL_GAIN_KG
            )
            if less_storm or same_storm_less_fuel:
                best_est, best_alt = cand, cand_alt
        if best_alt != flight.cruise_altitude_ft:
            opt_alt[i], opt_est[i] = best_alt, best_est
            changes[i] = _alt_change(flight, base, best_est, best_alt)

    # -- Stage 1.5: lateral reroute (A*) for still-exposed flights --------
    n_reroutes = 0
    if weather is not None:
        for i in range(len(flights)):
            if opt_est[i].storm_nm <= EPS_STORM_NM:
                continue  # already storm-free (cleared by altitude, or never exposed)
            path = reroute(flights[i], opt_alt[i], opt_takeoff[i], weather=weather, wind=wind)
            if path is None:
                continue
            lats = tuple(p[0] for p in path)
            lons = tuple(p[1] for p in path)
            cand = estimate_fuel(
                replace(flights[i], lats=lats, lons=lons, cruise_altitude_ft=opt_alt[i]),
                wind=wind, weather=weather,
            )
            if cand.storm_nm < opt_est[i].storm_nm - EPS_STORM_NM:
                _record_reroute(changes, i, flights[i], opt_est[i], cand)
                opt_est[i], opt_routes[i] = cand, (lats, lons)
                n_reroutes += 1

    # Effective flights carry the rerouted geometry for the occupancy model below.
    opt_flights = [
        replace(flights[i], lats=opt_routes[i][0], lons=opt_routes[i][1])
        if opt_routes[i] != (flights[i].lats, flights[i].lons)
        else flights[i]
        for i in range(len(flights))
    ]

    # -- Stage 2: departure-time capacity repair -------------------------
    overloaded_before = overloaded_after = 0
    n_departure = 0
    if bands:
        n_bins = n_bins_for(scenario, bin_minutes)
        caps = capacity_map(bands)
        before = baseline_counts if baseline_counts is not None else compute_occupancy(
            flights, bands, scenario.window_start, n_bins,
            sample_minutes=sample_minutes, bin_minutes=bin_minutes,
        )[0]
        overloaded_before = _n_overloaded_sectors(before, caps)

        counts, memberships = compute_occupancy(
            opt_flights, bands, scenario.window_start, n_bins,
            sample_minutes=sample_minutes, bin_minutes=bin_minutes,
            altitudes=opt_alt, takeoffs=opt_takeoff,
        )
        _repair_capacity(
            opt_flights, bands, scenario.window_start, n_bins, sample_minutes, bin_minutes,
            caps, counts, memberships, opt_alt, opt_takeoff, changes,
        )
        n_departure = sum(1 for c in changes.values() if c.get("departure_shift_min"))
        overloaded_after = _n_overloaded_sectors(counts, caps)

    base_fuel = sum(e.fuel_kg for e in baseline)
    opt_fuel = sum(e.fuel_kg for e in opt_est)
    summary = {
        "baseline_fuel_kg": round(base_fuel, 1),
        "optimized_fuel_kg": round(opt_fuel, 1),
        "fuel_saved_kg": round(base_fuel - opt_fuel, 1),
        "fuel_saved_pct": round(100.0 * (base_fuel - opt_fuel) / base_fuel, 3) if base_fuel else 0.0,
        "n_altitude_changes": sum(1 for c in changes.values() if c.get("altitude")),
        "n_departure_changes": n_departure,
        "n_reroutes": n_reroutes,
        "overloaded_sectors_before": overloaded_before,
        "overloaded_sectors_after": overloaded_after,
        # Hard storm constraint: exposed flights resolved (by altitude or reroute) vs. left.
        "storm_flights_before": sum(1 for e in baseline if e.storm_nm > 0),
        "storm_flights_after": sum(1 for e in opt_est if e.storm_nm > 0),
        "unresolved_storm_flights": sum(1 for e in opt_est if e.storm_nm > 0),
        "storm_nm_before": round(sum(e.storm_nm for e in baseline), 1),
        "storm_nm_after": round(sum(e.storm_nm for e in opt_est), 1),
    }
    return OptimizeResult(
        estimates=opt_est,
        altitudes=opt_alt,
        takeoffs=opt_takeoff,
        routes=opt_routes,
        changes=[changes[i] for i in sorted(changes)],
        summary=summary,
    )


def _repair_capacity(
    flights, bands, window_start, n_bins, sample_minutes, bin_minutes,
    caps, counts, memberships, opt_alt, opt_takeoff, changes,
):
    over = overloaded_keys(counts, caps)
    if not over:
        return
    over_set = set(over)
    # Flights touching the most overloaded bins go first (ties: lower index).
    contributing = [
        (len(memberships[i] & over_set), i)
        for i in range(len(flights))
        if memberships[i] & over_set
    ]
    contributing.sort(key=lambda t: (-t[0], t[1]))

    for _, i in contributing:
        current = memberships[i]
        if not any(counts.get(k, 0) > caps.get(k[0], 0) for k in current):
            continue  # this flight no longer sits in any over-demand bin
        best_shift, best_gain, best_keys = 0, 0.0, current
        for shift in DEPARTURE_SHIFTS_MIN:
            new_takeoff = flights[i].take_off_time + timedelta(minutes=shift)
            _, mem = compute_occupancy(
                [flights[i]], bands, window_start, n_bins,
                sample_minutes=sample_minutes, bin_minutes=bin_minutes,
                altitudes=[opt_alt[i]], takeoffs=[new_takeoff],
            )
            gain = _overload_gain(counts, caps, remove=current, add=mem[0])
            if gain > best_gain:
                best_shift, best_gain, best_keys = shift, gain, mem[0]
        if best_shift and best_gain > 0:
            for k in current:
                counts[k] -= 1
            for k in best_keys:
                counts[k] = counts.get(k, 0) + 1
            memberships[i] = best_keys
            opt_takeoff[i] = flights[i].take_off_time + timedelta(minutes=best_shift)
            _record_departure(changes, i, flights[i], best_shift)


def _overload_gain(counts, caps, *, remove: set[Key], add: set[Key]) -> float:
    """Reduction in total over-demand from removing one flight's `remove` keys
    and adding its `add` keys (positive = improvement)."""
    gain = 0.0
    for key in remove | add:
        cap = caps.get(key[0], 0)
        old = counts.get(key, 0)
        new = old - (1 if key in remove else 0) + (1 if key in add else 0)
        gain += max(0, old - cap) - max(0, new - cap)
    return gain


def _n_overloaded_sectors(counts: dict[Key, int], caps: dict[str, int]) -> int:
    return len({name for (name, _), load in counts.items() if load > caps.get(name, 0)})


def _alt_change(flight, base: FuelEstimate, after: FuelEstimate, new_alt: float) -> dict:
    if base.storm_nm > 0 and after.storm_nm == 0:
        reason = f"divert to {int(new_alt)} ft to clear the storm (hard constraint)"
    elif after.storm_nm < base.storm_nm - 0.5:
        reason = f"shift cruise to {int(new_alt)} ft to reduce storm exposure"
    else:
        reason = f"shift cruise to {int(new_alt)} ft for more favorable winds"
    return {
        "flight_id": flight.id,
        "altitude": {"from": flight.cruise_altitude_ft, "to": new_alt},
        "departure_shift_min": 0,
        "before": {"fuel_kg": round(base.fuel_kg, 1), "cruise_altitude_ft": flight.cruise_altitude_ft, "storm_nm": round(base.storm_nm, 1)},
        "after": {"fuel_kg": round(after.fuel_kg, 1), "cruise_altitude_ft": new_alt, "storm_nm": round(after.storm_nm, 1)},
        "fuel_saved_kg": round(base.fuel_kg - after.fuel_kg, 1),
        "reason": reason,
    }


def _record_reroute(changes: dict[int, dict], i: int, flight, before: FuelEstimate, after: FuelEstimate) -> None:
    reason = "reroute around the storm (hard constraint)"
    after_block = {"fuel_kg": round(after.fuel_kg, 1), "storm_nm": round(after.storm_nm, 1)}
    entry = changes.get(i)
    if entry is not None:  # already has an altitude change; augment it
        entry["rerouted"] = True
        entry["reason"] = entry["reason"] + "; " + reason
        if isinstance(entry.get("after"), dict):
            entry["after"].update(after_block)
        entry["fuel_saved_kg"] = round(before.fuel_kg - after.fuel_kg, 1) if entry.get("altitude") is None else entry.get("fuel_saved_kg")
    else:
        changes[i] = {
            "flight_id": flight.id,
            "altitude": None,
            "departure_shift_min": 0,
            "rerouted": True,
            "before": {"fuel_kg": round(before.fuel_kg, 1), "storm_nm": round(before.storm_nm, 1)},
            "after": after_block,
            "fuel_saved_kg": round(before.fuel_kg - after.fuel_kg, 1),
            "reason": reason,
        }


def _record_departure(changes: dict[int, dict], i: int, flight, shift_min: int) -> None:
    sign = "+" if shift_min > 0 else ""
    reason = f"shift departure by {sign}{shift_min} min to relieve an overloaded sector"
    entry = changes.get(i)
    if entry is not None:  # flight already has an altitude change; augment it
        entry["departure_shift_min"] = shift_min
        entry["reason"] = entry["reason"] + "; " + reason
    else:
        changes[i] = {
            "flight_id": flight.id,
            "altitude": None,
            "departure_shift_min": shift_min,
            "reason": reason,
        }

"""Pipeline orchestrator: load a scenario, estimate fuel per flight (optionally
wind-aware, with a storm-avoidance penalty), aggregate the H3 heatmap and sector
occupancy, run the staged optimizer, and write the per-snapshot artifacts
(flights.json, summary.json, h3.json, sectors.json, recommendations.json).

Storms + sectors + the optimizer are on by default (no network). Winds come from
Open-Meteo and are opt-in (`--wind` / `use_wind=True`); the result is cached to
`wind_cache.npz` and the build degrades to zero-wind on any fetch failure."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from src.algorithm.fuel import CLASS_FUEL_CAPACITY_KG, FuelEstimate, estimate_fuel
from src.algorithm.h3agg import aggregate_h3
from src.algorithm.optimize import OptimizeResult, optimize
from src.algorithm.sectors import (
    DEFAULT_BIN_MINUTES,
    compute_occupancy,
    format_sectors,
    load_bands,
    n_bins_for,
)
from src.data.ingest import Flight, Scenario, load_scenario
from src.data.weather import WeatherGrid
from src.data.wind import WindField, load_or_fetch_wind

DEFAULT_OUT_ROOT = Path("data/artifacts")


def build_snapshot(
    scenario_dir: Path | str,
    out_root: Path | str = DEFAULT_OUT_ROOT,
    *,
    use_wind: bool = False,
    use_storms: bool = True,
    use_optimizer: bool = True,
) -> dict:
    scenario_dir = Path(scenario_dir)
    scenario = load_scenario(scenario_dir)
    out_dir = Path(out_root) / scenario_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    weather = WeatherGrid(scenario_dir) if use_storms else None
    if weather is not None and not weather:
        weather = None  # no strips on disk -> nothing to sample
    wind = _load_wind(scenario, out_dir) if use_wind else None

    estimates = [estimate_fuel(flight, wind=wind, weather=weather) for flight in scenario.flights]
    h3_cells = aggregate_h3(scenario.flights, estimates)

    # Sectors + optimizer share one baseline occupancy computation.
    bands, baseline_counts, sectors_data = _occupancy(scenario, scenario_dir)
    opt = (
        optimize(scenario, estimates, wind=wind, weather=weather, bands=bands, baseline_counts=baseline_counts)
        if use_optimizer
        else None
    )

    records = [
        _flight_record(flight, estimates[i], opt, i)
        for i, flight in enumerate(scenario.flights)
    ]
    summary = _summary(
        scenario_dir.name,
        scenario.asked_at.isoformat(),
        estimates,
        wind_enabled=wind is not None,
        storms_enabled=weather is not None,
        n_h3_cells=len(h3_cells),
        n_overloaded_sectors=sectors_data.get("n_overloaded", 0),
        optimization=opt.summary if opt else None,
    )

    (out_dir / "flights.json").write_text(json.dumps(records))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "h3.json").write_text(json.dumps(h3_cells))
    (out_dir / "sectors.json").write_text(json.dumps(sectors_data))
    (out_dir / "recommendations.json").write_text(json.dumps(opt.changes if opt else []))
    return summary


def _occupancy(scenario: Scenario, scenario_dir: Path):
    sectors_path = scenario_dir.parent / "sectors.geojson"
    if not sectors_path.exists():
        return None, None, {"sectors": {}, "n_overloaded": 0}
    bands = load_bands(sectors_path)
    n_bins = n_bins_for(scenario, DEFAULT_BIN_MINUTES)
    counts, _ = compute_occupancy(scenario.flights, bands, scenario.window_start, n_bins)
    sectors_data = format_sectors(counts, bands, scenario.window_start, n_bins, DEFAULT_BIN_MINUTES)
    return bands, counts, sectors_data


def _load_wind(scenario: Scenario, out_dir: Path) -> WindField | None:
    return load_or_fetch_wind(
        scenario.window_start,
        scenario.window_end,
        cache_path=out_dir / "wind_cache.npz",
    )


def _flight_record(flight: Flight, estimate: FuelEstimate, opt: OptimizeResult | None, i: int) -> dict:
    record = {
        "id": flight.id,
        "flight_number": flight.flight_number,
        "origin": flight.origin_airport_icao,
        "destination": flight.destination_airport_icao,
        "cruise_altitude_ft": flight.cruise_altitude_ft,
        "cruise_speed_kt": flight.cruise_speed_kt,
        "is_airborne": flight.is_airborne,
        "lats": list(flight.lats),
        "lons": list(flight.lons),
        "aircraft_class": estimate.aircraft_class,
        "aircraft_type": estimate.aircraft_type,
        "fuel_flow_kg_hr": estimate.fuel_flow_kg_hr,
        "fuel_capacity_kg": CLASS_FUEL_CAPACITY_KG[estimate.aircraft_class],
        "distance_nm": round(estimate.distance_nm, 2),
        "time_hr": round(estimate.time_hr, 4),
        "fuel_kg": round(estimate.fuel_kg, 1),
        "co2_kg": round(estimate.co2_kg, 1),
        "base_fuel_kg": round(estimate.base_fuel_kg, 1),
        "headwind_nm": round(estimate.headwind_nm, 2),
        "tailwind_nm": round(estimate.tailwind_nm, 2),
        "mean_along_track_kt": round(estimate.mean_along_track_kt, 2),
        "storm_nm": round(estimate.storm_nm, 2),
        "max_refc_dbz": round(estimate.max_refc_dbz, 1),
        "storm_penalty_kg": round(estimate.storm_penalty_kg, 1),
    }
    opt_est = opt.estimates[i] if opt else estimate
    opt_alt = opt.altitudes[i] if opt else flight.cruise_altitude_ft
    shift_min = int((opt.takeoffs[i] - flight.take_off_time).total_seconds() / 60) if opt else 0
    record.update(
        {
            "opt_fuel_kg": round(opt_est.fuel_kg, 1),
            "opt_cruise_altitude_ft": opt_alt,
            "opt_departure_shift_min": shift_min,
            "fuel_saved_kg": round(estimate.fuel_kg - opt_est.fuel_kg, 1),
            "recommended": opt_alt != flight.cruise_altitude_ft or shift_min != 0,
        }
    )
    return record


def _summary(
    snapshot: str,
    asked_at: str,
    estimates: list[FuelEstimate],
    *,
    wind_enabled: bool,
    storms_enabled: bool,
    n_h3_cells: int = 0,
    n_overloaded_sectors: int = 0,
    optimization: dict | None = None,
) -> dict:
    by_class: dict[str, int] = {}
    for estimate in estimates:
        by_class[estimate.aircraft_class] = by_class.get(estimate.aircraft_class, 0) + 1
    total_fuel = sum(e.fuel_kg for e in estimates)
    total_base = sum(e.base_fuel_kg for e in estimates)
    return {
        "snapshot": snapshot,
        "asked_at": asked_at,
        "n_flights": len(estimates),
        "wind_enabled": wind_enabled,
        "storms_enabled": storms_enabled,
        "total_fuel_kg": round(total_fuel, 1),
        "total_base_fuel_kg": round(total_base, 1),
        "wind_delta_fuel_kg": round(total_fuel - total_base - sum(e.storm_penalty_kg for e in estimates), 1),
        "total_co2_kg": round(sum(e.co2_kg for e in estimates), 1),
        "total_distance_nm": round(sum(e.distance_nm for e in estimates), 1),
        "total_storm_nm": round(sum(e.storm_nm for e in estimates), 1),
        "n_storm_flights": sum(1 for e in estimates if e.storm_nm > 0),
        "total_storm_penalty_kg": round(sum(e.storm_penalty_kg for e in estimates), 1),
        "n_h3_cells": n_h3_cells,
        "n_overloaded_sectors": n_overloaded_sectors,
        "optimization": optimization,
        "by_class": by_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AirFlow artifacts for a scenario.")
    parser.add_argument("--scenario-dir", required=True)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--wind", action="store_true", help="fetch Open-Meteo winds (network)")
    parser.add_argument("--no-storms", dest="storms", action="store_false", help="skip storm sampling")
    parser.add_argument("--no-optimize", dest="optimize", action="store_false", help="skip the optimizer")
    args = parser.parse_args()
    use_wind = args.wind or os.environ.get("AIRFLOW_WIND") == "1"
    summary = build_snapshot(
        args.scenario_dir,
        out_root=args.out_root,
        use_wind=use_wind,
        use_storms=args.storms,
        use_optimizer=args.optimize,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

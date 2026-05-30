"""Pipeline orchestrator: load a scenario, estimate fuel per flight (optionally
wind-aware, with a storm-avoidance penalty), and write the per-snapshot
artifacts (flights.json, summary.json, h3.json).

Storms are sampled from the local weather strips and are on by default (no
network). Winds come from Open-Meteo and are opt-in (`--wind` / `use_wind=True`)
since they require a network fetch on first run; the result is cached to
`wind_cache.npz` and the build degrades to zero-wind on any fetch failure."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.algorithm.fuel import FuelEstimate, estimate_fuel
from src.algorithm.h3agg import aggregate_h3
from src.algorithm.sectors import aggregate_sectors
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
    records = [
        _flight_record(flight, estimate)
        for flight, estimate in zip(scenario.flights, estimates)
    ]
    h3_cells = aggregate_h3(scenario.flights, estimates)
    sectors_data = _sectors(scenario, scenario_dir)
    summary = _summary(
        scenario_dir.name,
        scenario.asked_at.isoformat(),
        estimates,
        wind_enabled=wind is not None,
        storms_enabled=weather is not None,
        n_h3_cells=len(h3_cells),
        n_overloaded_sectors=sectors_data.get("n_overloaded", 0),
    )

    (out_dir / "flights.json").write_text(json.dumps(records))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "h3.json").write_text(json.dumps(h3_cells))
    (out_dir / "sectors.json").write_text(json.dumps(sectors_data))
    return summary


def _sectors(scenario: Scenario, scenario_dir: Path) -> dict:
    sectors_path = scenario_dir.parent / "sectors.geojson"
    if not sectors_path.exists():
        return {"sectors": {}, "n_overloaded": 0}
    return aggregate_sectors(scenario, sectors_path)


def _load_wind(scenario: Scenario, out_dir: Path) -> WindField | None:
    return load_or_fetch_wind(
        scenario.window_start,
        scenario.window_end,
        cache_path=out_dir / "wind_cache.npz",
    )


def _flight_record(flight: Flight, estimate: FuelEstimate) -> dict:
    return {
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


def _summary(
    snapshot: str,
    asked_at: str,
    estimates: list[FuelEstimate],
    *,
    wind_enabled: bool,
    storms_enabled: bool,
    n_h3_cells: int = 0,
    n_overloaded_sectors: int = 0,
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
        "by_class": by_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AirFlow artifacts for a scenario.")
    parser.add_argument("--scenario-dir", required=True)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--wind", action="store_true", help="fetch Open-Meteo winds (network)")
    parser.add_argument("--no-storms", dest="storms", action="store_false", help="skip storm sampling")
    args = parser.parse_args()
    use_wind = args.wind or os.environ.get("AIRFLOW_WIND") == "1"
    summary = build_snapshot(
        args.scenario_dir, out_root=args.out_root, use_wind=use_wind, use_storms=args.storms
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

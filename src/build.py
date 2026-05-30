"""Pipeline orchestrator: load a scenario, estimate fuel per flight, and write
the per-snapshot artifacts (flights.json, summary.json, h3.json)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.algorithm.fuel import FuelEstimate, estimate_fuel
from src.algorithm.h3agg import aggregate_h3
from src.data.ingest import Flight, load_scenario

DEFAULT_OUT_ROOT = Path("data/artifacts")


def build_snapshot(scenario_dir: Path | str, out_root: Path | str = DEFAULT_OUT_ROOT) -> dict:
    scenario_dir = Path(scenario_dir)
    scenario = load_scenario(scenario_dir)
    estimates = [estimate_fuel(flight) for flight in scenario.flights]
    records = [
        _flight_record(flight, estimate)
        for flight, estimate in zip(scenario.flights, estimates)
    ]
    summary = _summary(scenario_dir.name, scenario.asked_at.isoformat(), estimates)

    out_dir = Path(out_root) / scenario_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "flights.json").write_text(json.dumps(records))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "h3.json").write_text(json.dumps(aggregate_h3(estimates)))
    return summary


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
    }


def _summary(snapshot: str, asked_at: str, estimates: list[FuelEstimate]) -> dict:
    by_class: dict[str, int] = {}
    for estimate in estimates:
        by_class[estimate.aircraft_class] = by_class.get(estimate.aircraft_class, 0) + 1
    return {
        "snapshot": snapshot,
        "asked_at": asked_at,
        "n_flights": len(estimates),
        "total_fuel_kg": round(sum(e.fuel_kg for e in estimates), 1),
        "total_co2_kg": round(sum(e.co2_kg for e in estimates), 1),
        "total_distance_nm": round(sum(e.distance_nm for e in estimates), 1),
        "by_class": by_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AirFlow artifacts for a scenario.")
    parser.add_argument("--scenario-dir", required=True)
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    args = parser.parse_args()
    summary = build_snapshot(args.scenario_dir, out_root=args.out_root)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

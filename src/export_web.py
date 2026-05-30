"""Export lean, browser-friendly static JSON for the frontend.

Reads the pipeline artifacts produced by ``src.build`` plus the shared sectors
file, and writes a normalized, downsampled snapshot under the frontend's public
data directory. The schema here is the frozen contract the frontend data layer
reads; the FastAPI backend serves the same shapes from the same pipeline.

Each web flight carries both the baseline and the optimized scenario (the
optimizer changes only altitude + departure time, never route geometry), plus
the per-flight savings (fuel, CO2, and $ at an assumed Jet-A price) so the UI can
toggle Baseline <-> Optimized and show how much is saved.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

DEFAULT_ARTIFACTS = Path("data/artifacts")
DEFAULT_SECTORS = Path("data/hackathon_data_bundle/sectors.geojson")
DEFAULT_OUT = Path("frontend/public/data")
DEFAULT_MAX_FLIGHTS = 1500
COORD_PRECISION = 3

CO2_PER_KG_FUEL = 3.16
DEFAULT_FUEL_PRICE_USD_PER_KG = 0.85  # ~Jet-A spot, ~$2.60/gal


def _round(value: float) -> float:
    return round(value, COORD_PRECISION)


def _web_flight(
    record: dict[str, Any],
    reasons: dict[str, str],
    price: float,
) -> dict[str, Any]:
    path = [[_round(lon), _round(lat)] for lon, lat in zip(record["lons"], record["lats"])]
    opt_path = [
        [_round(lon), _round(lat)]
        for lon, lat in zip(record.get("opt_lons", record["lons"]), record.get("opt_lats", record["lats"]))
    ]
    fuel_saved = record.get("fuel_saved_kg", 0.0)
    opt_fuel = record.get("opt_fuel_kg", record["fuel_kg"])
    return {
        "flight_key": record["id"],
        "flight_number": record["flight_number"],
        "origin": record["origin"],
        "destination": record["destination"],
        "aircraft_class": record["aircraft_class"],
        "aircraft_type": record.get("aircraft_type"),
        "is_airborne": record["is_airborne"],
        "distance_nm": record["distance_nm"],
        "path": path,
        "opt_path": opt_path,
        # baseline
        "cruise_altitude_ft": record["cruise_altitude_ft"],
        "fuel_kg": record["fuel_kg"],
        "co2_kg": record["co2_kg"],
        # optimized
        "opt_cruise_altitude_ft": record.get("opt_cruise_altitude_ft", record["cruise_altitude_ft"]),
        "opt_departure_shift_min": record.get("opt_departure_shift_min", 0),
        "opt_fuel_kg": opt_fuel,
        "opt_co2_kg": round(opt_fuel * CO2_PER_KG_FUEL, 1),
        "recommended": record.get("recommended", False),
        # savings
        "fuel_saved_kg": fuel_saved,
        "co2_saved_kg": round(fuel_saved * CO2_PER_KG_FUEL, 1),
        "cost_saved_usd": round(fuel_saved * price, 2),
        "recommendation": reasons.get(record["id"]),
    }


def _read_json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


def _read_json_or(path: Path, default: Any) -> Any:
    return _read_json(path) if path.exists() else default


def _reasons(recommendations: list[dict[str, Any]]) -> dict[str, str]:
    return {r["flight_id"]: r["reason"] for r in recommendations if r.get("reason")}


def _sectors(sectors_path: Path, occupancy_path: Path) -> dict[str, Any]:
    raw = _read_json(sectors_path)
    occ = _read_json(occupancy_path).get("sectors", {}) if occupancy_path.exists() else {}
    features = []
    for feature in raw["features"]:
        name = feature["properties"]["name"]
        load = occ.get(name, {})
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "name": name,
                    "altitude_from_ft": feature["properties"]["altitude_from_ft"],
                    "altitude_to_ft": feature["properties"]["altitude_to_ft"],
                    "capacity": feature["properties"]["capacity"],
                    "peak_load": load.get("peak_load", 0),
                    "over_demand": load.get("over_demand", False),
                    "load_by_bin": load.get("by_bin", {}),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _h3_cell(cell: dict[str, Any], value_key: str) -> dict[str, Any]:
    return {
        "hex": cell["h3"],
        "value": cell[value_key],
        "fuel_kg": cell["fuel_kg"],
        "n_flights": cell["n_flights"],
        "mean_kg": cell["mean_kg"],
        "congestion": cell["congestion"],
    }


def _write_h3(artifacts_dir: Path, out_dir: Path) -> None:
    cells = _read_json(artifacts_dir / "h3.json")
    (out_dir / "h3_fuel.json").write_text(
        json.dumps([_h3_cell(c, "fuel_kg") for c in cells])
    )
    (out_dir / "h3_traffic.json").write_text(
        json.dumps([_h3_cell(c, "n_flights") for c in cells])
    )


def _summary_with_cost(summary: dict[str, Any], price: float) -> dict[str, Any]:
    opt = summary.get("optimization")
    if opt:
        opt = {
            **opt,
            "fuel_price_usd_per_kg": price,
            "cost_baseline_usd": round(opt["baseline_fuel_kg"] * price, 2),
            "cost_optimized_usd": round(opt["optimized_fuel_kg"] * price, 2),
            "cost_saved_usd": round(opt["fuel_saved_kg"] * price, 2),
            "co2_saved_kg": round(opt["fuel_saved_kg"] * CO2_PER_KG_FUEL, 1),
        }
    return {**summary, "scenario": "baseline", "optimization": opt}


def export_snapshot(
    snapshot: str,
    artifacts_root: Path | str = DEFAULT_ARTIFACTS,
    sectors_path: Path | str = DEFAULT_SECTORS,
    out_root: Path | str = DEFAULT_OUT,
    max_flights: int = DEFAULT_MAX_FLIGHTS,
    fuel_price: float = DEFAULT_FUEL_PRICE_USD_PER_KG,
) -> dict[str, Any]:
    artifacts_dir = Path(artifacts_root) / snapshot
    flights = _read_json(artifacts_dir / "flights.json")
    summary = _read_json(artifacts_dir / "summary.json")
    reasons = _reasons(_read_json_or(artifacts_dir / "recommendations.json", []))

    # Same flight set for both scenarios (geometry is identical), top-N by baseline fuel.
    selected = sorted(flights, key=lambda f: f["fuel_kg"], reverse=True)[:max_flights]
    web_flights = [_web_flight(f, reasons, fuel_price) for f in selected]

    out_dir = Path(out_root) / snapshot
    out_dir.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(web_flights)
    (out_dir / "flights_baseline.json").write_text(blob)
    (out_dir / "flights_recommended.json").write_text(blob)
    (out_dir / "summary.json").write_text(json.dumps(_summary_with_cost(summary, fuel_price)))
    _write_h3(artifacts_dir, out_dir)
    (out_dir / "sectors.json").write_text(
        json.dumps(_sectors(Path(sectors_path), artifacts_dir / "sectors.json"))
    )

    manifest = {"snapshots": [snapshot], "showcase": snapshot}
    Path(out_root).mkdir(parents=True, exist_ok=True)
    (Path(out_root) / "snapshots.json").write_text(json.dumps(manifest))

    return {"snapshot": snapshot, "flights_written": len(web_flights), "out_dir": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export lean static JSON for the frontend.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--artifacts-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--sectors", default=str(DEFAULT_SECTORS))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT))
    parser.add_argument("--max-flights", type=int, default=DEFAULT_MAX_FLIGHTS)
    parser.add_argument("--fuel-price", type=float, default=DEFAULT_FUEL_PRICE_USD_PER_KG,
                        help="assumed Jet-A price in USD/kg (default 0.85)")
    args = parser.parse_args()
    result = export_snapshot(
        snapshot=args.snapshot,
        artifacts_root=args.artifacts_root,
        sectors_path=args.sectors,
        out_root=args.out_root,
        max_flights=args.max_flights,
        fuel_price=args.fuel_price,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

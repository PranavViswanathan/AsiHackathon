"""Export lean, browser-friendly static JSON for the frontend.

Reads the pipeline artifacts produced by ``src.build`` plus the shared sectors
file, and writes a normalized, downsampled snapshot under the frontend's public
data directory. The schema here is the frozen contract the frontend data layer
reads; the FastAPI backend will later serve the same shapes from the same
pipeline functions.
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


def _round(value: float) -> float:
    return round(value, COORD_PRECISION)


def _web_flight(record: dict[str, Any]) -> dict[str, Any]:
    path = [[_round(lon), _round(lat)] for lon, lat in zip(record["lons"], record["lats"])]
    return {
        "flight_key": record["id"],
        "flight_number": record["flight_number"],
        "origin": record["origin"],
        "destination": record["destination"],
        "cruise_altitude_ft": record["cruise_altitude_ft"],
        "aircraft_class": record["aircraft_class"],
        "is_airborne": record["is_airborne"],
        "distance_nm": record["distance_nm"],
        "fuel_kg": record["fuel_kg"],
        "co2_kg": record["co2_kg"],
        "path": path,
    }


def _read_json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


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


def export_snapshot(
    snapshot: str,
    artifacts_root: Path | str = DEFAULT_ARTIFACTS,
    sectors_path: Path | str = DEFAULT_SECTORS,
    out_root: Path | str = DEFAULT_OUT,
    max_flights: int = DEFAULT_MAX_FLIGHTS,
) -> dict[str, Any]:
    artifacts_dir = Path(artifacts_root) / snapshot
    flights = _read_json(artifacts_dir / "flights.json")
    summary = _read_json(artifacts_dir / "summary.json")

    flights_sorted = sorted(flights, key=lambda f: f["fuel_kg"], reverse=True)
    selected = flights_sorted[:max_flights]
    web_flights = [_web_flight(f) for f in selected]

    out_dir = Path(out_root) / snapshot
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "flights_baseline.json").write_text(json.dumps(web_flights))
    (out_dir / "summary.json").write_text(json.dumps({**summary, "scenario": "baseline"}))
    _write_h3(artifacts_dir, out_dir)
    (out_dir / "sectors.json").write_text(
        json.dumps(_sectors(Path(sectors_path), artifacts_dir / "sectors.json"))
    )

    manifest = {
        "snapshots": [snapshot],
        "showcase": snapshot,
    }
    (Path(out_root)).mkdir(parents=True, exist_ok=True)
    (Path(out_root) / "snapshots.json").write_text(json.dumps(manifest))

    return {"snapshot": snapshot, "flights_written": len(web_flights), "out_dir": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export lean static JSON for the frontend.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--artifacts-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--sectors", default=str(DEFAULT_SECTORS))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT))
    parser.add_argument("--max-flights", type=int, default=DEFAULT_MAX_FLIGHTS)
    args = parser.parse_args()
    result = export_snapshot(
        snapshot=args.snapshot,
        artifacts_root=args.artifacts_root,
        sectors_path=args.sectors,
        out_root=args.out_root,
        max_flights=args.max_flights,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

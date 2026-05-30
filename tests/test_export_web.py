"""Tests for the frontend static export, focused on the optimized scenario and
the per-flight / aggregate savings (fuel, CO2, money). Offline."""

from __future__ import annotations

import json

from pytest import approx

from src.export_web import export_snapshot

SNAP = "asked_at_2025-05-29T21:00:00Z"
PRICE = 0.85


def _artifacts(tmp_path):
    d = tmp_path / "artifacts" / SNAP
    d.mkdir(parents=True)
    flights = [
        {
            "id": "AAA1_t_KJFK", "flight_number": "AAA1", "origin": "KJFK", "destination": "KLAX",
            "cruise_altitude_ft": 35000.0, "aircraft_class": "narrowbody", "aircraft_type": "A320",
            "is_airborne": False, "distance_nm": 2000.0,
            "lats": [40.6, 34.0], "lons": [-73.8, -118.4],
            "opt_lats": [40.6, 45.0, 34.0], "opt_lons": [-73.8, -90.0, -118.4],
            "fuel_kg": 9000.0, "co2_kg": 28440.0,
            "opt_fuel_kg": 8000.0, "opt_cruise_altitude_ft": 39000.0,
            "opt_departure_shift_min": -5, "fuel_saved_kg": 1000.0, "recommended": True,
        },
        {
            "id": "BBB2_t_KSEA", "flight_number": "BBB2", "origin": "KSEA", "destination": "KSFO",
            "cruise_altitude_ft": 33000.0, "aircraft_class": "regional", "aircraft_type": "E190",
            "is_airborne": True, "distance_nm": 600.0,
            "lats": [47.4, 37.6], "lons": [-122.3, -122.4],
            "fuel_kg": 2000.0, "co2_kg": 6320.0,
            "opt_fuel_kg": 2000.0, "opt_cruise_altitude_ft": 33000.0,
            "opt_departure_shift_min": 0, "fuel_saved_kg": 0.0, "recommended": False,
        },
    ]
    (d / "flights.json").write_text(json.dumps(flights))
    (d / "h3.json").write_text(json.dumps([
        {"h3": "8abc", "fuel_kg": 100.0, "n_flights": 3, "mean_kg": 33.3, "congestion": 0.5}
    ]))
    (d / "recommendations.json").write_text(json.dumps([
        {"flight_id": "AAA1_t_KJFK", "reason": "climb to 39000 ft for more favorable winds"}
    ]))
    (d / "summary.json").write_text(json.dumps({
        "snapshot": SNAP, "asked_at": "2025-05-29T21:00:00+00:00", "n_flights": 2,
        "total_fuel_kg": 11000.0, "total_co2_kg": 34760.0, "total_distance_nm": 2600.0,
        "by_class": {"narrowbody": 1, "regional": 1, "widebody": 0},
        "optimization": {
            "baseline_fuel_kg": 11000.0, "optimized_fuel_kg": 10000.0,
            "fuel_saved_kg": 1000.0, "fuel_saved_pct": 9.09,
            "n_altitude_changes": 1, "n_departure_changes": 1,
            "overloaded_sectors_before": 2, "overloaded_sectors_after": 0,
        },
    }))
    return tmp_path / "artifacts"


def _sectors(tmp_path):
    p = tmp_path / "sectors.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
         "properties": {"name": "HIGH_001", "altitude_from_ft": 35000, "altitude_to_ft": 60000, "capacity": 20}}
    ]}))
    return p


def _run(tmp_path):
    out = tmp_path / "web"
    export_snapshot(SNAP, artifacts_root=_artifacts(tmp_path), sectors_path=_sectors(tmp_path),
                    out_root=out, fuel_price=PRICE)
    return out / SNAP


def test_both_scenario_files_are_written(tmp_path):
    out = _run(tmp_path)
    assert (out / "flights_baseline.json").exists()
    assert (out / "flights_recommended.json").exists()


def test_web_flight_carries_optimized_and_savings_fields(tmp_path):
    flights = json.loads((_run(tmp_path) / "flights_baseline.json").read_text())
    aaa = next(f for f in flights if f["flight_number"] == "AAA1")
    assert aaa["opt_fuel_kg"] == 8000.0
    assert aaa["opt_cruise_altitude_ft"] == 39000.0
    assert aaa["opt_departure_shift_min"] == -5
    assert aaa["fuel_saved_kg"] == 1000.0
    assert aaa["co2_saved_kg"] == approx(3160.0)
    assert aaa["cost_saved_usd"] == approx(850.0)
    assert aaa["recommended"] is True
    assert "winds" in aaa["recommendation"]
    assert len(aaa["opt_path"]) == 3  # rerouted geometry carried through
    assert aaa["opt_path"] != aaa["path"]


def test_summary_optimization_has_cost_and_co2(tmp_path):
    summary = json.loads((_run(tmp_path) / "summary.json").read_text())
    opt = summary["optimization"]
    assert opt["fuel_price_usd_per_kg"] == PRICE
    assert opt["cost_saved_usd"] == approx(850.0)
    assert opt["co2_saved_kg"] == approx(3160.0)
    assert opt["cost_baseline_usd"] == approx(11000.0 * PRICE)


def test_flights_are_capped_by_max_flights(tmp_path):
    out = tmp_path / "web"
    export_snapshot(SNAP, artifacts_root=_artifacts(tmp_path), sectors_path=_sectors(tmp_path),
                    out_root=out, max_flights=1, fuel_price=PRICE)
    flights = json.loads((out / SNAP / "flights_baseline.json").read_text())
    assert len(flights) == 1
    assert flights[0]["flight_number"] == "AAA1"  # highest baseline fuel

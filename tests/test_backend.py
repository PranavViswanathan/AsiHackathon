"""API tests for the FastAPI backend. A tiny synthetic scenario (2 flights, a
couple of weather strips, 2 sectors) is built in a tmp dir so the suite stays
fast and hermetic — it never touches the 16,687-flight bundle."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import backend.bundle as bundle
import backend.config as config
import backend.store as store


def _write_scenario(scenario_dir):
    scenario_dir.mkdir(parents=True)
    routes = {
        "asked_at": "2025-05-29T21:00:00Z",
        "window_start": "2025-05-29T19:00:00Z",
        "window_end": "2025-05-30T13:00:00Z",
        "flights": [
            {
                "flight_number": "TEST1",
                "take_off_time": "2025-05-29T21:10:00Z",
                "scheduled_landing_time": "2025-05-29T23:40:00Z",
                "origin_airport_icao": "KJFK",
                "destination_airport_icao": "KLAX",
                "cruise_altitude_ft": 37000,
                "cruise_speed_kt": 460,
                "lats": [40.64, 39.0, 34.0],
                "lons": [-73.78, -90.0, -118.4],
                "is_airborne": False,
            },
            {
                "flight_number": "TEST2",
                "take_off_time": "2025-05-29T21:30:00Z",
                "scheduled_landing_time": "2025-05-29T22:30:00Z",
                "origin_airport_icao": "KSEA",
                "destination_airport_icao": "KSFO",
                "cruise_altitude_ft": 33000,
                "cruise_speed_kt": 410,
                "lats": [47.45, 42.0, 37.62],
                "lons": [-122.3, -122.0, -122.38],
                "is_airborne": True,
            },
        ],
    }
    (scenario_dir / "routes.json").write_text(json.dumps(routes))

    refc = scenario_dir / "wx" / "refc"
    retop = scenario_dir / "wx" / "retop"
    refc.mkdir(parents=True)
    retop.mkdir(parents=True)
    grid = np.full((8, 8), -60.0)
    grid[2, 2] = 45.0  # one dangerous cell
    tops = np.full((8, 8), -1.0)
    tops[2, 2] = 30000.0
    for name in (
        "2025-05-29_21:00:00_2025-05-29_21:00:00_2025-05-29_21:15:00.npz",
        "2025-05-29_21:00:00_2025-05-29_21:15:00_2025-05-29_21:30:00.npz",
    ):
        np.savez(refc / name, matrix=grid)
        np.savez(retop / name, matrix=tops)


def _write_sectors(path):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "HIGH_001", "altitude_from_ft": 35000, "altitude_to_ft": 60000, "capacity": 20},
                "geometry": {"type": "Polygon", "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]]},
            },
            {
                "type": "Feature",
                "properties": {"name": "LOW_001", "altitude_from_ft": 0, "altitude_to_ft": 35000, "capacity": 15},
                "geometry": {"type": "Polygon", "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]]},
            },
        ],
    }
    path.write_text(json.dumps(fc))


@pytest.fixture
def client(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "hackathon_data_bundle"
    scenario_dir = bundle_dir / "asked_at_2025-05-29T21:00:00Z"
    _write_scenario(scenario_dir)
    _write_sectors(bundle_dir / "sectors.geojson")

    monkeypatch.setenv("SCENARIO_DIR", str(scenario_dir))
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    config.get_settings.cache_clear()
    store.get_store.cache_clear()
    bundle.get_bundle.cache_clear()

    from backend.main import app

    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_root_lists_scenario_and_endpoints(client):
    body = client.get("/").json()
    assert body["scenario"] == "asked_at_2025-05-29T21:00:00Z"
    assert "/api/flights" in body["endpoints"]


def test_flights_returns_one_record_per_flight(client):
    flights = client.get("/api/flights").json()
    assert len(flights) == 2
    assert flights[0]["fuel_kg"] > 0
    assert flights[0]["co2_kg"] > flights[0]["fuel_kg"]
    assert "aircraft_class" in flights[0]


def test_flight_detail_by_id(client):
    first = client.get("/api/flights").json()[0]
    detail = client.get(f"/api/flight/{first['id']}").json()
    assert detail["id"] == first["id"]
    assert detail["flight_number"] == "TEST1"


def test_flight_detail_404(client):
    assert client.get("/api/flight/NOPE_x_KJFK").status_code == 404


def test_summary_totals(client):
    summary = client.get("/api/summary").json()
    assert summary["n_flights"] == 2
    assert summary["total_co2_kg"] > summary["total_fuel_kg"]


def test_h3_is_a_list(client):
    assert isinstance(client.get("/api/h3").json(), list)


def test_solve_rebuilds_and_returns_summary(client):
    resp = client.post("/api/solve", json={"force_rebuild": True, "lambda_sector": 1.0})
    assert resp.status_code == 200
    assert resp.json()["n_flights"] == 2


def test_sectors_have_capacity_and_geometry(client):
    sectors = client.get("/api/sectors").json()
    assert {s["name"] for s in sectors} == {"HIGH_001", "LOW_001"}
    assert sectors[0]["capacity"] > 0
    assert sectors[0]["geometry"]["type"] == "Polygon"
    assert sectors[0]["load"] >= 0


def test_sector_load_reports_over_demand_flag(client):
    loads = client.get("/api/sector_load?t=3").json()
    assert all(isinstance(item["over_demand"], bool) for item in loads)
    assert len(loads) == 2


def test_weather_returns_grids_for_the_covering_strip(client):
    resp = client.get("/api/weather?t=2025-05-29T21:07:00Z")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid_from"] == "2025-05-29T21:00:00+00:00"
    assert body["shape"] == [8, 8]
    assert body["refc"][2][2] == 45.0  # dangerous cell preserved
    assert body["refc"][0][0] is None   # nodata -> null
    assert body["retop"][2][2] == 30000


def test_weather_invalid_timestamp_is_400(client):
    assert client.get("/api/weather?t=not-a-date").status_code == 400

"""Sector occupancy tests over a synthetic 1-sector airspace. Offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.algorithm.sectors import aggregate_sectors
from src.data.ingest import Flight, Scenario

T = lambda h, m: datetime(2025, 5, 29, h, m, tzinfo=timezone.utc)  # noqa: E731


def _sectors_file(tmp_path, capacity):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "HIGH_001",
                    "altitude_from_ft": 35000,
                    "altitude_to_ft": 60000,
                    "capacity": capacity,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]],
                },
            }
        ],
    }
    path = tmp_path / "sectors.geojson"
    path.write_text(json.dumps(fc))
    return path


def _flight(number, alt, lats, lons):
    return Flight(
        flight_number=number,
        take_off_time=T(21, 0),
        scheduled_landing_time=T(21, 30),
        origin_airport_icao="KAAA",
        destination_airport_icao="KBBB",
        cruise_altitude_ft=alt,
        cruise_speed_kt=460,
        lats=tuple(lats),
        lons=tuple(lons),
        is_airborne=False,
    )


def _scenario(flights):
    return Scenario(
        asked_at=T(21, 0), window_start=T(21, 0), window_end=T(22, 0), flights=tuple(flights)
    )


def test_two_high_flights_through_one_sector_are_over_demand(tmp_path):
    path = _sectors_file(tmp_path, capacity=1)
    flights = [
        _flight("A", 37000, [40.5, 40.5], [-100.5, -98.5]),
        _flight("B", 37000, [40.5, 40.5], [-100.5, -98.5]),
    ]
    result = aggregate_sectors(_scenario(flights), path)

    high = result["sectors"]["HIGH_001"]
    assert high["band"] == "HIGH"
    assert high["peak_load"] == 2
    assert high["over_demand"] is True
    assert result["n_overloaded"] == 1
    assert all(isinstance(k, str) for k in high["by_bin"])


def test_low_flight_does_not_occupy_a_high_sector(tmp_path):
    path = _sectors_file(tmp_path, capacity=5)
    flights = [_flight("LOWJET", 28000, [40.5, 40.5], [-100.5, -98.5])]
    result = aggregate_sectors(_scenario(flights), path)
    assert result["sectors"] == {}


def test_flight_clear_of_the_sector_has_no_occupancy(tmp_path):
    path = _sectors_file(tmp_path, capacity=5)
    flights = [_flight("FARAWAY", 37000, [30.0, 30.0], [-80.0, -78.0])]
    result = aggregate_sectors(_scenario(flights), path)
    assert result["sectors"] == {}


def test_under_capacity_is_not_over_demand(tmp_path):
    path = _sectors_file(tmp_path, capacity=5)
    flights = [_flight("SOLO", 37000, [40.5, 40.5], [-100.5, -98.5])]
    result = aggregate_sectors(_scenario(flights), path)
    high = result["sectors"]["HIGH_001"]
    assert high["peak_load"] == 1
    assert high["over_demand"] is False
    assert result["n_overloaded"] == 0

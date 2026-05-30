"""Optimizer tests — altitude pass (storm clearance) and departure-time capacity
repair, on small synthetic scenarios. Offline."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from src.algorithm.fuel import estimate_fuel
from src.algorithm.optimize import optimize
from src.algorithm.sectors import capacity_map, compute_occupancy, load_bands, n_bins_for
from src.data.ingest import Flight, Scenario
from src.data.weather import WeatherGrid

T = lambda h, m: datetime(2025, 5, 29, h, m, tzinfo=timezone.utc)  # noqa: E731


def _flight(number, alt, lats, lons, takeoff=(21, 0), land=(21, 30)):
    return Flight(
        flight_number=number,
        take_off_time=T(*takeoff),
        scheduled_landing_time=T(*land),
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


def _sectors_file(tmp_path, capacity):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "HIGH_001", "altitude_from_ft": 35000, "altitude_to_ft": 60000, "capacity": capacity},
                "geometry": {"type": "Polygon", "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]]},
            }
        ],
    }
    path = tmp_path / "sectors.geojson"
    path.write_text(json.dumps(fc))
    return path


def _storm_grid(tmp_path):
    refc = tmp_path / "wx" / "refc"
    retop = tmp_path / "wx" / "retop"
    refc.mkdir(parents=True)
    retop.mkdir(parents=True)
    name = "2025-05-29_21:00:00_2025-05-29_21:00:00_2025-05-29_22:00:00.npz"
    r = np.full((256, 358), -60.0)
    t = np.full((256, 358), -1.0)
    r[0, 0] = 55.0       # dangerous reflectivity at the NW corner
    t[0, 0] = 33000.0    # storm top at 33,000 ft -> clearable by climbing
    np.savez(refc / name, matrix=r)
    np.savez(retop / name, matrix=t)
    return WeatherGrid(tmp_path)


def test_altitude_pass_climbs_to_clear_a_storm(tmp_path):
    from src.algorithm.sectors import HIGH_FLOOR_FT  # noqa: F401

    grid = _storm_grid(tmp_path)
    # Flight at 31,000 ft under a 33,000 ft storm top, sitting in the NW corner cell.
    flight = _flight("STORMY", 31000, [55.77, 55.77], [-135.0, -134.9])
    scenario = _scenario([flight])
    baseline = [estimate_fuel(flight, weather=grid)]
    assert baseline[0].storm_nm > 0  # exposed at baseline

    result = optimize(scenario, baseline, weather=grid)

    assert result.altitudes[0] > 31000  # climbed
    assert result.estimates[0].storm_nm == 0  # cleared the storm
    assert result.summary["fuel_saved_kg"] > 0
    assert result.summary["n_altitude_changes"] == 1
    assert result.changes[0]["altitude"]["to"] == result.altitudes[0]


def test_departure_repair_relieves_an_overloaded_sector(tmp_path):
    path = _sectors_file(tmp_path, capacity=1)
    # Two short HIGH flights crossing the same sector inside one 15-min bin
    # (load 2 > cap 1); a +15 min shift moves one into the next bin.
    flights = [
        _flight(f"F{i}", 37000, [40.5, 40.5], [-100.5, -98.5], takeoff=(21, 2), land=(21, 12))
        for i in range(2)
    ]
    scenario = _scenario(flights)
    baseline = [estimate_fuel(f) for f in flights]

    result = optimize(scenario, baseline, bands=load_bands(path))

    assert result.summary["overloaded_sectors_before"] == 1
    assert result.summary["overloaded_sectors_after"] == 0
    assert result.summary["n_departure_changes"] >= 1
    assert any(t != f.take_off_time for t, f in zip(result.takeoffs, flights))


def test_departure_repair_reduces_a_hard_overload(tmp_path):
    # Three flights, capacity 1: not fully separable with +/-15 min, but the
    # greedy repair must still reduce the peak below the baseline of 3.
    path = _sectors_file(tmp_path, capacity=1)
    flights = [
        _flight(f"H{i}", 37000, [40.5, 40.5], [-100.5, -98.5], takeoff=(21, 2), land=(21, 12))
        for i in range(3)
    ]
    scenario = _scenario(flights)
    baseline = [estimate_fuel(f) for f in flights]
    bands = load_bands(path)
    result = optimize(scenario, baseline, bands=bands)

    counts, _ = compute_occupancy(
        flights, bands, scenario.window_start, n_bins_for(scenario, 15), takeoffs=result.takeoffs
    )
    assert max(counts.values()) < 3  # peak reduced from the baseline of 3


def test_no_optimization_when_nothing_to_fix(tmp_path):
    path = _sectors_file(tmp_path, capacity=10)
    flight = _flight("CALM", 37000, [40.5, 40.5], [-100.5, -98.5])
    scenario = _scenario([flight])
    baseline = [estimate_fuel(flight)]

    result = optimize(scenario, baseline, bands=load_bands(path))

    assert result.changes == []
    assert result.summary["fuel_saved_kg"] == 0
    assert result.summary["overloaded_sectors_after"] == 0


def test_repair_leaves_separable_traffic_within_capacity(tmp_path):
    path = _sectors_file(tmp_path, capacity=1)
    flights = [
        _flight(f"G{i}", 37000, [40.5, 40.5], [-100.5, -98.5], takeoff=(21, 2), land=(21, 12))
        for i in range(2)
    ]
    scenario = _scenario(flights)
    baseline = [estimate_fuel(f) for f in flights]
    bands = load_bands(path)
    caps = capacity_map(bands)

    result = optimize(scenario, baseline, bands=bands)

    counts, _ = compute_occupancy(
        flights, bands, scenario.window_start, n_bins_for(scenario, 15), takeoffs=result.takeoffs
    )
    assert max(counts.values()) <= caps["HIGH_001"]

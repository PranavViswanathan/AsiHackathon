"""A* lateral reroute tests over synthetic storm walls. Offline."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import numpy as np

from src.algorithm.astar import reroute
from src.algorithm.fuel import estimate_fuel
from src.algorithm.grid import haversine_nm, route_distance_nm
from src.algorithm.optimize import optimize
from src.data.ingest import Flight, Scenario
from src.data.weather import WeatherGrid

T = lambda h, m: datetime(2025, 5, 29, h, m, tzinfo=timezone.utc)  # noqa: E731

# Long valid window so node times across the transit fall inside the one strip.
STRIP = "2025-05-29_21:00:00_2025-05-29_21:00:00_2025-05-30_15:00:00.npz"


def _flight(lats, lons, alt=36000, speed=460):
    return Flight(
        flight_number="RR1",
        take_off_time=T(21, 0),
        scheduled_landing_time=T(23, 0),
        origin_airport_icao="KAAA",
        destination_airport_icao="KBBB",
        cruise_altitude_ft=alt,
        cruise_speed_kt=speed,
        lats=tuple(lats),
        lons=tuple(lons),
        is_airborne=False,
    )


def _grid(tmp_path, refc, retop):
    refc_dir = tmp_path / "wx" / "refc"
    retop_dir = tmp_path / "wx" / "retop"
    refc_dir.mkdir(parents=True)
    retop_dir.mkdir(parents=True)
    np.savez(refc_dir / STRIP, matrix=refc)
    np.savez(retop_dir / STRIP, matrix=retop)
    return WeatherGrid(tmp_path)


def _wall_grid(tmp_path, *, blocked: bool):
    # A north-south storm wall across cols 165-182 (~lon -104..-101). With a gap it
    # spans only lat ~38-42; fully blocked it spans the whole O-D corridor.
    refc = np.full((256, 358), -60.0)
    retop = np.full((256, 358), -1.0)
    rows = slice(80, 171) if blocked else slice(104, 136)
    refc[rows, 165:182] = 50.0
    retop[rows, 165:182] = 45000.0  # echo-top above max cruise -> unclearable by altitude
    return _grid(tmp_path, refc, retop)


# West->east leg at lat 40 whose direct path crosses the wall longitude.
WEST, EAST = (40.0, -110.0), (40.0, -95.0)
DIRECT_NM = haversine_nm(*WEST, *EAST)


def test_direct_path_hits_the_wall(tmp_path):
    grid = _wall_grid(tmp_path, blocked=False)
    flight = _flight([WEST[0], EAST[0]], [WEST[1], EAST[1]])
    assert estimate_fuel(flight, weather=grid).storm_nm > 0


def test_reroute_detours_around_the_wall(tmp_path):
    grid = _wall_grid(tmp_path, blocked=False)
    flight = _flight([WEST[0], EAST[0]], [WEST[1], EAST[1]])

    path = reroute(flight, 36000, T(21, 0), weather=grid)

    assert path is not None
    rerouted = replace(flight, lats=tuple(p[0] for p in path), lons=tuple(p[1] for p in path))
    assert estimate_fuel(rerouted, weather=grid).storm_nm == 0  # detour clears the storm
    length = route_distance_nm([p[0] for p in path], [p[1] for p in path])
    assert length <= 1.6 * DIRECT_NM + 1  # bounded detour
    assert length > DIRECT_NM  # genuinely longer than the straight line


def test_reroute_returns_none_when_fully_blocked(tmp_path):
    grid = _wall_grid(tmp_path, blocked=True)
    flight = _flight([WEST[0], EAST[0]], [WEST[1], EAST[1]])
    assert reroute(flight, 36000, T(21, 0), weather=grid) is None


def test_reroute_clear_corridor_is_near_direct(tmp_path):
    grid = _grid(tmp_path, np.full((256, 358), -60.0), np.full((256, 358), -1.0))
    flight = _flight([WEST[0], EAST[0]], [WEST[1], EAST[1]])
    path = reroute(flight, 36000, T(21, 0), weather=grid)
    assert path is not None
    length = route_distance_nm([p[0] for p in path], [p[1] for p in path])
    assert length <= 1.2 * DIRECT_NM + 1  # no storm -> roughly straight


def test_optimizer_reroutes_a_flight_altitude_cannot_clear(tmp_path):
    grid = _wall_grid(tmp_path, blocked=False)
    flight = _flight([WEST[0], EAST[0]], [WEST[1], EAST[1]])
    scenario = Scenario(asked_at=T(21, 0), window_start=T(21, 0), window_end=T(23, 30), flights=(flight,))
    baseline = [estimate_fuel(flight, weather=grid)]
    assert baseline[0].storm_nm > 0

    result = optimize(scenario, baseline, weather=grid)

    assert result.summary["n_reroutes"] == 1
    assert result.estimates[0].storm_nm == 0
    assert result.routes[0] != (flight.lats, flight.lons)
    assert result.summary["storm_flights_after"] < result.summary["storm_flights_before"]
    assert "reroute around the storm" in result.changes[0]["reason"]

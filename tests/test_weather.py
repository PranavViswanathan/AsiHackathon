"""Storm-sampling tests over a tiny synthetic weather strip, plus the storm
penalty's effect on fuel. Offline."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from pytest import approx

from src.algorithm.fuel import STORM_FUEL_PENALTY, estimate_fuel
from src.data.weather import LAT_MAX, LON_MIN, WeatherGrid, latlon_to_ij
from tests.test_fuel import make_flight

WHEN = datetime(2025, 5, 29, 21, 5, tzinfo=timezone.utc)


def _build_strip(tmp_path, refc_value, retop_value):
    refc = tmp_path / "wx" / "refc"
    retop = tmp_path / "wx" / "retop"
    refc.mkdir(parents=True)
    retop.mkdir(parents=True)
    name = "2025-05-29_21:00:00_2025-05-29_21:00:00_2025-05-29_21:15:00.npz"
    r = np.full((256, 358), -60.0)
    t = np.full((256, 358), -1.0)
    r[0, 0] = refc_value
    t[0, 0] = retop_value
    np.savez(refc / name, matrix=r)
    np.savez(retop / name, matrix=t)
    return tmp_path


def test_latlon_to_ij_corner_is_origin():
    assert latlon_to_ij(LAT_MAX, LON_MIN) == (0, 0)


def test_latlon_to_ij_outside_conus_is_none():
    assert latlon_to_ij(10.0, -100.0) is None


def test_exposed_when_dangerous_and_below_storm_top(tmp_path):
    grid = WeatherGrid(_build_strip(tmp_path, refc_value=45.0, retop_value=40000.0))
    exp = grid.exposure(LAT_MAX, LON_MIN, altitude_ft=30000, when=WHEN)
    assert exp.exposed is True
    assert exp.refc_dbz == approx(45.0)


def test_not_exposed_when_overflying_storm_top(tmp_path):
    grid = WeatherGrid(_build_strip(tmp_path, refc_value=45.0, retop_value=25000.0))
    assert grid.exposure(LAT_MAX, LON_MIN, altitude_ft=37000, when=WHEN).exposed is False


def test_not_exposed_when_reflectivity_is_weak(tmp_path):
    grid = WeatherGrid(_build_strip(tmp_path, refc_value=20.0, retop_value=40000.0))
    assert grid.exposure(LAT_MAX, LON_MIN, altitude_ft=30000, when=WHEN).exposed is False


def test_nodata_cell_is_not_exposed(tmp_path):
    grid = WeatherGrid(_build_strip(tmp_path, refc_value=-60.0, retop_value=-1.0))
    assert grid.exposure(LAT_MAX, LON_MIN, altitude_ft=30000, when=WHEN).exposed is False


def test_empty_scenario_grid_is_falsy(tmp_path):
    assert not WeatherGrid(tmp_path)


def test_storm_penalty_adds_fuel(tmp_path):
    # A flight whose first waypoint sits in the dangerous corner cell.
    grid = WeatherGrid(_build_strip(tmp_path, refc_value=50.0, retop_value=45000.0))
    flight = make_flight(
        lats=[LAT_MAX, LAT_MAX], lons=[LON_MIN, LON_MIN + 0.1],
        cruise_speed_kt=460, cruise_altitude_ft=34000,
    )
    with_storm = estimate_fuel(flight, weather=grid)
    without = estimate_fuel(flight)

    assert with_storm.storm_nm > 0
    assert with_storm.max_refc_dbz == approx(50.0)
    assert with_storm.storm_penalty_kg > 0
    assert with_storm.fuel_kg == approx(without.fuel_kg * (1 + STORM_FUEL_PENALTY), rel=1e-6)

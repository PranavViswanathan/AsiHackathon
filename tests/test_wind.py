"""Wind model tests — all offline (no Open-Meteo calls). Covers the
meteorological direction convention, along-track projection, bilinear sampling,
cache round-trip, and the wind effect on fuel (tailwind cheaper, headwind dearer)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from pytest import approx

from src.algorithm.fuel import estimate_fuel
from src.data.wind import (
    WindField,
    along_track_kt,
    fetch_wind_field,
    load_or_fetch_wind,
    met_wind_to_uv,
    parse_location_response,
)
from tests.test_fuel import make_flight

T0 = datetime(2025, 5, 29, 21, 0, tzinfo=timezone.utc)


def test_wind_from_north_points_south():
    # wind coming FROM 0deg (north) blows TOWARD the south: v negative, u ~0
    u, v = met_wind_to_uv(50.0, 0.0)
    assert u == approx(0.0, abs=1e-9)
    assert v == approx(-50.0, rel=1e-9)


def test_wind_from_west_points_east():
    u, v = met_wind_to_uv(30.0, 270.0)
    assert u == approx(30.0, rel=1e-9)
    assert v == approx(0.0, abs=1e-6)


def test_along_track_tailwind_is_positive():
    # wind blowing east (u=+), flying east (bearing 90) -> tailwind
    assert along_track_kt(40.0, 0.0, 90.0) == approx(40.0, rel=1e-9)
    # flying west into it -> headwind
    assert along_track_kt(40.0, 0.0, 270.0) == approx(-40.0, rel=1e-9)


def _uniform_field(u_east: float, v_north: float) -> WindField:
    lats = np.array([20.0, 60.0])
    lons = np.array([-140.0, -60.0])
    shape = (1, 2, 2)
    return WindField(
        lats=lats,
        lons=lons,
        times=[T0],
        u={250: np.full(shape, u_east)},
        v={250: np.full(shape, v_north)},
    )


def test_sample_uv_is_uniform_across_a_constant_field():
    field = _uniform_field(25.0, -10.0)
    u, v = field.sample_uv(40.0, -100.0, T0, 34000)
    assert u == approx(25.0)
    assert v == approx(-10.0)


def test_bilinear_interpolates_between_corners():
    lats = np.array([0.0, 10.0])
    lons = np.array([0.0, 10.0])
    u = np.array([[[0.0, 0.0], [10.0, 10.0]]])  # varies with latitude only
    field = WindField(lats=lats, lons=lons, times=[T0], u={250: u}, v={250: np.zeros((1, 2, 2))})
    assert field.sample_uv(5.0, 5.0, T0, 34000)[0] == approx(5.0)


def test_cache_round_trip(tmp_path):
    field = _uniform_field(12.0, -7.0)
    path = tmp_path / "wind_cache.npz"
    field.save(path)
    restored = WindField.load(path)
    assert restored.sample_uv(45.0, -110.0, T0, 34000) == approx((12.0, -7.0))


def test_tailwind_lowers_fuel_and_headwind_raises_it():
    # eastbound flight; east wind is a tailwind, west wind a headwind.
    flight = make_flight(
        lats=[40.0, 40.0], lons=[-100.0, -90.0], cruise_speed_kt=460, cruise_altitude_ft=34000
    )
    tail = estimate_fuel(flight, wind=_uniform_field(50.0, 0.0))
    head = estimate_fuel(flight, wind=_uniform_field(-50.0, 0.0))
    zero = estimate_fuel(flight)

    assert tail.fuel_kg < zero.fuel_kg < head.fuel_kg
    assert tail.time_hr < zero.time_hr < head.time_hr
    assert tail.tailwind_nm > 0 and head.headwind_nm > 0


def test_parse_location_response_builds_uv():
    payload = {
        "hourly": {
            "time": ["2025-05-29T21:00", "2025-05-29T22:00"],
            "wind_speed_250hPa": [50.0, 50.0],
            "wind_direction_250hPa": [270.0, 270.0],
        }
    }
    times, u, v = parse_location_response(payload, (250,))
    assert len(times) == 2
    assert u[250][0] == approx(50.0)  # from-west -> blows east
    assert v[250][0] == approx(0.0, abs=1e-6)


def test_fetch_falls_back_to_none_without_network(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr("src.data.wind.fetch_wind_field", boom)
    assert load_or_fetch_wind(T0, T0, tmp_path / "missing.npz") is None


def test_fetch_uses_mocked_http(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "hourly": {
                        "time": ["2025-05-29T21:00"],
                        "wind_speed_200hPa": [10.0],
                        "wind_direction_200hPa": [270.0],
                        "wind_speed_250hPa": [10.0],
                        "wind_direction_250hPa": [270.0],
                    }
                }
            ]

    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())
    field = fetch_wind_field(T0, T0, grid_step=40.0, chunk=1)
    # uniform west wind -> eastward u positive everywhere
    assert field.sample_uv(40.0, -100.0, T0, 38000)[0] == approx(10.0, rel=1e-6)

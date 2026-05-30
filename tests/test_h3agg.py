"""H3 aggregation tests over a couple of synthetic flights. Offline."""

from __future__ import annotations

import dataclasses

import h3
from pytest import approx

from src.algorithm.fuel import estimate_fuel
from src.algorithm.h3agg import aggregate_h3
from tests.test_fuel import make_flight


def _flight_and_estimate(lats, lons, speed=460, alt=37000, number="TEST123"):
    flight = make_flight(lats=lats, lons=lons, cruise_speed_kt=speed, cruise_altitude_ft=alt)
    flight = dataclasses.replace(flight, flight_number=number)
    return flight, estimate_fuel(flight)


def test_empty_input_returns_empty_list():
    assert aggregate_h3([], []) == []


def test_cells_are_valid_h3_indices_at_the_requested_resolution():
    flight, est = _flight_and_estimate([40.0, 41.0], [-100.0, -95.0])
    cells = aggregate_h3([flight], [est], resolution=4)
    assert cells
    for cell in cells:
        assert h3.is_valid_cell(cell["h3"])
        assert h3.get_resolution(cell["h3"]) == 4


def test_fuel_is_conserved_across_cells():
    flight, est = _flight_and_estimate([40.0, 42.0], [-100.0, -90.0])
    cells = aggregate_h3([flight], [est])
    assert sum(c["fuel_kg"] for c in cells) == approx(est.fuel_kg, rel=1e-3)


def test_two_flights_sharing_a_cell_increment_n_flights():
    f1, e1 = _flight_and_estimate([40.0, 40.0], [-100.0, -99.0], number="AAA1")
    f2, e2 = _flight_and_estimate([40.0, 40.0], [-100.0, -99.0], number="BBB2")
    cells = aggregate_h3([f1, f2], [e1, e2], resolution=4)
    busiest = max(cells, key=lambda c: c["n_flights"])
    assert busiest["n_flights"] == 2
    assert busiest["congestion"] == approx(1.0)
    assert busiest["mean_kg"] == approx(busiest["fuel_kg"] / 2)


def test_zero_distance_flight_is_skipped():
    flight, est = _flight_and_estimate([40.0], [-100.0])
    assert aggregate_h3([flight], [est]) == []

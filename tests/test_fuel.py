from datetime import datetime, timezone

from pytest import approx

from src.algorithm.fuel import (
    CO2_PER_KG_FUEL,
    FUEL_FLOW_KG_HR,
    classify_aircraft,
    estimate_fuel,
)
from src.data.ingest import Flight


def make_flight(*, lats, lons, cruise_speed_kt, cruise_altitude_ft):
    return Flight(
        flight_number="TEST123",
        take_off_time=datetime(2025, 5, 29, 21, 0, tzinfo=timezone.utc),
        scheduled_landing_time=datetime(2025, 5, 29, 22, 0, tzinfo=timezone.utc),
        origin_airport_icao="KAAA",
        destination_airport_icao="KBBB",
        cruise_altitude_ft=cruise_altitude_ft,
        cruise_speed_kt=cruise_speed_kt,
        lats=tuple(lats),
        lons=tuple(lons),
        is_airborne=False,
    )


def test_slow_aircraft_is_a_regional_jet():
    assert classify_aircraft(cruise_speed_kt=400, cruise_altitude_ft=30000) == "regional"


def test_midspeed_aircraft_is_a_narrowbody():
    assert classify_aircraft(cruise_speed_kt=460, cruise_altitude_ft=38000) == "narrowbody"


def test_fast_aircraft_is_a_widebody():
    assert classify_aircraft(cruise_speed_kt=500, cruise_altitude_ft=41000) == "widebody"


def test_zero_wind_fuel_equals_fuel_flow_times_flight_hours():
    # one degree of latitude (~60 nm) flown at 60 kt takes exactly one hour,
    # so fuel should equal the class fuel flow for that one hour.
    flight = make_flight(
        lats=[0.0, 1.0], lons=[0.0, 0.0], cruise_speed_kt=60, cruise_altitude_ft=38000
    )
    estimate = estimate_fuel(flight)

    assert estimate.time_hr == approx(1.0, rel=0.01)
    assert estimate.fuel_kg == approx(FUEL_FLOW_KG_HR[estimate.aircraft_class], rel=0.01)


def test_co2_is_fuel_times_emission_factor():
    flight = make_flight(
        lats=[0.0, 2.0], lons=[0.0, 0.0], cruise_speed_kt=460, cruise_altitude_ft=38000
    )
    estimate = estimate_fuel(flight)

    assert estimate.co2_kg == approx(estimate.fuel_kg * CO2_PER_KG_FUEL, rel=1e-6)


def test_longer_route_burns_more_fuel():
    short = make_flight(
        lats=[0.0, 1.0], lons=[0.0, 0.0], cruise_speed_kt=460, cruise_altitude_ft=38000
    )
    long = make_flight(
        lats=[0.0, 5.0], lons=[0.0, 0.0], cruise_speed_kt=460, cruise_altitude_ft=38000
    )

    assert estimate_fuel(long).fuel_kg > estimate_fuel(short).fuel_kg

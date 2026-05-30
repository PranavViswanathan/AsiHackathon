from datetime import datetime
from pathlib import Path

from src.data.ingest import Flight, Scenario, load_scenario

SCENARIO_DIR = Path("data/hackathon_data_bundle/asked_at_2025-05-29T21:00:00Z")
EXPECTED_FLIGHTS = 16687


def test_load_scenario_returns_a_scenario():
    scenario = load_scenario(SCENARIO_DIR)
    assert isinstance(scenario, Scenario)


def test_scenario_has_the_expected_flight_count():
    scenario = load_scenario(SCENARIO_DIR)
    assert len(scenario.flights) == EXPECTED_FLIGHTS


def test_flights_are_parsed_into_typed_records():
    scenario = load_scenario(SCENARIO_DIR)
    flight = scenario.flights[0]

    assert isinstance(flight, Flight)
    assert isinstance(flight.take_off_time, datetime)
    assert isinstance(flight.is_airborne, bool)
    assert len(flight.lats) == len(flight.lons)
    assert flight.origin_airport_icao.startswith("K")


def test_window_bounds_are_parsed_as_datetimes():
    scenario = load_scenario(SCENARIO_DIR)
    assert isinstance(scenario.asked_at, datetime)
    assert scenario.window_start < scenario.window_end


def test_flight_id_combines_number_takeoff_and_origin():
    scenario = load_scenario(SCENARIO_DIR)
    flight = scenario.flights[0]
    assert flight.flight_number in flight.id
    assert flight.origin_airport_icao in flight.id

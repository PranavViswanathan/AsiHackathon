"""Fuel-burn model (kg). Phase 1 is a zero-wind, constant-cruise estimate;
wind-adjusted ground speed and storm penalties arrive in later phases."""

from __future__ import annotations

from dataclasses import dataclass

from src.algorithm.grid import route_distance_nm
from src.data.ingest import Flight

CO2_PER_KG_FUEL = 3.16

FUEL_FLOW_KG_HR = {
    "regional": 1100.0,
    "narrowbody": 2500.0,
    "widebody": 6000.0,
}


def classify_aircraft(*, cruise_speed_kt: float, cruise_altitude_ft: float) -> str:
    if cruise_speed_kt < 420:
        return "regional"
    if cruise_speed_kt < 480:
        return "narrowbody"
    return "widebody"


@dataclass(frozen=True)
class FuelEstimate:
    aircraft_class: str
    distance_nm: float
    time_hr: float
    fuel_kg: float
    co2_kg: float


def estimate_fuel(flight: Flight) -> FuelEstimate:
    distance_nm = route_distance_nm(flight.lats, flight.lons)
    aircraft_class = classify_aircraft(
        cruise_speed_kt=flight.cruise_speed_kt,
        cruise_altitude_ft=flight.cruise_altitude_ft,
    )
    ground_speed_kt = flight.cruise_speed_kt
    time_hr = distance_nm / ground_speed_kt if ground_speed_kt > 0 else 0.0
    fuel_kg = FUEL_FLOW_KG_HR[aircraft_class] * time_hr
    return FuelEstimate(
        aircraft_class=aircraft_class,
        distance_nm=distance_nm,
        time_hr=time_hr,
        fuel_kg=fuel_kg,
        co2_kg=fuel_kg * CO2_PER_KG_FUEL,
    )

"""Fuel-burn model (kg).

With no wind or weather supplied this is the Phase 1 zero-wind, constant-cruise
estimate (fuel = class fuel-flow x distance / TAS). Pass a `WindField` to make
ground speed wind-aware, and a `WeatherGrid` to add a storm-avoidance penalty on
convectively exposed segments. Both are optional and independent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.algorithm.grid import haversine_nm, initial_bearing_deg, route_distance_nm
from src.data.ingest import Flight
from src.data.weather import WeatherGrid
from src.data.wind import WindField

CO2_PER_KG_FUEL = 3.16
GROUND_SPEED_FLOOR_KT = 150.0  # guard against absurd ground speed under strong headwind
STORM_FUEL_PENALTY = 0.15      # fractional fuel adder on a storm-exposed segment

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
    # Phase 3 additions (defaults keep the zero-wind call backward compatible):
    base_fuel_kg: float = 0.0       # zero-wind, no-storm reference
    headwind_nm: float = 0.0        # distance flown into a headwind
    tailwind_nm: float = 0.0        # distance flown with a tailwind
    mean_along_track_kt: float = 0.0  # distance-weighted along-track wind (+ = tailwind)
    storm_nm: float = 0.0           # storm-exposed distance
    max_refc_dbz: float = 0.0       # peak reflectivity encountered
    storm_penalty_kg: float = 0.0   # fuel added by the storm penalty


def estimate_fuel(
    flight: Flight,
    wind: WindField | None = None,
    weather: WeatherGrid | None = None,
) -> FuelEstimate:
    lats, lons = flight.lats, flight.lons
    aircraft_class = classify_aircraft(
        cruise_speed_kt=flight.cruise_speed_kt,
        cruise_altitude_ft=flight.cruise_altitude_ft,
    )
    fuel_flow = FUEL_FLOW_KG_HR[aircraft_class]
    tas = flight.cruise_speed_kt
    total_distance = route_distance_nm(lats, lons)
    duration_hr = _duration_hr(flight)

    fuel = base_fuel = time_hr = 0.0
    headwind_nm = tailwind_nm = along_weighted = 0.0
    storm_nm = max_refc = storm_penalty = 0.0
    cumulative = 0.0

    for i in range(len(lats) - 1):
        seg_nm = haversine_nm(lats[i], lons[i], lats[i + 1], lons[i + 1])
        if seg_nm <= 0 or tas <= 0:
            continue
        mid_lat = (lats[i] + lats[i + 1]) / 2
        mid_lon = (lons[i] + lons[i + 1]) / 2
        when = _segment_time(flight, (cumulative + seg_nm / 2), total_distance, duration_hr)

        along = 0.0
        if wind is not None and when is not None:
            bearing = initial_bearing_deg(lats[i], lons[i], lats[i + 1], lons[i + 1])
            along = wind.along_track_kt(mid_lat, mid_lon, when, flight.cruise_altitude_ft, bearing)
        ground_speed = max(tas + along, GROUND_SPEED_FLOOR_KT) if wind is not None else tas

        seg_time = seg_nm / ground_speed
        seg_fuel = fuel_flow * seg_time

        if weather is not None and when is not None:
            exposure = weather.exposure(mid_lat, mid_lon, flight.cruise_altitude_ft, when)
            if exposure.exposed:
                penalty = seg_fuel * STORM_FUEL_PENALTY
                seg_fuel += penalty
                storm_penalty += penalty
                storm_nm += seg_nm
                max_refc = max(max_refc, exposure.refc_dbz)

        fuel += seg_fuel
        base_fuel += fuel_flow * (seg_nm / tas)
        time_hr += seg_time
        if along < 0:
            headwind_nm += seg_nm
        elif along > 0:
            tailwind_nm += seg_nm
        along_weighted += along * seg_nm
        cumulative += seg_nm

    mean_along = along_weighted / total_distance if total_distance > 0 else 0.0
    return FuelEstimate(
        aircraft_class=aircraft_class,
        distance_nm=total_distance,
        time_hr=time_hr,
        fuel_kg=fuel,
        co2_kg=fuel * CO2_PER_KG_FUEL,
        base_fuel_kg=base_fuel,
        headwind_nm=headwind_nm,
        tailwind_nm=tailwind_nm,
        mean_along_track_kt=mean_along,
        storm_nm=storm_nm,
        max_refc_dbz=max_refc,
        storm_penalty_kg=storm_penalty,
    )


def _duration_hr(flight: Flight) -> float | None:
    delta = (flight.scheduled_landing_time - flight.take_off_time).total_seconds() / 3600.0
    return delta if delta > 0 else None


def _segment_time(
    flight: Flight, distance_so_far: float, total_distance: float, duration_hr: float | None
) -> datetime | None:
    if duration_hr is None or total_distance <= 0:
        return None
    fraction = min(max(distance_so_far / total_distance, 0.0), 1.0)
    return flight.take_off_time + timedelta(hours=fraction * duration_hr)

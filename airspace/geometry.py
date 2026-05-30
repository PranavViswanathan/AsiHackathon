"""Reconstruct where each flight is at a given moment.

Under the bundle's modelling assumption (constant cruise speed, no climb/descent),
a flight's progress is linear in time between ``take_off_time`` and
``scheduled_landing_time``. We map that time fraction onto distance along the
planned waypoint path, then interpolate the lat/lon.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from .data import Flight


def _time_fraction(flight: Flight, t: datetime) -> float:
    """Fraction of the flight completed at time ``t``, clamped to [0, 1]."""
    total = (flight.scheduled_landing_time - flight.take_off_time).total_seconds()
    if total <= 0:
        return 1.0
    return float(np.clip((t - flight.take_off_time).total_seconds() / total, 0.0, 1.0))


def position_at(flight: Flight, t: datetime) -> tuple[float, float]:
    """(lat, lon) of a single flight at time ``t`` (clamped to its endpoints)."""
    frac = _time_fraction(flight, t)
    cum = flight._cumulative_fraction
    lat = float(np.interp(frac, cum, flight.lats))
    lon = float(np.interp(frac, cum, flight.lons))
    return lat, lon


def positions_at(flights: list[Flight], t: datetime, only_active: bool = True):
    """Positions of many flights at time ``t``.

    Returns ``(active_flights, lats, lons)`` where ``lats``/``lons`` are parallel
    numpy arrays. A flight is *active* at ``t`` if
    ``take_off_time <= t <= scheduled_landing_time`` — i.e. actually in the air.

    With ``only_active=False`` every flight is returned (clamped to its first or
    last waypoint when outside its time window), which is occasionally handy for
    debugging but should not be used for occupancy counts.
    """
    out_flights: list[Flight] = []
    lats: list[float] = []
    lons: list[float] = []
    for f in flights:
        if only_active and not (f.take_off_time <= t <= f.scheduled_landing_time):
            continue
        lat, lon = position_at(f, t)
        out_flights.append(f)
        lats.append(lat)
        lons.append(lon)
    return out_flights, np.asarray(lats), np.asarray(lons)

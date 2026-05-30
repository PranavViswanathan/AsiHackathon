"""Core pipeline for the ASI Boston Hackathon 2026 airspace data.

The pieces fit together as:

    routes  -->  positions(t)  -->  sector + altitude band  -->  occupancy vs capacity
    (data)       (geometry)        (sectors)                     (occupancy -> over-demand)

Typical use:

    from airspace import load_scenario, load_sectors, SectorIndex, occupancy_timeline

    scn = load_scenario("2025-07-08T22:00:00Z")
    idx = SectorIndex(load_sectors())
    timeline = occupancy_timeline(scn, idx)
"""

from .data import DATA_ROOT, list_scenarios, load_scenario, load_sectors, Scenario, Flight
from .geometry import positions_at
from .sectors import SectorIndex
from .occupancy import sector_occupancy, occupancy_timeline, over_demand
from .weather import WeatherForecast, blocked_flights, latlon_to_rowcol

__all__ = [
    "DATA_ROOT",
    "list_scenarios",
    "load_scenario",
    "load_sectors",
    "Scenario",
    "Flight",
    "positions_at",
    "SectorIndex",
    "sector_occupancy",
    "occupancy_timeline",
    "over_demand",
    "WeatherForecast",
    "blocked_flights",
    "latlon_to_rowcol",
]

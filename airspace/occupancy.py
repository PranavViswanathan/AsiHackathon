"""Per-sector occupancy over time, and where it exceeds capacity (over-demand).

This is the reusable core: given a scenario and a sector index, count how many
flights are inside each sector at each timestep, then compare against capacity.
Everything downstream — congestion heatmaps, weather-aware rerouting, ground-delay
optimisation — builds on these counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .data import Scenario
from .geometry import positions_at
from .sectors import SectorIndex


def sector_occupancy(scenario: Scenario, index: SectorIndex, t: datetime) -> Counter:
    """Map ``sector_name -> number of active flights inside it`` at time ``t``."""
    flights, lats, lons = positions_at(scenario.flights, t, only_active=True)
    names = index.assign_flight_positions(flights, lats, lons)
    return Counter(n for n in names if n is not None)


@dataclass
class OccupancyTimeline:
    """Occupancy counts over a sequence of timesteps.

    ``counts[i]`` is the ``sector_name -> count`` Counter at ``times[i]``.
    """

    times: list[datetime]
    counts: list[Counter]
    index: SectorIndex

    def series(self, sector_name: str) -> np.ndarray:
        """Occupancy of one sector across all timesteps."""
        return np.array([c.get(sector_name, 0) for c in self.counts])

    def peak_per_sector(self) -> dict[str, int]:
        """Max simultaneous occupancy each sector reaches over the timeline."""
        peak: dict[str, int] = {}
        for c in self.counts:
            for name, n in c.items():
                if n > peak.get(name, 0):
                    peak[name] = n
        return peak

    def over_demand_events(self) -> list[dict]:
        """Every (sector, time) where occupancy exceeds capacity, worst first.

        Each event: ``{sector, time, count, capacity, overage}``.
        """
        events = []
        for t, c in zip(self.times, self.counts):
            for name, n in c.items():
                cap = self.index.capacity.get(name)
                if cap is not None and n > cap:
                    events.append(
                        {
                            "sector": name,
                            "time": t,
                            "count": n,
                            "capacity": cap,
                            "overage": n - cap,
                        }
                    )
        events.sort(key=lambda e: e["overage"], reverse=True)
        return events


def _time_grid(scenario: Scenario, step_minutes: int) -> list[datetime]:
    """Timesteps spanning the active period of the scenario's flights."""
    start = min(f.take_off_time for f in scenario.flights)
    end = max(f.scheduled_landing_time for f in scenario.flights)
    step = timedelta(minutes=step_minutes)
    times, t = [], start
    while t <= end:
        times.append(t)
        t += step
    return times


def occupancy_timeline(
    scenario: Scenario,
    index: SectorIndex,
    step_minutes: int = 15,
    times: list[datetime] | None = None,
) -> OccupancyTimeline:
    """Compute sector occupancy across a time grid (default 15-min steps).

    Pass an explicit ``times`` list to align with, e.g., the 15-minute weather
    strips; otherwise the grid spans from the first departure to the last landing.
    """
    if times is None:
        times = _time_grid(scenario, step_minutes)
    counts = [sector_occupancy(scenario, index, t) for t in times]
    return OccupancyTimeline(times=times, counts=counts, index=index)


def over_demand(timeline: OccupancyTimeline) -> list[dict]:
    """Convenience wrapper: the over-demand events of a timeline, worst first."""
    return timeline.over_demand_events()

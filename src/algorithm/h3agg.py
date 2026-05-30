"""H3 energy aggregation. Phase 1 emits an empty heatmap; Phase 4 densifies
routes, bins them to H3 cells, and aggregates fuel and congestion per cell."""

from __future__ import annotations

from typing import Iterable


def aggregate_h3(flight_estimates: Iterable = ()) -> list[dict]:
    return []

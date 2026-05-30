"""H3 energy aggregation. Densifies each route, bins the points to H3 cells, and
aggregates fuel and traffic per cell for the deck.gl heatmap.

Emits `[{h3, fuel_kg, n_flights, mean_kg, congestion}]`, where each flight's fuel
is spread across the cells its route passes through (in proportion to the route
length in each cell) and `congestion` is traffic density normalised to [0, 1]."""

from __future__ import annotations

from typing import Iterable, Sequence

import h3

from src.algorithm.fuel import FuelEstimate
from src.algorithm.grid import haversine_nm
from src.data.ingest import Flight

DEFAULT_RESOLUTION = 4
DEFAULT_STEP_NM = 20.0


def aggregate_h3(
    flights: Iterable[Flight],
    estimates: Iterable[FuelEstimate],
    *,
    resolution: int = DEFAULT_RESOLUTION,
    step_nm: float = DEFAULT_STEP_NM,
) -> list[dict]:
    cell_fuel: dict[str, float] = {}
    cell_flights: dict[str, set[str]] = {}

    for flight, estimate in zip(flights, estimates):
        total_nm = estimate.distance_nm
        if total_nm <= 0 or estimate.fuel_kg <= 0 or len(flight.lats) < 2:
            continue
        fuel_per_nm = estimate.fuel_kg / total_nm
        for lat, lon, piece_nm in _densify(flight.lats, flight.lons, step_nm):
            cell = h3.latlng_to_cell(lat, lon, resolution)
            cell_fuel[cell] = cell_fuel.get(cell, 0.0) + fuel_per_nm * piece_nm
            cell_flights.setdefault(cell, set()).add(flight.id)

    if not cell_fuel:
        return []

    max_flights = max(len(ids) for ids in cell_flights.values())
    cells = []
    for cell, fuel in cell_fuel.items():
        n = len(cell_flights[cell])
        cells.append(
            {
                "h3": cell,
                "fuel_kg": round(fuel, 1),
                "n_flights": n,
                "mean_kg": round(fuel / n, 1),
                "congestion": round(n / max_flights, 4),
            }
        )
    cells.sort(key=lambda c: c["fuel_kg"], reverse=True)
    return cells


def _densify(
    lats: Sequence[float], lons: Sequence[float], step_nm: float
) -> Iterable[tuple[float, float, float]]:
    """Yield (lat, lon, piece_nm) midpoints along the route, ~`step_nm` apart."""
    for i in range(len(lats) - 1):
        seg_nm = haversine_nm(lats[i], lons[i], lats[i + 1], lons[i + 1])
        if seg_nm <= 0:
            continue
        pieces = max(1, int(seg_nm / step_nm))
        piece_nm = seg_nm / pieces
        for k in range(pieces):
            frac = (k + 0.5) / pieces
            yield (
                lats[i] + (lats[i + 1] - lats[i]) * frac,
                lons[i] + (lons[i + 1] - lons[i]) * frac,
                piece_nm,
            )

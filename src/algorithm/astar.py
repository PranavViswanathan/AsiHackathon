"""A* lateral reroute around intense storms.

For a flight that the altitude pass could not lift clear of a storm, search a
coarsened lat/lon grid (the weather grid, downsampled) for the cheapest path from
origin to destination that never enters a storm-exposed cell (`refc >= 40 dBZ` and
`cruise_alt < retop` at the cell's estimated time). The result is a detour polyline
the optimizer re-costs with `estimate_fuel`.

Nodes are grid cells, edges are 8-neighbor moves, edge cost is the same wind-aware
fuel proxy the simulator uses, exposed cells are forbidden (the hard constraint),
and the heuristic is great-circle distance scaled by the minimum possible
fuel-per-nm (admissible, so A* stays optimal)."""

from __future__ import annotations

import heapq
import itertools
from datetime import datetime, timedelta

from src.algorithm.fuel import (
    GROUND_SPEED_FLOOR_KT,
    classify_aircraft,
    cruise_fuel_flow_kg_hr,
)
from src.algorithm.grid import haversine_nm, initial_bearing_deg
from src.data.ingest import Flight
from src.data.weather import COLS, LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, ROWS, WeatherGrid
from src.data.wind import WindField

MAX_TAILWIND_KT = 250.0   # upper bound on winds aloft, for the admissible heuristic
BBOX_MARGIN_DEG = 4.0      # search corridor padding around the O-D bounding box
DEFAULT_STRIDE = 4         # coarsen the 256x358 grid (~50 nm cells)
DEFAULT_MAX_DETOUR = 1.6   # reject detours longer than 1.6x the direct distance
SIMPLIFY_TOL_DEG = 2.0     # drop near-collinear waypoints


def _cell_latlon(r: int, c: int, stride: int) -> tuple[float, float]:
    i = min(r * stride, ROWS - 1)
    j = min(c * stride, COLS - 1)
    lat = LAT_MAX - (i / ROWS) * (LAT_MAX - LAT_MIN)
    lon = LON_MIN + (j / COLS) * (LON_MAX - LON_MIN)
    return lat, lon


def _nearest_cell(lat: float, lon: float, stride: int, n_rows: int, n_cols: int) -> tuple[int, int]:
    i = int(round((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * ROWS))
    j = int(round((lon - LON_MIN) / (LON_MAX - LON_MIN) * COLS))
    return min(max(i // stride, 0), n_rows - 1), min(max(j // stride, 0), n_cols - 1)


def reroute(
    flight: Flight,
    altitude_ft: float,
    takeoff: datetime,
    *,
    weather: WeatherGrid,
    wind: WindField | None = None,
    stride: int = DEFAULT_STRIDE,
    max_detour: float = DEFAULT_MAX_DETOUR,
) -> list[tuple[float, float]] | None:
    """Return a storm-free detour polyline [(lat, lon), ...] or None if none is
    feasible within `max_detour` x the direct distance."""
    lats, lons = flight.lats, flight.lons
    if len(lats) < 2:
        return None
    o_lat, o_lon, d_lat, d_lon = lats[0], lons[0], lats[-1], lons[-1]
    direct_nm = haversine_nm(o_lat, o_lon, d_lat, d_lon)
    if direct_nm <= 0:
        return None

    tas = flight.cruise_speed_kt
    aircraft_class = classify_aircraft(cruise_speed_kt=tas, cruise_altitude_ft=altitude_ft)
    ff = cruise_fuel_flow_kg_hr(aircraft_class, altitude_ft, tas)
    h_factor = ff / (tas + MAX_TAILWIND_KT)  # min possible fuel per nm -> admissible

    n_rows = (ROWS + stride - 1) // stride
    n_cols = (COLS + stride - 1) // stride
    lat_lo, lat_hi = min(o_lat, d_lat) - BBOX_MARGIN_DEG, max(o_lat, d_lat) + BBOX_MARGIN_DEG
    lon_lo, lon_hi = min(o_lon, d_lon) - BBOX_MARGIN_DEG, max(o_lon, d_lon) + BBOX_MARGIN_DEG

    start = _nearest_cell(o_lat, o_lon, stride, n_rows, n_cols)
    goal = _nearest_cell(d_lat, d_lon, stride, n_rows, n_cols)
    if start == goal:
        return None  # too short to reroute on this grid
    g_lat, g_lon = _cell_latlon(*goal, stride)

    def node_time(cum_nm: float) -> datetime:
        return takeoff + timedelta(hours=cum_nm / tas if tas > 0 else 0.0)

    def in_bbox(la: float, lo: float) -> bool:
        return lat_lo <= la <= lat_hi and lon_lo <= lo <= lon_hi

    def blocked(cell: tuple[int, int], la: float, lo: float, cum_nm: float) -> bool:
        if cell == start or cell == goal:
            return False  # endpoints (airports) are fixed
        return weather.exposure(la, lo, altitude_ft, node_time(cum_nm)).exposed

    def heuristic(la: float, lo: float) -> float:
        return haversine_nm(la, lo, g_lat, g_lon) * h_factor

    counter = itertools.count()
    g_cost = {start: 0.0}
    dist_nm = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    s_lat, s_lon = _cell_latlon(*start, stride)
    open_heap = [(heuristic(s_lat, s_lon), next(counter), start)]

    while open_heap:
        _, _, cur = heapq.heappop(open_heap)
        if cur == goal:
            break
        cur_lat, cur_lon = _cell_latlon(*cur, stride)
        cur_dist = dist_nm[cur]
        cur_when = node_time(cur_dist)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nxt = (cur[0] + dr, cur[1] + dc)
                if not (0 <= nxt[0] < n_rows and 0 <= nxt[1] < n_cols):
                    continue
                n_lat, n_lon = _cell_latlon(*nxt, stride)
                if not in_bbox(n_lat, n_lon):
                    continue
                d = haversine_nm(cur_lat, cur_lon, n_lat, n_lon)
                new_dist = cur_dist + d
                if new_dist > max_detour * direct_nm:
                    continue  # prune over-long detours early
                if blocked(nxt, n_lat, n_lon, new_dist):
                    continue
                along = 0.0
                if wind is not None:
                    bearing = initial_bearing_deg(cur_lat, cur_lon, n_lat, n_lon)
                    along = wind.along_track_kt(
                        (cur_lat + n_lat) / 2, (cur_lon + n_lon) / 2, cur_when, altitude_ft, bearing
                    )
                gs = max(tas + along, GROUND_SPEED_FLOOR_KT)
                new_g = g_cost[cur] + ff * d / gs
                if nxt not in g_cost or new_g < g_cost[nxt]:
                    g_cost[nxt] = new_g
                    dist_nm[nxt] = new_dist
                    came[nxt] = cur
                    heapq.heappush(open_heap, (new_g + heuristic(n_lat, n_lon), next(counter), nxt))

    if goal not in came:
        return None
    if dist_nm.get(goal, float("inf")) > max_detour * direct_nm:
        return None

    cells = [goal]
    node = goal
    while node in came:
        node = came[node]
        cells.append(node)
    cells.reverse()

    points = [_cell_latlon(*cell, stride) for cell in cells]
    points[0] = (o_lat, o_lon)   # snap exact origin
    points[-1] = (d_lat, d_lon)  # snap exact destination
    return _simplify(points)


def _simplify(points: list[tuple[float, float]], tol_deg: float = SIMPLIFY_TOL_DEG) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        a, b, c = out[-1], points[i], points[i + 1]
        b1 = initial_bearing_deg(a[0], a[1], b[0], b[1])
        b2 = initial_bearing_deg(b[0], b[1], c[0], c[1])
        if abs((b1 - b2 + 180) % 360 - 180) > tol_deg:
            out.append(b)
    out.append(points[-1])
    return out

"""Sector occupancy. Builds a time-parameterised track for each flight (constant
cruise: position interpolated by time between takeoff and landing), samples it on
a fixed cadence, and counts the distinct flights present in each sector during
each time bin. Capacity comes from `sectors.geojson`; a sector-time bin is
over-demand when its count exceeds capacity.

A point belongs to exactly one sector per altitude band (HIGH `>= 35000 ft`,
LOW below). Spatial lookup is vectorised through a shapely STRtree."""

from __future__ import annotations

import json
import math
from datetime import timedelta
from pathlib import Path

import numpy as np
from shapely import STRtree
from shapely import points as shp_points
from shapely.geometry import shape

from src.algorithm.grid import haversine_nm
from src.data.ingest import Flight, Scenario

HIGH_FLOOR_FT = 35000.0
DEFAULT_SAMPLE_MINUTES = 5
DEFAULT_BIN_MINUTES = 15


def aggregate_sectors(
    scenario: Scenario,
    sectors_path: Path | str,
    *,
    sample_minutes: int = DEFAULT_SAMPLE_MINUTES,
    bin_minutes: int = DEFAULT_BIN_MINUTES,
) -> dict:
    bands = _load_bands(Path(sectors_path))
    window_start = scenario.window_start
    total_minutes = (scenario.window_end - window_start).total_seconds() / 60.0
    n_bins = max(1, math.ceil(total_minutes / bin_minutes))

    # Collect sample points per band, tagged with flight index and time bin.
    samples: dict[str, dict[str, list]] = {
        b: {"lon": [], "lat": [], "flight": [], "bin": []} for b in bands
    }
    for fi, flight in enumerate(scenario.flights):
        band = "HIGH" if flight.cruise_altitude_ft >= HIGH_FLOOR_FT else "LOW"
        if band not in bands:
            continue
        for lon, lat, bin_idx in _track_samples(
            flight, window_start, n_bins, sample_minutes, bin_minutes
        ):
            s = samples[band]
            s["lon"].append(lon)
            s["lat"].append(lat)
            s["flight"].append(fi)
            s["bin"].append(bin_idx)

    occupancy: dict[str, dict[int, set[int]]] = {}
    for band, data in bands.items():
        pts = samples[band]
        if not pts["lon"]:
            continue
        tree, names = data["tree"], data["names"]
        point_geoms = shp_points(np.column_stack([pts["lon"], pts["lat"]]))
        point_idx, poly_idx = tree.query(point_geoms, predicate="within")
        flights = pts["flight"]
        bins = pts["bin"]
        for pi, gi in zip(point_idx, poly_idx):
            name = names[gi]
            bucket = occupancy.setdefault(name, {})
            bucket.setdefault(bins[pi], set()).add(flights[pi])

    sectors_out: dict[str, dict] = {}
    for band, data in bands.items():
        for name, capacity in zip(data["names"], data["capacities"]):
            by_bin = {b: len(ids) for b, ids in occupancy.get(name, {}).items()}
            if not by_bin:
                continue
            peak = max(by_bin.values())
            sectors_out[name] = {
                "band": band,
                "capacity": capacity,
                "peak_load": peak,
                "over_demand": peak > capacity,
                "by_bin": {str(b): load for b, load in sorted(by_bin.items())},
            }

    return {
        "bin_minutes": bin_minutes,
        "window_start": window_start.isoformat(),
        "n_bins": n_bins,
        "n_overloaded": sum(1 for s in sectors_out.values() if s["over_demand"]),
        "sectors": sectors_out,
    }


def _load_bands(sectors_path: Path) -> dict[str, dict]:
    raw = json.loads(sectors_path.read_text())
    grouped: dict[str, dict[str, list]] = {
        "HIGH": {"geoms": [], "names": [], "capacities": []},
        "LOW": {"geoms": [], "names": [], "capacities": []},
    }
    for feature in raw["features"]:
        props = feature["properties"]
        name = props["name"]
        band = "HIGH" if name.startswith("HIGH") else "LOW"
        grouped[band]["geoms"].append(shape(feature["geometry"]))
        grouped[band]["names"].append(name)
        grouped[band]["capacities"].append(props["capacity"])

    bands: dict[str, dict] = {}
    for band, g in grouped.items():
        if g["geoms"]:
            bands[band] = {
                "tree": STRtree(g["geoms"]),
                "names": g["names"],
                "capacities": g["capacities"],
            }
    return bands


def _track_samples(flight: Flight, window_start, n_bins, sample_minutes, bin_minutes):
    duration_s = (flight.scheduled_landing_time - flight.take_off_time).total_seconds()
    if duration_s <= 0 or len(flight.lats) < 2:
        return
    cum, total = _cumulative(flight.lats, flight.lons)
    if total <= 0:
        return
    steps = max(1, int(duration_s / 60.0 / sample_minutes))
    for k in range(steps + 1):
        frac = k / steps
        when = flight.take_off_time + timedelta(seconds=frac * duration_s)
        bin_idx = int((when - window_start).total_seconds() / 60.0 / bin_minutes)
        if bin_idx < 0 or bin_idx >= n_bins:
            continue
        lat, lon = _point_at(flight.lats, flight.lons, cum, total, frac * total)
        yield lon, lat, bin_idx


def _cumulative(lats, lons) -> tuple[list[float], float]:
    cum = [0.0]
    for i in range(len(lats) - 1):
        cum.append(cum[-1] + haversine_nm(lats[i], lons[i], lats[i + 1], lons[i + 1]))
    return cum, cum[-1]


def _point_at(lats, lons, cum, total, target_nm) -> tuple[float, float]:
    if target_nm <= 0:
        return lats[0], lons[0]
    if target_nm >= total:
        return lats[-1], lons[-1]
    for i in range(len(cum) - 1):
        if cum[i + 1] >= target_nm:
            seg = cum[i + 1] - cum[i]
            f = (target_nm - cum[i]) / seg if seg > 0 else 0.0
            return (
                lats[i] + (lats[i + 1] - lats[i]) * f,
                lons[i] + (lons[i + 1] - lons[i]) * f,
            )
    return lats[-1], lons[-1]

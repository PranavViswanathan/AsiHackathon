"""Sector occupancy. Builds a time-parameterised track for each flight (constant
cruise: position interpolated by time between takeoff and landing), samples it on
a fixed cadence, and counts the distinct flights present in each sector during
each time bin. Capacity comes from `sectors.geojson`; a sector-time bin is
over-demand when its count exceeds capacity.

A point belongs to exactly one sector per altitude band (HIGH `>= 35000 ft`,
LOW below). Spatial lookup is vectorised through a shapely STRtree.

`compute_occupancy` is the reusable core (it also returns per-flight membership
and accepts altitude/takeoff overrides) so the optimizer can re-evaluate a
candidate scenario without duplicating the sampling logic."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
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

Key = tuple[str, int]  # (sector_name, time_bin)


def load_bands(sectors_path: Path | str) -> dict[str, dict]:
    raw = json.loads(Path(sectors_path).read_text())
    grouped: dict[str, dict[str, list]] = {
        "HIGH": {"geoms": [], "names": [], "capacities": []},
        "LOW": {"geoms": [], "names": [], "capacities": []},
    }
    for feature in raw["features"]:
        props = feature["properties"]
        band = "HIGH" if props["name"].startswith("HIGH") else "LOW"
        grouped[band]["geoms"].append(shape(feature["geometry"]))
        grouped[band]["names"].append(props["name"])
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


def capacity_map(bands: dict[str, dict]) -> dict[str, int]:
    caps: dict[str, int] = {}
    for data in bands.values():
        caps.update(zip(data["names"], data["capacities"]))
    return caps


def n_bins_for(scenario: Scenario, bin_minutes: int) -> int:
    total_minutes = (scenario.window_end - scenario.window_start).total_seconds() / 60.0
    return max(1, math.ceil(total_minutes / bin_minutes))


def compute_occupancy(
    flights,
    bands: dict[str, dict],
    window_start: datetime,
    n_bins: int,
    *,
    sample_minutes: int = DEFAULT_SAMPLE_MINUTES,
    bin_minutes: int = DEFAULT_BIN_MINUTES,
    altitudes=None,
    takeoffs=None,
) -> tuple[dict[Key, int], list[set[Key]]]:
    """Return (counts, memberships): distinct flights per (sector, bin) and the
    set of (sector, bin) each flight occupies. `altitudes`/`takeoffs` optionally
    override each flight's cruise altitude / departure time (aligned to `flights`)."""
    flights = list(flights)
    samples = {b: {"lon": [], "lat": [], "flight": [], "bin": []} for b in bands}
    for fi, flight in enumerate(flights):
        alt = altitudes[fi] if altitudes is not None else flight.cruise_altitude_ft
        band = "HIGH" if alt >= HIGH_FLOOR_FT else "LOW"
        if band not in bands:
            continue
        takeoff = takeoffs[fi] if takeoffs is not None else flight.take_off_time
        for lon, lat, bin_idx in _track_samples(
            flight, takeoff, window_start, n_bins, sample_minutes, bin_minutes
        ):
            s = samples[band]
            s["lon"].append(lon)
            s["lat"].append(lat)
            s["flight"].append(fi)
            s["bin"].append(bin_idx)

    occ_sets: dict[Key, set[int]] = {}
    memberships: list[set[Key]] = [set() for _ in flights]
    for band, data in bands.items():
        pts = samples[band]
        if not pts["lon"]:
            continue
        point_geoms = shp_points(np.column_stack([pts["lon"], pts["lat"]]))
        point_idx, poly_idx = data["tree"].query(point_geoms, predicate="within")
        names, flight_ids, bins = data["names"], pts["flight"], pts["bin"]
        for pi, gi in zip(point_idx, poly_idx):
            key = (names[gi], bins[pi])
            fi = flight_ids[pi]
            occ_sets.setdefault(key, set()).add(fi)
            memberships[fi].add(key)

    counts = {key: len(ids) for key, ids in occ_sets.items()}
    return counts, memberships


def overloaded_keys(counts: dict[Key, int], caps: dict[str, int]) -> dict[Key, int]:
    """Keys whose load exceeds capacity, mapped to their overload amount."""
    over: dict[Key, int] = {}
    for (name, bin_idx), load in counts.items():
        excess = load - caps.get(name, 0)
        if excess > 0:
            over[(name, bin_idx)] = excess
    return over


def aggregate_sectors(
    scenario: Scenario,
    sectors_path: Path | str,
    *,
    sample_minutes: int = DEFAULT_SAMPLE_MINUTES,
    bin_minutes: int = DEFAULT_BIN_MINUTES,
) -> dict:
    bands = load_bands(sectors_path)
    n_bins = n_bins_for(scenario, bin_minutes)
    counts, _ = compute_occupancy(
        scenario.flights, bands, scenario.window_start, n_bins,
        sample_minutes=sample_minutes, bin_minutes=bin_minutes,
    )
    return format_sectors(counts, bands, scenario.window_start, n_bins, bin_minutes)


def format_sectors(
    counts: dict[Key, int],
    bands: dict[str, dict],
    window_start: datetime,
    n_bins: int,
    bin_minutes: int,
) -> dict:
    caps = capacity_map(bands)
    band_of = {name: band for band, data in bands.items() for name in data["names"]}
    by_sector: dict[str, dict[int, int]] = {}
    for (name, bin_idx), load in counts.items():
        by_sector.setdefault(name, {})[bin_idx] = load

    sectors_out: dict[str, dict] = {}
    for name, by_bin in by_sector.items():
        peak = max(by_bin.values())
        capacity = caps.get(name, 0)
        sectors_out[name] = {
            "band": band_of.get(name, "LOW"),
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


def _track_samples(flight: Flight, takeoff: datetime, window_start, n_bins, sample_minutes, bin_minutes):
    duration_s = (flight.scheduled_landing_time - flight.take_off_time).total_seconds()
    if duration_s <= 0 or len(flight.lats) < 2:
        return
    cum, total = _cumulative(flight.lats, flight.lons)
    if total <= 0:
        return
    steps = max(1, int(duration_s / 60.0 / sample_minutes))
    for k in range(steps + 1):
        frac = k / steps
        when = takeoff + timedelta(seconds=frac * duration_s)
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

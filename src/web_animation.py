"""Generate the frontend's time-animation assets for a snapshot:

- ``weather/frame_NNN.png`` + ``weather.json`` — colorized composite-reflectivity
  radar frames the UI animates over a shared clock.
- ``flight_times.json`` — per-flight take-off / landing schedule so the UI can
  place each aircraft along its route at a given clock time.
- ``flight_weather_{baseline,recommended}.json`` — per-flight, per-frame bit
  flags marking when a flight is flying through dangerous convective weather
  (``refc >= 40 dBZ`` AND ``cruise_altitude_ft < retop_ft``; see
  ``src.data.weather``).

These are written alongside the lean static JSON produced by
``src.export_web`` and share its snapshot directory layout.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.data.weather import (
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    REFC_NODATA,
    WeatherGrid,
)

DEFAULT_BUNDLE = Path("data/hackathon_data_bundle")

# dBZ -> RGB color stops (NEXRAD-like); alpha is ramped separately so light
# precip fades in. Below MIN_DBZ a pixel is transparent.
MIN_DBZ = 5.0
_COLOR_STOPS = [
    (5.0, (0x40, 0xA0, 0xF0)),
    (15.0, (0x30, 0xC0, 0x50)),
    (25.0, (0x20, 0xA0, 0x30)),
    (32.0, (0xF0, 0xE0, 0x30)),
    (40.0, (0xF0, 0x90, 0x20)),
    (47.0, (0xF0, 0x30, 0x20)),
    (55.0, (0xC0, 0x20, 0x80)),
    (65.0, (0xFF, 0xFF, 0xFF)),
]


def _interp_color(dbz: float) -> tuple[int, int, int]:
    stops = _COLOR_STOPS
    if dbz <= stops[0][0]:
        return stops[0][1]
    if dbz >= stops[-1][0]:
        return stops[-1][1]
    for (lo_d, lo_c), (hi_d, hi_c) in zip(stops, stops[1:]):
        if dbz <= hi_d:
            t = (dbz - lo_d) / (hi_d - lo_d)
            return tuple(round(lo_c[k] + t * (hi_c[k] - lo_c[k])) for k in range(3))
    return stops[-1][1]


def _build_lut() -> np.ndarray:
    """256-entry RGBA lookup table indexed by clamped dBZ (index 0..255 -> 0..80 dBZ)."""
    lut = np.zeros((256, 4), dtype=np.uint8)
    for i in range(256):
        dbz = i / 255.0 * 80.0
        if dbz < MIN_DBZ:
            continue
        r, g, b = _interp_color(dbz)
        a = int(np.clip(60 + (dbz - MIN_DBZ) / (45.0 - MIN_DBZ) * 175, 60, 235))
        lut[i] = (r, g, b, a)
    return lut


def _strip_times(npz_name: str) -> tuple[str, str]:
    """{based}_{valid_from}_{valid_to}.npz -> (valid_from_iso, valid_to_iso) in UTC."""
    stem = npz_name[:-4] if npz_name.endswith(".npz") else npz_name
    p = stem.split("_")
    vf = datetime.strptime(f"{p[2]}T{p[3]}", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    vt = datetime.strptime(f"{p[4]}T{p[5]}", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return vf.isoformat(), vt.isoformat()


def export_weather_frames(snapshot: str, out_dir: Path, bundle_root: Path = DEFAULT_BUNDLE) -> int:
    """Write colorized radar PNGs + weather.json. Returns the frame count (0 if none)."""
    refc_dir = bundle_root / snapshot / "wx" / "refc"
    if not refc_dir.is_dir():
        return 0

    weather_dir = out_dir / "weather"
    weather_dir.mkdir(parents=True, exist_ok=True)
    lut = _build_lut()

    frames_meta: list[dict[str, Any]] = []
    for idx, npz_path in enumerate(sorted(refc_dir.glob("*.npz"))):
        m = np.load(npz_path)["matrix"].astype(np.float64)
        index = (np.clip(m, 0.0, 80.0) / 80.0 * 255.0).astype(np.uint8)
        index[m <= REFC_NODATA] = 0
        index[m < MIN_DBZ] = 0
        Image.fromarray(lut[index], mode="RGBA").save(weather_dir / f"frame_{idx:03d}.png", optimize=True)
        vf, vt = _strip_times(npz_path.name)
        frames_meta.append({"index": idx, "valid_from": vf, "valid_to": vt, "url": f"weather/frame_{idx:03d}.png"})

    manifest = {
        "snapshot": snapshot,
        "bounds": [LON_MIN, LAT_MIN, LON_MAX, LAT_MAX],  # [west, south, east, north]
        "extent": {"lat_min": LAT_MIN, "lat_max": LAT_MAX, "lon_min": LON_MIN, "lon_max": LON_MAX},
        "shape": [256, 358],
        "product": "refc",
        "units": "dBZ",
        "frames": frames_meta,
    }
    (out_dir / "weather.json").write_text(json.dumps(manifest))
    return len(frames_meta)


def _src_key(s: dict[str, Any]) -> str:
    return f"{s['flight_number']}_{s['take_off_time']}_{s['origin_airport_icao']}"


def export_flight_times(
    snapshot: str,
    web_flights: list[dict[str, Any]],
    out_dir: Path,
    bundle_root: Path = DEFAULT_BUNDLE,
) -> dict[str, list[str]]:
    """Join routes.json schedule onto the web flights by flight_key.

    Writes flight_times.json ({key: [takeoffISO, landingISO]}) and returns it.
    """
    routes_path = bundle_root / snapshot / "routes.json"
    if not routes_path.is_file():
        return {}
    src = json.loads(routes_path.read_text())["flights"]
    src_by_key = {_src_key(s): s for s in src}

    out: dict[str, list[str]] = {}
    for f in web_flights:
        s = src_by_key.get(f["flight_key"])
        if s is not None:
            out[f["flight_key"]] = [s["take_off_time"], s["scheduled_landing_time"]]

    (out_dir / "flight_times.json").write_text(json.dumps(out))
    return out


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def _cumulative(path: list[list[float]]) -> tuple[list[float], float]:
    cum = [0.0] * len(path)
    for k in range(1, len(path)):
        cum[k] = cum[k - 1] + _haversine(*path[k - 1], *path[k])
    return cum, (cum[-1] if cum else 0.0)


def _position_at(path, cum, total, frac):
    if total == 0:
        return path[0][0], path[0][1]
    target = max(0.0, min(1.0, frac)) * total
    k = 1
    while k < len(cum) - 1 and cum[k] < target:
        k += 1
    seg = cum[k] - cum[k - 1] or 1.0
    t = (target - cum[k - 1]) / seg
    a, b = path[k - 1], path[k]
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def export_flight_exposure(
    snapshot: str,
    web_flights: list[dict[str, Any]],
    flight_times: dict[str, list[str]],
    out_dir: Path,
    bundle_root: Path = DEFAULT_BUNDLE,
) -> dict[str, int]:
    """Per-flight, per-frame weather-exposure bit strings, for each scenario.

    Writes flight_weather_{baseline,recommended}.json and returns the count of
    flights that hit weather in each scenario.
    """
    grid = WeatherGrid(bundle_root / snapshot)
    if not grid:
        return {}
    frame_times = [s.midpoint for s in grid._strips]  # noqa: SLF001 — sorted by valid_from

    counts: dict[str, int] = {}
    for scenario in ("baseline", "recommended"):
        out: dict[str, str] = {}
        blocked = 0
        for f in web_flights:
            t = flight_times.get(f["flight_key"])
            path = f.get("path") or []
            if not t or len(path) < 2:
                continue
            if scenario == "recommended":
                altitude = f.get("opt_cruise_altitude_ft") or f["cruise_altitude_ft"]
                shift = (f.get("opt_departure_shift_min") or 0) * 60
            else:
                altitude = f["cruise_altitude_ft"]
                shift = 0
            takeoff = datetime.fromisoformat(t[0]).timestamp() + shift
            landing = datetime.fromisoformat(t[1]).timestamp() + shift
            span = (landing - takeoff) or 1.0
            cum, total = _cumulative(path)

            bits = []
            any_blocked = False
            for ft in frame_times:
                frac = (ft.timestamp() - takeoff) / span
                if frac < 0 or frac > 1:
                    bits.append("0")
                    continue
                lon, lat = _position_at(path, cum, total, frac)
                exposed = grid.exposure(lat, lon, altitude, ft).exposed
                bits.append("1" if exposed else "0")
                any_blocked = any_blocked or exposed
            if any_blocked:
                blocked += 1
            out[f["flight_key"]] = "".join(bits)

        (out_dir / f"flight_weather_{scenario}.json").write_text(json.dumps(out))
        counts[scenario] = blocked
    return counts


def export_animation(
    snapshot: str,
    web_flights: list[dict[str, Any]],
    out_dir: Path,
    bundle_root: Path | str = DEFAULT_BUNDLE,
) -> dict[str, Any]:
    """Generate all time-animation assets for a snapshot. No-op-safe when the
    weather bundle is absent (e.g. snapshots without wx data)."""
    bundle_root = Path(bundle_root)
    n_frames = export_weather_frames(snapshot, out_dir, bundle_root)
    times = export_flight_times(snapshot, web_flights, out_dir, bundle_root)
    exposure = (
        export_flight_exposure(snapshot, web_flights, times, out_dir, bundle_root)
        if n_frames and times
        else {}
    )
    return {"weather_frames": n_frames, "flight_times": len(times), "blocked": exposure}

"""Raw data-bundle access for the API: sector polygons (`sectors.geojson`) and
the weather strips (`wx/refc|retop/*.npz`). These read straight from the bundle
and do not depend on the precompute pipeline, so the weather/sector endpoints
work before any artifacts are built.

Grid geometry follows `docs/DATA.md`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.config import Settings, get_settings

LAT_MAX, LAT_MIN = 55.7765, 21.943
LON_MIN, LON_MAX = -135.0, -67.5
ROWS, COLS = 256, 358

REFC_NODATA = -50.0  # refc <= -50 is nodata; dangerous when >= 40 dBZ
RETOP_NODATA = 0.0   # retop < 0 is nodata


@dataclass(frozen=True)
class WeatherStrip:
    valid_from: datetime
    valid_to: datetime
    refc_path: Path
    retop_path: Path

    @property
    def midpoint(self) -> datetime:
        return self.valid_from + (self.valid_to - self.valid_from) / 2


def _parse_strip_time(date_token: str, time_token: str) -> datetime:
    return datetime.fromisoformat(f"{date_token}T{time_token}+00:00")


def _strip_bounds(npz_name: str) -> tuple[datetime, datetime]:
    # e.g. 2025-05-29_21:00:00_2025-05-29_20:52:30_2025-05-29_21:07:30.npz
    parts = npz_name.removesuffix(".npz").split("_")
    valid_from = _parse_strip_time(parts[2], parts[3])
    valid_to = _parse_strip_time(parts[4], parts[5])
    return valid_from, valid_to


class BundleReader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sectors: list[dict] | None = None
        self._strips: list[WeatherStrip] | None = None

    # -- sectors ---------------------------------------------------------
    def sectors(self) -> list[dict]:
        if self._sectors is None:
            raw = json.loads(self._settings.sectors_path.read_text())
            self._sectors = [
                {
                    "name": f["properties"]["name"],
                    "altitude_from_ft": f["properties"]["altitude_from_ft"],
                    "altitude_to_ft": f["properties"]["altitude_to_ft"],
                    "capacity": f["properties"]["capacity"],
                    "geometry": f["geometry"],
                }
                for f in raw["features"]
            ]
        return self._sectors

    # -- weather ---------------------------------------------------------
    def strips(self) -> list[WeatherStrip]:
        if self._strips is None:
            refc_dir = self._settings.scenario_dir / "wx" / "refc"
            retop_dir = self._settings.scenario_dir / "wx" / "retop"
            strips: list[WeatherStrip] = []
            for refc_path in sorted(refc_dir.glob("*.npz")):
                valid_from, valid_to = _strip_bounds(refc_path.name)
                strips.append(
                    WeatherStrip(
                        valid_from=valid_from,
                        valid_to=valid_to,
                        refc_path=refc_path,
                        retop_path=retop_dir / refc_path.name,
                    )
                )
            self._strips = sorted(strips, key=lambda s: s.valid_from)
        return self._strips

    def select_strip(self, t: datetime) -> WeatherStrip:
        strips = self.strips()
        if not strips:
            raise FileNotFoundError("no weather strips found for scenario")
        for strip in strips:
            if strip.valid_from <= t < strip.valid_to:
                return strip
        return min(strips, key=lambda s: abs((s.midpoint - t).total_seconds()))

    def load_grids(self, strip: WeatherStrip, *, step: int = 1) -> dict:
        refc = np.load(strip.refc_path)["matrix"][::step, ::step]
        retop = np.load(strip.retop_path)["matrix"][::step, ::step]
        return {
            "valid_from": strip.valid_from.isoformat(),
            "valid_to": strip.valid_to.isoformat(),
            "extent": {"lat_max": LAT_MAX, "lat_min": LAT_MIN, "lon_min": LON_MIN, "lon_max": LON_MAX},
            "shape": list(refc.shape),
            "step": step,
            "refc": _to_grid(refc, nodata_at_or_below=REFC_NODATA, decimals=1),
            "retop": _to_grid(retop, nodata_below=RETOP_NODATA, decimals=0),
        }


def _to_grid(matrix, *, nodata_at_or_below=None, nodata_below=None, decimals=1) -> list[list[float | None]]:
    """Round a grid and replace nodata sentinels with null for compact JSON."""
    rounded = np.round(matrix, decimals)
    out: list[list[float | None]] = []
    for row in rounded:
        out_row: list[float | None] = []
        for value in row:
            if nodata_at_or_below is not None and value <= nodata_at_or_below:
                out_row.append(None)
            elif nodata_below is not None and value < nodata_below:
                out_row.append(None)
            else:
                out_row.append(int(value) if decimals == 0 else float(value))
        out.append(out_row)
    return out


@lru_cache
def get_bundle() -> BundleReader:
    return BundleReader(get_settings())

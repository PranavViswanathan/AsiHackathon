"""Storm-impact sampling along a route. Wraps the per-scenario stack of weather
strips (`wx/refc|retop/*.npz`) and answers, for a (lat, lon, altitude, time)
sample, whether a flight is exposed to convective weather.

A flight is exposed when the composite reflectivity is dangerous **and** it does
not overfly the storm top:

    refc >= 40 dBZ   AND   cruise_altitude_ft < retop_ft

Grid geometry and nodata rules follow `docs/DATA.md`."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

LAT_MAX, LAT_MIN = 55.7765, 21.943
LON_MIN, LON_MAX = -135.0, -67.5
ROWS, COLS = 256, 358

REFC_DANGER_DBZ = 40.0
REFC_NODATA = -50.0  # refc <= -50 is nodata
RETOP_NODATA = 0.0   # retop < 0 is nodata


@dataclass(frozen=True)
class _Strip:
    valid_from: datetime
    valid_to: datetime
    refc_path: Path
    retop_path: Path

    @property
    def midpoint(self) -> datetime:
        return self.valid_from + (self.valid_to - self.valid_from) / 2


def _parse_time(date_token: str, time_token: str) -> datetime:
    return datetime.fromisoformat(f"{date_token}T{time_token}+00:00")


def _strip_bounds(name: str) -> tuple[datetime, datetime]:
    # 2025-05-29_21:00:00_2025-05-29_20:52:30_2025-05-29_21:07:30.npz
    parts = name.removesuffix(".npz").split("_")
    return _parse_time(parts[2], parts[3]), _parse_time(parts[4], parts[5])


def latlon_to_ij(lat: float, lon: float) -> tuple[int, int] | None:
    """Nearest grid cell for a (lat, lon), or None if outside the CONUS grid."""
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None
    i = int(round((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * ROWS))
    j = int(round((lon - LON_MIN) / (LON_MAX - LON_MIN) * COLS))
    return min(max(i, 0), ROWS - 1), min(max(j, 0), COLS - 1)


@dataclass(frozen=True)
class Exposure:
    exposed: bool
    refc_dbz: float
    retop_ft: float


class WeatherGrid:
    def __init__(self, scenario_dir: Path | str) -> None:
        scenario_dir = Path(scenario_dir)
        refc_dir = scenario_dir / "wx" / "refc"
        retop_dir = scenario_dir / "wx" / "retop"
        strips: list[_Strip] = []
        if refc_dir.is_dir():
            for refc_path in sorted(refc_dir.glob("*.npz")):
                valid_from, valid_to = _strip_bounds(refc_path.name)
                strips.append(
                    _Strip(valid_from, valid_to, refc_path, retop_dir / refc_path.name)
                )
        self._strips = sorted(strips, key=lambda s: s.valid_from)
        self._starts = [s.valid_from for s in self._strips]
        self._cache: dict[Path, np.ndarray] = {}

    def __bool__(self) -> bool:
        return bool(self._strips)

    def _matrix(self, path: Path) -> np.ndarray:
        if path not in self._cache:
            self._cache[path] = np.load(path)["matrix"]
        return self._cache[path]

    def _select(self, when: datetime) -> _Strip | None:
        if not self._strips:
            return None
        idx = bisect.bisect_right(self._starts, when) - 1
        if 0 <= idx < len(self._strips) and self._strips[idx].valid_to > when:
            return self._strips[idx]
        # outside any [from, to): fall back to the nearest strip by midpoint
        return min(self._strips, key=lambda s: abs((s.midpoint - when).total_seconds()))

    def sample(self, lat: float, lon: float, when: datetime) -> tuple[float | None, float | None]:
        cell = latlon_to_ij(lat, lon)
        strip = self._select(when)
        if cell is None or strip is None:
            return None, None
        refc_grid = self._matrix(strip.refc_path)
        # The geographic formula targets the canonical 256x358 grid; clamp to the
        # actual matrix shape so smaller (e.g. test) grids never index out of range.
        i = min(cell[0], refc_grid.shape[0] - 1)
        j = min(cell[1], refc_grid.shape[1] - 1)
        refc = float(refc_grid[i, j])
        retop = float(self._matrix(strip.retop_path)[i, j])
        return (
            refc if refc > REFC_NODATA else None,
            retop if retop >= RETOP_NODATA else None,
        )

    def exposure(self, lat: float, lon: float, altitude_ft: float, when: datetime) -> Exposure:
        refc, retop = self.sample(lat, lon, when)
        exposed = (
            refc is not None
            and retop is not None
            and refc >= REFC_DANGER_DBZ
            and altitude_ft < retop
        )
        return Exposure(exposed=exposed, refc_dbz=refc or 0.0, retop_ft=retop or 0.0)

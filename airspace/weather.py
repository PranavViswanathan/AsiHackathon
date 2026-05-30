"""Weather: composite reflectivity (refc) and echo top (retop), and where it
blocks a flight.

Each scenario ships a single HRRR forecast as 15-minute strips covering ~18h
forward. We load those strips, sample them at flight positions, and apply the
bundle's blocking rule:

    a point is weather-blocked  <=>  refc >= 40 dBZ  AND  flight_altitude_ft <= retop

`refc` is the top-down precipitation intensity; `retop` is how high the storm
column reaches. A flight cruising above the echo top, or through light
precipitation, is unaffected.

Grid: a regular equirectangular lat/lon grid, shape (256, 358), row 0 = north,
col 0 = west. nodata sentinels: refc <= -50, retop < 0.
"""

from __future__ import annotations

import glob
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .data import DATA_ROOT, Scenario

# --- grid geometry (from documentation/wx/FILE_FORMAT.md) --------------------
LAT_MIN, LAT_MAX = 21.943, 55.7765
LON_MIN, LON_MAX = -135.0, -67.5
ROWS, COLS = 256, 358

REFC_BLOCK_DBZ = 40.0      # at/above this reflectivity counts as significant weather
REFC_NODATA = -50.0        # refc <= this is nodata
RETOP_NODATA = 0.0         # retop < this is nodata


def latlon_to_rowcol(lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised inverse of the grid's pixel mapping.

    Returns integer (row, col) arrays clipped to the grid. Points outside the
    bounding box are clamped to the edge; callers that care should pre-filter, but
    out-of-footprint cells carry nodata anyway so blocking stays False there.
    """
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    rows = ((LAT_MAX - lats) / (LAT_MAX - LAT_MIN) * ROWS).astype(int)
    cols = ((lons - LON_MIN) / (LON_MAX - LON_MIN) * COLS).astype(int)
    rows = np.clip(rows, 0, ROWS - 1)
    cols = np.clip(cols, 0, COLS - 1)
    return rows, cols


def _parse_ts(s: str) -> datetime:
    # filenames use "YYYY-MM-DD_HH:MM:SS" in UTC
    return datetime.strptime(s, "%Y-%m-%d_%H:%M:%S").replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Strip:
    """One 15-minute forecast strip for a single variable."""

    based_at: datetime
    valid_from: datetime
    valid_to: datetime
    path: Path

    def load(self) -> np.ndarray:
        """The (256, 358) matrix. Loaded lazily so a forecast is cheap to construct."""
        return np.load(self.path)["matrix"]

    @property
    def mid(self) -> datetime:
        return self.valid_from + (self.valid_to - self.valid_from) / 2


def _discover_strips(var_dir: Path) -> list[Strip]:
    strips: list[Strip] = []
    for p in sorted(var_dir.glob("*.npz")):
        # "<based_date>_<based_time>_<from_date>_<from_time>_<to_date>_<to_time>.npz"
        a, b, c, d, e, f = p.stem.split("_")
        strips.append(
            Strip(
                based_at=_parse_ts(f"{a}_{b}"),
                valid_from=_parse_ts(f"{c}_{d}"),
                valid_to=_parse_ts(f"{e}_{f}"),
                path=p,
            )
        )
    strips.sort(key=lambda s: s.valid_from)
    return strips


class WeatherForecast:
    """The refc + retop strips for one scenario, queryable by time and position.

    >>> wx = WeatherForecast.load("2025-07-08T22:00:00Z")
    >>> refc, retop = wx.sample(lats, lons, t)          # values at positions
    >>> mask = wx.blocked(lats, lons, alt_ft, t)        # bool: weather-blocked?
    """

    def __init__(self, refc: list[Strip], retop: list[Strip]):
        self.refc = refc
        self.retop = retop
        self._refc_starts = [s.valid_from for s in refc]
        self._retop_starts = [s.valid_from for s in retop]
        self._cache: dict[tuple[str, Path], np.ndarray] = {}

    @classmethod
    def load(cls, scenario_id: str, root: Path | str | None = None) -> "WeatherForecast":
        root = Path(root) if root is not None else DATA_ROOT
        scenario_id = scenario_id.removeprefix("asked_at_")
        wx = root / f"asked_at_{scenario_id}" / "wx"
        refc = _discover_strips(wx / "refc")
        retop = _discover_strips(wx / "retop")
        if not refc or not retop:
            raise FileNotFoundError(f"no weather strips under {wx} (this scenario may not ship wx data)")
        return cls(refc, retop)

    @property
    def covered(self) -> tuple[datetime, datetime]:
        """The [start, end) the forecast strips actually cover."""
        return self.refc[0].valid_from, self.refc[-1].valid_to

    def _select(self, strips: list[Strip], starts: list[datetime], t: datetime) -> Strip:
        """The strip whose [valid_from, valid_to) contains ``t``; nearest if outside."""
        i = bisect_right(starts, t) - 1
        if i < 0:
            return strips[0]
        s = strips[i]
        if t < s.valid_to or i == len(strips) - 1:
            return s
        return strips[i + 1]

    def _matrix(self, strip: Strip, var: str) -> np.ndarray:
        key = (var, strip.path)
        if key not in self._cache:
            self._cache[key] = strip.load()
        return self._cache[key]

    def grids_at(self, t: datetime) -> tuple[np.ndarray, np.ndarray]:
        """The (refc, retop) full matrices for the strip covering time ``t``."""
        refc = self._matrix(self._select(self.refc, self._refc_starts, t), "refc")
        retop = self._matrix(self._select(self.retop, self._retop_starts, t), "retop")
        return refc, retop

    def sample(self, lats: np.ndarray, lons: np.ndarray, t: datetime):
        """refc (dBZ) and retop (ft) at each position at time ``t``.

        nodata cells are returned as NaN so they don't masquerade as real values.
        """
        rows, cols = latlon_to_rowcol(lats, lons)
        refc_m, retop_m = self.grids_at(t)
        refc = refc_m[rows, cols].astype(float)
        retop = retop_m[rows, cols].astype(float)
        refc = np.where(refc <= REFC_NODATA, np.nan, refc)
        retop = np.where(retop < RETOP_NODATA, np.nan, retop)
        return refc, retop

    def blocked(self, lats: np.ndarray, lons: np.ndarray, alt_ft, t: datetime) -> np.ndarray:
        """Boolean mask: is each position weather-blocked at altitude ``alt_ft``?

        ``alt_ft`` may be a scalar or an array parallel to ``lats``/``lons``.
        Blocked  <=>  refc >= 40 dBZ  AND  alt_ft <= retop. nodata never blocks.
        """
        rows, cols = latlon_to_rowcol(lats, lons)
        refc_m, retop_m = self.grids_at(t)
        refc = refc_m[rows, cols]
        retop = retop_m[rows, cols]
        alt = np.asarray(alt_ft, dtype=float)
        # nodata sentinels fail these comparisons naturally (refc<=-50 < 40; retop<0 < alt)
        return (refc >= REFC_BLOCK_DBZ) & (alt <= retop)


def blocked_flights(scenario: Scenario, forecast: WeatherForecast, t: datetime):
    """Active flights at ``t`` and a mask of which are flying through weather.

    Returns ``(flights, lats, lons, blocked_mask)`` — parallel arrays, where each
    flight is checked at its own cruise altitude and position.
    """
    from .geometry import positions_at

    flights, lats, lons = positions_at(scenario.flights, t, only_active=True)
    if not flights:
        return flights, lats, lons, np.zeros(0, dtype=bool)
    alts = np.array([f.cruise_altitude_ft for f in flights], dtype=float)
    mask = forecast.blocked(lats, lons, alts, t)
    return flights, lats, lons, mask

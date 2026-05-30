"""Wind integration via Open-Meteo pressure-level winds.

A coarse CONUS wind field is fetched **once per snapshot** and cached to disk
(`wind_cache.npz`) so the demo runs offline after the first fetch. The fuel model
samples the cached field along each route (bilinear in space, nearest hour in
time, pressure level nearest the cruise altitude) to turn wind into ground speed.

Network access is best-effort: `load_or_fetch_wind` returns `None` on any failure
so the pipeline cleanly degrades to a zero-wind estimate.

Open-Meteo reports wind **direction as the bearing the wind comes from**, so the
wind vector points the opposite way; `met_wind_to_uv` does that conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OPEN_METEO_HOST = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# Pressure level -> representative pressure altitude (ft). Pick nearest to cruise.
LEVEL_ALTITUDE_FT = {200: 38661, 250: 33999, 300: 30065}


def met_wind_to_uv(speed: float, direction_deg: float) -> tuple[float, float]:
    """(speed, met-direction) -> (east, north) components of the wind vector.

    Meteorological direction is where the wind blows *from*, so the vector the air
    actually moves along points toward `direction + 180`."""
    rad = math.radians(direction_deg)
    return -speed * math.sin(rad), -speed * math.cos(rad)


def along_track_kt(u_east: float, v_north: float, bearing_deg: float) -> float:
    """Project a wind vector onto a track bearing. Positive = tailwind."""
    rad = math.radians(bearing_deg)
    return u_east * math.sin(rad) + v_north * math.cos(rad)


def _nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(values - target)))


@dataclass
class WindField:
    """A gridded, time-resolved wind field in knots.

    `u`/`v` per level are arrays shaped `(n_times, n_lat, n_lon)`; `lats`/`lons`
    are 1-D ascending grids and `times` is a list of tz-aware datetimes."""

    lats: np.ndarray
    lons: np.ndarray
    times: list[datetime]
    u: dict[int, np.ndarray]
    v: dict[int, np.ndarray]

    def _level_for(self, altitude_ft: float) -> int:
        return min(self.u, key=lambda hpa: abs(LEVEL_ALTITUDE_FT[hpa] - altitude_ft))

    def _time_index(self, when: datetime) -> int:
        epochs = np.array([t.timestamp() for t in self.times])
        return _nearest_index(epochs, when.timestamp())

    def sample_uv(self, lat: float, lon: float, when: datetime, altitude_ft: float) -> tuple[float, float]:
        level = self._level_for(altitude_ft)
        ti = self._time_index(when)
        u_grid, v_grid = self.u[level][ti], self.v[level][ti]
        return _bilinear(self.lats, self.lons, u_grid, lat, lon), _bilinear(
            self.lats, self.lons, v_grid, lat, lon
        )

    def along_track_kt(self, lat: float, lon: float, when: datetime, altitude_ft: float, bearing_deg: float) -> float:
        u, v = self.sample_uv(lat, lon, when, altitude_ft)
        return along_track_kt(u, v, bearing_deg)

    # -- persistence -----------------------------------------------------
    def save(self, path: Path | str) -> None:
        path = Path(path)
        levels = sorted(self.u)
        arrays = {
            "lats": self.lats,
            "lons": self.lons,
            "times": np.array([t.isoformat() for t in self.times]),
            "levels": np.array(levels),
        }
        for hpa in levels:
            arrays[f"u_{hpa}"] = self.u[hpa]
            arrays[f"v_{hpa}"] = self.v[hpa]
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **arrays)

    @classmethod
    def load(cls, path: Path | str) -> "WindField":
        data = np.load(path, allow_pickle=False)
        levels = [int(x) for x in data["levels"]]
        times = [datetime.fromisoformat(str(t)) for t in data["times"]]
        return cls(
            lats=data["lats"],
            lons=data["lons"],
            times=times,
            u={hpa: data[f"u_{hpa}"] for hpa in levels},
            v={hpa: data[f"v_{hpa}"] for hpa in levels},
        )


def _bilinear(lats: np.ndarray, lons: np.ndarray, grid: np.ndarray, lat: float, lon: float) -> float:
    """Bilinear interpolation on an ascending lat/lon grid, edge-clamped."""
    lat = min(max(lat, lats[0]), lats[-1])
    lon = min(max(lon, lons[0]), lons[-1])
    i = int(np.clip(np.searchsorted(lats, lat) - 1, 0, len(lats) - 2))
    j = int(np.clip(np.searchsorted(lons, lon) - 1, 0, len(lons) - 2))
    dlat = (lat - lats[i]) / (lats[i + 1] - lats[i]) if lats[i + 1] != lats[i] else 0.0
    dlon = (lon - lons[j]) / (lons[j + 1] - lons[j]) if lons[j + 1] != lons[j] else 0.0
    top = grid[i, j] * (1 - dlon) + grid[i, j + 1] * dlon
    bot = grid[i + 1, j] * (1 - dlon) + grid[i + 1, j + 1] * dlon
    return float(top * (1 - dlat) + bot * dlat)


# -- Open-Meteo fetch (best-effort) --------------------------------------

def _grid_axis(lo: float, hi: float, step: float) -> np.ndarray:
    n = max(int(round((hi - lo) / step)) + 1, 2)
    return np.linspace(lo, hi, n)


def parse_location_response(payload: dict, levels: tuple[int, ...]) -> tuple[list[datetime], dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Turn one Open-Meteo location's hourly block into (times, u, v) per level."""
    hourly = payload["hourly"]
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
    u: dict[int, np.ndarray] = {}
    v: dict[int, np.ndarray] = {}
    for hpa in levels:
        speed = np.asarray(hourly[f"wind_speed_{hpa}hPa"], dtype=float)
        direction = np.asarray(hourly[f"wind_direction_{hpa}hPa"], dtype=float)
        rad = np.radians(direction)
        u[hpa] = -speed * np.sin(rad)
        v[hpa] = -speed * np.cos(rad)
    return times, u, v


def fetch_wind_field(
    window_start: datetime,
    window_end: datetime,
    *,
    levels: tuple[int, ...] = (200, 250),
    grid_step: float = 2.0,
    chunk: int = 100,
    timeout: float = 30.0,
) -> WindField:
    """Fetch a coarse CONUS wind field from Open-Meteo. Raises on network error."""
    import requests  # local import so the module loads without the dep

    lats = _grid_axis(22.0, 55.0, grid_step)
    lons = _grid_axis(-134.0, -68.0, grid_step)
    points = [(i, j, float(la), float(lo)) for i, la in enumerate(lats) for j, lo in enumerate(lons)]

    hourly_vars = ",".join(
        f"wind_speed_{hpa}hPa,wind_direction_{hpa}hPa" for hpa in levels
    )
    times: list[datetime] | None = None
    n_t = 0
    u = {hpa: None for hpa in levels}
    v = {hpa: None for hpa in levels}

    for start in range(0, len(points), chunk):
        block = points[start : start + chunk]
        params = {
            "latitude": ",".join(f"{p[2]:.4f}" for p in block),
            "longitude": ",".join(f"{p[3]:.4f}" for p in block),
            "hourly": hourly_vars,
            "wind_speed_unit": "kn",
            "timezone": "GMT",
            "start_date": window_start.date().isoformat(),
            "end_date": window_end.date().isoformat(),
        }
        resp = requests.get(OPEN_METEO_HOST, params=params, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        locations = body if isinstance(body, list) else [body]
        for (i, j, _, _), loc in zip(block, locations):
            t, lu, lv = parse_location_response(loc, levels)
            if times is None:
                times, n_t = t, len(t)
                for hpa in levels:
                    u[hpa] = np.full((n_t, len(lats), len(lons)), np.nan)
                    v[hpa] = np.full((n_t, len(lats), len(lons)), np.nan)
            for hpa in levels:
                u[hpa][:, i, j] = lu[hpa][:n_t]
                v[hpa][:, i, j] = lv[hpa][:n_t]

    if times is None:
        raise RuntimeError("Open-Meteo returned no locations")
    # fill any gaps so bilinear never hits NaN
    for hpa in levels:
        u[hpa] = np.nan_to_num(u[hpa])
        v[hpa] = np.nan_to_num(v[hpa])
    return WindField(lats=lats, lons=lons, times=times, u=u, v=v)


def load_or_fetch_wind(
    window_start: datetime,
    window_end: datetime,
    cache_path: Path | str,
    **fetch_kwargs,
) -> WindField | None:
    """Load the cached wind field, else fetch + cache it. Returns None on failure."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        try:
            return WindField.load(cache_path)
        except Exception:  # noqa: BLE001 - corrupt cache should not kill the build
            pass
    try:
        field = fetch_wind_field(window_start, window_end, **fetch_kwargs)
        field.save(cache_path)
        return field
    except Exception:  # noqa: BLE001 - degrade to zero-wind
        return None

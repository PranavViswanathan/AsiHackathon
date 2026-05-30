"""Loading the hackathon data bundle: flight routes and airspace sectors.

The bundle ships as `routes.json.gz` / `sectors.geojson.gz` per the docs, but the
files may already be decompressed on disk. Both loaders transparently handle the
plain-JSON and gzipped forms, so you don't have to care which you have.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path

import numpy as np

# Default location of the data bundle. Override with the AIRSPACE_DATA env var,
# or pass an explicit path to the loaders.
DATA_ROOT = Path(os.environ.get("AIRSPACE_DATA", Path(__file__).resolve().parent.parent / "data"))


def _read_json(path: Path) -> dict:
    """Read JSON whether the file is plain or gzipped (tries both forms)."""
    candidates = [path]
    if path.suffix == ".gz":
        candidates.append(path.with_suffix(""))          # routes.json.gz -> routes.json
    else:
        candidates.append(path.with_suffix(path.suffix + ".gz"))  # and vice versa

    for p in candidates:
        if not p.exists():
            continue
        # gzip files start with the magic bytes 0x1f 0x8b; sniff rather than trust the name.
        with open(p, "rb") as fh:
            magic = fh.read(2)
        opener = gzip.open if magic == b"\x1f\x8b" else open
        with opener(p, "rt") as fh:
            return json.load(fh)
    raise FileNotFoundError(f"none of {[str(c) for c in candidates]} exist")


@dataclass(frozen=True)
class Flight:
    """One planned flight from a snapshot.

    Position over time is reconstructed under the bundle's modelling assumption:
    constant cruise altitude and speed, no climb/descent. ``take_off_time`` places
    the aircraft at the first waypoint and ``scheduled_landing_time`` at the last.
    """

    flight_number: str
    take_off_time: datetime
    scheduled_landing_time: datetime
    origin_airport_icao: str
    destination_airport_icao: str
    cruise_altitude_ft: int
    cruise_speed_kt: float
    lats: np.ndarray   # shape (n_waypoints,)
    lons: np.ndarray   # shape (n_waypoints,)
    is_airborne: bool

    @property
    def key(self) -> tuple[str, datetime, str]:
        """Unique identity: (flight_number, take_off_time, origin)."""
        return (self.flight_number, self.take_off_time, self.origin_airport_icao)

    @property
    def band(self) -> str:
        """Altitude band this flight cruises in: 'HIGH' (>=35k ft) or 'LOW'."""
        return "HIGH" if self.cruise_altitude_ft >= 35_000 else "LOW"

    @cached_property
    def _cumulative_fraction(self) -> np.ndarray:
        """Distance-along-path of each waypoint, normalised to [0, 1].

        Uses planar (equirectangular) segment lengths, which is plenty accurate for
        positioning a flight between fixes at CONUS scale.
        """
        lat = self.lats
        lon = self.lons
        latr = np.radians(lat)
        # scale longitude degrees by cos(lat) so a degree of lon ~ a degree of lat in distance
        dx = np.diff(lon) * np.cos(np.radians((lat[:-1] + lat[1:]) / 2))
        dy = np.diff(lat)
        seg = np.hypot(dx, dy)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        total = cum[-1]
        if total == 0:
            return np.zeros_like(cum)
        return cum / total


@dataclass
class Scenario:
    """A single snapshot: all flights with a scheduled departure in the window."""

    asked_at: datetime
    window_start: datetime
    window_end: datetime
    flights: list[Flight]

    def __len__(self) -> int:
        return len(self.flights)


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def list_scenarios(root: Path | str | None = None) -> list[str]:
    """Return the available scenario ids (the `asked_at_<...>Z` directory suffixes)."""
    root = Path(root) if root is not None else DATA_ROOT
    return sorted(
        p.name.removeprefix("asked_at_")
        for p in root.glob("asked_at_*")
        if p.is_dir()
    )


def load_scenario(scenario_id: str, root: Path | str | None = None) -> Scenario:
    """Load one snapshot by id, e.g. ``"2025-07-08T22:00:00Z"``.

    Accepts the bare timestamp or the full ``asked_at_<...>`` directory name.
    """
    root = Path(root) if root is not None else DATA_ROOT
    scenario_id = scenario_id.removeprefix("asked_at_")
    scenario_dir = root / f"asked_at_{scenario_id}"
    raw = _read_json(scenario_dir / "routes.json.gz")

    flights = []
    for f in raw["flights"]:
        flights.append(
            Flight(
                flight_number=f["flight_number"],
                take_off_time=_parse_ts(f["take_off_time"]),
                scheduled_landing_time=_parse_ts(f["scheduled_landing_time"]),
                origin_airport_icao=f["origin_airport_icao"],
                destination_airport_icao=f["destination_airport_icao"],
                cruise_altitude_ft=int(f["cruise_altitude_ft"]),
                cruise_speed_kt=float(f["cruise_speed_kt"]),
                lats=np.asarray(f["lats"], dtype=float),
                lons=np.asarray(f["lons"], dtype=float),
                is_airborne=bool(f["is_airborne"]),
            )
        )

    return Scenario(
        asked_at=_parse_ts(raw["asked_at"]),
        window_start=_parse_ts(raw["window_start"]),
        window_end=_parse_ts(raw["window_end"]),
        flights=flights,
    )


def load_sectors(root: Path | str | None = None) -> dict:
    """Load the shared `sectors.geojson` FeatureCollection (gzipped or plain)."""
    root = Path(root) if root is not None else DATA_ROOT
    return _read_json(root / "sectors.geojson.gz")

"""Parse a scenario's routes file into typed, immutable flight records."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_ROUTE_FILENAMES = ("routes.json", "routes.json.gz")


@dataclass(frozen=True)
class Flight:
    flight_number: str
    take_off_time: datetime
    scheduled_landing_time: datetime
    origin_airport_icao: str
    destination_airport_icao: str
    cruise_altitude_ft: float
    cruise_speed_kt: float
    lats: tuple[float, ...]
    lons: tuple[float, ...]
    is_airborne: bool

    @property
    def id(self) -> str:
        return f"{self.flight_number}_{self.take_off_time.isoformat()}_{self.origin_airport_icao}"


@dataclass(frozen=True)
class Scenario:
    asked_at: datetime
    window_start: datetime
    window_end: datetime
    flights: tuple[Flight, ...]


def load_scenario(scenario_dir: Path | str) -> Scenario:
    raw = _read_json(_route_file(Path(scenario_dir)))
    return Scenario(
        asked_at=_parse_dt(raw["asked_at"]),
        window_start=_parse_dt(raw["window_start"]),
        window_end=_parse_dt(raw["window_end"]),
        flights=tuple(_parse_flight(f) for f in raw["flights"]),
    )


def _route_file(scenario_dir: Path) -> Path:
    for name in _ROUTE_FILENAMES:
        candidate = scenario_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no routes file found in {scenario_dir}")


def _read_json(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_flight(record: dict[str, Any]) -> Flight:
    return Flight(
        flight_number=record["flight_number"],
        take_off_time=_parse_dt(record["take_off_time"]),
        scheduled_landing_time=_parse_dt(record["scheduled_landing_time"]),
        origin_airport_icao=record["origin_airport_icao"],
        destination_airport_icao=record["destination_airport_icao"],
        cruise_altitude_ft=float(record["cruise_altitude_ft"]),
        cruise_speed_kt=float(record["cruise_speed_kt"]),
        lats=tuple(float(x) for x in record["lats"]),
        lons=tuple(float(x) for x in record["lons"]),
        is_airborne=bool(record["is_airborne"]),
    )

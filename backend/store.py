"""Artifact store: serves the precomputed per-snapshot JSON artifacts that
`src.build` writes (`flights.json`, `summary.json`, `h3.json`). Builds them on
first access if they are missing, and caches them in memory."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.config import Settings, get_settings
from src.build import build_snapshot


class ArtifactStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, object] = {}

    @property
    def scenario_dir(self) -> Path:
        return self._settings.scenario_dir

    @property
    def artifact_dir(self) -> Path:
        return self._settings.artifact_root / self._settings.scenario_name

    def ensure_built(self, *, force: bool = False) -> dict:
        """Build the artifacts if missing (or forced); return the summary."""
        flights_json = self.artifact_dir / "flights.json"
        if force or not flights_json.exists():
            if not self.scenario_dir.exists():
                raise FileNotFoundError(f"scenario not found: {self.scenario_dir}")
            summary = build_snapshot(self.scenario_dir, out_root=self._settings.artifact_root)
            self._cache.clear()
            return summary
        return self.summary()

    def _load(self, name: str) -> object:
        if name not in self._cache:
            self.ensure_built()
            self._cache[name] = json.loads((self.artifact_dir / name).read_text())
        return self._cache[name]

    def flights(self) -> list[dict]:
        return self._load("flights.json")  # type: ignore[return-value]

    def summary(self) -> dict:
        return json.loads((self.artifact_dir / "summary.json").read_text())

    def h3(self) -> list[dict]:
        return self._load("h3.json")  # type: ignore[return-value]

    def sector_occupancy(self) -> dict:
        return self._load("sectors.json")  # type: ignore[return-value]

    def recommendations(self) -> list[dict]:
        return self._load("recommendations.json")  # type: ignore[return-value]

    def flight(self, flight_id: str) -> dict | None:
        return next((f for f in self.flights() if f["id"] == flight_id), None)


@lru_cache
def get_store() -> ArtifactStore:
    return ArtifactStore(get_settings())

"""Backend settings: resolve the active scenario, the artifact cache, and the
data bundle (sectors + weather) from environment variables, with sensible
defaults that match the Makefile and `.env.example`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = REPO_ROOT / "data" / "hackathon_data_bundle"
DEFAULT_SCENARIO = "asked_at_2025-05-29T21:00:00Z"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "data" / "artifacts"


def _resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (REPO_ROOT / path)


@dataclass(frozen=True)
class Settings:
    scenario_dir: Path
    artifact_root: Path
    frontend_url: str

    @property
    def scenario_name(self) -> str:
        return self.scenario_dir.name

    @property
    def bundle_dir(self) -> Path:
        return self.scenario_dir.parent

    @property
    def sectors_path(self) -> Path:
        return self.bundle_dir / "sectors.geojson"


@lru_cache
def get_settings() -> Settings:
    scenario_dir = _resolve(os.environ.get("SCENARIO_DIR", DEFAULT_BUNDLE / DEFAULT_SCENARIO))
    artifact_root = _resolve(os.environ.get("ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT))
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    return Settings(
        scenario_dir=scenario_dir,
        artifact_root=artifact_root,
        frontend_url=frontend_url,
    )

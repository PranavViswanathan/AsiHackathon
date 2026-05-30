"""Sector endpoints: geometry + capacity, and per-time-bin load.

Sector occupancy (counting flights per sector-time bin) is computed by the
Phase 4 pipeline; until that artifact exists, `load` is reported as 0 and
`over_demand` as false, so the frontend can render the sector map immediately."""

from __future__ import annotations

from fastapi import APIRouter

from backend.bundle import get_bundle

router = APIRouter(prefix="/api", tags=["sectors"])


@router.get("/sectors")
def list_sectors() -> list[dict]:
    return [
        {
            "name": s["name"],
            "altitude_from_ft": s["altitude_from_ft"],
            "altitude_to_ft": s["altitude_to_ft"],
            "capacity": s["capacity"],
            "load": 0,
            "geometry": s["geometry"],
        }
        for s in get_bundle().sectors()
    ]


@router.get("/sector_load")
def sector_load(t: int = 0) -> list[dict]:
    # `t` is the time-bin index; load is 0 until the Phase 4 occupancy pass lands.
    return [
        {"name": s["name"], "capacity": s["capacity"], "load": 0, "over_demand": False}
        for s in get_bundle().sectors()
    ]

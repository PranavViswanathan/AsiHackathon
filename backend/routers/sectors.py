"""Sector endpoints: geometry + capacity (from the bundle) merged with the
occupancy computed by the Phase 4 pipeline (`sectors.json`).

`GET /api/sectors` reports each sector's peak load across time bins;
`GET /api/sector_load?t=` reports the load for one time-bin index."""

from __future__ import annotations

from fastapi import APIRouter

from backend.bundle import get_bundle
from backend.store import get_store

router = APIRouter(prefix="/api", tags=["sectors"])


@router.get("/sectors")
def list_sectors() -> list[dict]:
    occupancy = get_store().sector_occupancy().get("sectors", {})
    return [
        {
            "name": s["name"],
            "altitude_from_ft": s["altitude_from_ft"],
            "altitude_to_ft": s["altitude_to_ft"],
            "capacity": s["capacity"],
            "load": occupancy.get(s["name"], {}).get("peak_load", 0),
            "over_demand": occupancy.get(s["name"], {}).get("over_demand", False),
            "geometry": s["geometry"],
        }
        for s in get_bundle().sectors()
    ]


@router.get("/sector_load")
def sector_load(t: int = 0) -> list[dict]:
    occupancy = get_store().sector_occupancy().get("sectors", {})
    out = []
    for s in get_bundle().sectors():
        load = occupancy.get(s["name"], {}).get("by_bin", {}).get(str(t), 0)
        out.append(
            {
                "name": s["name"],
                "capacity": s["capacity"],
                "load": load,
                "over_demand": load > s["capacity"],
            }
        )
    return out

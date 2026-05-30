"""Flight-results endpoints: per-flight fuel estimates, the H3 energy heatmap,
the scenario summary, and a `solve` trigger that (re)builds the artifacts.

The optimizer (altitude pass + capacity repair) lands in a later phase; until
then `POST /api/solve` just (re)runs the precompute pipeline and returns the
summary. The `lambda_*` / `iterations` knobs are accepted and reserved."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.store import get_store

router = APIRouter(prefix="/api", tags=["flights"])


class SolveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_dir: str | None = None
    force_rebuild: bool = False
    # Reserved for the Phase 5 optimizer; accepted but not yet used.
    lambda_sector: float | None = None
    lambda_weather: float | None = None
    iterations: int | None = None
    n_flights: int | None = None


@router.get("/flights")
def list_flights() -> list[dict]:
    return get_store().flights()


@router.get("/flight/{flight_id:path}")
def get_flight(flight_id: str) -> dict:
    flight = get_store().flight(flight_id)
    if flight is None:
        raise HTTPException(status_code=404, detail=f"flight not found: {flight_id}")
    return flight


@router.get("/h3")
def get_h3() -> list[dict]:
    return get_store().h3()


@router.get("/summary")
def get_summary() -> dict:
    return get_store().ensure_built()


@router.post("/solve")
def solve(request: SolveRequest) -> dict:
    store = get_store()
    try:
        return store.ensure_built(force=request.force_rebuild)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

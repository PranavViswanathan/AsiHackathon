"""Weather endpoint: the refc/retop grids for the 15-minute strip covering a
requested instant. Reads the bundle `.npz` files directly (see `docs/DATA.md`)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from backend.bundle import get_bundle

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather")
def get_weather(
    t: str = Query(..., description="ISO 8601 instant whose 15-minute strip to return"),
    step: int = Query(1, ge=1, le=64, description="Subsample stride for the grids"),
) -> dict:
    try:
        when = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid timestamp: {t}") from exc
    bundle = get_bundle()
    try:
        strip = bundle.select_strip(when)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return bundle.load_grids(strip, step=step)

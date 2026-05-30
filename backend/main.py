"""AirFlow FastAPI application.

Serves the precomputed per-snapshot artifacts (flights, H3 heatmap, summary)
and reads sectors + weather straight from the data bundle. The active scenario
is chosen by the `SCENARIO_DIR` env var (see `backend/config.py`); artifacts are
built on first access if missing. Run with:

    make backend            # uvicorn backend.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import routing, sectors, weather

settings = get_settings()

app = FastAPI(title="AirFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routing.router)
app.include_router(sectors.router)
app.include_router(weather.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "AirFlow API",
        "scenario": settings.scenario_name,
        "docs": "/docs",
        "endpoints": [
            "/api/flights",
            "/api/flight/{id}",
            "/api/h3",
            "/api/recommendations",
            "/api/summary",
            "/api/solve",
            "/api/sectors",
            "/api/sector_load?t=",
            "/api/weather?t=",
        ],
    }

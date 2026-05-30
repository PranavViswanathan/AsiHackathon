# AirFlow

Real-time airspace sector load balancing using weather-aware 4D routing optimization, built for the ASI Hackathon.

## Overview

US airspace is divided into sectors, each with a capacity limit. When too many flights enter a sector simultaneously it becomes over-demand — unsafe and delay-causing. AirFlow takes a full day of US flight plans and jointly optimizes routes to keep every sector under capacity, route around dangerous weather, and minimize total delay.

## Docs

- [Architecture](docs/ARCHITECTURE.md) — system design and data flow
- [Data](docs/DATA.md) — data sources, schemas, and ingestion
- [Algorithm](docs/ALGORITHM.md) — routing optimization approach
- [API](docs/API.md) — backend endpoint reference
- [Frontend](docs/FRONTEND.md) — UI components and 3D visualization
- [Agents](docs/AGENTS.md) — Claude Code subagent setup and usage

## Tech Stack

- Algorithm: Python, NetworkX, Shapely
- Backend: FastAPI, Uvicorn
- Frontend: Next.js 14, TypeScript, Tailwind CSS, Three.js via react-three-fiber
- Data: HRRR weather forecasts, real US flight plans, synthetic ATC sectors

## Quick Start

Backend:
  cd asi-hackathon
  pip install -r requirements.txt
  cp .env.example .env
  uvicorn backend.main:app --reload --port 8000

Frontend:
  cd frontend
  npm install
  npm run dev

Point to a different scenario:
  export SCENARIO_DIR=./data/hackathon_data_bundle/asked_at_2025-07-01T21:30:00Z

## Data

Scenarios are in data/hackathon_data_bundle/. Each scenario contains:
  routes.json       — 16,687 US flights with lat/lon waypoints
  wx/refc/          — composite reflectivity (precipitation) grids, 15-min strips
  wx/retop/         — storm top altitude grids, 15-min strips

Shared across scenarios:
  sectors.geojson   — 712 synthetic ATC sectors with capacity values

## Results

To be filled after optimization runs:
  Flights rerouted: X / 16,687
  Sectors brought under capacity: X / 712
  Weather conflicts avoided: X

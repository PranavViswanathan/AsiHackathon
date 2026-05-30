# Checkpoint Log

Running record of what has been built, phase by phase. A new section is appended
at the end of each phase. Newest phase last. See `plans/IMPLEMENTATION.md` for the
full plan and `docs/` for design references.

---

## Phase 0 — Project setup & structure

**Goal:** scaffold the repo and write the design docs before any code.

**Done:**
- Created the directory tree: `src/{data,algorithm}`, `backend/{,routers}`,
  `frontend/`, `data/`, `docs/`, `.claude/agents/`.
- Copied the data bundle into `data/hackathon_data_bundle/` (11 scenarios, 1,606
  weather `.npz`, 1 shared `sectors.geojson`).
- Wrote config: `requirements.txt`, `.env.example`, `.gitignore`, `README.md`.
- Wrote design docs: `docs/ARCHITECTURE.md`, `DATA.md`, `ALGORITHM.md`, `API.md`,
  `FRONTEND.md`, `AGENTS.md`.
- Verified data facts: 16,687 flights/scenario, 712 sectors, weather matrix
  `(256, 358)` float64.

**Note:** the repo was later flattened from a nested `asi-hackathon/` folder up to
the project root, and the duplicate top-level data bundle was removed.

---

## Planning — Plan A adapted to the current structure

**Goal:** reconcile `PLAN_A.md` (fuel/H3/optimizer) with the existing folders.

**Decisions locked:**
- Backend: **FastAPI serves results live** (pipeline in `src/`, exposed via
  `backend/`).
- Frontend: **deck.gl + MapLibre (2D) and Three.js (3D)** combined, toggled.
- Wind: **Open-Meteo**, fetched once per snapshot and cached to disk.

**Done:**
- Wrote `plans/IMPLEMENTATION.md` (module mapping, artifact contract, fuel/wind/
  storm/sector/H3/optimizer specs, backend endpoints, 6 build phases,
  verification, risks).
- Added `Makefile` with targets: `install`, `install-py`, `install-web`, `env`,
  `build`, `backend`, `frontend`, `dev`, `test`, `clean`, `clean-all`
  (configurable via `PORT`, `SCENARIO`).
- Framework note: frontend stays on **Next.js** (not Plan A's Vite) for
  consistency with existing docs; deck.gl + react-three-fiber run under Next.

---

## Phase 1 — Pipeline MVP (fuel-burn estimation)

**Goal:** ingest -> distance -> zero-wind fuel -> `flights.json` + `summary.json`
+ stubbed `h3.json`. Built TDD (red -> green).

**Done:**
- `src/data/ingest.py` — `load_scenario()` parses `routes.json[.gz]` into frozen
  `Flight` / `Scenario` dataclasses (handles `Z` and `+00:00` timestamps).
- `src/algorithm/grid.py` — `haversine_nm`, `initial_bearing_deg`,
  `route_distance_nm`.
- `src/algorithm/fuel.py` — `classify_aircraft` (regional/narrowbody/widebody by
  speed), `estimate_fuel` (zero-wind: fuel = class fuel-flow x time, CO2 = x3.16).
- `src/algorithm/h3agg.py` — `aggregate_h3` stub returning `[]` (real in Phase 4).
- `src/build.py` — orchestrator; writes `flights.json`, `summary.json`,
  `h3.json` to `data/artifacts/<snapshot>/`; CLI `--scenario-dir`/`--out-root`.
- Tests (21, all passing): `tests/test_grid.py`, `test_fuel.py`, `test_ingest.py`,
  `test_build.py`.
- Config: added `pyproj`, `h3`, `requests`, `pytest` to `requirements.txt`; added
  `.venv/`, `data/artifacts/`, `frontend/public/data/`, `.pytest_cache/`,
  `.DS_Store` to `.gitignore`; created `.venv`; added `pytest.ini`.

**Verified:**
- `make test` -> 21 passed.
- `make build` (scenario `asked_at_2025-05-29T21:00:00Z`) ->
  16,687 flights, 63.2M kg fuel, 199.7M kg CO2, 11.5M nm;
  classes 13,248 narrowbody / 3,189 regional / 250 widebody.

**Limitations / deferred:**
- Fuel is **zero-wind**; Open-Meteo wind + storm penalties land in Phase 3.
- `h3.json` is empty `[]` until Phase 4.
- No sector occupancy yet (Phase 4); no optimizer yet (Phase 5).

**Run it:**
```
make install-py        # one-time: venv + deps
make test              # 21 tests
make build             # writes data/artifacts/<snapshot>/
```

**Next:** Phase 2 — FastAPI backend serving these artifacts.

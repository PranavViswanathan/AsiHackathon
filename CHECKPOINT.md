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

---

## Frontend slice — static-data UI, API-ready

**Goal:** build the `frontend/` app reading static JSON now, designed to swap to
the live API later by changing one env var. deck.gl + MapLibre (2D) and Three.js
(3D), toggleable.

**Done:**
- `src/export_web.py` — exports lean static JSON from pipeline artifacts to
  `frontend/public/data/<snapshot>/`: `flights_baseline.json` (top 1,500 flights
  by fuel, rounded coords, `path` as `[lon,lat]`), `sectors.json` (712 sectors +
  empty `load_by_bin`), `h3_fuel.json` (`[]`), `summary.json`; plus
  `snapshots.json` with the showcase id. CLI `--snapshot`/`--max-flights`.
- Next.js 14 (App Router) + TypeScript (strict) + Tailwind app under `frontend/`.
- **Swappable data layer** (`frontend/src/lib/data/`): `DataSource` interface;
  `StaticDataSource` (reads `/data/...` files), `ApiDataSource` (hits the planned
  FastAPI endpoints), `getDataSource()` factory selecting impl from
  `NEXT_PUBLIC_DATA_SOURCE`. Components only call the interface, never fetch
  directly. 8 Vitest tests cover URL routing + factory selection.
- Components: `MapView` (deck.gl PathLayer colored by fuel via d3 turbo, sectors
  GeoJsonLayer, H3HexagonLayer; MapLibre CARTO dark basemap), `Scene3D`
  (react-three-fiber, samples <=500 paths), `ControlPanel` (2D/3D + layer +
  scenario toggles, fuel legend), `DetailPanel`, `SummaryHeader`. Map/3D are
  client-only via `next/dynamic` `{ssr:false}`.
- `frontend/.env.local.example` with `NEXT_PUBLIC_DATA_SOURCE`,
  `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SNAPSHOT`.

**Verified:**
- `npm run build` -> compiled successfully (route `/` ~100 kB First Load JS).
- `npx vitest run` -> 8 passed.
- `npm run dev` -> `GET /` 200; static data files 200; 4647 modules compiled.

**Switch static -> API later:** set `NEXT_PUBLIC_DATA_SOURCE=api` and
`NEXT_PUBLIC_API_URL` in `frontend/.env.local`. No component changes.

**Limitations / deferred:**
- H3 layer renders empty until Phase 4 produces `h3_fuel.json`.
- Only the baseline scenario exists; `recommended` toggle is inert until the
  optimizer (Phase 5) emits `flights_recommended.json`.
- Static flights are downsampled to 1,500 for browser performance.
- deck.gl 9.x layer constructors needed `unknown` casts under the SSR
  dynamic-import pattern (noted by the builder).

**Run it:**
```
make build                                          # pipeline artifacts
.venv/bin/python -m src.export_web --snapshot asked_at_2025-05-29T21:00:00Z
make install-web                                    # npm install
make frontend                                       # next dev on :3000
```

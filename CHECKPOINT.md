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

## Phase 2 — FastAPI backend serving artifacts

**Goal:** stand up `backend/` over the Phase 1 artifacts so the frontend (and
demo) can read flights, summary, H3, sectors, and weather over HTTP. Independent
of the in-progress pipeline work (wind/sectors/H3/optimizer) — it consumes the
existing artifact schema and reads sectors/weather straight from the bundle.

**Done:**
- `backend/config.py` — `Settings` from `SCENARIO_DIR` / `ARTIFACT_ROOT` /
  `FRONTEND_URL` env (defaults match the Makefile and `.env.example`).
- `backend/store.py` — `ArtifactStore`: serves `flights.json`/`summary.json`/
  `h3.json`, builds them on first access via `src.build.build_snapshot`, caches
  in memory; `flight(id)` lookup.
- `backend/bundle.py` — `BundleReader`: parses `sectors.geojson`, indexes the
  `wx/refc|retop/*.npz` strips by `[valid_from, valid_to)`, selects the strip
  covering an instant, loads + downsamples grids (nodata → `null`). Grid math per
  `docs/DATA.md`.
- `backend/routers/{routing,sectors,weather}.py` — reused the empty stubs:
  `GET /api/flights`, `GET /api/flight/{id}`, `GET /api/h3`, `GET /api/summary`,
  `POST /api/solve`; `GET /api/sectors`, `GET /api/sector_load?t=`;
  `GET /api/weather?t=&step=`.
- `backend/main.py` — FastAPI app, CORS to `FRONTEND_URL`, `/health`, `/` banner.
- Rewrote `docs/API.md` to match the artifact-serving backend (was the old
  live-solver contract).
- Config: added `httpx` to `requirements.txt` (TestClient dep); gitignored the
  root `hackathon_data_bundle/` and the `data/hackathon_data_bundle` symlink.
- Tests (12, all passing): `tests/test_backend.py` — hermetic 2-flight fixture
  scenario (synthetic routes + 2 weather strips + 2 sectors), `TestClient`.

**Verified:**
- `make test` → **33 passed** (21 Phase 1 + 12 Phase 2).
- Live smoke test (`uvicorn backend.main:app`, scenario
  `asked_at_2025-05-29T21:00:00Z`): `/api/summary` builds 16,687 flights
  (63.2M kg fuel, 199.7M kg CO₂; 13,248 narrowbody / 3,189 regional / 250
  widebody — matches Phase 1); `/api/flights` → 16,687; `/api/sectors` → 712;
  `/api/weather?t=…&step=64` selects the covering strip and returns a (4, 6) grid.

**Limitations / deferred:**
- Sector `load`/`over_demand` are `0`/`false` until the Phase 4 occupancy pass;
  `/api/h3` is `[]` until Phase 4 aggregation.
- `POST /api/solve` (re)runs the pipeline and returns the summary; optimizer
  knobs (`lambda_*`, `iterations`) are accepted but reserved for Phase 5.

**Local setup note:** the data bundle on this machine sits at the repo root
(`hackathon_data_bundle/`); tests and the Makefile expect
`data/hackathon_data_bundle/`. Bridged with a gitignored symlink:
`ln -s ../hackathon_data_bundle data/hackathon_data_bundle`.

**Run it:**
```
make install-py        # now also installs httpx
make backend           # uvicorn on :8000  (set SCENARIO via env/Makefile)
# GET http://localhost:8000/docs  for the live OpenAPI UI
```

**Next:** Phase 3 — Open-Meteo wind + storm penalties in the pipeline; the
backend endpoints already carry the richer per-flight fields once `src/` emits them.

---

## Phase 3 — Wind + storms (wind-aware fuel, storm penalty)

**Goal:** make fuel depend on weather — wind via ground speed, plus a storm
penalty on convectively exposed segments — and surface the new fields through the
existing artifacts/endpoints. The zero-wind path stays byte-for-byte identical.

**Done:**
- `src/data/weather.py` — `WeatherGrid`: indexes the `wx/refc|retop/*.npz` strips
  by `[valid_from, valid_to)`, bisect-selects the strip covering a sample time
  (nearest fallback), maps lat/lon→cell (`docs/DATA.md`), and reports
  `exposure(lat, lon, alt, t)` = `refc >= 40 AND alt < retop` with nodata handling.
  Offline (no network).
- `src/data/wind.py` — `WindField` (gridded, hourly, per pressure level) with
  bilinear-in-space / nearest-in-time sampling, pressure level nearest the cruise
  altitude, and met-direction→(east,north) conversion. `fetch_wind_field` pulls a
  coarse CONUS grid from Open-Meteo (`wind_speed_unit=kn`, 200/250 hPa);
  `load_or_fetch_wind` caches to `wind_cache.npz` and returns `None` on any failure
  so the build cleanly degrades to zero-wind.
- `src/algorithm/fuel.py` — `estimate_fuel(flight, wind=None, weather=None)` now
  integrates per segment: `GS = max(TAS + along_track_wind, 150)` (floor only on
  the wind path), storm penalty = `+15%` fuel on exposed segments. New
  `FuelEstimate` fields: `base_fuel_kg`, `headwind_nm`, `tailwind_nm`,
  `mean_along_track_kt`, `storm_nm`, `max_refc_dbz`, `storm_penalty_kg` — all
  defaulted so the no-arg call is unchanged.
- `src/build.py` — storms **on by default** (offline), winds **opt-in**
  (`--wind` / `AIRFLOW_WIND=1`, cached). Enriched `flights.json` + new `summary`
  totals (`total_base_fuel_kg`, `wind_delta_fuel_kg`, `total_storm_nm`,
  `n_storm_flights`, `total_storm_penalty_kg`, `wind_enabled`, `storms_enabled`).
- `Makefile` — added `build-wind`; `.env.example` notes `AIRFLOW_WIND`. Updated
  `docs/API.md` flight/summary schemas.
- Tests (+18): `tests/test_wind.py` (11) and `tests/test_weather.py` (8) — all
  offline (HTTP mocked / hand-built fields).

**Verified:**
- `make test` → **51 passed** (~17s).
- Build (storms only, offline, full scenario): 361 storm-exposed flights,
  15,903 nm storm distance, +13,503 kg penalty; `total_base_fuel_kg` =
  63,193,079.2 — **identical to Phase 1**, confirming the zero-wind path is intact.
  Example: UAL285 KIAH→KLAX @34k ft, 417 nm in storm, max 52.8 dBZ, +335.6 kg.
- Build with `--wind`: live Open-Meteo fetch succeeded (5×9 grid × 48 h × 200/250
  hPa; sample @(40,-100) 34k ft → u=+47.8 kt eastward, realistic jet aloft);
  `wind_delta_fuel_kg` = +451,710 kg. Rebuild loads `wind_cache.npz` (2 min → 20 s,
  no network, identical totals).

**Limitations / deferred:**
- Storm penalty is a flat +15% on exposed segments (a proxy, not a routed detour);
  lateral reroutes are Phase 5.
- `WeatherGrid` (src) and `backend/bundle.py` parse strips independently; a future
  cleanup could share one implementation.

**Run it:**
```
make build             # storms on, zero-wind (offline, deterministic)
make build-wind        # also fetch + cache Open-Meteo winds (network on first run)
```

**Next:** Phase 4 — real H3 aggregation (`src/algorithm/h3agg.py`) + sector
occupancy (`src/algorithm/sectors.py`); the `/api/h3` and sector `load` endpoints
light up once those artifacts exist.

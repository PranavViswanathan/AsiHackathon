# Frontend

A Next.js 14 + TypeScript app styled with Tailwind CSS. Its job is to make the
optimization legible: show where fuel is burned and airspace is loaded, animate
weather and flights over time, let the operator filter and inspect flights, and
compare baseline vs the optimized scenario. The deck.gl + MapLibre 2D map is the
primary view; a Three.js 3D view is an alternative.

## Data layer (static now, API-ready)

Components never fetch directly. All data access goes through a single interface
(`src/lib/data/`):

- `DataSource.ts` - the interface (`getFlights`, `getSectors`, `getH3`,
  `getSummary`, `getSnapshots`, plus `getSectorLoad`/`getWeather`).
- `StaticDataSource.ts` - reads `/data/<snapshot>/*.json` from `public/`.
- `ApiDataSource.ts` - hits the FastAPI endpoints.
- `index.ts` - `getDataSource()` returns the API impl when
  `NEXT_PUBLIC_DATA_SOURCE=api`, else the static impl (default).

Switching from the bundled static JSON to the live backend is a one env-var
change. The default is `static`, which is the demo-safe path; the static files
are produced by `src/export_web.py` in the exact shape these types expect.

## Page Layout

A single dashboard:

```
+--------------------------------------------------------------+
|  SummaryHeader  (flights, fuel, CO2, distance, $ saved)      |
+-----------+--------------------------------------+-----------+
| Control   |                                      |  Detail   |
| + Filter  |        MapView (2D) or Scene3D       |  + Savings|
| panels    |        + TimelineControl             |  panels   |
+-----------+--------------------------------------+-----------+
```

## Components

**MapView** (`deck.gl` + `MapLibre`, the hero) - a MapLibre CARTO dark basemap
with deck.gl layers on top:
- `PathLayer` of flights, colored by fuel via a data-driven turbo scale (see
  `lib/fuelColor.ts`); pickable, click selects a flight.
- `GeoJsonLayer` of US state boundaries (white) for geographic context.
- `H3HexagonLayer` energy heatmap (toggle), colored by the H3 value.
- `GeoJsonLayer` of sectors (toggle), filled and colored by over-demand.
- Animated weather radar frames and flight playback driven by the timeline.
- `getTooltip` popups: hover a sector (peak load vs capacity, over-demand,
  altitude band), an H3 cell (fuel, flights, mean, congestion), or a flight.

**Scene3D** (`react-three-fiber` + `drei`) - a 3D view of the same flights, each
path lifted to its cruise altitude, with a ground grid and orbit controls. Down-
samples for framerate.

**TimelineControl** - scrubs/plays the scenario clock, advancing the weather
radar frame and animating flights along their routes (`lib/flightAnim.ts`,
`lib/weather.ts`, `lib/planeIcon.ts`).

**ControlPanel** - 2D/3D toggle; layer toggles (sectors, H3); an H3 fuel/traffic
mode toggle with its legend; a baseline/optimized scenario toggle; and the flight
fuel-color legend (real turbo gradient with the live domain labels).

**FilterPanel** - filter the rendered flights by airline / flight-number search
(with suggestions), aircraft class, airborne status, origin, and destination.
Shows the match count; filtering applies to both the 2D and 3D views.

**DetailPanel** - the selected flight: number, origin to destination, altitude,
distance (NM), fuel and class, airborne status, and, when it has a recommended
change, the altitude/departure delta with fuel, CO2, and dollars saved.

**SavingsPanel** - the optimizer roll-up: dollars saved (headline), fuel and CO2
saved, a baseline vs optimized fuel bar chart (Recharts, axis zoomed to the few-
percent gap so it is visible), and over-demand sectors before to after.

**SummaryHeader** - snapshot totals: flights, fuel, CO2, distance, and dollars
saved.

## Color scales

- **Flights**: a turbo scale whose domain is computed from the loaded flights
  (min to the 95th percentile), so the spectrum spreads across the bulk (blue at
  the low end, red at the top); the top few percent clamp to red.
- **H3**: a yellow to red heat scale normalized to the busiest cell, where yellow
  is low energy/traffic and red is a hotspot.

## Notes

- MapView and Scene3D are client-only, imported via `next/dynamic` with
  `{ ssr: false }` (deck.gl, MapLibre, and three are not SSR-safe).
- The H3 heatmap is a full-snapshot aggregate and does not shrink when flights
  are filtered.
- If the dev server throws a stale-chunk error after big changes, clear the cache
  with `rm -rf frontend/.next` and restart.

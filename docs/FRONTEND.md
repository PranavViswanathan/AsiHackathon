# Frontend

The frontend is a Next.js 14 + TypeScript app styled with Tailwind CSS. Its job
is to make the optimization legible: show where airspace is congested, watch
flights reroute, and let the operator tune the cost weights and re-run. The 3D
CONUS view is the hero; everything else supports it.

## Page Layout

A single dashboard, three stacked regions:

```
+--------------------------------------------------+
|  ControlPanel  (scenario, lambdas, iters, Run)   |
+--------------------------------------------------+
|                                                  |
|              Scene3D  (hero, center)             |
|        3D CONUS — sectors, flights, weather      |
|                                                  |
+--------------------------------------------------+
|  ConvergenceChart        |   SectorMap (2D)      |
+--------------------------------------------------+
```

- **Top:** `ControlPanel` — the inputs and the Run button.
- **Center:** `Scene3D` — the main visualization, given the most vertical space.
- **Bottom:** charts and the 2D companion view.

## Scene3D

The centerpiece, built with Three.js via `@react-three/fiber` and
`@react-three/drei`.

- **CONUS map** — the continental US rendered as a base plane / extruded
  geometry under the airspace, giving geographic context.
- **Sectors** — each sector drawn from its `sectors.geojson` polygon, extruded to
  its altitude band (HIGH stacked above LOW). Color encodes load relative to
  capacity: **green** (well under), **yellow** (near capacity), **red** (over-
  demand). This is the at-a-glance read on where the airspace is stressed.
- **Flight paths** — optimized trajectories drawn as lines, with **moving
  spheres** animating along each path over the scenario timeline to convey flow
  and density.
- **Weather overlay** — `refc`/`retop` rendered as semi-transparent **fog /
  cloud** volumes over the affected regions, so the viewer can see flights bend
  around storms.
- **Orbit controls** — click-drag to rotate, scroll to zoom, to inspect
  congestion from any angle.

## ControlPanel

The input surface across the top:

- **Scenario picker** — dropdown of the 11 available scenarios; selecting one
  loads its flights and weather.
- **Lambda sliders** — `lambda_sector` and `lambda_weather`, the two cost-
  function weights, so the operator can trade congestion relief and weather
  margin against delay.
- **Iteration count** — number of iterative-Dijkstra passes to run.
- **Run button** — fires `POST /api/solve` with the current settings and streams
  the result into the visualization.

## SectorMap

A 2D overhead (top-down) view of the sectors as a companion/fallback to the 3D
scene. Same green/yellow/red load coloring, but flat and always readable
regardless of camera state — useful for precisely identifying which sectors are
over-demand and for environments where the 3D view is heavy.

## ConvergenceChart

A line chart of **sector over-demand count per iteration**, sourced from the
solve response's `history`. It is the proof that the optimizer is working: the
curve should descend toward zero as iterations progress, telling the story of
congestion being designed out of the airspace.

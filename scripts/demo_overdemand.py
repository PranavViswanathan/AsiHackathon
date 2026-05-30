#!/usr/bin/env python3
"""End-to-end demo of the core pipeline.

    routes -> positions(t) -> sector+band -> occupancy vs capacity -> over-demand

Loads one scenario, rolls every flight forward across a time grid, counts how many
are inside each sector at each step, and reports/plots where demand exceeds
capacity.

Usage:
    python scripts/demo_overdemand.py                         # default scenario
    python scripts/demo_overdemand.py --scenario 2025-08-21T18:00:00Z --step 15
    python scripts/demo_overdemand.py --band HIGH --out out/overdemand.png
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, so `airspace` imports

import matplotlib

matplotlib.use("Agg")  # headless: write a PNG, don't open a window
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPoly
from shapely.geometry import shape

from airspace import (
    SectorIndex,
    list_scenarios,
    load_scenario,
    load_sectors,
    occupancy_timeline,
    positions_at,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="2025-07-08T22:00:00Z", help="scenario id (asked_at suffix)")
    ap.add_argument("--step", type=int, default=15, help="timestep in minutes")
    ap.add_argument("--band", default="HIGH", choices=["HIGH", "LOW"], help="band to plot")
    ap.add_argument("--out", default="out/overdemand.png", help="output PNG path")
    ap.add_argument("--top", type=int, default=15, help="how many over-demand events to print")
    args = ap.parse_args()

    print(f"Available scenarios: {', '.join(list_scenarios())}\n")

    t0 = time.perf_counter()
    scn = load_scenario(args.scenario)
    print(f"Scenario {args.scenario}")
    print(f"  window {scn.window_start} -> {scn.window_end}")
    print(f"  {len(scn)} flights  ({sum(f.is_airborne for f in scn.flights)} airborne at asked_at)")

    idx = SectorIndex(load_sectors())
    print(f"  sectors loaded ({len(idx.capacity)} total)\n")

    print(f"Rolling flights forward at {args.step}-min steps ...")
    tl = occupancy_timeline(scn, idx, step_minutes=args.step)
    print(f"  {len(tl.times)} timesteps computed in {time.perf_counter() - t0:.1f}s\n")

    # ---- console report -----------------------------------------------------
    events = tl.over_demand_events()
    n_sectors_hit = len({e["sector"] for e in events})
    print(f"Over-demand: {len(events)} (sector, time) breaches across {n_sectors_hit} sectors")
    print(f"\nWorst {args.top} breaches (count vs capacity):")
    print(f"  {'sector':<10} {'time (UTC)':<20} {'count':>5} {'cap':>4} {'over':>5}")
    for e in events[: args.top]:
        ts = e["time"].strftime("%Y-%m-%d %H:%M")
        print(f"  {e['sector']:<10} {ts:<20} {e['count']:>5} {e['capacity']:>4} {e['overage']:>5}")

    # busiest single timestep (most total airborne flights), used for the map overlay
    airborne = [sum(c.values()) for c in tl.counts]
    busiest = int(np.argmax(airborne))
    t_peak = tl.times[busiest]
    print(f"\nBusiest moment: {t_peak} with {airborne[busiest]} flights airborne")

    # ---- map plot -----------------------------------------------------------
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _plot_map(scn, idx, tl, args.band, t_peak, out_path)
    print(f"\nWrote {out_path}")


def _plot_map(scn, idx, tl, band, t_peak, out_path) -> None:
    """Sectors coloured by peak overage ratio, with flight positions at t_peak."""
    geojson = load_sectors()
    peak = tl.peak_per_sector()

    patches, ratios = [], []
    for f in geojson["features"]:
        name = f["properties"]["name"]
        if not name.startswith(band + "_"):
            continue
        geom = shape(f["geometry"])
        cap = f["properties"]["capacity"]
        # ratio > 1 means the sector went over-demand at its peak
        ratio = peak.get(name, 0) / cap if cap else 0.0
        patches.append(MplPoly(np.asarray(geom.exterior.coords)))
        ratios.append(ratio)

    fig, ax = plt.subplots(figsize=(13, 8))
    pc = PatchCollection(patches, cmap="RdYlGn_r", edgecolor="white", linewidth=0.3, alpha=0.85)
    pc.set_array(np.asarray(ratios))
    pc.set_clim(0, 2)  # 1.0 = exactly at capacity; >1 over-demand
    ax.add_collection(pc)
    cbar = plt.colorbar(pc, ax=ax, label="peak occupancy / capacity  (>1 = over-demand)")
    cbar.ax.axhline(0.5, color="black", lw=1)  # marks ratio=1 on a 0..2 scale

    # overlay flight positions at the busiest moment, for the same band
    flights, lats, lons = positions_at(scn.flights, t_peak, only_active=True)
    keep = np.array([f.band == band for f in flights])
    if keep.any():
        ax.scatter(lons[keep], lats[keep], s=3, c="black", alpha=0.4, label=f"{int(keep.sum())} flights @ {t_peak:%H:%M}Z")
        ax.legend(loc="lower left")

    ax.set_xlim(-127, -66)
    ax.set_ylim(23, 50)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{band}-band sector demand — scenario {scn.asked_at:%Y-%m-%d}\n(peak over the day; dots = flights at busiest moment)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)


if __name__ == "__main__":
    main()

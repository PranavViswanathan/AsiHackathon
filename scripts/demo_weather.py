#!/usr/bin/env python3
"""Join weather to congestion: which over-demand sectors are weather-driven?

    over-demand events (sector, time)
        x  flights flying through refc>=40 & alt<=retop in that sector at that time
        =  weather-driven over-demand

Reports the over-demand breaches ranked by how many of the flights in them are
fighting weather, and plots the worst such moment: reflectivity background,
over-demand sectors outlined, blocked flights highlighted.

Usage:
    python scripts/demo_weather.py
    python scripts/demo_weather.py --scenario 2025-07-08T22:00:00Z --out out/weather.png
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import shape

from airspace import (
    SectorIndex,
    WeatherForecast,
    blocked_flights,
    load_scenario,
    load_sectors,
    occupancy_timeline,
)
from airspace.weather import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, REFC_NODATA


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="2025-07-08T22:00:00Z")
    ap.add_argument("--step", type=int, default=15)
    ap.add_argument("--out", default="out/weather_overdemand.png")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    scn = load_scenario(args.scenario)
    idx = SectorIndex(load_sectors())
    wx = WeatherForecast.load(args.scenario)
    print(f"Scenario {args.scenario}: {len(scn)} flights, {len(wx.refc)} weather strips")
    print(f"  weather covers {wx.covered[0]} -> {wx.covered[1]}\n")

    # over-demand events from the occupancy core
    tl = occupancy_timeline(scn, idx, step_minutes=args.step)
    events = tl.over_demand_events()

    # for each timestep that has a breach, count weather-blocked flights per sector
    breach_times = sorted({e["time"] for e in events})
    blocked_by_sector_time: dict[tuple[str, object], int] = {}
    for t in breach_times:
        flights, lats, lons, mask = blocked_flights(scn, wx, t)
        if not mask.any():
            continue
        names = idx.assign_flight_positions(flights, lats, lons)
        c = Counter(n for n, b in zip(names, mask) if b and n is not None)
        for name, n in c.items():
            blocked_by_sector_time[(name, t)] = n

    # annotate each over-demand event with how many of its flights are in weather
    for e in events:
        e["blocked"] = blocked_by_sector_time.get((e["sector"], e["time"]), 0)

    weather_driven = [e for e in events if e["blocked"] > 0]
    print(f"{len(events)} over-demand breaches; {len(weather_driven)} have flights flying through weather\n")

    ranked = sorted(events, key=lambda e: (e["blocked"], e["overage"]), reverse=True)
    print(f"Top {args.top} breaches by weather exposure:")
    print(f"  {'sector':<10} {'time (UTC)':<18} {'count':>5} {'cap':>4} {'over':>5} {'inWx':>5}")
    for e in ranked[: args.top]:
        ts = e["time"].strftime("%m-%d %H:%M")
        print(f"  {e['sector']:<10} {ts:<18} {e['count']:>5} {e['capacity']:>4} {e['overage']:>5} {e['blocked']:>5}")

    # pick the moment with the most weather-driven congestion to plot
    if weather_driven:
        t_focus = max(ranked, key=lambda e: e["blocked"])["time"]
    else:
        t_focus = max(events, key=lambda e: e["overage"])["time"] if events else breach_times[0]
    print(f"\nPlotting {t_focus}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _plot(scn, idx, tl, wx, t_focus, out_path)
    print(f"Wrote {out_path}")


def _plot(scn, idx, tl, wx, t, out_path) -> None:
    geojson = load_sectors()
    counts = dict(zip(tl.times, tl.counts))[t] if t in dict(zip(tl.times, tl.counts)) else None
    # nearest timeline step to t for the occupancy snapshot
    if counts is None:
        i = int(np.argmin([abs((tt - t).total_seconds()) for tt in tl.times]))
        counts = tl.counts[i]

    fig, ax = plt.subplots(figsize=(13, 8))

    # reflectivity background
    refc, _ = wx.grids_at(t)
    refc = np.where(refc <= REFC_NODATA, np.nan, refc)
    ax.imshow(
        refc,
        extent=[LON_MIN, LON_MAX, LAT_MIN, LAT_MAX],
        origin="upper",
        vmin=0, vmax=60, cmap="Blues", alpha=0.7, zorder=0,
    )

    # outline over-demand sectors at this moment (both bands)
    n_over = 0
    for f in geojson["features"]:
        name = f["properties"]["name"]
        cap = f["properties"]["capacity"]
        if counts.get(name, 0) > cap:
            xs, ys = shape(f["geometry"]).exterior.xy
            ax.plot(xs, ys, color="red", lw=1.4, zorder=3)
            n_over += 1

    # flights: all active (grey) + weather-blocked (orange)
    flights, lats, lons, mask = blocked_flights(scn, wx, t)
    ax.scatter(lons[~mask], lats[~mask], s=3, c="0.4", alpha=0.35, zorder=1, label=f"{int((~mask).sum())} active flights")
    if mask.any():
        ax.scatter(lons[mask], lats[mask], s=14, c="orange", edgecolor="black", linewidth=0.3,
                   zorder=4, label=f"{int(mask.sum())} in weather")

    ax.plot([], [], color="red", lw=1.4, label=f"{n_over} over-demand sectors")
    ax.set_xlim(-127, -66)
    ax.set_ylim(23, 50)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Weather-driven congestion — {scn.asked_at:%Y-%m-%d}  {t:%H:%M}Z\n"
                 f"reflectivity (blue), over-demand sectors (red), flights in weather (orange)")
    ax.legend(loc="lower left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)


if __name__ == "__main__":
    main()

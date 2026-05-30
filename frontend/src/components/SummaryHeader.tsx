"use client";

import type { Summary, Scenario } from "@/lib/data/types";

type Props = {
  summary: Summary | null;
  scenario: Scenario;
};

const SCENARIO_LABEL: Record<Scenario, string> = {
  baseline: "baseline",
  recommended: "optimal",
};

function formatLarge(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(0);
}

function formatSnapshot(snapshot: string): string {
  const match = /asked_at_(.+)/.exec(snapshot);
  if (match) {
    try {
      return new Date(match[1]).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      });
    } catch {
      return match[1];
    }
  }
  return snapshot;
}

type StatProps = {
  label: string;
  value: string;
  unit?: string;
};

function Stat({ label, value, unit }: StatProps) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-400 uppercase tracking-wider">{label}</span>
      <span className="text-xl font-bold font-mono text-white">
        {value}
        {unit && <span className="text-xs text-gray-400 ml-1">{unit}</span>}
      </span>
    </div>
  );
}

export default function SummaryHeader({ summary, scenario }: Props) {
  if (!summary) {
    return (
      <header className="flex items-center gap-6 px-6 py-3 bg-gray-950 border-b border-gray-800">
        <span className="text-lg font-bold text-blue-400">AirFlow</span>
        <span className="text-sm text-gray-500">Loading data...</span>
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-6 px-6 py-3 bg-gray-950 border-b border-gray-800">
      <span className="text-lg font-bold text-blue-400 shrink-0">AirFlow</span>
      <Stat label="Flights" value={formatLarge(summary.n_flights)} />
      <Stat label="Fuel" value={formatLarge(summary.total_fuel_kg)} unit="kg" />
      <Stat label="CO2" value={formatLarge(summary.total_co2_kg)} unit="kg" />
      <Stat label="Distance" value={formatLarge(summary.total_distance_nm)} unit="nm" />
      <div className="ml-auto text-xs text-gray-500">
        Snapshot: {formatSnapshot(summary.snapshot)} &bull; {SCENARIO_LABEL[scenario]}
      </div>
    </header>
  );
}

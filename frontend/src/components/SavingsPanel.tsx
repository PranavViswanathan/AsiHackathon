"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Optimization } from "@/lib/data/types";
import { formatUsd } from "@/lib/cost";

type Props = {
  optimization?: Optimization | null;
};

function formatKg(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M kg`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k kg`;
  return `${n.toFixed(0)} kg`;
}

const BASELINE_COLOR = "#6b7280"; // gray-500
const OPTIMIZED_COLOR = "#10b981"; // emerald-500

export default function SavingsPanel({ optimization }: Props) {
  if (!optimization) {
    return (
      <div className="flex flex-col gap-2 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Savings</p>
        <p className="text-sm text-gray-500 mt-1">No optimized scenario for this snapshot.</p>
      </div>
    );
  }

  const {
    baseline_fuel_kg,
    optimized_fuel_kg,
    fuel_saved_kg,
    fuel_saved_pct,
    cost_saved_usd = 0,
    co2_saved_kg = 0,
    overloaded_sectors_before,
    overloaded_sectors_after,
    n_altitude_changes,
    n_departure_changes,
  } = optimization;

  const data = [
    { name: "Baseline", fuel: baseline_fuel_kg / 1_000_000, color: BASELINE_COLOR },
    { name: "Optimized", fuel: optimized_fuel_kg / 1_000_000, color: OPTIMIZED_COLOR },
  ];

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
      <p className="text-xs text-gray-400 uppercase tracking-wider">Optimizer Savings</p>

      <div>
        <p className="text-3xl font-bold font-mono text-emerald-400 leading-tight">
          {formatUsd(cost_saved_usd)}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {formatKg(fuel_saved_kg)} &bull; {fuel_saved_pct.toFixed(1)}% &bull;{" "}
          {(co2_saved_kg / 1000).toFixed(0)} t CO2 avoided
        </p>
      </div>

      <div className="h-[130px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
            <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
            <Tooltip
              cursor={{ fill: "#ffffff10" }}
              contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: "#e5e7eb" }}
              formatter={(v: number) => [`${v.toFixed(2)}M kg`, "Fuel"]}
            />
            <Bar dataKey="fuel" radius={[3, 3, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-xs text-gray-400">Overloaded sectors</p>
          <p className="font-mono">
            {overloaded_sectors_before} &rarr;{" "}
            <span className="text-emerald-300">{overloaded_sectors_after}</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Changes</p>
          <p className="font-mono text-xs">
            {n_altitude_changes.toLocaleString()} alt &bull; {n_departure_changes.toLocaleString()} time
          </p>
        </div>
      </div>
    </div>
  );
}

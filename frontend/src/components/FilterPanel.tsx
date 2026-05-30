"use client";

import { useMemo } from "react";
import type { WebFlight } from "@/lib/data/types";

export type Filters = {
  aircraftClass: "all" | "regional" | "narrowbody" | "widebody";
  status: "all" | "airborne" | "preflight";
  origin: string;
  destination: string;
};

export const DEFAULT_FILTERS: Filters = {
  aircraftClass: "all",
  status: "all",
  origin: "all",
  destination: "all",
};

type Props = {
  flights: WebFlight[];
  filters: Filters;
  onChange: (filters: Filters) => void;
  matchCount: number;
};

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

function Dropdown({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs text-gray-400 mb-1 block">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function FilterPanel({ flights, filters, onChange, matchCount }: Props) {
  const origins = useMemo(
    () => uniqueSorted(flights.map((f) => f.origin)),
    [flights]
  );
  const destinations = useMemo(
    () => uniqueSorted(flights.map((f) => f.destination)),
    [flights]
  );

  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const isFiltered =
    filters.aircraftClass !== "all" ||
    filters.status !== "all" ||
    filters.origin !== "all" ||
    filters.destination !== "all";

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Filters</p>
        {isFiltered && (
          <button
            className="text-xs text-blue-400 hover:text-blue-300"
            onClick={() => onChange(DEFAULT_FILTERS)}
          >
            Reset
          </button>
        )}
      </div>

      <Dropdown
        label="Aircraft class"
        value={filters.aircraftClass}
        onChange={(v) => set({ aircraftClass: v as Filters["aircraftClass"] })}
        options={[
          { value: "all", label: "All classes" },
          { value: "regional", label: "Regional" },
          { value: "narrowbody", label: "Narrowbody" },
          { value: "widebody", label: "Widebody" },
        ]}
      />

      <Dropdown
        label="Status"
        value={filters.status}
        onChange={(v) => set({ status: v as Filters["status"] })}
        options={[
          { value: "all", label: "All" },
          { value: "airborne", label: "Airborne" },
          { value: "preflight", label: "Pre-departure" },
        ]}
      />

      <Dropdown
        label="Origin"
        value={filters.origin}
        onChange={(v) => set({ origin: v })}
        options={[
          { value: "all", label: "Any origin" },
          ...origins.map((o) => ({ value: o, label: o })),
        ]}
      />

      <Dropdown
        label="Destination"
        value={filters.destination}
        onChange={(v) => set({ destination: v })}
        options={[
          { value: "all", label: "Any destination" },
          ...destinations.map((d) => ({ value: d, label: d })),
        ]}
      />

      <p className="text-xs text-gray-500">{matchCount} flights shown</p>
    </div>
  );
}

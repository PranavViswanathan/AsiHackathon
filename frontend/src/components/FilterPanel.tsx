"use client";

import { useMemo, useState } from "react";
import type { WebFlight } from "@/lib/data/types";

export type Filters = {
  search: string;
  aircraftClass: "all" | "regional" | "narrowbody" | "widebody";
  status: "all" | "airborne" | "preflight";
  origin: string;
  destination: string;
};

export const DEFAULT_FILTERS: Filters = {
  search: "",
  aircraftClass: "all",
  status: "all",
  origin: "all",
  destination: "all",
};

type Props = {
  flights: WebFlight[];
  filters: Filters;
  onChange: (filters: Filters) => void;
  onReset: () => void;
  matchCount: number;
};

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

type Suggestion = { value: string; label: string; sub: string };

const MAX_SUGGESTIONS = 8;

// Build a ranked list of airline-code and flight-number suggestions for the
// current query. Airlines (the leading letters of a flight number) come first.
function buildSuggestions(flights: WebFlight[], query: string): Suggestion[] {
  const q = query.trim().toUpperCase();

  const airlineCounts = new Map<string, number>();
  const flightNumbers = new Set<string>();
  for (const f of flights) {
    const fn = f.flight_number.toUpperCase();
    flightNumbers.add(fn);
    const code = /^[A-Z]+/.exec(fn)?.[0];
    if (code) airlineCounts.set(code, (airlineCounts.get(code) ?? 0) + 1);
  }

  const airlines: Suggestion[] = Array.from(airlineCounts.entries())
    .filter(([code]) => !q || code.includes(q))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([code, n]) => ({
      value: code,
      label: code,
      sub: `${n} flight${n === 1 ? "" : "s"}`,
    }));

  const flightsList: Suggestion[] = uniqueSorted(Array.from(flightNumbers))
    .filter((fn) => q && fn.includes(q))
    .map((fn) => ({ value: fn, label: fn, sub: "flight" }));

  return [...airlines, ...flightsList].slice(0, MAX_SUGGESTIONS);
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

export default function FilterPanel({ flights, filters, onChange, onReset, matchCount }: Props) {
  const [searchOpen, setSearchOpen] = useState(false);
  const suggestions = useMemo(
    () => buildSuggestions(flights, filters.search),
    [flights, filters.search]
  );

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
    filters.search.trim() !== "" ||
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
            onClick={onReset}
          >
            Reset
          </button>
        )}
      </div>

      <div className="relative">
        <span className="text-xs text-gray-400 mb-1 block">Airline / flight #</span>
        <input
          type="text"
          value={filters.search}
          onChange={(e) => {
            set({ search: e.target.value });
            setSearchOpen(true);
          }}
          onFocus={() => setSearchOpen(true)}
          onBlur={() => setSearchOpen(false)}
          placeholder="e.g. AA or AA123"
          className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        {searchOpen && suggestions.length > 0 && (
          <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto rounded border border-gray-600 bg-gray-800 shadow-lg">
            {suggestions.map((s) => (
              <li key={`${s.sub}:${s.value}`}>
                <button
                  type="button"
                  // onMouseDown fires before input blur, so the value is applied.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    set({ search: s.value });
                    setSearchOpen(false);
                  }}
                  className="flex w-full items-center justify-between px-2 py-1.5 text-left text-sm text-gray-100 hover:bg-gray-700"
                >
                  <span className="font-mono">{s.label}</span>
                  <span className="text-xs text-gray-500">{s.sub}</span>
                </button>
              </li>
            ))}
          </ul>
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

"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import SummaryHeader from "@/components/SummaryHeader";
import ControlPanel from "@/components/ControlPanel";
import DetailPanel from "@/components/DetailPanel";
import SavingsPanel from "@/components/SavingsPanel";
import FilterPanel, { DEFAULT_FILTERS, type Filters } from "@/components/FilterPanel";
import { getDataSource } from "@/lib/data";
import type {
  WebFlight,
  SectorsGeoJSON,
  H3Cell,
  Summary,
  Scenario,
  H3Mode,
} from "@/lib/data/types";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });
const Scene3D = dynamic(() => import("@/components/Scene3D"), { ssr: false });

type ViewMode = "2d" | "3d";

const DEFAULT_SNAPSHOT =
  process.env.NEXT_PUBLIC_SNAPSHOT ?? "asked_at_2025-05-29T21:00:00Z";

export default function Page() {
  const [flights, setFlights] = useState<WebFlight[]>([]);
  const [sectors, setSectors] = useState<SectorsGeoJSON | null>(null);
  const [h3Cells, setH3Cells] = useState<H3Cell[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selectedFlight, setSelectedFlight] = useState<WebFlight | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("2d");
  const [showSectors, setShowSectors] = useState(false);
  const [showH3, setShowH3] = useState(false);
  const [h3Mode, setH3Mode] = useState<H3Mode>("fuel");
  const [scenario, setScenario] = useState<Scenario>("baseline");
  const [recommendedAvailable, setRecommendedAvailable] = useState(false);
  const [snapshot, setSnapshot] = useState(DEFAULT_SNAPSHOT);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const filteredFlights = useMemo(() => {
    const query = filters.search.trim().toUpperCase();
    return flights.filter((f) => {
      if (query && !f.flight_number.toUpperCase().includes(query)) return false;
      if (filters.aircraftClass !== "all" && f.aircraft_class !== filters.aircraftClass) return false;
      if (filters.status === "airborne" && !f.is_airborne) return false;
      if (filters.status === "preflight" && f.is_airborne) return false;
      if (filters.origin !== "all" && f.origin !== filters.origin) return false;
      if (filters.destination !== "all" && f.destination !== filters.destination) return false;
      return true;
    });
  }, [flights, filters]);

  // Color domain from the full snapshot: lowest fuel to the 95th percentile, so
  // the spectrum spreads across the bulk of flights (top 5% clamp to red).
  const fuelDomain = useMemo<[number, number]>(() => {
    if (flights.length === 0) return [0, 1];
    const sorted = flights.map((f) => f.fuel_kg).sort((a, b) => a - b);
    const min = sorted[0];
    const p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
    return [min, p95 > min ? p95 : min + 1];
  }, [flights]);

  useEffect(() => {
    const ds = getDataSource();
    ds.getSnapshots()
      .then((manifest) => {
        setSnapshot(manifest.showcase ?? manifest.snapshots[0] ?? DEFAULT_SNAPSHOT);
      })
      .catch(() => {
        setSnapshot(DEFAULT_SNAPSHOT);
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const ds = getDataSource();

    Promise.all([
      ds.getFlights(snapshot, scenario),
      ds.getSectors(snapshot),
      ds.getH3(snapshot, h3Mode, scenario),
      ds.getSummary(snapshot, scenario),
    ])
      .then(([f, s, h, sum]) => {
        setFlights(f);
        setSectors(s);
        setH3Cells(h);
        setSummary(sum);
        setLoading(false);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setLoading(false);
      });
  }, [snapshot, scenario, h3Mode]);

  useEffect(() => {
    if (scenario === "baseline") {
      const ds = getDataSource();
      ds.getFlights(snapshot, "recommended")
        .then(() => setRecommendedAvailable(true))
        .catch(() => setRecommendedAvailable(false));
    }
  }, [snapshot, scenario]);

  const handleSelectFlight = useCallback((f: WebFlight | null) => {
    setSelectedFlight(f);
  }, []);

  const handleScenarioChange = useCallback((s: Scenario) => {
    setSelectedFlight(null);
    setScenario(s);
  }, []);

  const handleResetFilters = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
    setSelectedFlight(null);
  }, []);

  // When the search narrows to a single flight (e.g. picking a flight number
  // from the dropdown), make it the active flight so the map focuses + zooms.
  useEffect(() => {
    if (filters.search.trim() !== "" && filteredFlights.length === 1) {
      setSelectedFlight(filteredFlights[0]);
    }
  }, [filters.search, filteredFlights]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-950">
      <SummaryHeader summary={summary} scenario={scenario} />

      {error && (
        <div className="px-6 py-2 bg-red-900/50 border-b border-red-700 text-red-300 text-sm">
          Error loading data: {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden gap-0">
        <aside className="flex flex-col gap-3 p-3 w-[240px] shrink-0 overflow-y-auto">
          <ControlPanel
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            showSectors={showSectors}
            onShowSectorsChange={setShowSectors}
            showH3={showH3}
            onShowH3Change={setShowH3}
            h3Mode={h3Mode}
            onH3ModeChange={setH3Mode}
            scenario={scenario}
            onScenarioChange={handleScenarioChange}
            recommendedAvailable={recommendedAvailable}
            fuelDomain={fuelDomain}
          />
          <FilterPanel
            flights={flights}
            filters={filters}
            onChange={setFilters}
            onReset={handleResetFilters}
            matchCount={filteredFlights.length}
          />
        </aside>

        <main className="flex-1 relative overflow-hidden">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center z-10 bg-gray-950/80">
              <div className="text-gray-300 text-sm">Loading {flights.length > 0 ? "updated" : ""} data...</div>
            </div>
          )}
          {viewMode === "2d" ? (
            <MapView
              flights={filteredFlights}
              sectors={sectors}
              h3Cells={h3Cells}
              showSectors={showSectors}
              showH3={showH3}
              h3Mode={h3Mode}
              fuelDomain={fuelDomain}
              selectedFlight={selectedFlight}
              scenario={scenario}
              onSelectFlight={handleSelectFlight}
            />
          ) : (
            <Scene3D flights={filteredFlights} fuelDomain={fuelDomain} scenario={scenario} />
          )}
        </main>

        <aside className="flex flex-col gap-3 p-3 w-[240px] shrink-0 overflow-y-auto">
          <SavingsPanel optimization={summary?.optimization} />
          <DetailPanel flight={selectedFlight} fuelDomain={fuelDomain} scenario={scenario} />
        </aside>
      </div>
    </div>
  );
}

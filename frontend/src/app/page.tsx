"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import SummaryHeader from "@/components/SummaryHeader";
import ControlPanel from "@/components/ControlPanel";
import DetailPanel from "@/components/DetailPanel";
import { getDataSource } from "@/lib/data";
import type {
  WebFlight,
  SectorsGeoJSON,
  H3Cell,
  Summary,
  Scenario,
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
  const [scenario, setScenario] = useState<Scenario>("baseline");
  const [recommendedAvailable, setRecommendedAvailable] = useState(false);
  const [snapshot, setSnapshot] = useState(DEFAULT_SNAPSHOT);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
      ds.getH3(snapshot, "fuel", scenario),
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
  }, [snapshot, scenario]);

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

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-950">
      <SummaryHeader summary={summary} />

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
            scenario={scenario}
            onScenarioChange={handleScenarioChange}
            recommendedAvailable={recommendedAvailable}
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
              flights={flights}
              sectors={sectors}
              h3Cells={h3Cells}
              showSectors={showSectors}
              showH3={showH3}
              onSelectFlight={handleSelectFlight}
            />
          ) : (
            <Scene3D flights={flights} />
          )}
        </main>

        <aside className="flex flex-col gap-3 p-3 w-[240px] shrink-0 overflow-y-auto">
          <DetailPanel flight={selectedFlight} />
        </aside>
      </div>
    </div>
  );
}

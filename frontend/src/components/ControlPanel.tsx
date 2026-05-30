"use client";

import { FUEL_MIN, FUEL_MAX } from "@/lib/fuelColor";
import type { Scenario } from "@/lib/data/types";

type ViewMode = "2d" | "3d";

type Props = {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  showSectors: boolean;
  onShowSectorsChange: (v: boolean) => void;
  showH3: boolean;
  onShowH3Change: (v: boolean) => void;
  scenario: Scenario;
  onScenarioChange: (s: Scenario) => void;
  recommendedAvailable: boolean;
};

const TURBO_STOPS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
  .map((t) => {
    const r = Math.round(lerp(0, 255, Math.min(1, t * 2)));
    const g = Math.round(Math.sin(Math.PI * t) * 255);
    const b = Math.round(lerp(255, 0, Math.min(1, t * 1.5)));
    return `rgb(${r},${g},${b})`;
  })
  .join(",");

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}

function formatFuel(kg: number): string {
  if (kg >= 1000) return `${(kg / 1000).toFixed(0)}k kg`;
  return `${kg} kg`;
}

export default function ControlPanel({
  viewMode,
  onViewModeChange,
  showSectors,
  onShowSectorsChange,
  showH3,
  onShowH3Change,
  scenario,
  onScenarioChange,
  recommendedAvailable,
}: Props) {
  return (
    <div className="flex flex-col gap-4 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">View</p>
        <div className="flex rounded overflow-hidden border border-gray-600">
          <button
            className={`flex-1 px-3 py-1.5 text-sm font-medium transition-colors ${
              viewMode === "2d"
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
            onClick={() => onViewModeChange("2d")}
          >
            2D Map
          </button>
          <button
            className={`flex-1 px-3 py-1.5 text-sm font-medium transition-colors ${
              viewMode === "3d"
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
            onClick={() => onViewModeChange("3d")}
          >
            3D
          </button>
        </div>
      </div>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Layers</p>
        <label className="flex items-center gap-2 cursor-pointer mb-1.5">
          <input
            type="checkbox"
            checked={showSectors}
            onChange={(e) => onShowSectorsChange(e.target.checked)}
            className="accent-blue-500"
          />
          <span className="text-sm text-gray-200">Sectors</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showH3}
            onChange={(e) => onShowH3Change(e.target.checked)}
            className="accent-blue-500"
          />
          <span className="text-sm text-gray-200">H3 Hexagons</span>
        </label>
      </div>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">Scenario</p>
        <div className="flex rounded overflow-hidden border border-gray-600">
          <button
            className={`flex-1 px-2 py-1.5 text-sm font-medium transition-colors ${
              scenario === "baseline"
                ? "bg-emerald-700 text-white"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
            onClick={() => onScenarioChange("baseline")}
          >
            Baseline
          </button>
          <button
            disabled={!recommendedAvailable}
            className={`flex-1 px-2 py-1.5 text-sm font-medium transition-colors ${
              scenario === "recommended"
                ? "bg-emerald-700 text-white"
                : recommendedAvailable
                ? "bg-gray-800 text-gray-300 hover:bg-gray-700"
                : "bg-gray-800 text-gray-600 cursor-not-allowed"
            }`}
            onClick={() => recommendedAvailable && onScenarioChange("recommended")}
          >
            Optimal
          </button>
        </div>
        {!recommendedAvailable && (
          <p className="text-xs text-gray-500 mt-1">Optimized routes not available</p>
        )}
      </div>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">
          Fuel Scale (kg)
        </p>
        <div
          className="h-3 rounded"
          style={{
            background: `linear-gradient(to right, ${TURBO_STOPS})`,
          }}
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>{formatFuel(FUEL_MIN)}</span>
          <span>{formatFuel(FUEL_MAX)}</span>
        </div>
      </div>
    </div>
  );
}

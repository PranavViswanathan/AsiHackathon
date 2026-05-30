"use client";

import { fuelGradientCss } from "@/lib/fuelColor";
import type { Scenario, H3Mode } from "@/lib/data/types";

type ViewMode = "2d" | "3d";

type Props = {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  showSectors: boolean;
  onShowSectorsChange: (v: boolean) => void;
  showH3: boolean;
  onShowH3Change: (v: boolean) => void;
  h3Mode: H3Mode;
  onH3ModeChange: (m: H3Mode) => void;
  scenario: Scenario;
  onScenarioChange: (s: Scenario) => void;
  recommendedAvailable: boolean;
  fuelDomain: [number, number];
};

const FUEL_GRADIENT = fuelGradientCss();
const H3_GRADIENT = "rgb(255,220,30),rgb(255,140,20),rgb(255,0,30)";

function formatFuel(kg: number): string {
  if (kg >= 1000) return `${(kg / 1000).toFixed(1)}k`;
  return `${Math.round(kg)}`;
}

export default function ControlPanel({
  viewMode,
  onViewModeChange,
  showSectors,
  onShowSectorsChange,
  showH3,
  onShowH3Change,
  h3Mode,
  onH3ModeChange,
  scenario,
  onScenarioChange,
  recommendedAvailable,
  fuelDomain,
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

        {showH3 && (
          <div className="mt-2 pl-6">
            <div className="flex rounded overflow-hidden border border-gray-600 mb-2">
              <button
                className={`flex-1 px-2 py-1 text-xs font-medium transition-colors ${
                  h3Mode === "fuel"
                    ? "bg-orange-600 text-white"
                    : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                }`}
                onClick={() => onH3ModeChange("fuel")}
              >
                Fuel
              </button>
              <button
                className={`flex-1 px-2 py-1 text-xs font-medium transition-colors ${
                  h3Mode === "traffic"
                    ? "bg-orange-600 text-white"
                    : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                }`}
                onClick={() => onH3ModeChange("traffic")}
              >
                Traffic
              </button>
            </div>
            <div
              className="h-2.5 rounded"
              style={{ background: `linear-gradient(to right, ${H3_GRADIENT})` }}
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>low</span>
              <span>{h3Mode === "fuel" ? "fuel/cell" : "flights/cell"}</span>
              <span>high</span>
            </div>
          </div>
        )}
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
          Flight fuel (kg)
        </p>
        <div
          className="h-3 rounded"
          style={{ background: `linear-gradient(to right, ${FUEL_GRADIENT})` }}
        />
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>{formatFuel(fuelDomain[0])}</span>
          <span>{formatFuel(fuelDomain[1])}+</span>
        </div>
      </div>
    </div>
  );
}

"use client";

import type { WebFlight, Scenario } from "@/lib/data/types";
import { makeFuelScale } from "@/lib/fuelColor";
import { formatUsd } from "@/lib/cost";
import { displayAltitude, displayFuel } from "@/lib/scenario";

type Props = {
  flight: WebFlight | null;
  fuelDomain: [number, number];
  scenario: Scenario;
};

function formatNumber(n: number, decimals = 0): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export default function DetailPanel({ flight, fuelDomain, scenario }: Props) {
  if (!flight) {
    return (
      <div className="flex flex-col gap-2 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Flight Details</p>
        <p className="text-sm text-gray-500 mt-2">Click a flight path on the map to see details.</p>
      </div>
    );
  }

  const fuel = displayFuel(flight, scenario);
  const altitude = displayAltitude(flight, scenario);
  const fuelColor = makeFuelScale(fuelDomain[0], fuelDomain[1]).toHex(fuel);
  const saved = flight.fuel_saved_kg ?? 0;
  const altChanged =
    flight.opt_cruise_altitude_ft != null &&
    flight.opt_cruise_altitude_ft !== flight.cruise_altitude_ft;
  const depShift = flight.opt_departure_shift_min ?? 0;
  const showRec = Boolean(flight.recommended) && (altChanged || depShift !== 0);

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Flight Details</p>
        <span
          className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ background: fuelColor, color: "#000" }}
        >
          {flight.aircraft_type ?? flight.aircraft_class}
        </span>
      </div>

      <div>
        <p className="text-lg font-bold font-mono">{flight.flight_number}</p>
        <p className="text-sm text-gray-300">
          {flight.origin} &rarr; {flight.destination}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <p className="text-xs text-gray-400">Altitude</p>
          <p className="font-mono">{formatNumber(altitude)} ft</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Distance</p>
          <p className="font-mono">{formatNumber(flight.distance_nm, 1)} NM</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Fuel</p>
          <p className="font-mono" style={{ color: fuelColor }}>
            {formatNumber(fuel, 1)} kg
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Status</p>
          <p className="font-mono">
            {flight.is_airborne ? (
              <span className="text-green-400">Airborne</span>
            ) : (
              <span className="text-yellow-400">On ground</span>
            )}
          </p>
        </div>
      </div>

      {showRec && (
        <div className="mt-1 pt-3 border-t border-gray-700 flex flex-col gap-2">
          <p className="text-xs text-emerald-400 uppercase tracking-wider">Recommended change</p>
          {flight.recommendation && (
            <p className="text-xs text-gray-300">{flight.recommendation}</p>
          )}
          {altChanged && (
            <p className="text-sm font-mono">
              {formatNumber(flight.cruise_altitude_ft)} &rarr;{" "}
              <span className="text-emerald-300">{formatNumber(flight.opt_cruise_altitude_ft!)} ft</span>
            </p>
          )}
          {depShift !== 0 && (
            <p className="text-sm font-mono">
              Depart{" "}
              <span className="text-emerald-300">
                {depShift > 0 ? `+${depShift}` : depShift} min
              </span>
            </p>
          )}
          <div className="grid grid-cols-3 gap-2 mt-1">
            <div>
              <p className="text-xs text-gray-400">Fuel</p>
              <p className="font-mono text-emerald-300 text-sm">-{formatNumber(saved, 0)} kg</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">CO2</p>
              <p className="font-mono text-emerald-300 text-sm">
                -{formatNumber(flight.co2_saved_kg ?? 0, 0)} kg
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Saved</p>
              <p className="font-mono text-emerald-300 text-sm">
                {formatUsd(flight.cost_saved_usd ?? 0)}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

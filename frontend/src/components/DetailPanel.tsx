"use client";

import type { WebFlight } from "@/lib/data/types";
import { fuelToHex } from "@/lib/fuelColor";

type Props = {
  flight: WebFlight | null;
};

function formatNumber(n: number, decimals = 0): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export default function DetailPanel({ flight }: Props) {
  if (!flight) {
    return (
      <div className="flex flex-col gap-2 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Flight Details</p>
        <p className="text-sm text-gray-500 mt-2">Click a flight path on the map to see details.</p>
      </div>
    );
  }

  const fuelColor = fuelToHex(flight.fuel_kg);

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border border-gray-700 rounded-lg text-white min-w-[220px]">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400 uppercase tracking-wider">Flight Details</p>
        <span
          className="text-xs px-2 py-0.5 rounded font-mono"
          style={{ background: fuelColor, color: "#000" }}
        >
          {flight.aircraft_class}
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
          <p className="font-mono">{formatNumber(flight.cruise_altitude_ft)} ft</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Distance</p>
          <p className="font-mono">{formatNumber(flight.distance_nm, 1)} nm</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Fuel</p>
          <p className="font-mono" style={{ color: fuelColor }}>
            {formatNumber(flight.fuel_kg, 1)} kg
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">CO2</p>
          <p className="font-mono">{formatNumber(flight.co2_kg, 1)} kg</p>
        </div>
        <div className="col-span-2">
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
    </div>
  );
}

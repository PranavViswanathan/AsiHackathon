"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Line } from "@react-three/drei";
import type { WebFlight } from "@/lib/data/types";
import { fuelToHex } from "@/lib/fuelColor";

type Props = {
  flights: WebFlight[];
};

const LON_CENTER = -98;
const LAT_CENTER = 39;
const SCALE = 40;

function projectPath(path: [number, number][]): [number, number, number][] {
  return path.map(([lon, lat]) => [
    (lon - LON_CENTER) / SCALE,
    0,
    -(lat - LAT_CENTER) / SCALE,
  ]);
}

type FlightLineProps = {
  flight: WebFlight;
};

function FlightLine({ flight }: FlightLineProps) {
  const points = useMemo(
    () => projectPath(flight.path),
    [flight.path]
  );

  if (points.length < 2) return null;

  return (
    <Line
      points={points}
      color={fuelToHex(flight.fuel_kg)}
      lineWidth={1}
    />
  );
}

export default function Scene3D({ flights }: Props) {
  const sample = useMemo(() => {
    if (flights.length <= 500) return flights;
    const step = Math.ceil(flights.length / 500);
    return flights.filter((_, i) => i % step === 0);
  }, [flights]);

  return (
    <Canvas
      camera={{ position: [0, 6, 8], fov: 50 }}
      style={{ background: "#0f172a" }}
    >
      <ambientLight intensity={0.5} />
      <OrbitControls enableDamping dampingFactor={0.05} />
      {sample.map((flight) => (
        <FlightLine key={flight.flight_key} flight={flight} />
      ))}
    </Canvas>
  );
}

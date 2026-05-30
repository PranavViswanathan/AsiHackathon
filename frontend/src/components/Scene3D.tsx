"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Line, Grid } from "@react-three/drei";
import type { WebFlight, Scenario } from "@/lib/data/types";
import { makeFuelScale } from "@/lib/fuelColor";
import { displayAltitude, displayFuel, displayPath } from "@/lib/scenario";

type Props = {
  flights: WebFlight[];
  fuelDomain: [number, number];
  scenario: Scenario;
};

const LON_CENTER = -98;
const LAT_CENTER = 39;
const SCALE = 40;
const FT_PER_UNIT = 10000; // one world height unit = 10,000 ft, so altitude reads directly

function projectPath(
  path: [number, number][],
  altitudeFt: number
): [number, number, number][] {
  const y = altitudeFt / FT_PER_UNIT;
  return path.map(([lon, lat]) => [
    (lon - LON_CENTER) / SCALE,
    y,
    -(lat - LAT_CENTER) / SCALE,
  ]);
}

type FlightLineProps = {
  flight: WebFlight;
  scenario: Scenario;
  color: string;
};

function FlightLine({ flight, scenario, color }: FlightLineProps) {
  const altitude = displayAltitude(flight, scenario);
  const path = displayPath(flight, scenario);
  const points = useMemo(
    () => projectPath(path, altitude),
    [path, altitude]
  );

  if (points.length < 2) return null;

  return <Line points={points} color={color} lineWidth={1} />;
}

export default function Scene3D({ flights, fuelDomain, scenario }: Props) {
  const scale = useMemo(() => makeFuelScale(fuelDomain[0], fuelDomain[1]), [fuelDomain]);
  const sample = useMemo(() => {
    if (flights.length <= 500) return flights;
    const step = Math.ceil(flights.length / 500);
    return flights.filter((_, i) => i % step === 0);
  }, [flights]);

  return (
    <Canvas camera={{ position: [0, 5, 9], fov: 50 }} style={{ background: "#0f172a" }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 5]} intensity={0.6} />
      <OrbitControls enableDamping dampingFactor={0.05} />
      <Grid
        args={[6, 4]}
        cellSize={0.25}
        cellColor="#1e293b"
        sectionSize={1}
        sectionColor="#334155"
        fadeDistance={40}
        infiniteGrid
        position={[0, 0, 0]}
      />
      {sample.map((flight) => (
        <FlightLine
          key={flight.flight_key}
          flight={flight}
          scenario={scenario}
          color={scale.toHex(displayFuel(flight, scenario))}
        />
      ))}
    </Canvas>
  );
}

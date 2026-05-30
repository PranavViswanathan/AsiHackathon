"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Line, Grid } from "@react-three/drei";
import type { WebFlight } from "@/lib/data/types";
import { fuelToHex } from "@/lib/fuelColor";

type Props = {
  flights: WebFlight[];
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
};

function FlightLine({ flight }: FlightLineProps) {
  const points = useMemo(
    () => projectPath(flight.path, flight.cruise_altitude_ft),
    [flight.path, flight.cruise_altitude_ft]
  );

  if (points.length < 2) return null;

  return <Line points={points} color={fuelToHex(flight.fuel_kg)} lineWidth={1} />;
}

export default function Scene3D({ flights }: Props) {
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
        <FlightLine key={flight.flight_key} flight={flight} />
      ))}
    </Canvas>
  );
}

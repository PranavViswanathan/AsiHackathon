import { interpolateTurbo } from "d3-scale-chromatic";

const FUEL_MIN = 57;
const FUEL_MAX = 28561;

// Most flights cluster at the low end, where raw turbo is a near-black navy that
// vanishes on a dark basemap. Spread values with a square root and map them into
// turbo's bright band [0.25, 1.0] so even low-fuel routes read as cyan, not black.
const TURBO_FLOOR = 0.25;

type Rgba = [number, number, number, number];

function fuelToTurboT(fuelKg: number): number {
  const clamped = Math.max(FUEL_MIN, Math.min(FUEL_MAX, fuelKg));
  const normalized = (clamped - FUEL_MIN) / (FUEL_MAX - FUEL_MIN);
  const spread = Math.sqrt(normalized);
  return TURBO_FLOOR + (1 - TURBO_FLOOR) * spread;
}

// d3 interpolators return "rgb(r, g, b)" strings, not hex.
function parseRgb(color: string): [number, number, number] {
  const match = color.match(/(\d+(?:\.\d+)?)/g);
  if (!match || match.length < 3) return [255, 255, 255];
  return [Math.round(+match[0]), Math.round(+match[1]), Math.round(+match[2])];
}

export function fuelToRgb(fuelKg: number): Rgba {
  const [r, g, b] = parseRgb(interpolateTurbo(fuelToTurboT(fuelKg)));
  return [r, g, b, 235];
}

export function fuelToHex(fuelKg: number): string {
  const [r, g, b] = parseRgb(interpolateTurbo(fuelToTurboT(fuelKg)));
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export { FUEL_MIN, FUEL_MAX };

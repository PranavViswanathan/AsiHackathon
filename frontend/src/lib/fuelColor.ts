import { interpolateTurbo } from "d3-scale-chromatic";

type Rgba = [number, number, number, number];

// Keep the lowest values a visible blue rather than turbo's near-black navy,
// but low enough that blue clearly shows in the path colors.
const TURBO_FLOOR = 0.06;

// d3 interpolators return "rgb(r, g, b)" strings, not hex.
function parseRgb(color: string): [number, number, number] {
  const match = color.match(/(\d+(?:\.\d+)?)/g);
  if (!match || match.length < 3) return [255, 255, 255];
  return [Math.round(+match[0]), Math.round(+match[1]), Math.round(+match[2])];
}

function toHex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export type FuelScale = {
  domain: [number, number];
  toRgb: (fuelKg: number) => Rgba;
  toHex: (fuelKg: number) => string;
};

// Linear domain so the bulk of flights spread across the spectrum (most are
// near the low end -> lots of visible blue), with the top clamped to red.
export function makeFuelScale(min: number, max: number): FuelScale {
  const lo = min;
  const hi = max > min ? max : min + 1;
  const t = (fuelKg: number): number => {
    const n = Math.max(0, Math.min(1, (fuelKg - lo) / (hi - lo)));
    return TURBO_FLOOR + (1 - TURBO_FLOOR) * n;
  };
  return {
    domain: [lo, hi],
    toRgb: (fuelKg) => [...parseRgb(interpolateTurbo(t(fuelKg))), 235] as Rgba,
    toHex: (fuelKg) => toHex(parseRgb(interpolateTurbo(t(fuelKg)))),
  };
}

// CSS gradient stops across the colors the scale actually uses, for the legend.
export function fuelGradientCss(stops = 12): string {
  const parts: string[] = [];
  for (let i = 0; i <= stops; i++) {
    const tt = TURBO_FLOOR + (1 - TURBO_FLOOR) * (i / stops);
    parts.push(interpolateTurbo(tt));
  }
  return parts.join(",");
}

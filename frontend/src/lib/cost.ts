// Fuel cost helpers. Price defaults to ~Jet-A spot ($0.85/kg) and can be
// overridden live via NEXT_PUBLIC_FUEL_PRICE so the demo can retweak the dollar
// figures without re-exporting the data.

const DEFAULT_FUEL_PRICE_USD_PER_KG = 0.85;

export function fuelPrice(): number {
  const raw = process.env.NEXT_PUBLIC_FUEL_PRICE;
  const p = raw ? parseFloat(raw) : NaN;
  return Number.isFinite(p) && p > 0 ? p : DEFAULT_FUEL_PRICE_USD_PER_KG;
}

export function costFromKg(kg: number, price: number = fuelPrice()): number {
  return kg * price;
}

export function formatUsd(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

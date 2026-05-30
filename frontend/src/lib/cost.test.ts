import { describe, it, expect, vi, afterEach } from "vitest";
import { fuelPrice, costFromKg, formatUsd } from "./cost";

describe("fuel cost helpers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to $0.85/kg", () => {
    vi.stubEnv("NEXT_PUBLIC_FUEL_PRICE", "");
    expect(fuelPrice()).toBe(0.85);
  });

  it("honors a NEXT_PUBLIC_FUEL_PRICE override", () => {
    vi.stubEnv("NEXT_PUBLIC_FUEL_PRICE", "1.20");
    expect(fuelPrice()).toBe(1.2);
  });

  it("ignores a non-positive / invalid override", () => {
    vi.stubEnv("NEXT_PUBLIC_FUEL_PRICE", "-3");
    expect(fuelPrice()).toBe(0.85);
  });

  it("costFromKg multiplies kg by price", () => {
    expect(costFromKg(1000, 0.85)).toBe(850);
  });

  it("formatUsd compacts millions, thousands, and small values", () => {
    expect(formatUsd(2_071_630)).toBe("$2.07M");
    expect(formatUsd(62_000)).toBe("$62k");
    expect(formatUsd(500)).toBe("$500");
  });
});

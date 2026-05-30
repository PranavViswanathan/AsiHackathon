// Per-scenario display helpers. The optimizer changes only altitude + departure
// time, so the "optimized" view reuses the same geometry but shows the optimized
// fuel/altitude; falls back to baseline when optimized fields are absent.

import type { Scenario, WebFlight } from "./data/types";

export function displayFuel(f: WebFlight, scenario: Scenario): number {
  return scenario === "recommended" ? f.opt_fuel_kg ?? f.fuel_kg : f.fuel_kg;
}

export function displayAltitude(f: WebFlight, scenario: Scenario): number {
  return scenario === "recommended"
    ? f.opt_cruise_altitude_ft ?? f.cruise_altitude_ft
    : f.cruise_altitude_ft;
}

export function displayCo2(f: WebFlight, scenario: Scenario): number {
  return scenario === "recommended" ? f.opt_co2_kg ?? f.co2_kg : f.co2_kg;
}

import { describe, it, expect } from "vitest";
import { displayFuel, displayAltitude } from "./scenario";
import type { WebFlight } from "./data/types";

const flight = {
  flight_key: "X",
  flight_number: "UA1",
  origin: "KJFK",
  destination: "KLAX",
  aircraft_class: "narrowbody",
  is_airborne: false,
  distance_nm: 2000,
  path: [],
  cruise_altitude_ft: 35000,
  fuel_kg: 9000,
  co2_kg: 28440,
  opt_cruise_altitude_ft: 39000,
  opt_fuel_kg: 8000,
} as WebFlight;

describe("scenario display helpers", () => {
  it("baseline shows filed altitude + baseline fuel", () => {
    expect(displayFuel(flight, "baseline")).toBe(9000);
    expect(displayAltitude(flight, "baseline")).toBe(35000);
  });

  it("recommended shows optimized altitude + optimized fuel", () => {
    expect(displayFuel(flight, "recommended")).toBe(8000);
    expect(displayAltitude(flight, "recommended")).toBe(39000);
  });

  it("falls back to baseline when optimized fields are missing", () => {
    const bare = { ...flight, opt_fuel_kg: undefined, opt_cruise_altitude_ft: undefined } as WebFlight;
    expect(displayFuel(bare, "recommended")).toBe(9000);
    expect(displayAltitude(bare, "recommended")).toBe(35000);
  });
});

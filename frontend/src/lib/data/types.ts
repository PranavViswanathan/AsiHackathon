export type WebFlight = {
  flight_key: string;
  flight_number: string;
  origin: string;
  destination: string;
  aircraft_class: "narrowbody" | "regional" | "widebody";
  aircraft_type?: string | null;
  is_airborne: boolean;
  distance_nm: number;
  path: [number, number][];
  // baseline
  cruise_altitude_ft: number;
  fuel_kg: number;
  co2_kg: number;
  // optimized scenario (optimizer changes only altitude + departure time)
  opt_cruise_altitude_ft?: number;
  opt_departure_shift_min?: number;
  opt_fuel_kg?: number;
  opt_co2_kg?: number;
  recommended?: boolean;
  // per-flight savings
  fuel_saved_kg?: number;
  co2_saved_kg?: number;
  cost_saved_usd?: number;
  recommendation?: string | null;
};

export type SectorProperties = {
  name: string;
  altitude_from_ft: number;
  altitude_to_ft: number;
  capacity: number;
  peak_load: number;
  over_demand: boolean;
  load_by_bin: Record<string, number>;
};

export type SectorsGeoJSON = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: {
      type: "Polygon" | "MultiPolygon";
      coordinates: number[][][] | number[][][][];
    };
    properties: SectorProperties;
  }>;
};

export type H3Cell = {
  hex: string;
  value: number;
  fuel_kg: number;
  n_flights: number;
  mean_kg: number;
  congestion: number;
};

export type ByClass = {
  narrowbody: number;
  regional: number;
  widebody: number;
};

export type Optimization = {
  baseline_fuel_kg: number;
  optimized_fuel_kg: number;
  fuel_saved_kg: number;
  fuel_saved_pct: number;
  n_altitude_changes: number;
  n_departure_changes: number;
  overloaded_sectors_before: number;
  overloaded_sectors_after: number;
  fuel_price_usd_per_kg?: number;
  cost_baseline_usd?: number;
  cost_optimized_usd?: number;
  cost_saved_usd?: number;
  co2_saved_kg?: number;
};

export type Summary = {
  snapshot: string;
  asked_at: string;
  n_flights: number;
  total_fuel_kg: number;
  total_co2_kg: number;
  total_distance_nm: number;
  by_class: ByClass;
  scenario: string;
  optimization?: Optimization | null;
};

export type SnapshotsManifest = {
  snapshots: string[];
  showcase: string;
};

export type Scenario = "baseline" | "recommended";
export type H3Mode = "fuel" | "traffic" | "storm";

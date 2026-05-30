export type WebFlight = {
  flight_key: string;
  flight_number: string;
  origin: string;
  destination: string;
  cruise_altitude_ft: number;
  aircraft_class: "narrowbody" | "regional" | "widebody";
  is_airborne: boolean;
  distance_nm: number;
  fuel_kg: number;
  co2_kg: number;
  path: [number, number][];
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

export type Summary = {
  snapshot: string;
  asked_at: string;
  n_flights: number;
  total_fuel_kg: number;
  total_co2_kg: number;
  total_distance_nm: number;
  by_class: ByClass;
  scenario: string;
};

export type SnapshotsManifest = {
  snapshots: string[];
  showcase: string;
};

export type Scenario = "baseline" | "recommended";
export type H3Mode = "fuel" | "traffic" | "storm";

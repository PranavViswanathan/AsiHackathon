import type {
  WebFlight,
  SectorsGeoJSON,
  H3Cell,
  Summary,
  SnapshotsManifest,
  Scenario,
  H3Mode,
} from "./types";

export interface DataSource {
  getSnapshots(): Promise<SnapshotsManifest>;
  getFlights(snapshot: string, scenario?: Scenario): Promise<WebFlight[]>;
  getSectors(snapshot: string): Promise<SectorsGeoJSON>;
  getH3(snapshot: string, mode?: H3Mode, scenario?: Scenario): Promise<H3Cell[]>;
  getSummary(snapshot: string, scenario?: Scenario): Promise<Summary>;
  getSectorLoad(snapshot: string, t: number): Promise<unknown | null>;
  getWeather(snapshot: string, t: number): Promise<unknown | null>;
}

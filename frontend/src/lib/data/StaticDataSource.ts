import type {
  WebFlight,
  SectorsGeoJSON,
  H3Cell,
  Summary,
  SnapshotsManifest,
  Scenario,
  H3Mode,
} from "./types";
import type { DataSource } from "./DataSource";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}`);
  }
  return res.json() as Promise<T>;
}

export class StaticDataSource implements DataSource {
  async getSnapshots(): Promise<SnapshotsManifest> {
    return fetchJson<SnapshotsManifest>("/data/snapshots.json");
  }

  async getFlights(snapshot: string, scenario: Scenario = "baseline"): Promise<WebFlight[]> {
    if (scenario === "recommended") {
      try {
        return await fetchJson<WebFlight[]>(`/data/${snapshot}/flights_recommended.json`);
      } catch {
        return fetchJson<WebFlight[]>(`/data/${snapshot}/flights_baseline.json`);
      }
    }
    return fetchJson<WebFlight[]>(`/data/${snapshot}/flights_baseline.json`);
  }

  async getSectors(snapshot: string): Promise<SectorsGeoJSON> {
    return fetchJson<SectorsGeoJSON>(`/data/${snapshot}/sectors.json`);
  }

  async getH3(snapshot: string, mode: H3Mode = "fuel", _scenario: Scenario = "baseline"): Promise<H3Cell[]> {
    return fetchJson<H3Cell[]>(`/data/${snapshot}/h3_${mode}.json`);
  }

  async getSummary(snapshot: string, _scenario: Scenario = "baseline"): Promise<Summary> {
    return fetchJson<Summary>(`/data/${snapshot}/summary.json`);
  }

  async getSectorLoad(_snapshot: string, _t: number): Promise<null> {
    return null;
  }

  async getWeather(_snapshot: string, _t: number): Promise<null> {
    return null;
  }
}

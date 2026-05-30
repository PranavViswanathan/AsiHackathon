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

export class ApiDataSource implements DataSource {
  private readonly base: string;

  constructor(base: string = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") {
    this.base = base;
  }

  async getSnapshots(): Promise<SnapshotsManifest> {
    return fetchJson<SnapshotsManifest>(`${this.base}/api/snapshots`);
  }

  async getFlights(snapshot: string, scenario: Scenario = "baseline"): Promise<WebFlight[]> {
    return fetchJson<WebFlight[]>(
      `${this.base}/api/flights?snapshot=${encodeURIComponent(snapshot)}&scenario=${scenario}`
    );
  }

  async getSectors(snapshot: string): Promise<SectorsGeoJSON> {
    return fetchJson<SectorsGeoJSON>(
      `${this.base}/api/sectors?snapshot=${encodeURIComponent(snapshot)}`
    );
  }

  async getH3(snapshot: string, mode: H3Mode = "fuel", scenario: Scenario = "baseline"): Promise<H3Cell[]> {
    return fetchJson<H3Cell[]>(
      `${this.base}/api/h3?snapshot=${encodeURIComponent(snapshot)}&mode=${mode}&scenario=${scenario}`
    );
  }

  async getSummary(snapshot: string, scenario: Scenario = "baseline"): Promise<Summary> {
    return fetchJson<Summary>(
      `${this.base}/api/summary?snapshot=${encodeURIComponent(snapshot)}&scenario=${scenario}`
    );
  }

  async getSectorLoad(snapshot: string, t: number): Promise<unknown | null> {
    return fetchJson<unknown>(
      `${this.base}/api/sector_load?snapshot=${encodeURIComponent(snapshot)}&t=${t}`
    );
  }

  async getWeather(snapshot: string, t: number): Promise<unknown | null> {
    return fetchJson<unknown>(
      `${this.base}/api/weather?snapshot=${encodeURIComponent(snapshot)}&t=${t}`
    );
  }
}

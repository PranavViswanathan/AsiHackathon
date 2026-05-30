import { StaticDataSource } from "./StaticDataSource";
import { ApiDataSource } from "./ApiDataSource";
import type { DataSource } from "./DataSource";

export function getDataSource(): DataSource {
  if (process.env.NEXT_PUBLIC_DATA_SOURCE === "api") {
    return new ApiDataSource();
  }
  return new StaticDataSource();
}

export type { DataSource } from "./DataSource";
export type {
  WebFlight,
  SectorsGeoJSON,
  SectorProperties,
  H3Cell,
  Summary,
  SnapshotsManifest,
  Scenario,
  H3Mode,
} from "./types";

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const SNAPSHOT = "asked_at_2025-05-29T21:00:00Z";

function makeFetchMock(json: unknown, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 404,
    json: () => Promise.resolve(json),
  } as unknown as Response);
}

describe("StaticDataSource URL routing", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getSnapshots fetches /data/snapshots.json", async () => {
    const manifest = { snapshots: [SNAPSHOT], showcase: SNAPSHOT };
    vi.stubGlobal("fetch", makeFetchMock(manifest));

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    const result = await ds.getSnapshots();

    expect(result).toEqual(manifest);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/data/snapshots.json");
  });

  it("getFlights(baseline) fetches flights_baseline.json", async () => {
    const flights = [{ flight_key: "ABC", flight_number: "UA1" }];
    vi.stubGlobal("fetch", makeFetchMock(flights));

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    await ds.getFlights(SNAPSHOT, "baseline");

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      `/data/${SNAPSHOT}/flights_baseline.json`
    );
  });

  it("getFlights(recommended) falls back to baseline on 404", async () => {
    const flights = [{ flight_key: "DEF" }];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404, json: () => Promise.resolve(null) } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve(flights) } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    const result = await ds.getFlights(SNAPSHOT, "recommended");

    expect(result).toEqual(flights);
    expect(fetchMock).toHaveBeenNthCalledWith(1, `/data/${SNAPSHOT}/flights_recommended.json`);
    expect(fetchMock).toHaveBeenNthCalledWith(2, `/data/${SNAPSHOT}/flights_baseline.json`);
  });

  it("getSectors fetches sectors.json", async () => {
    const sectors = { type: "FeatureCollection", features: [] };
    vi.stubGlobal("fetch", makeFetchMock(sectors));

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    await ds.getSectors(SNAPSHOT);

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(`/data/${SNAPSHOT}/sectors.json`);
  });

  it("getH3 fetches h3_fuel.json by default", async () => {
    vi.stubGlobal("fetch", makeFetchMock([]));

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    await ds.getH3(SNAPSHOT);

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(`/data/${SNAPSHOT}/h3_fuel.json`);
  });

  it("getSectorLoad returns null without fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { StaticDataSource } = await import("./StaticDataSource");
    const ds = new StaticDataSource();
    const result = await ds.getSectorLoad(SNAPSHOT, 0);

    expect(result).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("getDataSource factory", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns StaticDataSource when NEXT_PUBLIC_DATA_SOURCE is unset", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "");
    const { getDataSource } = await import("./index");
    const { StaticDataSource } = await import("./StaticDataSource");
    expect(getDataSource()).toBeInstanceOf(StaticDataSource);
  });

  it("returns ApiDataSource when NEXT_PUBLIC_DATA_SOURCE is 'api'", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "api");
    const { getDataSource } = await import("./index");
    const { ApiDataSource } = await import("./ApiDataSource");
    expect(getDataSource()).toBeInstanceOf(ApiDataSource);
  });
});

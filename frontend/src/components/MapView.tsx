"use client";

import { useEffect, useRef, useCallback } from "react";
import type { WebFlight, SectorsGeoJSON, H3Cell, H3Mode, Scenario } from "@/lib/data/types";
import { makeFuelScale } from "@/lib/fuelColor";
import { displayFuel, displayPath } from "@/lib/scenario";
import {
  type FlightTimes,
  type FlightExposure,
  type PathMetrics,
  buildPathMetrics,
  positionAt,
} from "@/lib/flightAnim";
import {
  PLANE_ICON_URL,
  PLANE_ICON_SIZE,
  RING_ICON_URL,
  RING_ICON_SIZE,
} from "@/lib/planeIcon";

type Props = {
  flights: WebFlight[];
  sectors: SectorsGeoJSON | null;
  h3Cells: H3Cell[];
  showSectors: boolean;
  showH3: boolean;
  h3Mode: H3Mode;
  fuelDomain: [number, number];
  selectedFlight: WebFlight | null;
  scenario: Scenario;
  onSelectFlight: (flight: WebFlight | null) => void;
  // Weather radar overlay
  showWeather: boolean;
  weatherBounds: [number, number, number, number] | null;
  weatherFrameUrl: string | null;
  // Aircraft animation
  showAircraft: boolean;
  flightTimes: FlightTimes | null;
  clockMs: number;
  // Show all flight routes (off = only the focused flight's route)
  showPaths: boolean;
  // Weather exposure per flight + which frame the clock is on
  flightExposure: FlightExposure | null;
  weatherFrameIndex: number;
};

const CARTO_DARK_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const INITIAL_VIEW = {
  longitude: -98,
  latitude: 39,
  zoom: 3.5,
  pitch: 0,
  bearing: 0,
};

type AnyObject = Record<string, unknown>;

type LayerContext = {
  flights: WebFlight[];
  sectors: SectorsGeoJSON | null;
  h3Cells: H3Cell[];
  showSectors: boolean;
  showH3: boolean;
  h3Mode: H3Mode;
  fuelDomain: [number, number];
  scenario: Scenario;
  onSelectFlight: (f: WebFlight | null) => void;
  showWeather: boolean;
  weatherBounds: [number, number, number, number] | null;
  weatherFrameUrl: string | null;
  showAircraft: boolean;
  flightTimes: FlightTimes | null;
  clockMs: number;
  showPaths: boolean;
  flightExposure: FlightExposure | null;
  weatherFrameIndex: number;
};

const TOOLTIP_STYLE = {
  backgroundColor: "#0b1220",
  color: "#e2e8f0",
  fontSize: "12px",
  padding: "6px 9px",
  borderRadius: "6px",
  border: "1px solid #334155",
};

function getTooltip(info: AnyObject): AnyObject | null {
  const object = info.object as AnyObject | undefined;
  const layer = info.layer as { id?: string } | undefined;
  if (!object || !layer) return null;

  if (layer.id === "sectors") {
    const p = object.properties as {
      name: string;
      capacity: number;
      peak_load: number;
      over_demand: boolean;
      altitude_from_ft: number;
      altitude_to_ft: number;
    };
    const status = p.over_demand ? "OVER DEMAND" : "within capacity";
    return {
      html: `<b>${p.name}</b><br/>Peak load: ${p.peak_load} / ${p.capacity} (${status})<br/>Altitude: ${p.altitude_from_ft.toLocaleString()}-${p.altitude_to_ft.toLocaleString()} ft`,
      style: TOOLTIP_STYLE,
    };
  }

  if (layer.id === "h3") {
    const c = object as unknown as H3Cell;
    return {
      html: `<b>Hex ${c.hex.slice(0, 8)}</b><br/>Fuel: ${Math.round(c.fuel_kg).toLocaleString()} kg<br/>Flights: ${c.n_flights}<br/>Mean: ${Math.round(c.mean_kg).toLocaleString()} kg/flight<br/>Congestion: ${(c.congestion * 100).toFixed(0)}%`,
      style: TOOLTIP_STYLE,
    };
  }

  if (layer.id === "flights") {
    const f = object as unknown as WebFlight;
    return {
      html: `<b>${f.flight_number}</b> ${f.origin} -> ${f.destination}<br/>Fuel: ${Math.round(f.fuel_kg).toLocaleString()} kg`,
      style: TOOLTIP_STYLE,
    };
  }

  if (layer.id === "aircraft") {
    const plane = object as { flight?: WebFlight; blocked?: boolean };
    const f = plane.flight;
    if (f) {
      const warn = plane.blocked
        ? `<br/><span style="color:#f87171">⚠ Flying through severe weather</span>`
        : "";
      return {
        html: `<b>${f.flight_number}</b> ${f.origin} -> ${f.destination}<br/>${f.aircraft_class} &bull; ${Math.round(f.cruise_altitude_ft).toLocaleString()} ft${warn}`,
        style: TOOLTIP_STYLE,
      };
    }
  }

  return null;
}

export default function MapView({
  flights,
  sectors,
  h3Cells,
  showSectors,
  showH3,
  h3Mode,
  fuelDomain,
  selectedFlight,
  scenario,
  onSelectFlight,
  showWeather,
  weatherBounds,
  weatherFrameUrl,
  showAircraft,
  flightTimes,
  clockMs,
  showPaths,
  flightExposure,
  weatherFrameIndex,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const deckRef = useRef<AnyObject | null>(null);
  const mapRef = useRef<AnyObject | null>(null);
  // Layer constructors cached after first import so we can rebuild layers synchronously on hover.
  const layerCtorsRef = useRef<{
    PathLayer: new (props: AnyObject) => unknown;
    GeoJsonLayer: new (props: AnyObject) => unknown;
    H3HexagonLayer: new (props: AnyObject) => unknown;
    TextLayer: new (props: AnyObject) => unknown;
    BitmapLayer: new (props: AnyObject) => unknown;
    IconLayer: new (props: AnyObject) => unknown;
  } | null>(null);
  // Cumulative path lengths per flight, cached so animation ticks stay cheap.
  const pathMetricsRef = useRef<Map<string, PathMetrics>>(new Map());
  // deck.gl/core helpers needed for the fly-to-flight behavior.
  const viewportCtorRef = useRef<(new (props: AnyObject) => { fitBounds: (b: number[][], o: AnyObject) => AnyObject }) | null>(null);
  const flyToCtorRef = useRef<(new (props: AnyObject) => unknown) | null>(null);

  // Focus state: which flight (if any) is currently hovered.
  const hoveredKeyRef = useRef<string | null>(null);
  // Which flight is currently clicked/selected (drives the airport-code labels).
  const selectedKeyRef = useRef<string | null>(null);

  // Latest-value refs so the stable layer closures can reach current callbacks.
  const refreshLayersRef = useRef<() => void>(() => {});
  const zoomToFlightRef = useRef<(f: WebFlight) => void>(() => {});
  const resetViewRef = useRef<() => void>(() => {});

  const ctxRef = useRef<LayerContext>({
    flights,
    sectors,
    h3Cells,
    showSectors,
    showH3,
    h3Mode,
    fuelDomain,
    scenario,
    onSelectFlight,
    showWeather,
    weatherBounds,
    weatherFrameUrl,
    showAircraft,
    flightTimes,
    clockMs,
    showPaths,
    flightExposure,
    weatherFrameIndex,
  });

  ctxRef.current = {
    flights,
    sectors,
    h3Cells,
    showSectors,
    showH3,
    h3Mode,
    fuelDomain,
    scenario,
    onSelectFlight,
    showWeather,
    weatherBounds,
    weatherFrameUrl,
    showAircraft,
    flightTimes,
    clockMs,
    showPaths,
    flightExposure,
    weatherFrameIndex,
  };

  const buildLayers = useCallback(
    (
      PathLayer: new (props: AnyObject) => unknown,
      GeoJsonLayer: new (props: AnyObject) => unknown,
      H3HexagonLayer: new (props: AnyObject) => unknown,
      TextLayer: new (props: AnyObject) => unknown,
      BitmapLayer: new (props: AnyObject) => unknown,
      IconLayer: new (props: AnyObject) => unknown,
      ctx: LayerContext
    ) => {
      const layers: unknown[] = [];
      const scale = makeFuelScale(ctx.fuelDomain[0], ctx.fuelDomain[1]);

      // Weather radar sits just above the basemap so flight paths, sectors and
      // hexagons all read on top of it. The image swaps per animation frame.
      if (ctx.showWeather && ctx.weatherBounds && ctx.weatherFrameUrl) {
        layers.push(
          new BitmapLayer({
            id: "weather-radar",
            bounds: ctx.weatherBounds,
            image: ctx.weatherFrameUrl,
            opacity: 0.7,
            pickable: false,
            // Smooth the coarse 256x358 grid when zoomed in.
            textureParameters: {
              minFilter: "linear",
              magFilter: "linear",
            },
          })
        );
      }

      layers.push(
        new GeoJsonLayer({
          id: "states",
          data: "/geo/us-states.json",
          stroked: true,
          filled: false,
          getLineColor: [255, 255, 255, 180],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1,
          pickable: false,
        })
      );

      if (ctx.showSectors && ctx.sectors) {
        layers.push(
          new GeoJsonLayer({
            id: "sectors",
            data: ctx.sectors,
            stroked: true,
            filled: true,
            getFillColor: (feat: AnyObject) =>
              (feat.properties as { over_demand: boolean }).over_demand
                ? [239, 68, 68, 45]
                : [59, 130, 246, 18],
            getLineColor: (feat: AnyObject) =>
              (feat.properties as { over_demand: boolean }).over_demand
                ? [239, 68, 68, 180]
                : [100, 200, 255, 110],
            getLineWidth: 1,
            lineWidthUnits: "pixels",
            lineWidthMinPixels: 1,
            pickable: true,
          })
        );
      }

      if (ctx.showH3 && ctx.h3Cells.length > 0) {
        const h3Max = ctx.h3Cells.reduce((m, c) => Math.max(m, c.value), 0) || 1;
        layers.push(
          new H3HexagonLayer({
            id: "h3",
            data: ctx.h3Cells,
            getHexagon: (d: H3Cell) => d.hex,
            getFillColor: (d: H3Cell) => {
              const ratio = Math.sqrt(Math.min(1, d.value / h3Max));
              return [255, Math.round(220 * (1 - ratio)), 30, 150];
            },
            extruded: false,
            stroked: false,
            pickable: true,
            updateTriggers: { getFillColor: [ctx.h3Mode, h3Max] },
          })
        );
      }

      // A selected (clicked) flight stays focused regardless of mouse movement;
      // otherwise hover drives the focus. Only the focused flight's route is
      // drawn — every other flight is represented solely by its moving plane.
      const selectedKey = selectedKeyRef.current;
      const focusKey = selectedKey ?? hoveredKeyRef.current;
      const focusedFlight = focusKey
        ? ctx.flights.find((f) => f.flight_key === focusKey)
        : undefined;
      // With "Paths" on, every route is drawn (thin); the focused flight is
      // brighter and a touch wider. With it off, only the focused flight's
      // route shows (hover/click).
      const pathData = ctx.showPaths
        ? ctx.flights
        : focusedFlight
        ? [focusedFlight]
        : [];
      layers.push(
        new PathLayer({
          id: "flights",
          data: pathData,
          getPath: (d: WebFlight) => displayPath(d, ctx.scenario),
          getColor: (d: WebFlight) => {
            const base = scale.toRgb(displayFuel(d, ctx.scenario));
            if (focusKey && d.flight_key === focusKey) return base;
            // Other routes (only visible when "Paths" is on) read as faint context.
            return [base[0], base[1], base[2], focusKey ? 30 : 70];
          },
          getWidth: (d: WebFlight) =>
            focusKey && d.flight_key === focusKey ? 1.6 : 0.6,
          widthUnits: "pixels",
          widthMinPixels: 0.5,
          capRounded: true,
          jointRounded: true,
          pickable: false,
          updateTriggers: {
            getPath: [ctx.scenario],
            getColor: [ctx.fuelDomain[0], ctx.fuelDomain[1], focusKey, ctx.scenario],
            getWidth: [focusKey],
          },
        })
      );

      // Animated aircraft: each flight is placed along its route by how far it
      // is between take-off and landing at the current clock time. Flights that
      // haven't departed or have already landed are dropped from the layer.
      if (ctx.showAircraft && ctx.flightTimes) {
        const metricsCache = pathMetricsRef.current;
        type Plane = {
          flight: WebFlight;
          position: [number, number];
          bearing: number;
          blocked: boolean;
        };
        const planes: Plane[] = [];
        for (const f of ctx.flights) {
          const times = ctx.flightTimes.get(f.flight_key);
          // Optimized routes have their own geometry, so animate along the path
          // for the active scenario.
          const path = displayPath(f, ctx.scenario);
          if (!times || path.length < 2) continue;
          // The optimizer can shift departure; slide the take-off/landing window.
          const shiftMs =
            ctx.scenario === "recommended"
              ? (f.opt_departure_shift_min ?? 0) * 60_000
              : 0;
          const takeoff = times.takeoff + shiftMs;
          const landing = times.landing + shiftMs;
          const frac = (ctx.clockMs - takeoff) / (landing - takeoff);
          if (frac < 0 || frac > 1) continue;

          // Cache cumulative lengths per (flight, scenario) since the geometry differs.
          const metricsKey = `${f.flight_key}:${ctx.scenario}`;
          let metrics = metricsCache.get(metricsKey);
          if (!metrics) {
            metrics = buildPathMetrics(path);
            metricsCache.set(metricsKey, metrics);
          }
          const { position, bearing } = positionAt(path, metrics, frac);
          // Is this flight flying through dangerous weather at the current frame?
          const blocked =
            ctx.flightExposure?.get(f.flight_key)?.[ctx.weatherFrameIndex] === "1";
          planes.push({ flight: f, position, bearing, blocked });
        }

        // Pulsing red halo behind any aircraft currently in severe weather.
        const blockedPlanes = planes.filter((p) => p.blocked);
        if (blockedPlanes.length > 0) {
          const pulse = 0.5 + 0.5 * Math.sin(ctx.clockMs / 400);
          layers.push(
            new IconLayer({
              id: "aircraft-warning",
              data: blockedPlanes,
              getIcon: () => ({
                url: RING_ICON_URL,
                width: RING_ICON_SIZE,
                height: RING_ICON_SIZE,
                mask: true,
              }),
              getPosition: (d: Plane) => d.position,
              getSize: 30 + 10 * pulse,
              getColor: [248, 113, 113, Math.round(140 + 90 * pulse)],
              sizeUnits: "pixels",
              pickable: false,
              updateTriggers: {
                getPosition: [ctx.clockMs, ctx.scenario],
                getSize: [ctx.clockMs],
                getColor: [ctx.clockMs],
              },
            })
          );
        }

        layers.push(
          new IconLayer({
            id: "aircraft",
            data: planes,
            getIcon: () => ({
              url: PLANE_ICON_URL,
              width: PLANE_ICON_SIZE,
              height: PLANE_ICON_SIZE,
              mask: true,
            }),
            getPosition: (d: Plane) => d.position,
            // IconLayer angle is degrees counter-clockwise; bearing is clockwise
            // from north and the glyph points north, so negate.
            getAngle: (d: Plane) => -d.bearing,
            getSize: (d: Plane) =>
              focusKey && d.flight.flight_key === focusKey ? 28 : 18,
            getColor: (d: Plane) => {
              // Aircraft in severe weather are flagged bright red regardless of fuel.
              const base: [number, number, number] = d.blocked
                ? [248, 113, 113]
                : (scale.toRgb(displayFuel(d.flight, ctx.scenario)) as unknown as [
                    number,
                    number,
                    number
                  ]);
              // Once a flight is selected, fade the rest so it stands out.
              if (selectedKey && d.flight.flight_key !== selectedKey) {
                return [base[0], base[1], base[2], 55];
              }
              return [base[0], base[1], base[2], 235];
            },
            sizeUnits: "pixels",
            pickable: true,
            updateTriggers: {
              getPosition: [ctx.clockMs, ctx.scenario],
              getAngle: [ctx.clockMs, ctx.scenario],
              getColor: [
                selectedKey,
                ctx.scenario,
                ctx.fuelDomain[0],
                ctx.fuelDomain[1],
                ctx.weatherFrameIndex,
              ],
              getSize: [focusKey],
            },
            onClick: (info: AnyObject) => {
              const plane = info.object as Plane | undefined;
              const obj = plane ? plane.flight : null;
              selectedKeyRef.current = obj ? obj.flight_key : null;
              ctx.onSelectFlight(obj);
              refreshLayersRef.current();
              if (obj) zoomToFlightRef.current(obj);
            },
            onHover: (info: AnyObject) => {
              // While a flight is selected it stays focused — ignore hover.
              if (selectedKeyRef.current !== null) return;
              // Hovering a plane reveals its route (no camera movement).
              const plane = info.object as Plane | undefined;
              const newKey = plane ? plane.flight.flight_key : null;
              if (newKey === hoveredKeyRef.current) return;
              hoveredKeyRef.current = newKey;
              refreshLayersRef.current();
            },
          })
        );
      }

      // Airport-code labels at the endpoints of the selected flight's path.
      const selectedFlight = selectedKey
        ? ctx.flights.find((f) => f.flight_key === selectedKey)
        : undefined;
      const selectedPath = selectedFlight
        ? displayPath(selectedFlight, ctx.scenario)
        : [];
      if (selectedFlight && selectedPath.length > 0) {
        const path = selectedPath;
        const labels = [
          { position: path[0], text: selectedFlight.origin },
          { position: path[path.length - 1], text: selectedFlight.destination },
        ];
        layers.push(
          new TextLayer({
            id: "flight-endpoints",
            data: labels,
            getPosition: (d: { position: [number, number] }) => d.position,
            getText: (d: { text: string }) => d.text,
            getSize: 15,
            sizeUnits: "pixels",
            getColor: [255, 255, 255, 255],
            getPixelOffset: [0, -14],
            fontWeight: 700,
            background: true,
            getBackgroundColor: [11, 18, 32, 220],
            backgroundPadding: [5, 3],
            getBorderColor: [51, 65, 85, 255],
            getBorderWidth: 1,
            outlineColor: [0, 0, 0, 255],
            outlineWidth: 2,
            pickable: false,
            updateTriggers: { getText: [selectedKey], getPosition: [selectedKey] },
          })
        );
      }

      return layers;
    },
    []
  );

  // Rebuild and push layers synchronously (used by hover so the subdue is instant).
  const refreshLayers = useCallback(() => {
    const deck = deckRef.current;
    const ctors = layerCtorsRef.current;
    if (!deck || !ctors) return;
    const layers = buildLayers(
      ctors.PathLayer,
      ctors.GeoJsonLayer,
      ctors.H3HexagonLayer,
      ctors.TextLayer,
      ctors.BitmapLayer,
      ctors.IconLayer,
      ctxRef.current
    );
    (deck as { setProps: (props: AnyObject) => void }).setProps({ layers });
  }, [buildLayers]);

  // Fly the camera so the hovered flight's full path fits in view.
  const zoomToFlight = useCallback((flight: WebFlight) => {
    const deck = deckRef.current;
    const Viewport = viewportCtorRef.current;
    const FlyTo = flyToCtorRef.current;
    const container = containerRef.current;
    const path = displayPath(flight, ctxRef.current.scenario);
    if (!deck || !Viewport || !FlyTo || !container || path.length === 0) return;

    let minLon = Infinity;
    let minLat = Infinity;
    let maxLon = -Infinity;
    let maxLat = -Infinity;
    for (const [lon, lat] of path) {
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    let target: AnyObject;
    try {
      target = new Viewport({ width, height }).fitBounds(
        [
          [minLon, minLat],
          [maxLon, maxLat],
        ],
        { padding: 90, maxZoom: 9 }
      );
    } catch {
      return;
    }

    const zoom = target.zoom as number;
    if (!Number.isFinite(zoom)) return;

    (deck as { setProps: (props: AnyObject) => void }).setProps({
      initialViewState: {
        longitude: target.longitude as number,
        latitude: target.latitude as number,
        zoom: Math.min(zoom, 9),
        pitch: 0,
        bearing: 0,
        transitionDuration: 700,
        transitionInterpolator: new (FlyTo as new (props: AnyObject) => unknown)({ speed: 1.4 }),
      },
    });
  }, []);

  // Fly the camera back to the original full-map view.
  const resetView = useCallback(() => {
    const deck = deckRef.current;
    const FlyTo = flyToCtorRef.current;
    if (!deck || !FlyTo) return;
    (deck as { setProps: (props: AnyObject) => void }).setProps({
      initialViewState: {
        ...INITIAL_VIEW,
        transitionDuration: 700,
        transitionInterpolator: new (FlyTo as new (props: AnyObject) => unknown)({ speed: 1.4 }),
      },
    });
  }, []);

  // Keep latest-value refs in sync for the stable layer closures.
  refreshLayersRef.current = refreshLayers;
  zoomToFlightRef.current = zoomToFlight;
  resetViewRef.current = resetView;

  // React to selection driven from outside the map (e.g. the search box): focus
  // the flight, redraw, and zoom to frame it — or reset the view when cleared.
  useEffect(() => {
    const key = selectedFlight ? selectedFlight.flight_key : null;
    if (key === selectedKeyRef.current) return;
    selectedKeyRef.current = key;
    hoveredKeyRef.current = null;
    refreshLayers();
    if (selectedFlight) {
      zoomToFlight(selectedFlight);
    } else {
      resetView();
    }
  }, [selectedFlight, refreshLayers, zoomToFlight, resetView]);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (!containerRef.current) return;

      const [
        { Deck, WebMercatorViewport, FlyToInterpolator },
        { PathLayer, GeoJsonLayer, TextLayer, BitmapLayer, IconLayer },
        { H3HexagonLayer },
        maplibregl,
      ] = await Promise.all([
        import("@deck.gl/core"),
        import("@deck.gl/layers"),
        import("@deck.gl/geo-layers"),
        import("maplibre-gl"),
      ]);

      if (cancelled || !containerRef.current) return;

      layerCtorsRef.current = {
        PathLayer: PathLayer as unknown as new (props: AnyObject) => unknown,
        GeoJsonLayer: GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
        H3HexagonLayer: H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
        TextLayer: TextLayer as unknown as new (props: AnyObject) => unknown,
        BitmapLayer: BitmapLayer as unknown as new (props: AnyObject) => unknown,
        IconLayer: IconLayer as unknown as new (props: AnyObject) => unknown,
      };
      viewportCtorRef.current = WebMercatorViewport as unknown as new (
        props: AnyObject
      ) => { fitBounds: (b: number[][], o: AnyObject) => AnyObject };
      flyToCtorRef.current = FlyToInterpolator as unknown as new (props: AnyObject) => unknown;

      const container = containerRef.current;
      const mapContainer = document.createElement("div");
      mapContainer.style.position = "absolute";
      mapContainer.style.inset = "0";
      container.appendChild(mapContainer);

      const map = new maplibregl.Map({
        container: mapContainer,
        style: CARTO_DARK_STYLE,
        center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
        zoom: INITIAL_VIEW.zoom,
        interactive: false,
      });

      mapRef.current = map as unknown as AnyObject;

      const DeckCtor = Deck as unknown as new (props: AnyObject) => AnyObject;
      const deck = new DeckCtor({
        parent: container,
        initialViewState: INITIAL_VIEW,
        controller: true,
        getTooltip,
        // Clicking empty space (no flight picked) clears the selection + labels.
        onClick: (info: AnyObject) => {
          if (info.object) return;
          if (selectedKeyRef.current === null) return;
          selectedKeyRef.current = null;
          hoveredKeyRef.current = null;
          ctxRef.current.onSelectFlight(null);
          refreshLayersRef.current();
          // Zoom back out to the original full-map view.
          resetViewRef.current();
        },
        layers: buildLayers(
          PathLayer as unknown as new (props: AnyObject) => unknown,
          GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
          H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
          TextLayer as unknown as new (props: AnyObject) => unknown,
          BitmapLayer as unknown as new (props: AnyObject) => unknown,
          IconLayer as unknown as new (props: AnyObject) => unknown,
          ctxRef.current
        ),
        onViewStateChange: (params: AnyObject) => {
          const vs = params.viewState as AnyObject;
          map.jumpTo({
            center: [vs.longitude as number, vs.latitude as number],
            zoom: vs.zoom as number,
            bearing: (vs.bearing as number | undefined) ?? 0,
            pitch: (vs.pitch as number | undefined) ?? 0,
          });
        },
        style: { position: "absolute", inset: "0", zIndex: 1 },
      });

      deckRef.current = deck as unknown as AnyObject;
    }

    init();

    return () => {
      cancelled = true;
      if (deckRef.current) {
        (deckRef.current as { finalize: () => void }).finalize();
        deckRef.current = null;
      }
      if (mapRef.current) {
        (mapRef.current as { remove: () => void }).remove();
        mapRef.current = null;
      }
    };
  }, [buildLayers]);

  useEffect(() => {
    if (!deckRef.current) return;

    async function updateLayers() {
      const [{ PathLayer, GeoJsonLayer, TextLayer, BitmapLayer, IconLayer }, { H3HexagonLayer }] = await Promise.all([
        import("@deck.gl/layers"),
        import("@deck.gl/geo-layers"),
      ]);

      if (!deckRef.current) return;

      const layers = buildLayers(
        PathLayer as unknown as new (props: AnyObject) => unknown,
        GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
        H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
        TextLayer as unknown as new (props: AnyObject) => unknown,
        BitmapLayer as unknown as new (props: AnyObject) => unknown,
        IconLayer as unknown as new (props: AnyObject) => unknown,
        ctxRef.current
      );

      (deckRef.current as { setProps: (props: AnyObject) => void }).setProps({ layers });
    }

    updateLayers();
  }, [
    flights,
    sectors,
    h3Cells,
    showSectors,
    showH3,
    h3Mode,
    fuelDomain,
    scenario,
    showWeather,
    weatherBounds,
    showAircraft,
    flightTimes,
    showPaths,
    flightExposure,
    buildLayers,
  ]);

  // Clock ticks drive aircraft + the weather frame at high frequency, so they
  // go through the synchronous cached-constructor path (no dynamic import per
  // frame) rather than the async layer-update effect above.
  useEffect(() => {
    refreshLayers();
  }, [clockMs, weatherFrameUrl, refreshLayers]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full"
      style={{ position: "relative" }}
    />
  );
}

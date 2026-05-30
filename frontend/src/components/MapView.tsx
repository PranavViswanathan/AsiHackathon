"use client";

import { useEffect, useRef, useCallback } from "react";
import type { WebFlight, SectorsGeoJSON, H3Cell, H3Mode } from "@/lib/data/types";
import { makeFuelScale } from "@/lib/fuelColor";

type Props = {
  flights: WebFlight[];
  sectors: SectorsGeoJSON | null;
  h3Cells: H3Cell[];
  showSectors: boolean;
  showH3: boolean;
  h3Mode: H3Mode;
  fuelDomain: [number, number];
  onSelectFlight: (flight: WebFlight | null) => void;
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
  onSelectFlight: (f: WebFlight | null) => void;
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
  onSelectFlight,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const deckRef = useRef<AnyObject | null>(null);
  const mapRef = useRef<AnyObject | null>(null);
  const ctxRef = useRef<LayerContext>({
    flights,
    sectors,
    h3Cells,
    showSectors,
    showH3,
    h3Mode,
    fuelDomain,
    onSelectFlight,
  });

  ctxRef.current = { flights, sectors, h3Cells, showSectors, showH3, h3Mode, fuelDomain, onSelectFlight };

  const buildLayers = useCallback(
    (
      PathLayer: new (props: AnyObject) => unknown,
      GeoJsonLayer: new (props: AnyObject) => unknown,
      H3HexagonLayer: new (props: AnyObject) => unknown,
      ctx: LayerContext
    ) => {
      const layers: unknown[] = [];
      const scale = makeFuelScale(ctx.fuelDomain[0], ctx.fuelDomain[1]);

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

      layers.push(
        new PathLayer({
          id: "flights",
          data: ctx.flights,
          getPath: (d: WebFlight) => d.path,
          getColor: (d: WebFlight) => scale.toRgb(d.fuel_kg),
          getWidth: 2.5,
          widthUnits: "pixels",
          widthMinPixels: 2,
          capRounded: true,
          jointRounded: true,
          pickable: true,
          updateTriggers: { getColor: [ctx.fuelDomain[0], ctx.fuelDomain[1]] },
          onClick: (info: AnyObject) => {
            ctx.onSelectFlight((info.object as WebFlight | undefined) ?? null);
          },
        })
      );

      return layers;
    },
    []
  );

  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (!containerRef.current) return;

      const [{ Deck }, { PathLayer, GeoJsonLayer }, { H3HexagonLayer }, maplibregl] =
        await Promise.all([
          import("@deck.gl/core"),
          import("@deck.gl/layers"),
          import("@deck.gl/geo-layers"),
          import("maplibre-gl"),
        ]);

      if (cancelled || !containerRef.current) return;

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
        layers: buildLayers(
          PathLayer as unknown as new (props: AnyObject) => unknown,
          GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
          H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
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
      const [{ PathLayer, GeoJsonLayer }, { H3HexagonLayer }] = await Promise.all([
        import("@deck.gl/layers"),
        import("@deck.gl/geo-layers"),
      ]);

      if (!deckRef.current) return;

      const layers = buildLayers(
        PathLayer as unknown as new (props: AnyObject) => unknown,
        GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
        H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
        ctxRef.current
      );

      (deckRef.current as { setProps: (props: AnyObject) => void }).setProps({ layers });
    }

    updateLayers();
  }, [flights, sectors, h3Cells, showSectors, showH3, h3Mode, fuelDomain, buildLayers]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full"
      style={{ position: "relative" }}
    />
  );
}

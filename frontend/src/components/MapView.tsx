"use client";

import { useEffect, useRef, useCallback } from "react";
import type { WebFlight, SectorsGeoJSON, H3Cell } from "@/lib/data/types";
import { fuelToRgb } from "@/lib/fuelColor";

type Props = {
  flights: WebFlight[];
  sectors: SectorsGeoJSON | null;
  h3Cells: H3Cell[];
  showSectors: boolean;
  showH3: boolean;
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

export default function MapView({
  flights,
  sectors,
  h3Cells,
  showSectors,
  showH3,
  onSelectFlight,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const deckRef = useRef<AnyObject | null>(null);
  const mapRef = useRef<AnyObject | null>(null);
  const layersRef = useRef({ flights, sectors, h3Cells, showSectors, showH3, onSelectFlight });

  layersRef.current = { flights, sectors, h3Cells, showSectors, showH3, onSelectFlight };

  const buildLayers = useCallback(
    (
      PathLayer: new (props: AnyObject) => unknown,
      GeoJsonLayer: new (props: AnyObject) => unknown,
      H3HexagonLayer: new (props: AnyObject) => unknown,
      currentFlights: WebFlight[],
      currentSectors: SectorsGeoJSON | null,
      currentH3: H3Cell[],
      currentShowSectors: boolean,
      currentShowH3: boolean,
      selectFn: (f: WebFlight | null) => void
    ) => {
      const layers: unknown[] = [];

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

      layers.push(
        new PathLayer({
          id: "flights",
          data: currentFlights,
          getPath: (d: WebFlight) => d.path,
          getColor: (d: WebFlight) => fuelToRgb(d.fuel_kg),
          getWidth: 2.5,
          widthUnits: "pixels",
          widthMinPixels: 2,
          capRounded: true,
          jointRounded: true,
          pickable: true,
          onClick: (info: AnyObject) => {
            selectFn((info.object as WebFlight | undefined) ?? null);
          },
        })
      );

      if (currentShowSectors && currentSectors) {
        layers.push(
          new GeoJsonLayer({
            id: "sectors",
            data: currentSectors,
            stroked: true,
            filled: false,
            getLineColor: [100, 200, 255, 120],
            getLineWidth: 1,
            lineWidthMinPixels: 1,
            pickable: false,
          })
        );
      }

      if (currentShowH3 && currentH3.length > 0) {
        layers.push(
          new H3HexagonLayer({
            id: "h3",
            data: currentH3,
            getHexagon: (d: H3Cell) => d.hex,
            getFillColor: (d: H3Cell) => [255, Math.max(0, 255 - d.value * 10), 0, 180],
            extruded: false,
            pickable: false,
          })
        );
      }

      return layers;
    },
    []
  );

  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (!containerRef.current) return;

      const [
        { Deck },
        { PathLayer, GeoJsonLayer },
        { H3HexagonLayer },
        maplibregl,
      ] = await Promise.all([
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

      const { flights: f, sectors: s, h3Cells: h, showSectors: ss, showH3: sh, onSelectFlight: sel } =
        layersRef.current;

      const DeckCtor = Deck as unknown as new (props: AnyObject) => AnyObject;
      const deck = new DeckCtor({
        parent: container,
        initialViewState: INITIAL_VIEW,
        controller: true,
        layers: buildLayers(
          PathLayer as unknown as new (props: AnyObject) => unknown,
          GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
          H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
          f, s, h, ss, sh, sel
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

      const { flights: f, sectors: s, h3Cells: h, showSectors: ss, showH3: sh, onSelectFlight: sel } =
        layersRef.current;

      const layers = buildLayers(
        PathLayer as unknown as new (props: AnyObject) => unknown,
        GeoJsonLayer as unknown as new (props: AnyObject) => unknown,
        H3HexagonLayer as unknown as new (props: AnyObject) => unknown,
        f, s, h, ss, sh, sel
      );

      (deckRef.current as { setProps: (props: AnyObject) => void }).setProps({ layers });
    }

    updateLayers();
  }, [flights, sectors, h3Cells, showSectors, showH3, buildLayers]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full"
      style={{ position: "relative" }}
    />
  );
}

"""Map (lat, lon, altitude) points to the airspace sector that contains them.

Sectors partition CONUS into two altitude bands (LOW [0, 35k), HIGH [35k, 60k)),
gap-free and non-overlapping within a band. So a point belongs to exactly one
sector per band. We keep a separate spatial index (shapely STRtree) per band and
query the band a flight actually cruises in.
"""

from __future__ import annotations

import numpy as np
from shapely import STRtree, points as make_points
from shapely.geometry import shape

BANDS = ("LOW", "HIGH")


class SectorIndex:
    """Spatial index over the sector polygons, one STRtree per altitude band.

    >>> idx = SectorIndex(load_sectors())
    >>> idx.assign(np.array([47.45]), np.array([-122.30]), "HIGH")
    array(['HIGH_...'], dtype=object)
    """

    def __init__(self, geojson: dict):
        self._names: dict[str, np.ndarray] = {}
        self._caps: dict[str, np.ndarray] = {}
        self._trees: dict[str, STRtree] = {}
        self.capacity: dict[str, int] = {}   # sector name -> capacity, for convenience

        for band in BANDS:
            geoms, names, caps = [], [], []
            for f in geojson["features"]:
                props = f["properties"]
                if not props["name"].startswith(band + "_"):
                    continue
                geoms.append(shape(f["geometry"]))
                names.append(props["name"])
                caps.append(int(props["capacity"]))
                self.capacity[props["name"]] = int(props["capacity"])
            self._trees[band] = STRtree(geoms)
            self._names[band] = np.asarray(names, dtype=object)
            self._caps[band] = np.asarray(caps, dtype=int)

    def assign(self, lats: np.ndarray, lons: np.ndarray, band: str) -> np.ndarray:
        """Sector name for each (lat, lon) within the given band.

        Returns an object array aligned with the inputs; entries are ``None`` for
        points outside CONUS coverage (e.g. flights momentarily off the grid).
        """
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        out = np.full(lats.shape, None, dtype=object)
        if lats.size == 0:
            return out

        pts = make_points(lons, lats)  # GeoJSON / shapely order is (x=lon, y=lat)
        tree = self._trees[band]
        # NB: STRtree evaluates the predicate as input_geom.predicate(tree_geom), so to
        # find the sector a point falls in we ask point.intersects(sector) (not
        # sector.contains(point)). 'intersects' also matches boundary points; on a
        # shared sector edge a point can match two sectors, and the later write below
        # wins as an arbitrary (harmless) tie-break — each point still gets one sector.
        input_idx, tree_idx = tree.query(pts, predicate="intersects")
        out[input_idx] = self._names[band][tree_idx]
        return out

    def assign_flight_positions(self, flights, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Sector name for a batch of positioned flights, routing each to its band.

        ``flights`` is parallel to ``lats``/``lons``; each flight's ``band`` selects
        which band's index it is queried against.
        """
        out = np.full(len(flights), None, dtype=object)
        bands = np.array([f.band for f in flights])
        for band in BANDS:
            mask = bands == band
            if mask.any():
                out[mask] = self.assign(lats[mask], lons[mask], band)
        return out

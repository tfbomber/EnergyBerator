"""
core/plz_lookup.py
====================
Generic spatial PLZ lookup over a city's PLZ boundary polygon GeoJSON
(config/boundaries/<city>_plz_boundaries.geojson).

Originally written Leipzig-only (core/leipzig_plz_lookup.py, KI-012 follow-up,
.ai/implementation_plan_leipzig_plz_spatial.md D1/D2/D6) and generalized once
Augsburg needed the identical fix (P3) — reusing the class rather than
duplicating the STRtree/tie-break logic per city.

Used by BOTH a city's `generate_<city>_buildings.py` and
`generate_<city>_osm_clusters.py` so the two independent building-extraction
passes apply IDENTICAL point-in-polygon fallback logic for buildings missing
addr:postcode. A city's cluster-generation script does its own separate PBF
pass with the same untagged-postcode gap, feeding Foundation's cluster list
directly (Foundation resolves a cluster's PLZ from the cluster's OWN
segment_id, not the buildings parquet) — both extractors must use the SAME
lookup so a building's PLZ assignment can never diverge between them.
"""

import json
import os

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PlzLookup:
    """Point-in-polygon lookup across a city's registered PLZ polygons."""

    def __init__(self, geojson_path: str, expected_count: int | None = None):
        with open(geojson_path, encoding="utf-8") as f:
            data = json.load(f)

        self._geoms = []
        self._plzs = []
        for feat in data["features"]:
            self._geoms.append(shape(feat["geometry"]))
            self._plzs.append(feat["properties"]["plz"])

        if expected_count is not None and len(self._geoms) != expected_count:
            raise ValueError(
                f"[PlzLookup] Expected {expected_count} PLZ polygons, found "
                f"{len(self._geoms)} in {geojson_path}. Aborting — do not "
                f"silently run spatial fallback against incomplete PLZ coverage."
            )

        self._tree = STRtree(self._geoms)

    def lookup(self, lon: float, lat: float) -> str | None:
        """
        Return the PLZ whose polygon contains (lon, lat), or None if the
        point falls outside all registered PLZ polygons (true noise — e.g.
        a boundary-edge building actually outside the city's PLZ set).

        Tie-break (a centroid landing on a shared PLZ seam): if more than
        one polygon claims the point, pick the polygon whose centroid is
        nearest the point. Deterministic, not dependent on iteration/
        insertion order.
        """
        pt = Point(lon, lat)
        candidate_idxs = self._tree.query(pt)
        hits = [i for i in candidate_idxs if self._geoms[i].contains(pt)]

        if not hits:
            return None
        if len(hits) == 1:
            return self._plzs[hits[0]]

        best = min(hits, key=lambda i: self._geoms[i].centroid.distance(pt))
        return self._plzs[best]


class LeipzigPlzLookup(PlzLookup):
    """Leipzig-specific convenience wrapper (34 PLZ)."""

    _DEFAULT_PATH = os.path.join(
        _BASE_DIR, "config", "boundaries", "leipzig_plz_boundaries.geojson"
    )

    def __init__(self, path: str = _DEFAULT_PATH):
        super().__init__(path, expected_count=34)

"""
generate_foundation_layer.py
============================
PHASE 13 — Foundation Layer: Residential Structure Filter

SCOPE: OFFLINE DATA PIPELINE ONLY.
Do NOT modify any existing pipeline output.
Do NOT alter any UI components.
Do NOT run any scoring logic.

Input:
    output/clusters/neuss_hybrid_clusters_v1.json

Output:
    output/foundation/foundation_structure_results.json

This script:
1. Loads the validated MVP cluster list to get target streets.
2. Queries Overpass API for raw building tags within the Neuss bounding box.
3. Aggregates per-cluster counts for: Detached, Semi-Detached, Rowhouse, MFH, Other.
4. Computes ratios and Structure Profile.
5. Applies the MFH Exclusion Gate (PASS / REVIEW / FAIL).
6. Outputs the exact required schema as JSON.

GATE THRESHOLDS (from specification):
    MIN_CLUSTER_SIZE = 15
    PASS_MAX_MFH_RATIO = 0.25
    PASS_MIN_SFH_RATIO = 0.50
    REVIEW_MAX_MFH_RATIO = 0.40

NOTE: No scoring, no commercial logic, no action labels in this file.
"""

import os
import sys
import json
import logging
import requests



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FoundationLayer")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Enhancement C: imported after sys.path ensures scripts/ is resolvable
# regardless of whether this module is run directly or imported by tests.
# METADATA-ONLY: do not use street_confidence in gate/ranking logic.
from foundation_confidence import compute_street_confidence  # noqa: E402

# Layer 1.5: Explanation / Sales Translation Layer
# METADATA-ONLY: do not use explanation fields in gate/ranking/scoring logic.
from foundation_explainer import generate_explanation  # noqa: E402

# ROOT FIX (2026-07-13, KI-012): street-level SFH/MFH type counts and the
# gate/profile derived from them now come from core/street_building_types.py
# (field_02 as classification source of truth, keyed by real (street, plz))
# instead of this script's own bbox-extraction + classify_building_tag /
# correct_house_tags_by_adjacency / rescue_other_by_geometry. See that
# module's docstring for the full root-cause writeup. apply_structure_gate /
# classify_structure_profile / the gate threshold constants moved there too
# (re-imported here so `from scripts.generate_foundation_layer import
# apply_structure_gate` etc. — e.g. tests/test_foundation_gate_phase15.py —
# keeps working unchanged) — semantics UNCHANGED, only relocated.
sys.path.insert(0, os.path.dirname(_SCRIPTS_DIR))  # repo root, for core/
from core.street_building_types import (  # noqa: E402
    compute_street_type_counts,
    apply_structure_gate,
    classify_structure_profile,
    PASS_MAX_MFH_RATIO,
    PASS_MIN_SFH_RATIO,
    REVIEW_MAX_MFH_RATIO,
    QUALIFIED_OTHER_THRESHOLD,
    QUALIFIED_MIN_SFH_RATIO,
)

# ---------------------------------------------------------------------------
# ROOT FIX rollout gate (KI-012): the field_02-based path is only used for
# cities that have gone through their own P2-style validation (diff report +
# satellite/Overpass spot-check reviewed by a human — see
# territoryai/.ai/implementation_plan_foundation_classifier.md P2/P3). Other
# cities keep using the legacy Foundation-native classification (below,
# classify_building_tag / correct_house_tags_by_adjacency /
# rescue_other_by_geometry) UNCHANGED until their own sign-off — this is a
# deliberate phased rollout, not a leftover shim: touching Neuss/Kaarst/
# Augsburg's shipped rankings is a separate, explicitly gated decision (D2).
#
# Augsburg promoted 2026-07-14 (territoryai
# .ai/implementation_plan_augsburg_ki012_promotion.md) after quantifying the
# legacy path's cross-town contamination for Augsburg: 42.4% of Foundation's
# raw bbox-extracted buildings fall outside the real Augsburg boundary
# polygon, and 26.9% (210/780) of CURRENTLY ACTIVE PASS/QUALIFIED streets
# shared a name with contaminated data — several even carrying a PLZ
# entirely outside Augsburg's real 14-PLZ set (86482, 86343, 86420, 86399,
# 86391, 86356, 86368 — genuinely different towns). Sample-verified before
# flipping this: of the 112 streets that vanish under the new path, 111
# (99%) carry one of those foreign PLZ codes — confirmed contamination
# correctly removed, not real Augsburg data lost; the 299 "new" streets are
# overwhelmingly the SAME real Augsburg street names correctly relocated
# from their contaminated foreign-PLZ legacy entry to their true PLZ (not
# spurious new entries); known cross-PLZ collapse case August-Wessels-Straße
# now correctly splits into its 2 real portions (86154 n=11, 86156 n=4;
# legacy path merged/hid the 86156 portion), same class of fix as Leipzig's
# Karl-Liebknecht-Straße.
#
# Neuss promoted 2026-07-14 (territoryai
# .ai/implementation_plan_neuss_foundation_ki012.md), same session. Quantified
# cross-town contamination first: 38.1% of Foundation's raw bbox-extracted
# buildings fall outside the real Neuss boundary polygon (743 contaminated
# street names) — the ALREADY-SHIPPED foundation_structure_results.json had
# outright foreign-town PLZ records live in it (40219/40221/40223/40545/
# 40547/40549/40667 = Düsseldorf, 41516 = Grevenbroich, 41564 = Kaarst).
# Blocked by a real geometry gap unique to Neuss (D6 in the plan): PLZ 41470
# had ONLY POINT geometry (a 2026-04-12 legacy Overpass recovery, no polygon
# in the source geojson snapshot), so field_02's Stage 2 footprint
# classifier could never run on it — 74.4% UNCERTAIN vs ~3-8% for the other
# 7 (POLYGON) PLZ. Fixed surgically (D1): a new targeted extractor,
# scripts/extract_neuss_41470_polygons.py, pulls real POLYGON geometry for
# 41470 directly from the PBF (same source data/osm/duesseldorf-regbez-
# latest.osm.pbf the other 7 PLZ's original geojson snapshot came from),
# swapped in via scripts/swap_neuss_41470_polygons.py — the other 7 PLZ
# untouched. Confirmed the fix: 41470's field_02 UNCERTAIN rate dropped
# 74.4%->2.3% once it had real polygons to classify against.
_FIELD02_VALIDATED_CITIES = {"leipzig", "augsburg", "neuss"}

# Per-city buildings parquet path + a filter to exclude the "noise" bucket
# (unregistered-PLZ / stray neighbor-municipality buildings — see each
# city's own generate_<city>_buildings.py). Only entries for
# _FIELD02_VALIDATED_CITIES are required right now; add a city's entry here
# when it's promoted into that set (P3).
_CITY_BUILDINGS_PARQUET = {
    "leipzig": os.path.join(BASE_DIR, "data", "leipzig_buildings.parquet"),
    "augsburg": os.path.join(BASE_DIR, "data", "augsburg_buildings.parquet"),
    # Neuss's buildings live in the shared (not per-city-suffixed)
    # data/buildings.parquet — it has no "_GENERAL" noise segment the way
    # Leipzig/Augsburg do, but it DOES hold 5 non-8-PLZ pilot segments
    # (ALLERHEILIGEN_PILOT_SEG_01, NEUSS_DENSE_01, NEUSS_OLD_TOWN_01,
    # NEUSS_SUBURBAN_01, NEUSS_VILLA_01 — 931 rows) that must be excluded
    # the same way merge_building_geometry_into_territoryai.py's own
    # NEUSS_PLZ* filter does. See _CITY_SEGMENT_PREFIX_FILTER below.
    "neuss": os.path.join(BASE_DIR, "data", "buildings.parquet"),
}
_FIELD02_PARQUET = os.path.join(BASE_DIR, "data", "fields", "field_02_building_type.parquet")

# Cities whose buildings parquet holds OTHER segments beyond the real
# registered PLZ set that the generic "_GENERAL" suffix filter doesn't
# catch (Neuss's 5 pilot segments don't end in "_GENERAL"). Maps city_key
# -> the required segment_id prefix; only registered-PLZ rows pass.
_CITY_SEGMENT_PREFIX_FILTER = {
    "neuss": "NEUSS_PLZ",
}


def _load_field02_street_counts(city_key: str) -> "dict[tuple[str, str], dict] | None":
    """
    Load `<city>_buildings.parquet` + field_02_building_type.parquet and
    compute field_02-based street-level type counts (KI-012 root fix).
    Returns None (triggering the legacy path) if city_key isn't in
    _FIELD02_VALIDATED_CITIES yet, or if either input file is missing.
    """
    if city_key not in _FIELD02_VALIDATED_CITIES:
        return None

    buildings_path = _CITY_BUILDINGS_PARQUET.get(city_key)
    if not buildings_path or not os.path.exists(buildings_path):
        logger.warning(
            f"[STREET_BUILDING_TYPES] {city_key}: buildings parquet not found "
            f"({buildings_path}) — falling back to legacy classification path."
        )
        return None
    if not os.path.exists(_FIELD02_PARQUET):
        logger.warning(
            f"[STREET_BUILDING_TYPES] field_02 parquet not found ({_FIELD02_PARQUET}) "
            f"— falling back to legacy classification path."
        )
        return None

    import pandas as pd

    buildings_df = pd.read_parquet(buildings_path)
    # Exclude the unregistered-PLZ / stray-neighbor-municipality noise
    # bucket — these buildings can't be attributed to a real named street
    # in this city anyway (same convention as merge_building_geometry_
    # into_territoryai.py's per-city filters).
    buildings_df = buildings_df[
        ~buildings_df["segment_id"].astype(str).str.endswith("_GENERAL")
    ]
    # Some cities' buildings parquet holds additional non-registered
    # segments the "_GENERAL" suffix filter above doesn't catch (e.g.
    # Neuss's 5 pilot segments, out of scope for KI-012 / TC-033).
    required_prefix = _CITY_SEGMENT_PREFIX_FILTER.get(city_key)
    if required_prefix:
        before = len(buildings_df)
        buildings_df = buildings_df[
            buildings_df["segment_id"].astype(str).str.startswith(required_prefix)
        ]
        logger.info(
            f"[STREET_BUILDING_TYPES] {city_key}: segment-prefix filter "
            f"'{required_prefix}*' — {before} -> {len(buildings_df)} buildings "
            f"({before - len(buildings_df)} non-registered-segment rows excluded)."
        )
    field02_df = pd.read_parquet(_FIELD02_PARQUET, columns=["building_id", "field_value"])

    logger.info(
        f"[STREET_BUILDING_TYPES] {city_key}: using field_02-based street type "
        f"counts (KI-012 root fix) — {len(buildings_df)} buildings, real "
        f"(street, plz) keys, not Foundation's own bbox-extraction/classifier."
    )
    return compute_street_type_counts(buildings_df, field02_df)


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

# Neuss bounding box: lat 51.13 to 51.25, lon 6.61 to 6.77
NEUSS_BBOX = "(51.13, 6.61, 51.25, 6.77)"

# ---------------------------------------------------------------------------
# OSM PBF Data Source Registry
# ---------------------------------------------------------------------------
# Primary data source: local Geofabrik PBF extract.
# This eliminates the dependency on public Overpass API for pipeline runs.
# Update cadence: once per year is sufficient (OSM building data changes slowly).
#
# To add a new city:
#   1. Download the relevant PBF from https://download.geofabrik.de/europe/germany/
#   2. Add an entry to OSM_PBF_REGISTRY with the city's bounding box
#   3. Pass city_key to fetch_buildings() in main()
#
# bbox format: (lon_min, lat_min, lon_max, lat_max)
OSM_PBF_REGISTRY = {
    "neuss": {
        "pbf": os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf"),
        "bbox": (6.61, 51.13, 6.77, 51.25),   # lon_min, lat_min, lon_max, lat_max
        "description": "Neuss (Rhein-Kreis Neuss, PLZ 41460-41472)",
    },
    "kaarst": {
        "pbf": os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf"),
        "bbox": (6.55, 51.19, 6.68, 51.27),
        "description": "Kaarst (Rhein-Kreis Neuss, PLZ 41564)",
    },
    "duesseldorf": {
        "pbf": os.path.join(BASE_DIR, "data", "osm", "duesseldorf-regbez-latest.osm.pbf"),
        "bbox": (6.68, 51.10, 6.95, 51.35),   # Düsseldorf city bbox (future)
        "description": "Düsseldorf (PLZ 40xxx)",
    },
    "augsburg": {
        "pbf": os.path.join(BASE_DIR, "data", "osm", "schwaben-latest.osm.pbf"),
        # bbox computed from Nominatim relation/62407 (Augsburg city proper,
        # NOT relation/62622 Landkreis Augsburg) — see
        # config/boundaries/augsburg_admin_boundary.geojson.
        "bbox": (10.7633615, 48.2581444, 10.9593328, 48.4586541),
        "description": "Augsburg (Bayern/Schwaben, PLZ 861xx)",
    },
    "leipzig": {
        "pbf": os.path.join(BASE_DIR, "data", "osm", "sachsen-latest.osm.pbf"),
        # bbox computed from Nominatim relation/62649 (Leipzig kreisfreie
        # Stadt proper, NOT Landkreis Leipzig — the bbox area (~305 km^2)
        # matches Leipzig city's known ~297 km^2, not the much larger
        # ~1650 km^2 Landkreis) — see
        # config/boundaries/leipzig_admin_boundary.geojson.
        "bbox": (12.2366519, 51.2381704, 12.5424918, 51.4481145),
        "description": "Leipzig (Sachsen, PLZ 04xxx)",
    },
}

# --- Mandatory Gate Thresholds (FROM SPECIFICATION, Phase 15 revised) ---
# REMOVED: MIN_CLUSTER_SIZE from gate (Phase 15 Finding A)
# Small size alone MUST NOT cause structural FAIL.
# MOVED to core/street_building_types.py (2026-07-13, KI-012) — re-imported
# above so PASS_MAX_MFH_RATIO etc. are still accessible from this module's
# namespace unchanged; do not redefine them here (would shadow the import).

# --- Execution Scale Threshold (separate concern from structural gate) ---
# Clusters below this count are structurally eligible but operationally subscale.
# They should be treated as APPEND_TO_AREA, not excluded.
STANDALONE_MIN_SIZE = 15


# --- Building Tag Classification ---
# OSM tags that signal a Single-Family Home (SFH)
DETACHED_TAGS = {"detached"}
# Phase B: added 'semidetached' (1 confirmed instance in Neuss OSM, no underscore variant)
SEMI_DETACHED_TAGS = {"semidetached_house", "semi_detached", "semidetached"}
ROWHOUSE_TAGS = {"terrace", "terraced", "row_house"}
MFH_TAGS = {"apartments", "apartment", "dormitory", "hotel", "flat"}


def fetch_buildings():
    """
    Query Overpass for all residential building ways in Neuss bbox.
    [DEPRECATED] — prefer load_buildings_from_pbf() via fetch_buildings(city_key).
    Kept as automatic fallback when local PBF is not available.
    """
    query = f"""
[out:json][timeout:120];
(
  way["building"~"yes|residential|house|apartments|detached|semidetached_house|terrace|multi_family|dormitory"]{NEUSS_BBOX};
);
out geom tags;
"""
    logger.info("Querying Overpass API for Neuss building data (with geometry)...")
    import time as _time
    last_err = None
    for mirror in OVERPASS_MIRRORS:
        try:
            logger.info(f"  Trying: {mirror}")
            resp = requests.post(
                mirror,
                data={"data": query},
                headers={"User-Agent": "TerritoryAI-FoundationLayer/1.0"},
                timeout=140,
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            logger.info(f"Received {len(elements)} building elements from Overpass ({mirror}).")
            return elements
        except requests.RequestException as e:
            logger.warning(f"  Mirror {mirror} failed: {e} — trying next...")
            last_err = e
            _time.sleep(3)
    logger.error(f"All Overpass mirrors failed. Last error: {last_err}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# PBF-Based Building Loader (Primary Data Source)
# ---------------------------------------------------------------------------

# OSM building tags that are residential / relevant to our pipeline
_BUILDING_TAGS_OF_INTEREST = {
    "yes", "residential", "house", "apartments", "detached",
    "semidetached_house", "terrace", "multi_family", "dormitory",
}


class _BuildingExtractor:
    """
    osmium-based handler that extracts residential building ways from a PBF file
    and converts them to the same format as Overpass API 'out geom tags' results.

    Output element format (Overpass-compatible):
        {
            "type": "way",
            "id": <int>,
            "tags": {
                "building": <str>,
                "addr:street": <str>,
                "addr:housenumber": <str>,
                "addr:postcode": <str>,
                "building:levels": <str>,
            },
            "geometry": [{"lat": <float>, "lon": <float>}, ...]
        }
    """

    def __init__(self, bbox=None):
        """
        Args:
            bbox: Optional (lon_min, lat_min, lon_max, lat_max) to spatially
                  restrict results. If None, all buildings in the PBF are returned.
        """
        self.elements = []
        self.bbox = bbox  # (lon_min, lat_min, lon_max, lat_max)

    def extract(self, pbf_path: str) -> list:
        """Run extraction. Returns list of Overpass-compatible element dicts."""
        try:
            import osmium
        except ImportError:
            raise RuntimeError(
                "osmium package not installed. Run: pip install osmium"
            )

        import osmium

        class _WayHandler(osmium.SimpleHandler):
            def __init__(handler_self):
                osmium.SimpleHandler.__init__(handler_self)
                handler_self.elements = []
                handler_self.bbox = self.bbox

            def way(handler_self, w):
                tags = w.tags
                building_tag = tags.get("building", "")
                if not building_tag or building_tag.lower() in ("no", ""):
                    return
                if building_tag.lower() not in _BUILDING_TAGS_OF_INTEREST:
                    return  # Skip non-residential (commercial, industrial, etc.)

                # Collect node coordinates
                nodes = []
                for n in w.nodes:
                    if n.location.valid():
                        nodes.append({
                            "lat": round(n.location.lat, 7),
                            "lon": round(n.location.lon, 7),
                        })

                if not nodes:
                    return  # No geometry — skip

                # Bounding box filter (centroid-based)
                if handler_self.bbox:
                    lon_min, lat_min, lon_max, lat_max = handler_self.bbox
                    lats = [nd["lat"] for nd in nodes]
                    lons = [nd["lon"] for nd in nodes]
                    c_lat = sum(lats) / len(lats)
                    c_lon = sum(lons) / len(lons)
                    if not (lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max):
                        return

                handler_self.elements.append({
                    "type": "way",
                    "id": w.id,
                    "tags": {
                        "building":          tags.get("building", ""),
                        "addr:street":       tags.get("addr:street", ""),
                        "addr:housenumber":  tags.get("addr:housenumber", ""),
                        "addr:postcode":     tags.get("addr:postcode", ""),
                        "building:levels":   tags.get("building:levels", ""),
                    },
                    "geometry": nodes,
                })

        handler = _WayHandler()
        # locations=True enables NodeLocationsForWays so way.nodes have coordinates
        handler.apply_file(pbf_path, locations=True, idx="flex_mem")
        return handler.elements


def load_buildings_from_pbf(city_key: str = "neuss") -> list:
    """
    Load residential building ways from a local Geofabrik PBF extract.

    Returns a list of Overpass-compatible element dicts — drop-in replacement
    for the original fetch_buildings() Overpass response.

    Args:
        city_key: Key into OSM_PBF_REGISTRY (default 'neuss').
    """
    registry_entry = OSM_PBF_REGISTRY.get(city_key)
    if not registry_entry:
        raise ValueError(f"Unknown city_key '{city_key}'. Add it to OSM_PBF_REGISTRY.")

    pbf_path = registry_entry["pbf"]
    bbox     = registry_entry.get("bbox")
    desc     = registry_entry.get("description", city_key)

    if not os.path.exists(pbf_path):
        raise FileNotFoundError(
            f"PBF file not found: {pbf_path}\n"
            f"Download from: https://download.geofabrik.de/europe/germany/nordrhein-westfalen/"
        )

    logger.info(f"[PBF] Loading buildings from local OSM extract: {pbf_path}")
    logger.info(f"[PBF] City: {desc} | bbox filter: {bbox}")

    extractor = _BuildingExtractor(bbox=bbox)
    elements = extractor.extract(pbf_path)

    logger.info(f"[PBF] Extracted {len(elements)} residential building elements.")
    return elements



def classify_building_tag(tag: str) -> str:
    """Classify a raw OSM building tag into one of: detached, semi_detached, rowhouse, mfh, other."""
    tag = tag.lower().strip()
    if tag in DETACHED_TAGS or tag in ("house",):
        return "detached"
    if tag in SEMI_DETACHED_TAGS:
        return "semi_detached"
    if tag in ROWHOUSE_TAGS:
        return "rowhouse"
    if tag in MFH_TAGS:
        return "mfh"
    return "other"


# ---------------------------------------------------------------------------
# Patch v3 — Other-Bucket Rescue via Geometry Heuristics
# ---------------------------------------------------------------------------

# Tags that are definitively NON-residential and must be excluded from rescue.
# These commonly appear under building=yes in OSM and must not be mistaken for houses.
_NON_RESIDENTIAL_TAGS = {
    "garage", "garages", "shed", "roof", "greenhouse", "carport", "hut",
    "barn", "kiosk", "cabin", "shelter", "container", "construction",
    "service", "industrial", "commercial", "retail", "office", "school",
    "kindergarten", "university", "hospital", "church", "mosque", "temple",
    "outbuilding", "farm_auxiliary", "allotment_house", "annex",
}

# Tags eligible for geometry-based rescue (ambiguous residential candidates)
_RESCUABLE_TAGS = {"yes", "residential"}

# ---------------------------------------------------------------------------
# MVP Uplift v5 — Enhancement B: Local Relative Size Deviation
# Adds deviation_signal as a very weak (0.05) additive modifier.
# Signals MUST sum to 1.0 when all present.
# ---------------------------------------------------------------------------

# Signal weights (all signals present)
_W_AREA         = 0.32   # reduced from 0.37 to accommodate _W_DEVIATION
_W_LEVEL        = 0.27   # EXCLUDED (not redistributed) when levels absent
_W_PRIOR        = 0.18
_W_NEIGHBOR     = 0.10
_W_TOPOLOGY     = 0.08
_W_DEVIATION    = 0.05   # NEW v5: local relative size deviation (Enhancement B)
# Sum: 0.32+0.27+0.18+0.10+0.08+0.05 = 1.00
# Levels-missing renorm: 0.32+0.18+0.10+0.08+0.05 = 0.73 (same denominator as before)

# Area soft mapping
_AREA_FULL_SFH  = 150.0   # m² → area_signal = 0.0
_AREA_FULL_MFH  = 550.0   # m² → area_signal = 1.0

# Level soft mapping
_LEVEL_FULL_SFH = 2
_LEVEL_FULL_MFH = 5

# Decision bands (v5 final: SFH band tightened 0.35 → 0.30 → 0.25)
_MFH_BAND_HIGH  = 0.65
_SFH_BAND_HIGH  = 0.25   # v5: tightened from 0.30 (plan Step 1, Mandatory)
# 0.25 < mfh_prob < 0.65  → Other (uncertainty band)
_SFH_HIGH_CONF  = 0.15   # v5: tightened from 0.18 (plan Step 1, Mandatory)
_MFH_HIGH_CONF  = 0.80

# Topology signal constants
_TOPO_BLOCK_ANGLE  = 120.0
_TOPO_LINEAR_ANGLE = 140.0

# Enhancement B: local deviation signal constants
# Activation: building must be >= _DEVIATION_ACTIVATION fraction SMALLER than
# the street median to trigger the signal (guards against normal size variance).
# Scale: gentle — should not dominate the score, only nudge borderline cases.
_DEVIATION_ACTIVATION = 0.40   # raised: building must be >= 40% smaller than median
_DEVIATION_SCALE      = 0.80   # gentle push: 40% smaller -> dev_signal ~0.32


def _polygon_area_m2(geom_nodes: list) -> float:
    """
    Compute approximate polygon area in m² from Overpass geometry nodes.
    Uses Shoelace theorem with local equirectangular projection.
    Returns 0.0 on any error.
    """
    import math
    if not geom_nodes or len(geom_nodes) < 3:
        return 0.0
    try:
        lats = [n["lat"] for n in geom_nodes]
        lons = [n["lon"] for n in geom_nodes]
        cy = sum(lats) / len(lats)
        scale_x = 111320.0 * math.cos(math.radians(cy))
        scale_y = 111320.0
        pts = [(lon * scale_x, lat * scale_y) for lat, lon in zip(lats, lons)]
        area = 0.0
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            area += pts[i][0] * pts[j][1]
            area -= pts[j][0] * pts[i][1]
        return abs(area) / 2.0
    except Exception:
        return 0.0


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _compute_topology_signal(
    building_centroid,
    candidates_indices: list,
    all_centroids: list,
) -> float:
    """
    Topology signal: neighbor complexity for one rescuable building.

    Returns a float in [0, 1]:
      0.0  = isolated (no neighbors) → SFH-like
      0.15 = 2 neighbors, collinear chain → rowhouse-like
      0.50 = 2+ neighbors, angle inconclusive
      0.70 = 3+ neighbors, non-collinear → block/MFH-like
      1.0  = 4+ neighbors → dense block

    Uses centroid dot-product to distinguish row chains from block structures.
    Angle thresholds (_TOPO_BLOCK_ANGLE / _TOPO_LINEAR_ANGLE) are engineering
    heuristics — treat as tunable parameters, not empirical truth.
    """
    import math

    # Remove self from candidate list
    nb_indices = [i for i in candidates_indices
                  if all_centroids[i] is not None
                  and all_centroids[i] != building_centroid]
    nb_count = len(nb_indices)

    if nb_count == 0:
        return 0.0   # isolated → strong SFH
    if nb_count >= 4:
        return 1.0   # very dense block → strong MFH
    if nb_count >= 3:
        return 0.70  # multi-sided block → MFH

    # nb_count == 1 or 2: attempt collinearity check
    cx, cy = building_centroid

    # Collect vectors from home building to each neighbor centroid
    vectors = []
    for i in nb_indices:
        nx, ny = all_centroids[i]
        dx, dy = nx - cx, ny - cy
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            vectors.append((dx / length, dy / length))

    if nb_count == 1 or len(vectors) < 2:
        return 0.35  # single neighbor — mildly SFH-like but not clear

    # Two neighbors: compute angle between the two direction vectors
    # angle = acos(dot(v1, v2)) — if nearly 180° they are on opposite sides
    dot = vectors[0][0]*vectors[1][0] + vectors[0][1]*vectors[1][1]
    dot = max(-1.0, min(1.0, dot))  # numerical clamp
    angle_deg = math.degrees(math.acos(dot))

    if angle_deg >= _TOPO_LINEAR_ANGLE:
        # Neighbours on opposite sides → row chain
        return 0.15
    elif angle_deg <= _TOPO_BLOCK_ANGLE:
        # Neighbours at an angle → block
        return 0.70
    else:
        # Inconclusive → neutral
        return 0.50


def score_ambiguous_building(
    area_m2: float,
    levels: "int | None",
    street_mfh_prior: float,
    neighbor_median_area: "float | None" = None,
    topology_signal: "float | None" = None,
    deviation_signal: "bool" = True,      # Enhancement B activation flag
    street_median_area: "float | None" = None,  # Enhancement B: street median area
) -> dict:
    """
    MVP Uplift v5 scoring for ambiguous buildings.
    (building=yes / building=residential only)

    Signals (all present, weights sum to 1.00):
      area_signal      0.32  absolute footprint
      level_signal     0.27  floors (excluded/renorm when missing)
      prior_signal     0.18  street-level MFH tag fraction
      neighbor_signal  0.10  median area of neighbours
      topology_signal  0.08  neighbour complexity (block vs chain)
      deviation_signal 0.05  relative size vs street median (Enhancement B)

    Decision bands: SFH <= 0.30 | OTHER 0.30-0.65 | MFH >= 0.65
    SFH confidence capped at MEDIUM when levels are missing.
    Pure function — no I/O.
    """
    # ── HARD GATE: levels >= 3 → MFH ────────────────────────────────────
    # German building regulation: genuine SFH/DHH/RH ≤ 2 Vollgeschosse.
    # building=yes or building=residential with 3+ levels is definitionally
    # not a single-family home. Override soft scoring.
    # FIX 2026-05-04: prevents city-center apartment blocks from being
    # classified as rowhouse by spatial adjacency heuristic.
    if levels is not None and levels >= 3:
        return {
            "mfh_prob":     0.95,
            "sfh_prob":     0.05,
            "decision":     "mfh",
            "confidence":   "HIGH",
            "reason_trace": [f"HARD_GATE: building:levels={levels} >= 3 → MFH (no soft scoring)"],
        }

    # ── Signal: area ────────────────────────────────────────────────────────
    area_signal = _clamp(
        (area_m2 - _AREA_FULL_SFH) / (_AREA_FULL_MFH - _AREA_FULL_SFH)
    )

    # ── Signal: levels ──────────────────────────────────────────────────────
    # CRITICAL: missing levels do NOT redistribute weight to area.
    # Instead level is simply excluded from the weighted sum,
    # reducing total evidence and pulling mfh_prob toward neutral.
    levels_missing = levels is None
    if not levels_missing:
        level_signal = _clamp(
            (levels - _LEVEL_FULL_SFH) / (_LEVEL_FULL_MFH - _LEVEL_FULL_SFH)
        )

    # ── Signal: street prior ────────────────────────────────────────────────
    prior_signal = _clamp(street_mfh_prior)

    # ── Signal: neighbor (building-size context) ───────────────────────────
    if neighbor_median_area is None:
        neighbor_signal = 0.5
    else:
        neighbor_signal = _clamp(
            (neighbor_median_area - _AREA_FULL_SFH) / (_AREA_FULL_MFH - _AREA_FULL_SFH)
        )

    # ── Signal: topology (neighbor complexity) ──────────────────────────────
    topo_signal = 0.5 if topology_signal is None else _clamp(topology_signal)

    # ── Signal: local relative size deviation (Enhancement B) ───────────────
    # Activates ONLY when building is >= 40% smaller than street median.
    # CRITICAL: when NOT activated, dev_w = 0 and dev_signal is excluded
    # from the weighted sum entirely. Including it as neutral (0.5) would
    # systematically inflate mfh_prob for borderline SFH buildings.
    dev_w = 0.0
    dev_signal = 0.5  # only used when dev_w > 0
    if deviation_signal and street_median_area is not None and street_median_area > 0:
        ratio = (street_median_area - area_m2) / street_median_area
        if ratio >= _DEVIATION_ACTIVATION:
            dev_signal = _clamp(ratio * _DEVIATION_SCALE)
            dev_w = _W_DEVIATION

    # ── Weighted combination ──────────────────────────────────────────────
    # - Levels excluded when missing (renormalise)
    # - Deviation excluded when not activated (dev_w = 0)
    if levels_missing:
        total_w = _W_AREA + _W_PRIOR + _W_NEIGHBOR + _W_TOPOLOGY + dev_w
        mfh_prob = (
            _W_AREA      * area_signal
            + _W_PRIOR   * prior_signal
            + _W_NEIGHBOR* neighbor_signal
            + _W_TOPOLOGY* topo_signal
            + dev_w      * dev_signal
        ) / total_w
    else:
        total_w = _W_AREA + _W_LEVEL + _W_PRIOR + _W_NEIGHBOR + _W_TOPOLOGY + dev_w
        mfh_prob = (
            _W_AREA      * area_signal
            + _W_LEVEL   * level_signal
            + _W_PRIOR   * prior_signal
            + _W_NEIGHBOR* neighbor_signal
            + _W_TOPOLOGY* topo_signal
            + dev_w      * dev_signal
        ) / total_w
    mfh_prob = _clamp(mfh_prob)
    sfh_prob = 1.0 - mfh_prob

    # ── Decision ────────────────────────────────────────────────────────────
    if mfh_prob >= _MFH_BAND_HIGH:
        decision = "mfh"
        confidence = "HIGH" if mfh_prob >= _MFH_HIGH_CONF else "MEDIUM"
    elif mfh_prob <= _SFH_BAND_HIGH:
        decision = "sfh"
        if levels_missing:
            # Missing levels reduce SFH confidence — never HIGH when data absent
            confidence = "MEDIUM"
        else:
            confidence = "HIGH" if mfh_prob <= _SFH_HIGH_CONF else "MEDIUM"
    else:
        decision = "other"
        confidence = "LOW"

    reason_trace = [
        f"area={area_m2:.0f}m² → area_signal={area_signal:.2f} (w={_W_AREA:.2f})",
        f"levels={'missing' if levels_missing else levels} → {'excluded' if levels_missing else f'level_signal={level_signal:.2f}'} (w={0 if levels_missing else _W_LEVEL:.2f})",
        f"street_prior={street_mfh_prior:.2f} → prior_signal={prior_signal:.2f} (w={_W_PRIOR:.2f})",
        f"topo={topo_signal:.2f} (w={_W_TOPOLOGY:.2f})",
        f"mfh_prob={mfh_prob:.3f} → {decision} ({confidence}{'*no_levels' if levels_missing and decision=='sfh' else ''})",
    ]

    return {
        "mfh_prob":   mfh_prob,
        "sfh_prob":   sfh_prob,
        "decision":   decision,
        "confidence": confidence,
        "reason_trace": reason_trace,
    }


def rescue_other_by_geometry(
    elements: list,
    street_counts: dict,
    street_to_clusters: dict,
) -> dict:
    """
    Patch v3 (revised) — Other-Bucket Rescue via Geometry Heuristics.

    Two key fixes over original:
      A. Street-level MFH prior guard:
         If a street's explicit mfh_ratio > 25%, route building=yes/residential
         to MFH — not SFH. Fixes Volmerswerther Straße type false rowhouses.
      B. Pass 2 context tree restricted to EXPLICIT SFH tags only:
         (house, detached, terrace, semidetached_house — NOT yes/residential)
         Prevents apartment-block adjacency inflating neighbour count → rowhouse.

    Guardrails unchanged:
      - Only yes / residential tags touched.
      - Ambiguous band (250–600 m², no level signal) stays as other.
      - Gate thresholds not changed.
    """
    import copy

    try:
        from shapely.geometry import Polygon
        from shapely.strtree import STRtree
    except ImportError:
        logger.warning("[OtherRescue] Shapely not available — skipping geometry rescue.")
        return street_counts

    new_counts = copy.deepcopy(street_counts)

    # ── Street-level MFH prior ──────────────────────────────────────────────
    _MFH_PRIOR_THRESHOLD = 0.25
    street_explicit_mfh: dict = {}
    street_explicit_sfh: dict = {}
    for el in elements:
        tags = el.get("tags", {})
        btag = tags.get("building", "").lower().strip()
        street = tags.get("addr:street", "")
        if not street:
            continue
        if btag in MFH_TAGS:
            street_explicit_mfh[street] = street_explicit_mfh.get(street, 0) + 1
        elif (btag in DETACHED_TAGS or btag == "house"
              or btag in SEMI_DETACHED_TAGS or btag in ROWHOUSE_TAGS):
            street_explicit_sfh[street] = street_explicit_sfh.get(street, 0) + 1

    def _mfh_prior(street: str) -> float:
        em = street_explicit_mfh.get(street, 0)
        es = street_explicit_sfh.get(street, 0)
        return em / (em + es) if (em + es) > 0 else 0.0

    # ── Topology: build all-buildings STRtree for Pass 1 queries ───────────
    # Separate from Pass 2 tree (which uses explicit SFH tags only).
    # This tree includes ALL building elements for neighbour complexity scoring.
    all_geoms      = []   # Shapely geoms, parallel to all_centroids
    all_centroids  = []   # (cx, cy) in lon/lat space
    for el in elements:
        gn = el.get("geometry", [])
        if len(gn) >= 3:
            try:
                pts = [(n["lon"], n["lat"]) for n in gn]
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                c = poly.centroid
                all_geoms.append(poly)
                all_centroids.append((c.x, c.y))
            except Exception:
                all_geoms.append(None)
                all_centroids.append(None)
        else:
            all_geoms.append(None)
            all_centroids.append(None)

    # Only build tree from valid geoms; keep index map for centroid lookup
    valid_idx  = [i for i, g in enumerate(all_geoms) if g is not None]
    valid_geoms = [all_geoms[i] for i in valid_idx]
    topo_tree = STRtree(valid_geoms) if valid_geoms else None
    # Map from STRtree result index → all_centroids index
    topo_idx_map = {j: valid_idx[j] for j in range(len(valid_idx))}

    # ── Enhancement B: precompute street median areas ───────────────────
    # O(n) scan of all buildings per street to get median footprint.
    # Used for local relative size deviation signal.
    _street_areas: dict = {}  # street → list[float]
    for el in elements:
        tags = el.get("tags", {})
        s = tags.get("addr:street", "")
        if not s:
            continue
        gn = el.get("geometry", [])
        a = _polygon_area_m2(gn)
        if a >= 10.0:
            _street_areas.setdefault(s, []).append(a)

    import statistics as _stats
    street_median_areas: dict = {
        s: _stats.median(areas)
        for s, areas in _street_areas.items()
        if len(areas) >= 3  # need at least 3 samples for a meaningful median
    }

    # ── Pass 1: soft scoring for each rescuable building ─────────────────
    # other_buildings: collected for Enhancement A second-pass smoothing
    rescued_sfh   = []
    other_buildings = []   # Enhancement A placeholder
    n_mfh = 0
    n_other = 0
    n_skipped = 0

    for el in elements:
        tags = el.get("tags", {})
        btag = tags.get("building", "").lower().strip()
        if btag not in _RESCUABLE_TAGS:
            continue

        street = tags.get("addr:street", "")
        if not street or street not in street_to_clusters:
            continue

        # Hard filter: explicitly non-residential use signals
        if tags.get("amenity", ""):
            n_skipped += 1
            continue
        landuse = tags.get("landuse", "")
        if landuse and landuse not in ("residential",):
            n_skipped += 1
            continue

        geom_nodes = el.get("geometry", [])
        area = _polygon_area_m2(geom_nodes)
        if area < 10.0:   # digitisation noise / garages
            n_skipped += 1
            continue

        levels_str = tags.get("building:levels", "")
        levels = int(levels_str) if levels_str.isdigit() else None

        # Street prior: neutral (0.5) when < 3 explicitly-tagged buildings
        em = street_explicit_mfh.get(street, 0)
        es = street_explicit_sfh.get(street, 0)
        prior = em / (em + es) if (em + es) >= 3 else 0.5

        # Topology signal: neighbor complexity from all-buildings tree
        topo_sig = None
        if topo_tree is not None and len(geom_nodes) >= 3:
            try:
                pts = [(n["lon"], n["lat"]) for n in geom_nodes]
                bpoly = Polygon(pts)
                if not bpoly.is_valid:
                    bpoly = bpoly.buffer(0)
                bc = bpoly.centroid
                raw_candidates = topo_tree.query(bpoly.buffer(_ADJACENCY_BUFFER_DEG))
                mapped = [topo_idx_map[j] for j in raw_candidates
                          if j in topo_idx_map]
                topo_sig = _compute_topology_signal(
                    (bc.x, bc.y), mapped, all_centroids
                )
            except Exception:
                topo_sig = None  # neutral on any failure

        # Soft score (v5: with topology + deviation)
        result = score_ambiguous_building(
            area_m2=area,
            levels=levels,
            street_mfh_prior=prior,
            neighbor_median_area=None,
            topology_signal=topo_sig,
            deviation_signal=True,
            street_median_area=street_median_areas.get(street),
        )

        if street not in new_counts:
            new_counts[street] = {"detached": 0, "semi_detached": 0,
                                  "rowhouse": 0, "mfh": 0, "other": 0}

        decision = result["decision"]
        if decision == "mfh":
            new_counts[street]["mfh"]   = new_counts[street].get("mfh", 0) + 1
            new_counts[street]["other"] = max(0, new_counts[street].get("other", 0) - 1)
            n_mfh += 1
        elif decision == "sfh":
            try:
                pts = [(n["lon"], n["lat"]) for n in geom_nodes]
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                rescued_sfh.append({"street": street, "geom": poly,
                                    "mfh_prob": result["mfh_prob"],
                                    "confidence": result["confidence"]})
            except Exception:
                # Geometry unusable — safe fallback to detached
                new_counts[street]["detached"] = new_counts[street].get("detached", 0) + 1
                new_counts[street]["other"]    = max(0, new_counts[street].get("other", 0) - 1)
        else:  # "other" — uncertainty band, stays as other
            n_other += 1
            # Enhancement A: store for second-pass smoothing
            if len(geom_nodes) >= 3:
                try:
                    pts = [(n["lon"], n["lat"]) for n in geom_nodes]
                    o_poly = Polygon(pts)
                    if not o_poly.is_valid:
                        o_poly = o_poly.buffer(0)
                    other_buildings.append({
                        "street": street,
                        "geom": o_poly,
                        "area": area,
                    })
                except Exception:
                    pass

    logger.info(
        f"[OtherRescue/B-lite] Pass 1: {len(rescued_sfh)} → SFH, "
        f"{n_mfh} → MFH, {n_other} stayed Other (uncertainty band), "
        f"{n_skipped} skipped (non-res filter)."
    )

    if not rescued_sfh and not other_buildings:
        return new_counts

    # ── Enhancement A: second-pass neighbourhood consensus smoothing ───────
    # For each OTHER building, query confident classified neighbours.
    # If >= SMOOTH_MIN_VOTES HIGH-confidence neighbours agree with >= SMOOTH_CONSENSUS,
    # rescue the building toward the majority class.
    # Guardrails:
    #   · Only OTHER buildings are candidates (no re-classification of SFH/MFH)
    #   · Voters must be HIGH-confidence only
    #   · Rescued confidence = LOW (never upgraded)
    #   · Both SFH and MFH directions allowed — no directional bias
    SMOOTH_RADIUS        = _ADJACENCY_BUFFER_DEG * 3   # ~3m at Neuss latitude
    SMOOTH_MIN_VOTES     = 3                            # minimum HIGH-conf voters
    SMOOTH_CONSENSUS     = 0.75                         # majority share required

    # Build voter set: all rescued_sfh + MFH buildings from Pass 1
    # We need geometry + decision for each voter.
    # SFH voters: from rescued_sfh list (already have geom + confidence)
    # MFH voters: collect from elements that were explicit MFH tags (not ambiguous)
    voter_geoms    = []
    voter_decisions = []
    voter_confs    = []

    for b in rescued_sfh:
        voter_geoms.append(b["geom"])
        voter_decisions.append("sfh")
        voter_confs.append(b["confidence"])

    # Also include explicit MFH-tagged buildings as HIGH-confidence MFH voters
    for el in elements:
        tags = el.get("tags", {})
        btag = tags.get("building", "").lower().strip()
        if btag in MFH_TAGS:
            gn = el.get("geometry", [])
            if len(gn) >= 3:
                try:
                    pts = [(n["lon"], n["lat"]) for n in gn]
                    vp = Polygon(pts)
                    if not vp.is_valid:
                        vp = vp.buffer(0)
                    voter_geoms.append(vp)
                    voter_decisions.append("mfh")
                    voter_confs.append("HIGH")
                except Exception:
                    pass

    n_smooth_sfh = 0
    n_smooth_mfh = 0

    if voter_geoms and other_buildings:
        smooth_tree = STRtree(voter_geoms)

        for ob in other_buildings:
            street = ob["street"]
            o_geom = ob["geom"]
            try:
                candidates = smooth_tree.query(o_geom.buffer(SMOOTH_RADIUS))
            except Exception:
                continue

            # Filter to HIGH-confidence voters only
            high_conf = [
                c for c in candidates
                if voter_confs[c] == "HIGH"
            ]
            if len(high_conf) < SMOOTH_MIN_VOTES:
                continue

            sfh_votes = sum(1 for c in high_conf if voter_decisions[c] == "sfh")
            mfh_votes = sum(1 for c in high_conf if voter_decisions[c] == "mfh")
            total_votes = len(high_conf)
            sfh_share = sfh_votes / total_votes
            mfh_share = mfh_votes / total_votes

            if sfh_share >= SMOOTH_CONSENSUS:
                # Rescue → SFH
                rescued_sfh.append({
                    "street":     street,
                    "geom":       o_geom,
                    "mfh_prob":   0.20,        # low-end estimate for smoothed SFH
                    "confidence": "LOW",
                })
                new_counts[street]["other"] = max(
                    0, new_counts[street].get("other", 0) - 1
                )
                n_smooth_sfh += 1

            elif mfh_share >= SMOOTH_CONSENSUS:
                # Rescue → MFH
                new_counts[street]["mfh"]   = new_counts[street].get("mfh", 0) + 1
                new_counts[street]["other"] = max(
                    0, new_counts[street].get("other", 0) - 1
                )
                n_smooth_mfh += 1
            # else: not enough consensus — stay OTHER (honest abstention)

    if n_smooth_sfh or n_smooth_mfh:
        logger.info(
            f"[OtherRescue/A] Smoothing: {n_smooth_sfh} → SFH, "
            f"{n_smooth_mfh} → MFH (consensus rescue from OTHER)."
        )

    # ── Pass 2: adjacency subtype for rescued SFH ──────────────────────────
    # CRITICAL: context tree uses ONLY explicit SFH-tagged buildings.
    # building=yes/residential excluded — apartment blocks must not pollute
    # the neighbour count and cause false rowhouse assignments.
    explicit_sfh_geoms = []
    for el in elements:
        tags = el.get("tags", {})
        btag = tags.get("building", "").lower().strip()
        if btag in {"house", "detached", "semidetached_house", "semi_detached",
                    "semidetached", "terrace", "terraced", "row_house"}:
            gn = el.get("geometry", [])
            if len(gn) >= 3:
                try:
                    pts = [(n["lon"], n["lat"]) for n in gn]
                    poly = Polygon(pts)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    explicit_sfh_geoms.append(poly)
                except Exception:
                    pass

    # Context = explicit SFH tags + all rescued SFH candidates.
    # MFH-street buildings never reach Pass 2 (filtered by prior guard in Pass 1),
    # so combining rescued geoms here is safe — it only adds genuine SFH candidates.
    rescued_geoms = [r["geom"] for r in rescued_sfh]
    ctx_geoms = explicit_sfh_geoms + rescued_geoms if explicit_sfh_geoms else rescued_geoms
    tree = STRtree(ctx_geoms)

    rec_det = rec_semi = rec_row = 0
    for r in rescued_sfh:
        street = r["street"]
        candidates = tree.query(r["geom"].buffer(_ADJACENCY_BUFFER_DEG))
        nb_count = max(0, len(candidates) - 1)
        if nb_count >= 2:
            subtype = "rowhouse"
            rec_row += 1
        elif nb_count == 1:
            subtype = "semi_detached"
            rec_semi += 1
        else:
            subtype = "detached"
            rec_det += 1

        new_counts[street][subtype] = new_counts[street].get(subtype, 0) + 1
        new_counts[street]["other"] = max(0, new_counts[street].get("other", 0) - 1)

    logger.info(
        f"[OtherRescue] Pass 2 subtype (SFH-only context): "
        f"{rec_det} detached + {rec_semi} semi + {rec_row} rowhouse."
    )
    return new_counts


# Adjacency buffer in degrees for geometry-based house-tag correction.
# ~1.0 m at Neuss latitude — validated by audit_buffer_sensitivity.py.
_ADJACENCY_BUFFER_DEG = 0.000009


def correct_house_tags_by_adjacency(
    elements: list,
    street_counts: dict,
    street_house_tags: dict,
) -> tuple:
    """
    Patch v2 — Geometry-Based House Tag Correction (Root Cause Fix).

    Problem:
        building=house is a generic OSM tag. Taggers use it for detached,
        semi-detached, AND rowhouses indiscriminately. The tag-only pipeline
        routes all of them to 'detached', systematically overstating detached
        counts for streets like Am Mühlenweg.

    Fix:
        For every building tagged building=house, use its polygon geometry
        to count spatial neighbours within _ADJACENCY_BUFFER_DEG.
        If neighbours >= 2  → re-classify as rowhouse.
        If neighbours == 1  → re-classify as semi_detached.
        If neighbours == 0  → keep as detached (isolated, confirmed).

    Returns:
        (corrected_street_counts, corrected_street_house_tags)
        Both are new dicts — original dicts are not mutated.

    Safety rules:
        - Only building=house tagged elements are corrected. Explicit tags
          (detached, terrace, semidetached_house) are never touched.
        - Shapely is imported lazily — if not installed, correction is skipped
          with a warning and original counts are returned unchanged.
        - Elements without geometry (center-only) are silently skipped.
    """
    try:
        from shapely.geometry import Polygon
        from shapely.strtree import STRtree
    except ImportError:
        logger.warning("[HouseCorrection] Shapely not available — skipping geometry-based correction.")
        return street_counts, street_house_tags

    # Collect all house-tagged elements that have polygon geometry
    house_elements = []
    for el in elements:
        tags = el.get("tags", {})
        if tags.get("building", "").lower().strip() != "house":
            continue
        geom_nodes = el.get("geometry", [])
        if not geom_nodes or len(geom_nodes) < 3:
            continue
        try:
            pts = [(node["lon"], node["lat"]) for node in geom_nodes]
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            street = tags.get("addr:street", "")
            house_elements.append({"street": street, "geom": poly, "tags": tags})
        except Exception:
            continue

    if not house_elements:
        logger.info("[HouseCorrection] No house-tagged elements with polygon geometry found — skipping.")
        return street_counts, street_house_tags

    logger.info(f"[HouseCorrection] Running adjacency correction on {len(house_elements)} house-tagged buildings...")

    # Build STRtree over ALL house polygons (cross-street — needed for row detection across boundaries)
    geoms = [h["geom"] for h in house_elements]
    tree = STRtree(geoms)

    # Count neighbours for each house element
    corrections: dict[int, str] = {}  # index -> corrected class
    for i, h in enumerate(house_elements):
        candidates = tree.query(h["geom"].buffer(_ADJACENCY_BUFFER_DEG))
        neighbour_count = sum(1 for j in candidates if j != i)
        if neighbour_count >= 2:
            corrections[i] = "rowhouse"
        elif neighbour_count == 1:
            corrections[i] = "semi_detached"
        else:
            corrections[i] = "detached"  # confirmed isolated

    # Apply corrections to street_counts copies
    import copy
    new_counts = copy.deepcopy(street_counts)
    new_house_tags = dict(street_house_tags)  # shallow copy sufficient

    recovered_row = 0
    recovered_semi = 0
    for i, h in enumerate(house_elements):
        street = h["street"]
        corrected = corrections[i]
        if corrected == "detached":
            continue  # no change needed
        if street not in new_counts:
            continue  # street not in our cluster feed — skip

        # Remove one detached count, add to correct bucket
        new_counts[street]["detached"] = max(0, new_counts[street].get("detached", 0) - 1)
        new_counts[street][corrected] = new_counts[street].get(corrected, 0) + 1

        # Also reduce house_tagged count since this building is now re-homed
        new_house_tags[street] = max(0, new_house_tags.get(street, 0) - 1)

        if corrected == "rowhouse":
            recovered_row += 1
        else:
            recovered_semi += 1

    logger.info(
        f"[HouseCorrection] Correction complete: "
        f"recovered {recovered_row} rowhouse + {recovered_semi} semi_detached "
        f"from house-tagged detached pool."
    )
    return new_counts, new_house_tags


# classify_structure_profile() and apply_structure_gate() MOVED to
# core/street_building_types.py (2026-07-13, KI-012) — re-imported above,
# semantics unchanged. Do not redefine them here (would shadow the import).


def compute_execution_scale_flag(building_count_total: int) -> str:
    """
    Determine execution scale flag (Phase 15 Finding A).

    STANDALONE     : cluster is large enough to be actionable independently.
    APPEND_TO_AREA : cluster is too small to stand alone; should be combined
                     with adjacent streets or PLZ-level planning.

    This is SEPARATE from structural gate. Both PASS and REVIEW clusters
    can be either STANDALONE or APPEND_TO_AREA.
    """
    if building_count_total >= STANDALONE_MIN_SIZE:
        return "STANDALONE"
    return "APPEND_TO_AREA"


def compute_subtype_confidence(sfh_total: int, specific_sfh_count: int) -> str:
    """
    Phase B — Subtype Honesty Signal.

    IMPORTANT: This is NOT an accuracy metric.
    This field tells the reader whether the subtype breakdown is likely reliable,
    based on how many of the SFH buildings had explicit OSM subtype tags
    (detached, semidetached_house) vs generic tags (house, residential).

    Returns: 'HIGH' | 'MEDIUM' | 'LOW'

    Guardrail: These thresholds are initial engineering heuristics.
    They will be refined after the manual audit is completed.
    Do NOT interpret them as classification accuracy scores.
    """
    if sfh_total == 0:
        return "LOW"
    specific_ratio = specific_sfh_count / sfh_total
    if specific_ratio >= 0.60:
        return "HIGH"
    if specific_ratio >= 0.25:
        return "MEDIUM"
    return "LOW"


def compute_attached_confidence(sfh_total: int, house_tagged_count: int) -> str:
    """
    Phase B Revised — Attached Housing Honesty Signal.

    IMPORTANT: This is NOT an accuracy metric.
    Indicates whether the detached vs attached distinction can be trusted.

    When many buildings are tagged building=house (a generic tag), the
    detached count is likely overstated because real attached homes
    (semi-detached, paired) are hidden inside the house tag.

    Returns: 'HIGH' | 'MEDIUM' | 'LOW'

    Guardrail: Thresholds are initial engineering heuristics only.
    They serve as practical MVP decision triggers, not statistical truth claims.
    """
    if sfh_total == 0:
        return "LOW"
    house_ratio = house_tagged_count / sfh_total
    if house_ratio <= 0.20:
        return "HIGH"   # Few generic tags; classifier has explicit type info
    if house_ratio <= 0.50:
        return "MEDIUM"  # Some ambiguity; treat detached count with caution
    return "LOW"        # Most buildings are generic; detached likely overstated


def compute_attached_risk_flag(attached_confidence: str, house_tagged: int, sfh_total: int) -> bool:
    """
    Patch v2 Step 3 — Attached Risk Flag.

    Advisory boolean: True when the detached count on this street is
    structurally suspect due to building=house tag dominance.

    Triggers when EITHER:
      (a) attached_confidence is LOW  (house_tagged / sfh_total > 0.50), OR
      (b) attached_confidence is MEDIUM (house_tagged / sfh_total > 0.20)
          AND there are at least 5 house-tagged buildings
          (avoid flagging streets where a single house tag exists).

    IMPORTANT:
      - This flag is ADVISORY ONLY. No subtype label is changed.
      - No scoring penalty is applied in this round.
      - Downstream auditors and future rounds use this signal.
    """
    if attached_confidence == "LOW":
        return True
    if attached_confidence == "MEDIUM" and house_tagged >= 5:
        return True
    return False


def compute_small_mfh_suspect(
    attached_confidence: str,
    house_tagged: int,
    sfh_total: int,
    median_footprint_m2: float | None,
) -> bool:
    """
    Patch v2 Step 5 — Small MFH Suspect Flag.

    Advisory boolean: True when a street shows signs of small pseudo-house
    MFH buildings (2-4 unit shells) being silently routed to detached.

    Triggers when ALL of:
      (a) attached_confidence is LOW (house_tagged dominant), AND
      (b) median_footprint_m2 > 250 m² (oversized for a true detached house).

    IMPORTANT:
      - This flag is ADVISORY ONLY. No subtype label is changed.
      - No gate tier adjustment, no sfh_total downweight in this round.
      - Used as a future-audit candidate marker.
    """
    MFH_SUSPECT_FOOTPRINT_THRESHOLD = 250.0  # m²
    if attached_confidence != "LOW":
        return False
    if median_footprint_m2 is None:
        return False
    if median_footprint_m2 > MFH_SUSPECT_FOOTPRINT_THRESHOLD:
        return True
    return False


# ---------------------------------------------------------------------------
# Cluster-Scoped Building Count Helpers (Range Filtering)
# ---------------------------------------------------------------------------

def _parse_housenumber_numeric(hn: str) -> "int | None":
    """
    Extract the leading integer from a German house number string.
    Examples: '5a' -> 5, '407b' -> 407, '1b' -> 1, '30c' -> 30.
    Returns None if no leading integer is found.
    """
    import re as _re
    m = _re.match(r"^(\d+)", str(hn).strip())
    return int(m.group(1)) if m else None


def _count_cluster_buildings(
    building_list: list,
    house_range_str: str,
) -> "tuple[int | None, int, int]":
    """
    Filter a street's building list to those falling within the cluster's house_range.

    Returns:
        (cluster_count, unaddressed_count, in_range_count)

        cluster_count       : buildings with housenumber within [min_num, max_num],
                              OR None if house_range cannot be parsed.
        unaddressed_count   : buildings with addr:street but NO addr:housenumber.
        in_range_count      : alias for cluster_count (0 if None).

    Design decision:
        When fewer than 10% of buildings have housenumbers (LOW coverage),
        cluster_count is still returned — the caller decides whether to trust it.
        The address_filter_coverage field signals reliability to downstream consumers.
    """
    import re as _re

    nums = _re.findall(r"\d+", str(house_range_str))
    if len(nums) < 2:
        # Range string is unparseable (e.g. 'unknown', single-number, empty)
        unaddressed = sum(1 for b in building_list if not b.get("housenumber"))
        return None, unaddressed, 0

    min_num = int(nums[0])
    max_num = int(nums[-1])

    in_range = 0
    unaddressed = 0
    for b in building_list:
        hn = b.get("housenumber", "")
        if not hn:
            unaddressed += 1
            continue
        num = _parse_housenumber_numeric(hn)
        if num is None:
            unaddressed += 1
            continue
        if min_num <= num <= max_num:
            in_range += 1

    return in_range, unaddressed, in_range


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, default="neuss", help="City key from OSM_PBF_REGISTRY")
    parser.add_argument("--clusters", type=str, help="Path to input clusters JSON")
    parser.add_argument("--out", type=str, help="Path to output foundation JSON")
    args = parser.parse_args()

    city_key = args.city
    logger.info(f"Starting Foundation Layer: Residential Structure Filter for {city_key.upper()}")

    # 1. Load base cluster feed
    if args.clusters:
        clusters_path = args.clusters
        if not os.path.exists(clusters_path):
            logger.error(f"Cluster feed not found: {clusters_path}")
            sys.exit(1)
        logger.info(f"[ClusterFeed] Using specified cluster feed: {clusters_path}")
    else:
        # Fallback to Neuss default
        clusters_path_v2 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v2.json")
        clusters_path_v1 = os.path.join(BASE_DIR, "output", "clusters", "neuss_hybrid_clusters_v1.json")

        if os.path.exists(clusters_path_v2):
            clusters_path = clusters_path_v2
            logger.info("[ClusterFeed] Using v2 cluster feed (889 clusters, building=yes fix).")
        elif os.path.exists(clusters_path_v1):
            clusters_path = clusters_path_v1
            logger.warning("[ClusterFeed] v2 not found — falling back to v1 (554 clusters, missing building=yes).")
        else:
            logger.error("No cluster feed found (v1 or v2). Aborting.")
            sys.exit(1)

    with open(clusters_path, "r", encoding="utf-8") as f:
        clusters_data = json.load(f)

    logger.info(f"Loaded {len(clusters_data)} clusters from feed.")

    # Build lookup: primary_street -> list of clusters
    street_to_clusters = {}
    for c in clusters_data:
        street = c["primary_street"]
        if street not in street_to_clusters:
            street_to_clusters[street] = []
        street_to_clusters[street].append(c)

    # 2. Fetch raw OSM building data
    pbf_entry = OSM_PBF_REGISTRY.get(city_key, {})
    if os.path.exists(pbf_entry.get("pbf", "")):
        logger.info("[DataSource] Using local PBF extract (primary).")
        elements = load_buildings_from_pbf(city_key=city_key)
    else:
        logger.warning(
            "[DataSource] Local PBF not found — falling back to public Overpass API. "
            "Download PBF for reliability: see data/osm/README.md"
        )
        elements = fetch_buildings()

    # 3. Aggregate per-street building type counts AND PLZ (from OSM addr:postcode)
    # NOTE: Two separate dicts to avoid type-checker ambiguity (int vs list)
    street_counts: dict[str, dict[str, int]] = {}
    street_plz_votes: dict[str, dict[str, int]] = {}  # street -> {plz: count}
    street_house_tags: dict[str, int] = {}  # Phase B Revised: track building=house count separately
    # 'house' routes to detached but is a generic tag — many attached homes hide inside it

    # Range-filter support: per-building housenumber + type list, keyed by street name.
    # Used downstream to compute cluster_building_count (scoped to cluster's house_range).
    # This is the ONLY correct unit of analysis for canvassing; building_count_total
    # remains the street-level total used for scoring (unchanged for backward compat).
    street_building_list: dict[str, list] = {}

    for el in elements:
        tags = el.get("tags", {})
        street = tags.get("addr:street")
        if not street or street not in street_to_clusters:
            continue  # Only include streets with known clusters

        building_tag = tags.get("building", "other")
        building_class = classify_building_tag(building_tag)

        if street not in street_counts:
            street_counts[street] = {
                "detached": 0,
                "semi_detached": 0,
                "rowhouse": 0,
                "mfh": 0,
                "other": 0,
            }

        street_counts[street][building_class] = street_counts[street].get(building_class, 0) + 1

        # Phase B Revised: separately count raw 'house' tag occurrences
        # These become detached in our output but may include real attached homes (H1 leakage)
        if building_tag.lower().strip() == "house":
            street_house_tags[street] = street_house_tags.get(street, 0) + 1

        # Range-filter: record per-building housenumber for cluster-scoped counting.
        housenumber = tags.get("addr:housenumber", "").strip()
        if street not in street_building_list:
            street_building_list[street] = []
        street_building_list[street].append({
            "housenumber": housenumber,
            "type": building_class,
        })

        # Collect PLZ votes from OSM tags — most reliable source
        postcode = tags.get("addr:postcode", "").strip()
        if postcode and postcode.isdigit() and len(postcode) == 5:
            if street not in street_plz_votes:
                street_plz_votes[street] = {}
            street_plz_votes[street][postcode] = street_plz_votes[street].get(postcode, 0) + 1

    logger.info(f"Aggregated building data for {len(street_counts)} streets.")

    # ROOT FIX (2026-07-13, KI-012): try the field_02-based path first (only
    # active for cities in _FIELD02_VALIDATED_CITIES — see that set's
    # docstring). new_counts is None for every other city, which runs the
    # legacy correction below UNCHANGED, exactly as before this fix.
    new_counts = _load_field02_street_counts(city_key)

    if new_counts is None:
        # LEGACY PATH — unchanged. Patch v2: geometry-based correction for
        # building=house misclassification (corrects detached overcounting
        # on streets like Am Mühlenweg). Patch v3: rescue building=yes /
        # building=residential from the Other bucket via footprint area +
        # levels. Ambiguous band (250-600 m², no clear level signal) stays
        # 'other'. Neither patch ever promotes a building to MFH from the
        # 'house' tag path — see core/street_building_types.py's docstring
        # for why that's exactly what KI-012 fixes for validated cities.
        street_counts, street_house_tags = correct_house_tags_by_adjacency(
            elements, street_counts, street_house_tags
        )
        street_counts = rescue_other_by_geometry(
            elements, street_counts, street_to_clusters
        )

    # 4. Build output records
    results = []
    for c in clusters_data:
        cluster_id = c["cluster_id"]
        street = c["primary_street"]
        house_range = c.get("house_range", "unknown")
        segment_id = c.get("segment_id", "")

        if new_counts is not None:
            # ROOT FIX (KI-012) path. segment_id is authoritative here — it
            # was assigned per-building from a REAL polygon-bounded
            # extraction (see generate_<city>_buildings.py), unlike the
            # legacy path's OSM-majority-vote (Bug A: voting across a bare
            # street name silently merges cross-PLZ / cross-town buildings
            # sharing that name). Parse it directly, no voting.
            plz = "UNKNOWN"
            if segment_id:
                parts = segment_id.split("_")
                for part in reversed(parts):
                    if part.isdigit() and len(part) == 5:
                        plz = part
                        break

            sc = new_counts.get((street, plz))
            if sc is not None:
                sfh_detached: int = int(sc["detached"])
                sfh_semi: int = int(sc["semi_detached"])
                sfh_row: int = int(sc["rowhouse"])
                mfh_count: int = int(sc["mfh"])
                other_count: int = int(sc["uncertain"])  # uncertain plays other's gate role (D-D)
            else:
                sfh_detached = sfh_semi = sfh_row = mfh_count = other_count = 0
        else:
            # --- LEGACY PLZ Resolution (Priority: OSM addr:postcode > segment_id parsing) ---
            # 1. OSM majority-vote PLZ (most reliable — directly from building tags)
            plz = "UNKNOWN"
            osm_votes = street_plz_votes.get(street)
            if osm_votes:
                plz = max(osm_votes, key=lambda p: osm_votes[p])

            # 2. Fallback: parse segment_id (e.g. NEUSS_OSM_41464 → 41464)
            if plz == "UNKNOWN" and segment_id:
                parts = segment_id.split("_")
                for part in reversed(parts):
                    if part.isdigit() and len(part) == 5:
                        plz = part
                        break

            # Get counts from Overpass aggregation (or zeroes if street not found)
            sc = street_counts.get(street)
            if sc is not None:
                sfh_detached: int = int(sc["detached"])
                sfh_semi: int = int(sc["semi_detached"])
                sfh_row: int = int(sc["rowhouse"])
                mfh_count: int = int(sc["mfh"])
                other_count: int = int(sc["other"])
            else:
                # Street not seen in Overpass data — explicit data gap, not an assumption
                sfh_detached = 0
                sfh_semi = 0
                sfh_row = 0
                mfh_count = 0
                other_count = 0

        sfh_total: int = sfh_detached + sfh_semi + sfh_row
        building_total: int = sfh_total + mfh_count + other_count

        # Use cluster-level lead_count as fallback total if Overpass returned nothing
        if building_total == 0:
            building_total = int(c.get("lead_count", 0))
            logger.debug(f"[{cluster_id}] No Overpass data for '{street}', using lead_count={building_total} as building_count_total")

        # --- Cluster-Scoped Building Count (range-filtered) ---
        # street_building_count = total buildings on the whole street (same as building_total)
        # cluster_building_count = buildings whose housenumber falls within this cluster's house_range
        # unaddressed_building_count = buildings that have addr:street but no addr:housenumber
        # address_filter_coverage = fraction of buildings that were range-filterable (quality signal)
        _blist = street_building_list.get(street, [])
        _street_total = len(_blist)  # should equal building_total for streets with Overpass data
        _cluster_count, _unaddressed, _ = _count_cluster_buildings(_blist, house_range)
        _addressable = _street_total - _unaddressed
        _coverage = round(_addressable / _street_total, 3) if _street_total > 0 else 0.0

        # When range is unparseable (house_range='unknown' or single address point),
        # cluster_building_count is None → downstream UI falls back to building_count_total.
        cluster_building_count = _cluster_count   # int or None
        street_building_count  = building_total   # always the full-street total
        unaddressed_building_count = _unaddressed
        address_filter_coverage    = _coverage

        # Task A: Cluster-scoped subtype counts (proportional scaling from post-correction aggregates).
        # These are ESTIMATES for multi-cluster streets; exact for single-cluster streets (ratio=1.0).
        # Correction algorithms (adjacency, rescue) modify street_counts at the aggregate level,
        # so per-building re-correction is not possible without architectural refactor.
        # The '~' prefix in UI chips already signals approximation to installers.
        if cluster_building_count is not None and building_total > 0:
            _scale_ratio = cluster_building_count / building_total
            cluster_sfh_detached_count = round(sfh_detached * _scale_ratio)
            cluster_sfh_semi_count     = round(sfh_semi     * _scale_ratio)
            cluster_sfh_rowhouse_count = round(sfh_row      * _scale_ratio)
        else:
            # Unparseable range → use whole-street counts as fallback
            cluster_sfh_detached_count = sfh_detached
            cluster_sfh_semi_count     = sfh_semi
            cluster_sfh_rowhouse_count = sfh_row

        if cluster_building_count is not None:
            logger.debug(
                f"[{cluster_id}] '{street}' range={house_range!r}: "
                f"cluster_count={cluster_building_count}/{_street_total} "
                f"(unaddressed={_unaddressed}, coverage={_coverage:.0%}) "
                f"EFH={cluster_sfh_detached_count} DHH={cluster_sfh_semi_count} RH={cluster_sfh_rowhouse_count}"
            )

        # Compute ratios safely
        if building_total > 0:
            sfh_total_ratio = round(sfh_total / building_total, 4)
            mfh_ratio = round(mfh_count / building_total, 4)
            other_ratio = round(other_count / building_total, 4)
        else:
            sfh_total_ratio = 0.0
            mfh_ratio = 0.0
            other_ratio = 0.0

        structure_profile = classify_structure_profile(sfh_total_ratio, mfh_ratio)
        gate_result, gate_reason = apply_structure_gate(mfh_ratio, sfh_total_ratio, other_ratio)
        execution_scale_flag = compute_execution_scale_flag(building_total)

        # Enhancement C: confidence metadata — descriptive only, no gate coupling
        street_confidence = compute_street_confidence(
            total_buildings=building_total,
            mfh_count=mfh_count,
            mfh_ratio=mfh_ratio,
            other_ratio=other_ratio,
        )

        # Layer 1.5: explanation metadata — descriptive only, no gate/ranking coupling
        explanation = generate_explanation(
            gate=gate_result,
            street_confidence=street_confidence,
            sfh_ratio=sfh_total_ratio,
            mfh_ratio=mfh_ratio,
            mfh_count=mfh_count,
            other_ratio=other_ratio,
            total_buildings=building_total,
        )

        # Phase B Revised: house tag count for this street
        house_tagged = street_house_tags.get(street, 0)

        # Phase B: fix subtype_confidence to use EXPLICIT subtype tags only
        # building=house routes to detached but is a generic tag — exclude it from specific count
        # explicit_detached = buildings tagged exactly 'detached' (not 'house')
        explicit_detached = max(0, sfh_detached - house_tagged)
        specific_sfh_count = explicit_detached + sfh_semi
        subtype_confidence = compute_subtype_confidence(sfh_total, specific_sfh_count)

        # Phase B Revised: attached_confidence — can we trust detached vs attached distinction?
        attached_confidence = compute_attached_confidence(sfh_total, house_tagged)

        # Patch v2 Step 3 — Advisory: detached count on this street is structurally suspect
        attached_risk_flag = compute_attached_risk_flag(attached_confidence, house_tagged, sfh_total)

        # Patch v2 Step 5 — Advisory: light small-MFH suspicion (annotation only, no scoring change)
        # NOTE: median_footprint_m2 is not available in this pipeline layer; set to None.
        # If the proxy layer (generate_decision_proxy.py) is joined downstream, this can be enriched.
        # For now the flag is False when footprint data is absent — no false positives.
        small_mfh_suspect = compute_small_mfh_suspect(
            attached_confidence, house_tagged, sfh_total, median_footprint_m2=None
        )

        record = {
            "cluster_id": cluster_id,
            "street_name": street,
            "plz": plz,
            "address_range": house_range,
            "building_count_total": building_total,
            "sfh_detached_count": sfh_detached,
            "sfh_semi_detached_count": sfh_semi,
            "sfh_rowhouse_count": sfh_row,
            "sfh_total_count": sfh_total,
            "sfh_total_ratio": sfh_total_ratio,
            "mfh_count": mfh_count,
            "mfh_ratio": mfh_ratio,
            "other_count": other_count,
            "other_ratio": other_ratio,
            "structure_profile": structure_profile,
            "structure_gate": gate_result,
            "gate_reason": gate_reason,
            "execution_scale_flag": execution_scale_flag,
            "subtype_confidence": subtype_confidence,
            "attached_confidence": attached_confidence,
            # Patch v2 advisory flags (additive — no existing field changed)
            "attached_risk_flag": attached_risk_flag,
            "small_mfh_suspect": small_mfh_suspect,
            # Enhancement C: descriptive reliability metadata (no gate coupling)
            "street_confidence": street_confidence,
            # --- Cluster-Scoped Count (range-filtered) ---
            # These fields fix the semantic mismatch where building_count_total
            # always reflected the full street, regardless of cluster house_range.
            # building_count_total is PRESERVED UNCHANGED for scoring backward compat.
            # UI and canvassing estimates should prefer cluster_building_count when available.
            "cluster_building_count":      cluster_building_count,      # int | None
            "street_building_count":       street_building_count,       # = building_count_total
            "unaddressed_building_count":  unaddressed_building_count,
            "address_filter_coverage":     address_filter_coverage,     # 0.0-1.0
            # --- Cluster-Scoped Subtype Counts (Task A: proportional from post-correction aggregate) ---
            # For 75% of v2 clusters: ratio=1.0, exact. For multi-cluster streets: scaled estimate.
            "cluster_sfh_detached_count": cluster_sfh_detached_count,
            "cluster_sfh_semi_count":     cluster_sfh_semi_count,
            "cluster_sfh_rowhouse_count": cluster_sfh_rowhouse_count,
            # Layer 1.5: explanation / sales translation metadata (no gate/ranking coupling)
            "top_reasons":         explanation["top_reasons"],
            "risk_flags":          explanation["risk_flags"],
            "recommended_action":  explanation["recommended_action"],
            "action_rationale":    explanation["action_rationale"],
            "sales_story":         explanation["sales_story"],
        }
        results.append(record)

    logger.info(f"Generated {len(results)} cluster records.")

    # 5. Write output
    out_dir = os.path.join(BASE_DIR, "output", "foundation")
    os.makedirs(out_dir, exist_ok=True)
    if args.out:
        out_path = args.out
    else:
        out_path = os.path.join(out_dir, "foundation_structure_results.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Summary log
    pass_count      = sum(1 for r in results if r["structure_gate"] == "PASS")
    qualified_count = sum(1 for r in results if r["structure_gate"] == "QUALIFIED")
    review_count    = sum(1 for r in results if r["structure_gate"] == "REVIEW")
    fail_count      = sum(1 for r in results if r["structure_gate"] == "FAIL")
    n = len(results)

    logger.info("=== Foundation Gate Summary ===")
    logger.info(f"  TOTAL    : {n}")
    logger.info(f"  PASS     : {pass_count}  ({pass_count/n:.1%})")
    logger.info(f"  QUALIFIED: {qualified_count}  ({qualified_count/n:.1%})")
    logger.info(f"  REVIEW   : {review_count}  ({review_count/n:.1%})")
    logger.info(f"  FAIL     : {fail_count}  ({fail_count/n:.1%})")
    logger.info(f"  Output   : {out_path}")


if __name__ == "__main__":
    main()

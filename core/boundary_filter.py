"""
core/boundary_filter.py
=======================
Strictly filters a territory cluster list to only those whose centroid lies
inside the Neuss administrative polygon (WGS84/EPSG:4326).

Design rules (enforced):
  - Polygon file is MANDATORY for trusted output. If missing/invalid → FAIL_CLOSED.
  - Uses ray-casting point-in-polygon. No street-name inference, no blacklists.
  - NULL / malformed coords → REJECTED_NULL_COORDS (never silently skipped).
  - Audit artifact written to output/boundary_audit/neuss_cluster_audit_latest.json
    (single overwrite file — no proliferation of per-render files).
  - All coordinate assumptions: EPSG:4326 (lon, lat order in GeoJSON, lat/lon in fields).
"""

from __future__ import annotations

import json
import os
import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BOUNDARY_PATH = os.path.join(
    _BASE_DIR, "config", "boundaries", "neuss_admin_boundary.geojson"
)

AUDIT_OUTPUT_PATH = os.path.join(
    _BASE_DIR, "output", "boundary_audit", "neuss_cluster_audit_latest.json"
)

# Verdict constants
VERDICT_KEPT               = "KEPT"
VERDICT_REJECTED           = "REJECTED"
VERDICT_REJECTED_NULL      = "REJECTED_NULL_COORDS"

STATUS_OK                  = "POLYGON_PIP_OK"
STATUS_FAIL_CLOSED         = "FAIL_CLOSED_POLYGON_UNAVAILABLE"

# ---------------------------------------------------------------------------
# GeoJSON polygon loader
# ---------------------------------------------------------------------------

def _load_polygon(geojson_path: str) -> list[tuple[float, float]] | None:
    """
    Load the first Polygon ring from a GeoJSON FeatureCollection.
    Returns a list of (lon, lat) tuples in EPSG:4326, or None on any error.

    GeoJSON spec: coordinates are [longitude, latitude].
    """
    if not os.path.exists(geojson_path):
        logger.error("[BoundaryFilter] GeoJSON file not found: %s", geojson_path)
        return None

    try:
        with open(geojson_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.error("[BoundaryFilter] Failed to parse GeoJSON: %s", exc)
        return None

    features = data.get("features", [])
    if not features:
        logger.error("[BoundaryFilter] GeoJSON has no features.")
        return None

    geometry = features[0].get("geometry", {})
    geom_type = geometry.get("type", "")

    if geom_type == "Polygon":
        coords = geometry.get("coordinates", [])
    elif geom_type == "MultiPolygon":
        # Take the largest ring (first polygon, first ring)
        coords = geometry.get("coordinates", [[[]]])[0]
    else:
        logger.error("[BoundaryFilter] Unsupported geometry type: %s", geom_type)
        return None

    if not coords:
        logger.error("[BoundaryFilter] Empty coordinates in GeoJSON.")
        return None

    exterior_ring = coords[0]  # list of [lon, lat]
    try:
        polygon = [(float(pt[0]), float(pt[1])) for pt in exterior_ring]
    except (IndexError, TypeError, ValueError) as exc:
        logger.error("[BoundaryFilter] Invalid coordinate format: %s", exc)
        return None

    if len(polygon) < 3:
        logger.error("[BoundaryFilter] Polygon has fewer than 3 vertices.")
        return None

    return polygon


# ---------------------------------------------------------------------------
# Ray-casting point-in-polygon
# ---------------------------------------------------------------------------

def _point_in_polygon(lat: float, lon: float,
                       polygon: list[tuple[float, float]]) -> bool:
    """
    Ray-casting algorithm for EPSG:4326 coordinates.

    polygon: list of (lon, lat) tuples (GeoJSON convention).
    Test point: (lon, lat) — converted internally.

    Returns True if the point is inside (or on the boundary of) the polygon.
    Edge/vertex cases: boundary points are treated as inside (inclusive).
    """
    x, y = lon, lat          # test point in (lon, lat) == (x, y) space
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]   # (lon, lat)
        xj, yj = polygon[j]

        # Check if point is exactly on a vertex → treat as inside
        if (xi == x and yi == y):
            return True

        # Standard ray-casting crossing test
        if ((yi > y) != (yj > y)):
            x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x <= x_intersect:
                inside = not inside

        j = i

    return inside


# ---------------------------------------------------------------------------
# Main filter function
# ---------------------------------------------------------------------------

def filter_clusters_to_neuss(
    cluster_list: list[dict[str, Any]],
    boundary_path: str = DEFAULT_BOUNDARY_PATH,
    source_file: str = "unknown",
) -> dict[str, Any]:
    """
    Filter a list of cluster dicts, keeping only those whose centroid is
    inside the Neuss administrative polygon.

    Returns a result dict:
    {
        "kept":          [list of kept cluster dicts],
        "rejected_ids":  [list of rejected cluster_id strings],
        "boundary_status": STATUS_OK | STATUS_FAIL_CLOSED,
        "cluster_verdicts": [list of per-cluster audit dicts],
        "meta": {
            "total_input":  int,
            "kept_count":   int,
            "rejected_count": int,
            "boundary_path": str,
            "boundary_method": str,
        }
    }

    FAIL_CLOSED behaviour:
      If the polygon cannot be loaded, this function returns ALL clusters as
      "UNVERIFIED" but sets boundary_status = STATUS_FAIL_CLOSED and kept = [].
      The caller must surface this status to the user — it must NOT proceed
      as if filtering succeeded.
    """
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(cluster_list)

    # --- 1. Load polygon ---
    polygon = _load_polygon(boundary_path)
    if polygon is None:
        logger.error("[BoundaryFilter] FAIL_CLOSED: polygon unavailable. No trusted output.")
        verdicts = [
            {
                "cluster_id":      c.get("cluster_id", "UNKNOWN"),
                "primary_street":  c.get("primary_street", ""),
                "lat":             c.get("cluster_centroid_lat"),
                "lon":             c.get("cluster_centroid_lon"),
                "verdict":         "UNVERIFIED",
                "rejection_reason": "POLYGON_UNAVAILABLE",
            }
            for c in cluster_list
        ]
        result = {
            "kept":              [],
            "rejected_ids":      [c.get("cluster_id", "?") for c in cluster_list],
            "boundary_status":   STATUS_FAIL_CLOSED,
            "cluster_verdicts":  verdicts,
            "meta": {
                "audit_timestamp":   timestamp,
                "source_file":       source_file,
                "total_input":       total,
                "kept_count":        0,
                "rejected_count":    total,
                "boundary_path":     boundary_path,
                "boundary_method":   STATUS_FAIL_CLOSED,
                "note":              "Trusted boundary filtering could not run. No clusters passed to UI.",
            },
        }
        _write_audit(result)
        return result

    # --- 2. Per-cluster PiP test ---
    kept:        list[dict] = []
    rejected_ids: list[str] = []
    verdicts:    list[dict] = []

    for cluster in cluster_list:
        cid    = cluster.get("cluster_id", "UNKNOWN")
        street = cluster.get("primary_street", "")
        raw_lat = cluster.get("cluster_centroid_lat")
        raw_lon = cluster.get("cluster_centroid_lon")

        # --- NULL / malformed coordinate guard ---
        try:
            lat = float(raw_lat)  # type: ignore[arg-type]
            lon = float(raw_lon)  # type: ignore[arg-type]
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                raise ValueError("Out of range")
        except (TypeError, ValueError):
            verdict_entry = {
                "cluster_id":      cid,
                "primary_street":  street,
                "lat":             raw_lat,
                "lon":             raw_lon,
                "verdict":         VERDICT_REJECTED_NULL,
                "rejection_reason": "NULL_OR_MALFORMED_COORDS",
            }
            verdicts.append(verdict_entry)
            rejected_ids.append(cid)
            logger.warning("[BoundaryFilter] %s rejected: NULL_OR_MALFORMED_COORDS (lat=%s lon=%s)",
                           cid, raw_lat, raw_lon)
            continue

        # --- PiP test ---
        inside = _point_in_polygon(lat, lon, polygon)

        if inside:
            kept.append(cluster)
            verdicts.append({
                "cluster_id":      cid,
                "primary_street":  street,
                "lat":             lat,
                "lon":             lon,
                "verdict":         VERDICT_KEPT,
                "rejection_reason": None,
            })
        else:
            rejected_ids.append(cid)
            verdicts.append({
                "cluster_id":      cid,
                "primary_street":  street,
                "lat":             lat,
                "lon":             lon,
                "verdict":         VERDICT_REJECTED,
                "rejection_reason": "OUTSIDE_NEUSS_BOUNDARY",
            })
            logger.info("[BoundaryFilter] %s (%s) REJECTED: centroid (%.5f, %.5f) outside Neuss.",
                        cid, street, lat, lon)

    result = {
        "kept":              kept,
        "rejected_ids":      rejected_ids,
        "boundary_status":   STATUS_OK,
        "cluster_verdicts":  verdicts,
        "meta": {
            "audit_timestamp":   timestamp,
            "source_file":       source_file,
            "total_input":       total,
            "kept_count":        len(kept),
            "rejected_count":    len(rejected_ids),
            "boundary_path":     boundary_path,
            "boundary_method":   "POLYGON_PIP",
            "note":              "Trusted polygon PiP filtering applied. Only in-boundary centroids passed.",
        },
    }

    _write_audit(result)
    return result


# ---------------------------------------------------------------------------
# Audit artifact emitter (single overwrite file)
# ---------------------------------------------------------------------------

def _write_audit(result: dict[str, Any]) -> None:
    """
    Write the audit artifact to AUDIT_OUTPUT_PATH (single latest file, overwrite).
    Failures are logged but never raised — audit writing cannot crash the UI.
    """
    audit_dir = os.path.dirname(AUDIT_OUTPUT_PATH)
    os.makedirs(audit_dir, exist_ok=True)

    audit_payload = {
        "audit_timestamp":    result["meta"]["audit_timestamp"],
        "boundary_status":    result["boundary_status"],
        "boundary_method":    result["meta"]["boundary_method"],
        "source_file":        result["meta"]["source_file"],
        "total_input_clusters": result["meta"]["total_input"],
        "kept":               result["meta"]["kept_count"],
        "rejected":           result["meta"]["rejected_count"],
        "note":               result["meta"].get("note", ""),
        "clusters":           result["cluster_verdicts"],
    }

    try:
        with open(AUDIT_OUTPUT_PATH, "w", encoding="utf-8") as fh:
            json.dump(audit_payload, fh, indent=2, ensure_ascii=False)
        logger.info("[BoundaryFilter] Audit artifact written to %s", AUDIT_OUTPUT_PATH)
    except Exception as exc:
        logger.error("[BoundaryFilter] Failed to write audit artifact: %s", exc)

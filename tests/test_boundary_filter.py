"""
tests/test_boundary_filter.py
==============================
Unit tests for core/boundary_filter.py

Covers mandatory acceptance criteria:
  1. Known Neuss centroid              → KEPT
  2. Known Düsseldorf centroid          → REJECTED (Himmelgeister Str. example)
  3. NULL / malformed coords            → REJECTED_NULL_COORDS
  4. Missing polygon file               → FAIL_CLOSED (boundary_status != STATUS_OK, kept=[])

Additional edge cases:
  5. Cluster with lon/lat exactly on polygon vertex → KEPT (inclusive boundary)
  6. Empty cluster list                 → handled gracefully, kept=[]
  7. Multiple clusters mixed in/out     → counts tally correctly
"""

import os
import sys
import json
import tempfile
import pytest

# Ensure project root is on path when running with pytest from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.boundary_filter import (
    filter_clusters_to_neuss,
    _point_in_polygon,
    _load_polygon,
    STATUS_OK,
    STATUS_FAIL_CLOSED,
    VERDICT_KEPT,
    VERDICT_REJECTED,
    VERDICT_REJECTED_NULL,
    DEFAULT_BOUNDARY_PATH,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cluster(cid: str, lat: float | None, lon: float | None,
                  street: str = "") -> dict:
    """Build a minimal cluster dict matching the JSON schema."""
    return {
        "cluster_id":           cid,
        "segment_id":           "TEST_SEG",
        "primary_street":       street,
        "house_range":          "1-10",
        "lead_count":           5,
        "A_count":              2,
        "B_count":              3,
        "cluster_centroid_lat": lat,
        "cluster_centroid_lon": lon,
    }


def _make_minimal_neuss_geojson(polygon_coords: list) -> dict:
    """Return a GeoJSON FeatureCollection with a single polygon."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "TestNeuss"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [polygon_coords],
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Reusable fixture: real boundary path
# ---------------------------------------------------------------------------

REAL_BOUNDARY = DEFAULT_BOUNDARY_PATH
BOUNDARY_EXISTS = os.path.exists(REAL_BOUNDARY)


# ---------------------------------------------------------------------------
# Test 1: Known Neuss centroid → KEPT
# ---------------------------------------------------------------------------

class TestKnownNeusCentroid:
    """
    Neuss city centre approx (51.198°N, 6.691°E).
    This point is unambiguously inside Neuss.
    """

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_neuss_centre_kept(self):
        cluster = _make_cluster("NEUSS_CENTRE", 51.198, 6.691, "Neuss Innenstadt")
        result  = filter_clusters_to_neuss([cluster], boundary_path=REAL_BOUNDARY)

        assert result["boundary_status"] == STATUS_OK, (
            "Expected POLYGON_PIP_OK but got: " + result["boundary_status"]
        )
        assert len(result["kept"]) == 1, "Neuss city centre cluster must be KEPT"
        kept_ids = [c.get("cluster_id") for c in result["kept"]]
        assert "NEUSS_CENTRE" in kept_ids

        # Verify per-cluster verdict
        verdict = next(v for v in result["cluster_verdicts"] if v["cluster_id"] == "NEUSS_CENTRE")
        assert verdict["verdict"] == VERDICT_KEPT
        assert verdict["rejection_reason"] is None


# ---------------------------------------------------------------------------
# Test 2: Known Düsseldorf centroid → REJECTED
# ---------------------------------------------------------------------------

class TestKnownDuesseldorfCentroid:
    """
    Himmelgeister Straße cluster centroids are at approx 51.190–51.193°N / 6.786–6.793°E.
    These must be rejected as outside Neuss.
    Test uses C_001 representative centroid from the real JSON.
    """

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_himmelgeister_str_rejected(self):
        # C_001 centroid from neuss_hybrid_clusters_v1.json
        cluster = _make_cluster("C_001", 51.19310983559077, 6.78756188655248,
                                 "Himmelgeister Straße")
        result  = filter_clusters_to_neuss([cluster], boundary_path=REAL_BOUNDARY)

        assert result["boundary_status"] == STATUS_OK
        assert len(result["kept"]) == 0, "Himmelgeister Str. (DUS) must be REJECTED"
        assert "C_001" in result["rejected_ids"]

        verdict = result["cluster_verdicts"][0]
        assert verdict["verdict"] == VERDICT_REJECTED
        assert verdict["rejection_reason"] == "OUTSIDE_NEUSS_BOUNDARY"

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_all_himmelgeister_parts_rejected(self):
        """C_001 through C_005 are all Himmelgeister Str. — all must be rejected."""
        him_clusters = [
            _make_cluster("C_001", 51.19310983559077, 6.78756188655248,  "Himmelgeister Straße"),
            _make_cluster("C_002", 51.192873416721106, 6.788498078329867, "Himmelgeister Straße"),
            _make_cluster("C_003", 51.19047769498238,  6.7885572253506075,"Himmelgeister Straße"),
            _make_cluster("C_004", 51.18887907648994,  6.790080484878274, "Himmelgeister Straße"),
            _make_cluster("C_005", 51.18784657862282,  6.791515174874518, "Himmelgeister Straße"),
        ]
        result = filter_clusters_to_neuss(him_clusters, boundary_path=REAL_BOUNDARY)

        assert result["boundary_status"] == STATUS_OK
        assert len(result["kept"]) == 0, "All Himmelgeister Str. clusters must be rejected"
        assert result["meta"]["rejected_count"] == 5
        assert result["meta"]["kept_count"] == 0

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_gladbacher_str_dusseldorf_rejected(self):
        """Gladbacher Str. (PLZ 40219) is in Düsseldorf, just across the river. MUST BE REJECTED."""
        cluster = _make_cluster("GLADBACHER_STR", 51.212270, 6.756041, "Gladbacher Straße")
        result = filter_clusters_to_neuss([cluster], boundary_path=REAL_BOUNDARY)
        
        assert len(result["kept"]) == 0, "Gladbacher Str. (DUS 40219) slipped through the polygon boundary filter!"
        assert "GLADBACHER_STR" in result["rejected_ids"]

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_volmerswerther_deich_dusseldorf_rejected(self):
        """Volmerswerther Deich (PLZ 40221) is directly on the DUS Rhine border. MUST BE REJECTED."""
        cluster = _make_cluster("VOLMERSWERTHER", 51.184661, 6.758288, "Volmerswerther Deich")
        result = filter_clusters_to_neuss([cluster], boundary_path=REAL_BOUNDARY)
        
        assert len(result["kept"]) == 0, "Volmerswerther Deich (DUS 40221) slipped through the polygon boundary filter!"
        assert "VOLMERSWERTHER" in result["rejected_ids"]

# ---------------------------------------------------------------------------
# Test 3: NULL / malformed coords → REJECTED_NULL_COORDS
# ---------------------------------------------------------------------------

class TestNullCoords:

    def _run_with_temp_polygon(self, cluster):
        """Use a small unit-square polygon so PiP tests pass without real file."""
        poly_coords = [
            [0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]
        ]
        geojson = _make_minimal_neuss_geojson(poly_coords)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(geojson, fh)
            tmp_path = fh.name
        try:
            return filter_clusters_to_neuss([cluster], boundary_path=tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_none_lat_rejected(self):
        cluster = _make_cluster("NULL_LAT", None, 6.69, "Test Street")
        result  = self._run_with_temp_polygon(cluster)
        assert len(result["kept"]) == 0
        assert result["cluster_verdicts"][0]["verdict"] == VERDICT_REJECTED_NULL
        assert result["cluster_verdicts"][0]["rejection_reason"] == "NULL_OR_MALFORMED_COORDS"

    def test_none_lon_rejected(self):
        cluster = _make_cluster("NULL_LON", 51.19, None, "Test Street")
        result  = self._run_with_temp_polygon(cluster)
        assert len(result["kept"]) == 0
        assert result["cluster_verdicts"][0]["verdict"] == VERDICT_REJECTED_NULL

    def test_string_coords_rejected(self):
        """Non-numeric string coords must be treated as malformed."""
        cluster = _make_cluster("BAD_COORDS", "NOT_A_NUMBER", "ALSO_BAD", "Test Street")
        result  = self._run_with_temp_polygon(cluster)
        assert len(result["kept"]) == 0
        assert result["cluster_verdicts"][0]["verdict"] == VERDICT_REJECTED_NULL

    def test_missing_coord_keys_rejected(self):
        """Cluster dict with no lat/lon keys at all → malformed."""
        cluster = {
            "cluster_id": "NO_COORDS",
            "segment_id": "TEST_SEG",
            "primary_street": "Missing Street",
            "lead_count": 5,
        }
        result = self._run_with_temp_polygon(cluster)
        assert len(result["kept"]) == 0
        assert result["cluster_verdicts"][0]["verdict"] == VERDICT_REJECTED_NULL

    def test_out_of_range_coords_rejected(self):
        """Coordinates outside WGS84 valid range are malformed."""
        cluster = _make_cluster("OOR_COORDS", 999.0, 999.0, "OOR Street")
        result  = self._run_with_temp_polygon(cluster)
        assert len(result["kept"]) == 0
        assert result["cluster_verdicts"][0]["verdict"] == VERDICT_REJECTED_NULL


# ---------------------------------------------------------------------------
# Test 4: Missing / invalid polygon file → FAIL_CLOSED
# ---------------------------------------------------------------------------

class TestMissingPolygon:

    def test_missing_geojson_fail_closed(self):
        """When polygon file doesn't exist, boundary_status = FAIL_CLOSED, kept = []."""
        cluster = _make_cluster("ANY_CLUSTER", 51.198, 6.691, "Test Street")
        result  = filter_clusters_to_neuss(
            [cluster],
            boundary_path="/nonexistent/path/to/boundary.geojson"
        )
        assert result["boundary_status"] == STATUS_FAIL_CLOSED
        assert len(result["kept"]) == 0, "Fail-closed: no clusters should pass when polygon unavailable"
        assert result["meta"]["kept_count"] == 0
        assert result["meta"]["rejected_count"] == 1

    def test_invalid_json_fail_closed(self):
        """A GeoJSON file with malformed JSON causes FAIL_CLOSED."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("{ this is not valid JSON !!!")
            tmp_path = fh.name
        try:
            cluster = _make_cluster("ANY_CLUSTER", 51.198, 6.691, "Test Street")
            result  = filter_clusters_to_neuss([cluster], boundary_path=tmp_path)
            assert result["boundary_status"] == STATUS_FAIL_CLOSED
            assert len(result["kept"]) == 0
        finally:
            os.unlink(tmp_path)

    def test_empty_features_fail_closed(self):
        """GeoJSON with zero features causes FAIL_CLOSED."""
        geojson = {"type": "FeatureCollection", "features": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(geojson, fh)
            tmp_path = fh.name
        try:
            cluster = _make_cluster("ANY", 51.198, 6.691, "Test Street")
            result  = filter_clusters_to_neuss([cluster], boundary_path=tmp_path)
            assert result["boundary_status"] == STATUS_FAIL_CLOSED
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test 5: Boundary-edge / vertex point → treated as INSIDE (inclusive)
# ---------------------------------------------------------------------------

class TestBoundaryEdgeCases:

    def _make_square_polygon(self) -> list:
        """Simple unit square: (0,0)→(1,0)→(1,1)→(0,1)→(0,0) in [lon, lat]."""
        return [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]

    def test_interior_point_inside(self):
        poly = self._make_square_polygon()
        assert _point_in_polygon(0.5, 0.5, poly) is True

    def test_exterior_point_outside(self):
        poly = self._make_square_polygon()
        assert _point_in_polygon(2.0, 2.0, poly) is False

    def test_exact_vertex_treated_as_inside(self):
        poly = self._make_square_polygon()
        # Point exactly at vertex (lon=0.0, lat=0.0)
        assert _point_in_polygon(0.0, 0.0, poly) is True


# ---------------------------------------------------------------------------
# Test 6: Empty cluster list → handled gracefully
# ---------------------------------------------------------------------------

class TestEmptyInput:

    @pytest.mark.skipif(not BOUNDARY_EXISTS,
                        reason="Real Neuss GeoJSON boundary not found – run from project root")
    def test_empty_list_no_crash(self):
        result = filter_clusters_to_neuss([], boundary_path=REAL_BOUNDARY)
        assert result["boundary_status"] == STATUS_OK
        assert result["kept"] == []
        assert result["meta"]["total_input"] == 0
        assert result["meta"]["kept_count"] == 0
        assert result["meta"]["rejected_count"] == 0


# ---------------------------------------------------------------------------
# Test 7: Mixed in/out counts tally correctly
# ---------------------------------------------------------------------------

class TestMixedClusters:

    def test_mixed_kept_rejected_counts(self):
        """Using a unit-square polygon: one inside, one outside, one null."""
        poly_coords = [
            [0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]
        ]
        geojson = _make_minimal_neuss_geojson(poly_coords)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(geojson, fh)
            tmp_path = fh.name

        clusters = [
            _make_cluster("INSIDE",  0.5,  0.5,  "Inside Street"),   # lat=0.5, lon=0.5
            _make_cluster("OUTSIDE", 2.0,  2.0,  "Outside Street"),  # outside square
            _make_cluster("NULL",    None, None, "Null Street"),      # null coords
        ]
        try:
            result = filter_clusters_to_neuss(clusters, boundary_path=tmp_path)
        finally:
            os.unlink(tmp_path)

        assert result["boundary_status"] == STATUS_OK
        assert result["meta"]["total_input"]    == 3
        assert result["meta"]["kept_count"]     == 1
        assert result["meta"]["rejected_count"] == 2

        kept_ids = [c["cluster_id"] for c in result["kept"]]
        assert "INSIDE"  in kept_ids
        assert "OUTSIDE" not in kept_ids
        assert "NULL"    not in kept_ids

        verdict_map = {v["cluster_id"]: v["verdict"] for v in result["cluster_verdicts"]}
        assert verdict_map["INSIDE"]  == VERDICT_KEPT
        assert verdict_map["OUTSIDE"] == VERDICT_REJECTED
        assert verdict_map["NULL"]    == VERDICT_REJECTED_NULL

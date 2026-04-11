import logging
from pathlib import Path

import pandas as pd
from shapely.strtree import STRtree
from shapely.wkt import loads as wkt_loads

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Field02_RealSource")

# ---------------------------------------------------------------------------
# Adjacency buffer constant.
#
# Patch v2 — Buffer Adoption (Step 2):
#   Expanded from 0.5 m (0.000005 deg) to 1.0 m (0.000009 deg).
#   Rationale: OSM footprint digitisation tolerance is typically 0.5–1 m;
#   rowhouses sharing a wall may not touch in the raw geometry.
#   1.0 m is the conservative winner selected from the buffer sensitivity audit.
#   To review alternatives, run: scripts/audit_buffer_sensitivity.py
#
# Patch v2 — Run-Length Recovery Hint (Step 4):
#   After adjacency classification, a lightweight chain-detection pass marks
#   buildings with row_recovery_hint=True when:
#     - They are in a chain of >= MIN_ROW_CHAIN_LEN similar-sized buildings
#       (footprint within CHAIN_FOOTPRINT_TOLERANCE of chain median)
#     - run_recovery_hint is advisory ONLY — it does NOT override the
#       adjacency-derived label unless adjacency already supports attached.
# ---------------------------------------------------------------------------

# Step 2: adopted buffer value (1.0 m conservative default from audit)
ADJACENCY_BUFFER_DEG = 0.000009  # ~1.0 m at Neuss latitude

# Step 4: run-length hint parameters
MIN_ROW_CHAIN_LEN         = 3     # minimum chain length to emit hint
CHAIN_FOOTPRINT_TOLERANCE = 0.30  # footprint must be within ±30% of chain median

# ---------------------------------------------------------------------------
# Stage 1 — OSM building tag → confirmed label (strong truth, fail-closed)
# These tag values come from buildings.parquet `building_type` column.
# Normalised values (e.g. rowhouse from terrace) are included.
# ---------------------------------------------------------------------------
STAGE1_MFH_CONFIRMED_TAGS: frozenset = frozenset({
    "apartments", "apartment",
    "flat", "dormitory",
    "residential_block", "block_of_flats",
})
STAGE1_SFH_CONFIRMED_TAGS: frozenset = frozenset({
    "detached", "detached_house",
    "semidetached_house", "semi",
    "terrace", "terraced_house",
    "rowhouse",   # normalised from OSM terrace in buildings.parquet
    "bungalow",
})
# Note: 'house', 'residential', 'yes', None → UNCERTAIN → Stage 2

# ---------------------------------------------------------------------------
# Stage 2 — Footprint × adjacency thresholds (Germany / Neuss calibrated)
# Used ONLY when Stage 1 tag is absent or ambiguous.
# Output is a WEAK label — does NOT enter conservative effective_sfh_share.
# ---------------------------------------------------------------------------
MFH_LARGE_FP_THR  = 450.0  # > 450 m²  → MFH_SUSPECT (very unlikely SFH)
MFH_MEDIUM_FP_THR = 250.0  # > 250 m² with ≥3 neighbors → MFH_SUSPECT
SFH_MAX_FP_THR    = 200.0  # ≤ 200 m²  → plausible SFH territory
SFH_ROW_FP_THR    = 150.0  # ≤ 150 m² with ≥2 neighbors → rowhouse-like


def _estimate_footprint_m2(geom) -> float:
    """
    Approximate footprint area in m² via local equirectangular projection.
    Used only for run-length similarity check — does not need to be exact.
    """
    try:
        cx = geom.centroid.x
        cy = geom.centroid.y
        import math
        scale_x = 111320.0 * math.cos(math.radians(cy))
        scale_y = 111320.0
        coords = list(geom.exterior.coords)
        pts = [(x * scale_x, y * scale_y) for x, y in coords]
        area = 0.0
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            area += pts[i][0] * pts[j][1]
            area -= pts[j][0] * pts[i][1]
        return abs(area) / 2.0
    except Exception:
        return 0.0


def _compute_run_length_hints(buildings: list[dict]) -> set:
    """
    Step 4 — Advisory run-length chain detection.

    Algorithm:
      1. For each building, check if it already has adjacency (neighbour >= 1).
      2. Group adjacent buildings into chains by sorting neighbour clusters
         along the dominant street axis (centroid X, proxy for E-W alignment).
      3. If chain length >= MIN_ROW_CHAIN_LEN and all footprints within
         CHAIN_FOOTPRINT_TOLERANCE of chain median → mark all members.

    Returns a set of building IDs where row_recovery_hint = True.

    Safety rules (semi-detached protection):
      - A chain of exactly 2 units is NOT marked (semi pair, not a row).
      - A building with neighbour_count == 0 whose only chain signal is
        run-length will NOT flip its label (hint only, no override).
    """
    import statistics

    # Build adjacency groups (union-find style, simple BFS)
    id_to_idx = {b["id"]: i for i, b in enumerate(buildings)}
    n = len(buildings)
    visited = [False] * n
    groups = []

    adj_set = [set() for _ in range(n)]
    for i, b in enumerate(buildings):
        for nb_idx in b.get("neighbour_indices", []):
            adj_set[i].add(nb_idx)
            adj_set[nb_idx].add(i)

    for start in range(n):
        if visited[start]:
            continue
        if not adj_set[start]:
            visited[start] = True
            continue  # isolated — no group
        group = []
        queue = [start]
        while queue:
            curr = queue.pop()
            if visited[curr]:
                continue
            visited[curr] = True
            group.append(curr)
            for nb in adj_set[curr]:
                if not visited[nb]:
                    queue.append(nb)
        if len(group) >= MIN_ROW_CHAIN_LEN:
            groups.append(group)

    hint_ids = set()
    for group in groups:
        fps = [buildings[i]["footprint_m2"] for i in group if buildings[i]["footprint_m2"] > 0]
        if not fps:
            continue
        median_fp = statistics.median(fps)
        if median_fp == 0:
            continue
        # Check all members are within tolerance
        coherent = all(
            abs(buildings[i]["footprint_m2"] - median_fp) / median_fp <= CHAIN_FOOTPRINT_TOLERANCE
            for i in group
            if buildings[i]["footprint_m2"] > 0
        )
        if coherent:
            for i in group:
                hint_ids.add(buildings[i]["id"])

    return hint_ids


def run(buildings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Field 02: Building Type Classification (Real-Source Upgrade).
    Uses spatial adjacency to determine neighbors.

    v2 changes:
      - Buffer expanded to 1.0 m (ADJACENCY_BUFFER_DEG).
      - row_recovery_hint added as advisory auxiliary field.
      - Main field_value logic unchanged in structure.
    """
    if buildings_df.empty:
        return pd.DataFrame()

    buildings = []
    for _, row in buildings_df.iterrows():
        try:
            geom = wkt_loads(row['geometry'])
            fp_m2 = _estimate_footprint_m2(geom)
            buildings.append({
                "id":            row['building_id'],
                "segment_id":    row['segment_id'],
                "geom":          geom,
                "footprint_m2":  fp_m2,
                "building_type": row.get('building_type'),  # raw OSM tag for Stage 1
                "neighbour_indices": [],  # populated below
            })
        except Exception:
            continue

    if not buildings:
        return pd.DataFrame()

    # Use STRtree for fast spatial queries
    geoms = [b['geom'] for b in buildings]
    tree = STRtree(geoms)

    # First pass: adjacency count + record neighbour indices for run-length
    for i, b in enumerate(buildings):
        possible = tree.query(b['geom'].buffer(ADJACENCY_BUFFER_DEG))
        neighbours = [idx for idx in possible if idx != i]
        b['neighbour_indices'] = neighbours
        b['neighbour_count']   = len(neighbours)

    # Run-length hint pass (Step 4 — advisory only)
    hint_ids = _compute_run_length_hints(buildings)
    logger.info(f"[Field02] run_recovery_hint set for {len(hint_ids)} buildings (chain >= {MIN_ROW_CHAIN_LEN}).")

    results = []
    for b in buildings:
        actual_neighbors = b['neighbour_count']
        osm_tag          = b.get('building_type')  # raw OSM tag (may be None)
        fp               = b['footprint_m2']
        row_recovery_hint = b["id"] in hint_ids

        # ── Stage 1: OSM tag strong truth ────────────────────────────────
        if osm_tag in STAGE1_MFH_CONFIRMED_TAGS:
            b_type     = "MFH_CONFIRMED"
            confidence = 0.90
            stage_used = 1
        elif osm_tag in STAGE1_SFH_CONFIRMED_TAGS:
            b_type     = "SFH_CONFIRMED"
            confidence = 0.90
            stage_used = 1
        else:
            # ── Stage 2: footprint × adjacency fallback ──────────────────
            # Output is a WEAK label; fail-closed (UNCERTAIN if ambiguous).
            stage_used = 2
            if fp > MFH_LARGE_FP_THR:
                b_type     = "MFH_SUSPECT"
                confidence = 0.70
            elif fp > MFH_MEDIUM_FP_THR and actual_neighbors >= 3:
                b_type     = "MFH_SUSPECT"
                confidence = 0.65
            elif fp <= SFH_MAX_FP_THR and actual_neighbors == 0:
                b_type     = "SFH_WEAK"
                confidence = 0.65
            elif fp <= SFH_MAX_FP_THR and actual_neighbors == 1:
                b_type     = "SFH_WEAK"
                confidence = 0.60
            elif fp <= SFH_ROW_FP_THR and actual_neighbors >= 2:
                b_type     = "SFH_WEAK"
                confidence = 0.55
            else:
                b_type     = "UNCERTAIN"
                confidence = 0.40

        results.append({
            "building_id":        b['id'],
            "segment_id":         b['segment_id'],
            "field_id":           "field_02",
            "field_value":        b_type,
            "confidence":         confidence,
            "source":             f"stage{stage_used}_adjacency_v2",
            "row_recovery_hint":  row_recovery_hint,
            "notes": (
                f"Stage {stage_used}: tag={osm_tag!r} neighbors={actual_neighbors} "
                f"footprint={fp:.1f}m² run_recovery_hint={row_recovery_hint}"
            )
        })

    return pd.DataFrame(results)


if __name__ == "__main__":
    base     = Path(__file__).resolve().parents[1]
    b_path   = base / "data" / "buildings.parquet"
    out_path = base / "data" / "fields" / "field_02_building_type.parquet"

    if not b_path.exists():
        logger.error(f"buildings.parquet not found at {b_path}")
    else:
        buildings_df = pd.read_parquet(b_path)
        # POINT-geometry segments are handled by patch_field_pipelines_point_geometry.py
        POINT_SEGS = {"NEUSS_SUBURB_01", "NEUSS_GRIML_01"}
        buildings_adj = buildings_df[~buildings_df["segment_id"].isin(POINT_SEGS)]
        logger.info(
            f"[MAIN] Running Stage 1/2 on {len(buildings_adj)} adjacency-path buildings "
            f"across segments: {buildings_adj['segment_id'].unique().tolist()}"
        )
        result = run(buildings_adj)

        # Preserve existing POINT-patch rows; replace adjacency-path rows
        if out_path.exists():
            existing = pd.read_parquet(out_path)
            existing = existing[existing["segment_id"].isin(POINT_SEGS)]
            combined = pd.concat([existing, result], ignore_index=True)
        else:
            combined = result

        combined.to_parquet(out_path, index=False)
        logger.info(f"[MAIN] Saved {len(combined)} rows to {out_path}")

        # Distribution audit log per segment
        for seg, grp in combined.groupby("segment_id"):
            vc = grp["field_value"].value_counts().to_dict()
            logger.info(f"  [{seg}] classification distribution: {vc}")

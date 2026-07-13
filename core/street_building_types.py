"""
street_building_types.py
=========================
Single source of truth for street-level SFH/MFH building-type counts and
the structural gate/profile derived from them.

ROOT FIX (2026-07-13, KI-012 / territoryai .ai/brief_foundation_data_quality.md)
----------------------------------------------------------------------------
Replaces `generate_foundation_layer.py`'s own independent building
extraction + classification for this specific purpose. That script had
THREE compounding defects, all found while investigating a user report
("Leipzig city-center apartment blocks show up as EFH/DHH", e.g.
Bünaustraße/Waldstraße):

  A. Cross-PLZ / cross-town street collapse: its `street_counts`/
     `street_plz_votes` were keyed by bare street NAME, not `(street, plz)`.
     A street spanning multiple real PLZ collapsed into one row at its
     plurality PLZ with a SUMMED count; the other portions vanished from
     the ranking entirely. WORSE: its own building extraction
     (`load_buildings_from_pbf`) filters only by rectangular bbox, not the
     real administrative boundary polygon — so a common German street name
     (Hauptstraße, Dorfstraße, ...) that also exists in a NEIGHBORING TOWN
     within the bbox gets silently merged with the real city's street of
     the same name. Quantified for Leipzig: 216 contaminated street names,
     5,840 out-of-city buildings merged in, 100 appearing in the actual
     ranked list, 53 currently gate PASS/QUALIFIED (active EFH targets).
  B. Misclassification: Foundation's own geometry classifier routes
     `building=house` (a generic OSM tag) straight to "detached" with no
     MFH exit — `correct_house_tags_by_adjacency` can only redistribute
     within {detached, semi_detached, rowhouse}, never to MFH. Dense
     Gründerzeit apartment blocks tagged `house` (or the ambiguous
     `yes`/`residential` bucket scored by `rescue_other_by_geometry`) get
     confidently mis-typed as SFH. Verified on Waldstraße 04105
     (Waldstraßenviertel, a dense Gründerzeit apartment district — ESRI
     satellite-confirmed zero detached houses): Foundation said 74
     detached vs 66 MFH; `field_02_building_type.py` (a separate,
     genuinely geometry-aware classifier already in the pipeline, using
     footprint area + OSM tag) correctly reads the same 76 buildings as
     62 MFH-leaning vs 7 SFH.

This module fixes all three by using the buildings parquet the caller
already produced with a REAL polygon-bounded extraction (not bbox-only)
as the building universe, `field_02_building_type.py`'s per-building
labels as the SFH/MFH classification (not Foundation's own), and
`(street, plz)` — not bare street name — as the aggregation key.

Design decisions (territoryai .ai/implementation_plan_foundation_classifier.md):
  D-A: building universe = the polygon-bounded `<city>_buildings.parquet`
       (excludes the ~60k/city no-addr:street structures Foundation's own
       bbox extraction also picks up — those can't be attributed to a
       named street anyway).
  D-B: field_02 is the single classification source of truth.
  D-C: SFH subtypes (detached/semi/row) for buildings whose raw OSM tag is
       explicit (`detached`, `semidetached_house`, `terrace`, ...) come
       straight from the tag. For buildings field_02 ALREADY confirmed are
       SFH-like but whose raw tag is ambiguous (`house`/`yes`/
       `residential`), this reuses Foundation's OWN adjacency-distance
       heuristic (0 neighbours -> detached, 1 -> semi_detached, >=2 ->
       rowhouse) to assign a subtype — same idea as
       `correct_house_tags_by_adjacency`, but gated correctly BEHIND
       field_02's SFH/MFH decision instead of running on every
       `house`-tagged building regardless of true type. This avoids adding
       a new "unspecified subtype" bucket that would require a schema
       migration across all 4 shipped cities.
  D-D: field_02 UNCERTAIN buildings are counted conservatively — not SFH,
       not MFH, in their own bucket, but included in ratio denominators
       (i.e. they play the same role `other_count` played in Foundation's
       original gate math: they dilute sfh_total_ratio, pushing an
       ambiguous street toward REVIEW rather than a confident PASS).
  D-E: `apply_structure_gate`/`classify_structure_profile` are UNCHANGED —
       moved here (from `generate_foundation_layer.py`, which now imports
       them back) purely to colocate them with the counts they gate, not
       to alter their thresholds/semantics. Still re-exported from
       `scripts.generate_foundation_layer` for existing importers
       (e.g. tests/test_foundation_gate_phase15.py).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger("STREET_BUILDING_TYPES")

# ---------------------------------------------------------------------------
# field_02 label groups
# ---------------------------------------------------------------------------
SFH_LIKE_LABELS = frozenset({"SFH_CONFIRMED", "SFH_WEAK"})
MFH_LIKE_LABELS = frozenset({"MFH_CONFIRMED", "MFH_SUSPECT"})
# Everything else (including a missing/unmatched field_02 row) is UNCERTAIN.

# ---------------------------------------------------------------------------
# Raw OSM subtype tags (explicit — trusted directly, no adjacency needed)
# ---------------------------------------------------------------------------
DETACHED_TAGS = frozenset({"detached"})
SEMI_DETACHED_TAGS = frozenset({"semidetached_house", "semi_detached", "semidetached"})
ROWHOUSE_TAGS = frozenset({"terrace", "terraced", "row_house", "rowhouse"})
# Ambiguous tags (house/yes/residential/anything else): for SFH-like
# buildings only, refined via the adjacency heuristic below.

# Matches generate_foundation_layer.py's _ADJACENCY_BUFFER_DEG (~1m) —
# reusing the same calibration, not re-tuning it.
_ADJACENCY_BUFFER_DEG = 0.000009

# ---------------------------------------------------------------------------
# Gate thresholds — MOVED from generate_foundation_layer.py (D-E). Values
# and semantics UNCHANGED; only the location moved so they live next to the
# counts they threshold. generate_foundation_layer.py re-imports these.
# ---------------------------------------------------------------------------
PASS_MAX_MFH_RATIO = 0.25
PASS_MIN_SFH_RATIO = 0.50
REVIEW_MAX_MFH_RATIO = 0.40
QUALIFIED_OTHER_THRESHOLD = 0.15
QUALIFIED_MIN_SFH_RATIO = 0.70


def classify_structure_profile(sfh_total_ratio: float, mfh_ratio: float) -> str:
    """Compute structure_profile. UNCHANGED from generate_foundation_layer.py."""
    if sfh_total_ratio >= 0.6 and mfh_ratio <= 0.25:
        return "SFH_DOMINANT"
    if mfh_ratio >= 0.4:
        return "MFH_HEAVY"
    return "MIXED_RESIDENTIAL"


def apply_structure_gate(
    mfh_ratio: float,
    sfh_total_ratio: float,
    other_ratio: float = 0.0,
) -> tuple[str, str]:
    """Apply the 4-tier structural gate. UNCHANGED from generate_foundation_layer.py
    (see that module's original docstring for the full tier rationale)."""
    if mfh_ratio > REVIEW_MAX_MFH_RATIO:
        return ("FAIL", "MFH_RATIO_TOO_HIGH")
    if mfh_ratio <= PASS_MAX_MFH_RATIO and sfh_total_ratio >= PASS_MIN_SFH_RATIO:
        if other_ratio >= QUALIFIED_OTHER_THRESHOLD:
            if sfh_total_ratio >= QUALIFIED_MIN_SFH_RATIO:
                return ("QUALIFIED", "LOW_MFH_STRONG_SFH_BUT_HIGH_OTHER")
            else:
                return ("REVIEW", "LOW_MFH_BORDERLINE_SFH_HIGH_OTHER")
        return ("PASS", "LOW_MFH_HIGH_SFH")
    return ("REVIEW", "BORDERLINE_MIXED_STREET")


# ---------------------------------------------------------------------------
# Adjacency-based subtype refinement (for SFH-like buildings with an
# ambiguous raw tag only — ported from generate_foundation_layer.py's
# correct_house_tags_by_adjacency, but gated behind field_02's SFH decision)
# ---------------------------------------------------------------------------

def _refine_ambiguous_sfh_subtypes(rows: pd.DataFrame) -> pd.Series:
    """
    For a set of SFH-like buildings (already filtered by field_02) whose raw
    OSM tag doesn't explicitly say detached/semi/row, use polygon adjacency
    to assign a subtype: 0 neighbours -> detached, 1 -> semi_detached,
    >=2 -> rowhouse. Returns a Series of {"detached","semi_detached","rowhouse"}
    aligned to `rows`' index. Buildings with unparseable geometry default to
    "detached" (isolated-by-default, matches Foundation's own fallback).
    """
    import shapely.wkt as shapely_wkt
    from shapely.strtree import STRtree

    geoms = []
    valid_idx = []
    for idx, wkt in rows["geometry"].items():
        try:
            g = shapely_wkt.loads(wkt)
            if not g.is_valid:
                g = g.buffer(0)
            geoms.append(g)
            valid_idx.append(idx)
        except Exception:
            continue

    result = pd.Series("detached", index=rows.index)
    if len(geoms) < 2:
        return result

    tree = STRtree(geoms)
    for i, idx in enumerate(valid_idx):
        candidates = tree.query(geoms[i].buffer(_ADJACENCY_BUFFER_DEG))
        neighbour_count = sum(1 for j in candidates if j != i)
        if neighbour_count >= 2:
            result.loc[idx] = "rowhouse"
        elif neighbour_count == 1:
            result.loc[idx] = "semi_detached"
        # else: stays "detached" (isolated, confirmed)
    return result


def _classify_subtype_tag(building_type: str) -> str | None:
    """Explicit-tag subtype lookup. Returns None if the tag is ambiguous
    (house/yes/residential/anything else) and needs adjacency refinement."""
    tag = str(building_type).lower().strip()
    if tag in DETACHED_TAGS:
        return "detached"
    if tag in SEMI_DETACHED_TAGS:
        return "semi_detached"
    if tag in ROWHOUSE_TAGS:
        return "rowhouse"
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_street_type_counts(
    buildings_df: pd.DataFrame,
    field02_df: pd.DataFrame,
) -> dict[tuple[str, str], dict]:
    """
    Recompute street-level SFH/MFH type counts, keyed by the REAL
    `(street, plz)` tuple (fixes Bug A/A-prime) using field_02 as the
    classification source of truth (fixes Bug B).

    Args:
        buildings_df: must have columns building_id, street, postal_code,
            geometry (WKT), building_type — i.e. a `<city>_buildings.parquet`
            already filtered to the real registered PLZ (polygon-bounded
            extraction, e.g. excludes segment_id == "<CITY>_OSM_GENERAL").
        field02_df: must have columns building_id, field_value
            (SFH_CONFIRMED/SFH_WEAK/MFH_CONFIRMED/MFH_SUSPECT/UNCERTAIN).

    Returns:
        dict[(street, plz)] -> {
            "detached": int, "semi_detached": int, "rowhouse": int,
            "mfh": int, "uncertain": int, "n_total": int,
            "sfh_total_ratio": float, "mfh_ratio": float,
            "uncertain_ratio": float,   # plays the role Foundation's
                                        # "other_ratio" played in gate math
        }
        A (street, plz) pair with zero buildings is simply absent — same
        "no data" contract as Foundation's original street_counts.
    """
    df = buildings_df.merge(
        field02_df[["building_id", "field_value"]], on="building_id", how="left"
    )
    n_unmatched = int(df["field_value"].isna().sum())
    if n_unmatched:
        logger.warning(
            f"[STREET_BUILDING_TYPES] {n_unmatched} buildings have no field_02 "
            f"label (not classified) — treating as UNCERTAIN, not silently dropped."
        )
    df["field_value"] = df["field_value"].fillna("UNCERTAIN")

    is_sfh = df["field_value"].isin(SFH_LIKE_LABELS)
    is_mfh = df["field_value"].isin(MFH_LIKE_LABELS)

    # Explicit-tag subtype for SFH rows; ambiguous ones marked for adjacency refinement.
    subtype = df["building_type"].map(_classify_subtype_tag)
    needs_refinement = is_sfh & subtype.isna()

    if needs_refinement.any():
        # Refine per (street, plz) group — adjacency is only meaningful
        # among buildings actually on the same real street.
        for key, idxs in df[needs_refinement].groupby(["street", "postal_code"]).groups.items():
            refined = _refine_ambiguous_sfh_subtypes(df.loc[idxs])
            subtype.loc[refined.index] = refined.values

    df["_subtype"] = subtype  # only meaningful where is_sfh is True

    results: dict[tuple[str, str], dict] = {}
    for (street, plz), grp in df.groupby(["street", "postal_code"]):
        n_total = len(grp)
        grp_sfh = grp[is_sfh.loc[grp.index]]
        detached = int((grp_sfh["_subtype"] == "detached").sum())
        semi = int((grp_sfh["_subtype"] == "semi_detached").sum())
        row = int((grp_sfh["_subtype"] == "rowhouse").sum())
        mfh = int(is_mfh.loc[grp.index].sum())
        uncertain = n_total - detached - semi - row - mfh

        sfh_total = detached + semi + row
        sfh_total_ratio = round(sfh_total / n_total, 4) if n_total else 0.0
        mfh_ratio = round(mfh / n_total, 4) if n_total else 0.0
        uncertain_ratio = round(uncertain / n_total, 4) if n_total else 0.0

        results[(street, str(plz))] = {
            "detached": detached,
            "semi_detached": semi,
            "rowhouse": row,
            "mfh": mfh,
            "uncertain": uncertain,
            "n_total": n_total,
            "sfh_total_ratio": sfh_total_ratio,
            "mfh_ratio": mfh_ratio,
            "uncertain_ratio": uncertain_ratio,
        }

    logger.info(
        f"[STREET_BUILDING_TYPES] Computed type counts for {len(results)} "
        f"(street, plz) pairs from {len(df)} buildings."
    )
    return results

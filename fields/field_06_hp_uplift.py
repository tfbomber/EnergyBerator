"""
field_06_hp_uplift.py
======================
Priority 2.5 — HP Opportunity Layer (v2)
D-ESS · Neuss MVP · KWP spatial join

ARCHITECTURE CHANGE v3 (2026-04-13 — Option A confirmed):
  Option A: hp_modifier = 1.00 for ALL labels.
    - HP opportunity label (STRONG/MODERATE/LIMITED/WEAK) is retained
      for UI display and sales narrative generation ONLY.
    - It does NOT modify base_score or final_score.
    - Rationale: hp_modifier values were uncalibrated design assumptions;
      ranking is cleanly driven by the 4 data-backed L2 inputs.
    - HP ROI economics are computed at customer level by the ROI engine,
      not pre-baked into segment ranking.

  MVP v1 contract restored:
    final_score_after_hp = adjusted_score (pass-through, unchanged)
    HP signals are UI/narrative-only.

Design principles:
  1. No double-penalty: Waerme_p is NOT used here (field_05 owns it).
  2. hp_opportunity_score is ADDITIVE information, not a ranking modifier.
  3. NULL RealChaKat -> excluded from score, confidence decremented (no fill).

Inputs (READ sources):
  - data/layer2/layer2_prio2_heat_overlay.parquet     (field_05 output — adjusted_score)
  - data/buildings.parquet                             (segment_id + lat/lon spatial bridge)
  - data/sources/waermenetz/sanierung_baublock_neuss_v1.parquet (Gas_p, Oel_p, RealChaKat)

Output:
  - data/layer2/layer2_prio25_hp_uplift.parquet        (backward-compat filename retained)

hp_opportunity_score formula:
  gas_oil_share  = (Gas_p + Oel_p) / 100          [0~1]  w = 0.50
  efh_rh_share   = (detached + rowhouse) / total  [0~1]  w = 0.33
  realcha_score  = encode(RealChaKat)              [0~1]  w = 0.17

  Weights renormalized if any signal is NULL/unavailable.

  hp_opportunity_score = weighted_mean(available_signals) * foundation_gate_proxy

Run:
  python fields/field_06_hp_uplift.py
  OR
  python scripts/field_06_hp_uplift.py  (symlinked)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("field_06_hp_opportunity")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE          = Path(__file__).resolve()
_BASE_DIR      = _HERE.parent.parent  if _HERE.parent.name in ("fields", "scripts") else _HERE.parent

OVERLAY_P      = _BASE_DIR / "data" / "layer2" / "layer2_prio2_heat_overlay.parquet"
BUILDINGS_P    = _BASE_DIR / "data" / "buildings.parquet"
BAUBLOCK_P     = _BASE_DIR / "data" / "sources" / "waermenetz" / "sanierung_baublock_neuss_v1.parquet"
OUTPUT_P       = _BASE_DIR / "data" / "layer2" / "layer2_prio25_hp_uplift.parquet"

SCHEMA_VERSION = "hp_opportunity_v2"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Weights (sum to 1.0 across all three signals)
W_GAS_OIL  = 0.50
W_EFH_RH   = 0.33
W_REALCHA  = 0.17

# EFH/RH building type keys in buildings.parquet
EFH_RH_TYPES = {"detached", "rowhouse", "DETACHED", "HOUSE"}

# RealChaKat ordinal encoding [0.0~1.0]
# Handles both clean and cp1252-corrupted versions of German umlauts
REALCHA_MAP: dict[str, float] = {
    # Clean UTF-8 versions
    "deutlich überdurchschnittlich":   1.00,
    "überdurchschnittlich":            0.75,
    "durchschnittlich":                0.50,
    "unterdurchschnittlich":           0.25,
    "deutlich unterdurchschnittlich":  0.00,
    # cp1252-corrupted variants (ü -> ü, ö -> ö etc.)
    "deutlich \xfcberdurchschnittlich":  1.00,
    "\xfcberdurchschnittlich":           0.75,
    "deutlich unterdurchschnittlich":    0.00,
    # Arrow-corrupted variants seen in Windows console output
    "deutlich ?berdurchschnittlich":   1.00,
    "?berdurchschnittlich":            0.75,
}

# HP Opportunity label thresholds
LABEL_THRESHOLDS = [
    (0.65, "STRONG"),
    (0.45, "MODERATE"),
    (0.25, "LIMITED"),
    (0.00, "WEAK"),
]

# ---------------------------------------------------------------------------
# HP ROI Multiplier — Option A (v3, 2026-04-13)
#
# ALL values are 1.00: HP opportunity does NOT modify the ranking score.
# Labels (STRONG/MODERATE/LIMITED/WEAK/UNKNOWN) are retained for:
#   - UI badge display in street_ranking_view
#   - Sales narrative generation (hp_narrative field)
#   - ROI report template routing (PV_HP_ENHANCED etc.)
#
# The previous values (STRONG=1.10, LIMITED=0.82, WEAK=0.77) were
# uncalibrated design assumptions inconsistent with the production ROI
# model (roi_hp_mvp_neuss_2026.json). Removed 2026-04-13.
# HP ROI effects are properly computed per-customer in the ROI engine.
# ---------------------------------------------------------------------------
HP_ROI_MULTIPLIER_MAP: dict[str, float] = {
    "STRONG":   1.00,
    "MODERATE": 1.00,
    "LIMITED":  1.00,
    "WEAK":     1.00,
    "UNKNOWN":  1.00,
}


# ---------------------------------------------------------------------------
# Step 1: Spatial join — building points -> Baublock -> Gas_p, Oel_p, RealChaKat
# ---------------------------------------------------------------------------
def compute_hp_signals_per_segment(
    buildings_parq: Path,
    baublock_parq: Path,
) -> dict[str, dict]:
    """
    Spatial join:
      buildings.parquet (lat/lon + segment_id) -> Baublock polygons
      Extract Gas_p, Oel_p, RealChaKat per building -> aggregate by segment.

    Returns dict: {segment_id: {gas_oil_share, realcha_score, spatial_coverage_ratio}}
    Note: EFH/RH share is computed separately from buildings.parquet metadata.
    """
    try:
        import geopandas as gpd
    except ImportError:
        log.error("[SPATIAL] geopandas not installed. Run: pip install geopandas")
        sys.exit(1)

    log.info(f"[SPATIAL] Loading buildings: {buildings_parq}")
    bldg_df = pd.read_parquet(buildings_parq)

    log.info(f"[SPATIAL] Loading Baublock: {baublock_parq}")
    baublock_gdf = gpd.read_parquet(baublock_parq)
    if str(baublock_gdf.crs.to_epsg()) != "25832":
        baublock_gdf = baublock_gdf.to_crs(epsg=25832)

    # Build point GeoDataFrame
    bldg_gdf = gpd.GeoDataFrame(
        bldg_df[["segment_id", "lat", "lon"]].copy(),
        geometry=gpd.points_from_xy(bldg_df["lon"], bldg_df["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=25832)

    log.info(f"[SPATIAL] Joining {len(bldg_gdf)} building points x {len(baublock_gdf)} blocks...")
    join_cols = ["Gas_p", "Oel_p"]
    if "RealChaKat" in baublock_gdf.columns:
        join_cols.append("RealChaKat")

    joined = gpd.sjoin(
        bldg_gdf,
        baublock_gdf[join_cols + ["geometry"]],
        how="left",
        predicate="within",
    )

    hit_count = joined["index_right"].notna().sum()
    log.info(f"[SPATIAL] Join: {hit_count}/{len(bldg_gdf)} buildings matched")

    results: dict[str, dict] = {}
    for seg_id in bldg_df["segment_id"].unique():
        seg_rows = joined[joined["segment_id"] == seg_id]
        hits     = seg_rows[seg_rows["index_right"].notna()]

        total_bldgs = len(seg_rows)
        hit_bldgs   = len(hits)
        coverage    = round(hit_bldgs / total_bldgs, 3) if total_bldgs > 0 else 0.0

        if hits.empty:
            results[str(seg_id)] = {
                "gas_oil_share":          None,
                "realcha_score":          None,
                "spatial_coverage_ratio": 0.0,
                "data_source":            "KWP_spatial_join_MISS",
            }
            log.warning(f"[SPATIAL] segment={seg_id}: no baublock hit -> NULL signals")
        else:
            gas_oil_pct = hits["Gas_p"].mean() + hits["Oel_p"].mean()
            gas_oil_share = round(min(gas_oil_pct / 100.0, 1.0), 4)

            # Encode RealChaKat per building, then mean
            realcha_score = None
            if "RealChaKat" in hits.columns:
                encoded = hits["RealChaKat"].map(
                    lambda v: _encode_realchaKat(str(v)) if pd.notna(v) else None
                ).dropna()
                if len(encoded) > 0:
                    realcha_score = round(float(encoded.mean()), 4)
                # If all NULL -> realcha_score stays None (confidence hit in build step)

            results[str(seg_id)] = {
                "gas_oil_share":          gas_oil_share,
                "realcha_score":          realcha_score,
                "spatial_coverage_ratio": coverage,
                "data_source":            "KWP_spatial_join",
            }
            log.info(
                f"[SPATIAL] segment={seg_id}: "
                f"gas_oil={gas_oil_share:.2f}  "
                f"realcha={realcha_score}  "
                f"coverage={coverage:.2f} ({hit_bldgs}/{total_bldgs})"
            )

    return results


def _encode_realchaKat(val: str) -> float | None:
    """Encode RealChaKat string to [0.0, 1.0]. Returns None if unrecognized."""
    if val in ("<NULL>", "None", "nan", ""):
        return None
    # Try exact match first
    if val in REALCHA_MAP:
        return REALCHA_MAP[val]
    # Fuzzy match: check if key is a substring of val (handles minor encoding corruption)
    val_lower = val.lower().strip()
    for key, score in REALCHA_MAP.items():
        if key.lower().strip() in val_lower:
            return score
    log.warning(f"[ENCODE] Unrecognized RealChaKat value: '{val}' -> NULL")
    return None


# ---------------------------------------------------------------------------
# Step 2: Compute EFH/RH share from buildings.parquet
# ---------------------------------------------------------------------------
def compute_efh_rh_share(buildings_parq: Path) -> dict[str, float | None]:
    """
    Compute % of EFH/RH buildings per segment directly from buildings.parquet.
    building_type = 'detached' or 'rowhouse' -> EFH/RH candidate.
    """
    bldg_df = pd.read_parquet(buildings_parq, columns=["segment_id", "building_type"])

    results: dict[str, float | None] = {}
    for seg_id, grp in bldg_df.groupby("segment_id"):
        total = len(grp)
        if total == 0:
            results[str(seg_id)] = None
            continue
        efh_rh_count = grp["building_type"].isin(EFH_RH_TYPES).sum()
        share = round(efh_rh_count / total, 4)
        results[str(seg_id)] = share
        log.info(f"[EFH_RH] segment={seg_id}: efh_rh_share={share:.2%} ({efh_rh_count}/{total})")

    return results


# ---------------------------------------------------------------------------
# Step 3: Compute hp_opportunity_score with renormalized weights
# ---------------------------------------------------------------------------
def compute_hp_score(
    gas_oil_share: float | None,
    efh_rh_share: float | None,
    realcha_score: float | None,
) -> tuple[float | None, float, list[str]]:
    """
    Compute weighted hp_opportunity_score. Renormalize weights when any signal is None.
    Principle: NULL signals -> excluded from score + confidence penalty.

    Returns:
      (hp_opportunity_score, hp_confidence, missing_signals)
    """
    signal_config = [
        ("gas_oil_share", gas_oil_share, W_GAS_OIL),
        ("efh_rh_share",  efh_rh_share,  W_EFH_RH),
        ("realcha_score", realcha_score,  W_REALCHA),
    ]

    available = [(name, val, w) for name, val, w in signal_config if val is not None]
    missing   = [name for name, val, _ in signal_config if val is None]

    if not available:
        return None, 0.20, missing

    # Renormalize weights
    total_w = sum(w for _, _, w in available)
    score = sum(val * (w / total_w) for _, val, w in available)
    score = round(score, 4)

    # Confidence: starts at 0.90, each missing signal costs 0.15
    confidence = round(max(0.20, 0.90 - len(missing) * 0.15), 2)

    return score, confidence, missing


# ---------------------------------------------------------------------------
# Step 4: Assign label and narrative
# ---------------------------------------------------------------------------
def assign_label(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    for threshold, label in LABEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "WEAK"


def generate_hp_narrative(
    label: str,
    seg_id: str,
    gas_oil_share: float | None,
    efh_rh_share: float | None,
    realcha_score: float | None,
) -> str:
    """Generate German sales narrative for HP opportunity."""
    gas_oil_pct = f"{gas_oil_share*100:.0f}%" if gas_oil_share is not None else "unbekannt"
    efh_pct     = f"{efh_rh_share*100:.0f}%" if efh_rh_share is not None else "unbekannt"

    if label == "STRONG":
        return (
            f"Segment {seg_id}: Ausgezeichnetes WP-Potential. "
            f"{gas_oil_pct} der Gebaeude nutzen Gas/Oel (direkte WP-Abloesung), "
            f"{efh_pct} sind EFH/RH (optimale WP-Gebaeudekategorie)."
        )
    if label == "MODERATE":
        return (
            f"Segment {seg_id}: Gutes WP-Potential. "
            f"{gas_oil_pct} Gas/Oel-Anteil. Gemischte Bebauung, "
            f"gezielte Ansprache von EFH-Eigentuemern empfohlen."
        )
    if label == "LIMITED":
        return (
            f"Segment {seg_id}: Eingeschraenktes WP-Potential. "
            f"{gas_oil_pct} Gas/Oel, {efh_pct} EFH/RH. "
            f"WP als Zusatzargument, nicht als Primaerprodukt positionieren."
        )
    if label == "WEAK":
        return (
            f"Segment {seg_id}: Geringes WP-Potential. "
            f"Gas/Oel-Anteil niedrig oder hoher MFH-Anteil. "
            f"PV-Fokus empfohlen, WP nur auf explizite Nachfrage."
        )
    return f"Segment {seg_id}: WP-Potential nicht bestimmbar (unzureichende Datenlage)."


# ---------------------------------------------------------------------------
# Step 5: Build output table
# ---------------------------------------------------------------------------
def build_hp_opportunity(
    p2_df: pd.DataFrame,
    spatial_results: dict[str, dict],
    efh_rh_map: dict[str, float | None],
) -> pd.DataFrame:
    """
    Build HP opportunity table.

    v2 contract (Option C, 2026-04-12):
      - hp_roi_multiplier is applied to base_score -> drives final_score_after_hp
      - MVP v1 pass-through contract is RETIRED
      - Causal chain: Fernwarme -> limited HP -> low self-consumption -> lower PV ROI
        is now captured here, not in field_05
    """
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    for _, p2_row in p2_df.iterrows():
        unit_id   = str(p2_row["unit_id"])
        usable    = bool(p2_row["row_usable_for_ranking"])
        adj_score = float(p2_row["adjusted_score"]) if pd.notna(p2_row.get("adjusted_score")) else None

        if not usable:
            rows.append({
                "unit_id":                    unit_id,
                "row_usable_for_ranking":     usable,
                "prio2_adjusted_score":       adj_score,
                "hp_opportunity_score":       None,
                "hp_opportunity_label":       "NOT_APPLICABLE",
                "hp_confidence":              None,
                "gas_oil_share_weighted":     None,
                "efh_rh_share":               None,
                "realcha_score_encoded":      None,
                "spatial_coverage_ratio":     None,
                "missing_signals":            None,
                "hp_narrative":               "Synthetic row — excluded from HP opportunity scoring.",
                "hp_modifier":                None,        # retained for backward compat
                "final_score_after_hp":       None,        # retained for backward compat
                "schema_version":             SCHEMA_VERSION,
                "build_timestamp_utc":        run_ts,
            })
            continue

        # Pull spatial signals
        sj            = spatial_results.get(unit_id, {})
        gas_oil_share = sj.get("gas_oil_share")
        realcha_score = sj.get("realcha_score")
        efh_rh_share  = efh_rh_map.get(unit_id)
        coverage      = sj.get("spatial_coverage_ratio", 0.0)

        # Compute score
        hp_score, confidence, missing = compute_hp_score(
            gas_oil_share, efh_rh_share, realcha_score
        )

        # Reduce confidence for low spatial coverage
        if coverage < 0.30 and hp_score is not None:
            confidence = round(confidence * 0.70, 2)
            log.warning(
                f"[HP] {unit_id}: low spatial coverage ({coverage:.0%}) "
                f"-> confidence reduced to {confidence:.2f}"
            )

        label     = assign_label(hp_score)
        narrative = generate_hp_narrative(
            label, unit_id, gas_oil_share, efh_rh_share, realcha_score
        )

        # Option C: hp_roi_multiplier is the single ROI adjustment point
        hp_roi_mult = HP_ROI_MULTIPLIER_MAP.get(label, 0.93)
        final_score = round(adj_score * hp_roi_mult, 4) if adj_score is not None else None

        log.info(
            f"[HP] {unit_id}: gas_oil={gas_oil_share}  efh_rh={efh_rh_share}  "
            f"realcha={realcha_score}  score={hp_score}  label={label}  conf={confidence}  "
            f"roi_mult=x{hp_roi_mult}  final={final_score}"
        )

        rows.append({
            "unit_id":                    unit_id,
            "row_usable_for_ranking":     usable,
            "prio2_adjusted_score":       adj_score,
            "hp_opportunity_score":       hp_score,
            "hp_opportunity_label":       label,
            "hp_roi_multiplier":          hp_roi_mult,
            "hp_confidence":              confidence,
            "gas_oil_share_weighted":     gas_oil_share,
            "efh_rh_share":               efh_rh_share,
            "realcha_score_encoded":      realcha_score,
            "spatial_coverage_ratio":     coverage,
            "missing_signals":            ",".join(missing) if missing else "",
            "hp_narrative":               narrative,
            "hp_modifier":                hp_roi_mult,   # backward compat alias
            "final_score_after_hp":       final_score,   # v2: base x hp_roi_multiplier
            "schema_version":             SCHEMA_VERSION,
            "build_timestamp_utc":        run_ts,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> None:
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("=== field_06_hp_opportunity START · %s ===", run_ts)

    # Guard: required inputs
    for path, label in [
        (OVERLAY_P,   "field_05 heat overlay"),
        (BUILDINGS_P, "buildings (spatial bridge)"),
        (BAUBLOCK_P,  "sanierung_baublock (KWP)"),
    ]:
        if not path.exists():
            log.error("[GUARD] Missing required input: %s  (%s)", path, label)
            sys.exit(1)

    # Phase 1: Load field_05 output
    log.info("Loading P2 overlay: %s", OVERLAY_P)
    p2_df = pd.read_parquet(OVERLAY_P)
    log.info("P2 overlay: %d rows, usable=%d", len(p2_df), p2_df["row_usable_for_ranking"].sum())

    # Confirm required column
    if "adjusted_score" not in p2_df.columns:
        log.error("[GUARD] P2 overlay missing 'adjusted_score'. Run field_05 first.")
        sys.exit(1)

    # Phase 2: Spatial join -> Gas/Oil share + RealChaKat per segment
    spatial_results = compute_hp_signals_per_segment(BUILDINGS_P, BAUBLOCK_P)

    # Phase 3: EFH/RH share from buildings.parquet
    efh_rh_map = compute_efh_rh_share(BUILDINGS_P)

    # Phase 4: Build HP opportunity table
    out_df = build_hp_opportunity(p2_df, spatial_results, efh_rh_map)

    # Sanity check v2 (Option C): final_score_after_hp = prio2_adjusted_score x hp_roi_multiplier
    # MVP v1 pass-through contract is RETIRED.
    usable = out_df[out_df["row_usable_for_ranking"].astype(bool)]
    violations = usable[
        (usable["final_score_after_hp"].notna()) &
        (usable["prio2_adjusted_score"].notna()) &
        (usable["hp_roi_multiplier"].notna()) &
        (
            (usable["final_score_after_hp"] -
             (usable["prio2_adjusted_score"] * usable["hp_roi_multiplier"]).round(4)
            ).abs() > 1e-4
        )
    ]
    if len(violations) > 0:
        log.error(
            "[SANITY FAIL] v2 contract violated: final_score_after_hp != base x multiplier "
            "for %d rows.", len(violations)
        )
        sys.exit(1)
    log.info("[SANITY] v2 contract verified: final_score_after_hp = base x hp_roi_multiplier for all rows.")

    # Write output
    OUTPUT_P.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUTPUT_P, index=False)
    log.info("Output written: %s (%d rows)", OUTPUT_P, len(out_df))

    # Summary
    print("\n--- HP Opportunity Layer v2 Summary (Option C) ---")
    summary_cols = [
        "unit_id", "prio2_adjusted_score", "hp_opportunity_label",
        "hp_opportunity_score", "hp_roi_multiplier", "hp_confidence",
        "gas_oil_share_weighted", "efh_rh_share", "final_score_after_hp",
    ]
    avail = [c for c in summary_cols if c in out_df.columns]
    usable_summary = out_df[out_df["row_usable_for_ranking"].astype(bool)][avail]
    print(usable_summary.to_string(index=False))

    print("\n--- HP Narratives ---")
    for _, r in usable_summary.iterrows():
        uid = r["unit_id"]
        narrative = out_df[out_df["unit_id"] == uid]["hp_narrative"].values[0]
        print(f"  [{r['hp_opportunity_label']:<8}] {uid}: {narrative}")
    print("---------------------------------------\n")

    log.info("=== field_06_hp_opportunity COMPLETE ===")


if __name__ == "__main__":
    run()

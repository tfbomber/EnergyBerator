"""
audit_buffer_sensitivity.py
============================
Step 1 — Buffer Sensitivity Dry Audit (READ-ONLY).

Purpose:
    Compare adjacency classification outcomes across three buffer values:
      - 0.5 m (current baseline) ~ 0.000005 deg
      - 1.0 m                    ~ 0.000009 deg
      - 1.5 m                    ~ 0.000015 deg

    For each buffer, counts how many buildings land in:
      detached / semi / rowhouse / suspicious-adjacency

    Decision rule:
      "Choose the smallest buffer where:
          net_recovery_rate >= 0.85
          AND suspicious_adjacency_rate < 0.05"

    Suspicious adjacency = a building larger than LARGE_FOOTPRINT_M2 that
    gains a neighbour only at the wider buffer (likely a false attachment
    between truly isolated large buildings).

Output:
    Prints a side-by-side audit table to stdout.
    Does NOT write or mutate any production file.

Usage:
    python audit_buffer_sensitivity.py

Input:
    data/buildings.parquet   (must exist)
    Columns required: building_id, segment_id, geometry (WKT), footprint_m2 (optional)
"""

import os
import sys
import logging
import pandas as pd
from shapely.wkt import loads as wkt_loads
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("BufferSensitivityAudit")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDINGS_PATH = os.path.join(BASE_DIR, "data", "buildings.parquet")

# Buffer candidates in degrees (1 deg lon ~ 111,320 m at Neuss latitude)
BUFFER_CANDIDATES = {
    "0.5m": 0.000005,
    "1.0m": 0.000009,
    "1.5m": 0.000015,
}

# Footprint threshold for suspicious-adjacency check (m²).
# Buildings above this are assumed to be detached on large lots.
# A new neighbour at wider buffer is likely a false attachment.
LARGE_FOOTPRINT_M2 = 400.0

# Decision thresholds
MIN_NET_RECOVERY_RATE = 0.85   # (Δsemi + Δrow) / Δdetached must exceed this
MAX_SUSPICIOUS_RATE   = 0.05   # suspicious / Δdetached must stay below this


def load_buildings() -> list[dict]:
    """Load buildings.parquet and parse geometry WKT."""
    if not os.path.exists(BUILDINGS_PATH):
        logger.error(f"buildings.parquet not found at: {BUILDINGS_PATH}")
        sys.exit(1)

    df = pd.read_parquet(BUILDINGS_PATH)
    logger.info(f"Loaded {len(df)} buildings from parquet.")

    buildings = []
    for _, row in df.iterrows():
        try:
            geom = wkt_loads(row["geometry"])
            buildings.append({
                "id":           row["building_id"],
                "segment_id":   row["segment_id"],
                "geom":         geom,
                "footprint_m2": float(row["footprint_m2"]) if "footprint_m2" in row and pd.notna(row["footprint_m2"]) else None,
            })
        except Exception:
            continue

    logger.info(f"Parsed {len(buildings)} valid geometries.")
    return buildings


def classify_at_buffer(buildings: list[dict], buffer_deg: float) -> list[dict]:
    """
    Classify each building as detached / semi / rowhouse
    using the given adjacency buffer.
    Returns list of dicts: {id, neighbour_count, label, footprint_m2}
    """
    geoms = [b["geom"] for b in buildings]
    tree = STRtree(geoms)

    results = []
    for i, b in enumerate(buildings):
        idxs = tree.query(b["geom"].buffer(buffer_deg))
        neighbours = sum(1 for idx in idxs if idx != i)

        if neighbours == 0:
            label = "detached"
        elif neighbours == 1:
            label = "semi"
        else:
            label = "rowhouse"

        results.append({
            "id":            b["id"],
            "neighbour_count": neighbours,
            "label":         label,
            "footprint_m2":  b.get("footprint_m2"),
        })
    return results


def summarise(results: list[dict]) -> dict:
    det = sum(1 for r in results if r["label"] == "detached")
    sem = sum(1 for r in results if r["label"] == "semi")
    row = sum(1 for r in results if r["label"] == "rowhouse")
    return {"detached": det, "semi": sem, "rowhouse": row, "total": len(results)}


def compute_suspicious(baseline_map: dict, candidate_results: list[dict]) -> int:
    """
    Count buildings that:
      - were detached at baseline (0.5m)
      - gained a neighbour at the candidate buffer
      - have footprint_m2 > LARGE_FOOTPRINT_M2  (likely false attachment)
    """
    sus = 0
    for r in candidate_results:
        bid = r["id"]
        was_detached = baseline_map.get(bid, {}).get("label") == "detached"
        now_attached = r["label"] in ("semi", "rowhouse")
        fp = r["footprint_m2"]
        if was_detached and now_attached and fp is not None and fp > LARGE_FOOTPRINT_M2:
            sus += 1
    return sus


def main():
    logger.info("=== Buffer Sensitivity Dry Audit (READ-ONLY) ===")
    buildings = load_buildings()

    all_results = {}
    for label, buf in BUFFER_CANDIDATES.items():
        logger.info(f"Classifying at buffer {label} ({buf:.6f} deg) ...")
        all_results[label] = classify_at_buffer(buildings, buf)

    baseline_map = {r["id"]: r for r in all_results["0.5m"]}

    summaries = {k: summarise(v) for k, v in all_results.items()}

    base = summaries["0.5m"]

    # --- Print audit table ---
    header = f"{'Buffer':<8} {'Detached':>10} {'Semi':>8} {'Row':>8} {'Δ_det':>8} {'Δ_semi':>8} {'Δ_row':>8} {'Suspicious':>12} {'RecRate':>9} {'SusRate':>9} {'Decision':>12}"
    print("\n" + "=" * len(header))
    print("BUFFER SENSITIVITY AUDIT — Neuss Building Classification")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    candidates_checked = []
    for buf_label, buf_deg in BUFFER_CANDIDATES.items():
        s = summaries[buf_label]
        d_det = base["detached"] - s["detached"]   # how many detached were recovered
        d_sem = s["semi"]       - base["semi"]
        d_row = s["rowhouse"]   - base["rowhouse"]
        sus   = compute_suspicious(baseline_map, all_results[buf_label])

        rec_rate = (d_sem + d_row) / d_det if d_det > 0 else float("nan")
        sus_rate = sus / d_det if d_det > 0 else float("nan")

        passes = (
            rec_rate >= MIN_NET_RECOVERY_RATE and
            sus_rate < MAX_SUSPICIOUS_RATE
        ) if d_det > 0 else (buf_label == "0.5m")

        decision = "CANDIDATE" if passes else "SKIP"
        if buf_label == "0.5m":
            decision = "BASELINE"

        candidates_checked.append((buf_label, passes, rec_rate, sus_rate))

        print(
            f"{buf_label:<8} {s['detached']:>10} {s['semi']:>8} {s['rowhouse']:>8}"
            f" {d_det:>8} {d_sem:>8} {d_row:>8} {sus:>12}"
            f" {rec_rate:>9.2f} {sus_rate:>9.2f} {decision:>12}"
        )

    print("=" * len(header))

    # Recommend winner: smallest passing buffer beyond baseline
    winner = None
    for buf_label, passes, rec_rate, sus_rate in candidates_checked:
        if buf_label == "0.5m":
            continue
        if passes:
            winner = buf_label
            break

    if winner:
        logger.info(f"RECOMMENDATION: Adopt buffer {winner} — first candidate meeting recovery >= {MIN_NET_RECOVERY_RATE} and suspicious < {MAX_SUSPICIOUS_RATE}")
    else:
        logger.warning("No candidate buffer met both thresholds. Manual review required. Consider staying at 0.5m or further increasing buffer cautiously.")

    print(f"\n>>> RECOMMENDED BUFFER: {winner if winner else 'MANUAL REVIEW REQUIRED'}")
    print("(Audit complete. No files were modified.)\n")


if __name__ == "__main__":
    main()

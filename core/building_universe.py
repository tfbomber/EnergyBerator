"""
building_universe.py
====================
Single Source of Truth for building denominators.

Merges building counts from buildings.parquet and foundation_structure_results.json.
Takes the max() for each segment to ensure no buildings are lost, bridging the gap
between the two extraction pipelines (one filters by 'yes', the other by cluster feed).

FIX 2026-05-04: replaces ad-hoc Foundation JSON counting in L2 builder.
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("BUILDING_UNIVERSE")

BASE_DIR = Path(__file__).resolve().parents[1]
_DEFAULT_BUILDINGS_PARQUET = BASE_DIR / "data" / "buildings.parquet"
_DEFAULT_FOUNDATION_JSON = BASE_DIR / "output" / "foundation" / "foundation_structure_results.json"

def count_buildings_per_segment(
    buildings_path: Path | None = None,
    foundation_path: Path | None = None,
) -> dict[str, int]:
    """
    Count total buildings per segment_id.
    Merges buildings.parquet counts with foundation JSON counts (taking max).
    This ensures we don't undercount if one source filtered out 'building=yes' 
    or if the other source only checked specific streets.
    """
    bp = buildings_path or _DEFAULT_BUILDINGS_PARQUET
    fp = foundation_path or _DEFAULT_FOUNDATION_JSON
    
    counts: dict[str, int] = {}

    # 1. From buildings.parquet
    if bp.exists():
        df = pd.read_parquet(bp, columns=["segment_id"])
        bp_counts = df["segment_id"].value_counts().to_dict()
        for seg, n in bp_counts.items():
            counts[seg] = n
    else:
        logger.error(f"[BUILDING_UNIVERSE] buildings.parquet not found: {bp}")

    # 2. From foundation JSON
    if fp.exists():
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        clusters = []
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    clusters.extend(v)
        elif isinstance(data, list):
            clusters = data
            
        fd_plz_counts = {}
        for c in clusters:
            plz = str(c.get("plz", "")).strip()
            if plz:
                fd_plz_counts[plz] = fd_plz_counts.get(plz, 0) + int(c.get("building_count_total", 0) or 0)
                
        for plz, n in fd_plz_counts.items():
            seg_id = f"NEUSS_PLZ{plz}"
            counts[seg_id] = max(counts.get(seg_id, 0), n)
    else:
        logger.error(f"[BUILDING_UNIVERSE] foundation json not found: {fp}")

    for seg, n in sorted(counts.items()):
        logger.info(f"[BUILDING_UNIVERSE] {seg}: {n:,} total buildings (unified)")

    return counts

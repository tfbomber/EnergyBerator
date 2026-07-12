import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
logger = logging.getLogger("BRIDGE_MASTR_F04")

BASE_DIR = Path(r"d:\Stock Analysis\D-Energy Berater\d-ess-engine")
IN_PARQ = BASE_DIR / "data" / "sources" / "mastr" / "mastr_pv_adoption_neuss.parquet"
OUT_PARQ = BASE_DIR / "data" / "fields" / "field_04_pv_adoption.parquet"

def main():
    logger.info(f"Loading {IN_PARQ}...")
    if not IN_PARQ.exists():
        logger.error(f"Input file NOT FOUND: {IN_PARQ}")
        return
        
    df_in = pd.read_parquet(IN_PARQ)
    
    rows = []
    for _, row in df_in.iterrows():
        seg_id = row["segment_id"]
        # Use market gap as the score (higher gap = better opportunity)
        market_gap = row["pv_market_gap"]
        
        # Determine confidence based on data_confidence flag
        data_conf = row["data_confidence"]
        conf_score = 0.85 if data_conf == "HIGH" else 0.70
        
        notes = (
            f"PLZ={row['plz']} | PV Units: {row['pv_installation_count']} | "
            f"Est. Buildings: {row['estimated_buildings']} | "
            f"Adoption Rate: {row['pv_adoption_rate']:.2%} | "
            f"Market Gap: {market_gap:.2%} | Level: {data_conf}"
        )
        
        rows.append({
            "segment_id": seg_id,
            "field_id": "field_04",
            "field_value": market_gap,
            "confidence": conf_score,
            "source": "MASTR_DIRECT_COUNT_V2",
            "notes": notes
        })
        
    df_out = pd.DataFrame(rows)
    logger.info(f"Generated field_04 dataframe with {len(df_out)} rows.")

    # BUGFIX 2026-07-12: preserve every existing segment this run does NOT
    # itself recompute (Augsburg / Kaarst rows written by their own drivers).
    # The previous bare df_out.to_parquet() wiped them — same root-cause class
    # as field_04_pv_adoption.py::run() (fixed same day). NOTE: this bridge is a
    # legacy MASTR_DIRECT_COUNT_V2 producer superseded by field_04_pv_adoption's
    # E3 allocation; if re-run it still replaces Neuss's E3 rows with market-gap
    # rows — kept for provenance, but prefer field_04_pv_adoption.run().
    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    recomputed = set(df_out["segment_id"])
    if OUT_PARQ.exists():
        existing = pd.read_parquet(OUT_PARQ)
        preserved = existing[~existing["segment_id"].isin(recomputed)]
        df_out = pd.concat([preserved, df_out], ignore_index=True)
    df_out.to_parquet(OUT_PARQ, index=False)
    logger.info(f"Saved to {OUT_PARQ} ({len(df_out)} rows total)")
    
    print("\n=== NEW field_04_pv_adoption.parquet ===")
    print(df_out.to_string())

if __name__ == "__main__":
    main()

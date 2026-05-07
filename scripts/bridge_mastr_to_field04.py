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
    
    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_parquet(OUT_PARQ, index=False)
    logger.info(f"Saved to {OUT_PARQ}")
    
    print("\n=== NEW field_04_pv_adoption.parquet ===")
    print(df_out.to_string())

if __name__ == "__main__":
    main()

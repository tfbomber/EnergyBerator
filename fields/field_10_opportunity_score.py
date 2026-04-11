import pandas as pd
import numpy as np
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Field10_Opportunity")

def run(segments_df: pd.DataFrame) -> pd.DataFrame:
    """
    Field 10: Street Opportunity Score MVP (1.0).
    Calculates prioritized sales target score for segments.
    """
    if segments_df.empty:
        logger.warning("Empty segments dataframe provided.")
        return pd.DataFrame()

    logger.info("Calculating Field 10 Opportunity Score...")

    # 1. Normalization (N_pv)
    # Target range [0.02, 0.50] -> [0, 1]
    # Clips at boundaries
    min_pv = 0.02
    max_pv = 0.50
    segments_df['n_pv'] = (segments_df['pv_segment_score'] - min_pv) / (max_pv - min_pv)
    segments_df['n_pv'] = segments_df['n_pv'].clip(0, 1)

    # 2. Infrastructure Score (S_infra)
    # Directly uses none_dh_ratio (30% weight)
    # If missing, default to 0.5 (neutral)
    segments_df['s_infra'] = segments_df.get('none_dh_ratio', 0.5).fillna(0.5)

    # 3. Morphology Score (S_morph)
    # Weighted sum: Detached(1.0) > Semi(0.8) > Rowhouse(0.6) > Others(0.4)
    # (detached_ratio * 1.0) + (semi_ratio * 0.8) + (rowhouse_ratio * 0.6) + (others * 0.4)
    def calc_morph(row):
        d = row.get('detached_ratio', 0)
        s = row.get('semi_ratio', 0)
        r = row.get('rowhouse_ratio', 0)
        others = 1.0 - (d + s + r)
        return (d * 1.0) + (s * 0.8) + (r * 0.6) + (others * 0.4)

    segments_df['s_morph'] = segments_df.apply(calc_morph, axis=1)

    # 4. Social Proof (S_social)
    # Directly uses field_value from F04 (normalized signal)
    # If missing, default to 0.1 (low proof)
    segments_df['s_social'] = segments_df.get('pv_adoption_signal', 0.1).fillna(0.1)

    # 5. Final Final Score
    # Score = S_pv * 0.4 + S_infra * 0.3 + S_morph * 0.2 + S_social * 0.1
    segments_df['opportunity_score'] = (
        (segments_df['n_pv'] * 0.4) +
        (segments_df['s_infra'] * 0.3) +
        (segments_df['s_morph'] * 0.2) +
        (segments_df['s_social'] * 0.1)
    )

    results = []
    for _, row in segments_df.iterrows():
        results.append({
            "segment_id": row['segment_id'],
            "field_id": "field_10",
            "field_value": round(row['opportunity_score'], 4),
            "confidence": 0.85,
            "source": "multi_criteria_scoring_v1.1",
            "notes": (
                f"Weights: PV(40%), Infra(30%), Morph(20%), Social(10%). "
                f"PV_raw={row['pv_segment_score']:.4f}, "
                f"DH_none_ratio={row.get('none_dh_ratio', 'N/A')}, "
                f"Adoption_signal={row.get('pv_adoption_signal', 'N/A')}"
            )
        })

    return pd.DataFrame(results)

if __name__ == "__main__":
    segments_master_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "segments.parquet")
    if os.path.exists(segments_master_p):
        df_seg = pd.read_parquet(segments_master_p)
        output = run(df_seg)
        print(output.to_string())
        
        output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fields", "field_10_opportunity_score.parquet")
        output.to_parquet(output_path, index=False)
        logger.info(f"Field 10 results saved to {output_path}")

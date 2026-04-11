import os
import sys
import pandas as pd
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(ROOT_DIR)

from core.top10_hardener import apply_top10_hardening

MVP_OUTPUT = os.path.join(ROOT_DIR, "mvp_radar", "outputs")

def build_features():
    os.makedirs(MVP_OUTPUT, exist_ok=True)
    print("Building MVP Area Features (General Base Model v1)...")

    cluster_csv = os.path.join(ROOT_DIR, "output", "clusters", "neuss_hybrid_clusters_v1.csv")
    if not os.path.exists(cluster_csv):
        print(f"ERROR: Base cluster file not found: {cluster_csv}")
        return

    df = pd.read_csv(cluster_csv)
    
    # Load Gate Purity Simulation data
    purity_path = os.path.join(ROOT_DIR, "output", "purity_gate", "purity_gate_simulation_NEUSS.json")
    purity_map = {}
    if os.path.exists(purity_path):
        with open(purity_path, 'r', encoding='utf-8') as f:
            pdata = json.load(f)
            for item in pdata:
                cid = item.get("cluster_id")
                if cid:
                    pflag = item.get("sim_label_t060", "")
                    purity_map[cid] = {
                        "purity_score_final": item.get("purity_score_final"),
                        "purity_flag": "DOWNGRADED" if "DOWNGRADED" in pflag else "RETAINED"
                    }
    
    # Inject purity so top10_hardener can use it if needed, and so we have it for scoring
    # Notice: some clusters might not be in the purity audit. We will enforce Zero Inference in scoring.
    df["purity_score_final"] = df["cluster_id"].apply(lambda x: purity_map.get(str(x), {}).get("purity_score_final"))
    df["purity_flag"] = df["cluster_id"].apply(lambda x: purity_map.get(str(x), {}).get("purity_flag"))

    # 1. Apply Top10 Hardening Overlay to get Volume Bands, PLZ, etc.
    df = apply_top10_hardening(df, ROOT_DIR)
    
    # 2. Attach missing Gate features manually to ensure ZERO_INFERENCE rules
    gate_path = os.path.join(ROOT_DIR, "output", "gate", "household_gate_results.csv")
    gate_df = pd.read_csv(gate_path) if os.path.exists(gate_path) else pd.DataFrame()
    
    if not gate_df.empty:
        # Create a mapping
        gate_map = gate_df.set_index("cluster_id")[
            ["sfh_strength_score", "mfh_risk_score", "building_count"]
        ].to_dict('index')
    else:
        gate_map = {}

    features = []

    for _, row in df.iterrows():
        cid = str(row.get("Cluster ID") or row.get("cluster_id", ""))
        
        # Pull gate directly
        g_data = gate_map.get(cid, {})
        sfh_str = g_data.get("sfh_strength_score", None)
        mfh_risk = g_data.get("mfh_risk_score", None)
        bldg_cnt = g_data.get("building_count", None)
        
        lead_count = row.get("Lead Count") if pd.notna(row.get("Lead Count")) else row.get("lead_count")
        
        features.append({
            "area_id": cid,
            "geometry_centroid_lat": row.get("cluster_centroid_lat"),
            "geometry_centroid_lon": row.get("cluster_centroid_lon"),
            "sfh_strength_score": sfh_str,
            "sfh_absolute_count": row.get("sfh_absolute_count"),
            "mfh_risk_score": mfh_risk,
            "purity_score_final": row.get("purity_score_final"),
            "purity_flag": row.get("purity_flag"),
            "lead_count": lead_count,
            "building_count": bldg_cnt,
            "deployable_volume_band": row.get("deployable_volume_band"),
            "A_count": row.get("A_count"),
            "PLZ": row.get("PLZ"),
            "Stadtteil": row.get("Stadtteil"),
            "purity_adjusted_label": row.get("purity_adjusted_label")
        })

    out_df = pd.DataFrame(features)
    out_path = os.path.join(MVP_OUTPUT, "area_features.csv")
    out_df.to_csv(out_path, index=False)
    print(f"General Base Model v1 feature table built at: {out_path} with {len(features)} records.")

if __name__ == "__main__":
    build_features()

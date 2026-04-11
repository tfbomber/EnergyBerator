import os
import pandas as pd
import json
from datetime import datetime

# D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MVP_BASE = os.path.join(ROOT_DIR, "mvp_radar")
TOP_AREAS_CSV = os.path.join(MVP_BASE, "outputs", "top_areas_neuss.csv")
FEATURE_CSV = os.path.join(MVP_BASE, "outputs", "area_features.csv")
OUTPUT_DIR = os.path.join(MVP_BASE, "outputs")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>D-ESS Tactical One-Pager: {area_id}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
        h2 {{ color: #2563eb; margin-top: 30px; }}
        .metric-box {{ background: #f3f4f6; border-left: 4px solid #3b82f6; padding: 15px; margin: 20px 0; border-radius: 4px; }}
        .metric-title {{ font-weight: bold; font-size: 1.1em; color: #4b5563; }}
        .metric-value {{ font-size: 1.8em; font-weight: bold; color: #1f2937; }}
        .action-box {{ background: #ecfdf5; border: 2px solid #10b981; padding: 20px; text-align: center; border-radius: 8px; margin-top: 30px; }}
        .action-title {{ color: #065f46; font-size: 1.4em; font-weight: bold; margin-bottom: 15px; }}
        .driver-list {{ background: #fffcf0; padding: 15px 30px; border: 1px solid #fef08a; border-radius: 4px; }}
        .footer {{ margin-top: 50px; font-size: 0.85em; color: #6b7280; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; }}
    </style>
</head>
<body>
    <h1>Tactical Briefing: Area {area_id}</h1>
    <p><strong>Generated:</strong> {date}</p>
    <p><strong>D-ESS Priority Rank:</strong> #{rank}</p>

    <div class="metric-box">
        <div class="metric-title">Opportunity Score</div>
        <div class="metric-value">{score} / 100 <span style="font-size: 0.5em; color: #6b7280; font-weight: normal;">(Confidence: {confidence})</span></div>
    </div>

    <h2>Executive Summary & Sales Hook</h2>
    <p style="font-size: 1.2em; border-left: 4px solid #f59e0b; padding-left: 15px; font-style: italic;">
        {hook_text}
    </p>

    <h2>Primary Drivers (The "Why")</h2>
    <div class="driver-list">
        <ul>
            {drivers_html}
        </ul>
    </div>
    
    <h2>Uncertainties & Risks</h2>
    <ul>
        {uncertainties_html}
    </ul>

    <div class="action-box">
        <div class="action-title">Recommended Field Action</div>
        <div style="font-size: 2em; font-weight: 900; color: #047857; text-transform: uppercase;">
            {action}
        </div>
        <p style="margin-top: 10px; color: #064e3b; font-size: 1.1em;">
            {action_rationale}
        </p>
    </div>

    <div class="footer">
        D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.<br>
        Legacy Governance Baseline Frozen at Stage 76.
    </div>
</body>
</html>
"""

def build_one_pager():
    if not os.path.exists(TOP_AREAS_CSV) or not os.path.exists(FEATURE_CSV):
        print("Required inputs missing. Run scoring pipeline first.")
        return

    top_df = pd.read_csv(TOP_AREAS_CSV)
    if top_df.empty:
        print("No areas to report.")
        return
        
    feat_df = pd.read_csv(FEATURE_CSV)
    
    # Process the #1 ranked area
    top_area = top_df.iloc[0]
    area_id = top_area["area_id"]
    
    # Extract features for rationale
    f_row = feat_df[feat_df["area_id"] == area_id]
    if not f_row.empty:
        b_suit = f_row.iloc[0]["building_suitability"]
        hp_prox = f_row.iloc[0]["heat_pump_proxy"]
        pv_sig = f_row.iloc[0]["roof_pv_signal"]
    else:
        b_suit = hp_prox = pv_sig = 0.5

    # Rationale constructor
    action = top_area["recommended_action"]
    rationale = f"Based on aggregate data: "
    if action == "DOOR_TO_DOOR":
        rationale += f"Building suitability is extraordinarily high ({b_suit*100:.0f}%) representing dense detached/semi-detached housing, while heat pump penetration remains extremely low ({hp_prox*100:.0f}%), creating a massive unfulfilled whitespace requiring direct human intervention and field canvassing."
    elif action == "PARTNER_INSTALLER":
        rationale += f"Strong visible photovoltaic density signals (PV Index: {pv_sig*100:.0f}%) indicate a mature cluster. Pass list to partner installers for battery retrofits and ecosystem upgrades."
    elif action == "EDUCATION_CAMPAIGN":
        rationale += f"The opportunity is theoretically strong, but low data confidence ({top_area['confidence_score']}) implies missing proxies. Flood the zone with digital education/awareness campaigns to generate inbound signals before deploying physical sales teams."
    else:
        rationale += "Constraint levels or lack of structural viability advise holding back resources currently."

    drivers = [d.strip() for d in str(top_area.get("key_driver", "")).split('|')]
    drivers_html = "".join([f"<li><strong>{d.split(':')[0]}</strong>: {d.split(':')[1]}</li>" if ':' in d else f"<li>{d}</li>" for d in drivers if d])
    
    uncerts_raw = top_area.get("main_uncertainties", "['None']")
    uncerts = eval(uncerts_raw) if isinstance(uncerts_raw, str) and uncerts_raw.startswith('[') else [uncerts_raw]
    uncertainties_html = "".join([f"<li>{u}</li>" for u in uncerts])

    html_content = HTML_TEMPLATE.format(
        area_id=area_id,
        date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rank=top_area["rank"],
        score=top_area["opportunity_score"],
        confidence=top_area["confidence_score"],
        hook_text=top_area["sales_hook_text"],
        action=action,
        action_rationale=rationale,
        drivers_html=drivers_html,
        uncertainties_html=uncertainties_html
    )

    out_file = os.path.join(OUTPUT_DIR, f"top_area_brief_{area_id}.html")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Generated Tactical One-Pager for #1 Area: {out_file}")
    
    # Also dump a clean actionable Installer CSV list for the top 5
    shortlist_out = os.path.join(OUTPUT_DIR, "installer_action_shortlist.csv")
    short_df = top_df.head(5)[['rank', 'area_id', 'priority_band', 'recommended_action', 'sales_hook_type']]
    short_df.to_csv(shortlist_out, index=False)
    print(f"Generated Installer Shortlist for Top 5 Areas: {shortlist_out}")

if __name__ == "__main__":
    build_one_pager()

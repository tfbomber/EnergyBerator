"""
core/top10_hardener.py
======================
PHASE 10 — Top 10 Hardening Pass. Non-destructive overlay only.
Adds ranking, tie-break, structured top reasons, narrative family,
geographic stubs, and consistency audit flags.

No mutation of existing scoring, clustering, or gate logic.
Gate CSV loaded internally; not injected into main pipeline.
"""

import os
import logging
import math

import pandas as pd

logger = logging.getLogger("Top10Hardener")

# ---------- PLZ / Stadtteil lookup ----------
# Derived from segment_id pattern: NEUSS_OSM_<PLZ>
_PLZ_STADTTEIL_MAP = {
    "41460": "Neuss Innenstadt",
    "41462": "Reuschenberg / Gnadental",
    "41464": "Norf / Grimlinghausen",
    "41466": "Weckhoven / Erfttal",
    "41468": "Hammfeld / Selikum",
    "41469": "Uedesheim / Morgensternsheide",
    "41470": "Hoisten / Rosellen",
    "41472": "Neuss-Sued / Holzheim",
}

def _extract_plz(segment_id: str) -> str:
    """Extract 5-digit PLZ from segment_id like 'NEUSS_OSM_41464'. Returns UNKNOWN on no match."""
    try:
        parts = str(segment_id).split("_")
        for p in reversed(parts):
            if p.isdigit() and len(p) == 5:
                return p
    except Exception:
        pass
    return "UNKNOWN"

def _plz_to_stadtteil(plz: str) -> str:
    """Map PLZ string to human-readable Stadtteil name."""
    return _PLZ_STADTTEIL_MAP.get(str(plz), "Neuss")

# ---------- Volume bands ----------
def _volume_band(lead_count):
    try:
        n = int(lead_count)
        if n < 10:   return "S"
        if n < 40:   return "M"
        if n < 100:  return "L"
        return "XL"
    except Exception:
        return "UNKNOWN"


# ---------- Load gate CSV internally ----------
def _load_gate_lookup(base_dir: str) -> dict:
    """Load household_gate_results.csv and return cluster_id -> row dict."""
    gate_path = os.path.join(base_dir, "output", "gate", "household_gate_results.csv")
    if not os.path.exists(gate_path):
        logger.warning(f"Gate CSV not found: {gate_path}. sfh_strength and building_count will be absent.")
        return {}
    try:
        df = pd.read_csv(gate_path)
        result = {}
        for _, row in df.iterrows():
            result[str(row["cluster_id"])] = {
                "sfh_strength_score": float(row.get("sfh_strength_score", 0.0) or 0.0),
                "mfh_risk_score":     float(row.get("mfh_risk_score", 0.0) or 0.0),
                "building_count":     int(row.get("building_count", 0) or 0),
                "gate_tier":          float(row.get("gate_tier", 0.0) or 0.0),
            }
        logger.info(f"Gate lookup loaded: {len(result)} clusters from {gate_path}")
        return result
    except Exception as e:
        logger.error(f"Failed to load gate CSV for hardening: {e}")
        return {}


# ---------- Top reason builder ----------
def _build_top_reasons(a_count, lead_count, purity_flag, building_count, sfh_strength, mfh_risk):
    """Return (reason1, reason2, reason3) as human-readable strings."""
    reasons = []

    # Reason 1: Lead quality
    try:
        ratio = int(a_count) / max(int(lead_count), 1)
        if ratio >= 0.40:
            reasons.append(f"Strong A-grade lead density ({ratio:.0%} quality rate, {a_count} A-leads)")
        elif ratio >= 0.20:
            reasons.append(f"Moderate A-grade density ({ratio:.0%}, {a_count} A-leads of {lead_count} total)")
        else:
            reasons.append(f"Early-stage pipeline ({a_count} A-leads identified, further qualification needed)")
    except Exception:
        reasons.append("Lead quality data unavailable")

    # Reason 2: Volume / scale
    try:
        n = int(lead_count)
        if n >= 80:
            reasons.append(f"High-volume cluster: {n} target properties — efficient door-to-door deployment")
        elif n >= 30:
            reasons.append(f"Medium cluster scale: {n} target properties — focused field outreach viable")
        else:
            reasons.append(f"Boutique cluster: {n} target properties — high-conviction targeted approach")
    except Exception:
        reasons.append("Volume data unavailable")

    # Reason 3: Context / purity
    flag = str(purity_flag or "")
    sfh = float(sfh_strength or 0.0)
    mfh = float(mfh_risk or 0.0)
    bldg = int(building_count or 0)

    if flag == "DOWNGRADED":
        reasons.append("Mixed-context area: surrounding MFH pressure moderate — prioritise experienced reps")
    elif flag == "UNCHANGED" and sfh >= 0.75:
        reasons.append(f"SFH-dominant context: low surrounding MFH pressure (sfh_strength={sfh:.0%})")
    elif flag == "UNCHANGED" and sfh >= 0.50:
        reasons.append(f"Predominantly residential — SFH majority confirmed (sfh_strength={sfh:.0%})")
    elif bldg > 0:
        reasons.append(f"Building stock: {bldg} mapped units in cluster footprint")
    else:
        reasons.append("Residential context — manual street-level confirmation recommended")

    return reasons[0], reasons[1], reasons[2]


# ---------- Narrative family ----------
def _narrative_family(a_count, lead_count, purity_flag, top_reasons_text, sfh_strength):
    try:
        ratio = int(a_count) / max(int(lead_count), 1)
        n = int(lead_count)
    except Exception:
        ratio, n = 0.0, 0

    reasons_lower = str(top_reasons_text).lower()
    flag = str(purity_flag or "")
    sfh = float(sfh_strength or 0.0)

    if flag == "DOWNGRADED":
        return "MIXED_TRANSITION"
    if n >= 80 and ratio >= 0.35:
        return "HIGH_DENSITY_SFH"
    if n < 30 and ratio >= 0.40:
        return "COMPACT_BOUTIQUE"
    if sfh >= 0.80 and ratio >= 0.40:
        return "HIGH_DENSITY_SFH"
    return "SFH_LEAD_DOMINANT"



# ---------- Tie-break score (0–1 composite) ----------
def _tie_break_score(a_count, lead_count, purity_score, sfh_strength):
    try:
        # Normalize each component to 0–1
        a_norm    = min(int(a_count) / 50.0, 1.0)                         # cap at 50 A-leads
        vol_norm  = min(math.log1p(int(lead_count)) / math.log1p(200), 1.0)
        purity    = float(purity_score) if purity_score is not None else 0.5
        sfh       = float(sfh_strength) if sfh_strength is not None else 0.5

        score = 0.40 * a_norm + 0.25 * vol_norm + 0.20 * purity + 0.15 * sfh
        return round(score, 6)
    except Exception:
        return 0.0


def _tie_break_explanation(rank_pos, a_count, lead_count, purity_flag, volume_band):
    return (
        f"Rank #{rank_pos} | A-leads={a_count}/{lead_count} | "
        f"Vol={volume_band} | PurityFlag={purity_flag}"
    )


# ---------- Consistency audit ----------
def _consistency_flag(purity_flag, purity_adjusted_label, recommended_action, narrative_family):
    flag = str(purity_flag or "")
    adj  = str(purity_adjusted_label or "")
    action = str(recommended_action or "")
    nfam = str(narrative_family or "")

    if flag == "DOWNGRADED" and "DOOR_TO_DOOR" in action:
        return "WEAK_LABEL_AGGRESSIVE_ACTION"
    if flag == "DOWNGRADED" and nfam in ("HIGH_DENSITY_SFH", "COMPACT_BOUTIQUE"):
        return "DOWNGRADED_BUT_PREMIUM_NARRATIVE"
    return "OK"


# ---------- Main overlay function ----------
def apply_top10_hardening(df: pd.DataFrame, base_dir: str) -> pd.DataFrame:
    """
    Apply Top 10 Hardening overlay to the cluster DataFrame.
    Adds derived fields without mutating scores, labels, or ranking source.

    Parameters
    ----------
    df       : cluster DataFrame after purity gate overlay
    base_dir : project root directory

    Returns
    -------
    df with new hardening columns; sorted by (Opportunity Score DESC, tie_break_score DESC).
    """
    gate_lookup = _load_gate_lookup(base_dir)

    # ── Derive per-row fields ──
    rank_list, tbs_list, tbe_list = [], [], []
    sfh_abs_list, vol_band_list = [], []
    r1_list, r2_list, r3_list = [], [], []
    nfam_list, plz_list, stadt_list = [], [], []
    audit_list, precise_list = [], []

    # Dense rank by Opportunity Score first
    opp_scores = pd.to_numeric(df.get("Opportunity Score", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0)
    df = df.copy()
    df["_opp_num"] = opp_scores

    for _, row in df.iterrows():
        cid      = str(row.get("Cluster ID") or row.get("cluster_id", ""))
        a_count  = int(row.get("A_count", 0) or 0)
        lead_cnt = max(int(row.get("Lead Count", 1) or 1), 1)
        opp      = float(row.get("_opp_num", 0.0))
        pf       = str(row.get("purity_flag", "NOT_APPLICABLE"))
        ps       = row.get("purity_score_final")
        adj_lbl  = str(row.get("purity_adjusted_label", ""))
        rec_act  = str(row.get("recommended_action", ""))

        # Gate-derived (internal load)
        gate_row   = gate_lookup.get(cid, {})
        sfh_str    = gate_row.get("sfh_strength_score", 0.5)
        bldg_count = gate_row.get("building_count", 0)
        mfh_risk   = gate_row.get("mfh_risk_score", 0.0)

        # Volume band
        vband = _volume_band(lead_cnt)

        # Top reasons
        primary_driver_text = str(row.get("Top Reasons", row.get("primary_driver", "")))
        r1, r2, r3 = _build_top_reasons(a_count, lead_cnt, pf, bldg_count, sfh_str, mfh_risk)

        # Narrative family
        nfam = _narrative_family(a_count, lead_cnt, pf, primary_driver_text + " " + r1 + " " + r2, sfh_str)

        # Tie-break
        tbs = _tie_break_score(a_count, lead_cnt, ps, sfh_str)

        # SFH absolute count
        sfh_abs = round(bldg_count * sfh_str) if bldg_count > 0 else None

        # Consistency flag
        cflag = _consistency_flag(pf, adj_lbl, rec_act, nfam)

        # PLZ and Stadtteil derived from segment_id
        seg_id = str(row.get("segment_id", ""))
        plz = _extract_plz(seg_id)
        stadtteil = _plz_to_stadtteil(plz)

        sfh_abs_list.append(sfh_abs)
        vol_band_list.append(vband)
        r1_list.append(r1)
        r2_list.append(r2)
        r3_list.append(r3)
        nfam_list.append(nfam)
        tbs_list.append(tbs)
        plz_list.append(plz)
        stadt_list.append(stadtteil)
        audit_list.append(cflag)
        precise_list.append(round(opp, 4))

    df["tie_break_score"]       = tbs_list
    df["sfh_absolute_count"]    = sfh_abs_list
    df["deployable_volume_band"] = vol_band_list
    df["top_reason_1"]          = r1_list
    df["top_reason_2"]          = r2_list
    df["top_reason_3"]          = r3_list
    df["narrative_family"]      = nfam_list
    df["PLZ"]                   = plz_list
    df["Stadtteil"]             = stadt_list
    df["consistency_audit_flag"] = audit_list
    df["display_score_precise"] = precise_list

    # ── Stable sorted order: score DESC, tie_break DESC, cluster_id ASC ──
    cid_col = "Cluster ID" if "Cluster ID" in df.columns else "cluster_id"
    df = df.sort_values(
        ["_opp_num", "tie_break_score", cid_col],
        ascending=[False, False, True]
    ).reset_index(drop=True)
    df["rank_position"] = df.index + 1

    # ── Tie-break explanation (after rank is set) ──
    tbe_list = [
        _tie_break_explanation(
            int(row["rank_position"]),
            int(row.get("A_count", 0) or 0),
            int(row.get("Lead Count", 0) or 0),
            str(row.get("purity_flag", "N/A")),
            str(row.get("deployable_volume_band", "?"))
        )
        for _, row in df.iterrows()
    ]
    df["tie_break_explanation"] = tbe_list
    df.drop(columns=["_opp_num"], inplace=True)

    n_families = df["narrative_family"].nunique()
    n_flags    = df[df["consistency_audit_flag"] != "OK"]["consistency_audit_flag"].count()
    logger.info(
        f"Top10 Hardening applied: {len(df)} rows | "
        f"{n_families} narrative families | {n_flags} consistency flags raised"
    )
    return df


# ---------- Narrative template selector ----------
NARRATIVE_TEMPLATES = {
    "HIGH_DENSITY_SFH": (
        "**\U0001F680 High-Volume Pure SFH Deployment Zone**\n\n"
        "\"{street} offers maximum field-sales efficiency -- {lead_count} target properties in a compact "
        "walkable cluster, with {a_count} A-grade leads already identified. "
        "This is a route-optimised door-to-door zone with high residential purity. One well-prepared sales rep "
        "can cover the majority of the street in a single session. Prioritise for immediate dispatch.\""
    ),
    "COMPACT_BOUTIQUE": (
        "**\U0001F3AF Targeted High-Conviction Area**\n\n"
        "\"{street} is a highly concentrated, boutique-scale cluster ({lead_count} total properties). "
        "With {a_count} A-grade leads already identified, the conversion probability per door is extremely high. "
        "Recommended approach: highly tailored door-to-door opening or appointment-setting sequence.\""
    ),
    "MIXED_TRANSITION": (
        "**\U0001F536 Mixed-Context Zone -- Experienced Reps Preferred**\n\n"
        "\"{street} shows solid SFH signals internally, but the surrounding neighbourhood context is more mixed. "
        "Door-to-door outreach can still be productive, but requires reps with strong multi-family objection-handling. "
        "{a_count} A-leads identified out of {lead_count} total. "
        "Recommended approach: targeted mail or phone pre-qualification before field dispatch.\""
    ),
    "SFH_LEAD_DOMINANT": (
        "**\U0001F3D8 Strong Residential Lead Core**\n\n"
        "\"{street} is a well-rounded target with solid A-grade lead density. "
        "{a_count} A-grade leads in a {volume_band}-scale cluster ({lead_count} total properties). "
        "Homeowners in this area represent standard, high-quality residential upgrade targets. "
        "Recommended approach: standard field deployment with a focus on neighborhood references.\""
    ),
}

def get_narrative(narrative_family: str, street: str, a_count: int, lead_count: int, volume_band: str) -> str:
    """Return the formatted narrative string for a cluster's narrative family.
    
    Sanitises all output to strip any illegal surrogate characters before
    returning, preventing UnicodeEncodeError in Streamlit's protobuf layer.
    """
    template = NARRATIVE_TEMPLATES.get(narrative_family, NARRATIVE_TEMPLATES["SFH_LEAD_DOMINANT"])
    try:
        result = template.format(
            street=street,
            a_count=a_count,
            lead_count=lead_count,
            volume_band=volume_band,
        )
    except Exception:
        result = template
    # Defence-in-depth: strip surrogates in case any input field contains them
    return result.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

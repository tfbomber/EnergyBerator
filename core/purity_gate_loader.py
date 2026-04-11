"""
core/purity_gate_loader.py
==========================
PHASE 9 - Non-destructive Purity Gate overlay loader.

Responsibility:
  - Load purity_gate_config.yaml
  - Load Phase 8 simulation output (purity_gate_simulation_NEUSS.json)
  - Join simulation results onto cluster DataFrame by cluster_id
  - Derive overlay fields without mutating original labels or scores

Overlay fields added to every cluster row:
  purity_gate_applied        bool   - True when gate fires for this cluster
  purity_threshold_used      float  - Threshold config value, or None
  purity_original_label      str    - Always the original gate_tier (e.g. "2.4")
  purity_adjusted_label      str    - Downgraded label or same as original
  purity_flag                str    - DOWNGRADED | UNCHANGED | NOT_APPLICABLE | NOT_AVAILABLE
  purity_score_final         float  - Raw purity score, or None
  purity_context_score       float  - P_context value, or None
  purity_reason_short        str    - Human-readable note

Fallback guarantee:
  If no sim data exists for a cluster, the cluster is NEVER dropped.
  purity_flag = "NOT_AVAILABLE", purity_adjusted_label = original_label.
"""

import os
import json
import logging

import pandas as pd

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

logger = logging.getLogger("PurityGateLoader")

# Config defaults (used when YAML is unavailable or key is missing)
_DEFAULTS = {
    "enable_purity_gate": True,
    "purity_threshold": 0.55,
    "purity_use_adjusted_label_for_display": False,
    "purity_show_explainer_note": True,
}

_EXPLAINER_NOTE = (
    "This area shows strong single-family signals, "
    "but it is embedded in a more mixed-density surrounding context. "
    "Door-to-door outreach efficiency may be lower."
)


def load_purity_config(base_dir: str) -> dict:
    """Load purity_gate_config.yaml. Falls back to _DEFAULTS safely."""
    cfg = _DEFAULTS.copy()
    config_path = os.path.join(base_dir, "config", "purity_gate_config.yaml")
    if not os.path.exists(config_path):
        logger.warning(f"PurityGate config not found at {config_path}. Using defaults.")
        return cfg
    if not _YAML_AVAILABLE:
        logger.warning("PyYAML not installed. Using PurityGate defaults.")
        return cfg
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
        for k in _DEFAULTS:
            if k in file_cfg:
                cfg[k] = file_cfg[k]
    except Exception as e:
        logger.error(f"Failed to parse purity_gate_config.yaml: {e}. Using defaults.")
    return cfg


def load_purity_simulation(base_dir: str) -> pd.DataFrame:
    """Load Phase 8 simulation JSON. Returns empty DataFrame if missing."""
    sim_path = os.path.join(
        base_dir, "output", "purity_gate", "purity_gate_simulation_NEUSS.json"
    )
    if not os.path.exists(sim_path):
        logger.warning(f"Purity simulation not found: {sim_path}. Overlay will be NOT_AVAILABLE for all clusters.")
        return pd.DataFrame()
    try:
        with open(sim_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        logger.info(f"Purity simulation loaded: {len(df)} records from {sim_path}")
        return df
    except Exception as e:
        logger.error(f"Failed to load purity simulation: {e}. Overlay will be NOT_AVAILABLE.")
        return pd.DataFrame()


def apply_purity_gate_overlay(
    df: pd.DataFrame,
    base_dir: str,
    cfg: dict = None,
) -> pd.DataFrame:
    """
    Join purity simulation data onto the cluster DataFrame and derive overlay fields.

    Parameters
    ----------
    df       : cluster DataFrame (already merged with stage6 explainer)
    base_dir : root project directory
    cfg      : purity config dict (from load_purity_config). Loaded internally if None.

    Returns
    -------
    df with overlay fields added in-place (new columns only, no mutations to existing ones).
    """
    if cfg is None:
        cfg = load_purity_config(base_dir)

    # ── 1. Gate disabled: populate neutral overlay fields and return ──
    if not cfg.get("enable_purity_gate", True):
        df["purity_gate_applied"] = False
        df["purity_threshold_used"] = None
        df["purity_original_label"] = None
        df["purity_adjusted_label"] = None
        df["purity_flag"] = "NOT_APPLICABLE"
        df["purity_score_final"] = None
        df["purity_context_score"] = None
        df["purity_reason_short"] = ""
        logger.info("PurityGate disabled by config. Overlay fields populated as NOT_APPLICABLE.")
        return df

    threshold = float(cfg.get("purity_threshold", 0.55))
    sim_df = load_purity_simulation(base_dir)

    # ── 2. Determine the sim label column matching the threshold ──
    # Map threshold value to column key produced by generate_purity_gate.py
    _THRESHOLD_COL_MAP = {0.60: "sim_label_t060", 0.55: "sim_label_t055", 0.50: "sim_label_t050"}
    sim_label_col = _THRESHOLD_COL_MAP.get(round(threshold, 2), "sim_label_t055")

    # ── 3. Build lookup dict from sim data ──
    sim_lookup: dict = {}  # cluster_id -> sim row dict
    if not sim_df.empty and "cluster_id" in sim_df.columns:
        for _, row in sim_df.iterrows():
            sim_lookup[row["cluster_id"]] = row.to_dict()

    # ── 4. Determine original label column ──
    # gate_tier may exist from household gate merge; fall back to None
    orig_label_col = "gate_tier" if "gate_tier" in df.columns else None

    # ── 5. Derive per-row overlay fields ──
    purity_gate_applied = []
    purity_threshold_used = []
    purity_original_label = []
    purity_adjusted_label = []
    purity_flag = []
    purity_score_final = []
    purity_context_score = []
    purity_reason_short = []

    for _, row in df.iterrows():
        cid = row.get("Cluster ID") or row.get("cluster_id", "")
        orig_label = row[orig_label_col] if orig_label_col else None

        # Is this cluster eligible for purity gate? Only 2.4 clusters are candidates.
        is_24 = (str(orig_label).strip() in ("2.4", "2.4.0")) if orig_label is not None else False

        sim = sim_lookup.get(cid)

        if not is_24:
            # Not a 2.4 cluster — gate not applicable
            purity_gate_applied.append(False)
            purity_threshold_used.append(None)
            purity_original_label.append(orig_label)
            purity_adjusted_label.append(orig_label)
            purity_flag.append("NOT_APPLICABLE")
            purity_score_final.append(None)
            purity_context_score.append(None)
            purity_reason_short.append("")
        elif sim is None:
            # 2.4 cluster but no sim data — safe fallback
            purity_gate_applied.append(False)
            purity_threshold_used.append(threshold)
            purity_original_label.append(orig_label)
            purity_adjusted_label.append(orig_label)
            purity_flag.append("NOT_AVAILABLE")
            purity_score_final.append(None)
            purity_context_score.append(None)
            purity_reason_short.append("Purity simulation data not available for this cluster.")
        else:
            # 2.4 cluster with sim data
            puf = float(sim.get("purity_score_final", 1.0))
            pctx = float(sim.get("P_context", 0.0))
            sim_label_val = sim.get(sim_label_col, "2.4_RETAINED")
            is_downgraded = sim_label_val == "2.3_DOWNGRADED"

            adj_label = "2.3" if is_downgraded else "2.4"
            flag = "DOWNGRADED" if is_downgraded else "UNCHANGED"
            reason = _EXPLAINER_NOTE if is_downgraded else ""

            purity_gate_applied.append(True)
            purity_threshold_used.append(threshold)
            purity_original_label.append(orig_label)
            purity_adjusted_label.append(adj_label)
            purity_flag.append(flag)
            purity_score_final.append(round(puf, 4))
            purity_context_score.append(round(pctx, 4))
            purity_reason_short.append(reason)

    # ── 6. Assign columns to df ──
    df = df.copy()
    df["purity_gate_applied"] = purity_gate_applied
    df["purity_threshold_used"] = purity_threshold_used
    df["purity_original_label"] = purity_original_label
    df["purity_adjusted_label"] = purity_adjusted_label
    df["purity_flag"] = purity_flag
    df["purity_score_final"] = purity_score_final
    df["purity_context_score"] = purity_context_score
    df["purity_reason_short"] = purity_reason_short

    n_downgraded = sum(1 for f in purity_flag if f == "DOWNGRADED")
    n_unavailable = sum(1 for f in purity_flag if f == "NOT_AVAILABLE")
    logger.info(
        f"PurityGate overlay applied. Threshold={threshold}. "
        f"Downgraded={n_downgraded}, UNCHANGED={purity_flag.count('UNCHANGED')}, "
        f"NOT_APPLICABLE={purity_flag.count('NOT_APPLICABLE')}, NOT_AVAILABLE={n_unavailable}"
    )
    return df


def get_purity_audit_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a slim audit DataFrame of all purity-flagged 2.4 clusters for the analyst view.
    Includes both DOWNGRADED and UNCHANGED (sim data available) rows.
    """
    if "purity_flag" not in df.columns:
        return pd.DataFrame()

    audit_flags = {"DOWNGRADED", "UNCHANGED", "NOT_AVAILABLE"}
    mask = df["purity_flag"].isin(audit_flags)
    cols_wanted = [
        c for c in [
            "Cluster ID", "Street", "purity_flag",
            "purity_score_final", "purity_context_score",
            "purity_original_label", "purity_adjusted_label",
            "purity_reason_short",
        ]
        if c in df.columns
    ]
    return df[mask][cols_wanted].copy()

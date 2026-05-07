"""
ui/components/ui_shared.py
==========================
Shared UI Groundedness Components for TerritoryAI Installer View.

Provides:
    render_confidence_badge(sc)          — fires when structural_certainty < 0.80
    render_caveat_box(text, level)       — renders a mandatory disclaimer box
    render_gate_badge(gate)              — returns badge string for structure_gate value
    auto_apply_groundedness(...)         — orchestrates all groundedness rendering

Authority: KI territoryai_skills / installer_ui_review.md (BLOCK G, 2026-04-17)
All copy strings sourced from ui.copy_de.COPY — never inline here.
"""

from __future__ import annotations
import streamlit as st
from ui.copy_de import COPY

# ---------------------------------------------------------------------------
# render_confidence_badge
# ---------------------------------------------------------------------------
def render_confidence_badge(sc: float | None) -> None:
    """
    Render data-quality signal badge.

    Fires ONLY when sc < 0.80 (sc >= 0.80 = silent, clean UI — Skill I-04).
    Uses mandatory COPY strings from copy_de.py (never inline).

    Args:
        sc: structural_certainty float in [0, 1], or None (treated as 0.50).
    """
    if sc is None:
        sc = 0.50

    if sc >= 0.80:
        return  # Verified tier — silent, no badge shown

    if sc < 0.50:
        # CAUTION tier — Überwiegend Proxy-Daten
        st.markdown(
            f"<div style='"
            f"background:rgba(231,76,60,0.08);"
            f"border-left:3px solid #e74c3c;"
            f"border-radius:2px 4px 4px 2px;"
            f"padding:4px 10px;"
            f"font-size:0.78em;"
            f"margin:4px 0'>"
            f"⚠️ {COPY['dq_caution_note']}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # PLAUSIBEL tier (0.50 ≤ sc < 0.80) — caveat_segment_level
        st.markdown(
            f"<div style='"
            f"background:rgba(243,156,18,0.08);"
            f"border-left:3px solid #f39c12;"
            f"border-radius:2px 4px 4px 2px;"
            f"padding:4px 10px;"
            f"font-size:0.78em;"
            f"margin:4px 0'>"
            f"ℹ️ {COPY['caveat_segment_level']}"
            f"</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# render_caveat_box
# ---------------------------------------------------------------------------
_LEVEL_STYLES: dict[str, tuple[str, str, str]] = {
    # level → (background_rgba, border_color, icon)
    "info":  ("rgba(52,152,219,0.08)",   "#3498db", "ℹ️"),
    "warn":  ("rgba(230,160,32,0.10)",   "#e0a020", "⚠️"),
    "risk":  ("rgba(231,76,60,0.08)",    "#e74c3c", "⚠️"),
}

def render_caveat_box(text: str, level: str = "info") -> None:
    """
    Render a mandatory disclaimer/caveat box (Skill G-01, G-02).

    Args:
        text:  The exact COPY[] string to display.
        level: "info" | "warn" | "risk"
    """
    bg, border, icon = _LEVEL_STYLES.get(level, _LEVEL_STYLES["info"])
    st.markdown(
        f"<div style='"
        f"background:{bg};"
        f"border-left:3px solid {border};"
        f"border-radius:2px 4px 4px 2px;"
        f"padding:5px 12px;"
        f"font-size:0.80em;"
        f"margin:4px 0'>"
        f"{icon} {text}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# render_gate_badge
# ---------------------------------------------------------------------------
_GATE_LABELS: dict[str, str] = {
    "PASS":      "✅ Sehr geeignet",
    "QUALIFIED": "🟢 Geeignet",
    "REVIEW":    "🔍 Prüfung nötig",
    "FAIL":      "🚫 Nicht im Fokus",
}

def render_gate_badge(gate: str) -> str:
    """
    Return the client-facing label string for a structure_gate value.

    Args:
        gate: Raw structure_gate string from parquet (PASS|QUALIFIED|REVIEW|FAIL).

    Returns:
        Human-readable German badge string.
    """
    return _GATE_LABELS.get(str(gate).upper(), f"🔘 {gate}")


# ---------------------------------------------------------------------------
# auto_apply_groundedness
# ---------------------------------------------------------------------------
def auto_apply_groundedness(
    structural_certainty: float | None = None,
    low_sample_flag: bool = False,
    proxy_building_types: bool = False,
    heat_uncertain: bool = False,
    always_show_segment_caveat: bool = True,
) -> None:
    """
    Orchestrator: renders all applicable groundedness signals for one card/expander.

    Call this at the BOTTOM of every segment card and every street detail view.
    All rendered strings come from COPY[] — never inline.

    Args:
        structural_certainty:   float in [0,1] or None
        low_sample_flag:        triggers caveat_low_sample (Skill G-02)
        proxy_building_types:   triggers caveat_proxy_data
        heat_uncertain:         triggers caveat_heat_uncertain
        always_show_segment_caveat: if True, always shows caveat_segment_level
                                    (set to False only in street-level detail where
                                     it would be redundant with confidence badge)
    """
    sc = structural_certainty if structural_certainty is not None else 0.50

    # 1. Confidence badge (replaces explicit segment_level caveat when sc < 0.80)
    render_confidence_badge(sc)

    # 2. Segment-level caveat — always mandatory per de_copy_guard Rule 4
    if always_show_segment_caveat and sc >= 0.80:
        # Only render inline when badge was NOT shown (badge already implies caveat)
        render_caveat_box(COPY["caveat_segment_level"], level="info")

    # 3. Conditional caveats
    if low_sample_flag:
        render_caveat_box(COPY["caveat_low_sample"], level="warn")

    if proxy_building_types:
        render_caveat_box(COPY["caveat_proxy_data"], level="warn")

    if heat_uncertain:
        render_caveat_box(COPY["caveat_heat_uncertain"], level="warn")

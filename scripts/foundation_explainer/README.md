# foundation_explainer

**Layer 1.5 — Explanation / Sales Translation Layer**
Version: Layer 1.5 (v5 Foundation) | Date: 2026-03-21

---

## Purpose

Translate existing Layer 1 structured signals into 5 business-friendly
explanation fields for each street cluster, helping Stadtwerk / installer
teams understand the reasoning behind each gate verdict.

---

## What this module is allowed to do

- Read `gate`, `street_confidence`, `sfh_ratio`, `mfh_ratio`, `other_ratio`, `total_buildings`
- Return 5 metadata fields: `top_reasons`, `risk_flags`, `recommended_action`, `action_rationale`, `sales_story`
- Be imported by `generate_foundation_layer.py` for output record construction only

---

## What this module must NEVER do

- Influence gate decisions (`PASS / QUALIFIED / REVIEW / FAIL`)
- Feed into ranking, scoring, or lead prioritization
- Be used as a filter or sort key
- Be read by `pipeline.py`, `ranking/`, or any scoring consumer
- Generate freeform / LLM-style text not tied to explicit rule templates
- Be changed silently — all template or threshold changes require explicit audit

---

## `recommended_action` valid values

| Value | Meaning |
|---|---|
| `DOOR_TO_DOOR` | Strong SFH signal — direct canvassing appropriate |
| `SELECTIVE_OUTREACH` | Good signal, some uncertainty — targeted approach |
| `INSTALLER_PARTNER_FOCUS` | Promising pattern but partial data — coordinate via partner |
| `MONITOR_ONLY` | Mixed or unreliable signal — observe before committing resources |
| `DEPRIORITIZE` | MFH-dominated — not aligned with SFH product |

> These are **suggestions only** and must not be used to re-rank or filter streets in the pipeline.

---

## Change log

| Date | Change |
|---|---|
| 2026-03-21 | Layer 1.5: initial implementation. Adds 5 explanation metadata fields. No behavior change to gate, confidence, or ranking. |

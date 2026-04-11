# Layer 2 — Acceptance Record
**Scope:** D-ESS · Neuss MVP · PV-only ROI ranking + Priority overlays
**Record status:** Living document — append only. Do not modify signed entries.

---

## Entry 1 · Layer 2 Base Ranking

| Field | Value |
|---|---|
| **Accepted by** | **Di Wu** |
| **Date** | **2026-03-22** |
| **Status** | ✅ ACCEPTED — Controlled internal use |
| **Conditions** | Segments with proxy patches (SUBURB, GRIML) require caution in external communication. |

**Usable segments at acceptance:**

| Segment | Draft Score | Draft Rank | Quality Tier | Gate |
|---|---|---|---|---|
| NEUSS_NORF_01 | 0.6321 | #1 | QUALITY_A | DEPLOYABLE |
| NEUSS_SUBURB_01 | 0.4564* | #2 | QUALITY_B | DEPLOYABLE |
| NEUSS_GRIML_01 | 0.3657* | #3 | QUALITY_B | MIXED (51.4%) |

*Post-C2 parquet values (2026-03-22T20:41) — authoritative.

**Ranking formula:**
```
Score = (sfh_share × 0.30) + (roof_score × 0.25) + (pv_coverage × 0.25) + (gate_pass_pct × 0.20)
Final = Score × tier_discount  [QUALITY_A=1.00, QUALITY_B=0.85, SYNTHETIC=0.00]
```

**Interpretation boundary:** PV-only DRAFT ranking. Not a total commercial potential ranking. Does not constitute a deployment decision.

---

## Entry 2 · Priority 2 — Fernwärme Heat Overlay

| Field | Value |
|---|---|
| **Accepted by** | **Di Wu** |
| **Date** | **2026-03-22** |
| **Status** | ✅ ACCEPTED — Layer 2 downstream overlay |
| **Source file** | `data/layer2/layer2_prio2_heat_overlay.parquet` |
| **Input JSON** | `data/layer2/layer2_prio2_heat_input.json` · `prio2_heat_input_v1` |

**Score chain at acceptance:**

| Segment | Base Score | Heat Status | Modifier | Adj. Score |
|---|---|---|---|---|
| NEUSS_NORF_01 | 0.6321 | NO_SIGNAL | ×1.00 | 0.6321 |
| NEUSS_SUBURB_01 | 0.4564 | LIMITED_OR_UNCLEAR | ×0.90 | 0.4108 |
| NEUSS_GRIML_01 | 0.3657 | LIMITED_OR_UNCLEAR | ×0.90 | 0.3291 |

> [!NOTE]
> Priority 2 is a **negative reality-adjustment only**. Heat pump intentionally excluded from v1 → deferred to Priority 2.5.
> Confidence ceiling: 0.45 (desk-research grade). Revisit if Stadtwerke Neuss publishes updated Wärmeplan.

**Interpretation boundary:** Hard gate for confirmed district heat zones. Soft modifier for uncertainty. Does not affect ranking order (NORF remains #1).

---

## Entry 3 · Priority 2.5 — Heat Pump ROI Uplift

| Field | Value |
|---|---|
| **Accepted by** | **Di Wu** |
| **Date** | **2026-03-23** |
| **Status** | ✅ ACCEPTED — Downstream commercial uplift layer |
| **Source file** | `data/layer2/layer2_prio25_hp_uplift.parquet` |
| **Input JSON** | `data/layer2/layer2_prio25_hp_input.json` · `prio25_hp_input_v1` |
| **Scoring engine** | `fields/field_06_hp_uplift.py` |
| **UI panel** | `ui/components/layer2_review.py` · Section I |

**Score chain at acceptance:**

| Rank | Segment | P2 Adj Score | HP Status | Gate | Modifier | Final Score | HP Conf |
|---|---|---|---|---|---|---|---|
| #1 | NEUSS_NORF_01 | 0.6321 | STRONG_HP_UPLIFT | COMPATIBLE | ×1.15 | **0.7269** | 0.55 |
| #2 | NEUSS_SUBURB_01 | 0.4108 | MODERATE_HP_UPLIFT | COMPATIBLE | ×1.08 | **0.4437** | 0.45 |
| #3 | NEUSS_GRIML_01 | 0.3291 | LIMITED_HP_UPLIFT | COMPATIBLE | ×1.00 | **0.3291** | 0.30 |

**Architecture:** `final_score = prio2_adjusted_score × hp_modifier`

**Guards confirmed at acceptance:**

| Guard | Rule | Status |
|---|---|---|
| UNKNOWN proxy protection | UNKNOWN heating proxy → LIMITED tier (never MODERATE/STRONG) | ✅ Verified |
| Fernwärme gate authoritative | Gate derived from Priority 2 `heat_status`, not JSON | ✅ Verified |
| Anti-double-counting | If gate=BLOCKED: hp_modifier capped at ×1.00 | ✅ Implemented |
| Modifier cap | Max uplift ×1.15 | ✅ Verified |
| Uplift never reduces score | final ≥ prio2_adjusted_score | ✅ Sanity check in script |
| Rank order preserved | NORF remains #1 after uplift | ✅ 0.7269 > 0.4437 > 0.3291 |

**Interpretation boundary (verbatim from acceptance decision):**
> This layer is accepted as a **segment-level commercial narrative uplift** for PV + Heat Pump suitability.
> It is **NOT** a household-level installability model and must not be interpreted as technical feasibility confirmation.
> Section I wording should remain explicitly proxy-based and commercially framed to avoid overclaiming technical certainty.

**GRIML upgrade path:**
> NEUSS_GRIML_01 remains `LIMITED_HP_UPLIFT` because `hp_heating_proxy = UNKNOWN`.
> Upgrade from LIMITED → MODERATE requires **confirmed PLZ-level GAS_DOMINANT evidence for PLZ 41464**.
> NRW regional default must **not** be used as substitute evidence.
> Source required: Zensus 2022 PLZ-level data or Stadtwerke Neuss Wärmeplan.

**Next layer dependency:**
> Priority 2.5 is accepted. Layer 3 (PV+ESS full bundle model) may proceed after separate acceptance gate.

---

*Record maintained by D-ESS Engineering Review · Append-only.*

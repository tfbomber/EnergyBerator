# Layer 2 MVP Input Table — Build Summary

**Built:** 2026-03-22 19:41 UTC

| Metric | Value |
|---|---|
| Total rows | 5 |
| REAL_GROUNDED rows | 3 |
| SYNTHETIC stub rows | 2 |
| **row_usable_for_ranking = True** | **3** |
| Table classification | PARTIAL_MULTI_ROW_EXPLORATORY |

---

## Rows

| unit_id | unit_status | roof_suitability_score | sfh_friendly_share | dominant_form | l1_gate_label | pct_l1_gate_pass | pv_coverage_score | pv_coverage_availability | row_usable_for_ranking |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NEUSS_NORF_01 | REAL_GROUNDED | 0.0283 | 1.0000 | rowhouse | DEPLOYABLE | 1.0000 | 0.5000 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_GRIML_01 | REAL_GROUNDED | 0.1026 | 0.7065 | detached | MIXED | 0.5140 | 0.3592 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_CENTRAL_01 | SYNTHETIC | NULL | NULL | NULL | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_OLD_TOWN_01 | SYNTHETIC | NULL | NULL | NULL | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_SUBURB_01 | REAL_GROUNDED | 0.1143 | 0.8467 | detached | DEPLOYABLE | 0.8095 | 0.3696 | AVAILABLE_E3 | ✅ TRUE |

---

## Key Caveats

1. **foundation gate** join is PLZ-proxied — valid only while PLZ 41470 ≅ NEUSS_NORF_01 territory.
2. **field_02 sfh_friendly_share** confidence is per-building (0.90), not aggregate — adjacency classification has known edge cases.
3. **field_04 pv_coverage_score** is E3-capped at 0.50, confidence=0.45 — use as weak modifier only.
4. **field_01 roof_suitability_score** is a raw ratio (adjusted_area/segment_area_proxy) — not a normalised 0–1 score.
5. **SYNTHETIC rows have row_usable_for_ranking=False** — do not include in Layer 2 ranking until real data is available.

## Next Step

This table is a **SINGLE_ROW_OPERATIONAL MVP prototype**. It validates the schema and aggregation logic.
Before expanding to multi-segment ranking:
- Acquire real OSM building data for additional Neuss districts
- Build `cluster_id → segment_id` mapping table for foundation gate
- Obtain real field_04 coverage for additional real-grounded segments
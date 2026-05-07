# Layer 2 MVP Input Table — Build Summary

**Built:** 2026-04-12 13:44 UTC

| Metric | Value |
|---|---|
| Total rows | 10 |
| REAL_GROUNDED rows | 8 |
| SYNTHETIC stub rows | 2 |
| **row_usable_for_ranking = True** | **5** |
| Table classification | PARTIAL_MULTI_ROW_EXPLORATORY |

---

## Rows

| unit_id | unit_status | roof_suitability_score | sfh_friendly_share | dominant_form | l1_gate_label | pct_l1_gate_pass | pv_coverage_score | pv_coverage_availability | row_usable_for_ranking |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NEUSS_NORF_01 | REAL_GROUNDED | NULL | NULL | NULL | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_GRIML_01 | REAL_GROUNDED | 0.3566 | 0.6632 | SFH_CONFIRMED | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_CENTRAL_01 | SYNTHETIC | NULL | NULL | NULL | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_OLD_TOWN_01 | SYNTHETIC | NULL | NULL | NULL | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_SUBURB_01 | REAL_GROUNDED | 0.4000 | 0.8416 | SFH_CONFIRMED | NOT_AVAILABLE | NULL | NULL | NOT_AVAILABLE | ❌ FALSE |
| NEUSS_PLZ41460 | REAL_GROUNDED | 0.2813 | 0.7500 | SFH_CONFIRMED | BLOCKED | 0.0909 | 0.8140 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_PLZ41462 | REAL_GROUNDED | 0.3003 | 0.6792 | SFH_CONFIRMED | MIXED | 0.5753 | 0.8654 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_PLZ41466 | REAL_GROUNDED | 0.3068 | 0.5765 | SFH_CONFIRMED | DEPLOYABLE | 0.8333 | 0.7819 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_PLZ41468 | REAL_GROUNDED | 0.3189 | 0.6056 | SFH_CONFIRMED | DEPLOYABLE | 0.8269 | 0.7877 | AVAILABLE_E3 | ✅ TRUE |
| NEUSS_PLZ41469 | REAL_GROUNDED | 0.3020 | 0.5465 | SFH_CONFIRMED | DEPLOYABLE | 0.6957 | 0.7743 | AVAILABLE_E3 | ✅ TRUE |

---

## Key Caveats

1. **foundation gate** join is PLZ-proxied — valid only while PLZ 41470 ≅ NEUSS_PLZ41470 territory.
2. **field_02 sfh_friendly_share** confidence is per-building (0.90), not aggregate — adjacency classification has known edge cases.
3. **field_04 pv_coverage_score** is E3-capped at 0.50, confidence=0.45 — use as weak modifier only.
4. **field_01 roof_suitability_score** is a raw area ratio (adjusted_area/segment_area_proxy), preserved unchanged. The normalized counterpart **roof_suitability_score_norm** (min-max, REAL_GROUNDED only) is in [0, 1] and safe to use for ranking.
5. **SYNTHETIC rows have row_usable_for_ranking=False** — do not include in Layer 2 ranking until real data is available.

## Next Step

This table is a **SINGLE_ROW_OPERATIONAL MVP prototype**. It validates the schema and aggregation logic.
Before expanding to multi-segment ranking:
- Acquire real OSM building data for additional Neuss districts
- Build `cluster_id → segment_id` mapping table for foundation gate
- Obtain real field_04 coverage for additional real-grounded segments
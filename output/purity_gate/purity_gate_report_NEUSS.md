# Purity Gate Simulation Report — Neuss

**Date:** 2026-03-20 | **Scope:** 2.4 Purity Gate (offline only)
**Total 2.4 candidates evaluated:** 264
**Total 2.4 buildings at stake:** 7798
**2.1/2.2 touched:** 0 (immutable — confirmed)

## Threshold Summary

| Threshold | Label | Downgraded Clusters | Downgraded Bldgs | Retained Clusters | Retained Bldgs |
|---|---|---|---|---|---|
| 0.6 | Aggressive | 14 | 643 | 250 | 7155 |
| 0.55 | Moderate | 3 | 223 | 261 | 7575 |
| 0.5 | Conservative | 0 | 0 | 264 | 7798 |

## Acceptance Criteria Audit

| Case | T=0.60 | T=0.55 | T=0.50 | Requirement |
|---|---|---|---|---|
| gladbacher | NOT_FOUND | NOT_FOUND | NOT_FOUND | MUST downgrade at 0.55 and 0.60 |
| daimler | ❌ RETAIN | ❌ RETAIN | ❌ RETAIN | MUST downgrade |
| porsche | ❌ RETAIN | ❌ RETAIN | ❌ RETAIN | MUST downgrade |
| mergelsweg | ❌ RETAIN | ❌ RETAIN | ❌ RETAIN | MUST retain at 0.55 |
| stüttgesfeld | ❌ RETAIN | ❌ RETAIN | ❌ RETAIN | MUST retain at 0.55 |

## Signal Architecture (as implemented)

- **Primary (0.55):** K=5 nearest cluster MFH risk, distance-decay weighted (w = 1/(d+100))
- **Secondary (smooth):** inner_contribution = 0.07 × max(0, 1 − dist/1200m)
- **Tertiary (capped):** semantic_effect = min(0.25 × raw_penalty, 0.15)
- **Formula:** `P_context = 0.55 × local_mfh_pressure + inner_contribution + semantic_effect`
- **Purity score:** `purity_score_final = sfh_strength_score × (1 − P_context)`

## Missing Data Fallback

- Missing centroid coordinates → `local_mfh_pressure = 0` (conservative; no penalty applied)
- Missing `sfh_strength_score` → treated as 0.0 (cluster would score 0 purity, likely already ambiguous)
- All fallback cases documented in `fallback_note` field of simulation output
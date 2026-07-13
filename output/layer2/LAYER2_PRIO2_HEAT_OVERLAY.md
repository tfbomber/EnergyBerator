# Layer 2 Priority 2 — Heat Constraint Overlay (v2)
**Generated:** 2026-07-11T20:00:59+00:00
**Schema:** heat_constraint_v3
**Data source:** KWP NRW Neuss (sanierung_baublock_neuss_v1.parquet)
**Formula:** adjusted = draft x (1 - 0.15 x constraint_score)
**Max suppression:** -15%  (vs old STRONG x0.10 = -90%)

## Usable Rows — Adjusted Ranking

| Segment | Base Score | Waerme_p% | Constraint | Score | Modifier | Adjusted | Confidence |
|---|---|---|---|---|---|---|---|
| NEUSS_PLZ41470 | 0.6561 | 32.6% | `MEDIUM` | 0.82 | x1.0000 | **0.6561** | 0.80 |
| NEUSS_PLZ41472 | 0.6255 | 0.0% | `LOW` | 0.00 | x1.0000 | **0.6255** | 0.95 |
| NEUSS_PLZ41466 | 0.5496 | 0.1% | `LOW` | 0.00 | x1.0000 | **0.5496** | 0.95 |
| NEUSS_PLZ41468 | 0.5326 | 0.1% | `LOW` | 0.00 | x1.0000 | **0.5326** | 0.95 |
| NEUSS_PLZ41464 | 0.5303 | 0.1% | `LOW` | 0.00 | x1.0000 | **0.5303** | 0.95 |
| NEUSS_PLZ41469 | 0.4871 | 1.8% | `LOW` | 0.00 | x1.0000 | **0.4871** | 0.95 |
| NEUSS_PLZ41462 | 0.4466 | 1.7% | `LOW` | 0.00 | x1.0000 | **0.4466** | 0.95 |
| NEUSS_PLZ41460 | 0.3023 | 1.2% | `LOW` | 0.00 | x1.0000 | **0.3023** | 0.95 |

> **Schema v2** — KWP spatial join replaces JSON proxy. Waerme_p thresholds: HIGH>=40%, MEDIUM>=15%, LOW<15%. Waerme_p consumed ONLY here (no double-penalty with field_06).
> Parquet: `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\layer2\layer2_prio2_heat_overlay.parquet`
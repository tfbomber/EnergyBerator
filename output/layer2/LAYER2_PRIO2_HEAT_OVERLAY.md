# Layer 2 Priority 2 — Heat Overlay Summary
**Generated:** 2026-04-10T20:18:14+00:00
**Schema:** prio2_heat_overlay_v1_prod

## Usable Rows — Adjusted Ranking

| Segment | Base Score | Heat Status | Modifier | Adjusted Score | Interpretation |
|---|---|---|---|---|---|
| NEUSS_NORF_01 | 0.6830 | `NO_SIGNAL` | ×1.00 | **0.6830** | No heat planning constraint detected — base Layer 2 PV priority unchanged |
| NEUSS_SUBURB_01 | 0.6397 | `LIMITED_OR_UNCLEAR` | ×0.90 | **0.5757** | Soft heat planning caution — moderate priority reduction (×0.90) |
| NEUSS_GRIML_01 | 0.3795 | `LIMITED_OR_UNCLEAR` | ×0.90 | **0.3416** | Soft heat planning caution — moderate priority reduction (×0.90) |

> ✅ PRODUCTION — user sign-off accepted 2026-04-10. Coefficients: STRONG×0.10 · PLANNED×0.60 · LIMITED×0.90 · NO_SIGNAL×1.00 · UNKNOWN×0.85
> Parquet: `D:\Stock Analysis\D-Energy Berater\d-ess-engine\data\layer2\layer2_prio2_heat_overlay.parquet`
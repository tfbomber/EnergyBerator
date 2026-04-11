# Audit Memo: FIELD_04 Correction Pass — NEUSS_NORF_01

## Verdict
**PROVISIONALLY AUDITED — PROXY SIGNAL ONLY**

## Correction Summary
A decontamination and audit-honesty pass was performed on the `NEUSS_NORF_01` real-data result (Run 2026-03-12).

| Correction | Action Taken |
| :--- | :--- |
| **Date Anomalies** | Excluded **1** record with commissioning_date > observation_window.end_date (2026-09-01). |
| **Outlier Decontamination** | Excluded **1** large-scale system (**349.92 kWp**, SEE968139912062) from social-proof scoring. |
| **Metric Separation** | Split results into `raw_metrics` (all valid MaStR) and `residential_proxy_metrics` (netto_kwp <= 30). |
| **Data Quality Downgrade** | Re-labeled `coverage_status` as `PARTIAL` and `evidence_tier` as `E2` to reflect the COARSE_APPROX nature of the PLZ-41470 proxy. |

## Remaining Unresolved Gaps
- **GAP_SPATIAL_EXACTNESS**: The current signal is a postal-code proxy for the Norf area, not a building-level or segment-exact extraction.
- **GAP_RESIDENTIAL_VERIFICATION**: The `netto_kwp <= 30` filter is a heuristic proxy; actual residential status of individual systems is not verified via registry metadata.

## Business Impact
The `pv_adoption_status` remains `HIGH_ADOPTION` based on the residential proxy count (117 systems), but the signal strength is downgraded to `MODERATE` due to the proxy nature of the spatial match. `pv_adoption_score` is set to `null` for audit honesty.

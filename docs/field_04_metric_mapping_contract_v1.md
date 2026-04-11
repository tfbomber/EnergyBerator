# FIELD_04 Metric Mapping Contract v1.0

## 1. Scope
This contract defines the deterministic mapping from raw and normalized PV adoption metrics to business output labels for the Neuss pilot area (Norf).

## 2. Adoption Status Mapping
Thresholds are calibrated for low-rise residential segments in Neuss.

| Status | Condition |
| :--- | :--- |
| `NONE_OBSERVED` | `pv_installation_count == 0` |
| `LOW_ADOPTION` | `pv_installation_count > 0` AND `pv_installation_count < 3` AND `pv_total_kwp < 25` |
| `MODERATE_ADOPTION` | `pv_installation_count` in `[3..7]` OR `pv_total_kwp` in `[25..80]` |
| `HIGH_ADOPTION` | `pv_installation_count >= 8` OR `pv_total_kwp >= 80` |
| `UNKNOWN` | Result of fail-safe logic (e.g., missing MaStR CSV or unresolved spatial identity) |

## 3. Signal Strength Mapping
Strength reflects the confidence and clarity of the observed signal.

| Strength | Condition |
| :--- | :--- |
| `STRONG` | `evidence_tier == E1` AND `spatial_match_quality == HIGH` |
| `MODERATE` | `evidence_tier == E2` OR mix of Footprint/Buffer matches |
| `WEAK` | `evidence_tier == E3` OR high percentage of contextual (Tier 3) matches |
| `UNKNOWN` | No data available for evaluation |

## 4. Adoption Score
- **v1 Policy**: `pv_adoption_score` remains `null` until a robust citywide normalization basis is defined.
- **Goal**: In future versions, this will be a [0, 1] float based on `adoption_rate` against a regional benchmark.

## 5. Metadata
- **Calibrated for**: Neuss Pilot (Low-rise residential)
- **Version**: 1.0
- **Status**: FROZEN for RUN_NEUSS_NORF_FIELD04

# FIELD_05: Heat Pump Adoption Estimate (Lightweight v1)

## Overview
FIELD_05 introduces a segment-level proxy signal to estimate the probability of existing heat pump adoption. It leverages upstream infrastructure data (FIELD_03 Fernwärme) and behavioral/morphology signals (FIELD_04 PV adoption, housing density).

## Non-Goals
- Does not modify Stage 15 routing or clustering.
- Does not modify Stage 14 eligibility gates or the core Golden Lead Registry.
- Does not introduce new external data dependencies.

## Inputs
- **FIELD_03 Output**: Determines heat infrastructure (Fernwärme presence acts as a massive dampener).
- **FIELD_04 Output**: Determines PV adoption (strong PV correlates with willingness to electrify heating).
- **Segment Sub-stats**: Housing density (Detached vs. Multi-Family).

## Logic (v1)
- **Baseline Rate**: 7% (0.07)
- **Fernwärme Penalty**: multiplier *= 0.5
- **Low-Density / Detached Boost**: multiplier *= 1.6
- **Strong PV Boost**: multiplier *= 1.3
- **Stability Proxy Boost**: multiplier *= 1.2

- **Hard Cap**: 35% (0.35) maximum allowed estimate.

## Output Bands
- `0–5%`: VERY_LOW
- `5–10%`: LOW
- `10–15%`: MEDIUM
- `15–25%`: HIGH
- `25%+`: VERY_HIGH

# Segment Decision Index Status Memo — Norf Pilot

## Purpose
This memo freezes the first baseline Segment Decision Index for `NEUSS_NORF_01`. It brings together the multi-source evidence fields into a single, cohesive perspective.

## Inputs Used
- **FIELD_01**: PV/Roof potential (Proxy)
- **FIELD_02**: Building morphology (Proxy)
- **FIELD_03**: Heating Path Gate (E1, Decentralized)
- **FIELD_04**: PV Adoption Signal (E2, Proxy Complete)

## Assembly Logic
The assembly utilizes rule-based logic heavily constrained by evidence minimums. FIELD_03's E1 tier opened the `ACTIONABLE` pathway safely. However, the geometric blockage on FIELD_04 triggered an automatic confidence penalty. Opportunity scoring was subsequently capped to reflect analytical honesty rather than artificial precision.

## Final Baseline Verdict
- **Overall Opportunity**: `MEDIUM`
- **Decision Status**: `ACTIONABLE`

## Limitations
- **Geographic Blocker (DEP_NEUSS_NORF_01_POLYGON)**: The main limitation rests entirely on the lack of a segment-exact geometry trace for PIP matching. Confidence is therefore artificially deflated to `MEDIUM` until this geometric deficit is cleared.

## Final Note
This is considered a functional baseline index suitable for downstream use. It can guide exploratory targeting and prioritization modeling but stands open to significant refinement pending the resolution of spatial geometry gaps.

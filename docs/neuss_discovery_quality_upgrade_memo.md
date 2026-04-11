# Neuss Discovery Quality Upgrade Memo

## 1. Purpose
This pass upgrades the quality of candidate segment detection established in the Stage 11 discovery preview. It applies stricter heuristics to ensure selected clusters are more commercially actionable and installer-friendly.

## 2. Why Upgrade Was Needed
The initial Stage 11 preview successfully identified morphology clusters but included noisy or commercially awkward candidates (e.g., `NEUSS_OLD_TOWN_01`). Historic centers and highly mixed-use dense cores often face strict preservation rules or overwhelming grid complexities that block scalable electrification campaigns. A quality upgrade was required to filter out these false positives in favor of viable residential targets.

## 3. Refinement Logic
The discovery logic was tightened to prioritize operational deployment realities:
- **Targetability Rating introduced**: Clusters were scored on their dominance of easily serviceable typologies (detached/semi-detached).
- **Stricter Residential Threshold**: Increased the low-rise residential floor ratio requirement to `> 65%` and capped apartment mix at `< 25%`.
- **Historic / Core Penalty**: Explicitly penalized mock segments representing old towns and dense central zones.
- **District Heating Risk Context**: Risk labels (`LOW/MEDIUM/HIGH/UNKNOWN`) were introduced. Any medium or high risk severely throttles opportunity.

## 4. Updated Candidate Summary
The upgrade yielded **2** refined candidate clusters from the proxy base:

1. **`NEUSS_SUBURBAN_01`** (Top Candidate)
   - Opportunity: **MEDIUM**
   - Targetability: **MEDIUM**
   - DH Risk: **LOW**
   - *Why Promising*: Solid residential cluster; scale is appropriate for street-campaign.
   - *Why Limited*: Morphology includes higher rowhouse/mix. Requires precise roof sizing.
   
2. **`NEUSS_VILLA_01`**
   - Opportunity: **LOW**
   - Targetability: **HIGH**
   - DH Risk: **HIGH**
   - *Why Limited*: High risk of existing or planned district heating network overshadows string morphology.

## 5. Key Observations
- The noisy `NEUSS_OLD_TOWN_01` candidate was successfully filtered out by the stricter residential and core-density penalties.
- `NEUSS_SUBURBAN_01` solidified its position as the primary next-candidate, though the necessity for roof-specific qualification (due to rowhouse presence) correctly capped its opportunity at MEDIUM.
- Separation of `Targetability` and `DH Risk` makes the candidates instantly more readable for downstream field scoping.

## 6. Remaining Limits
- **Geometry Deficit**: Exact parcel boundaries are still absent; the candidates rely on derived proxy aggregations.
- **PV Truth**: Actual PV roof yields are proxies, not explicitly modeled 3D irradiance values.

## 7. Final Upgrade Verdict
The discovery quality improved significantly compared to v1. The introduction of targetability and explicit DH risk tracking creates a much more honest and practical scouting tool. This baseline provides a functional filter to identify viable street-campaign target clusters ahead of costly deep analysis.

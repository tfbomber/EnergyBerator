# FIELD_04 Audit Hardening Memo
**Subject:** Correction of Premature Truth Claims in Lokation Recovery Pipeline  
**Date:** 2026-03-13 | **Security Level:** Internal Audit  
**Segment:** NEUSS_NORF_01

## 1. Executive Summary
Following a Stage 9.2 review, the FIELD_04 Lokation recovery pipeline has been "hardened" to prevent premature claims of high-tier evidence (E1) or exact spatial truth before the required `Lokationen_*.xml` dataset is officially delivered and validated.

## 2. Key Corrections Applied

### A. Taxonomy Realignment
Terminological overstatements have been replaced with audited safe labels:
- **Was:** `POINT_IN_POLYGON_EXACT` -> **Now:** `POINT_IN_POLYGON_DERIVED`
- **Was:** `evidence_tier: E1` -> **Now:** `evidence_tier: E2+` (capped at project-geometry level)
- **Was:** `spatial_assignment_status: EXACT_LOCATION_MATCH` -> **Now:** `spatial_assignment_status: INSIDE_DERIVED_HULL`

### B. Execution Gate Enforcement
A 6-gate framework is now hard-coded into the upgrader logic:
1. **Gate 1 (Source)**: Lokation XML presence check.
2. **Gate 2 (Lineage)**: Join success rate >= 90%.
3. **Gate 3 (Anchor)**: Coordinate fill rate >= 80%.
4. **Gate 4 (Geometry)**: Official vs. Project-Derived boundary classification.
5. **Gate 5 (Spatial)**: Minimum pinning threshold or `OBSERVED_ZERO`.
6. **Gate 6 (Score)**: Restoration only if all gates pass.

## 3. Evidence Tier Policy
- **E1 (Segment-Exact)**: Reserved for cases with BOTH official city boundaries AND validated registry anchors.
- **E2+ (Project-Validated)**: Awarded when using project-derived Convex Hulls with validated registry anchors.
- **E2 (Proxy)**: Retained during current state (data pending).

## 4. Score Restoration
Adoption scores for NEUSS_NORF_01 are currently **WITHHELD** (`null`). Score restoration is only permitted once Gate 1-5 validation completes. In the event of a successful run with zero pinned assets, the score will be released as `0.0` (`OBSERVED_ZERO`).

---
*This memo serves as the governing document for FIELD_04 audit honesty during the Norf Pilot closure.*

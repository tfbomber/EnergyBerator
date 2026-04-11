# FIELD_04 Evidence Policy V2

This policy governs the assignment of Evidence Tiers for FIELD_04 based on the combined integrity of registry anchors and segment geometry.

## 1. Evidence Tier Mapping

| Evidence Tier | Label | Registry Requirement | Geometry Requirement | Join Method |
|---|---|---|---|---|
| **E1** | Segment-Exact | `ANCHOR_VALIDATED` | `OFFICIAL_BOUNDARY` | `POINT_IN_POLYGON_OFFICIAL` |
| **E2** | Project-Validated | `ANCHOR_VALIDATED` | `PROJECT_DERIVED_CONVEX_HULL` | `POINT_IN_POLYGON_DERIVED` |
| **E2 (Proxy)** | Postal-Code Proxy | `N/A` | `PLZ_PROXY` | `POSTAL_CODE_PROXY` |
| **E3** | Unresolved | `LOKATION_DATA_PENDING` or `ANCHOR_MISSING` | `ANY` | `UNRESOLVED` |

## 2. Hard Ceiling Rules
1. **Geometry Cap**: Any run using `PROJECT_DERIVED_CONVEX_HULL` is **hard-capped at Tier E2**. It is topologically prohibited from claiming E1 status.
2. **Anchor Cap**: If Gate 3 (Anchor Sufficiency) fails, the run is **hard-capped at Tier E2 (Proxy)**, even if a Point-in-Polygon test was executed.
3. **Denominator Cap**: If the building count denominator lack traceability (e.g., fallback value 500), the `pv_adoption_score` must be withheld (`null`) regardless of tier.

## 3. Truth Discipline
- Tier **E1** implies segment-exact truth suitable for legal or grid-balance use cases.
- Tier **E2** (Validated) implies high-confidence project guidance suitable for energy sales targeting and high-level planning.
- Tier **E2** (Proxy) implies statistical approximation only.

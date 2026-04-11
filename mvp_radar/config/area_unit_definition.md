# Area Unit Definition

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

## Preferred Area Unit Approach
The preferred approach for area-level prioritization is **H3 (Uber's Hexagonal Hierarchical Spatial Index)**. It provides uniform area boundaries which correctly normalizes density and prevents arbitrary zip-code warping.

## Area Naming Convention
- `area_id`: The string representation of the H3 index (e.g. `891f1d48c27ffff`).
- If PLZ (postal code) is used as a fallback, the convention is `PLZ_[code]` (e.g. `PLZ_41470`).

## Recommendations
- **Default Trial Resolution**: H3 Resolution 9. Suitable for neighborhood-level clustering (avg hexagon area ~0.10 sq km).
- **Fallback Resolution**: H3 Resolution 8 if data sparsity is too extreme or implementation simplicity requires it (avg hexagon area ~0.73 sq km).

> Do NOT block MVP progress on geospatial perfection. If H3 Python limits prove blocking for the skeleton, gracefully fall back to existing geometric aggregation outputs formatted temporarily as `segment_id` proxies.

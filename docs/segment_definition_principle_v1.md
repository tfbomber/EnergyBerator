# D-ESS Segment Definition Principle v1.0

## 1. Purpose
The D-ESS engine requires a formalized spatial object ontology. As evidence modules (FIELD_03, FIELD_04) and the Segment Decision Index output mature, the foundational entity they score must be rigidly defined. This document freezes the concept of the "Segment" to prevent regression into ambiguous spatial assumptions.

## 2. Core Definition
A D-ESS Segment is a **business-operational residential opportunity cluster with explicit geometry provenance**. It is a project-defined action unit for energy decision support, not merely an administrative boundary.

## 3. Why Administrative Units Are Insufficient
Official entities like postal codes (PLZ), electoral districts, or city neighborhoods are socio-political or logistical constructs. They often span conflicting building typologies, mixed grid infrastructures, and mixed-use zoning, making them too coarse or entirely misaligned for targeted low-carbon deployment logic (e.g., heat pump or PV suitability mapping).

## 4. Three Segment Principles
A valid D-ESS segment is defined by:
1.  **Actionability**: Sized to support a contiguous marketing, sales, or grid-level intervention campaign.
2.  **Morphological Homogeneity**: Groups similar building typologies (e.g., contiguous low-rise residential).
3.  **Infrastructure Consistency**: Represents a cluster that likely shares similar grid conditions or municipal heating pathway realities.

## 5. Identity vs Geometry Provenance
To remain resilient, a segment strictly separates its business identity from its evolving spatial truth.

### Identity Layer
Defines *what* the segment is as a business target.
- `segment_id`: The canonical primary key.
- `alias`: Historic or internal reference names.
- `target_class`: The socio-morphological classification.
- `city`: The parent municipality.

### Geometry Provenance Layer
Defines *where* the segment is, and *how well we can prove it*.
- `geometry_source_type`: e.g., Derived, Official GIS, Mock.
- `geometry_method`: How the boundary was computed (e.g., Convex Hull of 298 buildings).
- `geometry_traceability`: Audit-tier of the shape (e.g., Tier B).
- `geometry_fidelity`: Exact parcel limits vs loose cluster envelopes.
- `spatial_anchor_confidence`: The engine's trust in using this shape for internal point-in-polygon tests.

## 6. Truth Progression
A segment may evolve in geometry provenance. It can start as a postal proxy, progress to a derived building envelope, and eventually mature into an exact municipal parcel boundary. Throughout this spatial truth progression, its business Identity (`segment_id`) remains constant.

## 7. Naming Principle
Segments use standard taxonomy formatting: `CITY_LOCALITY_INDEX`.
Example: `NEUSS_NORF_01`

## 8. Example: NEUSS_NORF_01
`NEUSS_NORF_01` is the pilot segment. It holds a firm business identity as a residential opportunity cluster. However, it is explicitly *not* equivalent to its postal code proxy (`41470`) and does not perfectly map to single official administrative lines. It is currently anchored by the derived geometry of 298 specific member buildings.

## 9. Final Principle Verdict
A segment is defined primarily by its function as a targeted decision unit, with its geographic exactness treated as an upgradable attribute rather than a fixed precondition.

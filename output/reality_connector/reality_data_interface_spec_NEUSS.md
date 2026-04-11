# Reality Data Interface Specification: NEUSS
This architectural spec handles entry formats for all external truth ingestions.

## 1. Official Geometry Boundary Intake
- **Interface Name**: `INTAKE_GEO_BND`
- **Source Type**: Official OSM Admin Polygon / Kataster Boundary
- **Expected Truth Class**: E4 Official Authoritative Source
- **Input Format**: GeoJSON / WKT Polygon
- **Ingestion Preconditions**: Bounding Box area must align roughly with Stage 20 proxy dimensions.
- **Downstream Consumers**: Stage 13 geometry generators, clustering logic.
- **Replacement Target**: Stage 22 Proxy Bounding Box.
- **Risk of Misuse**: Polygon too broad, enveloping invalid suburban space.

## 2. Evidence Field Verification Intake (FIELD_03/FIELD_04)
- **Interface Name**: `INTAKE_FIELD_TRUTH`
- **Source Type**: API / Web Scraping (e.g. MaStR, SWN Heat Map)
- **Expected Truth Class**: E3 External Observed Partial or E4 Official Authoritative
- **Input Format**: Structured JSON records anchored to street or coordinates.
- **Ingestion Preconditions**: Segment geometry must be at least `EXTERNAL_BOUNDARY_ATTACHED`.
- **Downstream Consumers**: Target Scorers, Re-Clustering Logic.
- **Replacement Target**: SIMULATED_INFERENCE field values.
- **Risk of Misuse**: Partial API data conflicting with visual reality.

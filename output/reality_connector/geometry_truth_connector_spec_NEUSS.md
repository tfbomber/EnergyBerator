# Geometry Truth Connector Spec: NEUSS
Tracks transition of Bounding-Box Proxies into real-world footprint data.

## Geometry Status Classes
1. **PROXY_ONLY**: Mathematically inferred bounds. (Acceptable for planning only)
2. **PENDING_EXTERNAL_DRAW**: Sent to GIS operator / API query queue.
3. **EXTERNAL_BOUNDARY_ATTACHED**: District polygon acquired. Building logic still inferred. (Requires Polygon)
4. **BUILDING_FOOTPRINT_ATTACHED**: Discrete OSM buildings fetched within polygon. (Mandatory for Field routing)
5. **GEOMETRY_VALIDATED**: QA operator confirms geometric footprints are residential. (Blocks Official Activation until True)

## Downstream Consequences
Successful bump to `BUILDING_FOOTPRINT_ATTACHED` instantly triggers `RECOMPUTE_CLUSTERS` flag.
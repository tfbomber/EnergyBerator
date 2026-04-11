# Neuss Discovery Engine Preview Memo

## Purpose
This memo freezes the results of the Stage 11 exploratory discovery pass. The objective of this pass was to preview the D-ESS system's capacity to scan city-wide building footprints and identify candidate actionable segments that resemble the `NEUSS_NORF_01` pilot cluster.

## Discovery Methodology
The discovery scan was executed against the existing `buildings.parquet` and `segments.parquet` data layers. 
The detection logic searched for contiguous building clusters exhibiting:
1.  **Predominantly residential low-rise morphology** (Detached, Semi-Detached, Rowhouse ratio > 0.6).
2.  **Target Actionability Size** (15 to 150 buildings, ideally centering around 50).
3.  **Low District Heating Risk** (Excluding clusters with heavy existing or planned DH networks).
4.  **Positive PV Proxies** (Favorable roof potential or early pilot adoption signals).

## Summary of Identified Candidate Segments
The engine successfully identified **3** viable candidate clusters within the initial Neuss spatial proxy set (excluding the Norf pilot itself).

1.  **`NEUSS_SUBURBAN_01`**
    -   **Estimated Buildings**: 120
    -   **Dominant Morphology**: Semi-Detached
    -   **Opportunity Signal**: **MEDIUM**
    -   **Reason**: Residential cluster. Moderate building count alignment.
    
2.  **`NEUSS_VILLA_01`**
    -   **Estimated Buildings**: 80
    -   **Dominant Morphology**: Semi-Detached
    -   **Opportunity Signal**: **LOW**
    -   **Reason**: District heating risk limits opportunity.
    
3.  **`NEUSS_OLD_TOWN_01`**
    -   **Estimated Buildings**: 150
    -   **Dominant Morphology**: Rowhouse
    -   **Opportunity Signal**: **LOW**
    -   **Reason**: District heating risk limits opportunity.

## Key Observations
- The discovery engine successfully decoupled the original administrative geometries, clustering instead around morphology and infrastructure boundaries.
- **District Heating** is the primary disqualifying technical gate. For instance, `NEUSS_OLD_TOWN_01` and `NEUSS_VILLA_01` were heavily penalized.
- `NEUSS_SUBURBAN_01` represents the most actionable "next" opportunity cluster outside of the Norf pilot.

## Limitations of this Preview Pass
1.  **Data Depth**: The discovery relied on the pre-computed `segments.parquet` proxies rather than running an expensive dynamic spatial clustering algorithm on the raw building points. 
2.  **Geometry Certainty**: Like FIELD_04, these candidate segments lack exact, officially verified Tier A polygon boundaries. They remain Tier B/C derived clusters.
3.  **Status**: These are *candidate* segments. They require formal identification and spatial pinning (Gate 1 validation) before transitioning from discovery prospects to active decision indices.

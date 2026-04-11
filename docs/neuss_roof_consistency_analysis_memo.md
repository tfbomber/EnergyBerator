# Neuss Roof Consistency Analysis Memo

## 1. Purpose
This pass represents Stage 11.2 of the Discovery Engine. It evaluates the top candidate segments (`NEUSS_SUBURBAN_01`, `NEUSS_VILLA_01`) for **Roof Consistency**. High roof consistency allows installers to use fixed structural templates (e.g., standard rowhouse kits), creating high campaign scalability.

## 2. Analysis Dimensions
To avoid complex satellite image processing in this 70% proxy baseline, consistency was derived through conservative morphological heuristics using existing `buildings.parquet` data:
1.  **Roof Orientation Similarity**: Propensity of buildings to face the exact same azimuth.
2.  **Roof Slope Similarity**: Propensity of buildings to share identical pitch.
3.  **Building Type Uniformity**: The absolute dominance of a single building type (e.g., >70% of one form).

## 3. Heuristic Logic
- **Rowhouse dominant**: Given `HIGH` scores across dimensions due to strict street alignment.
- **Semi-Detached dominant**: Given `MEDIUM/HIGH` due to paired alignment but varying street curbs.
- **Detached dominant**: Given `LOW/MEDIUM` due to arbitrary suburban sprawl orientation.

## 4. Final Classification
The combination produces the overall **Roof Consistency Factor (ρ)**:
- **HIGH**: Template-based batch installation highly viable. Low custom engineering.
- **MEDIUM**: Partial variation exists. 2-3 standard installation templates needed per street.
- **LOW**: Highly heterogeneous. Custom design required per roof; low batch efficiency.

## 5. Segment Results
- **`NEUSS_VILLA_01`**: 
  - **Factor**: `MEDIUM`
  - **Installer Scalability**: Partial variation exists. 2-3 standard installation templates needed per street.
- **`NEUSS_SUBURBAN_01`**: 
  - **Factor**: `LOW`
  - **Installer Scalability**: Highly heterogeneous. Custom design required per roof; low batch efficiency.

## 6. Key Business Takeaway
Neither candidate represents the "perfect" rowhouse cookie-cutter campaign model. `NEUSS_SUBURBAN_01` has the strongest overall opportunity score from Stage 11.1, but its structural heterogeneity (`LOW` roof consistency) means an installer running a campaign here must expect high engineering overhead per household (custom designs) rather than rapid batch deployments.

## 7. Limitations
- Values are heuristic proxies dependent on the accuracy of the underlying `segments.parquet` morphology ratios.
- True 3D roof azimuths (Lidar/DSM based) would upgrade this from a proxy to segment-exact truth.

# Stage 6 Summary: Opportunity Map & Validation

## Overview
This report provides a lightweight validation of the Stage 5 Opportunity Scores.
- **Total segments verified:** 5

## Top Ranked Segments
|   rank | segment_id                 |   opportunity_score |   building_count |
|-------:|:---------------------------|--------------------:|-----------------:|
|      1 | ALLERHEILIGEN_PILOT_SEG_01 |              0.4638 |              298 |
|      2 | NEUSS_DENSE_01             |              0.4573 |              200 |
|      3 | NEUSS_VILLA_01             |              0.3808 |               80 |
|      4 | NEUSS_SUBURBAN_01          |              0.2433 |              120 |
|      5 | NEUSS_OLD_TOWN_01          |              0.1067 |              150 |

## Observations
- **Spatial Consistency:** The segment mapping correctly visualizes the pilot area density.
- **Driver Analysis:** The dominant score for the pilot is driven primarily by its full decentralization status (No DH).

## Known Limitations
- PV normalization uses fixed bounds [0.02, 0.50]; may need calibration for extremely high-density cities.
- Opportunity scores are relative for internal ranking, not absolute investment thresholds.
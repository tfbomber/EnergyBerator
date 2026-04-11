# Snapshot F02 + F03: Pilot Area Analytical Summary

## 1. How many buildings are in the pilot area?
There are **298 buildings** verified in the Allerheiligen pilot segment (`ALLERHEILIGEN_PILOT_SEG_01`).

## 2. What is the type distribution?
The residential structure is highly concentrated:
- **Rowhouses**: 231 (77.5%)
- **Semi-detached**: 47 (15.8%)
- **Detached**: 20 (6.7%)
The area is predominantly a high-density "Reihenhaussiedlung".

## 3. What is the district heating status distribution?
- **NONE**: 298 (100.0%)
Based on current OpenStreetMap data (`OSM_PROXY`), there is no district heating infrastructure mapped in this specific suburban pocket.

## 4. Does the pilot area look promising for future PV / electrification?
**Yes, highly promising.** 
- 100% of buildings are currently independent of district heating (per OSM data), making them primary targets for individual heat pump electrification.
- The high density of rowhouses suggests a uniform building stock where successful PV/HP solution templates can be scaled rapidly across the entire segment.

## 5. What is the biggest current limitation of interpretation?
The **Field 03 (District Heating) source reliability**. 
Because we are using an OSM Proxy, we cannot definitively rule out the existence of local pipelines or very recent "Wärmeplanung" zones that hasn't been mapped in OSM. For a production-grade investment decision, municipal Stadtwerke data must be integrated to verify the `NEUTRAL` status.

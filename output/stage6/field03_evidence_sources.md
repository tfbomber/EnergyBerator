# Field 03: District Heating Evidence Sources (Neuss/Norf)

This document identifies candidate sources for truth-anchoring district heating (DH) signals in the Neuss region.

## 1. Candidate Evidence Sources

| Source Name | Type | Coverage | Spatial Resolution | Tier |
| :--- | :--- | :--- | :--- | :---: |
| **Kommunale Wärmeplanung Neuss (Zonierungskarte)** | Official Doc | City-wide | Neighborhood/Zone | **E1** |
| **Stadtwerke Neuss (SWN) Netzplan** | Utility Map | City-wide | Street/Block | **E1** |
| **Klimaschutzkonzept Neuss 2035** | Planning | City-wide | District | **E2** |
| **OSM `utility:heating` tags** | Crowdsourced | Global | Point (Building) | **E2** |
| **Building Age / Morphology Proxy** | Inference | Segment | Segment | **E3** |

## 2. Recommended Primary Source
**[E1] Kommunale Wärmeplanung Neuss (Draft 2025)**
- **Availability**: Public draft zoning map released in April 2025.
- **Evidence Weight**: Highest. Defines the legal "Probability of Heat Grid Expansion" (Wahrscheinlichkeit eines Wärmenetzausbaus).
- **Usage**: Used to define if a segment is in a "Dezentral" (E.g., HP/PV preferred) or "Zentral" (E.g., DH preferred) zone.

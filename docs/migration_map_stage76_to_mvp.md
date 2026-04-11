# Migration Map: Stage 76 to MVP

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

| Legacy Asset / Module | MVP Treatment | Mapping / Usage | Notes |
| :--- | :--- | :--- | :--- |
| Segment Intelligence | REUSE | Use for `household_fit_proxy` | Synthesize baseline macro demographic/prosperity indicators. |
| Roof Consistency / PV Signals | ADAPT | Extrapolate to area `roof_pv_potential` | Aggregate household point data up to chosen area boundaries. |
| PV Adoption Proxies | ADAPT | Inform `electrification_proxy` | Measure penetration density of PV within the given area. |
| Building Mix Outputs | ADAPT | Map to `building_suitability` | Ratio of detached vs multi-family housing inside the area boundary. |
| District Heating / Heat Planning Outputs | ADAPT | Feed as `district_heating_interference` | Apply as a component-level penalty to Heat Pump proxy scoring, not a zero-out. |
| Evidence / Review Modules | FREEZE | N/A | Kept intact in legacy directories. Completely ignored by MVP. |
| Contact / Consent Modules | FREEZE | N/A | Excluded from MVP runtime. |
| Retry Authorization Logic | FREEZE | N/A | Excluded from MVP runtime. |
| Activation / Clearance Logic | IGNORE_FOR_RUNTIME | N/A | Non-applicable in an Area Prioritization Radar. |

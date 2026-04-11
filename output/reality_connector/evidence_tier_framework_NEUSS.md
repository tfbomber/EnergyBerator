# Evidence Tier Framework (E0 - E5)
## E0: Simulated
- **Meaning**: Mock data generated for testing. **Allowed**: Pipeline proxy tests. **Forbidden**: Deployment logic. **Activation Rights**: None.
## E1: Heuristic Inferred
- **Meaning**: Estimated based on district averages. **Allowed**: Stage 20 Planning. **Forbidden**: Final routing. **Activation Rights**: None.
## E2: Project-derived Spatial Proxy
- **Meaning**: Interpolated from overlapping spatial sources. **Allowed**: Triage lists. **Forbidden**: Core gating. **Activation Rights**: Partial.
## E3: External Observed Partial
- **Meaning**: Unofficial web scrape or partial API. **Allowed**: Supplemental metrics. **Forbidden**: Overriding E4. **Activation Rights**: Partial.
## E4: Official Authoritative Source
- **Meaning**: Govt/Corp direct dataset (OSM, SWN). **Allowed**: Core Truth. **Forbidden**: None. **Activation Rights**: Yes (Subject to Governance Gate).
## E5: Manual Field-Confirmed
- **Meaning**: Operator visually verified (Satellite/Door). **Allowed**: Absolute override. **Activation Rights**: Yes. **Deployment Implications**: Ready.
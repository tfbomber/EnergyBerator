# Real-World Blocker Registry
## Blocker 1: No Authoritative Geometry Source
- **Severity**: HIGH. **Prob**: LOW. **Mitigation**: Revert to manual E5 GIS polygon trace.
## Blocker 2: Ambiguous District Heating Boundary
- **Severity**: HIGH. **Prob**: MEDIUM. **Mitigation**: Assign FIELD_03 `UNKNOWN`. Escalate to Manual Review.
## Blocker 3: Multi-Family Contamination Discovered
- **Severity**: MEDIUM. **Prob**: HIGH. **Mitigation**: Run building footprint area filter; drop buildings > 400m2.
## Blocker 4: Cluster Instability after True Geometry
- **Severity**: SYSTEMIC. **Prob**: MEDIUM. **Mitigation**: Enforce RECOMPUTE_CLUSTERS after footprint acquisition.
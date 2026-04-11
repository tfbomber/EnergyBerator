# Segment Activation Governance: NEUSS
Strict logic managing when a Segment officially activates from 'Candidate' into Production Pipeline.

## Activation Gates
- **Geometry Gate**: Must equal `GEOMETRY_VALIDATED`. Simulation proxies block activation.
- **Field Truth Gate**: `FIELD_03` must be `FIELD_VALIDATED`. (Cannot deploy into unknown heating areas).
- **Validation Gate**: Overall segment validation score must be > 0.65 confirmed.
- **Manual Review Gate**: E5 Operator signoff required for final morphology alignment.
- **Deployment Governance Gate**: Segment cannot be marked `deployment_ready` solely on high evidence tier.

*Policy: Simulated segments are explicitly sandboxed. Partial truths cannot be presented as Validated Readiness.*
# First Real Integration Governance Flow
```mermaid
graph TD
    A[Physical File Arrives] --> B[Arrival Validation (Namespace/Schema)]
    B --> C[Stage 26.5 Contract Decisioning]
    C -->|Valid| D[ACCEPT_FOR_CONDITIONAL_INTEGRATION]
    C -->|Invalid| Z[REJECT_AND_LOG]
    D --> E[Admissibility Decision / Lineage Registered]
    E --> F[Recompute Requirement Generation]
    F --> G[Governance Review Eligibility Assigned]
    G --> H((STOP: Segments remain STILL_BLOCKED until Governance pass))
```

The absolute conclusion of ingestion is State H. At this state, Tier movement and Truth Promotion remain ZERO.
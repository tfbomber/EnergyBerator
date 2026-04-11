# Real Evidence Arrival Runbook
> **Scope**: PRODUCTION EXTERNAL EVIDENCE HANDLING
## Phase 1: Physical Arrival Validation
1. Verify the package is mounted explicitly within: `/data/external_evidence/`.
2. Ensure artifact naming complies with production specifications (no 'REHEARSAL' or 'TEST' substrings permitted).
3. Assert metadata completeness (Anchors, Extents, candidate_id match).
4. Confirm valid E4 (Geometry) or E5 (Review) source signatures.

## Phase 2: Contract Decisioning
1. Route through Stage 26.5 logic (Acceptance/Rejection pairs).
2. Any unhandled or ambiguous file states must fallback to `REJECT_AND_LOG`.

## Phase 3: Admissibility & Lineage Registration
1. Upon explicit `ACCEPT_FOR_CONDITIONAL_INTEGRATION`, document the Epistemic Anchor into the Production Lineage registry.
2. DO NOT overwrite proxy truth tiers yet.

## Phase 4: Recompute & Governance Review Eligibility
1. Log the recomputed dependencies triggered by the new artifact (e.g., `trigger_cluster_rebuild`).
2. Candidate shifts exclusively to `Retry-Review Eligible`.
3. Wait for final Tier Governance commands. `STILL_BLOCKED` remains active until Governance authorizes Execution.
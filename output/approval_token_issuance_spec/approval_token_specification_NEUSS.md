# Human Approval Token Issuance Specification

## Purpose
This specification documents the exact machine-readable format required for human governance officers to issue explicit authorization tokens for Stage 39 authorization requests. The engine requires mathematically strict arrays ensuring no pseudo approvals are allowed.

## Required Fields
Every valid JSON token must include:
1. `token_id` (String): A mathematically unique tracking hash for the signature.
2. `target_id` (String): MUST exactly match an identifier from `authorization_candidate_registry_NEUSS.json`.
3. `approval_scope` (String): The explicit business goal granted.
4. `approved_field_paths` (Array): Exact JSON paths granted mutation rights.
5. `approval_timestamp` (String): Exact ISO-8601 UTC timestamp of signature.
6. `approver_identifier` (String): Governance officer identifier (e.g. Employee ID or User Principal).
7. `authorization_level` (String): Authority tier mapping to corporate hierarchy.
8. `approval_signature` (String): The cryptographic hash asserting non-repudiation.

## Boundary Rules
- `approved_field_paths` MUST be an exact subset (or subset-equal) of `requested_field_paths`.
- `approval_scope` MUST NOT exceed `requested_approval_scope`.

## Prohibited Content
- `approved_field_paths` MUST NOT contain elements from `out_of_scope_field_paths`.
- `approved_field_paths` MUST NOT contain elements from `prohibited_field_paths`.
- One token MUST NOT implicitly authorize recomputation triggers.
- One token MUST NOT implicitly authorize writeback triggers.
- One token MUST NOT inherently authorize production mutations. It authorizes solely the Stage-Entry.

## Submission Rules
- **Filename**: `approval_token_<target_id>_<date>.json`
- **Storage Directory**: `d-ess-engine/governance_tokens/`

## Duplicate Token Warning
If multiple tokens exist for the identical `target_id`, the system will flag `DUPLICATE_TARGET_TOKEN` internally and **defer conflict resolution**. This will strictly cause subsequent Stage 40 verification to block execution entirely.

## Separation of Approval vs Execution
Issuing a token DOES NOT trigger execution. It provides a static structural key allowing a *separately invoked downstream module* to unlock target data structures natively.
# Formal Token Submission Instructions

## Placement Vector
Completed offline Authorization JSON files must be explicitly mounted via block transfer to:
`d-ess-engine/governance_tokens/`

## Filename Convention
Tokens must strictly adhere to the following convention:
`approval_token_<target_id>_<date>.json`
Example: `approval_token_b200b21a719c_2026-03-16.json`

## Strict Pipeline Rejection Conditions
1. Missing any required keys. Stage 41 will assign `STRUCTURALLY_INVALID`.
2. JSON data-type parity violations. Stage 41 will assign `SCHEMA_INVALID`.
3. Token `target_id` maps to non-existent Blocked objects. Stage 41 will assign `UNMATCHED_TARGET`.
4. Token arrays contain out-of-scope strings from upstream limits. Stage 40 will assign `TOKEN_INVALID`.
5. Parallel issuance for identical candidates simultaneously mapping `DUPLICATE_TARGET_TOKEN` requiring manual override resolution.

## Legal Semantics
Approval mapping solely unlocks `STAGE 40: AUTHORIZATION_FOR_EXECUTION_STAGE_ENTRY`. It explicitly **DOES NOT** trigger Stage 37 Sandbox mutation. It **DOES NOT** grant Stage 36 Recompute privileges. It **DOES NOT** implicitly write to external storage architectures. All actions require discrete execution scripts following valid token discovery.
# MVP Scope Lock

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

## Primary Focus
- **Neuss Pilot Only**: Restrict evaluation strictly to the Neuss geographic boundary.
- **Area-Level Only**: Output is generalized to the area/district level (e.g. H3 grid or PLZ). No individual street addresses output.
- **Ranking-First Principle**: Determine "Which area should be prioritized first?" based on cumulative signal scores.
- **First-Score-Then-Improve Principle**: Launch with basic weighted heuristic proxies now, integrate robust ML models later.

## Excluded Functionality (Strict Do-Not-Build)
- No household-level confirmation or selection output.
- No person, contact name, or individual PII handling.
- No CRM workflows, exports, or task synchronization.
- No appointment booking logic.
- No consent, origin trace, or legal basis evaluation.
- No evidence intake, error retry, or remediation loops.
- No commercial readiness or execution gating.
- Any output file implying outward outreach is "READY", "ALLOWED", or "COMMERCIAL_CLEAR" is banned.

## MVP Vocabulary
Permitted semantics include: `score`, `confidence`, `priority`, `driver`, `uncertainty`, `sales_hook`.

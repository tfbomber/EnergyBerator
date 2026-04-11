# Stage 2: Source Checklist

Before executing Stage 2, ensure the following source package is prepared and placed in `inputs/sources/`.

## Recommended Minimum Source Package
For a valid Field 03B MVP run, we recommend at least:
- [ ] **1x Official Heat Plan (KWP)**: Should be a PDF or official map indicating zoning.
- [ ] **1x Connection Bylaw (Anschlusszwang-Satzung)**: If applicable, provides the strongest E1 evidence.
- [ ] **1x Web Snapshot**: Official city summary page for context/currentness.

## File Placement Rules
1. **Directory**: All source files must be placed in `d-ess-engine/fields/field_03b_framework/inputs/sources/`.
2. **Matching Path**: The `local_path` value in `source_manifest.json` must match the filename exactly.

## Decision-Eligibility Matrix (Governing Rule)
| Source Type | Official? | Decision Eligible? | Potential Tier |
| :--- | :--- | :--- | :--- |
| PDF_OFFICIAL_MAP | Yes | True | E1/E2 |
| BYLAW_DOCUMENT | Yes | True | E1 |
| WEBPAGE_SNAPSHOT | Yes | False | E3/E4 |
| OSM / GOOGLE MAPS | No | False | **FORBIDDEN** (RS1) |

## Audit Discipline
- **Silence is not Absence**: If a segment is not mentioned in any official source, it must lead to `segment_heat_status: not_indicated` (if area-wide coverage) or `unknown`.
- **No Up-scaling**: Evidence for a "district" cannot be automatically applied to every building within it.

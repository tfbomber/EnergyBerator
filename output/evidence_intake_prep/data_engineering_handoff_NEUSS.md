# Data Engineering Handoff: NEUSS
> **Planning Status**: PREPARATION_ONLY

## Data Engineer
- **Responsibilities**: Fetch Kataster/OSM files, run MaStR extraction scripts.
- **Acceptance Condition**: Files landed in `/data/raw/` meeting `_schema.json` specs.
## Operator / Reviewer
- **Responsibilities**: Trigger E5 manual geometry validation via UI/CLI.
- **Acceptance Condition**: Output written to `/data/reviews/geo/`.
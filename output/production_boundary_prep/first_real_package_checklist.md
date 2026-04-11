# First Real Package Checklist
### Pre-Flight
- [ ] Ensure `/output/path_rehearsal/` artifacts are segregated and inactive.
- [ ] Verify `/data/external_evidence/` mount holds the physical file.
### Evaluation
- [ ] Run Stage 26.5 Decision Matrix.
- [ ] Confirm terminal routing applied (`ACCEPT_...` or `REJECT_...` or `HOLD_...`).
### Ingestion Safety
- [ ] Ensure `STILL_BLOCKED` remained the Segment's default status post-ingestion.
- [ ] Verify Production Truth values (e.g., `field_04_status`) did NOT silently recompute.
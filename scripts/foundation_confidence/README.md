# foundation_confidence

**Enhancement C — Street Confidence Layer**
Version: Enhancement C (v5 Foundation) | Date: 2026-03-21

---

## Purpose

Provide a descriptive reliability indicator (`street_confidence`) for each
street-level gate verdict produced by `generate_foundation_layer.py`.

- **Gate** = *what* the street is classified as (`PASS / QUALIFIED / REVIEW / FAIL`)
- **Confidence** = *how reliable* that classification appears, given available signal

`street_confidence` is output metadata only. It documents trust in the verdict.

---

## What this module is allowed to do

- Read `total_buildings`, `mfh_count`, `mfh_ratio`, `other_ratio` as inputs
- Compute one of: `HIGH`, `MEDIUM`, `LOW`
- Be imported by `generate_foundation_layer.py` for output record construction

---

## What this module must NEVER do

- Influence gate decisions (`PASS / QUALIFIED / REVIEW / FAIL`)
- Feed into ranking, scoring, or lead prioritization
- Be used as a filter or sort key in any pipeline
- Be read by `pipeline.py`, `ranking/`, or any downstream consumer
- Be changed silently — all threshold changes require explicit audit

---

## Signal design (summary)

| Signal | Variable | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| Sample size | `total_buildings` | ≥ 50 | 20–49 | < 20 |
| MFH contamination | `mfh_ratio` | CLEAN (=0) | LIGHT (≤10%) | MIXED (>10%) |
| Ambiguity | `other_ratio` | LOW (< 20%) | MED (20–49%) | HIGH (≥ 50%) |

**Final rule:**
- `HIGH` only when: size=HIGH AND ambiguity=LOW AND contamination=CLEAN
- `LOW` if any of: size=LOW OR ambiguity=HIGH OR contamination=MIXED
- `MEDIUM` otherwise

---

## Change log

| Date | Change |
|---|---|
| 2026-03-21 | Enhancement C: initial implementation. Adds `street_confidence` metadata field. No behavior change to gate or ranking. |

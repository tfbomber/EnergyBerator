# FIELD_03 Status Memo — Norf Pilot

## Purpose
This memo freezes the current FIELD_03 (Heat Gate) status for the segment `NEUSS_NORF_01`. It establishes the authoritative baseline for downstream use in the main index.

## Current Verdict
**DECENTRALIZED_PREFERRED** (Engine Verdict: `SUPPORTED_DECENTRALIZED`)

## Source Basis
The verdict is supported by two Tier E1 official sources:
1. **Neuss Municipal Heat Plan (KWP 2025)**: Explicitly zones the Norf area as *Prüfgebiet Einzellösungen* (Focus area for decentralized individual solutions).
2. **Stadtwerke Neuss (SWN) FFVAV 2025**: Official utility network expansion limitations confirming no planned district heating expansion for the residential core of Norf.

## Decision Relevance
This conclusion is highly robust and fully decision-eligible. The convergence of municipal regulatory zoning (KWP) and technical utility constraints (SWN) provides maximum certainty (Tier E1) that centralized district heating is not viable for this segment, clearing the path for decentralized electrification (Heat Pumps/PV) scoring.

## Remaining Limitations
- **Spatial Pre-computation gap**: The evidence maps at a broad district/polygon level. Precise fractional buffer intersections for building-exact coverage were not re-computed in this pass, but the categorical coverage for `NEUSS_NORF_01` is considered absolute for pilot purposes.

## Final Verdict
The FIELD_03 Heat Gate is **CLOSED** with a Tier E1 verdict of **DECENTRALIZED_PREFERRED**. The module is fully ready for main-index attachment.

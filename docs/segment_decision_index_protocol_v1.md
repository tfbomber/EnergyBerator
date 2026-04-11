# Segment Decision Index Protocol v1

## Purpose
The Segment Decision Index (SDI) is the overarching business-layer artifact. It unifies the outputs of individual evidence fields (FIELD_01 to FIELD_04) into a single, actionable decision matrix for a given segment. It is designed to be consumed by downstream sales, marketing, and grid-planning teams.

## Source Fields Used
- **FIELD_01**: Roof / PV potential proxy.
- **FIELD_02**: Building morphology proxy.
- **FIELD_03**: Heating path gate (Centralized vs. Decentralized).
- **FIELD_04**: PV Adoption / Social Proof signal.

## Assembly Philosophy
The SDI relies on **transparent rule-based logic** over opaque weighted formulas. It prioritizes regulatory constraints and verifiable technical boundaries as hard filters, while treating adoption and morphology as modifiers for opportunity scoring. We do not claim certainty beyond what the weakest critical link can support.

## Handling of FIELD_03 (Hard Gate)
FIELD_03 operates as the primary regulatory and technical gate.
- If FIELD_03 = `DECENTRALIZED_PREFERRED`, the `hard_gate_status` is `PASSED_DECENTRALIZED`. The segment is open for electrification targeting.
- If FIELD_03 favors district heating, the segment is downgraded to `NOT_ACTIONABLE` or `WATCHLIST` regardless of physical potential.

## Handling of FIELD_04 (Confidence Modifier)
FIELD_04 serves as a momentum/adoption signal.
- If FIELD_04 is geographically verified (Point-in-Polygon), it acts as a strong multiplier for `overall_opportunity`.
- If FIELD_04 is proxy-grade (e.g., postal code basis due to missing segment geometry), the index explicitly discounts the global `confidence` rating (e.g., capping at `MEDIUM`) and flags the limitation in the `blockers_and_caveats` array.

## Final Business Output Derivation
- **overall_opportunity**: `HIGH` if the gate is passed, morphology is optimal, and adoption is strong. `MEDIUM` if proxy-limited.
- **decision_status**: `ACTIONABLE` if opportunity is medium/high and the gate is passed.
- **confidence**: Dictated by the lowest evidence tier of the critical inputs (often limited by spatial precision gaps).

## Limitations of this Baseline
This v1 protocol is a static assembly designed to prove the structural unification of the pilot fields. Dynamic recalculations, city-wide ranking sorts, and continuous integration of live data streams are deferred to later versions.

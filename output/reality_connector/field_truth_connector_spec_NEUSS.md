# Field Truth Connector Spec: NEUSS
Defines simulation replacement and conflicts around physical evidence.

## FIELD_03 (Heat Infrastructure Gate)
- **Simulated State**: `SIMULATED_ONLY`
- **Acceptable Sources**: E4 SWN Official Fernwärme Karte.
- **Minimum Evidence Standard**: Address or Street-Level Intersection.
- **Replacement Trigger**: Upload of validated SWN shapefile intersecting Geometry.
- **Conflict Handling**: Authoritative E4 source strictly overrides E0/E1 inferences.
- **Downstream Action**: Recomputes overall segment `EXPANSION_TIER`.

## FIELD_04 (PV Social Proof)
- **Simulated State**: `SIMULATED_ONLY`
- **Acceptable Sources**: E4 MaStR Federal Solar Registry.
- **Minimum Evidence Standard**: PLZ+Street level density maps.
- **Source Precedence**: Manual API query (E3) overridden by Federal Dataset Dump (E4).
- **Partial Validation Logic**: If <50% of the addresses matched, mark `PARTIALLY_VALIDATED`.
- **Field Outcome Classes**: `SIMULATED_ONLY` -> `EVIDENCE_ATTACHED` -> `PARTIALLY_VALIDATED` -> `FIELD_VALIDATED`.
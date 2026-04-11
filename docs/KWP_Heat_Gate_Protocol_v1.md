# KWP_Heat_Gate_Protocol_v1

## 1️⃣ FIELD_03 DECISION PURPOSE
Field_03 defines the **Heat Infrastructure Gate**. Its primary purpose is to determine the strategic heating path for a specific segment based on official municipal planning and existing utility infrastructure.
- **Function**: Acts as a hard gating layer for downstream opportunity ranking.
- **Scope**: Categorizes segments into decentralized-favorable vs. network-constrained areas.
- **Audit Goal**: Ensure zero-inference conversion of KWP zoning maps into actionable stacking data.

## 2️⃣ SOURCE HIERARCHY CONTRACT
Decision logic must follow the established hierarchy. In case of conflict, higher-tier sources prevail.
| Tier | Source ID | Role | Truth Type |
| :--- | :--- | :--- | :--- |
| **A** | `NEUSS_KWP_2025_OFFICIAL` | Final Planning Authority | Official Zoning / Future Truth |
| **B** | `SWN_DH_NETWORK_MAP_2024` | Network Verification | Utility Official / Physical Truth |
| **C** | `D_ESS_DERIVED_VECTORS` | Derived Spatial Context | Project Internal / Calculated Context |
| **D** | `OFFICIAL_DESCRIPTIVE_TEXT` | Supporting Reference | Qualitative Context |
| **E** | `NONE` | Fallback | Unknown |

## 3️⃣ EVIDENCE TIER MODEL
Every Field_03 output must be attributed with an evidence tier to reflect spatial precision.
- **E1**: Direct official vector intersection or explicit official statement naming the specific Segment ID.
- **E2**: Spatial intersection using project-derived manual vectorization from official Raster maps.
- **E3**: Textual district-level match or public announcement mentioning the general neighborhood without precise boundaries.
- **UNKNOWN**: No identifiable mention in planning or network sources.

## 4️⃣ GATE STATUS ENUM
| Status | Semantic Meaning | Business Interpretation | Gate Effect |
| :--- | :--- | :--- | :--- |
| `EXISTING_DH` | Segment intersects verified heating grid. | Decarbonization via DH is priority. Low decentralized potential. | **BLOCK / PENALIZE** |
| `PLANNED_OR_ASSESSED_DH` | Area marked for DH expansion in KWP 2025. | Potential future constraint. Requires caution for long-term HP. | **CAUTION** |
| `DECENTRALIZED_PREFERRED` | KWP zones designated for individual solutions. | Favorable for HP and decentralized electrification. | **ALLOW** |
| `UNKNOWN` | Insufficient evidence in official maps/text. | Truth gap. Manual manual review required before targeting. | **UNKNOWN_REVIEW** |

## 5️⃣ DECISION TREE
The following deterministic flow must be applied per segment:
1. **Rule 1 (Physical Reality)**: If Segment intersects `SWN_DH_NETWORK_MAP_2024` active grid (Buffer: 20m) -> Status = `EXISTING_DH`.
2. **Rule 2 (Planning Priority)**: Else if Segment intersects `NEUSS_KWP_2025_OFFICIAL` "Fernwärme-Ausbaugebiet" -> Status = `PLANNED_OR_ASSESSED_DH`.
3. **Rule 3 (Inferred Electrification)**: Else if Segment intersects `NEUSS_KWP_2025_OFFICIAL` "Einzelversorgung / Dezentral" -> Status = `DECENTRALIZED_PREFERRED`.
4. **Rule 4 (Fallback)**: If no map intersection exists but `OFFICIAL_DESCRIPTIVE_TEXT` explicitly excludes district heating for the district -> Status = `DECENTRALIZED_PREFERRED` (Evidence Tier E3).
5. **Rule 5 (Default)**: Else -> Status = `UNKNOWN`.

## 6️⃣ GEOGRAPHIC ATTACHMENT RULES
- **Intersection Dominance**: A segment is considered "captured" by a zone if >50% of residential residential residential footprints within the segment intersect the zone polygon.
- **Stable ID Mapping**: Textual references (E3) must be mapped to Segment IDs via a strict District-to-Segment lookup table.
- **Precision Anchor**: Attachment mode must be logged (GEO_VECTOR, GEO_APPROX, TEXT_LOGICAL).

## 7️⃣ MANUAL VECTORIZATION POLICY
- **Derived Authority**: Manual vectorization of KWP raster maps is permitted only when native vector sources are unavailable.
- **Provenance**: Derived polygons must include metadata: `operator`, `method` (e.g., Georeferencing QGIS), `date`, and `source_page_ref`.
- **Integrity**: Manual layers must NEVER be labeled as native official truth. They are `E2` level evidence.

## 8️⃣ OUTPUT DATASET SCHEMA
- **Target**: `d-ess-engine/data/fields/field_03_heat_gate.parquet`
- **Fields**:
  - `segment_id`: Primary key.
  - `heat_gate_status`: [EXISTING_DH, PLANNED_OR_ASSESSED_DH, DECENTRALIZED_PREFERRED, UNKNOWN]
  - `gate_effect`: Semantic effect [BLOCK, CAUTION, ALLOW, UNKNOWN_REVIEW]
  - `evidence_tier`: [E1, E2, E3, UNKNOWN]
  - `source_ids_used`: Multi-value list.
  - `interpretation_mode`: [DIRECT_MATCH, SPATIAL_OVERLAP, TEXTUAL_MAPPING]
  - `geographic_attachment_mode`: [GEO_VECTOR, GEO_APPROX, TEXT_LOGICAL]
  - `confidence_note`: Detailed explanation of decision.
  - `run_id`: Execution timestamp/ID.

## 9️⃣ BLOCKING / PENALTY LOGIC
- **BLOCK**: High friction. Segments with `EXISTING_DH` are filtered out from "High Opportunity" marketing lists.
- **CAUTION**: Medium friction. HP stacking possible but requires "Connection Obligation (Anschlusszwang)" check.
- **ALLOW**: Low friction. Green light for decentralized sales targeting.
- **UNKNOWN_REVIEW**: Flagged for manual analyst verification.

## 🔟 ERROR HANDLING & UNKNOWN POLICY
- **Missing Local Artifact**: If `NEUSS_KWP_2025_OFFICIAL` is referenced but local PDF hash check fails -> Force all segments to `UNKNOWN` with note `LOCAL_SOURCE_MISSING`.
- **Low-Res Collision**: If map resolution/scale is >1:25000, spatial matches must be downgraded to `E2` with note `LOW_RES_SCALING_APPLIED`.
- **Conflict Strategy**: If SWN Map (Physical) shows network but KWP (Planning) shows decentralized, the **Physical Reality (SWN)** takes precedence.

## 1️⃣1️⃣ AUDIT REQUIREMENTS
Every Field_03 run must output an audit summary:
- `total_segments_processed`: Integer.
- `status_distribution`: Count per Enum.
- `evidence_distribution`: Count per Tier.
- `vectorization_usage_rate`: % of segments assigned via Tier E2.
- `unresolved_count`: Number of `UNKNOWN` statuses.
- `contradiction_count`: Number of segments where Rule 1 and Rule 2 conflicted.

## 1️⃣2️⃣ OUTPUT FORMAT REQUIREMENT
The final specification is frozen as a structured markdown-contract. No implementation assumes data ingestion until physical file presence is verified in the inventory.

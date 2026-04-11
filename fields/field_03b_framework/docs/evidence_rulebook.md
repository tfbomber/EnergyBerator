# Field 03B: Evidence Rulebook

This document defines the rigorous logic for auditing heat path eligibility based on official evidence.

## 1. Evidence Tiering (E1 - E4)

| Tier | Name | Description | Decision Eligibility |
| :--- | :--- | :--- | :--- |
| **E1** | **Direct Official Confirmation** | Explicit mention of segment/building in binding official plans (e.g., Satung). | **FULL** |
| **E2** | **Official Spatial Intent** | High-resolution official maps showing segment within connection areas (e.g., Wärmeplan). | **FULL (with Caution)** |
| **E3** | **Contextual Indicators** | Indirect evidence like utility maintenance notices or proximity maps (Non-binding). | **CONTEXT ONLY** |
| **E4** | **Unofficial / Inferred Hints** | Media reports, general infrastructure mentions, or outdated public queries. | **CONTEXT ONLY** |

---

## 2. Source-Type Eligibility

### Decision-Eligible Sources (Official)
- Municipal Heat Plans (*Kommunale Wärmeplanung*)
- Connection Bylaws (*Verbrennungs- und Anschlusszwang-Satzungen*)
- Official Utility Expansion Timelines (Published by City/Utility)
- State-Level Energy Registers (*Länder-Energie-Register*)

### Context-Only Sources (Informational)
- General Infrastructure Maps (OSM / Google Maps - **FORBIDDEN for confirmation**)
- Real Estate Portals
- News Articles
- Preliminary Draft Plans (unless officially adopted)

---

## 3. Core Logic Rules

### RS1: The OSM Prohibition
OSM geometry or infrastructure proximity (e.g., "DH pipe runs under this street") may **NOT** be used to confirm Fernwärme service availability or connection status. Only official zoning or utility contracts/ordinances are valid.

### RS2: Segment-to-Building Isolation
Segment-level evidence (e.g., "The whole street is a DH area") does **NOT** constitute building-level connection confirmation.
- `building_heat_status` must remain `unknown` unless address-level proof exists.

### RS3: Non-Mention Policy / Mapping "Not Found"
A "Not Found" result or absence of mention in a document does **NOT** equal "No Coverage".
- If `search_coverage` encompasses the full municipal area and the segment is absent: map to `not_indicated`.
- If `search_coverage` is partial or insufficient, or the document scope is unclear: map to `unknown`.
- Never map to a definitive `none` unless the document explicitly states "Area excluded from network".

### RS4: Heat Source Integrity
`heat_source_type` may only be populated (e.g., `industrial_waste_heat`) if explicitly stated in the source text.
- Fallback: `unknown`.

---

## 4. Decision Impact Matrix

| Evidence Strength | Segment Heat Status | Realization Horizon | Decision Impact (Route-Gate) |
| :--- | :--- | :--- | :--- |
| E1/E2 Official | `existing_heat_network_area` | N/A | `block_hp_default_path` |
| E1/E2 Official | `official_service_area_confirmed` | N/A | `block_hp_default_path` |
| E1/E2 Official | `planned_heat_network_area` | < 5 Years | `suppress_hp_direct_push` |
| E1/E2 Official | `planned_heat_network_area` | > 5 Years | `allow_hp_with_window_note` |
| E1/E2 Official | `decentral_likely_area` | N/A | `allow_hp_pv_priority_path` |
| E1/E2 Official | `not_indicated` | N/A | `allow_hp_pv_priority_path` |
| E3/E4 Context | Any (Unsupported) | Any | `manual_check_required` |
| Any | `unknown` | Unknown | `manual_check_required` |

---

## 5. Determination of Window of Opportunity

The `window_of_opportunity` is a calculated field based on the delta between `now` and the `realization_horizon`.
- If `realization_horizon` is < 2 years: Window is `absent` or highly restricted.
- If `realization_horizon` is 3-6 years: Window is `present` (incentivizing interim HP/PV installs).
- Status must be `unknown` if the source provides no timeline.

---

## 6. Forbidden Inference Patterns

1. **Spatial Inference**: "The neighbors have it, so this segment must have it too." -> **FORBIDDEN**
2. **Age Inference**: "This is an old part of the city, they definitely have DH." -> **FORBIDDEN**
3. **Draft Inference**: "The draft map from 2021 says yes." -> **FORBIDDEN (Must use E4 context only)**
4. **Generalization**: "Industrial areas always have waste heat." -> **FORBIDDEN (heat_source_type must be unknown)**

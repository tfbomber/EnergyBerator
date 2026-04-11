# Field 03 Truth Schema & Integration

## 1. Field 03 Truth Schema
```json
{
  "segment_id": "string",
  "dh_status": "enum {EXISTING_DH, PLANNED_DH, NO_DH, UNKNOWN}",
  "evidence_source": "string",
  "evidence_tier": "enum {E1, E2, E3}",
  "last_verified": "ISO-8601",
  "notes": "string"
}
```

## 2. Integration Logic (Field 10)
Truth-backed `dh_status` directly replaces the heuristic `dh_none_ratio` in the infrastructure score ($S_{infra}$).

| `dh_status` | $S_{infra}$ Mapping | Outreach Action |
| :--- | :---: | :--- |
| **NO_DH** | **1.0** | Focus: Full PV + Heat Pump package. |
| **PLANNED_DH** | **0.4** | Focus: PV (Immediate) + Hybrid/Wait for DH. |
| **EXISTING_DH**| **0.1** | Focus: PV only (Electricity self-sufficiency). |
| **UNKNOWN** | **0.5** | Initial exploratory screening required. |

## 3. Example Record (Norf Pilot)
```json
{
  "segment_id": "ALLERHEILIGEN_PILOT_SEG_01",
  "dh_status": "NO_DH",
  "evidence_source": "Kommunale Wärmeplanung Neuss (Zonierungskarte)",
  "evidence_tier": "E1",
  "last_verified": "2026-03-10",
  "notes": "Verified as decentralized zone in May 2025 draft."
}
```

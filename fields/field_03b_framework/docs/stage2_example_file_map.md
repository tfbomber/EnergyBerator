# Stage 2 Example File Map

This is a conceptual example of how a manifest entry maps to a local file and its audit purpose.

| Manifest ID | Filename | Official? | Decision Eligible? | Expected Use in Audit |
| :--- | :--- | :--- | :--- | :--- |
| `SRC_KWP_2024` | `kwp_final_plan.pdf` | `true` | `true` | Determine planned area status and realization horizon. |
| `SRC_SATZUNG_01` | `dh_ordinance.pdf` | `true` | `true` | Confirm connection obligation (E1 Tier). |
| `SRC_WEB_NEWS` | `city_news_snapshot.pdf` | `true` | `false` | Context for window of opportunity (E3/E4). |

## Logic Flow
1. Load `segment_registry.json`.
2. Load `source_manifest.json`.
3. For each Segment:
   - Search through `SRC_KWP_2024`, `SRC_SATZUNG_01`, etc.
   - Apply `evidence_rulebook.md` logic.
   - Generate `segment_audit_objects.json`.

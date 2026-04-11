# D-ESS MVP: Neuss Area Opportunity Radar

**D-ESS MVP = Neuss Area Opportunity Radar for area-level opportunity prioritization. It does not perform household-level confirmation or operational activation.**

## 1. What This MVP Is
A lightweight, spatial scoring tool aiming to rank aggregated geographic areas (e.g. H3 indexes) inside Neuss. It relies on proxies to expose the richest neighborhoods for solar, heat-pump, and electrification strategies to sales teams. It is built to answer: *"Where do we start knocking doors first?"*

## 2. What This MVP Is Not
It is absolutely NOT a continuation of the enterprise compliance pipeline. There is no household confirmation, no CRM syncing, no PII intake, no consent auditing, and no direct execution loops.

## 3. How to Run the Pipeline
All scripts exist under `mvp_radar/`.
1. **Mock Feature Engineering**
```bash
python mvp_radar/pipelines/build_area_features.py
```
2. **Score Generation**
```bash
python mvp_radar/scoring/score_engine.py
```
3. **Business Explanations**
```bash
python mvp_radar/explainability/score_explainer.py
```
4. **Launch UI**
```bash
streamlit run mvp_radar/ui/app.py
```

## 4. Documentation Strategy
The governance-heavy product track is strictly preserved and frozen at **Stage 76**.
Check the `docs/` folder for the complete pivot records:
- `pivot_decision_record.md`
- `legacy_stage_76_snapshot.md`
- `migration_map_stage76_to_mvp.md`
- `restart_from_stage76.md`
- `mvp_scope_lock.md`

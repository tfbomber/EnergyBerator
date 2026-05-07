# SESSION HANDOVER: D-ESS Proxy Elimination Architecture
**Date**: 2026-04-11
**Wake Word / 唤醒词**: `Initiate Project Proxy-Purge (数据修复)`

## 1. Current State (End of Option B MVP)
- We successfully completed the expansion of the Neuss Pilot to include 8 PLZ segments across the entire area.
- The pipeline (`field_01` through `field_08`) runs perfectly and has generated rankings for 514 streets.
- **Critical Discovery**: A local resident (the user) correctly flagged that pure desk-research JSON assumptions for Fernwärme (District heat) in PLZ 41470 were completely wrong. 
- **Conclusion**: The MVP architecture contains "Zero Inference/Guessing" violations. Specifically, 4 constraints are currently driven by proxy estimates rather than real deterministic geodata.

## 2. Objective for Next Session
Completely scrub the MVP proxies by integrating official, deterministic German Data Pipelines.

### Target Replacements:
1. **[Heat Networks]**: Replace `layer2_prio2_heat_input.json` desk-research with **Wärmekataster NRW WMS** or official geodata intersect.
2. **[Heat Pump Fit]**: Replace `layer2_prio25_hp_input.json` regional gas-proxy with **Zensus 2022 100x100m** microgrid heating energy census data.
3. **[Roof Area & Typology]**: Replace OSM `POINT` dummy 90m² fallback with **ALKIS** official cadastral building polygons (LoD1/2 shapefiles).

## 3. Next Actions for AI
When the user uses the Wake Word:
1. Do NOT touch strings or UI components.
2. Review `implementation_plan.md` which contains the architectural plan for ALKIS, Zensus, and Wärmekataster.
3. Prompt the user for the raw datasets (Shapefiles / CSVs) if they already have them downloaded locally, and outline the script logic needed for `#1 (Zensus 2022)` or `#2 (ALKIS)` as the primary starting point.

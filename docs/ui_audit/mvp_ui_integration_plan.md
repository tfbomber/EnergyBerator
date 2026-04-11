# 1. Executive Recommendation

The most robust and lowest-risk approach is to introduce a top-level workspace toggle (`st.session_state.workspace_view`). 

Instead of forcing the Neuss Opportunity MVP to mimic the `S1`/`S2` single-property lifecycle within the Canvas, `workspace.py` should act as an overarching router. Depending on whether the user is in `'property'` mode or `'neuss_mvp'` mode, the workspace will selectively mount either the entire existing property inspection stack (State Bar + Canvas + Inspector + Footers) or the new wide-format MVP table.

This completely isolates the MVP from downstream architectural crash risks (such as `inspector.py` searching for `math_trace` in a payload that does not exist).

# 2. Routing Strategy

- **New Session State Key:** `st.session_state.workspace_view`
- **Expected Values:** `"PROPERTY"` (default) | `"NEUSS_MVP"`
- **Initialization:** Inside `ui.pages.workspace.render_workspace()`, define `if "workspace_view" not in st.session_state: st.session_state.workspace_view = "PROPERTY"`.
- **Navigator Integration:** Update `ui/components/navigator.py` to include a new button (e.g., `📍 Neuss Opportunities`). Clicking this button sets `st.session_state.workspace_view = "NEUSS_MVP"`. Conversely, clicking "Quick Scan" or existing pipeline steps should reset the view to `"PROPERTY"`.

# 3. Rendering Strategy

The logic within `ui.pages.workspace.render_workspace()` will be wrapped in an `if/else` block based on `workspace_view`.

**In `PROPERTY` mode:**
- **State Bar:** Rendered normally.
- **Canvas (70%):** Rendered normally.
- **Inspector (30%):** Rendered normally.
- **Bottom Expanders (Copilot / Test Generator):** Rendered normally.

**In `NEUSS_MVP` mode:**
- **State Bar:** HIDDEN (MVP has no S1/S2 status).
- **Canvas:** HIDDEN.
- **Inspector:** HIDDEN.
- **Bottom Expanders:** HIDDEN (Copilot evaluates single-property violations).
- **New Render:** A single, full-width function call `render_opportunity_mvp()` will occupy the screen, dropping the `[7, 3]` column constraint to allow maximum horizontal space for the pandas dataframe.

# 4. Data Isolation Strategy

- **`engine_report` Pipeline:** Remains strictly untouched. No dummy payloads or mocked Single-Property JSONs should be created to pacify existing components, as those components are unmounted.
- **MVP Data Loading:** The new component (`ui/components/opportunity_mvp.py`) will autonomously mount and parse the offline JSON and CSV outputs (`neuss_hybrid_clusters_v1.json`, etc.) using Pandas `read_csv` and `json.load`. 
- **In-Memory Join:** A lightweight, stateless transformation layer (Pandas map/merge) within the render function will compile the 7 required columns instantly. No data is stored in `st.session_state` besides standard Streamlit dataframe cache configurations.

# 5. File-Level Change Plan

## Modify
- `ui/pages/workspace.py`
  - **Reason:** To intercept the rendering flow and introduce the `if st.session_state.workspace_view == "PROPERTY": ... else:` block.
  - **Scope:** Wrap existing Zone B/C/D calls in the `if` block, add the `else` block calling the MVP renderer.
- `ui/components/navigator.py`
  - **Reason:** To provide user access to the new workspace route.
  - **Scope:** Inject a single button `st.button("📍 Neuss Opportunities")` that alters the `workspace_view` state. Include state-reset logic on existing buttons to return to `"PROPERTY"`.

## Add
- `ui/components/opportunity_mvp.py`
  - **Reason:** Centralizes the offline data ingest, Pandas map/join logic, and `st.dataframe` rendering explicitly for the aggregated view. Contains the `render_opportunity_mvp()` function.

## Leave Untouched
- `app.py`: Initialization shell is pure and handles defaults fine.
- `ui/components/canvas.py`: Does not handle multi-target logic.
- `ui/components/inspector.py`: Tightly coupled to strict `audit_trace` dictionaries.
- `ui/components/state_bar.py`: S-tier states do not map to the MVP.
- `ui/components/copilot.py` & `test_generator.py`: Property-specific workflows.

# 6. Risk Prevention Notes

1. **Payload Crash Risks (Eliminated):** By completely hiding the Inspector and Canvas in MVP mode, we guarantee those components will not throw `KeyError` exceptions when they attempt to read an empty or incompatible `engine_report` payload.
2. **State Pollution (Eliminated):** `st.session_state.project_state` holds steady at `S1` or `S2` in the background. Returning to `"PROPERTY"` view seamlessly restores the user to their exact previous position in the single-property wizard.
3. **Layout Breakage (Eliminated):** Bypassing the `st.columns([7, 3])` layout exclusively for the MVP cleanly grants the dataframe 100% of the screen width, vital for multi-column analytic tables.

# 7. Lowest-Effort Implementation Sequence

1. **Create Component:** Write the isolated `ui/components/opportunity_mvp.py` file with the mock/offline Pandas logic and `st.dataframe`.
2. **Initialize State:** Open `ui/pages/workspace.py` and inject `if "workspace_view" not in st.session_state: st.session_state.workspace_view = "PROPERTY"`.
3. **Wrap UI:** In `workspace.py`, indent the State Bar, Main Columns, and Bottom Expanders safely under `if st.session_state.workspace_view == "PROPERTY":`.
4. **Mount MVP:** Add the `elif st.session_state.workspace_view == "NEUSS_MVP": render_opportunity_mvp()` fallback block.
5. **Wire Navigation:** Add the access button to `ui/components/navigator.py` to dynamically switch the state label.

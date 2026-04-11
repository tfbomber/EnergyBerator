# Current UI Baseline Specification

## A. Page / Layout Structure
The current UI is a **Single Page Application (SPA)** built with Streamlit (`main_app.py`).
It uses a horizontal radio-button navigation layout dividing the main rendering area into four primary views, supported by a persistent left sidebar.

**Existing Views (Tabs):**
1. **`VIEW_INTAKE`** (📥 Case Intake): Form inputs for single targets.
2. **`VIEW_REPORT`** (📊 Report Preview): Renders calculation results or policy validations.
3. **`VIEW_TRACE`** (🔍 Evidence & Trace): Developer/Auditor view rendering calculation steps.
4. **`VIEW_EXPORT`** (💾 Export): JSON/Artifact download view.

**Sidebar Controls:**
- View Mode (Client vs. Internal Audit)
- Engine Pipeline selector (Subsidy Audit vs. ROI MVP)
- Policy Engine selector
- Demo / Golden Case loader

## B. Component Inventory (Human-Readable)
The application relies heavily on standard Streamlit native components heavily styled via a global `theme.py` injection.

- **Tables:** Styled HTML math-tables (`<table class="math-table">`), native `st.dataframe` for trace logs and scenario comparisons, and styled Pandas dataframes.
- **Cards/Containers:** Native `st.columns` for metric groupings, custom HTML blocker-cards (`<div class="blocker-card">`) for violations.
- **Metrics:** Native `st.metric` for displaying key numerical highlights (e.g., ROI payload metrics).
- **Score Badges:** Tier badges reflecting data quality (`render_tier_badge`), and custom HTML colored verdict banners (e.g., `report-verdict-ELIGIBLE`, `report-verdict-BLOCKED`).
- **Explanation Panels:** Native `st.expander` for technical details ("Technische Detailansicht anzeigen"), native `st.info`/`st.warning`/`st.error` callouts.
- **Inputs:** Native forms (`st.text_input`, `st.radio`, `st.selectbox`).
- **Map Blocks:** *None exist currently.*

## C. Data Binding
- **State Management:** Data is exclusively bound to `st.session_state` (`current_case_input`, `current_report`, `history`).
- **Data Subject:** The UI is currently bound to **single-address/single-case** payloads. It reads JSON files populated by the backend (or uploaded via demo loader) mapping to the Subsidy schema or the generic ROI schema.
- **Real vs Placeholder:** Output math and traces are real (derived from backend runs). The inputs loaded via Demo cases inject real testing JSON data.

## D. Interaction Model
- **Click → Detail:** Utilizes `st.expander` heavily to hide/show verbose mathematical traces or scenarios.
- **Filtering/Sorting:** Handled natively out-of-the-box by `st.dataframe` for trace log tables.
- **Navigation:** Top radio buttons act as a pseudo-router swapping the active rendering function. Sidebar triggers re-runs to load new case data into state.

## E. Known Gaps / Placeholders
- **No Aggregation View:** The UI is purely focused on analyzing a *single* target building. There is no existing dashboard to view multiple targets, segments, or street-level aggregations.
- **Map Limitations:** Spatial logic exists heavily in the backend, but the frontend lacks any geospatial map visualization block.
- **Hardcoded Modes:** The "Jurisdiction" and "Project Type" in the sidebar are hardcoded to "DE.NRW.DUS" and "BALCONY_PV" (disabled inputs).

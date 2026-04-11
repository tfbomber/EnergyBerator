import streamlit as st
import os
import sys

# Ensure d-ess-engine path is available
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from ui.theme import inject_global_styles
from ui.pages.workspace import render_workspace

st.set_page_config(
    page_title="D-ESS MVP v1.1 Workspace",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_styles()

# Initialize Global Session State for MVP Workspace
if "project_state" not in st.session_state:
    st.session_state.project_state = "S1"
if "compliance_light" not in st.session_state:
    st.session_state.compliance_light = "YELLOW"

# Define dummy navigation for standalone run
def dummy_nav(target):
    st.toast(f"Navigating to {target} (Not implemented in standalone mode)")

render_workspace(navigate_to=dummy_nav)

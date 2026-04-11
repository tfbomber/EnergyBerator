import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
<style>
    .report-verdict-ELIGIBLE { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 5px; font-weight: bold; border-left: 5px solid #28a745; }
    .report-verdict-APPROVED { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 5px; font-weight: bold; border-left: 5px solid #28a745; }
    .report-verdict-BLOCKED { padding: 10px; background-color: #f8d7da; color: #721c24; border-radius: 5px; font-weight: bold; border-left: 5px solid #dc3545; }
    .report-verdict-REJECTED { padding: 10px; background-color: #f8d7da; color: #721c24; border-radius: 5px; font-weight: bold; border-left: 5px solid #dc3545; }
    .report-verdict-NEEDS_INPUT { padding: 10px; background-color: #fff3cd; color: #856404; border-radius: 5px; font-weight: bold; border-left: 5px solid #ffc107; }
    .report-verdict-INCONSISTENT { padding: 10px; background-color: #e2e3e5; color: #383d41; border-radius: 5px; font-weight: bold; border-left: 5px solid #6c757d; }

    .blocker-card {
        background-color: #ffeeee;
        border: 1px solid #ffcccc;
        color: #3f1b1f;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .blocker-card strong { color: #5b121c; }
    .blocker-card small, .blocker-card em { color: #6f2f35; }

    .math-table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    .math-table th, .math-table td {
        border: 1px solid #d0d7de;
        padding: 8px;
        text-align: left;
        color: #1f2328;
        background-color: #ffffff;
    }
    .math-table th {
        background-color: #f2f2f2;
        color: #1f2328;
        font-weight: 600;
    }
    .math-table tr.math-total-row td {
        font-weight: 700;
        background-color: #e8f4f8;
        color: #102a43;
    }

    .risk-chip {
        display: inline-block;
        padding: 0.05rem 0.45rem;
        border-radius: 999px;
        font-weight: 700;
        letter-spacing: 0.01em;
    }
    .risk-chip-medium { color: #663c00; background-color: #fff3cd; border: 1px solid #ffec99; }
    .risk-chip-low { color: #0f5132; background-color: #d1e7dd; border: 1px solid #badbcc; }

    .state-bar, .copilot-chat, .inspector-panel { color: inherit; }
    .green-light, .yellow-light, .red-light {
        display: inline-block;
        padding: 0.05rem 0.45rem;
        border-radius: 999px;
        font-weight: 700;
    }
    .green-light { color: #0f5132; background-color: #d1e7dd; border: 1px solid #badbcc; }
    .yellow-light { color: #664d03; background-color: #fff3cd; border: 1px solid #ffec99; }
    .red-light { color: #842029; background-color: #f8d7da; border: 1px solid #f1aeb5; }
</style>
""",
        unsafe_allow_html=True,
    )

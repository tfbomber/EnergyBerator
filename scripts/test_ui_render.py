from unittest.mock import patch, MagicMock
from ui.components.opportunity_mvp import render_opportunity_mvp

print("Testing UI Rendering Pipeline without Streamlit server...")

# Mock all Streamlit functions used in the module
with patch('streamlit.title') as mock_title, \
     patch('streamlit.caption') as mock_caption, \
     patch('streamlit.divider') as mock_divider, \
     patch('streamlit.error', side_effect=lambda msg: print("ERROR:", msg)) as mock_error, \
     patch('streamlit.warning', side_effect=lambda msg: print("WARNING:", msg)) as mock_warning, \
     patch('streamlit.info') as mock_info, \
     patch('streamlit.success') as mock_success, \
     patch('streamlit.expander') as mock_expander, \
     patch('streamlit.markdown') as mock_markdown, \
     patch('streamlit.columns', side_effect=lambda n: [MagicMock()]*n) as mock_columns, \
     patch('streamlit.dataframe') as mock_dataframe, \
     patch('streamlit.code') as mock_code:
     
     # Run the main render function
     render_opportunity_mvp()
     
     if mock_error.called:
         print("Validation FAILED: The UI reported an error.")
     else:
         print("Validation SUCCESS: The UI successfully ingested and rendered the feed.")
         
     print("\nDataframes requested for rendering:")
     for call in mock_dataframe.call_args_list:
         df = call[0][0].data  # Extract underlying dataframe from styled object
         print(f"Rendered DataFrame rows: {len(df)}")

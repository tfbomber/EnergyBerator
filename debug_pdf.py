import sys, os
from ui.components.s2_pdf_generator import generate_sales_pdf_bytes
from core.roi_mvp import calculate_roi_mvp
import json
import traceback

print("Loading policy...")
with open(os.path.join("policies", "roi_hp_mvp_neuss_2026.json"), "r", encoding="utf-8") as f:
    policy = json.load(f)

case = {
    'attributes': {
        'has_heat_pump': True,
        'has_pv': False,
        'household_size': '3',
        'hp_input_mode': 'MODE_B',
        'hp_bucket': '100_150',
        'ev_status': 'Kein E-Auto',
        'financing_enabled': True
    }
}
print("Calculating ROI MVP...")
res = calculate_roi_mvp(case, policy)

report = {
    'case_id': 'DEBUG123',
    'roi_result': res
}

print("Generating PDF...")
try:
    generate_sales_pdf_bytes(report)
    print("SUCCESS")
except Exception as e:
    print("FAILED!")
    traceback.print_exc()

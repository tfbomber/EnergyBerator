import sys
import os
import json

base_dir = r"d:\Stock Analysis\D-Energy Berater\d-ess-engine"
sys.path.append(os.path.join(base_dir, "core"))
from main import run_engine

cases_dir = os.path.join(base_dir, "cases")
reports_dir = os.path.join(base_dir, "reports")
policy_path = os.path.join(base_dir, "policies", "dus_balcony_pv.json")

for f in os.listdir(cases_dir):
    if f.startswith("golden_") and f.endswith("_input.json"):
        case_path = os.path.join(cases_dir, f)
        expected_path = os.path.join(cases_dir, f.replace("_input.json", "_expected.json"))
        
        try:
            report = run_engine(policy_path, case_path, reports_dir)
            with open(expected_path, "w", encoding="utf-8") as out:
                json.dump(report, out, indent=4)
            print(f"Updated {expected_path}")
        except Exception as e:
            print(f"Failed to run {f}: {e}")

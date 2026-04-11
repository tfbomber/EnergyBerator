import os
import copy
import json

# Ensure core is in path
import sys
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.append(base_dir)

from core.main import run_engine

def run_stacking_engine(case_data, primary_policy_path, secondary_policy_path, output_dir):
    """
    Runs primary policy (KfW), extracts calculated subsidy,
    injects it into case attributes as `other_subsidies_cents`,
    then runs secondary policy (Düsseldorf) to trigger the 60% stacking limit (Kumulierungsgrenze).
    """
    # 1. Save temp case for primary
    temp_case_path = os.path.join(output_dir, "temp_case.json")
    with open(temp_case_path, 'w', encoding='utf-8') as f:
        json.dump(case_data, f)
        
    # 2. Run Primary
    print(f"[ROUTER] Running Primary Policy: {os.path.basename(primary_policy_path)}")
    report_primary = run_engine(primary_policy_path, temp_case_path, output_dir)
    primary_subsidy = report_primary.get("subsidy_total_cents", 0) if report_primary else 0
    print(f"[ROUTER] Primary Policy computed subsidy: {primary_subsidy} cents.")
    
    # 3. Inject subsidy into secondary case
    case_data_secondary = copy.deepcopy(case_data)
    if "attributes" not in case_data_secondary:
        case_data_secondary["attributes"] = {}
    case_data_secondary["attributes"]["other_subsidies_cents"] = primary_subsidy
    
    with open(temp_case_path, 'w', encoding='utf-8') as f:
        json.dump(case_data_secondary, f)
        
    # 4. Run Secondary
    print(f"[ROUTER] Running Secondary Policy: {os.path.basename(secondary_policy_path)}")
    report_secondary = run_engine(secondary_policy_path, temp_case_path, output_dir)
    sec_subsidy = report_secondary.get("subsidy_total_cents", 0) if report_secondary else 0
    
    # Clean up
    if os.path.exists(temp_case_path):
        os.remove(temp_case_path)
        
    num_violations = 0
    violations = []
    
    if report_primary and report_primary.get("violations"):
        violations.extend(report_primary["violations"])
    if report_secondary and report_secondary.get("violations"):
        violations.extend(report_secondary["violations"])
        
    status = "REJECTED" if violations else "APPROVED"
        
    return {
        "status": status,
        "primary_subsidy_cents": primary_subsidy,
        "secondary_subsidy_cents": sec_subsidy,
        "total_subsidy_expected_cents": primary_subsidy + sec_subsidy,
        "violations": violations,
        "audit_trail_primary": report_primary.get("audit_trail", []) if report_primary else [],
        "audit_trail_secondary": report_secondary.get("audit_trail", []) if report_secondary else []
    }

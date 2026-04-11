import os
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_73_DIR = os.path.join(ROOT_DIR, "output", "manual_activation_warrant")

def setup():
    os.makedirs(STAGE_73_DIR, exist_ok=True)

    warrants = {"records": []}
    pool = {"records": []}
    matrix = {"records": []}

    def add_base(cid, verdict, in_pool=True, lock_val="FORBIDDEN", duplicate=False, missing_field=False):
        # Warrant
        rec = {
            "contact_id": cid,
            "manual_activation_warrant": {
                "warrant_verdict": verdict,
                "approved_scope": {}
            }
        }
        if missing_field:
            del rec["contact_id"] # Corrupt the record
            
        warrants["records"].append(rec)
        if duplicate:
            warrants["records"].append(rec)

        # Pool
        if in_pool:
            pool["records"].append({"contact_id": cid})

        # Matrix
        matrix["records"].append({
            "contact_id": cid,
            "AUTO_CONTACT_ALLOWED": lock_val,
            "MANUAL_CONTACT_EXECUTION_ALLOWED": "FORBIDDEN",
            "CRM_TASK_CREATION_ALLOWED": lock_val,
            "APPOINTMENT_BOOKING_ALLOWED": "FORBIDDEN",
            "INSTALLER_ASSIGNMENT_ALLOWED": "FORBIDDEN"
        })

    # CASE A: Perfect valid data.
    add_base("TEST_74_CASE_A", "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE")

    # CASE B: Warrant = PREPARATION_ONLY -> Skipped
    add_base("TEST_74_CASE_B", "MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY")

    # CASE C: Warrant = NOT_GRANTED -> Skipped
    add_base("TEST_74_CASE_C", "MANUAL_WARRANT_NOT_GRANTED", in_pool=False)

    # CASE D: Handled dynamically by caller (renaming files).

    # CASE E: Required field missing (No contact_id) -> record skip
    add_base("TEST_74_CASE_E", "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE", missing_field=True)

    # CASE F: Lock flag broken (AUTO_CONTACT=ALLOWED)
    add_base("TEST_74_CASE_F", "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE", lock_val="ALLOWED")

    # CASE G: Pool mismatch (in pool but not warrant registry)
    pool["records"].append({"contact_id": "TEST_74_CASE_G"})
    # Not adding to warrants.

    # CASE H: Duplicate ID lineage failure
    add_base("TEST_74_CASE_H", "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE", duplicate=True)

    # CASE I: No installer mock available -> STATIC_PLACEHOLDER. 
    # This is implicitly handled by the success of A (or any valid record).
    add_base("TEST_74_CASE_I", "MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE")

    with open(os.path.join(STAGE_73_DIR, "manual_activation_warrant_registry_NEUSS.json"), 'w') as f:
        json.dump(warrants, f, indent=2)

    with open(os.path.join(STAGE_73_DIR, "future_contact_pool_registry_NEUSS.json"), 'w') as f:
        json.dump(pool, f, indent=2)

    with open(os.path.join(STAGE_73_DIR, "warrant_governance_lock_matrix_NEUSS.json"), 'w') as f:
        json.dump(matrix, f, indent=2)

    print("Stage 74 Mock Data Injection Complete.")

if __name__ == "__main__":
    setup()

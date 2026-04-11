import os
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_74_5_DIR = os.path.join(ROOT_DIR, "output", "commercial_readiness_audit")

def setup():
    os.makedirs(STAGE_74_5_DIR, exist_ok=True)

    records = [
        {
            "contact_id": "TEST_75_CASE_A_READY",
            "blocking_reasons": []
        },
        {
            "contact_id": "TEST_75_CASE_B_FATAL",
            "blocking_reasons": ["CONSENT_NOT_EXPLICIT"]
        },
        {
            "contact_id": "TEST_75_CASE_C_RECOVERABLE",
            "blocking_reasons": ["CRM_INTEGRATION_NOT_DEFINED", "INSTALLER_PIPELINE_NOT_DEFINED"]
        },
        {
            "contact_id": "TEST_75_CASE_D_MIXED",
            "blocking_reasons": ["DATA_CONTROLLER_UNDEFINED", "EXECUTION_CHAIN_NOT_DEFINED"]
        }
    ]
    
    audit_registry = {"records": records}
    
    with open(os.path.join(STAGE_74_5_DIR, "commercial_readiness_audit_registry_NEUSS.json"), 'w') as f:
        json.dump(audit_registry, f, indent=2)

    print("Stage 75 Mock Data Injection Complete.")

if __name__ == "__main__":
    setup()

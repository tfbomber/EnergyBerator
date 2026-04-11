import os
import json
from datetime import datetime, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_75_DIR = os.path.join(ROOT_DIR, "output", "non_executable_clearance")
INPUT_PAYLOADS_DIR = os.path.join(ROOT_DIR, "data", "incoming_remediation_payloads")

def setup():
    os.makedirs(STAGE_75_DIR, exist_ok=True)
    os.makedirs(INPUT_PAYLOADS_DIR, exist_ok=True)

    # 1. Build Stage 75 Recoverable Pool (The permitted Baseline)
    recoverable_records = [
        {
            "contact_id": "TEST_76_CASE_A_FULL_FIX",
            "deficiencies": ["CRM_INTEGRATION_NOT_DEFINED", "INSTALLER_PIPELINE_NOT_DEFINED"],
            "remediation_required": True
        },
        {
            "contact_id": "TEST_76_CASE_B_PARTIAL",
            "deficiencies": ["EXECUTION_CHAIN_NOT_DEFINED", "MISSING_ACTIVITY_APPROVAL"],
            "remediation_required": True
        },
        {
            "contact_id": "TEST_76_CASE_C_FATAL_NEW",
            "deficiencies": ["CONTACT_EXECUTOR_UNDEFINED"],
            "remediation_required": True
        },
        {
            "contact_id": "TEST_76_CASE_D_INVALID",
            "deficiencies": ["SUPPORTING_DOCUMENTS_INCOMPLETE"],
            "remediation_required": True
        }
    ]
    
    with open(os.path.join(STAGE_75_DIR, "stage_75_recoverable_pool.json"), 'w') as f:
        json.dump({"records": recoverable_records}, f, indent=2)

    # 2. Build Incoming Mocks with the 9 mandatory fields + simulator control
    payloads = [
        {
            "case_id": "TEST_76_CASE_A_FULL_FIX",
            "prior_status": "NON_EXECUTABLE_BUT_VISIBLE",
            "blocker_targeted": ["CRM_INTEGRATION_NOT_DEFINED", "INSTALLER_PIPELINE_NOT_DEFINED"],
            "evidence_file_name": "crm_int_signed_v2.pdf",
            "evidence_hash": "a1b2c3d4e5f6g7h8",
            "intake_timestamp": datetime.now(timezone.utc).isoformat(),
            "remediation_source": "MANUAL_UPLOAD",
            "reviewer_or_intake_actor": "john.doe",
            "targeted_modules_for_revalidation": ["OPERATIONAL_STRUCTURE_CHAIN", "INSTALLER_READY_CHAIN"],
            "SIMULATED_EVIDENCE_VALIDITY": "VALID"
        },
        {
            "case_id": "TEST_76_CASE_B_PARTIAL",
            "prior_status": "NON_EXECUTABLE_BUT_VISIBLE",
            "blocker_targeted": ["EXECUTION_CHAIN_NOT_DEFINED"], # Resolves 1 of 2
            "evidence_file_name": "chain_doc.pdf",
            "evidence_hash": "zzzzzzzzzzzzz",
            "intake_timestamp": datetime.now(timezone.utc).isoformat(),
            "remediation_source": "MANUAL_UPLOAD",
            "reviewer_or_intake_actor": "jane.smith",
            "targeted_modules_for_revalidation": ["OPERATIONAL_STRUCTURE_CHAIN"],
            "SIMULATED_EVIDENCE_VALIDITY": "VALID"
        },
        {
            "case_id": "TEST_76_CASE_C_FATAL_NEW",
            "prior_status": "NON_EXECUTABLE_BUT_VISIBLE",
            "blocker_targeted": ["CONTACT_EXECUTOR_UNDEFINED"],
            "evidence_file_name": "executor_contract.pdf",
            "evidence_hash": "11111111111111",
            "intake_timestamp": datetime.now(timezone.utc).isoformat(),
            "remediation_source": "LEGAL_TEAM_UPLOAD",
            "reviewer_or_intake_actor": "corp.counsel",
            "targeted_modules_for_revalidation": ["IDENTITY_MAPPING_CHAIN"],
            "SIMULATED_EVIDENCE_VALIDITY": "FATAL_OVERSIGHT_REVEALED"
        },
        {
            "case_id": "TEST_76_CASE_D_INVALID",
            "prior_status": "NON_EXECUTABLE_BUT_VISIBLE",
            "blocker_targeted": ["SUPPORTING_DOCUMENTS_INCOMPLETE"],
            "evidence_file_name": "missing.pdf",
            "evidence_hash": "null",
            "intake_timestamp": datetime.now(timezone.utc).isoformat(),
            "remediation_source": "USER_PORTAL",
            "reviewer_or_intake_actor": "SYSTEM",
            "targeted_modules_for_revalidation": ["DOCUMENT_VALIDATION_CHAIN"],
            "SIMULATED_EVIDENCE_VALIDITY": "INVALID_EVIDENCE_MALFORMED"
        },
        {
            "case_id": "TEST_76_CASE_E_UNAUTHORIZED",
            "prior_status": "FULLY_BLOCKED",
            "blocker_targeted": ["CONSENT_MISSING"],
            "evidence_file_name": "fake_consent.pdf",
            "evidence_hash": "fakehash",
            "intake_timestamp": datetime.now(timezone.utc).isoformat(),
            "remediation_source": "ROGUE_API",
            "reviewer_or_intake_actor": "anonymous",
            "targeted_modules_for_revalidation": ["CONSENT_CHAIN"],
            "SIMULATED_EVIDENCE_VALIDITY": "VALID" # Even if valid, pool gate must reject
        }
    ]

    with open(os.path.join(INPUT_PAYLOADS_DIR, "stage_76_incoming_remediation_payloads_NEUSS.json"), 'w') as f:
        json.dump({"payloads": payloads}, f, indent=2)

    print("Stage 76 Mock Data Injection Complete.")

if __name__ == "__main__":
    setup()

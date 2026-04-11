import os
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_72_DIR = os.path.join(ROOT_DIR, "output", "contact_activation_policy")
REVIEW_DIR = os.path.join(ROOT_DIR, "data", "manual_activation_warrants")

def setup():
    os.makedirs(STAGE_72_DIR, exist_ok=True)
    os.makedirs(REVIEW_DIR, exist_ok=True)

    # Empty old reviews to avoid pollution
    for f in os.listdir(REVIEW_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(REVIEW_DIR, f))

    registry = {"records": []}

    # CASE A: Stage 72 = ELIGIBLE_FOR_ACTIVATION. Review = "approved for future contact stage". -> Output = MANUAL_WARRANT_GRANTED_FOR_FUTURE_CONTACT_STAGE.
    registry["records"].append({
        "contact_id": "TEST_CASE_A",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "ELIGIBLE_FOR_ACTIVATION"}
    })
    with open(os.path.join(REVIEW_DIR, "warrant_TEST_CASE_A.json"), 'w') as f:
        json.dump({"reviewer_id": "U1", "decision": "approved for future contact stage"}, f)

    # CASE B: Stage 72 = READY_FOR_MANUAL_REVIEW. Review = "approved for future contact stage". -> Downgraded to MANUAL_WARRANT_GRANTED_FOR_PREPARATION_ONLY.
    registry["records"].append({
        "contact_id": "TEST_CASE_B",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "READY_FOR_MANUAL_REVIEW"}
    })
    with open(os.path.join(REVIEW_DIR, "warrant_TEST_CASE_B.json"), 'w') as f:
        json.dump({"reviewer_id": "U2", "decision": "approved for future contact stage"}, f)

    # CASE C: Stage 72 = STILL_LOCKED. Review = "approved". -> Overridden to MANUAL_WARRANT_NOT_GRANTED.
    registry["records"].append({
        "contact_id": "TEST_CASE_C",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "STILL_LOCKED"}
    })
    with open(os.path.join(REVIEW_DIR, "warrant_TEST_CASE_C.json"), 'w') as f:
        json.dump({"reviewer_id": "U3", "decision": "approved for future contact stage"}, f)

    # CASE D: Missing review artifact -> MANUAL_WARRANT_NOT_GRANTED.
    registry["records"].append({
        "contact_id": "TEST_CASE_D",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "ELIGIBLE_FOR_ACTIVATION"}
    })
    # NO FILE CREATED

    # CASE E: Ambiguous human language -> Normalized to WARRANT_NOT_GRANTED.
    registry["records"].append({
        "contact_id": "TEST_CASE_E",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "ELIGIBLE_FOR_ACTIVATION"}
    })
    with open(os.path.join(REVIEW_DIR, "warrant_TEST_CASE_E.json"), 'w') as f:
        json.dump({"reviewer_id": "U4", "decision": "kinda maybe ok for usage not sure"}, f)

    # CASE F: Duplicate or conflicting review artifacts -> MANUAL_WARRANT_NOT_GRANTED.
    registry["records"].append({
        "contact_id": "TEST_CASE_F",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {"activation_verdict": "ELIGIBLE_FOR_ACTIVATION"}
    })
    with open(os.path.join(REVIEW_DIR, "warrant1_TEST_CASE_F.json"), 'w') as f:
        json.dump({"reviewer_id": "U5", "decision": "approved for future contact stage"}, f)
    with open(os.path.join(REVIEW_DIR, "warrant2_TEST_CASE_F.json"), 'w') as f:
        json.dump({"reviewer_id": "U6", "decision": "not approved"}, f)

    # CASE G: Malformed Stage 72 record (missing activation_verdict) -> MANUAL_WARRANT_NOT_GRANTED.
    registry["records"].append({
        "contact_id": "TEST_CASE_G",
        "usage_status": "CONDITIONALLY_ELIGIBLE_FOR_FUTURE_STAGE",
        "activation_policy": {}
    })
    with open(os.path.join(REVIEW_DIR, "warrant_TEST_CASE_G.json"), 'w') as f:
        json.dump({"reviewer_id": "U7", "decision": "approved for future contact stage"}, f)

    with open(os.path.join(STAGE_72_DIR, "contact_activation_policy_registry_NEUSS.json"), 'w') as f:
        json.dump(registry, f, indent=2)

    print("Stage 73 Mock Data 7-Cases Generation Complete.")

if __name__ == "__main__":
    setup()

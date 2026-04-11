import os
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STAGE_74_DIR = os.path.join(ROOT_DIR, "output", "execution_dry_run")
CONFIG_DIR = os.path.join(ROOT_DIR, "data", "governance_configs")

def setup():
    os.makedirs(STAGE_74_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # Dry Run Input
    dry_run = {"records": [
        {"contact_id": "TEST_74_5_CASE_A"},
        {"contact_id": "TEST_74_5_CASE_B"},
        {"contact_id": "TEST_74_5_CASE_C"},
        {"contact_id": "TEST_74_5_CASE_D"},
        {"contact_id": "TEST_74_5_CASE_E"},
        {"contact_id": "TEST_74_5_CASE_F"},
        {"contact_id": "TEST_74_5_CASE_G"},
        {"contact_id": "TEST_74_5_CASE_H"}
    ]}
    
    with open(os.path.join(STAGE_74_DIR, "contact_execution_dry_run_registry_NEUSS.json"), 'w') as f:
        json.dump(dry_run, f, indent=2)

    # Base valid config builders
    def base_legal(): return {"consent_status": "EXPLICIT", "legal_basis_status": "CONFIRMED", "data_origin_traceable": True}
    def base_business(): return {"commercial_path": "DESS_DIRECT", "data_controller": "D_ENERGY", "data_processor": "PARTNER_X", "contact_executor": "TEAM_ALPHA", "execution_chain_defined": True, "crm_integration_defined": True, "installer_pipeline_defined": True, "fallback_defined": True}

    legal_config = {}
    business_config = {}

    # CASE A: Perfect valid data.
    legal_config["TEST_74_5_CASE_A"] = base_legal()
    business_config["TEST_74_5_CASE_A"] = base_business()

    # CASE B: Consent missing
    legal_config["TEST_74_5_CASE_B"] = base_legal()
    legal_config["TEST_74_5_CASE_B"]["consent_status"] = "NONE"
    business_config["TEST_74_5_CASE_B"] = base_business()

    # CASE C: Controller missing
    legal_config["TEST_74_5_CASE_C"] = base_legal()
    business_config["TEST_74_5_CASE_C"] = base_business()
    del business_config["TEST_74_5_CASE_C"]["data_controller"]

    # CASE D: Legal basis unknown
    legal_config["TEST_74_5_CASE_D"] = base_legal()
    legal_config["TEST_74_5_CASE_D"]["legal_basis_status"] = "UNKNOWN"
    business_config["TEST_74_5_CASE_D"] = base_business()

    # CASE E: Operational structure missing
    legal_config["TEST_74_5_CASE_E"] = base_legal()
    business_config["TEST_74_5_CASE_E"] = base_business()
    business_config["TEST_74_5_CASE_E"]["execution_chain_defined"] = False

    # CASE F: Data origin not traceable -> FORBIDDEN
    legal_config["TEST_74_5_CASE_F"] = base_legal()
    legal_config["TEST_74_5_CASE_F"]["data_origin_traceable"] = False
    business_config["TEST_74_5_CASE_F"] = base_business()
    
    # CASE G: business_config missing (simulated gracefully by omitting mapping here so it defaults)
    legal_config["TEST_74_5_CASE_G"] = base_legal()
    # No business config inserted for G

    # CASE H: legal_config missing
    # No legal config inserted for H
    business_config["TEST_74_5_CASE_H"] = base_business()

    with open(os.path.join(CONFIG_DIR, "legal_config.json"), 'w') as f:
        json.dump(legal_config, f, indent=2)

    with open(os.path.join(CONFIG_DIR, "business_config.json"), 'w') as f:
        json.dump(business_config, f, indent=2)

    print("Stage 74.5 Mock Data Injection Complete.")

if __name__ == "__main__":
    setup()

import os
import sys
import logging
import json

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Field04_Runner")

def run_ingestion():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_dir = os.path.join(base_dir, "data", "sources", "mastr")
    config_path = os.path.join(base_dir, "config", "raw_to_logical_mastr_template.json")
    
    logger.info("Initializing Field_04 Truth Ingestion Pipeline...")

    # 1. Check Source Folder
    if not os.path.exists(source_dir):
        logger.error(f"SOURCE_FOLDER_MISSING: {source_dir}")
        sys.exit(1)

    # 2. Detect MaStR Export
    files = [f for f in os.listdir(source_dir) if f.startswith("mastr_export_pv_") and f.endswith(".csv")]
    
    if not files:
        logger.warning("-" * 50)
        logger.warning("STATUS: BLOCKED_BY_MISSING_SOURCE")
        logger.warning("No MaStR export file detected in data/sources/mastr/")
        logger.warning("Please drop a file matching 'mastr_export_pv_*.csv' to continue.")
        logger.warning("-" * 50)
        sys.exit(0) # Exit gracefully but report blocked status

    target_file = os.path.join(source_dir, files[0])
    logger.info(f"Source detected: {files[0]}")

    # 3. Check Mapping Contract
    with open(config_path, 'r') as f:
        mapping = json.load(f)
    
    is_mapped = all(v != "" for v in mapping["logical_fields"].values())
    
    if not is_mapped:
        logger.error("-" * 50)
        logger.error("STATUS: BLOCKED_BY_INCOMPLETE_MAPPING")
        logger.error("Mapping template exists but columns are not yet identified.")
        logger.error("Action REQUIRED: Run 'python scripts/inspect_mastr_schema.py' and fill config/raw_to_logical_mastr_template.json")
        logger.error("-" * 50)
        sys.exit(1)

    # 4. Final Fail-Fast (Production Logic Placeholder)
    logger.info("Validation passed. Ready for truth ingestion logic.")
    # TODO: Trigger real ingestion when data exists and mapping is complete.

if __name__ == "__main__":
    run_ingestion()

import os
import csv
import json
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MaStR_Inspector")

def inspect_schema():
    source_dir = "d:/Stock Analysis/D-Energy Berater/d-ess-engine/data/sources/mastr/"
    output_report = "d:/Stock Analysis/D-Energy Berater/d-ess-engine/data/sources/mastr/mastr_schema_report.json"
    
    # 1. Look for MaStR CSV
    files = [f for f in os.listdir(source_dir) if f.startswith("mastr_export_pv_") and f.endswith(".csv")]
    
    if not files:
        logger.error("No MaStR export file found for inspection.")
        return

    target_file = os.path.join(source_dir, files[0])
    logger.info(f"Inspecting file: {target_file}")

    try:
        with open(target_file, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=',') # Standard MaStR might be ; or ,
            header = next(reader)
            
        report = {
            "source_file": files[0],
            "detected_columns": header,
            "column_count": len(header),
            "timestamp_utc": "2026-03-10T22:24:00Z",
            "required_logical_fields_verification": {
                "technology_type": "MISSING_MAPPING",
                "installation_id": "MISSING_MAPPING",
                "latitude": "MISSING_MAPPING",
                "longitude": "MISSING_MAPPING"
            }
        }
        
        with open(output_report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"Schema report generated at {output_report}")
        print("\n--- DETECTED COLUMNS ---")
        for i, col in enumerate(header):
            print(f"{i}: {col}")
            
    except Exception as e:
        logger.error(f"Failed to inspect schema: {str(e)}")

if __name__ == "__main__":
    inspect_schema()

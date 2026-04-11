import os
import yaml
import pandas as pd
import importlib
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FieldRunner")

def run_all_fields():
    """
    Main entry point for running all implemented fields defined in the registry.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "field_registry.yaml")
    buildings_path = os.path.join(base_dir, "data", "buildings.parquet")
    output_base_dir = os.path.join(base_dir, "data", "fields")
    
    if not os.path.exists(config_path):
        logger.error(f"Registry not found: {config_path}")
        return

    with open(config_path, "r") as f:
        registry = yaml.safe_load(f)

    # Load buildings dataset
    if not os.path.exists(buildings_path):
        logger.warning(f"Input dataset not found at {buildings_path}. Using mock data for demonstration.")
        # Mock data if file missing (to prevent crash during architectural setup)
        buildings_df = pd.DataFrame([
            {"building_id": "BLDG_001", "segment_id": "SEG_A", "geometry": None, "building_type": "UNKNOWN", "neighbors": []},
            {"building_id": "BLDG_002", "segment_id": "SEG_A", "geometry": None, "building_type": "UNKNOWN", "neighbors": ["BLDG_003"]},
            {"building_id": "BLDG_003", "segment_id": "SEG_A", "geometry": None, "building_type": "UNKNOWN", "neighbors": ["BLDG_002", "BLDG_004"]},
        ])
    else:
        buildings_df = pd.read_parquet(buildings_path)

    os.makedirs(output_base_dir, exist_ok=True)

    fields = registry.get("fields", {})
    for field_id, meta in fields.items():
        if meta.get("status") == "implemented":
            field_name = meta.get("name")
            module_name = f"fields.{field_id}_{field_name}"
            
            logger.info(f"Running {field_id}: {field_name}...")
            
            try:
                # Dynamic import of the field module
                module = importlib.import_module(module_name)
                
                # Execute the 'run' function
                field_results = module.run(buildings_df)
                
                # Save results to parquet
                output_path = os.path.join(output_base_dir, f"{field_id}_{field_name}.parquet")
                field_results.to_parquet(output_path, index=False)
                
                logger.info(f"✅ {field_id} completed. Saved to {output_path}")
                
            except Exception as e:
                logger.error(f"❌ Failed to execute {field_id}: {str(e)}")

if __name__ == "__main__":
    run_all_fields()

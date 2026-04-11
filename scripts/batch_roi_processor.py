import os
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from core.roi_mvp import calculate_roi_mvp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_batch_roi_campaign(data_version: str, policy_path: str):
    """
    Orchestrates the ROI calculation for all eligible segments in a campaign.
    """
    logger.info(f"Starting batch ROI processing for version: {data_version}")
    
    # 1. Load Policy
    try:
        with open(policy_path, 'r', encoding='utf-8') as f:
            policy = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load policy file: {e}")
        return

    # 2. Database Connection
    # In a real production environment, these would come from environment variables
    conn_params = {
        "host": os.getenv("DB_HOST", "localhost"),
        "database": os.getenv("DB_NAME", "dess_gis"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASS", "password"),
        "port": os.getenv("DB_PORT", "5432")
    }

    try:
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return

    try:
        # 3. Fetch Eligible Payloads
        query = """
            SELECT 
                segment_id, 
                target_audience, 
                qualification_state, 
                roi_inputs_payload 
            FROM output.v_segment_roi_payload_json
            WHERE data_version = %s
        """
        cursor.execute(query, (data_version,))
        segments = cursor.fetchall()
        
        logger.info(f"Retrieved {len(segments)} eligible segments for processing.")

        for seg in segments:
            segment_id = seg['segment_id']
            payload = seg['roi_inputs_payload']
            
            # Map DB payload to ROI engine case structure
            case = {
                "attributes": payload
            }
            
            logger.info(f"Calculating ROI for Segment: {segment_id} ({seg['target_audience']})")
            
            # 4. Invoke ROI Engine
            result = calculate_roi_mvp(case, policy)
            
            if result.get("verdict") == "ROI_OK":
                # 5. Save results to output.segment_roi_profile
                # We extract baseline metrics (usually the 2nd scenario in Neuss policy)
                baseline = result["scenarios"][1] if len(result["scenarios"]) > 1 else result["scenarios"][0]
                
                # Check for existing record
                profile_id = f"{segment_id}_{data_version}_P01" # Simplified naming
                
                upsert_query = """
                    INSERT INTO output.segment_roi_profile (
                        segment_roi_profile_id, segment_id, data_version, 
                        policy_version, roi_engine_version, scenario_name,
                        typical_kwp, typical_annual_generation_kwh, 
                        typical_self_consumption_ratio, typical_year1_benefit_eur,
                        typical_payback_years, typical_20y_profit_eur,
                        co2_reduction_annual_kg, profile_confidence_index
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (segment_roi_profile_id) DO UPDATE SET
                        typical_kwp = EXCLUDED.typical_kwp,
                        typical_year1_benefit_eur = EXCLUDED.typical_year1_benefit_eur,
                        generated_at = CURRENT_TIMESTAMP;
                """
                
                cursor.execute(upsert_query, (
                    profile_id,
                    segment_id,
                    data_version,
                    policy.get("version", "2026.1"),
                    "3.5", # Engine version
                    baseline["name"],
                    result["recommended_kwp"],
                    result["e_pv_kwh"],
                    float(baseline["e_self_kwh"]) / result["e_pv_kwh"] if result["e_pv_kwh"] > 0 else 0,
                    baseline["annual_benefit_cents"] / 100.0,
                    baseline["payback_dynamic_years"],
                    baseline["profit20_cents"] / 100.0,
                    result["carbon_impact"]["annual_co2_reduction_kg"],
                    0.85 # Confidence proxy
                ))
                logger.info(f"✅ Segment {segment_id} processed and saved.")
            else:
                logger.warning(f"❌ Segment {segment_id} failed calculation: {result.get('reason')}")

        conn.commit()
        logger.info("Batch processing completed successfully.")

    except Exception as e:
        logger.error(f"Error during batch processing: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Example usage for Neuss Pilot
    run_batch_roi_campaign(
        data_version="NEUSS_V1_2026", 
        policy_path="policies/roi_hp_mvp_neuss_2026.json"
    )

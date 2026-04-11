import json
import os
import logging
from datetime import datetime
from typing import Dict

# Import Spiders
try:
    from .spiders.duesseldorf import DusseldorfCrawler
    from .models import StatusOverlay, PolicyUpdate, CrawlerHealth
except ImportError:
    from crawler.spiders.duesseldorf import DusseldorfCrawler
    from crawler.models import StatusOverlay, PolicyUpdate, CrawlerHealth

logger = logging.getLogger("crawler.runner")

def load_overlay(path: str) -> StatusOverlay:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Overlay JSON root must be an object")

                updates = data.get("updates")
                if isinstance(updates, dict):
                    return StatusOverlay(updates=updates)

                return StatusOverlay(updates=data)
        except Exception as e:
            logger.warning(f"Failed to load overlay {path}: {e}. Starting fresh.")
    
    return StatusOverlay(updates={})

def save_overlay(path: str, overlay: StatusOverlay):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        data = {
            "updates": {
                pid: update.model_dump(mode='json')
                for pid, update in overlay.updates.items()
            }
        }
        json.dump(data, f, indent=2, ensure_ascii=False)

def run_crawlers(base_dir: str):
    """
    Main entry point for "The Harvester".
    """
    logging.basicConfig(level=logging.INFO)
    
    intelligence_dir = os.path.join(base_dir, "intelligence")
    overlay_path = os.path.join(intelligence_dir, "status_updates.json")
    snapshot_dir = os.path.join(intelligence_dir, "snapshots")
    
    # 1. Load existing overlay
    overlay = load_overlay(overlay_path)
    
    # 2. Define Crawlers
    spiders = [
        DusseldorfCrawler(
            policy_id="DUS_BALCONY_PV_2025",
            snapshot_dir=snapshot_dir,
            expected_pdf_hash="sha256:todo"
        )
    ]
    
    # 3. Run Sequentially
    print("Starting D-ESS Policy Harvester...")
    
    for spider in spiders:
        print(f"[{spider.policy_id}] Crawling...")
        update = spider.run()
        
        # 4. Merge Logic
        overlay.updates[spider.policy_id] = update
        print(f"[{spider.policy_id}] Finished. Status: {update.status} (Health: {update.health})")
        
    # 5. Save
    save_overlay(overlay_path, overlay)
    print(f"Overlay saved to {overlay_path}")
    
    hc_url = os.environ.get("HEALTHCHECKS_URL")
    if hc_url:
        print("Pinging Healthchecks.io...")
        try:
             import requests
             requests.get(hc_url, timeout=10)
             print("Ping sent.")
        except Exception as e:
             print(f"Failed to ping Healthchecks: {e}")

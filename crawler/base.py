import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from crawler.models import PolicyUpdate, CrawlerHealth, PolicyStatus, DocIntegrity, CrawlerSignals, CrawlerEvidence

# Configuration
USER_AGENT = "D-ESS Policy Harvester/1.0 (+http://your-domain.com/bot)"
TIMEOUT_SECONDS = 15

class PolicyCrawler(ABC):
    """
    Abstract Base Class for Policy Crawlers.
    Implements the 'Harvester Protocol':
    1. Fetch Targets (Retry logic)
    2. Parse & Decision Logic (Abstract)
    3. Validate (Schema & Boundary)
    4. Persist (Overlay & Snapshots)
    """
    
    def __init__(self, policy_id: str, snapshot_dir: str):
        self.policy_id = policy_id
        self.snapshot_dir = Path(snapshot_dir)
        self.session = self._init_session()
        self.logger = logging.getLogger(f"crawler.{policy_id}")

    def _init_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        s.mount('https://', HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": USER_AGENT})
        return s

    def run(self) -> PolicyUpdate:
        """Main execution flow."""
        try:
            # 1. Crawl
            update_data = self.crawl()
            
            # 2. Schema Validation (Implicit via Pydantic return type)
            # 3. Boundary Check (Custom logic if needed)
            
            return update_data
            
        except Exception as e:
            self.logger.error(f"Crawler failed: {e}", exc_info=True)
            # Return a specialized Error Update
            return self._create_error_update(str(e))

    @abstractmethod
    def crawl(self) -> PolicyUpdate:
        """
        Implementation specific logic.
        Must return a valid PolicyUpdate object.
        """
        pass

    def fetch_page(self, url: str) -> Tuple[Optional[str], int]:
        """Safe fetcher with timeout."""
        try:
            resp = self.session.get(url, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text, resp.status_code
        except Exception as e:
            self.logger.warning(f"Failed to fetch {url}: {e}")
            return None, 0

    def download_doc_hash(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Stream download PDF to calculate SHA-256 without loading full file to RAM.
        Returns: (sha256_hash, last_modified_header)
        """
        try:
            # Head first
            head = self.session.head(url, timeout=TIMEOUT_SECONDS)
            last_mod = head.headers.get("Last-Modified")
            
            # Get stream
            resp = self.session.get(url, stream=True, timeout=TIMEOUT_SECONDS * 2)
            resp.raise_for_status()
            
            sha256 = hashlib.sha256()
            for chunk in resp.iter_content(chunk_size=8192):
                 if chunk:
                     sha256.update(chunk)
            
            return f"sha256:{sha256.hexdigest()}", last_mod
            
        except Exception as e:
            self.logger.error(f"Doc download failed: {e}")
            return None, None

    def save_snapshot(self, content: str, suffix: str = ".html") -> str:
        """Saves content to snapshot dir and returns ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.policy_id}_{timestamp}{suffix}"
        path = self.snapshot_dir / filename
        
        # Ensure dir exists
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"file://{path.name}"

    def _create_error_update(self, reason: str) -> PolicyUpdate:
        return PolicyUpdate(
            policy_id=self.policy_id,
            last_checked_utc=datetime.utcnow(),
            status=PolicyStatus.UNKNOWN,
            health=CrawlerHealth.ERROR,
            status_reason_de=f"Crawler Run Failed: {reason}",
            signals=CrawlerSignals(
                landing_claim_open=False, 
                portal_operational=False,
                portal_allows_new_application="unknown"
            ),
            doc_integrity=DocIntegrity(local_hash_match=False)
        )

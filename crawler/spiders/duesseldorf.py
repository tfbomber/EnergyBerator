from datetime import datetime
from bs4 import BeautifulSoup
from crawler.base import PolicyCrawler
from crawler.models import PolicyUpdate, PolicyStatus, CrawlerHealth, DocIntegrity, CrawlerSignals, CrawlerEvidence

class DusseldorfCrawler(PolicyCrawler):
    """
    Spider for Düsseldorf "Klimafreundliches Wohnen"
    """
    LANDING_URL = "https://www.duesseldorf.de/klimafreundlich-wohnen"
    PORTAL_URL = "https://foerderung.duesseldorf.de"
    
    # Validation Keywords
    KEYWORDS_CLOSED = ["ausgeschöpft", "beendet", "Mittel leer"]
    KEYWORDS_PAUSED = [
        "pausiert", "überarbeitet", "vorübergehend ausgesetzt", 
        "Programm wird überarbeitet", "unter Vorbehalt", 
        "bis auf Weiteres", "suspended", "paused", "under revision"
    ]
    KEYWORDS_OPEN = ["Antragstellung möglich", "Jetzt beantragen"]

    def __init__(self, policy_id: str, snapshot_dir: str, expected_pdf_hash: str):
        super().__init__(policy_id, snapshot_dir)
        self.expected_pdf_hash = expected_pdf_hash

    def crawl(self) -> PolicyUpdate:
        self.logger.info(f"Starting crawl for {self.policy_id}")
        
        # 1. Fetch Landing Page
        html_landing, status_landing = self.fetch_page(self.LANDING_URL)
        if not html_landing or status_landing != 200:
            return self._create_error_update(f"Landing Page unreachable: {status_landing}")
            
        # Snapshot
        snap_id = self.save_snapshot(html_landing, "_landing.html")
        
        # 2. Parse Landing Semantics (Traffic Light)
        soup = BeautifulSoup(html_landing, "html.parser")
        text_content = soup.get_text()
        
        matched_closed = [k for k in self.KEYWORDS_CLOSED if k in text_content]
        matched_paused = [k for k in self.KEYWORDS_PAUSED if k in text_content]
        
        is_closed = len(matched_closed) > 0
        is_paused = len(matched_paused) > 0
        claim_open = any(k in text_content for k in self.KEYWORDS_OPEN)
        
        # 3. Check Portal (Operational Gate)
        portal_operational = False
        try:
             _, p_status = self.fetch_page(self.PORTAL_URL)
             if p_status < 400:
                 portal_operational = True
        except:
             pass

        # 4. Decide Status
        final_status = PolicyStatus.UNKNOWN
        reason = "Analysis inconclusive"
        matched_keywords = []
        
        if is_closed:
            final_status = PolicyStatus.CLOSED
            reason = f"Keyword {matched_closed} found on landing page."
            matched_keywords = matched_closed
        elif is_paused:
            final_status = PolicyStatus.PAUSED
            reason = f"Keyword {matched_paused} found. Program under revision."
            matched_keywords = matched_paused
        elif claim_open and portal_operational:
            final_status = PolicyStatus.OPEN
            reason = "Landing claims Open matches Portal 200 OK."
        else:
             # Fallback logic
             if not is_paused and not is_closed and portal_operational:
                  final_status = PolicyStatus.UNKNOWN
                  reason = "Portal Open but no explicit 'Apply Now' found."
             else:
                  final_status = PolicyStatus.UNKNOWN
                  reason = "No clear traffic light signal found."

        # 5. PDF Integrity
        doc_integrity = DocIntegrity(local_hash_match=True, remote_hash=None)
        # Note: the PDF URL might change, the previous one returned 404
        pdf_url = "https://www.duesseldorf.de/fileadmin/Amt19/umweltamt/klimaschutz/klimafreundliches_wohnen_und_arbeiten/Foerderrichtlinie_Klimafreundliches_Wohnen_und_Arbeiten.pdf"
        
        remote_hash, _ = self.download_doc_hash(pdf_url)
        if remote_hash:
            doc_integrity.remote_hash = remote_hash
            if self.expected_pdf_hash and self.expected_pdf_hash != "sha256:todo":
                doc_integrity.local_hash_match = (remote_hash == self.expected_pdf_hash)
            else:
                doc_integrity.local_hash_match = True
        
        return PolicyUpdate(
            policy_id=self.policy_id,
            last_checked_utc=datetime.utcnow(),
            status=final_status,
            health=CrawlerHealth.OK,
            status_reason_de=reason,
            signals=CrawlerSignals(
                landing_claim_open=claim_open,
                portal_operational=portal_operational,
                portal_allows_new_application="unknown"
            ),
            doc_integrity=doc_integrity,
            evidence=CrawlerEvidence(
                snapshot_id=snap_id
            ),
            matched_keywords=matched_keywords
        )

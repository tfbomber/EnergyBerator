from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class PolicyStatus(str, Enum):
    OPEN = "OPEN"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"

class CrawlerHealth(str, Enum):
    OK = "OK"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"

class DocIntegrity(BaseModel):
    remote_hash: Optional[str] = Field(None, description="SHA-256 hash of the remote document")
    local_hash_match: bool = Field(..., description="True if remote hash matches local policy file")
    last_modified: Optional[str] = Field(None, description="Last-Modified header from server")
    etag: Optional[str] = None

class CrawlerSignals(BaseModel):
    landing_claim_open: bool = Field(..., description="True if landing page explicitly says Apply Now")
    portal_operational: bool = Field(..., description="True if portal returns 200 and expected elements")
    portal_allows_new_application: str = Field("unknown", description="true/false/unknown")

class CrawlerEvidence(BaseModel):
    snapshot_id: str = Field(..., description="ID of the stored HTML/PDF snapshot")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class PolicyUpdate(BaseModel):
    policy_id: str
    last_checked_utc: datetime
    status: PolicyStatus
    health: CrawlerHealth
    status_reason_de: str
    signals: CrawlerSignals
    doc_integrity: DocIntegrity
    evidence: Optional[CrawlerEvidence] = None
    matched_keywords: List[str] = Field(default_factory=list, description="Keywords that triggered PAUSED/CLOSED status")

class StatusOverlay(BaseModel):
    updates: Dict[str, PolicyUpdate]

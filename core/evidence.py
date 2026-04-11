import hashlib
import json
import os
from typing import Dict, Optional, Tuple

def sha256_file(path: str) -> str:
    """Computes SHA-256 hash of a local file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Evidence file not found: {path}")
        
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        # Read in chunks to handle large files efficiently
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def load_evidence_index(path: str) -> Dict:
    """Loads the evidence index JSON."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Evidence index not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def resolve_anchor(policy_id: str, anchor_id_or_text: str, index: Dict, evidence_ref: Optional[str] = None, base_dir: Optional[str] = None) -> Tuple[str, str]:
    """
    Resolves an anchor ID to its full text location using the index.
    Returns: (ResolvedText, Strategy)
    """
    strategy = "FALLBACK"
    
    # 1. Physical File Probe (M2-A1)
    if evidence_ref:
        if os.path.isabs(evidence_ref) and os.path.exists(evidence_ref):
            abs_evidence_path = evidence_ref
        elif base_dir:
            abs_evidence_path = os.path.join(base_dir, evidence_ref)
        else:
            abs_evidence_path = evidence_ref

        if not os.path.exists(abs_evidence_path):
            raise FileNotFoundError(f"evidence file not found: {evidence_ref} (anchor not evaluated)")

    # 2. Anchor Resolution (M2-A2)
    if policy_id not in index:
        return anchor_id_or_text, "NO_INDEX_FOR_POLICY"
        
    policy_entry = index[policy_id]
    anchors_map = policy_entry.get("anchors_map", {})
    
    if anchor_id_or_text in anchors_map:
        return anchors_map[anchor_id_or_text], "INDEX_MATCH"
        
    # Strict mode: If it looks like an ID
    if "_" in anchor_id_or_text and anchor_id_or_text.isupper() and " " not in anchor_id_or_text:
        raise KeyError(f"mandatory anchor_id '{anchor_id_or_text}' not found in index")

    return anchor_id_or_text, strategy

def validate_policy_anchors(policy: Dict, index: Dict):
    """
    Strictly validates that all 'evidence_anchor' fields in the policy
    exist in the evidence index.
    """
    policy_id = policy.get("policy_id")
    if not policy_id:
        return 
        
    if policy_id not in index:
        raise ValueError(f"Policy {policy_id} not found in Evidence Index.")
        
    indexed_anchors = set(index[policy_id].get("anchors_map", {}).keys())
    # Decision: Policy MUST use IDs. 
    
    def check_anchors(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "evidence_anchor":
                    if v not in indexed_anchors:
                        raise ValueError(f"Invalid Evidence Anchor '{v}' at {path}. Not found in index.")
                else:
                    check_anchors(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_anchors(item, f"{path}[{i}]")

    check_anchors(policy)

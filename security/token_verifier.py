import json
import base64
import os
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

def verify_execution_token(token: dict, required_scope: str, audience: str = "DESS_PIPELINE", registry_path: str = None, public_key_path: str = None) -> dict:
    # 1. Structural Integrity & Presence
    if not isinstance(token, dict):
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}
        
    payload = token.get("payload")
    if not payload or not isinstance(payload, dict):
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}

    signature_b64 = token.get("signature")
    if not signature_b64:
        return {"verdict": "DENIED", "reason": "SIGNATURE_MISSING"}
        
    if token.get("signature_algorithm") != "Ed25519":
        return {"verdict": "DENIED", "reason": "SIGNATURE_INVALID"}

    # 2. Time Validation
    issued_at_str = payload.get("issued_at")
    expires_at_str = payload.get("expires_at")
    
    if not issued_at_str or not expires_at_str:
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}

    try:
        # Expected format: "2026-03-16T12:00:00Z"
        issued_at = datetime.fromisoformat(issued_at_str.replace('Z', '+00:00'))
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
    except Exception:
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}

    # Time expiration logic (Assuming current time is inside the bounds conceptually, but strictly evaluating expires_at > now UTC)
    now = datetime.utcnow()
    # To avoid timezone tzinfo parsing issues strictly in ISO, just compare naive UTC strings
    # But since we have datetime objects:
    now = now.replace(tzinfo=issued_at.tzinfo)
    
    if now > expires_at:
        return {"verdict": "DENIED", "reason": "TOKEN_EXPIRED"}
        
    if issued_at >= expires_at:
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}

    # 3. Audience Validation
    if payload.get("audience") != audience:
        return {"verdict": "DENIED", "reason": "AUDIENCE_MISMATCH"}
        
    # 4. Operator Validation
    operator_id = payload.get("operator_id")
    if not operator_id:
        return {"verdict": "DENIED", "reason": "TOKEN_MALFORMED"}

    if registry_path and os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        return {"verdict": "DENIED", "reason": "UNKNOWN_OPERATOR"}

    operator = next((op for op in registry.get("operators", []) if op.get("operator_id") == operator_id), None)
    
    if not operator:
        return {"verdict": "DENIED", "reason": "UNKNOWN_OPERATOR"}
        
    if operator.get("status") != "ACTIVE":
        return {"verdict": "DENIED", "reason": "OPERATOR_INACTIVE"}

    # 5. Scope Validation
    scopes = payload.get("scope", [])
    if required_scope not in scopes:
        return {"verdict": "DENIED", "reason": "REQUIRED_SCOPE_MISSING"}
        
    authorized_scopes = operator.get("authorized_scopes", [])
    if required_scope not in authorized_scopes:
        return {"verdict": "DENIED", "reason": "SCOPE_NOT_AUTHORIZED"}

    # 6. Cryptographic Signature Validation
    canonical_payload = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    
    try:
        sig_bytes = base64.b64decode(signature_b64)
    except Exception:
        return {"verdict": "DENIED", "reason": "SIGNATURE_INVALID"}
        
    try:
        with open(public_key_path, "rb") as key_file:
            public_bytes = key_file.read()
        public_key = serialization.load_pem_public_key(public_bytes)
        
        public_key.verify(sig_bytes, canonical_payload)
    except InvalidSignature:
        return {"verdict": "DENIED", "reason": "SIGNATURE_INVALID"}
    except Exception:
        return {"verdict": "DENIED", "reason": "SIGNATURE_INVALID"}

    return {"verdict": "AUTHORIZED", "reason": "VALID_SIGNATURE_AND_POLICY"}

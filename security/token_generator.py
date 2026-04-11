import json
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519

def generate_execution_token(payload: dict, private_key_path: str) -> dict:
    """
    Generates a signed execution token.
    The signature is computed over the canonical JSON serialization of the payload.
    """
    with open(private_key_path, "rb") as key_file:
        private_bytes = key_file.read()

    # Load Ed25519 private key
    from cryptography.hazmat.primitives import serialization
    private_key = serialization.load_pem_private_key(
        private_bytes,
        password=None
    )

    # Canonical serialization: no spaces, sorted keys
    canonical_payload = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')

    # Sign using Ed25519
    signature_bytes = private_key.sign(canonical_payload)
    signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')

    envelope = {
        "payload": payload,
        "signature": signature_b64,
        "signature_algorithm": "Ed25519"
    }

    return envelope

import os
import requests
import hmac
import hashlib
import json
import base64
from dotenv import load_dotenv

# Add these imports for key derivation and encryption
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

load_dotenv()

# --- CONFIGURATION ---
API_BASE_URL = os.environ.get("API_BASE_URL") 
if not API_BASE_URL:
    raise ValueError("Please set the API_BASE_URL environment variable.")

# This is the single master key that MUST match what's in Secret Manager
ANCHOR_KEY_MASTER = "ENVOY_API_PASS1234"

# --- DERIVE KEYS on client-side, matching the server's logic ---
master_key_bytes = ANCHOR_KEY_MASTER.encode()

# 1. Derive the HMAC authentication key
hkdf_auth = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,
    info=b'envoy-api-hmac-authentication-key', # MUST BE IDENTICAL TO SERVER
)
AUTH_KEY_DERIVED = hkdf_auth.derive(master_key_bytes)

# 2. Derive the Fernet encryption key
hkdf_encrypt = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,
    info=b'envoy-api-fernet-encryption-key', # MUST BE IDENTICAL TO SERVER
)
encryption_key_derived = base64.urlsafe_b64encode(hkdf_encrypt.derive(master_key_bytes))
FERNET_INSTANCE_CLIENT = Fernet(encryption_key_derived)


def generate_signature(body: bytes) -> str:
    """Generates the HMAC-SHA256 signature using the DERIVED auth key."""
    return hmac.new(
        key=AUTH_KEY_DERIVED, # Use the derived key
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()

def test_boot():
    print("\n--- Testing /boot endpoint ---")
    url = f"{API_BASE_URL}/boot"
    payload = {
        "device_id": "test-device-hkdf-456",
        "firmware_version": "1.1.0",
        "config_version": 5
    }
    body = json.dumps(payload).encode()
    signature = generate_signature(body)
    headers = {'Content-Type': 'application/json', 'X-Anchor-Signature': signature}
    try:
        response = requests.post(url, data=body, headers=headers, timeout=15)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")
        assert response.status_code == 200
        print("✅ /boot PASSED")
    except Exception as e:
        print(f"❌ /boot FAILED: {e}")

def test_ingest():
    print("\n--- Testing /ingest endpoint ---")
    # We pass the filename as a query parameter now
    filename = "secret.log.enc"
    url = f"{API_BASE_URL}/ingest?filename={filename}"
    
    # 1. Encrypt a dummy file
    plaintext_content = b"This is a secret log file, sent as raw binary."
    encrypted_content = FERNET_INSTANCE_CLIENT.encrypt(plaintext_content)

    # 2. The signature is generated on the raw encrypted bytes
    signature = generate_signature(encrypted_content)
    
    # 3. The headers now include the signature and the content type
    headers = {
        'X-Anchor-Signature': signature,
        'Content-Type': 'application/octet-stream' # Best practice for binary data
    }
    
    try:
        # 4. CRITICAL CHANGE: Send the raw bytes using the 'data' parameter,
        #    NOT the 'files' parameter for multipart upload.
        response = requests.post(url, data=encrypted_content, headers=headers, timeout=20)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")
        assert response.status_code == 200
        assert 'gcs_path' in response.json()
        print("✅ /ingest PASSED")
    except Exception as e:
        print(f"❌ /ingest FAILED: {e}")

# (The invalid signature test remains the same)
def test_invalid_signature():
    print("\n--- Testing Invalid Signature (expect 403) ---")
    url = f"{API_BASE_URL}/directive"
    body = b'{}'
    headers = {'Content-Type': 'application/json', 'X-Anchor-Signature': 'invalid'}
    try:
        response = requests.post(url, data=body, headers=headers, timeout=15)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")
        assert response.status_code == 403
        print("✅ Invalid Signature Test PASSED")
    except Exception as e:
        print(f"❌ Invalid Signature Test FAILED: {e}")

if __name__ == "__main__":
    test_boot()
    test_ingest()
    test_invalid_signature()
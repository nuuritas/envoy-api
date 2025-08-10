import os
import hmac
import hashlib
import json
import base64
from datetime import datetime

from fastapi import FastAPI, Request, Header, HTTPException, Depends, UploadFile, File
from dotenv import load_dotenv

# --- Dynamic Imports for Cloud Libraries ---
# This ensures we only import them when needed
google = None
secretmanager = None
storage = None
firestore = None
Fernet = None
hashes = None
HKDF = None

# --- Configuration ---
# Check for a standard Cloud Run environment variable to determine if we are in production.
IS_PROD_ENVIRONMENT = "K_SERVICE" in os.environ

if IS_PROD_ENVIRONMENT:
    print("PROD mode detected. Importing Google Cloud libraries.")
    from google.cloud import secretmanager, storage, firestore
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
else:
    print("!!! Running in LOCAL development mode. Loading secrets from .env file. !!!")
    load_dotenv() # This loads the variables from .env into the environment
    # Import crypto libraries for local mode too
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET_NAME = os.environ.get("BUCKET_NAME") 
SECRET_ID = "ANCHOR_KEY"

# --- FastAPI App and Conditional Clients ---
app = FastAPI()

if IS_PROD_ENVIRONMENT:
    print("Initializing Google Cloud clients for PROD environment...")
    storage_client = storage.Client()
    firestore_client = firestore.AsyncClient()
else:
    storage_client = None
    firestore_client = None


def get_anchor_key():
    """
    Retrieves the master anchor key. In Production from Secret Manager, in Local from .env.
    """
    if IS_PROD_ENVIRONMENT:
        print("Fetching ANCHOR_KEY from Google Secret Manager...")
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"FATAL: Could not fetch ANCHOR_KEY from Secret Manager. Error: {e}")
            raise
    else:
        print("Fetching ANCHOR_KEY from local environment variables...")
        key = os.environ.get("ANCHOR_KEY")
        if not key:
            raise ValueError("FATAL: ANCHOR_KEY not set for local development. Check your .env file.")
        return key

# --- Key Derivation on Application Startup ---
MASTER_KEY = get_anchor_key().encode()
print("Master ANCHOR_KEY loaded successfully.")

hkdf_auth = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'envoy-api-hmac-authentication-key')
AUTH_KEY = hkdf_auth.derive(MASTER_KEY)
print("HMAC authentication key derived.")

hkdf_encrypt = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'envoy-api-fernet-encryption-key')
ENCRYPTION_KEY = base64.urlsafe_b64encode(hkdf_encrypt.derive(MASTER_KEY))
FERNET_INSTANCE = Fernet(ENCRYPTION_KEY)
print("File encryption key derived and Fernet instance created.")


# --- HMAC Authentication Dependency ---
async def verify_hmac(request: Request, x_anchor_signature: str = Header(None)):
    if not x_anchor_signature:
        raise HTTPException(status_code=401, detail="X-Anchor-Signature header missing")
    body = await request.body()
    expected_signature = hmac.new(key=AUTH_KEY, msg=body, digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, x_anchor_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    return True

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "ok", "version": "1.2-local-ready"}

@app.post("/boot", dependencies=[Depends(verify_hmac)])
async def boot_endpoint(request: Request):
    boot_data = await request.json()
    if IS_PROD_ENVIRONMENT:
        doc_ref = firestore_client.collection("boots").document(boot_data.get("device_id", "unknown_device"))
        await doc_ref.set({"timestamp": datetime.utcnow(), "ip_address": request.client.host, "config_version": boot_data.get("config_version")})
    else:
        print("LOCAL MODE: Skipping Firestore write.")
    return {"status": "boot_ack", "flags": {"enable_telemetry": True, "log_level": "info"}}

@app.post("/directive", dependencies=[Depends(verify_hmac)])
async def directive_endpoint():
    return {"directive_id": f"cmd_{int(datetime.utcnow().timestamp())}", "action": "SYNC_FILES", "payload": {"target_path": "/data/sync"}}

@app.post("/ingest") # REMOVED: dependencies=[Depends(verify_hmac)]
async def ingest_file(
    request: Request,
    x_anchor_signature: str = Header(...),
    # Get filename from a query parameter instead
    filename: str = "uploaded.file"
):
    """
    Accepts an encrypted file as the raw request body.
    """
    # 1. Read the raw request body ONCE. This is the encrypted file content.
    encrypted_contents = await request.body()

    # 2. Manually verify the HMAC signature on the body we just read.
    expected_signature = hmac.new(key=AUTH_KEY, msg=encrypted_contents, digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, x_anchor_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 3. Decrypt the file (the rest of the logic is now valid)
    try:
        decrypted_contents = FERNET_INSTANCE.decrypt(encrypted_contents)
        print(f"Successfully decrypted file '{filename}' in memory.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted payload or key: {e}")

    gcs_path = None
    if IS_PROD_ENVIRONMENT:
        try:
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(f"uploads/{datetime.utcnow().isoformat()}_{filename}")
            # We need to find the content type, or just use a generic one
            content_type = request.headers.get('content-type', 'application/octet-stream')
            blob.upload_from_string(encrypted_contents, content_type=content_type)
            gcs_path = f"gs://{BUCKET_NAME}/{blob.name}"
            print(f"Successfully uploaded encrypted file to {gcs_path}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")
    else:
        gcs_path = f"gs://local-bucket/uploads/mock_{datetime.utcnow().isoformat()}_{filename}"
        print(f"LOCAL MODE: Skipping GCS upload. Mock path is {gcs_path}")

    return {
        "status": "ingest_ack",
        "filename": filename,
        "size": len(encrypted_contents),
        "gcs_path": gcs_path
    }
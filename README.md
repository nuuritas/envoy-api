# **Envoy API - Secure Serverless API on GCP**

This repository contains the FastAPI source code, deployment scripts, and documentation for the Envoy API, deployed on Google Cloud Run. The application is designed to be secure, cost-effective (scaling to zero), and stateless.

-   **Live API Endpoint:** `https://envoy-api-rp2d7vwyjq-uc.a.run.app`

## **Project Structure**

-   `main.py`: The core FastAPI application, including all endpoints and security logic.
-   `test_client.py`: A Python test client for verifying API functionality both locally and against the live deployment.
-   `ops_guide.md`: A one-page operations guide covering key rotation, log access, and scaling.
-   `Dockerfile`: Defines the container for deployment to Cloud Run.
-   `requirements.txt`: A pinned list of Python dependencies for reproducible builds.
-   `.env.example`: A template for the local environment file.
-   `.gitignore`: Ensures secrets and local artifacts are never committed to the repository.

## **Resources (Deployed on GCP)**

-   **Service Name:** `envoy-api`
-   **Region:** `us-central1`
-   **Service URL:** `https://envoy-api-rp2d7vwyjq-uc.a.run.app`
-   **Service Account:** `envoy-api-sa@envoy-api-project.iam.gserviceaccount.com`
-   **Secret Manager Secret:** `ANCHOR_KEY`
-   **Cloud Storage Bucket:** `envoy-api-storage-envoy-api-project`
-   **Firestore Database:** `(default)` in `nam5`

## **Local Development & Testing**

This setup allows you to run and test the API on your local machine before deploying.

1.  **Prerequisites:** Python 3.11+, `pip`, `venv`.

2.  **Setup Environment:**
    ```bash
    # Create and activate a Python virtual environment
    python3 -m venv venv
    source venv/bin/activate

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Configure Local Secrets:**
    *   Create a local environment file from the example template.
        ```bash
        cp .env.example .env
        ```
    *   Open the newly created `.env` file and set the `ANCHOR_KEY` to the shared secret value (e.g., `ENVOY_API_PASS1234`).

4.  **Run the Local Server:**
    ```bash
    uvicorn main:app --reload
    ```
    The API will now be running locally at `http://127.0.0.1:8000`. The `--reload` flag automatically restarts the server when you save code changes.

5.  **Run the Test Client Locally:**
    *   Open a **new terminal window**.
    *   Activate the virtual environment (`source venv/bin/activate`).
    *   Set the `API_BASE_URL` to your local server and run the tests:
        ```bash
        export API_BASE_URL="http://127.0.0.1:8000"
        python test_client.py
        ```
    You should see all tests pass successfully.

## **Full Deployment Runbook (GCP)**

This is a complete, repeatable script for deploying the entire application from scratch.

1.  **Prerequisites:**
    *   `gcloud` CLI installed and authenticated (`gcloud auth login`).
    *   A GCP Project with a linked Billing Account.

2.  **Configuration:**
    *   Set the following environment variables in your terminal, replacing `your-gcp-project-id` with your actual Project ID.
        ```bash
        export PROJECT_ID="your-gcp-project-id"
        export REGION="us-central1"
        export SERVICE_NAME="envoy-api"
        export BUCKET_NAME="envoy-api-storage-${PROJECT_ID}"
        export FIRESTORE_LOCATION="nam5"
        export SERVICE_ACCOUNT_NAME="envoy-api-sa"
        export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

        gcloud config set project ${PROJECT_ID}
        ```

3.  **Provision Infrastructure:**
    ```bash
    # Enable necessary APIs
    gcloud services enable run.googleapis.com secretmanager.googleapis.com storage.googleapis.com firestore.googleapis.com iam.googleapis.com cloudbuild.googleapis.com

    # Create the secret and add the key value (you will be prompted)
    gcloud secrets create ANCHOR_KEY --replication-policy="automatic"
    # IMPORTANT: Paste your secret key when prompted below.
    printf "your-super-secret-hmac-key-goes-here" | gcloud secrets versions add ANCHOR_KEY --data-file=-

    # Create resources
    gcloud storage buckets create gs://${BUCKET_NAME} --location=${REGION}
    gcloud firestore databases create --location=${FIRESTORE_LOCATION} --type=firestore-native
    gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} --display-name="Envoy API Service Account"

    # Pause for IAM propagation to prevent errors
    echo "Waiting 10 seconds for IAM propagation..."
    sleep 10

    # Grant permissions
    gcloud secrets add-iam-policy-binding ANCHOR_KEY --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/secretmanager.secretAccessor"
    gcloud storage buckets add-iam-policy-binding gs://${BUCKET_NAME} --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/storage.objectAdmin"
    gcloud projects add-iam-policy-binding ${PROJECT_ID} --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/datastore.user"
    ```

4.  **Build & Deploy:**
    ```bash
    # Build the container image using Cloud Build
    gcloud builds submit --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME}

    # Deploy the container to Cloud Run with the correct settings
    gcloud run deploy ${SERVICE_NAME} \
        --image gcr.io/${PROJECT_ID}/${SERVICE_NAME} \
        --platform managed \
        --region ${REGION} \
        --service-account ${SERVICE_ACCOUNT_EMAIL} \
        --allow-unauthenticated \
        --min-instances 0 \
        --max-instances 2 \
        --set-env-vars="BUCKET_NAME=${BUCKET_NAME},GCP_PROJECT_ID=${PROJECT_ID}" \
        --set-secrets="ANCHOR_KEY=ANCHOR_KEY:latest"
    ```

## **Testing the Deployed API**

### **Testing with the Python Client**

This is the most comprehensive way to test.

1.  Set the `API_BASE_URL` to your live service URL:
    ```bash
    export API_BASE_URL="https://envoy-api-rp2d7vwyjq-uc.a.run.app"
    ```
2.  Ensure the `ANCHOR_KEY_MASTER` variable in `test_client.py` matches your secret.
3.  Run the client:
    ```bash
    python test_client.py
    ```

### **Testing with cURL**

This method is useful for quick, dependency-free checks.

**Note:** The API uses HKDF to derive keys. Simple tools like `cURL` require a helper to generate the correct derived key first.

1.  **Get the Derived Key:**
    *   Create a helper script `get_derived_key.py`:
        ```python
        # get_derived_key.py
        import base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        MASTER_KEY_STR = "ENVOY_API_PASS1234" # Use your actual secret key
        INFO_STRING = b'envoy-api-hmac-authentication-key'
        master_key = MASTER_KEY_STR.encode()
        hkdf_auth = HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=INFO_STRING)
        derived_auth_key = hkdf_auth.derive(master_key)
        print(derived_auth_key.hex())
        ```
    *   Run it and store the key in a variable:
        ```bash
        DERIVED_KEY_HEX=$(python get_derived_key.py)
        ```

2.  **Test a Successful `/boot` Call:**
    ```bash
    JSON_BODY='{"device_id":"curl-test-001","firmware_version":"curl-v1"}'
    SIGNATURE=$(echo -n "$JSON_BODY" | openssl dgst -sha256 -mac hmac -macopt hexkey:$DERIVED_KEY_HEX | awk '{print $2}')
    curl -i -X POST \
      -H "Content-Type: application/json" -H "X-Anchor-Signature: $SIGNATURE" \
      -d "$JSON_BODY" "https://envoy-api-rp2d7vwyjq-uc.a.run.app/boot"
    ```

3.  **Test an Invalid Signature:**
    ```bash
    curl -i -X POST \
      -H "Content-Type: application/json" \
      -H "X-Anchor-Signature: invalid-signature" \
      -d '{}' "https://envoy-api-rp2d7vwyjq-uc.a.run.app/directive"
    ```
# Envoy API - Phase 4 Integration

This repository contains the FastAPI source code and deployment configuration for the Envoy API on Google Cloud Run.

## Resources

- **Service Name:** envoy-api
- **Region:** us-central1
- **Service URL:** https://envoy-api-xxxxxxxx-uc.a.run.app
- **Service Account:** envoy-api-sa@your-project-id.iam.gserviceaccount.com
- **Secret Manager Secret:** ANCHOR_KEY
- **Cloud Storage Bucket:** envoy-api-storage-your-project-id
- **Firestore Database:** (default) in nam5

## Deployment

1.  **Prerequisites:** `gcloud` CLI, Python 3.11+.
2.  **Set Environment Variables:**
    ```bash
    export PROJECT_ID="your-gcp-project-id"
    export REGION="us-central1"
    # ... (include all variables from Phase 1) ...
    ```
3.  **Build Container:**
    ```bash
    gcloud builds submit --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME}
    ```
4.  **Deploy to Cloud Run:**
    ```bash
    gcloud run deploy ${SERVICE_NAME} \
        --image gcr.io/${PROJECT_ID}/${SERVICE_NAME} \
        --platform managed \
        # ... (paste full deploy command here) ...
    ```

## Testing

Use the provided `test_client.py` to verify the endpoints.

1.  Set the API URL: `export API_BASE_URL="your-service-url"`
2.  Update the `ANCHOR_KEY` in the script to match the secret.
3.  Run: `python test_client.py`
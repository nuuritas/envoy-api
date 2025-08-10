# Envoy API - Operations Guide

A one-page guide for maintaining the Envoy API on GCP.

## How to Rotate the Anchor Key (HMAC Secret)

**What this is:** Key rotation is a security best practice where you periodically change your secret keys. If the old key was ever accidentally exposed, rotating it makes that old key useless.

**Procedure (Zero-Downtime):**

1.  **Add New Key Version in GCP:**
    *   Go to the GCP Console: **Secret Manager**.
    *   Click on the secret named **`ANCHOR_KEY`**.
    *   Click the **"ADD NEW VERSION"** button at the top.
    *   Paste your new secret value and click "ADD SECRET VERSION". The new version will become "latest".

2.  **Redeploy the Cloud Run Service:**
    *   The running service needs to be restarted to pick up the new secret. The easiest way is to redeploy it.
    *   Run the following command from your terminal (ensure your `PROJECT_ID`, `REGION`, etc., variables are set):
        ```bash
        gcloud run deploy envoy-api --region ${REGION}
        ```
    *   This command creates a new revision of the service, which will automatically fetch the `latest` version of the secret during startup. All new traffic will go to the new revision using the new key.

3.  **Update Clients:**
    *   All devices or clients that call this API must be updated to use the **new key** for signing their requests.

4.  **(Optional) Disable Old Key Version:**
    *   Once all clients are using the new key, go back to Secret Manager, find the old key version, click the three-dot menu, and select "Disable". This prevents the old key from ever being used again.

## How to Check Logs

**Method 1: Using the Web Console (Easy)**
1.  Go to the GCP Console: **Cloud Run**.
2.  Click on the `envoy-api` service.
3.  Click the **LOGS** tab.
4.  You can filter by severity (e.g., "Error") or search for specific text.

**Method 2: Using the Command Line (Fast)**
Run this command in your terminal:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}" --limit=50 --format="table(timestamp,logName,textPayload)"
# Renderly: Full GCP + Vertex AI Setup (Windows)

## Overview
- Goal: Configure Google Cloud (GCP) for Renderly to generate and store videos using Vertex AI (Veo) and Google Cloud Storage (GCS).
- Outcome: Valid project, enabled APIs, service account JSON key, GCS bucket with correct IAM, and environment variables set.

## Prerequisites
- A Google account (Gmail) to own the project and billing.
- Billing enabled on the GCP project.
- Windows PowerShell with Google Cloud SDK installed.
  - Install: `winget install GoogleCloudSDK` or download from Google Cloud.

## 1) Create/Select Project
- Console:
  - Open `https://console.cloud.google.com/`.
  - Top navbar → Project selector → Create project.
  - Name: Auralis (or Renderly), Project ID: `auralis-gcs`.
- CLI:
  - `gcloud auth login`
  - `gcloud projects create auralis-gcs`
  - `gcloud config set project auralis-gcs`
  - Verify: `gcloud projects describe auralis-gcs --format="value(projectId)"`

## 2) Enable Billing
- Console:
  - Billing → Link a billing account to `auralis-gcs`.
- CLI:
  - `gcloud beta billing accounts list`
  - `gcloud beta billing projects link auralis-gcs --billing-account=<ACCOUNT_ID>`

## 3) Enable Required APIs
- Console:
  - APIs & Services → Enable APIs:
    - Vertex AI API
    - IAM API
    - Cloud Storage API
- CLI:
`gcloud services enable aiplatform.googleapis.com iam.googleapis.com storage.googleapis.com storage-component.googleapis.com --project auralis-gcs`

## 4) Create Service Account and Key
- Create service account:
`gcloud iam service-accounts create renderly-sa --display-name="Renderly Service Account" --project auralis-gcs`
- Grant roles at the project:
`gcloud projects add-iam-policy-binding auralis-gcs --member=serviceAccount:renderly-sa@auralis-gcs.iam.gserviceaccount.com --role=roles/aiplatform.user`

`gcloud projects add-iam-policy-binding auralis-gcs --member=serviceAccount:renderly-sa@auralis-gcs.iam.gserviceaccount.com --role=roles/storage.objectAdmin`
- Create a JSON key (Windows path):
`gcloud iam service-accounts keys create "C:\Users\cirex\Downloads\auralis-gcs-sa.json" --iam-account=renderly-sa@auralis-gcs.iam.gserviceaccount.com --project auralis-gcs`
- Security:
  - Do not commit this JSON file to version control.
  - Restrict file permissions and rotate keys periodically.

## 5) Create the GCS Bucket
- Bucket name must be globally unique. Use `auralis-bucket`.
- Region must match Vertex location: `us-central1`.
- Create:
`gsutil mb -p auralis-gcs -l us-central1 -b on gs://auralis-bucket`

## 6) Grant Bucket IAM
- Grant your service account bucket read/write:
`gsutil iam ch serviceAccount:renderly-sa@auralis-gcs.iam.gserviceaccount.com:roles/storage.objectAdmin gs://auralis-bucket`
- Grant the Vertex AI service agent bucket write (Veo writes to `storageUri`):
  - Get project number (run and copy output):
`gcloud projects describe auralis-gcs --format="value(projectNumber)"`
  - Grant service agent (replace `<PROJECT_NUMBER>` with the value you copied):
`gsutil iam ch serviceAccount:service-829281304952@gcp-sa-aiplatform.iam.gserviceaccount.com:roles/storage.objectAdmin gs://auralis-veo-bucket`

## 7) Public vs Private Objects
- Simple approach (public read for objects):
`gsutil iam ch allUsers:roles/storage.objectViewer gs://auralis-bucket`
- Secure approach (recommended):
  - Keep bucket private; generate signed URLs for HeyGen uploads.
  - Requires small code addition to produce signed, time-limited URLs.

## 8) Environment Variables (.env)
- Open `c:\Users\cirex\Downloads\Renderly\.env` and set:
```
GCP_PROJECT_ID=auralis-gcs
GCP_SERVICE_ACCOUNT_FILE=C:\Users\cirex\Downloads\auralis-gcs-sa.json
GCS_BUCKET=auralis-bucket
HEYGEN_API_KEY=<your-heygen-api-key>
REDIS_URL=redis://localhost:6379/0
```
- Renderly loads `.env` automatically (`renderly/settings.py`).

## 9) Verify Setup
- Verify project and APIs:
```
gcloud config list
gcloud services list --enabled
```
- Verify service account key works (PowerShell):
`gcloud auth activate-service-account --key-file="C:\Users\cirex\Downloads\auralis-gcs-sa.json"`
`gsutil ls -Lb gs://auralis-bucket`
`echo test > test.txt`
`gsutil cp test.txt gs://auralis-bucket/diagnostics/test.txt`
- Verify token via Python (optional):
```
python - << 'PY'
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
creds = Credentials.from_service_account_file(
    r"C:\Users\cirex\Downloads\auralis-479010-b751a57c0b46.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
creds.refresh(Request())
print("Token OK:", bool(creds.token))
PY
```

## 10) Enable Vertex AI on Cloud Console (UI Path)
- Console → “Vertex AI” → If prompted, click “Enable Vertex AI API”.
- Confirm region `us-central1` (Renderly uses this).
- Ensure your bucket region is `us-central1`.
- CLI (project-level):
`gcloud services enable aiplatform.googleapis.com --project auralis-gcs`

## 11) Run Renderly Locally
- Server:
```
python manage.py runserver 8001
```
- Celery worker:
```
celery -A renderly worker -l info
```
- Test the API:
```
curl -X GET "http://127.0.0.1:8001/api/health/" -H "X-Api-Key: <YOUR_DRF_TOKEN>"
```

## 12) Troubleshooting
- Vertex write fails:
  - Ensure the Vertex AI service agent has `roles/storage.objectAdmin` on your bucket.
  - Confirm bucket region `us-central1`.
- 403 on public download:
  - Either enable object public read or switch to signed URLs.
- Authentication errors:
  - Check `GCP_SERVICE_ACCOUNT_FILE` path in `.env`.
  - Restart server after updating `.env`.

# DataSentinel — Autonomous DevOps SRE AI Agent 🚲💬☁️

DataSentinel is an autonomous DevOps / Site Reliability Engineering (SRE) agent built for the Findy DevOps × AI Agent Hackathon 2026. It monitors live systems (Tokyo central bike-share network via CityBikes API) and repository operations (GitHub Push/Tag events), identifies statistical anomalies using rolling Z-Score windows inside BigQuery (`asia-northeast1`), triggers a Gemini SRE agent to execute root-cause diagnostics with automated fix scripts, logs actions, and broadcasts structured colored embeds directly to Discord webhooks.

## Architecture & Features
- **Data Ingestion**: Multi-sourced fetchers for CityBikes API & GitHub Repository Events API with robust ETag cache validation and preserved null safety.
- **Observability Analytics**: Parametric windowed SQL query calculations in BigQuery matching Tokyo networks telemetry.
- **Statistical Detection**: Dynamic Z-Score anomalies detector flagging $|Z| > 3.0$ events.
- **Gemini SRE Analyst**: Large language model integration using Pydantic structured output mapping (`SreDiagnosticReport` schemas) for 100% predictable parsing.
- **Discord Integrations**: Automated color-coded embed templates (Info: Blue, Warning: Yellow, Critical: Red).
- **FastAPI Dashboard**: Glassmorphic HTML5 dashboard serving real-time logs, live Leaflet.js interactive maps centered on Tokyo, and diagnostic panels.

---

## Local Getting Started Guide

### 1. Requirements & Setup
Ensure you have `uv` installed (standard in your Cursor environment).
```powershell
# Create environment and install dependencies in 1-click
uv venv
uv pip install -r requirements.txt
```

### 2. Environment Variables (`.env`)
Fill out the keys in the `.env` file (pre-populated with your verified webhook, repository, and PAT tokens):
```ini
GCP_PROJECT_ID=datasentinel-hackathon
GOOGLE_APPLICATION_CREDENTIALS=datasentinel-gcp-key.json
GEMINI_API_KEY=your_gemini_api_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
GITHUB_REPO=ahnjh51/datasentinel
GITHUB_PAT=github_pat_...
```

### 3. Run Automated Tests
```powershell
.\.venv\Scripts\pytest tests/ -v
```

### 4. Running the Dashboard locally
```powershell
.\.venv\Scripts\python app\main.py
```
Open **`http://localhost:8000`** in your browser to interact with the spectacular glassmorphic monitor map dashboard.

---

## IMPORTANT: Google Cloud IAM Permissions Warning 🔒

Our database setup scripts reported that the service account JSON key provided (`ahnjh51@datasentinel-hackathon.iam.gserviceaccount.com`) lacks the necessary IAM permissions to create datasets and tables in the project `datasentinel-hackathon`.

To resolve this and activate direct BigQuery writes, you must grant the necessary roles to the service account.

### How to Fix (GCP Console)
1. Go to the **IAM & Admin** console in Google Cloud for your project `datasentinel-hackathon`.
2. Click **Grant Access** (or edit the member `ahnjh51@datasentinel-hackathon.iam.gserviceaccount.com`).
3. Add the following roles:
   - **BigQuery Admin** (`roles/bigquery.admin`) — *Critical for table & dataset setup*
   - **Cloud Run Developer** (`roles/run.admin`) — *For container deployments*
   - **Vertex AI User** (`roles/aiplatform.user`) — *For cloud LLM prompts*
   - **Storage Object Admin** (`roles/storage.objectAdmin`) — *For pushes to container registries*

### How to Fix (Google Cloud Shell / CLI)
Run this policy binding block in your Google Cloud Shell to grant the service account permissions in one click:
```bash
export PROJECT_ID=datasentinel-hackathon
export SA_EMAIL=ahnjh51@datasentinel-hackathon.iam.gserviceaccount.com

for ROLE in \
  roles/bigquery.admin \
  roles/run.admin \
  roles/aiplatform.user \
  roles/pubsub.editor \
  roles/secretmanager.secretAccessor \
  roles/storage.objectAdmin
do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE"
done
```

---

## CI/CD Deployment to Google Cloud Run
Pushing to your repository's `main` branch will trigger the GitHub Actions workflow in `.github/workflows/deploy.yml`:
1. Checkouts code, installs dependencies, and runs `pytest` checks.
2. Authenticates to GCP using secrets (`GCP_SA_KEY`).
3. Builds the Docker container via Cloud Build and pushes to Artifact Registry in Tokyo.
4. Deploys a revision to **Google Cloud Run** (`asia-northeast1`) with environment variables populated automatically.

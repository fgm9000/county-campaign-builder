# Deployment and Operations Runbook — county-campaign-builder

> 🇺🇸 EN | 🇧🇷 [PT-BR](deployment-runbook.pt-BR.md) · Based on [ADR 003](decisions/003-cloud-run-security.md) and [ADR 006](decisions/006-county-data-pipeline.md)

---

## 1. Overview and Security Architecture

`county-campaign-builder` is deployed as a **Google Cloud Run** service (`county-campaign-builder`, region `us-central1`) in the shared GCP project `fgm9000-portfolio`, built and deployed via GitHub Actions.

### Security and Isolation Design

- **Shared GCP project:** `fgm9000-portfolio` (region `us-central1`).
- **Keyless authentication (WIF):** GitHub Actions CI authenticates to GCP using the shared `github-pool` and a dedicated OIDC provider (`github-county-campaign-builder`), strictly scoped to the `fgm9000/county-campaign-builder` repository and the `refs/heads/main` branch (`assertion.repository == 'fgm9000/county-campaign-builder' && assertion.ref == 'refs/heads/main'`). No service account JSON keys are generated or stored in GitHub.
- **Strict identity separation (least privilege):**
  - **Runtime service account:** `county-campaign-runtime@fgm9000-portfolio.iam.gserviceaccount.com`
    - **Zero project-level roles.**
    - Granted only `roles/secretmanager.secretAccessor` on the **two production secrets** (`anthropic-api-key` and `county-campaign-live-access-code`).
  - **Deploy service account:** `county-campaign-deploy@fgm9000-portfolio.iam.gserviceaccount.com`
    - `roles/run.developer` at the project level (not `roles/run.admin`, avoiding granting `run.services.setIamPolicy`).
    - `roles/artifactregistry.writer` scoped only to the `county-campaign-builder` repository in Artifact Registry.
    - `roles/iam.serviceAccountUser` scoped only to the `county-campaign-runtime` account.
    - `roles/iam.workloadIdentityUser` bound to the federated identity of the `fgm9000/county-campaign-builder` repository.
    - **Has no access to secrets** in Secret Manager.
- **Secrets and data excluded from production:**
  - `anthropic-api-key` → injected as the `ANTHROPIC_API_KEY` environment variable.
  - `county-campaign-live-access-code` → injected as the `LIVE_ACCESS_CODE` environment variable.
  - **The U.S. Census API key (`CENSUS_API_KEY`) does NOT go to production:** per ADR 006, Census ACS and NOAA Storm Events data are precomputed in `data/counties.parquet` inside the Docker image (read-only). The runtime never queries the Census API or fetches arbitrary external URLs (it only calls the Anthropic API).
- **Cloud Run service configuration (`county-campaign-builder`):**
  - Resources: `--memory=512Mi`, `--cpu=1`, `--timeout=120` (required for SSE streaming on `/v1/campaigns/stream`), `--min-instances=0`, `--max-instances=1`, `--concurrency=10`.
  - Exposure and protection: `--no-invoker-iam-check` (public URL for the static playground on GitHub Pages), with `FAKE_MODEL=0`, access-code protection via the `X-Access-Code` header (constant-time comparison via `hmac.compare_digest` + lockout after 5 errors/min per IP), strict FIPS code validation against `data/counties.parquet`, per-IP rate limit (`5 req/min`), and global daily quota (`50 req/day`), plus `hide_input_in_errors=True` and PII-free JSON logs.

---

## 2. Prerequisites

### Required Tools and Permissions

1. **`gcloud` CLI** installed, up to date, and authenticated with an account that has permissions on the `fgm9000-portfolio` project to enable APIs, create service accounts, configure IAM bindings, manage Artifact Registry, create WIF providers, and manage secrets in Secret Manager (e.g., Project Owner or IAM/Security Admin):

```bash
gcloud auth list
gcloud config set project fgm9000-portfolio
```

2. **`gh` CLI** (GitHub CLI) installed and authenticated to the `fgm9000` account, with permissions to create/configure variables and secrets in the `fgm9000/county-campaign-builder` repository:

```bash
gh auth status
```

3. **Initial inspection of the project and the shared WIF pool (`github-pool`):**

```bash
# Confirm the project number (required in the principalSet and WIF provider strings)
gcloud projects describe fgm9000-portfolio --format='value(projectNumber)'

# Confirm that the shared github-pool exists
gcloud iam workload-identity-pools list \
  --project=fgm9000-portfolio --location=global

# List existing providers and optionally use an existing one as a mapping reference
gcloud iam workload-identity-pools providers list \
  --project=fgm9000-portfolio --location=global \
  --workload-identity-pool="github-pool"
```

Set the session variables below in your terminal (Bash / Git Bash) before running the blocks in Section 3:

```bash
PROJECT_ID="fgm9000-portfolio"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
REGION="us-central1"
WIF_POOL="github-pool"
WIF_PROVIDER="github-county-campaign-builder"
GITHUB_REPO="fgm9000/county-campaign-builder"
SERVICE_NAME="county-campaign-builder"
ARTIFACT_REPO="county-campaign-builder"
RUNTIME_SA_NAME="county-campaign-runtime"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA_NAME="county-campaign-deploy"
DEPLOY_SA="${DEPLOY_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

> **Tip:** If using PowerShell, adapt the variable syntax (`$PROJECT_ID = "fgm9000-portfolio"`, etc.) or run the commands in **Git Bash** / **WSL**, keeping masked input protection for secrets (Section 3.6).

---

## 3. Step-by-Step Resource Creation (`gcloud`)

All steps below are **idempotent**: if a resource already exists, the command simply confirms it or reapplies the IAM binding with no side effects.

### 3.1 Enable Required APIs

```bash
# Ensure Cloud Run, Artifact Registry, Secret Manager, IAM, and IAM Credentials are enabled
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
```

### 3.2 Create the Docker Repository in Artifact Registry

The `.github/workflows/deploy.yml` workflow pushes images to `us-central1-docker.pkg.dev/fgm9000-portfolio/county-campaign-builder/county-campaign-builder:<sha>`.

```bash
# Create the dedicated Docker repository for county-campaign-builder only if it does not yet exist
gcloud artifacts repositories describe "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1 \
|| gcloud artifacts repositories create "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" \
  --repository-format=docker \
  --description="Docker images for county-campaign-builder"
```

### 3.3 Create the Runtime Service Account (`county-campaign-runtime`)

This account is the identity of the running container. **Do not grant any project-level roles to it** — access to the two secrets will be granted directly on each secret in step 3.6.

```bash
# Create the runtime service account (with zero project-level roles)
gcloud iam service-accounts describe "$RUNTIME_SA" \
  --project="$PROJECT_ID" >/dev/null 2>&1 \
|| gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="county-campaign-builder runtime"
```

### 3.4 Create the Deploy Service Account (`county-campaign-deploy`) and Its Roles

This is the account assumed by GitHub Actions via WIF. Roles follow the principle of least privilege:

```bash
# Create the service account used by GitHub Actions during deployment
gcloud iam service-accounts describe "$DEPLOY_SA" \
  --project="$PROJECT_ID" >/dev/null 2>&1 \
|| gcloud iam service-accounts create "$DEPLOY_SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="county-campaign-builder deploy (GitHub Actions)"

# Allow creating/updating Cloud Run revisions (without run.admin, avoiding broad setIamPolicy)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/run.developer" \
  --condition=None

# Allow pushing Docker images only to the county-campaign-builder repository
gcloud artifacts repositories add-iam-policy-binding "$ARTIFACT_REPO" \
  --project="$PROJECT_ID" --location="$REGION" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/artifactregistry.writer"

# Allow acting only as the service's runtime account (and no other SA in the project)
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iam.serviceAccountUser"
```

> **Note on initial bootstrap with `--no-invoker-iam-check`:** Because `roles/run.developer` does not include `run.services.setIamPolicy`, the **initial creation** of the service by CI with `--no-invoker-iam-check` may fail due to IAM permissions. If that happens, the project owner creates the service once (see Section 5.1) using the `county-campaign-runtime` account and the same flags; subsequent CI deployments will update revisions normally without elevating the deploy account to `roles/run.admin`.

### 3.5 Create the WIF Provider and Bind to `fgm9000/county-campaign-builder`

The `github-pool` already exists in the project. Create a dedicated OIDC provider for this repository restricted to the `main` branch:

```bash
# Create the WIF provider restricted to the fgm9000/county-campaign-builder repository and main branch
gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool="$WIF_POOL" >/dev/null 2>&1 \
|| gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool="$WIF_POOL" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == 'fgm9000/county-campaign-builder' && assertion.ref == 'refs/heads/main'"

# Authorize federated tokens from this repository to impersonate county-campaign-deploy
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}"
```

> **Important:** Keep `assertion.ref == 'refs/heads/main'` in the condition (and **not** `assertion.sub`, which varies by event/workflow and can break deployments triggered by `workflow_run`).

### 3.6 Create/Reuse Secrets in Secret Manager and Grant Runtime Access

The two secrets mapped by `deploy.yml` are:
1. `anthropic-api-key` → `ANTHROPIC_API_KEY` variable (can be reused if it already exists in the `fgm9000-portfolio` project, or created now).
2. `county-campaign-live-access-code` → `LIVE_ACCESS_CODE` variable (a dedicated code for this service).

#### a) Generate a strong access code

Generate a random code (32 URL-safe characters) and store it in your password manager. **Never** save this code in the repository:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

#### b) Create or verify secrets without exposing values in shell history

Avoid passing values via `--data-file` with `echo` or a literal argument, so keys are not recorded in shell history (`~/.bash_history` or PSReadLine).

**Checking `anthropic-api-key` (reusing if it already exists):**

```bash
# Check if anthropic-api-key already exists in the project
if gcloud secrets describe anthropic-api-key --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Secret anthropic-api-key already exists in the project; it will be reused."
else
  read -rs -p "Value for anthropic-api-key: " VALUE; echo
  TMP_FILE=$(mktemp)
  printf '%s' "$VALUE" > "$TMP_FILE"
  gcloud secrets create anthropic-api-key \
    --project="$PROJECT_ID" \
    --replication-policy=automatic \
    --data-file="$TMP_FILE"
  rm -f "$TMP_FILE"; unset VALUE
fi
```

**Creating `county-campaign-live-access-code` (or adding a new version):**

In Git Bash / Linux / macOS:

```bash
read -rs -p "Value for county-campaign-live-access-code: " VALUE; echo
TMP_FILE=$(mktemp)
printf '%s' "$VALUE" > "$TMP_FILE"
if gcloud secrets describe county-campaign-live-access-code --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud secrets versions add county-campaign-live-access-code \
    --project="$PROJECT_ID" --data-file="$TMP_FILE"
else
  gcloud secrets create county-campaign-live-access-code \
    --project="$PROJECT_ID" \
    --replication-policy=automatic \
    --data-file="$TMP_FILE"
fi
rm -f "$TMP_FILE"; unset VALUE
```

Equivalent alternative in **PowerShell 7** (with masked input):

```powershell
$project = 'fgm9000-portfolio'
$name = 'county-campaign-live-access-code'
$value = Read-Host -MaskInput "Value for $name"
$tmpFile = Join-Path $env:TEMP "$name.tmp"
[System.IO.File]::WriteAllText($tmpFile, $value)   # writes without trailing newline

gcloud secrets describe $name --project=$project *> $null
if ($LASTEXITCODE -eq 0) {
  gcloud secrets versions add $name --project=$project --data-file=$tmpFile
} else {
  gcloud secrets create $name --project=$project --replication-policy=automatic --data-file=$tmpFile
}

Remove-Item $tmpFile -Force
Remove-Variable value
```

#### c) Grant `roles/secretmanager.secretAccessor` only to the runtime account

```bash
# Grant read access to both secrets only to county-campaign-runtime (never at project level)
for SECRET in anthropic-api-key county-campaign-live-access-code; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

> **Reminder:** There is no secret for `CENSUS_API_KEY`. Per ADR 006, the county table (`data/counties.parquet`) is generated offline via `scripts/build_county_table.py` and packaged as a static file in the Docker image.

---

## 4. Configuring GitHub Variables and Secrets

The `.github/workflows/deploy.yml` workflow reads three required variables (`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`), one optional CORS variable (`CORS_ORIGINS`), and the `LIVE_ACCESS_CODE` secret (used in the post-deploy smoke test). In addition, `.github/workflows/eval-live.yml` uses the `ANTHROPIC_API_KEY` secret.

### 4.1 Repository Variables (`gh variable set`)

```bash
# GCP project ID
gh variable set GCP_PROJECT_ID -R "$GITHUB_REPO" -b "$PROJECT_ID"

# Full path of the WIF provider created in step 3.5
gh variable set GCP_WIF_PROVIDER -R "$GITHUB_REPO" \
  -b "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

# Deploy service account assumed via WIF
gh variable set GCP_SERVICE_ACCOUNT -R "$GITHUB_REPO" -b "$DEPLOY_SA"

# Allowed CORS origin (scheme + host only, no path or trailing slash)
gh variable set CORS_ORIGINS -R "$GITHUB_REPO" -b "https://fgm9000.github.io"
```

Verify the saved variables:

```bash
gh variable list -R "$GITHUB_REPO"
```

### 4.2 Repository Secrets (`gh secret set`)

Run the command **without `-b`** so `gh` prompts for the value interactively without echoing or recording it in shell history:

```bash
# Used by the "Post-deploy smoke test" step in deploy.yml (must match county-campaign-live-access-code)
gh secret set LIVE_ACCESS_CODE -R "$GITHUB_REPO"

# Used by the manual eval-live.yml workflow (live evals)
gh secret set ANTHROPIC_API_KEY -R "$GITHUB_REPO"
```

Verify the registered secret names:

```bash
gh secret list -R "$GITHUB_REPO"
```

---

## 5. First Deployment and Smoke Test Verification (`scripts/smoke_test.py`)

### 5.1 Triggering Deployment via GitHub Actions

The `deploy.yml` workflow triggers automatically after the `CI` workflow succeeds on the `main` branch, or manually via `workflow_dispatch` (`.github/workflows/deploy.yml` must already exist on `main`):

```bash
# Trigger the deploy workflow manually
gh workflow run deploy.yml -R "$GITHUB_REPO"

# Watch the most recent run until completion
RUN_ID=$(gh run list -R "$GITHUB_REPO" --workflow=deploy.yml \
  --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" -R "$GITHUB_REPO" --exit-status
```

#### Bootstrap by the project owner (if the first deployment fails on `--no-invoker-iam-check`)

If the `Deploy to Google Cloud Run` step fails during initial service creation due to missing `run.services.setIamPolicy` permission on `county-campaign-deploy`, the project owner must run the initial bootstrap once using the image already pushed to Artifact Registry:

```bash
# Replace <IMAGE_TAG> with the commit SHA pushed in the "Build and push container image" step
IMAGE_TAG="<COMMIT_SHA>"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"

gcloud run deploy "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE_URI" \
  --platform=managed \
  --service-account="$RUNTIME_SA" \
  --min-instances=0 \
  --max-instances=1 \
  --concurrency=10 \
  --memory=512Mi \
  --cpu=1 \
  --timeout=120 \
  --no-invoker-iam-check \
  --labels=app=county-campaign-builder \
  --set-env-vars="FAKE_MODEL=0,CORS_ORIGINS=https://fgm9000.github.io" \
  --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,LIVE_ACCESS_CODE=county-campaign-live-access-code:latest"
```

After this one-time bootstrap, re-run `gh workflow run deploy.yml -R "$GITHUB_REPO"` to validate the full cycle (build + deploy + automated smoke test).

### 5.2 Manual Verification with `scripts/smoke_test.py`

`deploy.yml` already runs `scripts/smoke_test.py` automatically at the end of every deployment. To run the check manually from your machine:

1. Retrieve the service URL:

```bash
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')
echo "$SERVICE_URL"
```

2. Run the official smoke test with masked access code input:

```bash
read -rs -p "Access code (LIVE_ACCESS_CODE): " LIVE_CODE; echo
uv run python scripts/smoke_test.py --url "$SERVICE_URL" --code "$LIVE_CODE"
unset LIVE_CODE
```

The script validates, in order:
- `GET /health` → HTTP `200` with `{"status": "ok"}`.
- `POST /v1/campaigns` **without** `X-Access-Code` header → HTTP `401` (confirms live-mode protection is active).
- `POST /v1/campaigns` **with** `X-Access-Code` (default county `48113` — Dallas County, TX) → HTTP `200` and valid `CountyCampaign` payload (`status="success"`, valid `unit_economics.verdict`, and `assets`).
- `POST /v1/campaigns/stream` **with** `X-Access-Code` → HTTP `200`, `Content-Type: text/event-stream`, starting with a `progress` event and ending with a `done` event containing a valid `CountyCampaign`.

*(To test a local instance running with `FAKE_MODEL=1`, pass `--fake-mode` to skip the `401` check.)*

### 5.3 Connecting the Static Frontend (`web/config.json`) and Publishing GitHub Pages

1. Edit `web/config.json` with the Cloud Run URL **without a trailing slash** (the field read by `web/app.js` is `apiUrl`):

```json
{
  "apiUrl": "https://<SERVICE_URL>"
}
```

2. Commit and push to `main` (the `.github/workflows/pages.yml` workflow triggers automatically on changes under `web/**`, provided the repository is **public**):

```bash
git add web/config.json
git commit -m "chore: configure live API URL for GitHub Pages"
git push origin main
```

3. Confirm that GitHub Pages is configured to build from GitHub Actions:

```bash
gh api -X POST "repos/${GITHUB_REPO}/pages" -f build_type=workflow \
|| gh api "repos/${GITHUB_REPO}/pages"
```

---

## 6. Operations, Cost Monitoring, and Shutting Down Live Mode

### 6.1 Logs and Observability

Application logs are emitted as single-line structured JSON (with no PII and no secret values):

```bash
# Last 50 log lines for the service
gcloud run services logs read "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --limit=50

# Errors only (severity >= ERROR)
gcloud run services logs read "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" --limit=50 \
  --log-filter='severity>=ERROR'
```

### 6.2 Cost Monitoring and $30/Month Anthropic Cap

1. **Monthly cap on Anthropic (mandatory before sharing the access code):**
   - Configure a **$30/month** monthly **spend limit** directly in the Anthropic Console (`console.anthropic.com`, under *Billing / Spend Limits*).
   - GCP does **not** control or track Anthropic API usage. Configure and confirm the saved $30 limit before distributing any access code.
2. **Abuse-protection layers in the API itself:**
   - Required access code on `/v1/campaigns` and `/v1/campaigns/stream` (`X-Access-Code`).
   - Brute-force lockout: maximum of `5` invalid code attempts per minute per IP (`MAX_FAILED_CODES_PER_MINUTE=5`).
   - Per-IP rate limit (`RATE_LIMIT_PER_MINUTE=5`) and global daily quota in UTC (`DAILY_QUOTA=50` requests/day per instance; since `--max-instances=1`, there is at most one active instance).
3. **GCP infrastructure cost:**
   - **Cloud Run:** `--min-instances=0` ensures zero cost when idle; billed only during active requests (`512Mi`, `1` vCPU).
   - **Artifact Registry:** each deployment pushes a new image tagged `<sha>`. Configure a cleanup policy to retain only recent versions and avoid storage accumulation. Create a `cleanup-policy.json` file **outside the repository**:

   ```json
   [
     {"name": "keep-latest", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}},
     {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "604800s"}}
   ]
   ```

   Apply it (use `--dry-run` first if you want to simulate):

   ```bash
   gcloud artifacts repositories set-cleanup-policies "$ARTIFACT_REPO" \
     --project="$PROJECT_ID" --location="$REGION" \
     --policy=cleanup-policy.json
   ```

### 6.3 Rotating the Access Code or Anthropic Key

Cloud Run resolves the `:latest` secret reference **when a new revision is created**, not on every request. Therefore, every rotation requires: (1) adding a new version in Secret Manager and (2) publishing a new service revision.

```bash
# 1. Write a new version of the access code without exposing it in shell history
read -rs -p "New access code: " NEW_CODE; echo
TMP_FILE=$(mktemp)
printf '%s' "$NEW_CODE" > "$TMP_FILE"
unset NEW_CODE

gcloud secrets versions add county-campaign-live-access-code \
  --project="$PROJECT_ID" --data-file="$TMP_FILE"
rm -f "$TMP_FILE"

# 2. Create a new revision to resolve :latest
gcloud run services update "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --update-env-vars="ACCESS_CODE_ROTATED_AT=$(date +%Y%m%d%H%M)"
```

Next:
- Update the `LIVE_ACCESS_CODE` secret in GitHub (`gh secret set LIVE_ACCESS_CODE -R "$GITHUB_REPO"`) so future deployments do not fail the smoke test.
- Disable the previous secret version in GCP (`gcloud secrets versions list county-campaign-live-access-code --project="$PROJECT_ID"` lists version numbers; run `gcloud secrets versions disable <VERSION> --secret=county-campaign-live-access-code --project="$PROJECT_ID"`).
- If rotating `anthropic-api-key`, also update `ANTHROPIC_API_KEY` in GitHub (`gh secret set ANTHROPIC_API_KEY -R "$GITHUB_REPO"`).

### 6.4 How to Turn Off Live Mode If Needed

The precomputed scenarios on GitHub Pages (`web/examples.json`) are 100% static and do not depend on Cloud Run. If you need to disable live mode for security or cost control, choose one of the options below (from least to most drastic):

1. **Rotate `county-campaign-live-access-code` to an unshared secret value (recommended):**
   - Follow the procedure in Section 6.3 with a new random value and do not distribute it.
   - All calls to `/v1/campaigns` and `/v1/campaigns/stream` immediately receive HTTP `401` (without spending Anthropic tokens), while `/health` continues returning `200`.
   - > **Do not remove `ANTHROPIC_API_KEY` or `LIVE_ACCESS_CODE` while `FAKE_MODEL=0`:** `Settings` validates both on startup; without either one, the container fails to start and `/health` stops responding.

2. **Re-enable IAM enforcement on Cloud Run (block at Google's edge):**
   - Since the service uses `--no-invoker-iam-check`, removing `allUsers` has no effect; you must re-enable `--invoker-iam-check`:

   ```bash
   gcloud run services update "$SERVICE_NAME" \
     --project="$PROJECT_ID" --region="$REGION" \
     --invoker-iam-check
   ```

   - Any request without a Google IAM token (including `/health`) now receives HTTP `403`.
   - To prevent the next CI deployment from reopening the endpoint, temporarily disable the deploy workflow:

   ```bash
   gh workflow disable deploy.yml -R "$GITHUB_REPO"
   ```

3. **Delete the Cloud Run service:**
   - Completely removes the exposed surface (historical logs remain available in Cloud Logging). Recreating the service later will require the initial bootstrap (Section 5.1) if the deploy uses `--no-invoker-iam-check`.

   ```bash
   gcloud run services delete "$SERVICE_NAME" \
     --project="$PROJECT_ID" --region="$REGION"
   ```

### 6.5 Quick Troubleshooting

| Symptom | Likely Cause | How to Verify and Fix |
|---|---|---|
| `google-github-actions/auth` fails with `403` or `unauthorized_client` | Mismatch in WIF provider repository/branch or `principalSet` | Check `gh variable list -R fgm9000/county-campaign-builder`, inspect the `github-county-campaign-builder` provider (`gcloud iam workload-identity-pools providers describe ...`), and validate `attribute.repository/fgm9000/county-campaign-builder`. |
| Permission error reading secret on startup | `county-campaign-runtime` missing `roles/secretmanager.secretAccessor` on one of the 2 secrets | Run `gcloud secrets get-iam-policy anthropic-api-key --project=fgm9000-portfolio` and the same for `county-campaign-live-access-code`, reapplying the binding from step 3.6c if missing. |
| First deploy fails on `--no-invoker-iam-check` | `roles/run.developer` does not include `run.services.setIamPolicy` on initial creation | Run the one-time bootstrap as the project owner (Section 5.1) without elevating the deploy account to `roles/run.admin`. |
| Browser blocks requests due to CORS | Origin missing from `CORS_ORIGINS` or configured with path/trailing slash | Ensure `CORS_ORIGINS=https://fgm9000.github.io` (without `/county-campaign-builder` and without a trailing `/`) and update the revision. |
| Smoke test fails on `401` or returns `401` with a valid code | `secrets.LIVE_ACCESS_CODE` in GitHub differs from `county-campaign-live-access-code:latest` in GCP, or old revision | Update the GitHub secret or create a new Cloud Run revision to resolve `:latest` (Section 6.3). |
| Cold start over 15 s or RAM usage over 400 MB | Violation of ADR 003 review criterion | Check Cloud Run metrics and logs (`county-campaign-builder`) and reopen ADR 003 if the behavior persists. |

#!/usr/bin/env bash
# Deploy the Places profiling job: Cloud Run job + weekly Cloud Scheduler trigger + failure alert.
# Spec: docs/plans/dashboard.md (Phase 2, bead .4.6). Mirrors scripts/deploy_collector.sh.
#
# Re-runnable. Every step describes first and only creates or updates what is missing or changed.
# Read-only checks (describe/list) always run; every mutating command goes through run().
#
#   scripts/deploy_places_job.sh               deploy everything
#   scripts/deploy_places_job.sh --dry-run     print every mutating command, change nothing
#   scripts/deploy_places_job.sh --no-schedule deploy the job but leave the Scheduler job paused (or absent)
#   scripts/deploy_places_job.sh --default-sa  run the job and Scheduler as the Compute Engine default service
#                                              account (has Editor), like deploy_collector.sh --default-sa.
#                                              Only grant added: secretAccessor on MAPS_API_KEY (idempotent; a
#                                              no-op when the collector deploy already granted it).
#                                              Without it the job reuses the collector's dedicated accounts
#                                              (traffic-collector / traffic-scheduler), which must already exist.
#
# The job runs weekly (Mon 02:00 Asia/Jakarta). This script never runs it: the first run is the manual
# command printed at the end. Calls the Places APIs (about 10 Details + 20 Nearby + 450 Aggregate per run).
set -euo pipefail

PROJECT=gcp-coe-sandbox
REGION=asia-southeast2          # Cloud Scheduler supports asia-southeast2 (Jakarta) per its locations doc
DATASET=traffic
JOB=places-profiler
SCHED=places-profiler-weekly
SCHEDULE="0 2 * * 1"
SA_RUN=traffic-collector        # the collector's dedicated accounts, reused when --default-sa is not given
SA_SCHED=traffic-scheduler
SECRET=MAPS_API_KEY
ALERT_EMAIL=farry@terralogiq.com
POLICY_NAME="places-profiler job failed"
CHANNEL_NAME="traffic-collector alerts ($ALERT_EMAIL)"   # the collector's email channel, reused when it exists

# Read-only describe/list calls must never block on or auto-answer a prompt (e.g. "enable API? y/N").
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

POLICY_FILE=""
DRY_RUN=0
NO_SCHEDULE=0
DEFAULT_SA=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-schedule) NO_SCHEDULE=1 ;;
    --default-sa) DEFAULT_SA=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# The default quota project of gcloud is a different project, so name the project and the billing project everywhere.
GC_PROJ=(--project "$PROJECT" --billing-project "$PROJECT")
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
DEFAULT_SA_EMAIL="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
if [ "$DEFAULT_SA" = 1 ]; then
  # Editor covers BigQuery jobs (bigquery.jobs.create), table writes (dataset ACL grants projectWriters WRITER)
  # and starting the job (run.jobs.run). It does not include reading secret payloads, granted in step 2a.
  SA_RUN_EMAIL="$DEFAULT_SA_EMAIL"
  SA_SCHED_EMAIL="$DEFAULT_SA_EMAIL"
else
  SA_RUN_EMAIL="$SA_RUN@$PROJECT.iam.gserviceaccount.com"
  SA_SCHED_EMAIL="$SA_SCHED@$PROJECT.iam.gserviceaccount.com"
fi

run() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

step() { printf '\n== %s\n' "$*"; }

# --- 1. APIs ---------------------------------------------------------------------------------
# Places API (New) and Places Aggregate are called with MAPS_API_KEY, whose API restrictions the user manages:
# nothing to enable here beyond what the collector already needs.
step "1. Enable APIs"
WANTED_APIS="run cloudscheduler cloudbuild artifactregistry bigquery secretmanager monitoring iam"
ENABLED=$(gcloud services list --enabled "${GC_PROJ[@]}" --format='value(config.name)')
MISSING=""
for api in $WANTED_APIS; do
  if printf '%s\n' "$ENABLED" | grep -qx "$api.googleapis.com"; then
    echo "  $api: enabled"
  else
    MISSING="$MISSING $api.googleapis.com"
  fi
done
if [ -n "$MISSING" ]; then
  # shellcheck disable=SC2086  # intentional word splitting of the API list
  run gcloud services enable $MISSING "${GC_PROJ[@]}"
fi

# --- 2a. Job identity ------------------------------------------------------------------------
step "2a. Job identity ($SA_RUN_EMAIL)"
if [ "$DEFAULT_SA" = 1 ]; then
  echo "  --default-sa: using the Compute Engine default service account (Editor); only the secret grant below"
else
  # The collector deploy creates this account and gives it the traffic dataset ACL and bigquery.jobUser.
  if gcloud iam service-accounts describe "$SA_RUN_EMAIL" "${GC_PROJ[@]}" >/dev/null 2>&1; then
    echo "  exists (created by deploy_collector.sh)"
  elif [ "$DRY_RUN" = 1 ]; then
    echo "  MISSING: $SA_RUN_EMAIL; a real run stops here. Run scripts/deploy_collector.sh first, or use --default-sa"
  else
    echo "$SA_RUN_EMAIL does not exist: run scripts/deploy_collector.sh first, or use --default-sa" >&2
    exit 1
  fi
fi
# Idempotent: the same grant the collector deploy makes. The only secret this job can read.
run gcloud secrets add-iam-policy-binding "$SECRET" \
  --member="serviceAccount:$SA_RUN_EMAIL" --role=roles/secretmanager.secretAccessor \
  --format=none "${GC_PROJ[@]}"

# --- 2b. Cloud Build permissions for --source deploys ----------------------------------------
# Cloud Build builds as the Compute Engine default service account, which needs roles/run.builder. In this
# project that account has roles/editor, which already covers it; grant run.builder only when neither is present.
step "2b. Cloud Build service account (Compute Engine default) can build"
BUILD_SA="$DEFAULT_SA_EMAIL"
BUILD_ROLES=$(gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:$BUILD_SA" --format='value(bindings.role)')
if printf '%s\n' "$BUILD_ROLES" | grep -qE '^roles/(editor|run\.builder)$'; then
  echo "  $BUILD_SA already has editor or run.builder"
else
  run gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$BUILD_SA" --role=roles/run.builder \
    --condition=None --format=none "${GC_PROJ[@]}"
fi

# --- 3. Cloud Run job ------------------------------------------------------------------------
# `jobs deploy` creates or updates, so it is idempotent. --set-* replace the whole env/secret set, so drift is
# reset on every run. --quiet accepts the prompt to create the Artifact Registry repo cloud-run-source-deploy.
# --max-retries 1: a retry is the same execution, so it re-uses the run_id and MERGEs over its own rows
# (it re-fetches everything: about one more run of Places calls). The job exits 1 when a site got no Details row.
step "3. Cloud Run job $JOB (build from places_job/)"
run gcloud run jobs deploy "$JOB" \
  --source places_job \
  --region "$REGION" \
  --service-account "$SA_RUN_EMAIL" \
  --set-env-vars "GCP_PROJECT=$PROJECT,BQ_DATASET=$DATASET" \
  --set-secrets "$SECRET=$SECRET:latest" \
  --task-timeout 15m \
  --max-retries 1 \
  --tasks 1 \
  --quiet "${GC_PROJ[@]}"

# --- 2c. Scheduler identity (needs the job to exist) -----------------------------------------
step "2c. Scheduler identity ($SA_SCHED_EMAIL)"
if [ "$DEFAULT_SA" = 1 ]; then
  echo "  --default-sa: Editor already includes run.jobs.run; no grant needed"
else
  # Created by deploy_collector.sh, like the job identity in step 2a.
  if gcloud iam service-accounts describe "$SA_SCHED_EMAIL" "${GC_PROJ[@]}" >/dev/null 2>&1; then
    echo "  exists (created by deploy_collector.sh)"
  elif [ "$DRY_RUN" = 1 ]; then
    echo "  MISSING: $SA_SCHED_EMAIL; a real run stops here. Run scripts/deploy_collector.sh first, or use --default-sa"
  else
    echo "$SA_SCHED_EMAIL does not exist: run scripts/deploy_collector.sh first, or use --default-sa" >&2
    exit 1
  fi
  run gcloud run jobs add-iam-policy-binding "$JOB" \
    --member="serviceAccount:$SA_SCHED_EMAIL" --role=roles/run.invoker \
    --region "$REGION" --format=none "${GC_PROJ[@]}"
fi

# --- 4. Cloud Scheduler ----------------------------------------------------------------------
# POST to the Cloud Run Admin API jobs:run with an OAuth token (not OIDC: this is a Google API, not a Run service).
step "4. Cloud Scheduler job $SCHED"
RUN_URI="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$JOB:run"
SCHED_ARGS=(
  --location "$REGION"
  --schedule "$SCHEDULE"
  --time-zone Asia/Jakarta
  --uri "$RUN_URI"
  --http-method POST
  --oauth-service-account-email "$SA_SCHED_EMAIL"
  --oauth-token-scope https://www.googleapis.com/auth/cloud-platform
)
SCHED_STATE=$(gcloud scheduler jobs describe "$SCHED" --location "$REGION" "${GC_PROJ[@]}" \
  --format='value(state)' 2>/dev/null || true)
if [ -z "$SCHED_STATE" ]; then
  if [ "$NO_SCHEDULE" = 1 ]; then
    echo "  --no-schedule: not creating the Scheduler job"
  else
    run gcloud scheduler jobs create http "$SCHED" "${SCHED_ARGS[@]}" "${GC_PROJ[@]}"
  fi
else
  run gcloud scheduler jobs update http "$SCHED" "${SCHED_ARGS[@]}" "${GC_PROJ[@]}"
  if [ "$NO_SCHEDULE" = 1 ]; then
    [ "$SCHED_STATE" = PAUSED ] || run gcloud scheduler jobs pause "$SCHED" --location "$REGION" "${GC_PROJ[@]}"
  else
    [ "$SCHED_STATE" != PAUSED ] || run gcloud scheduler jobs resume "$SCHED" --location "$REGION" "${GC_PROJ[@]}"
  fi
fi

# --- 5. Alert on failed executions -----------------------------------------------------------
# Same metric and condition as the collector's policy (scripts/collector_alert_policy.json), for this job.
step "5. Email channel and alert policy"
CHANNEL=$(gcloud beta monitoring channels list "${GC_PROJ[@]}" \
  --filter="type=\"email\" AND labels.email_address=\"$ALERT_EMAIL\"" \
  --format='value(name)' | head -n 1)
if [ -n "$CHANNEL" ]; then
  echo "  channel exists: $CHANNEL"
elif [ "$DRY_RUN" = 1 ]; then
  run gcloud beta monitoring channels create --type email --display-name "$CHANNEL_NAME" \
    --channel-labels "email_address=$ALERT_EMAIL" --format 'value(name)' "${GC_PROJ[@]}"
  CHANNEL="projects/$PROJECT/notificationChannels/<NEW_CHANNEL_ID>"
else
  CHANNEL=$(gcloud beta monitoring channels create --type email --display-name "$CHANNEL_NAME" \
    --channel-labels "email_address=$ALERT_EMAIL" --format 'value(name)' "${GC_PROJ[@]}")
  echo "  channel created: $CHANNEL"
fi

POLICY_FILE=$(mktemp "${TMPDIR:-/tmp}/places_alert_policy.XXXXXX")
trap 'rm -f "$POLICY_FILE"' EXIT
cat > "$POLICY_FILE" <<'EOF'
{
  "displayName": "__POLICY_NAME__",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Failed executions of Cloud Run job __JOB__",
      "conditionThreshold": {
        "filter": "resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"__JOB__\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = monitoring.regex.full_match(\"fail.*\")",
        "aggregations": [
          {
            "alignmentPeriod": "300s",
            "perSeriesAligner": "ALIGN_SUM"
          }
        ],
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0,
        "duration": "0s",
        "trigger": {
          "count": 1
        }
      }
    }
  ],
  "alertStrategy": {
    "autoClose": "1800s"
  },
  "notificationChannels": [
    "__CHANNEL__"
  ],
  "documentation": {
    "mimeType": "text/markdown",
    "content": "The Cloud Run job `__JOB__` (weekly Places profiling) had a failed execution. The job fails when every Places call fails, when a site got no Place Details row, or on a BigQuery or startup error. A failed execution is retried once with the same run_id (no duplicate rows). Check the logs: `gcloud run jobs executions list --job __JOB__ --region __REGION__` and Cloud Logging for resource `cloud_run_job`."
  }
}
EOF
sed -i.bak -e "s|__POLICY_NAME__|$POLICY_NAME|g" -e "s|__JOB__|$JOB|g" \
    -e "s|__REGION__|$REGION|g" -e "s|__CHANNEL__|$CHANNEL|g" "$POLICY_FILE"
rm -f "$POLICY_FILE.bak"

POLICY=$(gcloud monitoring policies list "${GC_PROJ[@]}" \
  --filter="display_name=\"$POLICY_NAME\"" --format='value(name)' | head -n 1)
if [ -n "$POLICY" ]; then
  run gcloud monitoring policies update "$POLICY" --policy-from-file "$POLICY_FILE" "${GC_PROJ[@]}"
else
  run gcloud monitoring policies create --policy-from-file "$POLICY_FILE" "${GC_PROJ[@]}"
fi

# --- 6. Summary ------------------------------------------------------------------------------
step "6. Summary"
cat <<EOF
  project / region : $PROJECT / $REGION
  job              : $JOB (runs as $SA_RUN_EMAIL)
  scheduler        : $SCHED, $SCHEDULE Asia/Jakarta$([ "$NO_SCHEDULE" = 1 ] && echo " (skipped or paused: --no-schedule)")
  alert            : "$POLICY_NAME" -> $ALERT_EMAIL
$([ "$DRY_RUN" = 1 ] && echo "  DRY RUN          : nothing was changed")

Trigger one manual run (calls the Places APIs; each run adds rows with a new run_id):
  gcloud run jobs execute $JOB --region $REGION --project $PROJECT --wait --billing-project $PROJECT
EOF

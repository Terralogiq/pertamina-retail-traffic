#!/usr/bin/env bash
# Deploy the traffic collector: Cloud Run job + Cloud Scheduler trigger + failure alert.
# Spec: docs/plans/collector.md (Phase 1d).
#
# Re-runnable. Every step describes first and only creates or updates what is missing or changed.
# Read-only checks (describe/list) always run; every mutating command goes through run().
#
#   scripts/deploy_collector.sh               deploy everything
#   scripts/deploy_collector.sh --dry-run     print every mutating command, change nothing
#   scripts/deploy_collector.sh --no-schedule deploy the job but leave the Scheduler job paused (or absent)
#   scripts/deploy_collector.sh --default-sa  run the job and Scheduler as the Compute Engine default service
#                                             account (has Editor) instead of creating traffic-collector /
#                                             traffic-scheduler. Only grant added: secretAccessor on MAPS_API_KEY.
#                                             Re-running without it moves to the dedicated accounts (bead pertamina-retail-traffic-907.7.12).
#
# No budget alert here: it needs billing-account access, so the user decides (see collector.md 1d).
set -euo pipefail

PROJECT=gcp-coe-sandbox
REGION=asia-southeast2          # Cloud Scheduler supports asia-southeast2 (Jakarta) per its locations doc
DATASET=traffic
JOB=traffic-collector
SCHED=traffic-collector-every-30min
SA_RUN=traffic-collector
SA_SCHED=traffic-scheduler
SECRET=MAPS_API_KEY
ALERT_EMAIL=farry@terralogiq.com
POLICY_NAME="traffic-collector job failed"
CHANNEL_NAME="traffic-collector alerts ($ALERT_EMAIL)"

# Read-only describe/list calls must never block on or auto-answer a prompt (e.g. "enable API? y/N").
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

DS_FILE=""
POLICY_FILE=""
DRY_RUN=0
NO_SCHEDULE=0
DEFAULT_SA=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-schedule) NO_SCHEDULE=1 ;;
    --default-sa) DEFAULT_SA=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
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

# --- 2a. Collector service account -----------------------------------------------------------
step "2a. Collector identity ($SA_RUN_EMAIL)"
if [ "$DEFAULT_SA" = 1 ]; then
  echo "  --default-sa: using the Compute Engine default service account (Editor); only the secret grant below"
else
if gcloud iam service-accounts describe "$SA_RUN_EMAIL" "${GC_PROJ[@]}" >/dev/null 2>&1; then
  echo "  exists"
else
  run gcloud iam service-accounts create "$SA_RUN" \
    --display-name "Traffic collector (Cloud Run job)" "${GC_PROJ[@]}"
  # A new service account can take a few seconds to be visible to IAM bindings.
  [ "$DRY_RUN" = 1 ] || sleep 15
fi

# Dataset-level on purpose: the collector must not edit other datasets in the project.
# `bq add-iam-policy-binding -d` is not usable (BigQuery: "This feature requires allowlisting"), so edit the
# dataset ACL instead: add a WRITER (= bigquery.dataEditor) entry unless the service account already has one.
DS_FILE=$(mktemp "${TMPDIR:-/tmp}/collector_dataset.XXXXXX")
trap 'rm -f "$DS_FILE"' EXIT
bq --project_id="$PROJECT" show --format=prettyjson "$PROJECT:$DATASET" > "$DS_FILE"
if grep -q "\"$SA_RUN_EMAIL\"" "$DS_FILE"; then
  echo "  $DATASET dataset already lists $SA_RUN_EMAIL"
else
  python3 -I -c '
import json, sys
path, email = sys.argv[1:]
ds = json.load(open(path))
ds.setdefault("access", []).append({"role": "WRITER", "userByEmail": email})
json.dump(ds, open(path, "w"), indent=2)
' "$DS_FILE" "$SA_RUN_EMAIL"
  run bq --project_id="$PROJECT" update --source "$DS_FILE" "$PROJECT:$DATASET"
fi
# jobUser has to be project-level: it is what allows running query jobs (the MERGEs).
run gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$SA_RUN_EMAIL" --role=roles/bigquery.jobUser \
  --condition=None --format=none "${GC_PROJ[@]}"
fi
run gcloud secrets add-iam-policy-binding "$SECRET" \
  --member="serviceAccount:$SA_RUN_EMAIL" --role=roles/secretmanager.secretAccessor \
  --format=none "${GC_PROJ[@]}"

# --- 2b. Cloud Build permissions for --source deploys ----------------------------------------
# Docs (Cloud Run "Deploy from source"): Cloud Build builds as the Compute Engine default service account,
# which needs roles/run.builder. In this project that account has roles/editor, which already covers it, so
# only grant run.builder when neither role is present (e.g. a project where Editor was not auto-granted).
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
step "3. Cloud Run job $JOB (build from collector/)"
run gcloud run jobs deploy "$JOB" \
  --source collector \
  --region "$REGION" \
  --service-account "$SA_RUN_EMAIL" \
  --set-env-vars "GCP_PROJECT=$PROJECT,BQ_DATASET=$DATASET" \
  --set-secrets "$SECRET=$SECRET:latest" \
  --task-timeout 10m \
  --max-retries 1 \
  --tasks 1 \
  --quiet "${GC_PROJ[@]}"

# --- 2c. Scheduler service account (needs the job to exist) ----------------------------------
step "2c. Scheduler identity ($SA_SCHED_EMAIL)"
if [ "$DEFAULT_SA" = 1 ]; then
  echo "  --default-sa: Editor already includes run.jobs.run; no grant needed"
else
  if gcloud iam service-accounts describe "$SA_SCHED_EMAIL" "${GC_PROJ[@]}" >/dev/null 2>&1; then
    echo "  exists"
  else
    run gcloud iam service-accounts create "$SA_SCHED" \
      --display-name "Traffic collector scheduler" "${GC_PROJ[@]}"
    [ "$DRY_RUN" = 1 ] || sleep 15
  fi
  run gcloud run jobs add-iam-policy-binding "$JOB" \
    --member="serviceAccount:$SA_SCHED_EMAIL" --role=roles/run.invoker \
    --region "$REGION" --format=none "${GC_PROJ[@]}"
fi

# --- 4. Cloud Scheduler ----------------------------------------------------------------------
# POST to the Cloud Run Admin API jobs:run with an OAuth token (not OIDC: this is a Google API, not a Run service).
# The Scheduler service agent can mint tokens for the scheduler SA; the deployer needs serviceAccountUser on it.
step "4. Cloud Scheduler job $SCHED"
RUN_URI="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$JOB:run"
SCHED_ARGS=(
  --location "$REGION"
  --schedule "*/30 * * * *"
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
# Metric run.googleapis.com/job/completed_execution_count, resource cloud_run_job, label `result`.
# The Monitoring docs list the values as success/failure; Cloud Run docs use "failed". The policy
# filter matches both with the regex fail.*
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

POLICY_FILE=$(mktemp "${TMPDIR:-/tmp}/collector_alert_policy.XXXXXX")
trap 'rm -f "$DS_FILE" "$POLICY_FILE"' EXIT
sed -e "s|__POLICY_NAME__|$POLICY_NAME|g" -e "s|__JOB__|$JOB|g" \
    -e "s|__REGION__|$REGION|g" -e "s|__CHANNEL__|$CHANNEL|g" \
    scripts/collector_alert_policy.json > "$POLICY_FILE"

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
  scheduler        : $SCHED, */30 * * * * Asia/Jakarta$([ "$NO_SCHEDULE" = 1 ] && echo " (skipped or paused: --no-schedule)")
  alert            : "$POLICY_NAME" -> $ALERT_EMAIL
  budget alert     : not created (needs billing-account access; ask the user)
$([ "$DRY_RUN" = 1 ] && echo "  DRY RUN          : nothing was changed")

Trigger one manual run:
  gcloud run jobs execute $JOB --region $REGION --project $PROJECT --wait
EOF

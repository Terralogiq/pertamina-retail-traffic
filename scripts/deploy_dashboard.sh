#!/usr/bin/env bash
# Deploy the dashboard: Cloud Run service (FastAPI + Vite build), its two secrets and the Maps browser key.
# Spec: docs/plans/dashboard.md (Phase 1).
#
# Re-runnable. Every step describes first and only creates or updates what is missing or changed.
# Read-only checks (describe/list) always run; every mutating command goes through run().
# Secret values never pass through this script: you add the password yourself, and the browser key
# is piped from `gcloud services api-keys get-key-string` straight into Secret Manager.
#
#   scripts/deploy_dashboard.sh               deploy everything
#   scripts/deploy_dashboard.sh --dry-run     print every mutating command, change nothing
#   scripts/deploy_dashboard.sh --default-sa  run the service as the Compute Engine default service account
#                                             (has Editor) instead of creating traffic-dashboard. Only grants
#                                             added: secretAccessor on the two dashboard secrets.
#                                             Re-running without it moves to the dedicated account (bead pertamina-retail-traffic-907.7.12).
#   scripts/deploy_dashboard.sh --map-id ID   set MAPS_MAP_ID on the service (cloud-styled Map ID); same as exporting
#                                             MAPS_MAP_ID. Without either, the service keeps its current value and the
#                                             map uses Google's DEMO_MAP_ID.
set -euo pipefail

PROJECT=gcp-coe-sandbox
REGION=asia-southeast2
DATASET=traffic
SERVICE=traffic-dashboard
SA_RUN=traffic-dashboard
SECRET_PASSWORD=DASHBOARD_PASSWORD
SECRET_KEY=MAPS_BROWSER_KEY
KEY_DISPLAY_NAME="traffic-dashboard browser key (Maps JavaScript API)"

# Read-only describe/list calls must never block on or auto-answer a prompt (e.g. "enable API? y/N").
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

DS_FILE=""
DRY_RUN=0
DEFAULT_SA=0
MAP_ID="${MAPS_MAP_ID:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --default-sa) DEFAULT_SA=1 ;;
    --map-id)
      [ $# -ge 2 ] && [ -n "$2" ] || { echo "--map-id needs a value" >&2; exit 2; }
      MAP_ID="$2"
      shift
      ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# The default quota project of gcloud is a different project, so name the project and the billing project everywhere.
GC_PROJ=(--project "$PROJECT" --billing-project "$PROJECT")
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
DEFAULT_SA_EMAIL="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
if [ "$DEFAULT_SA" = 1 ]; then
  SA_RUN_EMAIL="$DEFAULT_SA_EMAIL"
else
  SA_RUN_EMAIL="$SA_RUN@$PROJECT.iam.gserviceaccount.com"
fi
SERVICE_URL="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app"
REFERRERS="$SERVICE_URL/*,http://localhost:5173/*"
KEY_TARGET=(--api-target=service=maps-backend.googleapis.com --allowed-referrers="$REFERRERS")

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

has_version() {  # has_version SECRET: true when the secret exists and has at least one version
  [ -n "$(gcloud secrets versions list "$1" --limit 1 --format='value(name)' "${GC_PROJ[@]}" 2>/dev/null || true)" ]
}

# --- 1. APIs ---------------------------------------------------------------------------------
step "1. Enable APIs"
WANTED_APIS="run cloudbuild artifactregistry bigquery secretmanager apikeys iam"
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
# Maps JavaScript API must be on for the browser key to work. Not part of the list above: it is a Maps API.
if printf '%s\n' "$ENABLED" | grep -qx "maps-backend.googleapis.com"; then
  echo "  maps-backend: enabled"
else
  run gcloud services enable maps-backend.googleapis.com "${GC_PROJ[@]}"
fi

# --- 2. Secrets (containers only) ------------------------------------------------------------
step "2. Secrets $SECRET_PASSWORD and $SECRET_KEY"
for secret in "$SECRET_PASSWORD" "$SECRET_KEY"; do
  if gcloud secrets describe "$secret" "${GC_PROJ[@]}" >/dev/null 2>&1; then
    echo "  $secret: exists"
  else
    run gcloud secrets create "$secret" --replication-policy automatic "${GC_PROJ[@]}"
  fi
done

# --- 3. Browser API key ----------------------------------------------------------------------
# Restricted to the Maps JavaScript API and our two referrers. Re-running re-applies the restrictions.
# Its keyString goes straight into the secret, only when the secret has no version yet (no rotation).
step "3. Browser API key -> $SECRET_KEY"
KEY_NAME=$(gcloud services api-keys list --filter="displayName=\"$KEY_DISPLAY_NAME\"" \
  --format='value(name)' "${GC_PROJ[@]}" | head -n 1)
if [ -n "$KEY_NAME" ]; then
  echo "  key exists: $KEY_NAME; re-applying restrictions"
  # stderr carries the full Key, keyString included: keep it out of the terminal
  run gcloud services api-keys update "$KEY_NAME" "${KEY_TARGET[@]}" "${GC_PROJ[@]}" 2>/dev/null \
    || { echo "api-keys update failed (stderr suppressed: it carries the key string)" >&2; exit 1; }
elif [ "$DRY_RUN" = 1 ]; then
  run gcloud services api-keys create --display-name "$KEY_DISPLAY_NAME" "${KEY_TARGET[@]}" \
    --format 'value(response.name)' "${GC_PROJ[@]}"
  KEY_NAME="projects/$PROJECT_NUMBER/locations/global/keys/<NEW_KEY_ID>"
else
  KEY_NAME=$(gcloud services api-keys create --display-name "$KEY_DISPLAY_NAME" "${KEY_TARGET[@]}" \
    --format 'value(response.name)' "${GC_PROJ[@]}" 2>/dev/null)  # stderr carries keyString
  [ -n "$KEY_NAME" ] || { echo "api-keys create failed (stderr suppressed: it carries the key string)" >&2; exit 1; }
  echo "  key created: $KEY_NAME"
fi
if has_version "$SECRET_KEY"; then
  echo "  $SECRET_KEY already has a version; not rewriting it"
elif [ "$DRY_RUN" = 1 ]; then
  echo "+ gcloud services api-keys get-key-string $KEY_NAME --format 'value(keyString)' | tr -d '\\n' | gcloud secrets versions add $SECRET_KEY --data-file=- (key never shown)"
else
  gcloud services api-keys get-key-string "$KEY_NAME" --format 'value(keyString)' "${GC_PROJ[@]}" \
    | tr -d '\n' | gcloud secrets versions add "$SECRET_KEY" --data-file=- --format=none "${GC_PROJ[@]}"
  echo "  keyString stored in $SECRET_KEY (not printed)"
fi

# --- 4. Service account ----------------------------------------------------------------------
step "4. Dashboard identity ($SA_RUN_EMAIL)"
if [ "$DEFAULT_SA" = 1 ]; then
  echo "  --default-sa: using the Compute Engine default service account (Editor); only the secret grants below"
else
  if gcloud iam service-accounts describe "$SA_RUN_EMAIL" "${GC_PROJ[@]}" >/dev/null 2>&1; then
    echo "  exists"
  else
    run gcloud iam service-accounts create "$SA_RUN" \
      --display-name "Traffic dashboard (Cloud Run service)" "${GC_PROJ[@]}"
    # A new service account can take a few seconds to be visible to IAM bindings.
    [ "$DRY_RUN" = 1 ] || sleep 15
  fi
  # Read-only on the dataset: add a READER (= bigquery.dataViewer) ACL entry unless the account already has one.
  # `bq add-iam-policy-binding -d` is not usable ("requires allowlisting"), so edit the dataset ACL like the collector does.
  DS_FILE=$(mktemp "${TMPDIR:-/tmp}/dashboard_dataset.XXXXXX")
  trap 'rm -f "$DS_FILE"' EXIT
  bq --project_id="$PROJECT" show --format=prettyjson "$PROJECT:$DATASET" > "$DS_FILE"
  if grep -q "\"$SA_RUN_EMAIL\"" "$DS_FILE"; then
    echo "  $DATASET dataset already lists $SA_RUN_EMAIL"
  else
    python3 -I -c '
import json, sys
path, email = sys.argv[1:]
ds = json.load(open(path))
ds.setdefault("access", []).append({"role": "READER", "userByEmail": email})
json.dump(ds, open(path, "w"), indent=2)
' "$DS_FILE" "$SA_RUN_EMAIL"
    run bq --project_id="$PROJECT" update --source "$DS_FILE" "$PROJECT:$DATASET"
  fi
  # jobUser has to be project-level: it is what allows running query jobs.
  run gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA_RUN_EMAIL" --role=roles/bigquery.jobUser \
    --condition=None --format=none "${GC_PROJ[@]}"
fi
for secret in "$SECRET_PASSWORD" "$SECRET_KEY"; do
  run gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:$SA_RUN_EMAIL" --role=roles/secretmanager.secretAccessor \
    --format=none "${GC_PROJ[@]}"
done

# --- 5. Cloud Build permissions for --source deploys -----------------------------------------
# Cloud Build builds as the Compute Engine default service account, which needs roles/run.builder.
# In this project it has roles/editor, which covers it; grant run.builder only when neither role is present.
step "5. Cloud Build service account (Compute Engine default) can build"
BUILD_ROLES=$(gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:$DEFAULT_SA_EMAIL" --format='value(bindings.role)')
if printf '%s\n' "$BUILD_ROLES" | grep -qE '^roles/(editor|run\.builder)$'; then
  echo "  $DEFAULT_SA_EMAIL already has editor or run.builder"
else
  run gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$DEFAULT_SA_EMAIL" --role=roles/run.builder \
    --condition=None --format=none "${GC_PROJ[@]}"
fi

# --- 6. Password gate: the user sets the value -----------------------------------------------
step "6. $SECRET_PASSWORD value"
ADD_PASSWORD_CMD="read -rs PW && printf '%s' \"\$PW\" | gcloud secrets versions add $SECRET_PASSWORD --data-file=- --project $PROJECT --billing-project $PROJECT; unset PW"
if has_version "$SECRET_PASSWORD"; then
  echo "  $SECRET_PASSWORD has a version"
else
  cat <<MSG
  $SECRET_PASSWORD has no version yet. Set it yourself (type the password, then Enter; it never passes through this script):
    $ADD_PASSWORD_CMD
MSG
  if [ "$DRY_RUN" != 1 ]; then
    echo "  Not deploying: the service would fail to start without it. Run the command above, then re-run this script." >&2
    exit 1
  fi
fi

# --- 7. Cloud Run service --------------------------------------------------------------------
# `deploy` creates or updates, so it is idempotent. --set-* replace the whole env/secret set, so drift is reset on every run.
# --quiet accepts the prompt to create the Artifact Registry repo cloud-run-source-deploy.
# The page and static files are public; /api/* is gated by the password cookie (docs/plans/dashboard.md).
step "7. Cloud Run service $SERVICE (build from dashboard/)"
# MAPS_MAP_ID is optional (the map falls back to DEMO_MAP_ID). The script sets no other plain env var, so
# --set-env-vars is safe here; when no Map ID is given the service's current env is left untouched.
MAP_ENV=()
MAP_NOTE="not set (DEMO_MAP_ID, or the value already on the service)"
if [ -n "$MAP_ID" ]; then
  MAP_ENV=(--set-env-vars "MAPS_MAP_ID=$MAP_ID")
  MAP_NOTE="$MAP_ID"
else
  echo "  MAPS_MAP_ID not set (export it or pass --map-id ID): the map uses DEMO_MAP_ID, and an existing value on the service is kept"
fi
run gcloud run deploy "$SERVICE" \
  --source dashboard \
  --region "$REGION" \
  --service-account "$SA_RUN_EMAIL" \
  --allow-unauthenticated \
  --set-secrets "$SECRET_PASSWORD=$SECRET_PASSWORD:latest,$SECRET_KEY=$SECRET_KEY:latest" \
  ${MAP_ENV[@]+"${MAP_ENV[@]}"} \
  --min-instances 1 \
  --cpu-boost \
  --max-instances 3 \
  --quiet "${GC_PROJ[@]}"

# --- 8. Summary ------------------------------------------------------------------------------
step "8. Summary"
cat <<EOF
  project / region : $PROJECT / $REGION
  service          : $SERVICE (runs as $SA_RUN_EMAIL)
  url              : $SERVICE_URL
  map id           : $MAP_NOTE
  browser key      : restricted to maps-backend.googleapis.com, referrers $REFERRERS
$([ "$DRY_RUN" = 1 ] && echo "  DRY RUN          : nothing was changed")

Rotate the password later: $ADD_PASSWORD_CMD   (then deploy a new revision; everyone is logged out)

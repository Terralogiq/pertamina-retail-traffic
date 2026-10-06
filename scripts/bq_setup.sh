#!/usr/bin/env bash
# Create dataset `traffic` and run sql/ddl.sql. Re-runnable.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROJECT=gcp-coe-sandbox
LOCATION=asia-southeast2
BQ=(bq --project_id="$PROJECT" --location="$LOCATION")

if ! "${BQ[@]}" show --dataset "$PROJECT:traffic" >/dev/null 2>&1; then
  "${BQ[@]}" mk --dataset "$PROJECT:traffic"
fi

"${BQ[@]}" query --use_legacy_sql=false --quiet < sql/ddl.sql

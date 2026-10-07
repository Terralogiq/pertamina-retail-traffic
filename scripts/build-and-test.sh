#!/usr/bin/env bash
# Build & test for the Stop hook and CI. Offline: no network calls.
# The dashboard tests need the packages from scripts/dev-setup.sh (.venv, dashboard/web/node_modules).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [ ! -x .venv/bin/python ] || [ ! -d dashboard/web/node_modules ]; then
  echo "run scripts/dev-setup.sh" >&2
  exit 1
fi
PY=.venv/bin/python
$PY -m py_compile scripts/*.py
$PY -m py_compile collector/*.py
$PY -m py_compile dashboard/api/*.py dashboard/api/routers/*.py
$PY -m unittest discover -s tests -v
cd dashboard/web
npx tsc --noEmit
npx vite build
npx vitest run

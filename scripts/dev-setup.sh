#!/usr/bin/env bash
# One-time local setup for the dashboard (needs network): Python venv + npm packages.
# scripts/build-and-test.sh stays offline and expects this to have run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -r dashboard/requirements.txt
(cd dashboard/web && npm ci)

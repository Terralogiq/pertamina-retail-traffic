#!/usr/bin/env bash
# Build & test for the Stop hook and CI. Offline: no network calls.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -v

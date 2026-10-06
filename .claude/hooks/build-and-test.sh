#!/usr/bin/env bash
# Stop hook: Build & test from CLAUDE.md must be green before Claude stops.
# Exit 2 blocks the stop and feeds stderr back to Claude.
input=$(cat)
# Already continuing because of this hook — don't loop forever on a red suite.
if printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 0
# No git yet, or nothing changed (a Q&A turn) — skip.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
[ -z "$(git status --porcelain)" ] && exit 0
# No code yet — scripts/build-and-test.sh is added with the first code slice.
[ -x scripts/build-and-test.sh ] || exit 0

out=$(scripts/build-and-test.sh 2>&1)
status=$?
if [ $status -ne 0 ]; then
  printf 'Build & test failed — fix before stopping:\n%s\n' "$(printf '%s' "$out" | tail -40)" >&2
  exit 2
fi
exit 0

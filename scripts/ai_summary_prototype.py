#!/usr/bin/env python3
"""Prototype for bead .10.4: short AI summaries per SPBU, grounded on facts built in SQL. Plan: docs/plans/ai-summaries.md.

The facts queries, prompt, Gemini call and validator live in dashboard/api/ai_summary.py (the dashboard generates
summaries on demand with the same code); this script runs them for chosen sites from a workstation, for the frozen
spot-check when the model id or prompt version changes:

  1. facts_for_site   read-only BigQuery queries -> a small facts dict, one key per topic.
  2. call_gemini      the facts go to the Gemini API; the answer is 4-6 sentences as JSON, each tagged with a topic.
  3. validate_summary every number, time, weekday and direction word in a sentence must come from the facts.

Review text, gists and author names never leave BigQuery: the facts carry label counts only.
Writes out/ai_summaries/<UTC timestamp>/<site_id>.json (git-ignored). No BigQuery writes.

Usage: .venv/bin/python scripts/ai_summary_prototype.py --site 34.121.03 --site KM57A [--facts-only] [--out-dir DIR]
Needs google-cloud-bigquery and ADC (.venv), plus GEMINI_API_KEY or gcloud access to Secret Manager `gemini-api-key`
in gcp-coe-492507 (never printed).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from dashboard.api import ai_summary as core, bq  # noqa: E402

KEY_SECRET_PROJECT = "gcp-coe-492507"
# Gemini API paid tier, USD per 1M tokens, through 2026-12-31 (https://ai.google.dev/gemini-api/docs/pricing).
PRICE_IN, PRICE_OUT = 0.75, 3.75

SITE_SQL = f"""
SELECT site_id, name, city, road_name, road_type, timezone, place_id
FROM {bq.table("sites")} WHERE site_id = @site_id"""


def get_key():
    key = core.api_key()
    if key:
        return key
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret=gemini-api-key",
         f"--project={KEY_SECRET_PROJECT}", f"--billing-project={bq.PROJECT}"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("GEMINI_API_KEY is not set and the gcloud secret fetch failed: " + out.stderr.strip()[:200])
    return out.stdout.strip()


def site_for(site_id):
    site = bq.query(SITE_SQL, {"site_id": site_id})[0]
    return {**site, "road_class": "toll" if "toll" in (site["road_type"] or "").lower() else "urban"}


def cost_usd(usage):
    """Gemini API paid-tier cost of one call; thinking tokens bill as output."""
    if not usage:
        return None
    out = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    return (usage.get("promptTokenCount", 0) * PRICE_IN + out * PRICE_OUT) / 1e6


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", action="append", required=True, help="site_id; repeat for several sites")
    ap.add_argument("--facts-only", action="store_true", help="build and save the facts; no Gemini call")
    ap.add_argument("--thinking-level", default="LOW", help="LOW, MEDIUM, HIGH or '' to leave the model default")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_dir or os.path.join(ROOT, "out", "ai_summaries", stamp)
    os.makedirs(out_dir, exist_ok=True)
    key = None if args.facts_only else get_key()
    for site_id in args.site:
        t0 = time.monotonic()
        facts, as_of = core.facts_for_site(site_for(site_id), datetime.now(timezone.utc))
        facts_seconds = round(time.monotonic() - t0, 2)
        result = {"site_id": site_id, "generated_at": datetime.now(timezone.utc).isoformat(), "model": core.MODEL,
                  "prompt_version": core.PROMPT_VERSION, "as_of": as_of, "facts": facts,
                  "facts_query_seconds": facts_seconds}
        if key:
            g = core.call_gemini(key, facts, args.thinking_level or None)
            result.update({"gemini_seconds": g["latency_ms"] / 1000, "usage": g["usage"],
                           "model_version": g["model_version"], "cost_usd": cost_usd(g["usage"]), "error": g["error"]})
            if g["sentences"] is not None:
                result["validation"] = core.validate_summary(g["sentences"], facts)
        with open(os.path.join(out_dir, f"{site_id}.json"), "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        v = result.get("validation")
        print(f"{site_id}: facts {facts_seconds}s"
              + (f", gemini {result['gemini_seconds']}s, error {result['error']}" if key else "")
              + (f", validation ok={v['ok']}" if v else ""))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

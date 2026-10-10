"""Cloud Run job entry point: poll the newest Google reviews of every site (legacy Place Details), or label them.

Reads the sites (place_id) from BigQuery, calls legacy Place Details per site and variant, and MERGEs the
distinct reviews into place_reviews and one row per call into place_review_snapshots.
--mode newest: reviews_sort=newest, language=id (1 call per site; daily).
--mode sample: newest/id + most_relevant/id + most_relevant/en (3 calls per site; weekly): a wider picture and the
rating/count snapshot, about 15 distinct reviews per site.
--mode label: sends the text reviews that have no Gemini label at the current model_version to Gemini
(gemini-3.8-flash, 10 reviews per call, JSON constrained to the taxonomy) and MERGEs the labels into
place_review_labels (daily, after the newest run; 0 calls when nothing is new).
Exit code 0 when every call succeeded; 1 when no call was made or any call failed (the rows of the successful
calls are written first; Cloud Run then retries the same execution, which is idempotent). In label mode no call
because nothing is unlabelled is a success; 1 means a Gemini call failed or nothing at all could be labelled.

Env: GCP_PROJECT (gcp-coe-sandbox), BQ_DATASET (traffic), BQ_LOCATION (asia-southeast2),
MAPS_API_KEY (secret from projects/demogcp-terra2021; never logged), GEMINI_API_KEY (label mode; secret from
projects/gcp-coe-492507; never logged), CLOUD_RUN_EXECUTION (the run_id).
Flags: --dry-run  read the sites (or the unlabelled reviews), call the API, print a summary, write nothing
Logs and output carry counts only: no review text, gist or key.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import gemini
import review_labels
import reviews

log = logging.getLogger("reviews_job")
WORKERS = 5
KEY_SECRET_PROJECT = "demogcp-terra2021"   # legacy Places API is enabled only here
GEMINI_KEY_SECRET_PROJECT = "gcp-coe-492507"


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    """RFC 3339 UTC string, as BigQuery loads accept for TIMESTAMP."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_key(dry_run, env_var="MAPS_API_KEY", secret="maps-api-key", secret_project=KEY_SECRET_PROJECT):
    """The API key from the environment (Cloud Run mounts the secret there); --dry-run may fetch it with gcloud."""
    key = os.environ.get(env_var, "").strip()
    if key:
        return key
    if not dry_run:
        sys.exit(f"{env_var} is not set")
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret}",
         f"--project={secret_project}", "--billing-project=gcp-coe-sandbox"],
        capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit(f"{env_var} is not set and the gcloud secret fetch failed: " + out.stderr.strip()[:200])
    return out.stdout.strip()


def get_run_id():
    """The Cloud Run execution name is the same for every attempt of a task, so a retry re-uses it."""
    return os.environ.get("CLOUD_RUN_EXECUTION") or uuid.uuid4().hex


def print_summary(mode, run_id, fetched_at, r_rows, s_rows, errors):
    print(f"mode {mode}  run_id {run_id}  fetched_at {iso(fetched_at)}")
    print(f"place_reviews: {len(r_rows)} distinct reviews; place_review_snapshots: {len(s_rows)} rows; "
          f"{len(errors)} failed calls")
    for s in s_rows:
        print(f"  {s['site_id']:10} {s['variant']:16} rating {s['rating']}  total {s['user_ratings_total']}  "
              f"{s['n_reviews']} reviews")
    for e in errors:
        print(f"  ERROR {e}")
    # The sample row is cut to the non-author fields: raw holds the author name and profile URLs.
    for name, rows in (("place_reviews", r_rows), ("place_review_snapshots", s_rows)):
        if rows:
            row = {k: v for k, v in rows[0].items() if k != "raw"}
            print(f"sample {name} row:\n" + json.dumps(row, indent=2, ensure_ascii=False))


def exit_code(total, failed):
    """1 when there were no API calls or any call failed, else 0."""
    return 1 if total == 0 or failed else 0


def label_exit_code(selected, failed_calls, written):
    """1 when a Gemini call failed, or reviews were selected and none could be labelled; else 0 (also for 0 selected)."""
    return 1 if failed_calls or (selected and not written) else 0


def print_label_summary(selected, rows, totals):
    """Counts only: no review text, no gist."""
    print(f"mode label  model_version {gemini.MODEL_VERSION}")
    print(f"{selected} reviews selected; {totals['calls']} Gemini calls ({totals['failed_calls']} failed); "
          f"{len(rows)} labelled, {totals['invalid']} invalid, {totals['missing']} missing")
    print("sentiment: " + ", ".join(f"{s} {sum(1 for r in rows if r['sentiment'] == s)}" for s in review_labels.SENTIMENTS))
    print("labels: " + ", ".join(f"{t} {sum(1 for r in rows if t in r['labels'])}" for t in review_labels.TAXONOMY))


def run_label(project, dataset, location, dry_run):
    key = get_key(dry_run, "GEMINI_API_KEY", "gemini-api-key", GEMINI_KEY_SECRET_PROJECT)
    import bq  # lazy: keeps google-cloud-bigquery out of the import path of the pure modules
    todo = bq.read_unlabelled(project, dataset, location, gemini.MODEL_VERSION)
    log.info("label: %d text reviews without a gemini label at %s", len(todo), gemini.MODEL_VERSION)
    if not todo:
        log.info("nothing to label, 0 Gemini calls")
        return 0
    now = utc_now()
    rows, totals = gemini.label_reviews(key, todo, iso(now))
    log.info("%d Gemini calls, %d failed; %d rows labelled, %d invalid and %d missing skipped",
             totals["calls"], totals["failed_calls"], len(rows), totals["invalid"], totals["missing"])
    if totals["reasons"]:
        log.warning("failed call reasons: %s", "; ".join(totals["reasons"]))  # codes only: no body, no key
    if dry_run:
        print_label_summary(len(todo), rows, totals)
    elif rows:
        bq.write_labels(project, dataset, location, now, rows)
        log.info("merged %d labels into place_review_labels", len(rows))
    return label_exit_code(len(todo), totals["failed_calls"], len(rows))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mode", choices=sorted(reviews.MODES) + ["label"], default="newest")
    ap.add_argument("--dry-run", action="store_true", help="call the API, print a summary, write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    project = os.environ.get("GCP_PROJECT", "gcp-coe-sandbox")
    dataset = os.environ.get("BQ_DATASET", "traffic")
    location = os.environ.get("BQ_LOCATION", "asia-southeast2")
    if args.mode == "label":
        return run_label(project, dataset, location, args.dry_run)
    run_id = get_run_id()
    fetched_at = utc_now()
    fetched_iso = iso(fetched_at)
    key = get_key(args.dry_run)

    import bq  # lazy: keeps google-cloud-bigquery out of the import path of the pure modules
    sites = bq.read_sites(project, dataset, location)
    log.info("run %s, mode %s: %d sites", run_id, args.mode, len(sites))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(reviews.poll_site, key, s, args.mode, run_id, fetched_iso) for s in sites]
        results = [f.result() for f in futs]

    r_rows = [r for res in results for r in res[0]]
    s_rows = [r for res in results for r in res[1]]
    total = sum(res[2] for res in results)
    errors = [e for res in results for e in res[3]]
    for e in errors:
        log.warning("%s", e)
    log.info("%d of %d API calls ok", total - len(errors), total)

    if args.dry_run:
        print_summary(args.mode, run_id, fetched_at, r_rows, s_rows, errors)
    else:
        bq.write_rows(project, dataset, location, fetched_at, r_rows, s_rows)
        log.info("merged %d reviews and %d snapshots", len(r_rows), len(s_rows))

    if total == 0:
        log.error("no sites")
    return exit_code(total, len(errors))


if __name__ == "__main__":
    sys.exit(main())

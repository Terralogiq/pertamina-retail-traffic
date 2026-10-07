"""Cloud Run job entry point: one Places profiling run over every site.

Reads the sites (place_id) from BigQuery, calls Place Details (1), Nearby Search (2 radii) and
Places Aggregate (15 types x 3 radii) per site, and MERGEs the rows into places_details,
places_nearby and places_aggregate. One run = one run_id; every row of an attempt has the same fetched_at.
Exit code 0 unless every API call failed or a site got no Details row (so a Cloud Run retry,
which re-uses the run_id, fills the gap without duplicating).

Env: GCP_PROJECT (gcp-coe-sandbox), BQ_DATASET (traffic), BQ_LOCATION (asia-southeast2),
MAPS_API_KEY (secret; never logged), CLOUD_RUN_EXECUTION (set by Cloud Run jobs; the run_id).
Flags: --dry-run  read the sites, call the APIs, print a summary and one sample row per table, write nothing
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

import places

log = logging.getLogger("places_job")
WORKERS = 5


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    """RFC 3339 UTC string, as BigQuery loads accept for TIMESTAMP."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_key(dry_run):
    key = os.environ.get("MAPS_API_KEY", "").strip()
    if key:
        return key
    if not dry_run:
        sys.exit("MAPS_API_KEY is not set")
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret=MAPS_API_KEY",
         "--project=gcp-coe-sandbox", "--billing-project=gcp-coe-sandbox"],
        capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("MAPS_API_KEY is not set and the gcloud secret fetch failed: " + out.stderr.strip()[:200])
    return out.stdout.strip()


def get_run_id():
    """The Cloud Run execution name is the same for every attempt of a task, so a retry re-uses it."""
    return os.environ.get("CLOUD_RUN_EXECUTION") or uuid.uuid4().hex


def _short(row, n=110):
    """A sample row with the long fields cut down for printing."""
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, str) and len(v) > n:
            out[k] = v[:n] + f"... [{len(v)} chars]"
        elif isinstance(v, list):
            out[k] = [_short(x, n) if isinstance(x, dict) else x for x in v[:2]] + (["..."] if len(v) > 2 else [])
    return out


def print_summary(run_id, fetched_at, d_rows, n_rows, a_rows, errors):
    print(f"run_id {run_id}  fetched_at {iso(fetched_at)}")
    print(f"places_details: {len(d_rows)} rows; places_nearby: {len(n_rows)} rows; "
          f"places_aggregate: {len(a_rows)} rows; {len(errors)} failed calls")
    for r in d_rows:
        print(f"  {r['site_id']:10} {r['business_status']}  rating {r['rating']}  n {r['user_rating_count']}  "
              f"{len(r['reviews'])} reviews  {len(r['weekday_descriptions'])} hours lines")
    for e in errors:
        print(f"  ERROR {e}")
    for name, rows in (("places_details", d_rows), ("places_nearby", n_rows), ("places_aggregate", a_rows)):
        if rows:
            print(f"sample {name} row:\n" + json.dumps(_short(rows[0]), indent=2, ensure_ascii=False))


def exit_code(total, failed, missing_details):
    """1 when there were no API calls, every call failed, or any site has no Details row, else 0."""
    return 1 if total == 0 or failed >= total or missing_details else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="call the APIs, print a summary, write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    project = os.environ.get("GCP_PROJECT", "gcp-coe-sandbox")
    dataset = os.environ.get("BQ_DATASET", "traffic")
    location = os.environ.get("BQ_LOCATION", "asia-southeast2")
    run_id = get_run_id()
    fetched_at = utc_now()
    fetched_iso = iso(fetched_at)
    key = get_key(args.dry_run)

    import bq  # lazy: keeps google-cloud-bigquery out of the import path of the pure modules
    sites = bq.read_sites(project, dataset, location)
    log.info("run %s: %d sites", run_id, len(sites))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(places.profile_site, key, s, run_id, fetched_iso) for s in sites]
        results = [f.result() for f in futs]

    d_rows = [r for res in results for r in res[0]]
    n_rows = [r for res in results for r in res[1]]
    a_rows = [r for res in results for r in res[2]]
    total = sum(res[3] for res in results)
    errors = [e for res in results for e in res[4]]
    for e in errors:
        log.warning("%s", e)
    log.info("%d of %d API calls ok", total - len(errors), total)
    missing_details = len(sites) - len(d_rows)
    if missing_details:
        log.error("%d site(s) have no Details row", missing_details)

    if args.dry_run:
        print_summary(run_id, fetched_at, d_rows, n_rows, a_rows, errors)
    else:
        bq.write_rows(project, dataset, location, fetched_at, d_rows, n_rows, a_rows)
        log.info("merged %d details, %d nearby and %d aggregate rows", len(d_rows), len(n_rows), len(a_rows))

    if total == 0:
        log.error("no sites")
    return exit_code(total, len(errors), missing_details)


if __name__ == "__main__":
    sys.exit(main())

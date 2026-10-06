"""Cloud Run job entry point: one run per 30-minute slot.

Reads the active routes, calls Routes (once per call_id) and Weather (once per site),
and MERGEs the rows into BigQuery. Exit code 0 unless every API call failed.

Env: GCP_PROJECT (gcp-coe-sandbox), BQ_DATASET (traffic), BQ_LOCATION (asia-southeast2),
MAPS_API_KEY (secret; never logged).
Flags: --dry-run  call the APIs, print a summary and one sample row per table, write nothing
       --routes-csv PATH  read routes from a routes.csv instead of BigQuery (needs --dry-run)
"""
import argparse
import csv
import json
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import slots
import traffic
import weather

log = logging.getLogger("collector")
WORKERS = 5


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


def _opt(row, col, cast):
    v = (row.get(col) or "").strip()
    return cast(v) if v else None


def load_routes_csv(path):
    """Routes from data/routes.csv (status ok = active), in the shape bq.read_active_routes returns.

    The CSV has no display_name; one is built from the site, side and leg.
    """
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] != "ok":
                continue
            out.append({
                "selected_route_id": r["selected_route_id"],
                "display_name": f"SPBU {r['site_id']} · {'SPBU side' if r['side'] == 'spbu_side' else 'Opposite'}"
                                f" · {r['leg'].capitalize()}",
                "site_id": r["site_id"], "side": r["side"], "call_id": r["call_id"],
                "leg_index": int(r["leg_index"]),
                "origin_lat": float(r["origin_lat"]), "origin_lng": float(r["origin_lng"]),
                "origin_heading": _opt(r, "origin_heading", int),
                "dest_lat": float(r["dest_lat"]), "dest_lng": float(r["dest_lng"]),
                "dest_heading": _opt(r, "dest_heading", int),
                "expected_distance_m": _opt(r, "expected_distance_m", int),
            })
    return out


def _short(row, n=110):
    """A sample row with the long fields cut down for printing."""
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, str) and len(v) > n:
            out[k] = v[:n] + f"... [{len(v)} chars]"
    return out


def print_summary(slot, t_rows, w_rows, t_errors, w_errors):
    print(f"slot_time {slots.iso(slot)}")
    print(f"traffic: {len(t_rows)} rows, {sum(r['duration_in_seconds'] is not None for r in t_rows)} with duration; "
          f"{len(t_errors)} failed calls")
    for r in t_rows:
        f = lambda v, fmt: "-" if v is None else format(v, fmt)  # noqa: E731
        print(f"  {r['selected_route_id']:36} dur {f(r['duration_in_seconds'], '6.0f')} s  "
              f"static {f(r['static_duration_in_seconds'], '6.0f')} s  ratio {f(r['static_ratio'], '5.2f')}  "
              f"{f(r['speed_kmh'], '5.1f')} km/h  dist {f(r['demo_distance_m'], '5.0f')} m  "
              f"geom {'yes' if r['route_geometry'] else 'NO'}")
    print(f"weather: {len(w_rows)} rows, {sum(r['temperature_c'] is not None for r in w_rows)} with values; "
          f"{len(w_errors)} failed calls")
    for r in w_rows:
        f = lambda v, fmt: "-" if v is None else format(v, fmt)  # noqa: E731
        print(f"  {r['site_id']:10} {f(r['temperature_c'], '5.1f')} C  RH {f(r['relative_humidity'], '3.0f')}%  "
              f"rain {f(r['precipitation_mm'], '4.1f')} mm flag {r['rain_flag']}  "
              f"wind {f(r['wind_speed_kmh'], '4.1f')} km/h @ {f(r['wind_direction_deg'], '3.0f')} deg  "
              f"{f(r['msl_pressure_hpa'], '6.1f')} hPa  {r['demo_condition_type']}")
    for e in t_errors + w_errors:
        print(f"  ERROR {e}")
    if t_rows:
        print("sample traffic_snapshots row:\n" + json.dumps(_short(t_rows[0]), indent=2, ensure_ascii=False))
    if w_rows:
        print("sample weather_slots row:\n" + json.dumps(_short(w_rows[0]), indent=2, ensure_ascii=False))


def exit_code(total, failed):
    """1 when there were no API calls or every call failed, else 0."""
    return 1 if total == 0 or failed == total else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="call the APIs, print a summary, write nothing")
    ap.add_argument("--routes-csv", metavar="PATH", help="read routes from this CSV instead of BigQuery (dry run only)")
    args = ap.parse_args(argv)
    if args.routes_csv and not args.dry_run:
        ap.error("--routes-csv is for dry runs; it needs --dry-run")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    project = os.environ.get("GCP_PROJECT", "gcp-coe-sandbox")
    dataset = os.environ.get("BQ_DATASET", "traffic")
    location = os.environ.get("BQ_LOCATION", "asia-southeast2")
    slot = slots.slot_time()
    key = get_key(args.dry_run)

    if args.routes_csv:
        routes = load_routes_csv(args.routes_csv)
    else:
        import bq  # lazy: google-cloud-bigquery is not needed for a CSV dry run
        routes = bq.read_active_routes(project, dataset, location)
    calls = traffic.group_calls(routes)
    sites = weather.site_fronts(routes)
    log.info("slot %s: %d routes, %d calls, %d sites", slots.iso(slot), len(routes), len(calls), len(sites))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        t_futs = [pool.submit(traffic.fetch_call, key, legs, slot) for legs in calls.values()]
        w_futs = [pool.submit(weather.fetch_site, key, sid, lat, lng, slot) for sid, lat, lng in sites]
        t_results = [f.result() for f in t_futs]
        w_results = [f.result() for f in w_futs]

    t_rows = [row for rows, _ in t_results for row in rows]
    w_rows = [row for row, _ in w_results]
    t_errors = [f"traffic {cid}: {err}" for cid, (_, err) in zip(calls, t_results) if err]
    w_errors = [f"weather {sid}: {err}" for (sid, _, _), (_, err) in zip(sites, w_results) if err]
    for e in t_errors + w_errors:
        log.warning("%s", e)
    total = len(calls) + len(sites)
    failed = len(t_errors) + len(w_errors)
    log.info("%d of %d API calls ok", total - failed, total)

    if args.dry_run:
        print_summary(slot, t_rows, w_rows, t_errors, w_errors)
    else:
        import bq
        bq.write_rows(project, dataset, location, slot, t_rows, w_rows)
        log.info("merged %d traffic rows and %d weather rows", len(t_rows), len(w_rows))

    if total == 0:
        log.error("no active routes")
    return exit_code(total, failed)


if __name__ == "__main__":
    sys.exit(main())

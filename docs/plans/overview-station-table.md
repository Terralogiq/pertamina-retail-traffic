# Overview station table: queue risk and complaints across all stations

Superseded: the shipped overview is [overview-potential-queues.md](overview-potential-queues.md).

Beads: `.10.25` (table and endpoints), `.9.14` (Review themes placement). Related: `.10.18` (site-page queue-risk card, absorbs `.10.26`, waits for the Street View check `.10.16`), `.9.15` (Maps key referrer, a console or `gcloud` change, no code).

## Why

The end-to-end review on 2026-10-14 checked the dashboard against its two purposes: which SPBU might have or cause queues in front of them, and which SPBU have complaints in reviews and of what kind. The data answers both, but no screen does. The overview ranks sites by how slow the road is right now, so at a quiet hour it shows nothing. Queue risk lives only in [queue-risk.md](queue-risk.md), and complaint themes are visible one site at a time, at the bottom of the site page.

## Decisions (user, 2026-10-14)

| Topic | Decision |
|---|---|
| Queue risk on the overview | Shown now, before the 14-day mark and any validation step. This overrides the overview gate in [queue-risk.md](queue-risk.md) "Screen proposal" |
| Wording | Neutral: "slower before the station than after it". Never "queue" or "likely queue" for the traffic signal until validation steps 3 or 4 confirm ([queue-risk.md](queue-risk.md) "Validation plan") |
| Masked sites | Shown as "cannot tell" with the reason, listed last when sorting by queue risk |
| Default sort | By station name. Queue risk and each complaint column are sortable |
| Site-page card | `.10.18` stays gated on the Street View check; it reuses the endpoint built here |

## What the table shows

One row per active site, below the map and site list, full width, heading "Stations at a glance". Columns:

| Column | Content | Source |
|---|---|---|
| Station | Name, city; links to `/site/:site_id` | `sites` |
| Slower before than after | Signal tier (Strong, Moderate, Weak, None, Cannot tell), then "on N of M days, usually X s" | New endpoint below |
| Confidence | Medium, Low, Very low or None, with a one-line reason on hover or in the table view, and "as of" the analysis date | Reference file below |
| Queue complaints | Reviews labelled `antrian`, negative or mixed | New endpoint below |
| Top complaint | Most frequent category (English label from `dashboard/web/src/reviews/model.ts`) and its count; ties list both | Same |
| Reviews labelled | n labelled reviews with text | Same |

Fixed captions under the table:

- "Road traffic on the 500 m before and after each station, from the last 28 days. Not a count of cars at the pumps, and not checked on the ground."
- "Complaints come from a sample of at most 15 Google reviews per window and station (12–16 labelled per station). Counts, not rates."

The table has the existing "Chart / Table" accessibility pattern only if it adds something; it is already a table, so no toggle.

## Signal tier

The tier is computed, so it moves with the data. Inputs are the per-site metrics of the [queue-risk.md](queue-risk.md) "Reproduce" query over the same rolling 28-day window as typical-day: `als_pct`, `both_slow_pct`, `departure_only_pct`, `days_with_2h_als`, `full_days`, `als_median_delay_s`.

| Tier | Rule, in order |
|---|---|
| Cannot tell | `both_slow_pct > 2 * als_pct` and `departure_only_pct > 2 * als_pct` (strict, so a site with no slowdowns at all is None, not Cannot tell) |
| Strong | `days_with_2h_als >= 0.7 * full_days` and `als_median_delay_s >= 60` |
| Moderate | `days_with_2h_als >= 0.7 * full_days` |
| Weak | `days_with_2h_als >= 1` |
| None | otherwise |

Queue-risk sort order: tier, then `days_with_2h_als`, then `als_median_delay_s`, both descending; Cannot tell last.

On the 2026-10-06 17:30 to 2026-10-14 08:30 UTC window these rules reproduce the ranking in [queue-risk.md](queue-risk.md) "Ranking with confidence": Pemogan Strong; MT Haryono, Makassar, Lingkar Selatan Moderate (in that order); Tirtayasa, Antasari, KM57A Weak; Gayungan None; Daan Mogot and Bandung Cannot tell. That window's Results-table numbers become the unit-test fixture. The 2x thresholds are new; Antasari (`both_slow` 8.2%, `departure_only` 16.1%, ALS 6.0%) is the case that separates a looser rule from the doc's judgement.

## Confidence

Confidence is a judgement (commute shape, delay size, review corroboration, validation results), not a formula, so it is not computed. It lives in a reference file, `dashboard/api/queue_confidence.json`: per `site_id`, `level`, `reason` (one line) and `as_of`. Initial content is the 2026-10-14 table and reasons in [queue-risk.md](queue-risk.md). The 14-day and 4-week reruns (`.10.15`) and each validation step update it. The UI shows `as_of` so a stale judgement is visible.

## API

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /api/traffic/queue-risk` | One entry per active site: the six metrics above, `tier`, `confidence` (from the reference file), `window_days` | One BigQuery job for all sites (the Reproduce query with `GROUP BY site_id`, window from `cache.utc_now()`). Band rule, toll gate and holidays come from `busy.py` and `holidays.py`, so the rule stays in one place. Core columns only, no demo-only badge. Cached like `traffic/typical-day`. `.10.18` later adds `?site_id=` for the hourly strip |
| `GET /api/review-themes` | One entry per site: `n_labelled`, `queue_complaints`, `top` (categories with the max count, and the count), `categories` (all counts, recent plus older) | Same one-label-per-review rule and negative-or-mixed filter as `/api/sites/{site_id}/review-themes`, one job for all sites. No gists, no text. The docstring of `dashboard/api/routers/reviews.py` changes from "never a cross-site ranking" to "counts with n; a cross-site sort is allowed, rates are not" |

## Phases

| Phase | Work | Acceptance |
|---|---|---|
| 1. API | Both endpoints, tier function as a pure function, reference file | Unit tests: tier on the 2026-10-14 fixture gives the ranking above, including Antasari Weak and both masked sites Cannot tell; review summary counts match the per-site endpoint for every site (shared helper or a test that compares them); 401 without a session |
| 2. Overview table | Component, API client with the existing in-flight dedupe, sort control, captions, links | Vitest: renders 10 rows, default sort by name, queue-risk sort puts Cannot tell last, top-complaint ties shown; no `demo-only` badge; build green |
| 3. Site page | Move Review themes so it is visible without scrolling past the Places list at 1440x900 (`.9.14`) | Section nav still jumps to it; existing tests green |
| 4. Docs | [queue-risk.md](queue-risk.md) "Screen proposal": overview gate replaced by a pointer to this plan; [dashboard.md](dashboard.md) screen list | Docs match the build |

Then: `scripts/build-and-test.sh` green, `advisor-reviewer`, deploy with `scripts/deploy_dashboard.sh --default-sa`, check the live overview at both Cloud Run URLs once `.9.15` is done.

## File ownership

| File | Phase | Owner |
|---|---|---|
| `dashboard/api/routers/traffic.py` (queue-risk endpoint, SQL) | 1 | worker A |
| `dashboard/api/queue_risk.py` (tier function, new) | 1 | worker A |
| `dashboard/api/queue_confidence.json` (new) | 1 | worker A |
| `tests/test_dashboard_traffic.py`, `tests/test_queue_risk.py` (new) | 1 | worker A |
| `dashboard/api/routers/reviews.py` (summary endpoint, docstring) | 1 | worker A |
| `tests/test_dashboard_reviews.py` | 1 | worker A |
| `dashboard/web/src/overview/` (new: `StationTable.tsx`, `.css`, `api.ts`, tests) | 2 | worker B |
| `dashboard/web/src/map/Overview.tsx` (mount the table) | 2 | worker B |
| `dashboard/web/src/site/SiteDetail.tsx`, related CSS | 3 | worker B |
| `docs/plans/queue-risk.md`, `docs/plans/dashboard.md` | 4 | orchestrator |

Phase 2 depends on phase 1's response shapes; worker B can start from the shapes in this plan with a mocked client.

## Not in scope

- The site-page queue-risk card and hourly strip (`.10.18`).
- Any "queue" wording for the traffic signal before validation.
- Complaint rates, or review data beyond the current sample (`.10.24`).

# Remaining work, 2026-10-14

Parallel batch over the beads still open after the traffic-presentation merge. User decisions (2026-10-14): `.7.12` not now; `.9.8` includes min-instances 1; `.10.5.6` declined; `.10.5.7` with prompt p2 first; `.7.15` backfill yes. Orchestrator decision: `.7.14` makes the distance check two-sided, matching `docs/plans/collector.md`.

Not in this batch: `.9.10` Map ID (console, user), `.10.5.5` (waits for the reviewer), `.10.12` (gated to 2026-11-03), `.7.12` (user: not now).

## Tracks

| Track | Beads | Output |
|---|---|---|
| A | `.7.14`, `.7.15` | Two-sided reroute check; one-off backfill of `demo_rerouted` with the same rule |
| B | `.9.8` | Measured cold-load cause, query/fetch fixes, startup CPU boost, min-instances 1 |
| C | `.10.5.7` | Prompt p2 for `lainnya`, relabel, manual vs p1 vs p2 write-up |
| D | `.10.1` | Queue-risk proxy, ranking with confidence, validation plan, screen proposal |
| E | `.10.2` | POI vs traffic analysis (descriptive, n=10), screen proposal |
| F | `.10.4` | AI-summary design doc and a 2-site prototype |
| G | `.5` | Prices from the public pricing pages, README cost table |
| — | `.7.13` | Rain-flag recheck (orchestrator) |

Live writes and deploys (BigQuery UPDATE, Cloud Run deploys, scheduler changes) are run by the orchestrator after review. Workers stop at dry runs.

## File ownership

| Path | Track |
|---|---|
| `collector/reroute.py`, `tests/test_collector_reroute.py`, `scripts/backfill_rerouted.py`, `tests/test_backfill_rerouted.py`, `docs/plans/collector.md` (reroute section) | A |
| `dashboard/api/**`, `dashboard/web/src/**` (fetch/loading only), `scripts/deploy_dashboard.sh`, `tests/test_dashboard_*.py` | B |
| `reviews_job/gemini.py`, `tests/test_reviews_*.py` (label tests), `docs/plans/complaints-analysis.md`, `docs/plans/review-labels.md` | C |
| `docs/plans/queue-risk.md` | D |
| `docs/plans/poi-analysis.md` | E |
| `docs/plans/ai-summaries.md`, `scripts/ai_summary_prototype.py` | F |
| `README.md` (cost table only) | G |
| `docs/plans/data-schema.md`, this file, everything else | orchestrator |

Gate: `scripts/build-and-test.sh` green, then `advisor-reviewer`, then deploys.

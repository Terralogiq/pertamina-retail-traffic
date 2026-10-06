# Handoff — 2026-10-06 — (no git yet)

## Request
Pertamina wants to monitor traffic in front of 10 SPBU (gas stations) using Google data at 30-minute intervals. RMI (Roads Management Insights) was proposed, but Pertamina has no access yet, so the interim source is Routes API called on a schedule. Terralogiq is building a demo dashboard: traffic plus weather, Places-based site profiling (POIs, competitors, reviews), and anything else valuable. This session: research how to do it, settle the data design, and bring the repo in line with `~/Dev/terralogiq-claude-harness-workflow.md`.

## Done
- Deep research (workflow run `wf_b36393f3-b4a`, 104 agents, 23 claims confirmed). Key verified facts:
  - Routes API must set `routingPreference: TRAFFIC_AWARE`. The default `TRAFFIC_UNAWARE` gives duration == staticDuration, so no traffic signal.
  - Congestion index = `duration / staticDuration`. This is an inference, not a metric Google documents. Durations are whole seconds, so very short segments are noisy.
  - `speedReadingIntervals` (NORMAL/SLOW/TRAFFIC_JAM) needs `extraComputations: TRAFFIC_ON_POLYLINE`. It is filled at route and leg level only, and it bills at the Enterprise tier.
  - Pricing, checked 2026-10-06:
    - Compute Routes Pro: $10/1k after 5k free a month.
    - Compute Routes Enterprise: $15/1k after 1k free.
    - 10 sites × 48 calls/day ≈ 14,400 calls/month ≈ $94 at Pro.
    - 2 directions per site ≈ 28,800 calls ≈ $238 at Pro.
  - Use `computeRoutes`, not `computeRouteMatrix`: a matrix computes every origin × destination combination, which wastes billed elements on independent pairs.
  - No backfill: a past departureTime is only allowed for transit. History starts when the scheduler starts.
  - RMI is contract-gated and aimed at public-sector bodies and road operators. It only covers the customer's managed territory and can reject routes as `LOW_ROAD_USAGE` or `OUTSIDE_JURISDICTION`. It delivers data every 2 minutes over Pub/Sub, or every 10 minutes into BigQuery.
  - Additional pricing, from direct fetches the research workflow did not verify:
    - Weather API: $0.15/1k after 10k free. This looks low; recheck in the console.
    - Air Quality: $5/1k.
    - Nearby Search: Pro $32, Enterprise $35, Enterprise + Atmosphere $40 per 1k.
    - Place Details with reviews (Enterprise + Atmosphere): $25/1k.
    - Places Aggregate: $10/1k after 5k free. Returns place IDs only when the count is ≤100.
  - Places: only `place_id` may be stored long-term. Reviews need author attribution and a Google Maps link. Places content shown without a map needs the Google Maps logo or text.
  - Popular times is not available in any official API.
- Data schema written: `docs/plans/data-schema.md`. It has BigQuery DDL for `sites`, `routes`, `traffic_snapshots` and `weather_slots`.
- Harness files created (templates copied from `~/Dev/days-chat`, because `harness-templates/` does not exist anywhere under home). Checked with `bd setup claude --check`: it confirms the plugin hooks are in place and only reports the missing Beads section in CLAUDE.md.

## In progress
- Git and Beads init. The user said "done both", but `/Users/farry/Dev/pertamina-retail-traffic` still had no `.git` and no `.beads` when this handoff was written. Next step: run, or ask the user to run:
  `git init && bd init && bd setup claude && bd setup claude --check`
  Once Beads exists, move this handoff into a bead (`bd create`).

## Not started
- `/plan` for the first feature: the collector (Cloud Scheduler `*/30` Asia/Jakarta → Cloud Run job → Routes + Weather → BigQuery).
- The Places test fetch for the 10 SPBU: Text Search for the SPBU itself, Place Details with reviews, Nearby Search for `gas_station` competitors within 1–3 km, and Places Aggregate POI counts at 500 m / 1 km / 3 km. Output: JSON samples plus field fill-rate for Indonesia.
- The dashboard frontend.
- `scripts/build-and-test.sh`, the Build & test entry point. It is created with the first code slice.

## Files changed
| Path (from repo root) | Change |
|---|---|
| `CLAUDE.md` | New thin router: project summary, rules table, Build & test placeholder, workflow, conventions |
| `README.md` | New; tool versions (Claude Code 2.1.291, bd 1.3.1) |
| `.gitignore` | New; includes `.claude/worktrees/`, `.env`, `settings.local.json` |
| `.claude/settings.json` | New: plansDirectory, agent teams off, Stop hook, beads plugin (`beads@beads-marketplace`) |
| `.claude/hooks/build-and-test.sh` | New Stop hook; skips when there is no git, no changes, or no `scripts/build-and-test.sh` |
| `.claude/agents/advisor-reviewer.md` | New, from days-chat; the project-rules check points at `data-sources.md` |
| `.claude/rules/data-sources.md` | New: demo vs production sources, core / `demo_*` / `raw` columns, Places storage and attribution rules, Google basemap only |
| `docs/plans/data-schema.md` | New: BigQuery DDL |

## Decisions
- **Routes API output is cached in BigQuery as a "pretend RMI" feed.** RMI comes with a license to cache traffic data once Google approves it, so the Routes caching limit is accepted for the demo. Don't re-raise it.
- **Weather is cached per 30-minute slot** as a stand-in for WeatherNext (Earth Engine) later.
- **Every table has core + `demo_*` + `raw` JSON columns.** Core columns match RMI or WeatherNext. `demo_*` keeps features only available now (reroute check, condition text and icon, thunderstorm probability, feels-like, UV, visibility). `raw` keeps the full response. Dashboard widgets that use `demo_*` get a visible "demo-only" label.
- **`speed_kmh`** is computed from `routes.expected_distance_m`, not from the per-call distance, so it stays a core metric that works on RMI data too.
- **2 segments per SPBU** (one per direction) at the Pro tier. `TRAFFIC_ON_POLYLINE` is optional.
- **Recommended frontend:** a custom app (Maps JS + charts reading BigQuery, live Places panels). Looker Studio can't make live Places calls with the required review attribution. Not final.
- **Settings use the marketplace name `beads-marketplace`** (the name actually installed), not `beads` as written in the workflow doc.

## Problems
- **`harness-templates/` is missing**, even though the workflow doc refers to it. Templates were copied from days-chat instead. Unresolved: tell the user the doc's path is wrong.
- **Git and Beads were not found** after the user said they had set them up. Unresolved.
- **GCP project `gcp-coe-492507` has no Maps APIs enabled.** The user will set up the environment. Unresolved: which project to use.

## Next session
1. Confirm `.git` and `.beads` exist in the repo. If not, run the init commands above. Then file this handoff as a bead.
2. Get from the user: the 10 SPBU (numbers or coordinates, main-road name and side of road) and the GCP project ID with Maps APIs enabled.
3. `/plan` the collector → `docs/plans/collector.md`, with a file-ownership table → Beads epic, features and tasks.
4. Run the Places test fetch once the SPBU list and project are ready.

Read first:
- `.claude/rules/data-sources.md`: the binding demo vs production rules.
- `docs/plans/data-schema.md`: the table design.

Watch out:
- Check RMI's BigQuery export field names and WeatherNext's variable list before the first ingest (TODO in data-schema.md).
- Pin each segment's waypoints with a `heading` so the router stays on the correct carriageway.
- Start collecting early. There is no backfill.
- The full research output (sources, refuted claims) is session-scoped scratch and will not survive. The facts above are the durable copy.

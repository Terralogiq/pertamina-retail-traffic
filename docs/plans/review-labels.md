# Review labels: table, validation, Gemini labeller, Review themes panel

Bead `.10.5` follow-up. User decisions 2026-10-10: (1) Indonesian-speaker validation of a stratified 100, (2) add `place_review_labels`, (3) Gemini labeller after `.10.13`, (4) "Review themes" dashboard panel. Taxonomy, sentiment rules and the sampling caveat: `docs/plans/complaints-analysis.md`.

## Constraints

- Review text never leaves `out/` (git-ignored) and is never committed. The labels table holds labels and a masked English gist, not text.
- Never print `gemini-api-key`, `maps-api-key` or other secrets.
- Every `bq`/`gcloud` call passes `--project gcp-coe-sandbox` (and `--billing-project gcp-coe-sandbox` where it applies).
- Places ToS limits are waived (`.claude/rules/data-sources.md`). The panel is demo-only because its data comes from Places review windows, not RMI-compatible core columns.

## Phases

### 1. `place_review_labels` table and manual load (bead `.10.5.1`)

DDL as proposed in `complaints-analysis.md` ("Proposed table"), appended to the review section of `sql/ddl.sql`:

`review_key STRING NOT NULL, site_id STRING NOT NULL, labels ARRAY<STRING>, sentiment STRING, praise_only BOOL, gist STRING, method STRING NOT NULL, model_version STRING, labeled_at TIMESTAMP NOT NULL`. Clustered by `site_id`, not partitioned. MERGE key `(review_key, method)`: a rerun with a new taxonomy or model version replaces that method's row.

- `method`: `manual` | `gemini`. `model_version`: `taxonomy_v1` for the manual pass; the pinned Gemini model id plus prompt version (e.g. `gemini-<ver>/p1`) for Gemini.
- Loader `scripts/load_review_labels.py <labels.json>`: reads `out/complaints/<date>/labels.json`, takes `site_id` from `v_place_reviews` by `review_key`, writes one MERGE.
- Document in `docs/plans/data-schema.md` under "Reviews tables" (core + no `raw`; derived table).

Acceptance: `bq_setup.sh` applies the DDL; 127 `manual` rows; rerunning the loader leaves 127; tests for the MERGE SQL and the json→row mapping.

### 2. Validation sample (bead `.10.5.2`)

Stratification: all 71 `neg`/`mixed` reviews (they drive every finding) plus 29 `pos` allocated across sites in proportion to each site's `pos` count, seeded. Output `out/complaints/2026-10-10/validation_sample.csv` with `review_key, site_id, rating, text, labels, sentiment, corrected_labels, corrected_sentiment, notes`, and a short `README.md` beside it with the category table and sentiment rules. Script: `scripts/export_validation_sample.py`.

Acceptance: 100 rows, 71 neg/mixed, no author fields. When the reviewer returns it: compute agreement (per-label precision and recall, sentiment agreement) and update Method and Limitations in `complaints-analysis.md` (follow-up bead `.10.5.5`).

### 3. Review themes panel (bead `.10.5.3`, after `.10.5.1`)

- API: `GET /api/sites/{site_id}/review-themes` in a new `dashboard/api/routers/reviews.py`. Per-category count of `neg`/`mixed` labels, split into last 12 months and older (`published_at`), plus `n_text_reviews`, `n_reviews`, and up to 5 recent gists. Reads `place_review_labels` joined with `v_place_reviews`; prefers `gemini` over `manual` per review when both exist. No author fields, no review text.
- Web: `dashboard/web/src/reviews/ReviewThemesPanel.tsx` on the site page, after the Places panel. Counts and n only, no percentages, no cross-site ranking. Badge: "demo-only · sampled, n ≤ 15 per window". No link to queue risk until `.10.1` exists.
- Tests: pytest for the router/SQL, vitest for the panel.

Acceptance: build-and-test green; panel renders for all 10 sites (browser check, then delete `.playwright-mcp/`). Deploy is run by the user (`! scripts/deploy_dashboard.sh --default-sa`).

### 4. Gemini labeller (bead `.10.5.4`, after `.10.13` and `.10.5.1`)

- `reviews_job` gains `--mode label`: reads `v_place_reviews` rows with text and no `gemini` row at the current `model_version`, calls the Gemini API (JSON output constrained to the taxonomy), MERGEs into `place_review_labels`. Key from Secret Manager `gemini-api-key` in `gcp-coe-492507` (projects/14729129282/secrets/gemini-api-key:latest); the gcp-coe-sandbox default compute SA has secretAccessor on it (2026-10-10). Key verified with models.list (gemini-2.5-flash available).
- Scheduler `reviews-poller-label` at `30 6 * * *` Asia/Jakarta, after the 06:00 newest run.
- Pinned model id; prompt holds the category table and the decision rules from `complaints-analysis.md` Method.
- Compare with the `manual` labels and with the validation set once it is back.

Acceptance: one live run labels all unlabelled text reviews; rerun is a no-op; tests with a stubbed Gemini client.

## File ownership

| Phase | Bead | Owns |
|---|---|---|
| 1 | `.10.5.1` | `sql/ddl.sql` (review section), `docs/plans/data-schema.md` (Reviews tables), `scripts/load_review_labels.py`, `tests/test_load_review_labels.py`, `tests/test_reviews_job.py` (view test slice) |
| 2 | `.10.5.2` | `scripts/export_validation_sample.py`, `tests/test_export_validation_sample.py`, `out/complaints/2026-10-10/` |
| 3 | `.10.5.3` | `dashboard/api/routers/reviews.py`, `dashboard/api/main.py` (router include), `dashboard/web/src/reviews/`, site page mount point, `tests/dashboard/test_reviews*.py` |
| 4 | `.10.5.4` | `reviews_job/` (label mode, gemini client), `scripts/deploy_reviews_job.sh`, `tests/reviews_job/test_label*.py` |

Phases 1 and 2 can run in parallel. 3 and 4 both read the table from 1 and do not share files.

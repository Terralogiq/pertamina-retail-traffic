# Dashboard redesign: UI/UX review and Pertamina Retail branding

Bead: `pertamina-retail-traffic-907.9` (feature). Builds on `docs/plans/dashboard.md`, which covers the functional scope; this plan changes presentation only. Rules: `.claude/rules/data-sources.md`. Tooling: the `impeccable` skill for critique, audit, design and polish.

## Goal

Make the dashboard look and read like a Pertamina Retail product, with the logo, colours and type, and fix the UX problems a structured review finds. The data, the API and what each screen shows stay the same. The demo-only labels, the "baseline building" state and the Google basemap stay; they get designed rather than bolted on.

## Starting point (2026-10-07)

- No stylesheet, no design tokens, no assets. Styling is 46 inline `style={{…}}` blocks across 14 components in `dashboard/web/src/`.
- Screens: overview (map + side list), site detail (map, traffic charts, heatmap, weather, Places), traffic vs rain, login.
- Charts: ECharts with default colours. Map: Maps JS with `DEMO_MAP_ID`, which allows no cloud styling.
- Colour already carries meaning: congestion and speed bands (green / amber / orange / red / grey) and the demo-only badge.

## Inputs needed before design starts

| Input | Source | Status |
|---|---|---|
| Pertamina Retail logo: SVG preferred, plus a light and a dark variant if they exist | From the user or the client (official file). Not traced or redrawn from a screenshot | **Needed** |
| Brand colours as exact hex values | Pertamina brand guideline, or values sampled from the official SVG. The logo is red, blue and green; the exact values must not be guessed | **Needed** |
| Brand typeface, and whether it's licensed for web | Brand guideline; fall back to a close Google Font if not | Unknown |
| Map styling | A cloud Map ID with a style in `gcp-coe-sandbox`, replacing `DEMO_MAP_ID` | To create in `.9.4` |

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Review environment | Local: `vite dev` on `localhost:5173` plus `uvicorn` on `:8080`, reading real BigQuery via ADC, with a throwaway local `DASHBOARD_PASSWORD`. `MAPS_BROWSER_KEY` already allows `localhost:5173`. Delete `.playwright-mcp/` after each browser session | A browser login on the live URL would put the real password or a 7-day cookie in the transcript |
| Styling system | One `src/theme/tokens.css` (CSS custom properties: colour, type scale, spacing, radius, shadow) and plain CSS modules per component. The inline styles are replaced, not wrapped. No CSS framework | Smallest change that gives one source of truth; no new runtime dependency |
| Brand vs data colour | Brand colours go to chrome: header, navigation, buttons, focus, logo. Data colours (congestion bands, chart series) stay a separate, validated palette. They must pass contrast and colour-blind checks and must not reuse brand red for "jam" unless it tests clearly | Brand red as both "Pertamina" and "congested" would blur meaning |
| Charts | One shared ECharts theme built from the tokens, registered once | Today each chart sets its own colours |
| Map | Cloud Map ID with a muted basemap style so the coloured legs stand out; markers in brand colours | Google basemap rule stays (`data-sources.md`) |
| Demo-only badge | Kept on the same widgets; redesigned as one consistent component | Labels decision in `dashboard.md` is unchanged |
| Language | English copy stays. Copy is reviewed for clarity, e.g. "congestion index" explained on first use | Language decision in `dashboard.md` |
| Scope guard | No new endpoints, metrics or screens. A new widget the review asks for becomes a bead | Keeps the redesign reviewable |

## Phases

### Phase 1: review (`.9.1`)

- Run `impeccable` critique and audit against every screen on the local build, at 1440 px and 390 px. Cover:
  - visual hierarchy, information architecture and cognitive load;
  - accessibility: contrast, focus order, keyboard, colour-only meaning;
  - empty, loading and error states, including baseline pending and no Places run;
  - responsive behaviour;
  - chart legibility;
  - map readability.
- Output: `docs/plans/dashboard-ux-review.md`, with findings ranked by severity, a screenshot reference for each, and the fix proposed. Screenshots go to `out/ux-review/` (git-ignored).
- Acceptance: the user reviews the findings and picks which go into Phase 3.

### Phase 2: brand foundation (`.9.2`, needs the logo and colour inputs)

- `src/theme/tokens.css`: brand palette, neutrals, the data palette (bands and series) and the type scale. The data palette passes the dataviz validator (contrast in light and dark, colour-blind distinguishable).
- Logo in `dashboard/web/public/` and favicon.
- ECharts theme from the tokens.
- Acceptance: the user signs off colours and logo use. Done 2026-10-07 through `docs/plans/brand-inputs.md` (Decision) instead of a dev-only token sheet page.

### Phase 3: redesign (`.9.3` app shell + login, `.9.4` map + overview, `.9.5` site detail + charts + Places, `.9.6` traffic vs rain)

- Use `impeccable` design/redesign per screen, using only tokens. Inline styles are removed from the files touched.
- `.9.3`: header with logo, navigation (overview, traffic vs rain), branded login, page layout grid.
- `.9.4`: cloud Map ID and style, brand markers, legend, side list as cards, baseline-pending state.
- `.9.5`: section layout, chart theme, heatmap palette, weather panel, Places panel (rating, reviews, competitor and POI tables).
- `.9.6`: rain vs dry layout and the demo-flag toggle.
- Acceptance per bead: the review findings mapped to it are fixed; the screens are checked at 1440 px and 390 px; no inline colour or size literals are left in its files.

### Phase 4: polish and verify (`.9.7`)

- Run `impeccable` polish and harden: focus states, motion (reduced-motion respected), empty and error states, number formatting.
- Re-run the Phase 1 audit. Every Phase 3 finding is closed or filed as a bead.
- Deploy (the user runs `deploy_dashboard.sh`), then check the live URL.

## File ownership

| Path | Owner bead | Notes |
|---|---|---|
| `docs/plans/dashboard-ux-review.md`, `out/ux-review/` | `.9.1` ✓ | |
| `src/theme/`, `src/shell/`, `src/weather/DemoBadge.{tsx,css}` (incl. `Widget`), `src/App.tsx`, `src/main.tsx`, `index.html` | `.9.3` | Frozen during the `.9.4`–`.9.6` fan-out. `.9.3` also made small wiring edits in `traffic/Chart.tsx`, `weather/EChart.tsx`, `weather/RainView.tsx`, `weather/WeatherPanel.tsx`, `map/bands.ts`, `map/Overview.tsx` before the fan-out |
| `src/theme/` brand values, `src/theme/Wordmark.tsx`, `dashboard/web/public/` (logo, favicon), `index.html` (favicon, title), `main.tsx` (font import), `src/shell/AppShell.*` (footer credit, logo sizing), `src/login/Login.css`, `tests/test_dashboard_static.py` | `.9.2` | Brand values, wordmark, favicon, Epilogue font and the "by Terralogiq" footer, per the brand-inputs Decision |
| `src/map/` | `.9.4` | Map ID through `/api/config`: one line in `dashboard/api/routers/sites.py` and a step in `scripts/deploy_dashboard.sh`. Adds `legBand()` in `map/bands.ts` for `.9.5` |
| `src/site/`, `src/traffic/`, `src/weather/{WeatherPanel,EChart,SiteWeather}.tsx`, `src/places/` | `.9.5` | |
| `src/weather/RainView.tsx` | `.9.6` | |
| `src/shell/` site picker (`SitePicker.tsx`, `AppShell.*`), `src/map/api.ts` (shared `getSites`), `src/weather/RainView.tsx` (filter label) | `.9.9` | After the fan-out |
| `src/site/{useSiteData.ts,SiteDetail.tsx,site.test.tsx}` | `.9.12` | |
| `src/places/*`, `src/theme/tokens.css` (`--rating-star`) | `.9.13` | |
| Cross-cutting polish: `src/api.ts`, `src/theme/tokens.css` (reduced motion), `src/map/*`, `src/site/SiteDetail.tsx`, `src/weather/{RainView,WeatherPanel}.tsx`, `src/places/PlacesPanel.tsx`, `src/login/Login.tsx`, `dashboard/api/main.py` (font MIME), `tests/test_dashboard_static.py` | `.9.7` | After `.9.2`–`.9.6`; nothing runs in parallel with it |
| `README.md`, `docs/plans/*.md` (other than the review doc) | orchestrator | |

## Contract for `.9.4`–`.9.6` (from the `.9.3` review)

1. Frozen: `src/theme/*`, `src/shell/*`, `src/weather/DemoBadge.*`, `main.tsx`, `index.html`, `App.tsx`. A missing token, shared class or card change goes to the orchestrator, not into a local copy.
2. `App.tsx` maps routes only. Each screen renders its own `<Page title context actions>`: page notices (baseline building) go in `context`, controls in `actions`.
3. Colours: bands via `BANDS`, `BandIndicator` or `var(--band-*)`; every chart series sets its colour from `SERIES`; heatmaps use `SEQUENTIAL` / `--seq-*`; no hex or size literals in screen files.
4. `.9.4` adds `legBand(latest) → { band, basis }` in `src/map/bands.ts`; `.9.5` imports it.
5. Demo labelling per section: one `<DemoNote>` plus a `<DemoMarker>` on each demo value, or `<Widget demo>` per card, not both. A `DemoMarker` never stands alone.
6. `import "./theme/tokens.css"` stays first in `main.tsx`.
7. `--ink-3` text only on `--surface-1` (on `--surface-page` it is below AA at 13 px).
8. Shared grid: `.page-grid`, `.span-{4,6,8,12}`; screen layout goes in the screen's own CSS file.
9. No dual-axis charts (`dataviz` rule): `.9.5` moves the rain bars from `.4.9` into a small chart under the traffic series, on the same time axis.

Order (re-sequenced 2026-10-07: layout starts before the brand inputs arrive; review findings in `docs/plans/dashboard-ux-review.md`, all 21 in scope):
1. `.9.1` ✓.
2. `.9.3`: app shell, navigation and login, plus provisional `src/theme/tokens.css` (neutral chrome, spacing, type scale), the validated data palette (congestion bands, chart series) and the `DemoBadge` design. The data palette is independent of brand colours, so F1, F7, F8 and F10 don't wait for `.9.2`.
3. `.9.4` ∥ `.9.5` ∥ `.9.6`, in worktrees, using the `.9.3` tokens.
4. `.9.2`, once the logo and colours are in: it swaps the brand token values and adds the logo, favicon, font and the footer credit. The only component change is the shell footer.
5. `.9.7`. `.9.8` (F9, slow cold loads) is backend work and runs independently.

## Open questions for the user

- Can you supply the official Pertamina Retail logo (SVG) and the brand guideline? Without them, colours would be sampled from a public logo file and need your sign-off.
- Should the dashboard carry Terralogiq branding too (e.g. "by Terralogiq" in the footer)?
- Dark mode: needed for the demo, or light only?

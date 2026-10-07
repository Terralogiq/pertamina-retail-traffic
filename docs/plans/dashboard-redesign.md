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
- Acceptance: a token sheet page (dev only) shows every token; the user signs off colours and logo use.

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
| `docs/plans/dashboard-ux-review.md`, `out/ux-review/` | `.9.1` | Read-only on code |
| `dashboard/web/src/theme/`, `dashboard/web/public/`, `dashboard/web/index.html`, `src/main.tsx` (stylesheet import) | `.9.2` | |
| `src/App.tsx`, `src/login/`, `src/shell/` (new) | `.9.3` | |
| `src/map/` | `.9.4` | Map ID: new secret or config value through `/api/config` (one line in `dashboard/api/routers/sites.py`, and a step in `scripts/deploy_dashboard.sh`) |
| `src/traffic/`, `src/weather/WeatherPanel.tsx`, `src/weather/EChart.tsx`, `src/places/` | `.9.5` | |
| `src/weather/RainView.tsx`, `src/weather/DemoBadge.tsx` | `.9.6` | `DemoBadge` is used by `.9.5` too: `.9.6` owns it, so do it first or agree the design in `.9.2` |
| `README.md`, `docs/plans/*.md` (other than the review doc) | orchestrator | |

Order:
1. `.9.1`, which can start now.
2. `.9.2`, once the logo and colours are in.
3. `.9.3`.
4. `.9.4` ∥ `.9.5` ∥ `.9.6`, in worktrees; `DemoBadge` is designed in `.9.2`.
5. `.9.7`.

## Open questions for the user

- Can you supply the official Pertamina Retail logo (SVG) and the brand guideline? Without them, colours would be sampled from a public logo file and need your sign-off.
- Should the dashboard carry Terralogiq branding too (e.g. "by Terralogiq" in the footer)?
- Dark mode: needed for the demo, or light only?

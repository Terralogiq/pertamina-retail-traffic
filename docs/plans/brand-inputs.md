# Brand inputs (bead .9.11)

Derived 2026-10-07 from https://pertaminaretail.com/ (homepage, `/news`, one news article) and its three linked stylesheets. No official brand guideline was obtained. Values are labelled **exact** (read from CSS/SVG source), **sampled** (pixel mode of a flat region in a raster) or **derived** (computed by us, not a brand value). Consumers: `dashboard/web/src/theme/tokens.css` `--brand-*` (bead .9.2).

## Assets

`out/brand/` is **gitignored** (`.gitignore:20 out/`). The files below are not tracked; the consumer must copy the chosen ones into the dashboard source tree (no `dashboard/web/public/` exists yet) or decide on tracking. Raw downloads are in `out/brand/raw/` (never executed).

| File in `out/brand/` | Source URL | Notes |
|---|---|---|
| `pertamina-retail-logo.png` | https://pertaminaretail.com/logo/logo.png | Header logo, `<img class="w-40" alt="pertamina-retail-logo">`. 770x202 RGBA, transparent bg. Raster only |
| `pertamina-retail-logo-white.png` | https://pertaminaretail.com/logo/logo-white.png | Footer logo, all-white (39,466 px, all `#FFFFFF`), same size. For dark surfaces |
| `pertamina-retail-favicon.ico` | https://pertaminaretail.com/favicon.ico | 9 sizes 16 to 256 px |
| `pertamina-retail-favicon-256.png` | extracted from the 256 px PNG entry of the `.ico` | Mark only (no wordmark), flat colours, white bg |
| `pertamina-corporate-logo.svg` | https://www.pertamina.com/file/files/2025/02/pertamina-logo.svg | **Corporate** "Pertamina" mark, vector, 174x40, no scripts/links. Only SVG found |
| `pertamina-corporate-logo-white.svg` | https://www.pertamina.com/images/Pertamina-white_Logo.svg | Corporate white variant, vector |

Not found on pertaminaretail.com: an SVG of the Retail logo (tried `/logo/logo.svg`, `/logo.svg`: 404), `og:image`, `apple-touch-icon`, web manifest, `theme-color` meta, robots.txt. Other images seen are not the logo: `/logo/bazma.png` (Bazma, a separate entity's logo), `/icons/pertamina-clean.svg` (whistleblowing icon, circle `#99AF32`).

The Retail wordmark ("PERTAMINA" black, "RETAIL" red, with the red/blue/green mark) exists only as the 770 px PNG. No tracing or redraw was done.

## Colours

The mark has three colours, and three sources disagree:

| Source | Blue | Red | Green | Status |
|---|---|---|---|---|
| Retail header PNG | `#0074FE` | `#FE0018` | `#9FE400` | sampled; oversaturated, matches no other source. Not proposed |
| Retail favicon 256 px | `#005CAB` | `#E1232B` | `#A2CD3A` | sampled (large flat areas). Blue equals the CSS literal below |
| Corporate SVG fills | `#006CB8` | `#ED1B2F` | `#ACC42A` | exact (vector) but a different rendition; wordmark `#082313` |

Retail-site CSS (`/_next/static/css/362b2fd113bc1d78.css`):

| Hex | Role | Where found | on white | on `--surface-page` `#f4f5f7` | Text use |
|---|---|---|---|---|---|
| `#005CAB` | **primary blue** (exact) | utilities `bg-/text-[#005CAB]`, scrollbar thumb; **not observed on any fetched page**, so defined but unproven in UI | 6.73 | 6.17 | text 13-16 px, white-on-it 6.73 |
| `#32599C` | secondary blue (exact) | `from-[#32599C]` hero gradient overlay on `/news` | 6.90 | 6.32 | text OK; graphic in practice |
| `#E1232B` | brand red (**sampled**, favicon) | logo mark; "RETAIL" text (PNG, mean `#ED081B`, noisy) | 4.69 | 4.30 | text on white only; on page bg large/graphic (>=3) |
| `#63AE1D` | **brand green** (exact) | `green-light`: `bg-`, `text-`, `border-`, `stroke-`, outline; primary buttons, section `h2`, hover fills | 2.76 | 2.53 | **fails 3:1**; graphic only. White-on-green 2.76 fails (the site does it anyway). `#171717` on it 6.49 |
| `#1AAC29` | accent green (exact) | `.banner-pagination ... b` progress bar | 3.01 | 2.76 | large/graphic only |
| `#80DC2B` | accent green (exact) | inline `style` on homepage | n/a | n/a | not used for text |
| `#171717` | neutral, footer bg | `bg-[#171717]` on `<footer>` | 17.93 | 16.43 | text; white-on-it 17.93 |
| `#262626` | neutral, body text | `html{color:#262626}` | 15.13 | 13.87 | text |
| `#EAEAEA` `#F2F2F2` `#A6B0A7` `#9CA9B1` | neutrals (exact) | borders/panels; `#A6B0A7` is a grey-green button bg | n/a | n/a | not for text |
| `#040A28D1` | navy overlay (exact) | `bg-[#040A28D1]` | n/a | n/a | overlay only |
| `#0078A8`, `#007AFF` | library defaults (Leaflet link, Swiper) | not brand | n/a | n/a | ignore |

Site chrome itself: white header (`bg-white text-black`, 80 px, bottom border), dark `#171717` footer, green buttons. A blue header in the dashboard would be a dashboard choice, not a mirror of the site. shadcn defaults (`--primary: 0 0% 9%`, greyscale) are present and unbranded.

## Typeface

- `html{font-size:14px;font-family:Epilogue,sans-serif!important;color:#262626}` in the same CSS file.
- Loaded via `@import` of Google Fonts `Epilogue:ital,wght@0,100..900;1,100..900` (variable). Also `Kalam` 300/400/700 (a handwriting display face; not proposed for the dashboard).
- Not self-hosted and not a licensed commercial face. Epilogue is open source (SIL OFL), free for web use and self-hostable via `@fontsource-variable/epilogue`, so licensing is not an issue and no substitute is needed. Adding it is a dependency/asset decision for .9.2. Fallback stack stays `--font-sans` in `tokens.css`.
- It is the site's face, not a documented brand typeface. The corporate wordmark lettering is not a font and is not available as one.

## Contrast: collisions with the data palette

- Brand red hue 357 vs jam band `#a51d2d` hue 353: the same hue family (inter-colour contrast only 1.59). Heavy `#e0602a` is hue 18. The plan's rule stands: brand red stays in the logo; do not use it as chrome accent, error or selection colour anywhere near the congestion legend or map legs.
- Brand blue (hue 208) and brand green (hue 91) are far from the jam/heavy hues. Green may sit near a "free-flow" band if the data palette uses green: check colour-blind separation in the .9.3 palette validation before using brand green on the map.
- Existing `--state-error` `#b3261e` is also red; unchanged, out of scope.

## Recommended mapping for `tokens.css` (proposal)

| Token | Value | Provenance | Why |
|---|---|---|---|
| `--brand-primary` | `#005CAB` | exact (CSS) + sampled (favicon) agree | 6.73 white, 6.17 on page; text-capable; buttons, header, links |
| `--brand-primary-hover` | `#004A8C` | **derived** | 8.91 white, 8.16 page |
| `--brand-on-primary` | `#ffffff` | n/a | 6.73 on primary |
| `--brand-secondary` | `#32599C` | exact (CSS gradient) | 6.90 / 6.32; keeps `a{color:var(--brand-secondary)}` legible. Or reuse `#005CAB` if two near-identical blues is unwanted (hue 208 vs 218) |
| `--brand-accent` | `#63AE1D` | exact (CSS `green-light`) | **non-text only** (markers, rules, focus fills, logo mark). Text-capable green, if wanted: `#3F7D0F` (**derived**, 5.06 white, 4.64 page) |
| brand red `#E1232B` | no token | sampled | logo only; do not add to chrome tokens |

`--focus-ring` and `--selection` already derive from `--brand-primary`; no further change. Surfaces and ink tokens need no change (primary on `--surface-2` `#eef0f3` 5.90, on `--surface-sunken` `#e6e9ed` 5.53).

## Open questions and risks

1. **Which mark.** The Retail logo ("PERTAMINA RETAIL", PNG only) is the right mark for a Pertamina Retail SPBU dashboard, but only a raster exists. The corporate "Pertamina" SVG is vector and has exact fills but is a different brand tier. Client to say which is wanted and supply the official Retail SVG.
2. **Colour disagreement.** Favicon/CSS (`#005CAB`/`#E1232B`/`#A2CD3A`) vs corporate SVG (`#006CB8`/`#ED1B2F`/`#ACC42A`). Red and green in the proposal are sampled, not exact. Needs the guideline or the official SVG to settle.
3. **Colours are from the website, not a guideline.** `#005CAB` is defined in CSS but unseen on pages fetched; the site's visible accent is green, and its green button text fails contrast.
4. **Licensing.** Logos are Pertamina trademarks scraped from public sites for a Pertamina demo. Written permission or an official asset pack is not on file. A staging API host (`api-stagingweb.pertaminaretail.com`) serves the site's images: not used.
5. **Raster logo quality.** 770x202 with soft anti-aliased edges. Fine at header size (about 160 px), not for retina large or print. White variant is pre-made.
6. **Not checked:** other site pages (only home, `/news`, one article; `/about-us` and `/products` are 404), the live rendered DOM (static HTML and CSS only), dark-mode styles.

## Decision (user sign-off, 2026-10-07)

- **Logo:** Pertamina Retail header PNG (`out/brand/pertamina-retail-logo.png`) in a white header; white variant unused for now. Ask the client for an official SVG later.
- **Colours:** `--brand-primary` `#005CAB`, `--brand-primary-hover` `#004A8C`, `--brand-secondary` `#32599C`, `--brand-accent` `#63AE1D` (graphic only; text green `#3F7D0F`). Brand red stays in the logo only.
- **Type:** Epilogue variable (SIL OFL), self-hosted via `@fontsource-variable/epilogue`.
- **Credit and theme:** small "by Terralogiq" in the footer; light theme only.
- **Favicon:** from `out/brand/pertamina-retail-favicon-256.png` / `.ico`.

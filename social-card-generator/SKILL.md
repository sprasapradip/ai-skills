---
name: social-card-generator
description: >-
  Generates production-ready OpenGraph/Twitter (X)/LinkedIn preview images, GitHub social-preview
  and README banners, and square feed cards as accessible SVG with verified PNG exports. Supports
  Starter (single themed card), Pro (brand palette, auto-fit typography, retina PNG, meta-tag
  snippet) and Enterprise (batch generation from a manifest, per-locale variants, CI validation).
  Use when the user says "create an OG social card", "generate a GitHub banner image",
  "build an SVG preview card", "make a Twitter/LinkedIn share image", "repo social preview",
  "blog post thumbnail", or "og:image for my site".
version: 2.0.0
tier: premium
author: Pradip Subedi (@sprasapradip)
homepage: https://github.com/sprasapradip/ai-skills
---

# Social Card Generator (Premium)

## 1. System Role & Objective

You are a **senior brand designer and front-end engineer** specialising in share imagery. You
understand platform crop behaviour, text legibility at thumbnail scale, SVG security and
rasterisation pipelines.

**Objective:** produce a card that reads clearly at 400 px wide, passes WCAG contrast, respects
platform safe zones, and is delivered as a validated SVG source **plus** a PNG. Social platforms
do not accept SVG for `og:image`.

## 2. Mode Selection

| Capability | Starter | Pro (default) | Enterprise |
|---|---|---|---|
| Output | 1 SVG + 1 PNG (1×) | SVG + PNG 1× and 2× | Batch: N cards from `cards.json`, consistent naming `slug-size.png` |
| Theme | Built-in theme (`midnight`, `ocean`, `forest`, `sunset`, `light`, `mono`) | Custom brand `--bg1/--bg2/--fg/--accent`, contrast-gated | Brand tokens file + per-locale variants (RTL-aware) |
| Sizes | `og` 1200×630 | + `github` 1280×640, `square` 1080×1080 | All sizes per card |
| Extras | none | HTML `<meta>` snippet (OG + Twitter) with `og:image:alt` | CI script: render → validate → rasterise → size-check, non-zero exit on any failure |

**Selection rule:** use the tier the user names. One card for one page means Starter. A brand or
product launch means Pro. A blog, docs site or many repos means Enterprise. Announce the tier in
one line.

## 3. Pre-Flight Validation

### 3.1 Input schema

| Field | Required | Rule | Fallback |
|---|---|---|---|
| `title` | **Blocking** | ≤ 90 chars (≤ 60 ideal) | Use the page/repo name; ask only if none exists |
| `subtitle` | No | ≤ 160 chars (≤ 100 ideal) | Use the repo description or meta description; else omit |
| `badge` | No | ≤ 24 chars, rendered uppercase | Category from context (`OPEN SOURCE`, `GUIDE`, `RELEASE v2.0`) |
| `handle` | No | ≤ 40 chars | `@owner` from the repo URL |
| `url` | No | ≤ 60 chars, no scheme | Domain or `github.com/owner/repo` |
| `theme` / colours | No | Hex only; contrast-gated | `midnight` |
| `size` | No | `og` \| `github` \| `square` | `og` (also valid for X `summary_large_image` and LinkedIn) |
| `alt` | Yes | Describes the card for `og:image:alt` | `title. subtitle` |

### 3.2 Edge cases

- **Title too long:** the renderer shrinks it from 76 to 44 px, wraps it to ≤ 3 lines, then
  shrinks the subtitle. Ellipsis truncation is a last resort and fails under `--strict`.
  Recommend a shorter title instead.
- **Brand colours fail contrast:** the renderer refuses to write the card. Adjust lightness, keep
  the hue, and re-run. Report the adjustment.
- **Non-Latin scripts / CJK:** width estimation is conservative (1 em for full-width glyphs). Make
  sure the rasteriser has a matching font (`fonts-noto`, `fonts-noto-cjk`). For RTL, mirror the
  layout (`text-anchor="end"`, x = width − padding).
- **Emoji:** avoid them in titles because rendering differs by platform. If the user insists,
  rasterise with Chromium (colour emoji support).
- **Logo supplied:** embed it as an inline `<path>` or a `data:` URI. Remote `href` fails
  validation because rasterisers and GitHub will not fetch it.
- **No renderer available for PNG:** deliver the validated SVG and state the exact command for the
  user's machine (`rsvg-convert -w 1200 -h 630 card.svg -o card.png`).
- **Caching:** platforms cache OG images. Tell the user to version the filename (`og-v2.png`) when
  replacing a card.

## 4. Core Execution Workflow

1. **Extract metadata** from the user input, repo or page per §3.1, and write it to `card.json`
   (Pro/Enterprise).
2. **Render the SVG**
   `python3 scripts/render_card.py --config card.json -o dist/card-og.svg --strict`
   or with flags: `--title … --subtitle … --badge … --handle … --url … --theme ocean --size og`.
3. **Validate the SVG:** `python3 scripts/validate_svg.py dist/card-og.svg --size og`.
4. **Rasterise:** `sh scripts/svg_to_png.sh dist/card-og.svg dist/card-og.png 1` (and `2` for
   retina on Pro+). The script picks rsvg-convert → Inkscape → headless Chromium and verifies the
   PNG dimensions and the 5 MB limit.
5. **Visually inspect** the PNG. Check that there is no clipped text and no overlap between
   title, subtitle and footer, and that the title is legible at 25% zoom.
6. **Meta snippet (Pro+):**
   ```html
   <meta property="og:image" content="https://example.org/og-v1.png">
   <meta property="og:image:width" content="1200">
   <meta property="og:image:height" content="630">
   <meta property="og:image:alt" content="…same as SVG <title>…">
   <meta name="twitter:card" content="summary_large_image">
   ```
   Replace the host with the user's real absolute `https://` URL, and never leave `example.org` in
   delivered markup.
7. **Enterprise batch:** loop over the manifest with a POSIX shell or Python stdlib driver. Stop
   at the first failure and print a summary table (card, size, KB, status).

## 5. Design System & Production Aesthetics

- **Grid and safe zone:** 80 px padding on all sides. All critical content sits inside the central
  safe area, because LinkedIn and X may centre-crop to roughly 1.91:1 and GitHub to 2:1.
- **Hierarchy (max 4 levels):** badge (20 px, 700, +0.12em tracking, accent on a 14% accent pill)
  → title (44–76 px, 800, −1 px tracking, ≤ 3 lines) → subtitle (24–32 px, 500, 82% opacity,
  ≤ 2 lines) → footer (handle with an initial mark, and a monospace URL in the accent colour).
- **Colour:** a two-stop 135° gradient. Text contrast ≥ **4.5:1 against both stops**, including
  the subtitle after opacity blending, and badge/URL accent ≥ 4.5:1. Glow and grid decoration
  stay at ≤ 22% opacity and never sit behind text at a level that lowers contrast.
- **Typography:** the stack `Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`
  always ends in a generic family. Use at most two families (sans + mono).
- **Light/dark:** provide the `light` theme for platforms or sites with light UIs and a dark theme
  for the rest. Pro+ can export both (`-light`/`-dark` suffixes).
- **Accessibility:** the root `<svg role="img" aria-labelledby>` has a `<title>` as its first
  child, real `<text>` (not outlined paths) for searchability, and `og:image:alt` mirroring the
  title.
- **Weight:** SVG ≤ 1 MB (typically < 5 KB). PNG ≤ 5 MB (X limit). Aim for < 1 MB for fast unfurls.

## 6. Zero-Dependency Automation Scripts

| Script | Purpose | Usage |
|---|---|---|
| `scripts/render_card.py` | SVG renderer: themes, auto-fit + vertical fit, XML escaping, contrast gate on both gradient stops, length warnings | `python3 scripts/render_card.py --title "…" -o card.svg [--theme] [--size og\|github\|square] [--config card.json] [--strict]` |
| `scripts/validate_svg.py` | Rejects DTD/ENTITY (XXE), `<script>`, `on*` handlers, `foreignObject`, remote hrefs; checks size/viewBox, `<title>`, safe zone (transform-aware), font fallbacks, weight | `python3 scripts/validate_svg.py card.svg --size og [--json]` |
| `scripts/svg_to_png.sh` | POSIX shell rasteriser: rsvg-convert → Inkscape → chrome-headless-shell → Chrome (with stdlib PNG crop fix), verifies PNG signature, dimensions and size | `sh scripts/svg_to_png.sh card.svg card.png [1\|2]` |

Exit codes: `0` ok, `1` quality gate failed, `2` usage/IO error or no renderer.

## 7. Negative Constraints (NEVER)

- **Never** reference an SVG as `og:image` or `twitter:image`. Always ship PNG (or JPEG) with
  absolute `https://` URLs.
- **Never** embed `<script>`, event handlers, `<foreignObject>`, external fonts via `@import`, or
  remote images.
- **Never** put text outside the safe zone, below 20 px at 1200 width, or below 4.5:1 contrast.
- **Never** use more than 4 text elements, 2 font families or 1 accent colour on a card.
- **Never** use stock gradients that clash with the user's brand when brand colours are provided.
- **Never** fabricate logos, trademarks, star counts, download numbers or "#1" claims.
- **Never** deliver without opening and inspecting the rendered PNG at least once.
- **Never** add filler commentary. Deliver the files, the commands run, and the gate results.

## 8. Production Checklist & Quality Gates

1. `render_card.py` exits `0` (contrast gate passed; under `--strict`, no truncation).
2. `validate_svg.py --size <size>` exits `0` with no safe-zone warnings.
3. `svg_to_png.sh` exits `0`, and the PNG dimensions equal the target × scale.
4. **Visual QA:** no overlap or clipping, the title is readable at a 300 px thumbnail, and there
   is balanced negative space.
5. **Copy QA:** title ≤ 60 chars ideal. No trailing punctuation in the title. Brand names are
   spelled exactly as the user wrote them.
6. **Meta QA (Pro+):** absolute URLs, width/height/alt tags present, filename versioned.

**Delivery format:** a one-line tier statement, the file list (`.svg`, `.png`, `@2x.png`), the
three gate result lines, the meta snippet (Pro+), and any adjustments made (colour lightness,
title shortening).

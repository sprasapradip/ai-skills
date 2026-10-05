---
name: pdf-maker
description: >-
  Compiles Markdown, structured JSON or plain text into styled, publication-ready PDFs (reports,
  proposals, invoices-as-documents, handbooks, CVs) in three tiers: Starter (zero-dependency
  standard-library engine), Pro (fpdf2 / reportlab with embedded Unicode fonts, images, TOC) and
  Enterprise (WeasyPrint HTML/CSS pipeline with PDF/A or PDF/UA tagging, branding, metadata).
  Every output is verified offline. Use when the user says "generate a PDF report", "convert
  markdown to PDF", "create a formatted PDF document", "export this as PDF", "make a printable
  document", or "turn these notes into a PDF".
version: 2.0.0
tier: premium
---

# PDF Maker (Premium)

## 1. System Role & Objective

You are a **senior document engineer and print typographer**. You know the PDF object model, font
embedding and encodings, pagination, accessible (tagged) PDF and archival standards.

**Objective:** produce a PDF whose content matches the source exactly, with professional
typography, correct pagination, metadata and navigation. It must pass `scripts/verify_pdf.py`
before delivery.

## 2. Mode Selection

| Capability | Starter | Pro (default when deps are allowed) | Enterprise |
|---|---|---|---|
| Engine | `scripts/md_to_pdf.py` (stdlib only) | `fpdf2` (preferred) or `reportlab` | `weasyprint` (HTML + print CSS) |
| Fonts / scripts | Base-14 Helvetica/Courier; Latin-1/cp1252 only | Embedded TTF (Inter/Noto) covering any script, including Devanagari, CJK and Arabic | Same as Pro + `@font-face` subsetting, OpenType features |
| Content | Headings, paragraphs, lists, task lists, tables, code, quotes, links, page breaks | + images, cover page, TOC with page numbers, footnotes | + cover/branding, running headers from `string-set`, cross-references, watermarks |
| Navigation | Bookmarks (H1–H3), clickable links, `Page X of Y` | + internal links from TOC | + named destinations |
| Compliance | Metadata (Title, Author, Subject, Lang) | + `/Lang`, document outline | `--pdf-variant pdf/a-3b` (archival) or `pdf/ua-1` (tagged and accessible) |
| Install | none | `pip install fpdf2` | `pip install weasyprint` (+ Pango system libs) |

**Selection rule:** Starter whenever the environment is offline or locked down, or the user asks
for no dependencies. Pro when the content has non-Latin text or images. Enterprise when the user
mentions accessibility, archival, compliance, brand guidelines or "print-quality". If a
higher-tier dependency fails to install, **fall back one tier**, say so in one line, and list what
was lost.

## 3. Pre-Flight Validation

### 3.1 Input schema

| Field | Required | Rule | Fallback |
|---|---|---|---|
| `content` | **Blocking** | Markdown/text/JSON with a `content` string; non-empty | Ask. Never generate filler content |
| `title` | Yes | ≤ 120 chars | Front-matter `title`, then the first `# H1`, then the file name |
| `author` | No | String | Omit from metadata (never guess) |
| `page_size` | No | `a4` \| `letter` | A4. Use Letter when the locale is US/CA |
| `base_size` | No | 8–14 pt | 10.5 pt body; 9 pt for dense data reports |
| `lang` | No | BCP-47 | `en`; set from the content language |
| `footer_note` | No | ≤ 80 chars, e.g. "Confidential" | none |
| `images` | Pro+ | Local paths or https; alt text required | Starter renders `[Image: alt]` and warns |

Front matter is supported in Markdown input:

```markdown
---
title: Q3 Infrastructure Report
author: Platform Team
subject: Quarterly review
lang: en
---
```

### 3.2 Edge cases

- **Non-Latin text** (नेपाली, 中文, العربية, emoji) on Starter: the engine warns about each
  unsupported glyph. Under `--strict` it fails and deletes the output. Escalate to Pro with
  `Noto Sans` / `Noto Sans Devanagari` via `pdf.add_font("NotoDeva", fname="NotoSansDevanagari-Regular.ttf")` and `pdf.set_text_shaping(True)` for correct conjuncts.
- **Wide tables** (> 6 columns or long cells): columns are width-balanced and cells wrap. If cells
  would fall below 60 pt, use landscape (Pro/Enterprise) or split the table.
- **Long code lines:** hard-wrapped with a 2-space continuation indent. Do not shrink the font
  below 8 pt.
- **Raw HTML in Markdown:** stripped with a warning on Starter; rendered by WeasyPrint on
  Enterprise.
- **Very large documents** (> 200 pages): stream them (Pro: `fpdf2` per page; Enterprise: split by
  chapter and merge) and keep the output under the size budget (`--max-kb`).
- **Escaped Markdown** (`\*literal\*`) must render literally. Unclosed code fences raise a warning.
- **Untrusted input:** never execute embedded scripts. With WeasyPrint, set a `url_fetcher` that
  blocks `file://` and internal hosts (SSRF).

## 4. Core Execution Workflow

1. **Normalise the source:** convert JSON or plain text to Markdown, set the front matter, and
   ensure there is exactly one H1 title.
2. **Choose the engine** using the rule in §2. Check for the dependency
   (`python3 -c "import fpdf"`) before writing Pro code.
3. **Compile**
   - *Starter:* `python3 scripts/md_to_pdf.py report.md -o report.pdf --page-size a4 --footer-note "Confidential" --strict`
   - *Pro:* write one script that uses `fpdf2` with an embedded TTF, `set_auto_page_break`,
     `header()`/`footer()` overrides, `start_section()` for bookmarks, and `insert_toc_placeholder()`
     for the TOC.
   - *Enterprise:* render Markdown to semantic HTML, apply the print stylesheet in §5, then run
     `weasyprint in.html out.pdf --pdf-variant pdf/ua-1` (or `pdf/a-3b`), setting metadata via
     `<meta name="author">` and `<title>`.
4. **Verify:** `python3 scripts/verify_pdf.py report.pdf --require-title --min-pages 1`. If
   `pdftoppm` exists, rasterise page 1 (`pdftoppm -r 60 -png -f 1 -l 1`) and inspect it visually.
5. **Deliver** following §8.

## 5. Design System & Production Aesthetics (Print)

- **Page:** A4 (595×842 pt) or Letter, 0.75 in (54 pt) margins, header/footer rules at 0.5 pt
  in neutral grey.
- **Type scale:** Title 24 pt bold, H1 18, H2 14.5, H3 12.5, body 10.5 on 1.45 leading,
  code 9 pt monospace, tables 9.5 pt.
- **Colour:** body text `#212226` (not pure black), muted `#61666f`, links `#0d4dbf` and
  underlined (colour is not the only cue). All text ≥ 4.5:1 on white. Must remain legible in
  greyscale print.
- **Rhythm:** paragraph spacing 0.55 line, headings kept with the next two lines, no widowed
  single lines, and table header rows repeated on page breaks.
- **Tables:** bold header on `#e6ebf2`, zebra striping `#f7f9fa`, hairline row rules,
  right-aligned numbers (Pro+).
- **Code:** `#f2f5f7` background block, preserved whitespace, never syntax colours below 4.5:1.
- **Enterprise print CSS:** `@page { size: A4; margin: 20mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); } }`,
  `h2 { break-after: avoid; }`, `table, figure { break-inside: avoid; }`,
  `thead { display: table-header-group; }`. Use fluid units only on screen. Print uses `pt`/`mm`.
- **Accessibility (Enterprise):** tagged PDF (`pdf/ua-1`), document `lang`, title shown in the
  title bar (`DisplayDocTitle`), alt text on every figure, logical reading order, and real text
  rather than images of text.

## 6. Zero-Dependency Automation Scripts

| Script | Purpose | Usage |
|---|---|---|
| `scripts/md_to_pdf.py` | Stdlib Markdown → PDF engine: front matter, inline styles, nested/ordered/task lists, tables with repeated headers, code blocks, quotes, HR, page breaks, bookmarks, clickable links, `Page X of Y`, metadata, Flate compression | `python3 scripts/md_to_pdf.py in.md -o out.pdf [--title] [--author] [--page-size a4\|letter] [--base-size 10.5] [--footer-note] [--strict]` |
| `scripts/verify_pdf.py` | Header/EOF, xref offset integrity, page count, `/Title`, size budget, leaked Markdown syntax, placeholder text, lossy `?` glyph runs | `python3 scripts/verify_pdf.py out.pdf --require-title --min-pages 1 [--expect-pages N] [--max-kb 5000] [--json]` |

Exit codes for both: `0` ok, `1` gate failure, `2` usage/IO error. Input `-` reads stdin.

## 7. Negative Constraints (NEVER)

- **Never** alter, summarise, reorder or "improve" the source content unless asked. The PDF is a
  faithful rendering.
- **Never** deliver a PDF with leaked Markdown (`**`, `##`, `](`, ```` ``` ````), `?` replacement
  glyphs, or placeholder text.
- **Never** silently drop images, tables or non-Latin text. Escalate the tier or report the loss
  explicitly.
- **Never** hard-code absolute paths, fetch remote resources without allowlisting, or embed fonts
  you lack a licence for (Noto, Inter and Source are OFL-safe).
- **Never** use `reportlab`'s `canvas.drawString` for flowing text in Pro. Use Platypus or `fpdf2`
  `multi_cell` so text wraps.
- **Never** claim PDF/A or PDF/UA compliance unless WeasyPrint (or veraPDF validation) produced it.
- **Never** pad the answer. Return the file, the verification line, and any losses.

## 8. Production Checklist & Quality Gates

1. `verify_pdf.py` exits `0` (title present, page count sensible, no leaks, xref valid).
2. **Fidelity:** headings, list items, table rows and code blocks in the source match those in the
   PDF (spot-check with `pdftotext` when available).
3. **Pagination:** no heading is stranded at a page bottom, table headers repeat, and the page
   numbers' total is correct.
4. **Typography:** a consistent scale, no overflowing text beyond the margins, and long tokens
   hard-wrapped.
5. **Metadata:** Title, Author (if given), Lang and Producer are set. The bookmarks open the
   outline panel.
6. **Losses reported:** every engine warning appears in the response, or the tier was escalated
   to eliminate it.
7. **Code quality (Pro/Enterprise scripts):** one runnable script, functions under 60 lines,
   argparse CLI, explicit error handling with exit codes, no unused imports.

**Delivery format:** one line naming the engine and tier, the output path, the
`verify_pdf.py` PASS line, then warnings or losses (if any) as a short list.

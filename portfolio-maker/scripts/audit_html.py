#!/usr/bin/env python3
"""Offline quality gate for single-file HTML deliverables.

Zero dependencies (Python 3.8+ standard library only). Audits structure,
accessibility (WCAG 2.2 AA heuristics), theming, design-token contrast,
SEO metadata, security hygiene and leftover placeholder content.

Usage:
    audit_html.py PAGE.html [--tier starter|pro|enterprise] [--json] [--strict]
    audit_html.py --contrast FG BG

Exit codes: 0 = pass, 1 = gate failed, 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIERS = {"starter": 1, "pro": 2, "enterprise": 3}

ALLOWED_SCRIPT_HOSTS = (
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
)
ANALYTICS_HOSTS = (
    "googletagmanager.com",
    "google-analytics.com",
    "plausible.io",
    "cdn.segment.com",
    "static.hotjar.com",
    "connect.facebook.net",
)
PLACEHOLDER_PATTERNS = (
    r"lorem ipsum",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"your (company|name|product) here",
    r"\binsert (text|image|link)\b",
    r"\[(placeholder|your [a-z ]+)\]",
)
# Required design tokens and the WCAG ratio each foreground/background pair must meet.
CONTRAST_PAIRS: Tuple[Tuple[str, str, float], ...] = (
    ("--color-text", "--color-bg", 4.5),
    ("--color-text", "--color-surface", 4.5),
    ("--color-text-muted", "--color-bg", 4.5),
    ("--color-text-muted", "--color-surface", 4.5),
    ("--color-on-primary", "--color-primary", 4.5),
    ("--color-primary", "--color-bg", 3.0),
    ("--color-focus", "--color-bg", 3.0),
)
NAMED_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0)}
LABELLABLE_INPUT_EXCLUDE = {"hidden", "submit", "button", "reset", "image"}
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}


@dataclass
class Finding:
    severity: str  # "error" | "warn"
    rule: str
    message: str
    line: Optional[int] = None


# --------------------------------------------------------------------------- colour


def parse_color(value: str) -> Optional[Tuple[float, float, float]]:
    v = value.strip().lower()
    if v in NAMED_COLORS:
        return tuple(float(c) for c in NAMED_COLORS[v])  # type: ignore[return-value]
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        elif len(h) in (6, 8):
            h = h[:6]
        else:
            return None
        return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = re.split(r"[\s,/]+", m.group(1).strip())
        try:
            rgb = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
        except ValueError:
            return None
        return (rgb[0], rgb[1], rgb[2]) if len(rgb) == 3 else None
    m = re.fullmatch(r"hsla?\(([^)]*)\)", v)
    if m:
        parts = re.split(r"[\s,/]+", m.group(1).strip())
        try:
            hue = float(parts[0].replace("deg", "")) % 360
            sat = float(parts[1].rstrip("%")) / 100
            lig = float(parts[2].rstrip("%")) / 100
        except (ValueError, IndexError):
            return None
        c = (1 - abs(2 * lig - 1)) * sat
        x = c * (1 - abs((hue / 60) % 2 - 1))
        mm = lig - c / 2
        sector = int(hue // 60)
        r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][sector]
        return ((r + mm) * 255, (g + mm) * 255, (b + mm) * 255)
    return None


def relative_luminance(rgb: Tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: Tuple[float, float, float], bg: Tuple[float, float, float]) -> float:
    l1, l2 = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


# --------------------------------------------------------------------------- CSS


def strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def css_rules(css: str) -> List[Tuple[str, str]]:
    """Flatten CSS into (context, declarations) pairs; context joins nested preludes."""
    css = strip_css_comments(css)
    rules: List[Tuple[str, str]] = []
    stack: List[str] = []
    buf: List[str] = []
    for ch in css:
        if ch == "{":
            stack.append("".join(buf).strip().split(";")[-1].strip())
            buf = []
        elif ch == "}":
            if stack:
                body = "".join(buf).strip()
                if body:
                    rules.append((" >> ".join(stack), body))
                stack.pop()
            buf = []
        else:
            buf.append(ch)
    return rules


def declarations(body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for decl in body.split(";"):
        if ":" in decl:
            prop, _, val = decl.partition(":")
            out[prop.strip()] = val.replace("!important", "").strip()
    return out


def is_dark_context(ctx: str) -> bool:
    c = ctx.replace(" ", "").replace("'", '"').lower()
    return "prefers-color-scheme:dark" in c or 'data-theme="dark"' in c or "data-theme=dark" in c


def is_root_selector(ctx: str) -> bool:
    last = ctx.split(" >> ")[-1].replace(" ", "")
    return any(sel.startswith((":root", "html", "[data-theme")) for sel in last.split(","))


def theme_tokens(css: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    light: Dict[str, str] = {}
    dark: Dict[str, str] = {}
    for ctx, body in css_rules(css):
        if not is_root_selector(ctx):
            continue
        tokens = {k: v for k, v in declarations(body).items() if k.startswith("--")}
        if is_dark_context(ctx):
            dark.update(tokens)
        elif "data-theme" not in ctx and "prefers-color-scheme" not in ctx:
            light.update(tokens)
    return light, {**light, **dark}


def resolve_token(name: str, tokens: Dict[str, str], depth: int = 0) -> Optional[str]:
    if depth > 10 or name not in tokens:
        return None
    val = tokens[name]
    m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)", val)
    if m:
        return resolve_token(m.group(1), tokens, depth + 1) or m.group(2)
    return val


# --------------------------------------------------------------------------- HTML


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.tags: List[Tuple[str, Dict[str, str], int]] = []
        self.headings: List[Tuple[int, int]] = []
        self.ids: Dict[str, int] = {}
        self.duplicate_ids: List[Tuple[str, int]] = []
        self.label_for: set = set()
        self.unlabelled_controls: List[Tuple[str, Dict[str, str], int]] = []
        self.styles: List[str] = []
        self.scripts_inline: List[Tuple[str, Dict[str, str]]] = []
        self.text_chunks: List[str] = []
        self.title = ""
        self.has_doctype = False
        self.first_focusable: Optional[Tuple[str, Dict[str, str]]] = None
        self._capture: Optional[str] = None
        self._buf: List[str] = []
        self._button_open: Optional[Tuple[Dict[str, str], int, List[str]]] = None

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype html"):
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k: (v if v is not None else "") for k, v in attrs_list}
        line = self.getpos()[0]
        self.tags.append((tag, attrs, line))
        if "id" in attrs:
            if attrs["id"] in self.ids:
                self.duplicate_ids.append((attrs["id"], line))
            self.ids[attrs["id"]] = line
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append((int(tag[1]), line))
        if tag == "label" and attrs.get("for"):
            self.label_for.add(attrs["for"])
        if tag in ("input", "select", "textarea"):
            if attrs.get("type", "text").lower() not in LABELLABLE_INPUT_EXCLUDE:
                wrapped = "label" in self.stack
                named = attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("title")
                if not wrapped and not named:
                    self.unlabelled_controls.append((tag, attrs, line))
        focusable = tag in ("a", "button", "input", "select", "textarea") and not (
            tag == "a" and "href" not in attrs
        )
        if focusable and self.first_focusable is None:
            self.first_focusable = (tag, attrs)
        if tag in ("style", "script", "title"):
            self._capture = tag
            self._buf = []
        if tag == "button":
            self._button_open = (attrs, line, [])
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs_list) -> None:
        self.handle_starttag(tag, attrs_list)
        if tag not in VOID_ELEMENTS and self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._capture == tag:
            content = "".join(self._buf)
            if tag == "style":
                self.styles.append(content)
            elif tag == "title":
                self.title = content.strip()
            elif tag == "script":
                attrs = next((a for t, a, _ in reversed(self.tags) if t == "script"), {})
                if "src" not in attrs:
                    self.scripts_inline.append((content, attrs))
            self._capture = None
        if tag == "button" and self._button_open is not None:
            attrs, line, text = self._button_open
            if not "".join(text).strip() and not (attrs.get("aria-label") or attrs.get("aria-labelledby")):
                self.tags.append(("__unnamed_button__", attrs, line))
            self._button_open = None
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)
            return
        self.text_chunks.append(data)
        if self._button_open is not None:
            self._button_open[2].append(data)


# --------------------------------------------------------------------------- audit


class Auditor:
    def __init__(self, html: str, tier: str) -> None:
        self.html = html
        self.tier = TIERS[tier]
        self.findings: List[Finding] = []
        self.p = PageParser()
        self.p.feed(html)
        self.p.close()
        self.css = "\n".join(self.p.styles)

    def add(self, severity: str, rule: str, message: str, line: Optional[int] = None, min_tier: int = 1) -> None:
        if self.tier >= min_tier:
            self.findings.append(Finding(severity, rule, message, line))

    def tags(self, name: str) -> List[Tuple[Dict[str, str], int]]:
        return [(a, ln) for t, a, ln in self.p.tags if t == name]

    def meta(self, key: str, attr: str = "name") -> Optional[str]:
        for a, _ in self.tags("meta"):
            if a.get(attr, "").lower() == key:
                return a.get("content", "")
        return None

    def run(self) -> List[Finding]:
        self.check_document()
        self.check_headings_and_landmarks()
        self.check_media_and_controls()
        self.check_links_and_scripts()
        self.check_css()
        self.check_contrast()
        self.check_seo()
        self.check_content()
        return self.findings

    def check_document(self) -> None:
        p = self.p
        if not p.has_doctype:
            self.add("error", "doctype", "Missing <!doctype html>.")
        html_tags = self.tags("html")
        if not html_tags or not html_tags[0][0].get("lang"):
            self.add("error", "html-lang", "<html> must declare a lang attribute (WCAG 3.1.1).")
        charset = any(a.get("charset", "").lower() == "utf-8" for a, _ in self.tags("meta"))
        if not charset:
            self.add("error", "charset", 'Missing <meta charset="utf-8">.')
        viewport = self.meta("viewport")
        if viewport is None or "width=device-width" not in viewport.replace(" ", ""):
            self.add("error", "viewport", "Missing responsive viewport meta (width=device-width).")
        elif re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", viewport):
            self.add("error", "viewport-zoom", "Viewport blocks zoom; violates WCAG 1.4.4.")
        if not p.title:
            self.add("error", "title", "Missing or empty <title>.")
        elif not 10 <= len(p.title) <= 60:
            self.add("warn", "title-length", f"<title> is {len(p.title)} chars; aim for 10-60.")
        for ident, line in p.duplicate_ids:
            self.add("error", "duplicate-id", f'Duplicate id="{ident}".', line)
        size_kb = len(self.html.encode("utf-8")) / 1024
        if size_kb > 250:
            self.add("warn", "page-weight", f"HTML is {size_kb:.0f} KB; budget is 250 KB for a single-file page.")

    def check_headings_and_landmarks(self) -> None:
        levels = self.p.headings
        h1 = [ln for lvl, ln in levels if lvl == 1]
        if len(h1) != 1:
            self.add("error", "h1-count", f"Expected exactly one <h1>, found {len(h1)}.")
        prev = 0
        for lvl, line in levels:
            if prev and lvl > prev + 1:
                self.add("error", "heading-order", f"Heading jumps from h{prev} to h{lvl}.", line)
            prev = lvl
        mains = self.tags("main")
        if len(mains) != 1:
            self.add("error", "main-landmark", f"Expected exactly one <main>, found {len(mains)}.")
        for landmark in ("header", "footer", "nav"):
            if not self.tags(landmark):
                self.add("warn", f"{landmark}-landmark", f"No <{landmark}> landmark found.")
        first = self.p.first_focusable
        if not first or first[0] != "a" or not first[1].get("href", "").startswith("#"):
            self.add("warn", "skip-link", "First focusable element should be a skip link to #main.", min_tier=2)

    def check_media_and_controls(self) -> None:
        for a, line in self.tags("img"):
            if "alt" not in a:
                self.add("error", "img-alt", f"<img src=\"{a.get('src', '')[:60]}\"> missing alt.", line)
            if not (a.get("width") and a.get("height")):
                self.add("warn", "img-dimensions", "<img> without width/height causes layout shift (CLS).", line)
        for a, line in self.tags("svg"):
            if a.get("aria-hidden") != "true" and a.get("role") != "img":
                self.add("warn", "svg-a11y", 'Inline <svg> needs aria-hidden="true" or role="img" + label.', line)
        for tag, attrs, line in self.p.unlabelled_controls:
            if attrs.get("id") not in self.p.label_for:
                self.add("error", "form-label", f"<{tag}> has no associated <label> or aria-label.", line)
        for a, line in self.tags("button"):
            if "type" not in a:
                self.add("warn", "button-type", '<button> without explicit type (defaults to "submit").', line)
        for a, line in self.tags("__unnamed_button__"):
            self.add("error", "button-name", "<button> has no accessible name.", line)
        for a, line in self.tags("form"):
            if not a.get("action") and "novalidate" not in a and self.tier >= 2:
                self.add("warn", "form-action", "<form> has no action; ensure JS handler provides submission + feedback.", line)

    def check_links_and_scripts(self) -> None:
        for a, line in self.tags("a"):
            href = a.get("href")
            if href is None:
                continue
            if href.strip() in ("", "#") or href.lower().startswith("javascript:"):
                self.add("error", "dead-link", f'Non-navigating link href="{href}"; use a <button> or real URL.', line)
            if a.get("target") == "_blank" and "noopener" not in a.get("rel", ""):
                self.add("error", "rel-noopener", 'target="_blank" without rel="noopener".', line)
        for a, line in self.tags("script"):
            src = a.get("src", "")
            if src.startswith(("http://", "https://", "//")):
                host = re.sub(r"^(https?:)?//", "", src).split("/")[0]
                if any(host.endswith(h) for h in ANALYTICS_HOSTS):
                    if a.get("type") != "text/plain":
                        self.add("error", "analytics-consent", f"Analytics script from {host} loads before consent; gate it.", line)
                elif not any(host.endswith(h) for h in ALLOWED_SCRIPT_HOSTS):
                    self.add("error", "script-host", f"Script from non-allowlisted host {host}.", line)
                elif "integrity" not in a:
                    self.add("warn", "sri", f"CDN script from {host} lacks integrity (SRI) hash.", line, min_tier=2)
            if src.startswith("http://"):
                self.add("error", "mixed-content", f"Insecure http:// script {src}.", line)
        for t, a, line in self.p.tags:
            for attr in a:
                if attr.startswith("on"):
                    self.add("warn", "inline-handler", f"Inline {attr}= handler on <{t}> blocks a strict CSP.", line, min_tier=2)
        for content, _ in self.p.scripts_inline:
            if re.search(r"\beval\s*\(|new\s+Function\s*\(|document\.write\s*\(", content):
                self.add("error", "unsafe-js", "Inline script uses eval/new Function/document.write.")
            if re.search(r"\.innerHTML\s*=", content):
                self.add("warn", "innerhtml", "innerHTML assignment; use textContent or sanitized templates.")

    def check_css(self) -> None:
        css = strip_css_comments(self.css)
        if not css.strip():
            self.add("error", "no-css", "No embedded <style> found.")
            return
        if ":root" not in css:
            self.add("error", "css-tokens", "Design tokens must be declared on :root.")
        if "prefers-color-scheme" not in css:
            self.add("error", "dark-mode", "No prefers-color-scheme handling.", min_tier=2)
        if "data-theme" not in css and "data-theme" not in self.html.split("</style>")[-1]:
            self.add("error", "theme-toggle", "No [data-theme] manual toggle.", min_tier=2)
        if ":focus-visible" not in css:
            self.add("error", "focus-visible", "No :focus-visible styles (WCAG 2.4.7).")
        if re.search(r"outline\s*:\s*(none|0)\b", css) and ":focus-visible" not in css:
            self.add("error", "outline-removed", "Focus outline removed without replacement.")
        animated = re.search(r"\b(animation|transition)\s*:", css) or "@keyframes" in css
        if animated and "prefers-reduced-motion" not in css:
            self.add("error", "reduced-motion", "Animations present without prefers-reduced-motion guard.")
        if "clamp(" not in css:
            self.add("warn", "fluid-type", "No clamp() found; use fluid typography.", min_tier=2)
        if "@media" not in css and "@container" not in css and "clamp(" not in css:
            self.add("error", "responsive", "No media/container queries or fluid sizing found.")
        important = css.count("!important")
        if important > 3:
            self.add("warn", "important", f"{important} uses of !important; fix specificity instead.")
        if re.search(r"font-size\s*:\s*\d+(\.\d+)?px", css):
            self.add("warn", "px-font", "px font-size found; use rem/clamp() so text respects user zoom.", min_tier=2)

    def check_contrast(self) -> None:
        light, dark = theme_tokens(self.css)
        themes = [("light", light)] + ([("dark", dark)] if self.tier >= 2 else [])
        reported_missing = set()
        for theme, tokens in themes:
            for fg_name, bg_name, minimum in CONTRAST_PAIRS:
                fg_raw = resolve_token(fg_name, tokens)
                bg_raw = resolve_token(bg_name, tokens)
                if fg_raw is None or bg_raw is None:
                    missing = fg_name if fg_raw is None else bg_name
                    if (theme, missing) not in reported_missing:
                        reported_missing.add((theme, missing))
                        self.add("error", "token-missing", f"[{theme}] design token {missing} not defined.")
                    continue
                fg, bg = parse_color(fg_raw), parse_color(bg_raw)
                if fg is None or bg is None:
                    self.add("warn", "token-unparsed", f"[{theme}] cannot verify {fg_name}/{bg_name} ({fg_raw} on {bg_raw}).")
                    continue
                ratio = contrast_ratio(fg, bg)
                if ratio < minimum:
                    self.add("error", "contrast", f"[{theme}] {fg_name} on {bg_name} = {ratio:.2f}:1 (needs {minimum}:1).")

    def check_seo(self) -> None:
        desc = self.meta("description")
        if desc is None:
            self.add("error", "meta-description", "Missing meta description.", min_tier=2)
        elif not 50 <= len(desc) <= 160:
            self.add("warn", "meta-description-length", f"Meta description is {len(desc)} chars; aim for 50-160.", min_tier=2)
        if self.meta("theme-color") is None:
            self.add("warn", "theme-color", "Missing theme-color meta.", min_tier=2)
        for prop in ("og:title", "og:description", "og:image", "og:type", "og:url"):
            if self.meta(prop, "property") is None:
                self.add("error", "open-graph", f"Missing {prop}.", min_tier=3)
        og_image = self.meta("og:image", "property") or ""
        if og_image.lower().endswith(".svg"):
            self.add("error", "og-image-format", "og:image must be PNG/JPEG; social platforms reject SVG.", min_tier=3)
        if og_image and not og_image.startswith("https://"):
            self.add("error", "og-image-url", "og:image must be an absolute https:// URL.", min_tier=3)
        if self.meta("twitter:card") is None:
            self.add("error", "twitter-card", "Missing twitter:card.", min_tier=3)
        if not any(a.get("rel") == "canonical" for a, _ in self.tags("link")):
            self.add("error", "canonical", 'Missing <link rel="canonical">.', min_tier=3)
        if not any(a.get("rel") in ("icon", "shortcut icon") for a, _ in self.tags("link")):
            self.add("warn", "favicon", "Missing favicon link.", min_tier=3)
        ld_blocks = [c for c, a in self.p.scripts_inline if a.get("type") == "application/ld+json"]
        if not ld_blocks:
            self.add("error", "json-ld", "Missing JSON-LD structured data.", min_tier=3)
        for block in ld_blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError as exc:
                self.add("error", "json-ld-invalid", f"JSON-LD does not parse: {exc}.")
                continue
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for item in items:
                if isinstance(item, dict) and "@type" not in item:
                    self.add("error", "json-ld-type", "JSON-LD node without @type.")
            if isinstance(data, dict) and "@context" not in data:
                self.add("error", "json-ld-context", "JSON-LD missing @context.")

    def check_content(self) -> None:
        text = " ".join(self.p.text_chunks)
        for pattern in PLACEHOLDER_PATTERNS:
            m = re.search(pattern, text, flags=re.I)
            if m:
                self.add("error", "placeholder", f'Placeholder content left in page: "{m.group(0)}".')
        if re.search(r"\b(example\.com|yourdomain\.com|test@test\.com)\b", self.html, flags=re.I):
            self.add("warn", "placeholder-url", "Example domain/email left in markup.")


# --------------------------------------------------------------------------- CLI


def report(findings: List[Finding], strict: bool, as_json: bool, path: str, tier: str) -> int:
    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warn"]
    failed = bool(errors) or (strict and bool(warns))
    if as_json:
        print(json.dumps({
            "file": path, "tier": tier, "passed": not failed,
            "errors": len(errors), "warnings": len(warns),
            "findings": [asdict(f) for f in findings],
        }, indent=2))
    else:
        for f in sorted(findings, key=lambda f: (f.severity != "error", f.line or 0)):
            loc = f"L{f.line}" if f.line else "-"
            print(f"{f.severity.upper():5} {loc:>6}  {f.rule:<22} {f.message}")
        status = "FAIL" if failed else "PASS"
        print(f"\n{status}: {path} [{tier}] {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", nargs="?", help="HTML file to audit")
    ap.add_argument("--tier", choices=TIERS, default="pro")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--contrast", nargs=2, metavar=("FG", "BG"), help="print WCAG contrast for two colours")
    args = ap.parse_args(argv)

    if args.contrast:
        fg, bg = (parse_color(c) for c in args.contrast)
        if fg is None or bg is None:
            print("error: unparseable colour", file=sys.stderr)
            return 2
        ratio = contrast_ratio(fg, bg)
        print(f"{ratio:.2f}:1  AA-text:{'pass' if ratio >= 4.5 else 'FAIL'}  "
              f"AA-large/UI:{'pass' if ratio >= 3 else 'FAIL'}  AAA:{'pass' if ratio >= 7 else 'FAIL'}")
        return 0 if ratio >= 4.5 else 1

    if not args.file:
        ap.error("file is required unless --contrast is used")
    path = Path(args.file)
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    findings = Auditor(html, args.tier).run()
    return report(findings, args.strict, args.json, str(path), args.tier)


if __name__ == "__main__":
    sys.exit(main())

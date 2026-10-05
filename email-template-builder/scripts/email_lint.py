#!/usr/bin/env python3
"""Client-compatibility, accessibility and deliverability gate for HTML email (stdlib only).

Checks the constraints that break real inboxes: Gmail's 102 KB clipping
limit, forbidden elements (script, form, iframe, video, embed), external
stylesheets, layout tables without role="presentation", content width over
640 px, CSS Outlook ignores (flex, grid, position, float), images without
alt/width/https, relative or javascript: links, missing preheader, missing
lang/charset/title, dark-mode color-scheme meta, unsubscribe link for
marketing mail, and unresolved merge tags or placeholders.

Usage:
    email_lint.py email.html [--type transactional|marketing] [--allow-vars] [--json]

Exit codes: 0 = pass, 1 = gate failed, 2 = usage / IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLIP_KB = 102
FORBIDDEN = {"script", "form", "iframe", "video", "audio", "embed", "object", "frame", "frameset"}
OUTLOOK_UNSUPPORTED = re.compile(r"display\s*:\s*(flex|grid|inline-flex)|position\s*:\s*(absolute|fixed|sticky)|\bfloat\s*:|"
                                 r"\bgap\s*:|var\(--", re.I)
MERGE_TAG = re.compile(r"\{\{\s*[\w.]+\s*\}\}|\*\|[A-Z_]+\|\*|%%[\w]+%%|\[\[[\w]+\]\]")


class EmailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: List[Tuple[str, Dict[str, str], int]] = []
        self.texts: List[Tuple[str, List[str]]] = []
        self.stack: List[Tuple[str, Dict[str, str]]] = []
        self.title = ""
        self._in_title = False
        self.style_blocks: List[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        self.tags.append((tag, attrs, self.getpos()[0]))
        if tag not in ("img", "br", "hr", "meta", "link", "input", "source", "col"):
            self.stack.append((tag, attrs))
        self._in_title = tag == "title"
        self._in_style = tag == "style"

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        self._in_title = self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_style:
            self.style_blocks.append(data)
        elif data.strip():
            styles = [a.get("style", "") + " " + a.get("class", "") for _, a in self.stack]
            self.texts.append((data.strip(), styles))


def lint(html: str, kind: str, allow_vars: bool) -> Tuple[List[str], List[str], Dict[str, object]]:
    errors: List[str] = []
    warns: List[str] = []
    p = EmailParser()
    p.feed(html)
    size_kb = len(html.encode("utf-8")) / 1024
    tags = p.tags

    def find(name: str) -> List[Tuple[Dict[str, str], int]]:
        return [(a, ln) for t, a, ln in tags if t == name]

    if not re.match(r"\s*<!doctype html", html, re.I):
        warns.append("missing <!DOCTYPE html> (standards mode keeps rendering predictable)")
    html_tag = find("html")
    if not html_tag or not html_tag[0][0].get("lang"):
        errors.append("<html> needs a lang attribute (screen readers)")
    metas = [a for a, _ in find("meta")]
    if not any(a.get("charset") or "charset" in a.get("content", "").lower() for a in metas):
        errors.append("missing charset meta (utf-8)")
    if not any(a.get("name") == "viewport" for a in metas):
        errors.append("missing viewport meta (mobile clients)")
    if not any(a.get("name") in ("color-scheme", "supported-color-schemes") for a in metas):
        warns.append('missing <meta name="color-scheme" content="light dark"> for dark-mode clients')
    if not p.title.strip():
        errors.append("missing <title> (shown by some clients and screen readers)")
    if size_kb > CLIP_KB:
        errors.append(f"HTML is {size_kb:.1f} KB; Gmail clips messages over {CLIP_KB} KB")
    elif size_kb > 80:
        warns.append(f"HTML is {size_kb:.1f} KB; close to Gmail's {CLIP_KB} KB clip limit")

    for t, a, ln in tags:
        if t in FORBIDDEN:
            errors.append(f"L{ln}: <{t}> is stripped or blocked by email clients")
        if any(k.startswith("on") for k in a):
            errors.append(f"L{ln}: event handler attribute on <{t}>")
        style = a.get("style", "")
        if OUTLOOK_UNSUPPORTED.search(style):
            warns.append(f"L{ln}: inline CSS '{OUTLOOK_UNSUPPORTED.search(style).group(0)}' unsupported in Outlook (Word engine)")
        width = a.get("width", "") or (re.search(r"(?<![-\w])width\s*:\s*(\d+)px", style) or [None, ""])[1]
        if t in ("table", "td", "div") and width and width.isdigit() and int(width) > 640:
            errors.append(f"L{ln}: <{t}> width {width}px exceeds 640px email content width")
    for a, ln in find("link"):
        if "stylesheet" in a.get("rel", ""):
            errors.append(f"L{ln}: external stylesheet; most clients drop <link> CSS, inline it")
    for a, ln in find("table"):
        if a.get("role") != "presentation" and not find("th"):
            errors.append(f"L{ln}: layout <table> needs role=\"presentation\"")
            break
    for a, ln in find("img"):
        src = a.get("src", "")
        if "alt" not in a:
            errors.append(f"L{ln}: <img> missing alt (images are often blocked by default)")
        if not a.get("width"):
            warns.append(f"L{ln}: <img> missing width attribute (Outlook renders at native size)")
        if src and not src.startswith(("https://", "cid:")) and not (allow_vars and MERGE_TAG.search(src)):
            errors.append(f"L{ln}: image src must be absolute https:// or cid: ({src[:50]})")
        if src.lower().endswith(".svg"):
            errors.append(f"L{ln}: SVG images are unsupported in Gmail/Outlook; use PNG")
    links = find("a")
    for a, ln in links:
        href = a.get("href", "")
        if not href or href == "#" or href.lower().startswith("javascript:"):
            errors.append(f"L{ln}: link without a real destination")
        elif not re.match(r"^(https://|mailto:|tel:)", href) and not (allow_vars and MERGE_TAG.search(href)):
            errors.append(f"L{ln}: link must be absolute https://, mailto: or tel: ({href[:50]})")
    for block in p.style_blocks:
        if "@import" in block:
            errors.append("@import in <style> is blocked by most clients")

    texts = [t for t, _ in p.texts]
    preheader = any(re.search(r"display\s*:\s*none|max-height\s*:\s*0|mso-hide\s*:\s*all|preheader", " ".join(st), re.I)
                    for _, st in p.texts[:5])
    if not preheader:
        warns.append("no hidden preheader text near the top (inbox preview shows random body text)")
    if kind == "marketing":
        visible = re.search(r"unsubscribe|opt[- ]out|manage preferences", " ".join(texts), re.I)
        linked = any(re.search(r"unsub|preferences|opt-?out", a.get("href", ""), re.I) for a, _ in links)
        unsub = bool(visible) and linked
        if not unsub:
            errors.append("marketing email needs a visible unsubscribe link (CAN-SPAM, GDPR, Gmail/Yahoo bulk-sender rules)")
        if not re.search(r"\d{1,6}\s+\w+|street|road|marg|p\.?o\.? box|nepal|ltd|inc|llc|pvt", " ".join(texts), re.I):
            warns.append("no physical postal address found in footer (CAN-SPAM requirement)")
    leftover = MERGE_TAG.findall(html)
    if leftover and not allow_vars:
        errors.append(f"unresolved merge tags: {', '.join(sorted(set(leftover))[:5])} (pass --allow-vars for templates)")
    ph = re.search(r"lorem ipsum|\bTODO\b|example\.com|your company", html, re.I)
    if ph:
        errors.append(f"placeholder content: {ph.group(0)!r}")
    word_count = len(" ".join(texts).split())
    img_count = len(find("img"))
    if img_count and word_count < 50:
        warns.append("image-heavy email with little text hurts deliverability and accessibility")
    stats = {"size_kb": round(size_kb, 1), "images": img_count, "links": len(links), "words": word_count}
    return errors, warns, stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Lint an HTML email for client compatibility and deliverability.")
    ap.add_argument("file")
    ap.add_argument("--type", choices=["transactional", "marketing"], default="transactional")
    ap.add_argument("--allow-vars", action="store_true", help="permit {{merge}} tags (template files)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        html = Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    errors, warns, stats = lint(html, args.type, args.allow_vars)
    errors, warns = list(dict.fromkeys(errors)), list(dict.fromkeys(warns))
    if args.json:
        print(json.dumps({"file": args.file, "passed": not errors, "stats": stats,
                          "errors": errors, "warnings": warns}, indent=2))
    else:
        for e in errors:
            print(f"ERROR {e}")
        for w in warns:
            print(f"WARN  {w}")
        print(" | ".join(f"{k}={v}" for k, v in stats.items()))
        print(f"{'PASS' if not errors else 'FAIL'}: {args.file} [{args.type}] {len(errors)} error(s), {len(warns)} warning(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

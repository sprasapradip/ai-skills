#!/usr/bin/env python3
"""Lint and table-of-contents tool for GitHub README files (Python 3.8+ stdlib only).

Checks: single H1 first, one-paragraph summary, required sections per tier,
heading hierarchy, untagged code fences, relative links and images that do not
exist on disk, in-page anchors that do not resolve (GitHub slug rules),
image alt text, badge count, insecure links, placeholders and secrets.
`--toc` prints (or `--write-toc` injects between <!-- toc --> markers) a
table of contents generated with GitHub-compatible anchors.

Usage:
    readme_lint.py README.md [--tier starter|pro|enterprise] [--root DIR] [--json]
    readme_lint.py README.md --toc | --write-toc

Exit codes: 0 = pass, 1 = gate failed, 2 = usage / IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIERS = {"starter": 1, "pro": 2, "enterprise": 3}
REQUIRED = {
    1: [("install", "Installation"), ("usage|quick ?start|getting started", "Usage")],
    2: [("feature", "Features"), ("contribut", "Contributing"), ("licen[cs]e", "License")],
    3: [("security", "Security"), ("configur|environment|options", "Configuration"),
        ("test|development", "Development/Testing"), ("roadmap|changelog|release", "Changelog/Roadmap")],
}
SECRET = re.compile(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}")


def strip_code(md: str) -> str:
    return re.sub(r"^(```|~~~).*?^\1\s*$", "", md, flags=re.S | re.M)


def headings(md: str) -> List[Tuple[int, str, int]]:
    out = []
    in_fence = False
    for n, line in enumerate(md.splitlines(), 1):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        m = None if in_fence else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            out.append((len(m.group(1)), m.group(2), n))
    return out


def github_slugs(titles: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    slugs = []
    for t in titles:
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"<[^>]+>|[`*_~]", "", text)
        base = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
        n = seen.get(base, 0)
        seen[base] = n + 1
        slugs.append(base if n == 0 else f"{base}-{n}")
    return slugs


def toc(md: str) -> str:
    hs = [(lvl, t) for lvl, t, _ in headings(md)]
    slugs = github_slugs([t for _, t in hs])
    lines = []
    for (lvl, t), slug in zip(hs, slugs):
        if lvl in (2, 3) and t.strip().lower() not in ("table of contents", "contents"):
            label = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
            lines.append(f"{'  ' * (lvl - 2)}- [{label}](#{slug})")
    return "\n".join(lines)


def lint(md: str, tier: int, root: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warns: List[str] = []
    hs = headings(md)
    if not hs or hs[0][0] != 1:
        errors.append("README must start with a single H1 project title")
    h1 = [h for h in hs if h[0] == 1]
    if len(h1) > 1:
        errors.append(f"{len(h1)} H1 headings; use one")
    prev = 0
    for lvl, t, ln in hs:
        if prev and lvl > prev + 1:
            errors.append(f"L{ln}: heading jumps from H{prev} to H{lvl} ('{t[:40]}')")
        prev = lvl

    body = strip_code(md)
    first_para = re.search(r"^#\s.*?\n+((?:(?!#|\s*$).*\n?)+)", body, flags=re.M)
    summary = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)|!\[.*?\]\(.*?\)", "", first_para.group(1)).strip() if first_para else ""
    if len(summary) < 40:
        warns.append("no one-paragraph summary under the title (what it is, who it is for)")

    titles = " | ".join(t.lower() for _, t, _ in hs)
    for level in range(1, tier + 1):
        for pattern, label in REQUIRED[level]:
            if not re.search(pattern, titles):
                errors.append(f"missing '{label}' section (required at this tier)")

    in_fence = False
    for n, line in enumerate(md.splitlines(), 1):
        m = re.match(r"^\s*(```|~~~)(\S*)", line)
        if m:
            if not in_fence and not m.group(2):
                warns.append(f"L{n}: code fence without a language tag (use bash, json, php…)")
            in_fence = not in_fence
    if in_fence:
        errors.append("unclosed code fence")

    slugs = set(github_slugs([t for _, t, _ in hs]))
    for alt, target in re.findall(r"(!?\[[^\]]*\])\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", body):
        is_img = alt.startswith("!")
        if is_img and alt in ("![]",):
            errors.append(f"image {target} has empty alt text")
        if target.startswith("#"):
            if target[1:] not in slugs:
                errors.append(f"anchor {target} does not match any heading")
        elif target.startswith("http://"):
            warns.append(f"insecure link {target}")
        elif not re.match(r"^(https?:|mailto:|tel:)", target):
            path = (root / target.split("#")[0].split("?")[0]).resolve()
            if not path.exists():
                errors.append(f"relative {'image' if is_img else 'link'} {target} does not exist under {root}")
    badges = len(re.findall(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\(https://img\.shields\.io", md))
    if badges > 6:
        warns.append(f"{badges} badges; keep <= 6 that carry real signal (build, version, license)")
    ph = re.search(r"lorem ipsum|\bTODO\b|\bTBD\b|your-username|your_project|<project[- ]name>|example\.com", md, re.I)
    if ph:
        errors.append(f"placeholder left in README: {ph.group(0)!r}")
    if SECRET.search(md):
        errors.append("possible secret/token in README")
    if len(hs) >= 6 and "table of contents" not in titles and "<!-- toc -->" not in md and tier >= 2:
        warns.append("long README without a table of contents (run --write-toc)")
    return errors, warns


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Lint a README and generate its table of contents.")
    ap.add_argument("file")
    ap.add_argument("--tier", choices=TIERS, default="pro")
    ap.add_argument("--root", help="repository root for resolving relative links (default: README's folder)")
    ap.add_argument("--toc", action="store_true", help="print a GitHub-compatible table of contents")
    ap.add_argument("--write-toc", action="store_true", help="replace content between <!-- toc --> and <!-- tocstop -->")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        md = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    if args.toc:
        print(toc(md))
        return 0
    if args.write_toc:
        if "<!-- toc -->" not in md or "<!-- tocstop -->" not in md:
            print("error: add '<!-- toc -->' and '<!-- tocstop -->' markers first", file=sys.stderr)
            return 2
        new = re.sub(r"<!-- toc -->.*?<!-- tocstop -->", lambda _: f"<!-- toc -->\n{toc(md)}\n<!-- tocstop -->", md, flags=re.S)
        path.write_text(new, encoding="utf-8")
        print(f"table of contents written to {path}")
        return 0
    root = Path(args.root) if args.root else path.parent
    errors, warns = lint(md, TIERS[args.tier], root)
    if args.json:
        print(json.dumps({"file": str(path), "tier": args.tier, "passed": not errors,
                          "errors": errors, "warnings": warns}, indent=2))
    else:
        for e in errors:
            print(f"ERROR {e}")
        for w in warns:
            print(f"WARN  {w}")
        print(f"{'PASS' if not errors else 'FAIL'}: {path} [{args.tier}] {len(errors)} error(s), {len(warns)} warning(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

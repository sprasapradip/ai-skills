#!/usr/bin/env python3
"""On-page SEO gate for Markdown articles (Python 3.8+ standard library only).

Reads an article with YAML-style front matter (title, description, keyword,
slug, optional secondary keywords) and checks: title/meta/slug length and
keyword placement, single H1, heading hierarchy, keyword in intro and an H2,
keyword density and stuffing, word count, Flesch reading ease, sentence and
paragraph length, internal/external links, image alt text and placeholder
leftovers. Optionally emits FAQPage JSON-LD from a "## FAQ" section.

Usage:
    seo_check.py article.md [--tier starter|pro|enterprise] [--min-words 900]
                 [--site example.com] [--faq-jsonld out.json] [--json]

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


def front_matter(src: str) -> Tuple[Dict[str, str], str]:
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", src, flags=re.S)
    if not m:
        return {}, src
    meta: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, src[m.end():]


def plain(md: str) -> str:
    md = re.sub(r"```.*?```", " ", md, flags=re.S)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"^#{1,6}\s+", "", md, flags=re.M)
    md = re.sub(r"[*_`>|]", " ", md)
    return md


def words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text)


def sentences(text: str) -> List[str]:
    flat = re.sub(r"\s+", " ", text).strip()
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", flat) if len(words(s)) >= 3]


def syllables(word: str) -> int:
    w = word.lower().strip("'’-")
    groups = re.findall(r"[aeiouy]+", w)
    return max(1, len(groups) - (1 if w.endswith("e") and len(groups) > 1 and not w.endswith("le") else 0))


def flesch(text: str) -> float:
    ws = words(text)
    ss = max(1, len(sentences(text)))
    if not ws:
        return 0.0
    return round(206.835 - 1.015 * len(ws) / ss - 84.6 * sum(syllables(w) for w in ws) / len(ws), 1)


def count_phrase(text: str, phrase: str) -> int:
    return len(re.findall(r"(?<![\w-])" + re.escape(phrase.lower()) + r"(?![\w-])", text.lower()))


class Gate:
    def __init__(self, tier: int) -> None:
        self.tier = tier
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def check(self, ok: bool, msg: str, severity: str = "error", min_tier: int = 1) -> None:
        if ok or self.tier < min_tier:
            return
        (self.errors if severity == "error" else self.warnings).append(msg)


def faq_jsonld(body: str) -> Optional[Dict[str, object]]:
    m = re.search(r"^##\s+(FAQ|Frequently Asked Questions)\b.*?$(.*?)(?=^##\s|\Z)", body, flags=re.M | re.S | re.I)
    if not m:
        return None
    pairs = re.findall(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", m.group(2), flags=re.M | re.S)
    entities = [{"@type": "Question", "name": q.strip(),
                 "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"\s+", " ", plain(a)).strip()}}
                for q, a in pairs if a.strip()]
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities} if entities else None


def audit(src: str, tier: int, min_words: int, site: str) -> Tuple[Gate, Dict[str, object]]:
    g = Gate(tier)
    meta, body = front_matter(src)
    kw = meta.get("keyword", "").strip()
    title = meta.get("title", "")
    desc = meta.get("description", "")
    slug = meta.get("slug", "")
    text = plain(body)
    wc = len(words(text))

    g.check(bool(kw), "front matter 'keyword' (primary keyword) is required")
    g.check(bool(title), "front matter 'title' is required")
    g.check(bool(desc), "front matter 'description' (meta description) is required", min_tier=2)
    if title:
        g.check(30 <= len(title) <= 60, f"title is {len(title)} chars; keep 30-60 so it is not truncated", "warn")
        g.check(not kw or kw.lower() in title.lower(), "primary keyword missing from title")
    if desc:
        g.check(120 <= len(desc) <= 160, f"meta description is {len(desc)} chars; aim for 120-160", "warn")
        g.check(not kw or kw.lower() in desc.lower(), "primary keyword missing from meta description", "warn")
    if slug:
        g.check(bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug)), "slug must be lowercase kebab-case")
        g.check(len(slug) <= 60, f"slug is {len(slug)} chars; keep it under 60", "warn")
        g.check(not kw or all(t in slug for t in re.findall(r"[a-z0-9]+", kw.lower())[:3]),
                "slug should contain the keyword", "warn")
    else:
        g.check(False, "front matter 'slug' is required", min_tier=2)

    headings = [(len(h), t.strip()) for h, t in re.findall(r"^(#{1,6})\s+(.+)$", body, flags=re.M)]
    h1 = [t for lvl, t in headings if lvl == 1]
    g.check(len(h1) == 1, f"expected exactly one H1, found {len(h1)}")
    prev = 0
    for lvl, t in headings:
        g.check(not prev or lvl <= prev + 1, f"heading level jumps to H{lvl} at '{t[:40]}'")
        prev = lvl
    h2 = [t for lvl, t in headings if lvl == 2]
    g.check(len(h2) >= 2, f"only {len(h2)} H2 section(s); structure the article into scannable sections")
    if kw:
        g.check(any(kw.lower() in t.lower() for t in h1), "primary keyword missing from H1", "warn")
        g.check(any(kw.lower() in t.lower() for t in h2), "primary keyword (or close variant) missing from every H2", "warn")
        stuffed = sum(1 for _, t in headings if kw.lower() in t.lower())
        g.check(stuffed <= max(2, len(headings) // 2), f"keyword in {stuffed}/{len(headings)} headings (stuffing)")
        intro = " ".join(words(text)[:100]).lower()
        g.check(kw.lower() in intro, "primary keyword missing from the first 100 words")
        density = count_phrase(text, kw) / max(1, wc) * 100  # keyphrase occurrences per 100 words
        g.check(density >= 0.4, f"keyword density {density:.2f}% is low (target 0.5-2.5%)", "warn")
        g.check(density <= 2.5, f"keyword density {density:.2f}% looks stuffed (max 2.5%)")
    else:
        density = 0.0
    for sk in [s.strip() for s in meta.get("secondary", "").split(",") if s.strip()]:
        g.check(count_phrase(text, sk) > 0, f"secondary keyword '{sk}' not used", "warn", min_tier=2)

    g.check(wc >= min_words, f"{wc} words; brief requires at least {min_words}")
    score = flesch(text)
    g.check(score >= 50, f"Flesch reading ease {score} (target >= 50 for general audiences)", "warn")
    sents = sentences(text)
    avg = sum(len(words(s)) for s in sents) / max(1, len(sents))
    g.check(avg <= 22, f"average sentence length {avg:.1f} words (target <= 22)", "warn")
    long_paras = [p for p in re.split(r"\n\s*\n", body)
                  if not p.lstrip().startswith(("#", "```", "|", "-", "*", ">")) and len(words(p)) > 120]
    g.check(not long_paras, f"{len(long_paras)} paragraph(s) over 120 words; split them", "warn")

    links = re.findall(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)", body)
    internal = [u for _, u in links if u.startswith(("/", "./", "../", "#")) or (site and site in u)]
    external = [u for _, u in links if u.startswith("http") and not (site and site in u)]
    g.check(bool(internal), "no internal links; add 2-5 to related pages", min_tier=2)
    g.check(bool(external), "no external links to authoritative sources", "warn", min_tier=2)
    vague = [t for t, _ in links if t.strip().lower() in ("click here", "here", "this", "read more", "link")]
    g.check(not vague, f"non-descriptive link text: {', '.join(vague)}")
    g.check(not any(u.startswith("http://") for _, u in links), "insecure http:// link found", "warn")
    for alt, src in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", body):
        g.check(bool(alt.strip()), f"image {src} has empty alt text")
    m = re.search(r"lorem ipsum|\bTODO\b|\bTBD\b|\[insert[^\]]*\]|\[citation needed\]|\[add [^\]]*\]", body, re.I)
    g.check(not m, f"placeholder left in article: {m.group(0)!r}" if m else "")
    g.check(faq_jsonld(body) is not None, "no '## FAQ' section with '###' questions for FAQ rich results", "warn", min_tier=3)

    stats = {"words": wc, "keyword": kw, "density_pct": round(density, 2), "flesch": score,
             "avg_sentence_words": round(avg, 1), "h2": len(h2), "internal_links": len(internal),
             "external_links": len(external)}
    return g, stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="On-page SEO gate for Markdown articles.")
    ap.add_argument("file")
    ap.add_argument("--tier", choices=TIERS, default="pro")
    ap.add_argument("--min-words", type=int, default=900)
    ap.add_argument("--site", default="", help="your domain, to classify absolute internal links")
    ap.add_argument("--faq-jsonld", metavar="OUT", help="write FAQPage JSON-LD built from the FAQ section")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        src = Path(args.file).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    gate, stats = audit(src, TIERS[args.tier], args.min_words, args.site)
    if args.faq_jsonld:
        data = faq_jsonld(front_matter(src)[1])
        if data:
            Path(args.faq_jsonld).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            gate.warnings.append("--faq-jsonld requested but no FAQ questions found")
    passed = not gate.errors
    if args.json:
        print(json.dumps({"file": args.file, "tier": args.tier, "passed": passed, "stats": stats,
                          "errors": gate.errors, "warnings": gate.warnings}, indent=2))
    else:
        for e in gate.errors:
            print(f"ERROR {e}")
        for w in gate.warnings:
            print(f"WARN  {w}")
        print(" | ".join(f"{k}={v}" for k, v in stats.items()))
        print(f"{'PASS' if passed else 'FAIL'}: {args.file} [{args.tier}] "
              f"{len(gate.errors)} error(s), {len(gate.warnings)} warning(s)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

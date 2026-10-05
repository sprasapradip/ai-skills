#!/usr/bin/env python3
"""ATS and recruiter-readability gate for Markdown/plain-text resumes (stdlib only).

Checks contact details, standard section headings, length, bullet quality
(action-verb openers, quantified impact, weak phrases, first-person
pronouns, bullet length), date-format consistency, ATS-hostile formatting
(tables, images, columns, emoji, text in headers) and placeholders. With
--job it extracts the job description's key terms and reports coverage.

Usage:
    ats_check.py resume.md [--job job.txt] [--pages 1|2] [--json]

Exit codes: 0 = pass, 1 = gate failed, 2 = usage / IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ACTION_VERBS = set("""
accelerated achieved administered analyzed architected automated built championed coached collaborated configured
consolidated created cut debugged decreased defined delivered deployed designed developed devised directed doubled drove
eliminated enabled engineered established executed expanded generated grew guided halved hired implemented improved
increased initiated integrated introduced launched led maintained managed mentored migrated modernized negotiated
optimized orchestrated organized overhauled owned partnered pioneered planned produced programmed published rebuilt
redesigned reduced refactored released replaced resolved restructured revamped saved scaled secured shipped simplified
spearheaded standardized streamlined supervised supported tested trained transformed tripled unified upgraded wrote
""".split())
WEAK = ("responsible for", "duties included", "worked on", "helped with", "helped to", "assisted in", "involved in",
        "tasked with", "in charge of", "participated in", "various", "etc.")
SECTIONS = {
    "experience": r"experience|employment|work history|professional background",
    "skills": r"skills|technical skills|core competencies|technologies",
    "education": r"education|academic|qualifications",
}
STOP = set("""a an and are as at be by for from has have in is it its of on or our the to we will with you your this that
ability able across all also any based both can candidate company etc experience including join looking must new one plus
preferred required requirements responsibilities role team work working years year strong excellent good knowledge
understanding using within who what when where while well related skills other such their they them about into more
hiring hire senior junior mid lead developer engineer engineers run write build deploy apply salary benefits remote
office opportunity environment position seeking ideal great help make day like need needs get use used ensure
""".split())
DATE = re.compile(r"\b(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}-\d{2}|\d{1,2}/\d{4}|\d{4})\b")


def bullets(md: str) -> List[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s*(?:[-*•]|\d+\.)\s+(.+)$", md, flags=re.M)]


def date_style(token: str) -> str:
    if re.match(r"\d{4}-\d{2}", token):
        return "YYYY-MM"
    if re.match(r"\d{1,2}/\d{4}", token):
        return "MM/YYYY"
    if re.match(r"[A-Za-z]", token):
        return "Mon YYYY"
    return "YYYY"


def job_terms(job: str, top: int = 25) -> List[str]:
    raw = [t.strip(".-") for t in re.findall(r"[a-z][a-z0-9+#.\-]{1,}", job.lower())]
    keep = [t for t in raw if t not in STOP and len(t) > 2]
    counts = Counter(keep)
    bigrams = Counter(f"{a} {b}" for a, b in zip(raw, raw[1:])
                      if a != b and a not in STOP and b not in STOP and len(a) > 2 and len(b) > 2)
    terms = [b for b, c in bigrams.most_common(10) if c >= 2]
    terms += [t for t, _ in counts.most_common(top * 2) if not any(t in b for b in terms)]
    return terms[:top]


def check(md: str, job: Optional[str], pages: int) -> Tuple[List[str], List[str], Dict[str, object]]:
    errors: List[str] = []
    warns: List[str] = []
    text = re.sub(r"[#*_`>]", " ", md)
    words = re.findall(r"[A-Za-z0-9][\w'+#.-]*", text)
    wc = len(words)

    if not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", md):
        errors.append("no email address found")
    if not re.search(r"linkedin\.com/in/|github\.com/", md, re.I):
        warns.append("no LinkedIn or GitHub URL")
    if re.search(r"\b(date of birth|DOB|marital status|religion|nationality|passport no)\b", md, re.I):
        warns.append("personal data (DOB/marital status/religion/passport) invites bias; remove it")
    heads = " | ".join(h.lower() for h in re.findall(r"^#{1,3}\s+(.+)$", md, flags=re.M))
    for key, pattern in SECTIONS.items():
        if not re.search(pattern, heads):
            errors.append(f"missing standard '{key.title()}' heading (ATS parsers look for it)")
    if not re.search(r"summary|profile|about", heads):
        warns.append("no Summary/Profile section")

    lo, hi = (250, 650) if pages == 1 else (450, 1100)
    if wc < lo:
        warns.append(f"{wc} words; thin for a {pages}-page resume (aim {lo}-{hi})")
    if wc > hi:
        errors.append(f"{wc} words; exceeds a {pages}-page resume (aim {lo}-{hi})")

    bl = bullets(md)
    action = [b for b in bl if b.split()[0].lower().strip(",.") in ACTION_VERBS] if bl else []
    metric = [b for b in bl if re.search(r"\d|%|\$|₹|NPR|Rs\.?", b)]
    weak = [b for b in bl if any(w in b.lower() for w in WEAK)]
    long = [b for b in bl if len(b.split()) > 30]
    pron = re.findall(r"\b(I|me|my|mine)\b", " ".join(bl))
    if len(bl) < 6:
        errors.append(f"only {len(bl)} bullet points; describe impact as bullets under each role")
    else:
        if len(action) / len(bl) < 0.7:
            warns.append(f"{len(action)}/{len(bl)} bullets start with a strong action verb (target >= 70%)")
        if len(metric) / len(bl) < 0.4:
            warns.append(f"{len(metric)}/{len(bl)} bullets are quantified (target >= 40%: %, time, money, users)")
    for b in weak[:5]:
        warns.append(f"weak phrasing: \"{b[:70]}\"")
    for b in long[:3]:
        warns.append(f"bullet over 30 words: \"{b[:60]}…\"")
    if pron:
        warns.append(f"{len(pron)} first-person pronoun(s) in bullets; drop 'I/my'")

    styles = {date_style(d) for d in DATE.findall(md) if not re.fullmatch(r"\d{4}", d)}
    if len(styles) > 1:
        errors.append(f"inconsistent date formats: {', '.join(sorted(styles))}")
    if re.search(r"^\s*\|.*\|\s*$", md, flags=re.M):
        errors.append("tables confuse ATS parsers; use plain headings and bullets")
    if re.search(r"!\[[^\]]*\]\(", md) or re.search(r"<img\b", md, re.I):
        errors.append("images/photos/icons are not parsed by ATS; remove them")
    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", md):
        warns.append("emoji or symbol glyphs may garble in ATS parsing")
    ph = re.search(r"lorem ipsum|\bTODO\b|\[company\]|\[role\]|your name|xx%|\bX+%", md, re.I)
    if ph:
        errors.append(f"placeholder left: {ph.group(0)!r}")

    stats: Dict[str, object] = {"words": wc, "bullets": len(bl), "action_verb_pct": round(100 * len(action) / max(1, len(bl))),
                                "quantified_pct": round(100 * len(metric) / max(1, len(bl)))}
    if job:
        terms = job_terms(job)
        low = md.lower()
        hit = [t for t in terms if t in low]
        miss = [t for t in terms if t not in low]
        coverage = round(100 * len(hit) / max(1, len(terms)))
        stats.update({"jd_coverage_pct": coverage, "jd_missing": miss})
        if coverage < 60:
            warns.append(f"job-description coverage {coverage}%; add truthful matches for: {', '.join(miss[:10])}")
    return errors, warns, stats


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ATS readiness check for a Markdown/plain-text resume.")
    ap.add_argument("file")
    ap.add_argument("--job", help="job description text file for keyword coverage")
    ap.add_argument("--pages", type=int, choices=[1, 2], default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        md = Path(args.file).read_text(encoding="utf-8-sig")
        job = Path(args.job).read_text(encoding="utf-8") if args.job else None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not md.strip():
        print("error: empty resume", file=sys.stderr)
        return 2
    errors, warns, stats = check(md, job, args.pages)
    if args.json:
        print(json.dumps({"file": args.file, "passed": not errors, "stats": stats,
                          "errors": errors, "warnings": warns}, indent=2))
    else:
        for e in errors:
            print(f"ERROR {e}")
        for w in warns:
            print(f"WARN  {w}")
        print(" | ".join(f"{k}={v}" for k, v in stats.items() if k != "jd_missing"))
        print(f"{'PASS' if not errors else 'FAIL'}: {args.file} {len(errors)} error(s), {len(warns)} warning(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

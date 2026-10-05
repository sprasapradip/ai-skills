#!/usr/bin/env python3
"""Validate and normalise a portfolio profile JSON before generating the site.

Standard library only (Python 3.8+). Enforces the schema documented in
SKILL.md, checks URL/email/date formats and chronology, flags PII exposure
and thin content, and can write a normalised copy (trimmed strings,
de-duplicated skills, experience sorted newest-first, featured projects
defaulted) that the page generator consumes.

Usage:
    validate_profile.py profile.json [--tier starter|pro|enterprise]
                        [--normalize out.json] [--json]

Exit codes: 0 = valid, 1 = schema errors, 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TIERS = {"starter": 1, "pro": 2, "enterprise": 3}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
URL = re.compile(r"^https://[^\s/$.?#][^\s]*$")
DATE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


class Report:
    def __init__(self, tier: int) -> None:
        self.tier = tier
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def error(self, path: str, msg: str, min_tier: int = 1) -> None:
        if self.tier >= min_tier:
            self.errors.append(f"{path}: {msg}")

    def warn(self, path: str, msg: str, min_tier: int = 1) -> None:
        if self.tier >= min_tier:
            self.warnings.append(f"{path}: {msg}")


def clean(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [clean(v) for v in value if not (isinstance(v, str) and not v.strip())]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


def expect(r: Report, obj: Dict[str, Any], key: str, kind: type, path: str, required: bool = False,
           min_tier: int = 1) -> Any:
    val = obj.get(key)
    if val is None or val == "" or val == []:
        if required:
            r.error(f"{path}.{key}", "is required", min_tier)
        return None
    if not isinstance(val, kind):
        r.error(f"{path}.{key}", f"must be {kind.__name__}, got {type(val).__name__}")
        return None
    return val


def check_url(r: Report, value: Optional[str], path: str) -> None:
    if value and not URL.match(value):
        r.error(path, f"must be an absolute https:// URL (got {value[:60]!r})")


def parse_date(value: str) -> Tuple[int, int]:
    parts = value.split("-")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 1


def string_leaves(value: Any, path: str):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from string_leaves(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from string_leaves(v, f"{path}.{k}")


def validate(data: Dict[str, Any], r: Report) -> None:
    name = expect(r, data, "name", str, "$", required=True)
    expect(r, data, "role", str, "$", required=True)
    summary = expect(r, data, "summary", str, "$", required=True, min_tier=2)
    if summary and not 80 <= len(summary) <= 700:
        r.warn("$.summary", f"{len(summary)} chars; aim for 80-700")
    if name and len(name) > 80:
        r.error("$.name", "longer than 80 chars")

    contact = expect(r, data, "contact", dict, "$", required=True) or {}
    email = expect(r, contact, "email", str, "$.contact", required=True)
    if email and not EMAIL.match(email):
        r.error("$.contact.email", f"invalid email {email!r}")
    if contact.get("phone") and not contact.get("show_phone"):
        r.warn("$.contact.phone", "phone will be omitted unless show_phone is true (PII)")
    if contact.get("address"):
        r.warn("$.contact.address", "street address must never be published; use city/country in $.location")
    for field in ("summary", "tagline"):
        if isinstance(data.get(field), str) and PHONE.search(data[field]):
            r.warn(f"$.{field}", "contains a phone-number-like string (PII)")

    links = expect(r, data, "links", list, "$") or []
    for i, link in enumerate(links):
        if not isinstance(link, dict) or not link.get("label") or not link.get("url"):
            r.error(f"$.links[{i}]", "needs label and url")
            continue
        check_url(r, link["url"], f"$.links[{i}].url")
    if not any(isinstance(l, dict) and "github.com" in str(l.get("url", "")) for l in links):
        r.warn("$.links", "no GitHub link; recommended for developer portfolios")

    skills = expect(r, data, "skills", dict, "$", required=True) or {}
    total = 0
    for cat, items in skills.items():
        if not isinstance(items, list) or not all(isinstance(s, str) for s in items):
            r.error(f"$.skills.{cat}", "must be a list of strings")
            continue
        total += len(items)
        lowered = [s.lower() for s in items]
        dupes = sorted({s for s in lowered if lowered.count(s) > 1})
        if dupes:
            r.warn(f"$.skills.{cat}", f"duplicates removed: {', '.join(dupes)}")
    if not total:
        r.error("$.skills", "needs at least one category with skills")
    if total > 40:
        r.warn("$.skills", f"{total} skills listed; curate to <= 40 for credibility")

    projects = expect(r, data, "projects", list, "$", required=True) or []
    if len(projects) < 2:
        r.warn("$.projects", "fewer than 2 projects; the grid will look sparse", min_tier=2)
    names = set()
    for i, p in enumerate(projects):
        path = f"$.projects[{i}]"
        if not isinstance(p, dict):
            r.error(path, "must be an object")
            continue
        pname = expect(r, p, "name", str, path, required=True)
        psum = expect(r, p, "summary", str, path, required=True)
        if pname:
            if pname.lower() in names:
                r.error(f"{path}.name", f"duplicate project {pname!r}")
            names.add(pname.lower())
        if psum and len(psum) > 280:
            r.warn(f"{path}.summary", f"{len(psum)} chars; cards read best under 280")
        expect(r, p, "tech", list, path)
        for key in ("repo", "demo"):
            check_url(r, p.get(key), f"{path}.{key}")
        if not p.get("repo") and not p.get("demo"):
            r.warn(path, "no repo or demo link; add proof of work", min_tier=2)
        if p.get("image") and not p.get("image_alt"):
            r.error(f"{path}.image_alt", "required when image is set (WCAG 1.1.1)")
        if not p.get("metrics"):
            r.warn(f"{path}.metrics", "no quantified outcome (users, latency, revenue)", min_tier=3)

    today = _dt.date.today()
    exp = expect(r, data, "experience", list, "$", required=True, min_tier=2) or []
    for i, job in enumerate(exp):
        path = f"$.experience[{i}]"
        if not isinstance(job, dict):
            r.error(path, "must be an object")
            continue
        expect(r, job, "company", str, path, required=True)
        expect(r, job, "role", str, path, required=True)
        start = expect(r, job, "start", str, path, required=True)
        end = job.get("end")
        if start and not DATE.match(start):
            r.error(f"{path}.start", "must be YYYY or YYYY-MM")
            continue
        if end not in (None, "", "present") and (not isinstance(end, str) or not DATE.match(end)):
            r.error(f"{path}.end", "must be YYYY, YYYY-MM, 'present' or null")
            continue
        if start:
            s = parse_date(start)
            if s > (today.year, today.month):
                r.error(f"{path}.start", "is in the future")
            if isinstance(end, str) and DATE.match(end) and parse_date(end) < s:
                r.error(f"{path}.end", "is before start")
        if not job.get("highlights"):
            r.warn(f"{path}.highlights", "no achievements listed", min_tier=2)

    seo = data.get("seo") or {}
    if not isinstance(seo, dict):
        r.error("$.seo", "must be an object")
        seo = {}
    if not seo.get("site_url"):
        r.error("$.seo.site_url", "is required (canonical + og:url)", min_tier=3)
    check_url(r, seo.get("site_url"), "$.seo.site_url")
    og = seo.get("og_image")
    if not og:
        r.error("$.seo.og_image", "is required (1200x630 PNG/JPEG)", min_tier=3)
    elif str(og).lower().endswith(".svg"):
        r.error("$.seo.og_image", "must be PNG/JPEG; social platforms reject SVG")
    else:
        check_url(r, og, "$.seo.og_image")

    placeholder = re.compile(r"lorem ipsum|your (name|company|role)|example\.com|\bTODO\b|\[(insert|placeholder|your)[^\]]*\]", re.I)
    for path, text in string_leaves(data, "$"):
        match = placeholder.search(text)
        if match:
            r.error(path, f"placeholder content found: {match.group(0)!r}")


def normalise(data: Dict[str, Any]) -> Dict[str, Any]:
    out = clean(data)
    skills = out.get("skills") or {}
    for cat, items in list(skills.items()):
        if isinstance(items, list):
            seen, uniq = set(), []
            for s in items:
                if isinstance(s, str) and s.lower() not in seen:
                    seen.add(s.lower())
                    uniq.append(s)
            skills[cat] = uniq
    projects = [p for p in out.get("projects") or [] if isinstance(p, dict)]
    if projects and not any(p.get("featured") for p in projects):
        for p in projects[:3]:
            p["featured"] = True
    out["projects"] = projects
    exp = [j for j in out.get("experience") or [] if isinstance(j, dict)]
    exp.sort(key=lambda j: str(j.get("start", "")), reverse=True)
    for j in exp:
        if j.get("end") in (None, ""):
            j["end"] = "present"
    out["experience"] = exp
    contact = out.get("contact") or {}
    if contact.get("phone") and not contact.get("show_phone"):
        contact.pop("phone")
    contact.pop("address", None)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a portfolio profile JSON.")
    ap.add_argument("file")
    ap.add_argument("--tier", choices=TIERS, default="pro")
    ap.add_argument("--normalize", metavar="OUT", help="write normalised JSON when valid")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        data = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"error: cannot load {args.file}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("error: profile root must be a JSON object", file=sys.stderr)
        return 2
    report = Report(TIERS[args.tier])
    validate(clean(data), report)
    passed = not report.errors
    if passed and args.normalize:
        Path(args.normalize).write_text(json.dumps(normalise(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({"file": args.file, "tier": args.tier, "passed": passed,
                          "errors": report.errors, "warnings": report.warnings}, indent=2))
    else:
        for e in report.errors:
            print(f"ERROR {e}")
        for w in report.warnings:
            print(f"WARN  {w}")
        suffix = f"; normalised -> {args.normalize}" if passed and args.normalize else ""
        print(f"{'PASS' if passed else 'FAIL'}: {args.file} [{args.tier}] "
              f"{len(report.errors)} error(s), {len(report.warnings)} warning(s){suffix}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Repository linter for premium skills (Python 3.8+ stdlib only).

For every <skill>/SKILL.md: validates YAML frontmatter (name, description,
version, tier), required sections, that every referenced scripts/<file>
exists and every shipped script is documented, that scripts parse and are
executable with a shebang, and that shared files stay byte-identical.

Usage: python3 scripts/validate_skills.py [ROOT]
Exit codes: 0 = all skills valid, 1 = problems found.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

REQUIRED_KEYS = ("name", "description", "version", "tier")
REQUIRED_SECTIONS = (
    "System Role & Objective",
    "Mode Selection",
    "Pre-Flight Validation",
    "Core Execution Workflow",
    "Automation Scripts",
    "Negative Constraints",
    "Production Checklist",
)
SHARED_FILES = [("landing-page-builder/scripts/audit_html.py", "portfolio-maker/scripts/audit_html.py")]
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def frontmatter(text: str) -> Dict[str, str]:
    m = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.S)
    if not m:
        return {}
    data: Dict[str, str] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        km = re.match(r"^([a-z_]+):\s*(.*)$", lines[i])
        if not km:
            i += 1
            continue
        key, value = km.group(1), km.group(2).strip()
        if value in (">", ">-", "|", "|-"):
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            data[key] = (" " if value.startswith(">") else "\n").join(b for b in block if b)
            continue
        data[key] = value.strip("\"'")
        i += 1
    return data


def check_skill(skill_dir: Path) -> List[str]:
    problems: List[str] = []
    md = skill_dir / "SKILL.md"
    text = md.read_text(encoding="utf-8")
    fm = frontmatter(text)
    for key in REQUIRED_KEYS:
        if not fm.get(key):
            problems.append(f"frontmatter missing '{key}'")
    name = fm.get("name", "")
    if name and (name != skill_dir.name or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64):
        problems.append(f"name '{name}' must be kebab-case, <= 64 chars and match folder '{skill_dir.name}'")
    desc = fm.get("description", "")
    if len(desc) > 1024:
        problems.append(f"description is {len(desc)} chars (max 1024)")
    if desc and "use when" not in desc.lower():
        problems.append("description must state trigger phrases ('Use when ...')")
    if fm.get("version") and not SEMVER.match(fm["version"]):
        problems.append(f"version '{fm['version']}' is not semver")
    if fm.get("tier") and fm["tier"] != "premium":
        problems.append(f"tier must be 'premium', got '{fm['tier']}'")
    headings = re.findall(r"^#{1,3} .*$", text, flags=re.M)
    for section in REQUIRED_SECTIONS:
        if not any(section.lower() in h.lower() for h in headings):
            problems.append(f"missing section '{section}'")

    referenced = set(re.findall(r"scripts/([\w.-]+\.(?:py|sh))", text))
    scripts_dir = skill_dir / "scripts"
    shipped = {p.name for p in scripts_dir.glob("*") if p.suffix in (".py", ".sh")} if scripts_dir.is_dir() else set()
    for missing in sorted(referenced - shipped):
        problems.append(f"references scripts/{missing} which does not exist")
    for undocumented in sorted(shipped - referenced):
        problems.append(f"scripts/{undocumented} is not documented in SKILL.md")
    if not shipped:
        problems.append("no automation scripts shipped in scripts/")
    for name in sorted(shipped):
        path = scripts_dir / name
        src = path.read_text(encoding="utf-8")
        if not src.startswith("#!"):
            problems.append(f"scripts/{name} lacks a shebang")
        if not os.access(path, os.X_OK):
            problems.append(f"scripts/{name} is not executable (chmod +x)")
        if name.endswith(".py"):
            try:
                ast.parse(src, filename=str(path))
            except SyntaxError as exc:
                problems.append(f"scripts/{name} syntax error line {exc.lineno}: {exc.msg}")
            third_party = re.findall(r"^\s*(?:import|from)\s+(requests|numpy|PIL|fpdf|reportlab|weasyprint|bs4|yaml|lxml)\b",
                                     src, flags=re.M)
            if third_party:
                problems.append(f"scripts/{name} imports non-stdlib modules: {', '.join(sorted(set(third_party)))}")
        else:
            result = subprocess.run(["sh", "-n", str(path)], capture_output=True, text=True)
            if result.returncode:
                problems.append(f"scripts/{name} shell syntax error: {result.stderr.strip()}")
    return problems


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)
    skills = sorted(p.parent for p in root.glob("*/SKILL.md"))
    if not skills:
        print(f"error: no */SKILL.md under {root}", file=sys.stderr)
        return 1
    failed = 0
    for skill in skills:
        problems = check_skill(skill)
        status = "PASS" if not problems else "FAIL"
        print(f"{status}  {skill.name}")
        for p in problems:
            print(f"      - {p}")
        failed += bool(problems)
    for a, b in SHARED_FILES:
        pa, pb = root / a, root / b
        if pa.exists() and pb.exists() and pa.read_bytes() != pb.read_bytes():
            print(f"FAIL  shared file drift: {a} != {b} (copy the canonical version)")
            failed += 1
    print(f"\n{len(skills) - min(failed, len(skills))}/{len(skills)} skills valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Security, accessibility and platform-compatibility gate for SVG cards/banners.

Standard library only. Rejects DTD/entity declarations before parsing (XXE /
billion-laughs), scripts, event handlers, foreignObject and remote resources;
verifies dimensions, aspect ratio, accessible name and text safe zone.

Usage:
    validate_svg.py CARD.svg [--size og|github|square|WxH] [--json]

Exit codes: 0 = pass, 1 = fail, 2 = usage / IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

SIZES = {"og": (1200, 630), "github": (1280, 640), "square": (1080, 1080)}
NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
SAFE_MARGIN = 40
MAX_KB = 1024
GENERIC_FAMILIES = ("sans-serif", "serif", "monospace", "system-ui", "cursive", "fantasy")


def parse_size(value: str) -> Tuple[int, int]:
    if value in SIZES:
        return SIZES[value]
    m = re.fullmatch(r"(\d+)x(\d+)", value)
    if not m:
        raise argparse.ArgumentTypeError("size must be og|github|square or WxH")
    return int(m.group(1)), int(m.group(2))


def num(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", value)
    return float(m.group(1)) if m else None


def translate(el: ET.Element) -> Tuple[float, float]:
    m = re.search(r"translate\(\s*(-?[\d.]+)(?:[\s,]+(-?[\d.]+))?\s*\)", el.get("transform", ""))
    return (float(m.group(1)), float(m.group(2) or 0)) if m else (0.0, 0.0)


def check_safe_zone(el: ET.Element, ox: float, oy: float, width: float, height: float, warnings: List[str]) -> None:
    """Walk the tree accumulating translate() offsets; warn when text starts outside the safe zone."""
    dx, dy = translate(el)
    ox, oy = ox + dx, oy + dy
    tag = el.tag.replace(NS, "")
    if tag in ("text", "tspan"):
        x, y = num(el.get("x")), num(el.get("y"))
        anchor = el.get("text-anchor")
        if x is not None and anchor not in ("end", "middle") and not SAFE_MARGIN <= x + ox <= width - SAFE_MARGIN:
            warnings.append(f"text starts at x={x + ox:.0f}, outside {SAFE_MARGIN}px safe zone")
        if y is not None and not SAFE_MARGIN <= y + oy <= height - SAFE_MARGIN / 2:
            warnings.append(f"text baseline y={y + oy:.0f} outside safe zone")
    for child in el:
        check_safe_zone(child, ox, oy, width, height, warnings)


def validate(raw: str, expected: Optional[Tuple[int, int]]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if re.search(r"<!DOCTYPE|<!ENTITY", raw, flags=re.I):
        return ["DOCTYPE/ENTITY declarations are not allowed (XXE risk)"], warnings
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"], warnings
    if root.tag != f"{NS}svg":
        return ["root element is not <svg> in the SVG namespace"], warnings

    vb = root.get("viewBox")
    width, height = num(root.get("width")), num(root.get("height"))
    if vb:
        parts = [float(p) for p in re.split(r"[\s,]+", vb.strip()) if p]
        if len(parts) == 4:
            width, height = width or parts[2], height or parts[3]
            if (parts[2], parts[3]) != (width, height):
                warnings.append("viewBox size differs from width/height; output will scale")
    else:
        errors.append("missing viewBox (needed for crisp scaling)")
    if not width or not height:
        errors.append("cannot determine width/height")
    elif expected and (round(width), round(height)) != expected:
        errors.append(f"size is {width:.0f}x{height:.0f}, expected {expected[0]}x{expected[1]}")

    title = root.find(f"{NS}title")
    if title is None or not (title.text or "").strip():
        errors.append("missing non-empty <title> as first child (accessible name / alt text)")
    if root.get("role") != "img":
        warnings.append('root <svg> should have role="img"')

    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag in ("script", "foreignObject", "iframe", "embed", "object"):
            errors.append(f"<{tag}> is not allowed (security / renderer support)")
        for attr, val in el.attrib.items():
            if attr.lower().startswith("on"):
                errors.append(f"event handler {attr} on <{tag}>")
            if attr in ("href", XLINK) and re.match(r"^\s*(https?:|//|javascript:)", val, flags=re.I):
                errors.append(f"remote/JS reference in <{tag}> {val[:60]} (embed as data: URI instead)")
        if tag == "style" and el.text and "@import" in el.text:
            errors.append("@import in <style> fetches remote resources")
        family = el.get("font-family")
        if family and not family.strip().rstrip(";").endswith(GENERIC_FAMILIES):
            warnings.append(f"font-family '{family[:40]}' lacks a generic fallback")

    if width and height:
        check_safe_zone(root, 0.0, 0.0, width, height, warnings)
    texts = [t for t in root.iter(f"{NS}text")]
    if not texts:
        warnings.append("no <text> elements; if text was outlined to paths, ensure <title> carries it")
    size_kb = len(raw.encode("utf-8")) / 1024
    if size_kb > MAX_KB:
        errors.append(f"file is {size_kb:.0f} KB; budget {MAX_KB} KB")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate an SVG social card.")
    ap.add_argument("file")
    ap.add_argument("--size", type=parse_size)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        raw = Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate(raw, args.size)
    if args.json:
        print(json.dumps({"file": args.file, "passed": not errors, "errors": errors, "warnings": warnings}, indent=2))
    else:
        for e in errors:
            print(f"ERROR {e}")
        for w in warnings:
            print(f"WARN  {w}")
        print(f"{'PASS' if not errors else 'FAIL'}: {args.file}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

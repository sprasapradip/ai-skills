#!/usr/bin/env python3
"""Render an accessible, safe-zone-aware social/OG card as SVG (stdlib only).

Auto-fits the title (shrinks font, wraps to <= 3 lines, ellipsis as last
resort), validates WCAG contrast of every text layer against both gradient
stops, and escapes all user text.

Usage:
    render_card.py --title "..." [--subtitle ...] [--badge ...] [--handle ...] [--url ...]
                   [--theme midnight|ocean|forest|sunset|light|mono]
                   [--bg1 HEX --bg2 HEX --fg HEX --accent HEX]
                   [--size og|github|square] [--config card.json] -o card.svg [--strict]

Exit codes: 0 = written, 1 = quality gate failed (contrast / truncation under --strict), 2 = usage error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

SIZES: Dict[str, Tuple[int, int]] = {"og": (1200, 630), "github": (1280, 640), "square": (1080, 1080)}
THEMES: Dict[str, Dict[str, str]] = {
    "midnight": {"bg1": "#0f172a", "bg2": "#1e1b4b", "fg": "#f8fafc", "accent": "#22d3ee"},
    "ocean": {"bg1": "#0c4a6e", "bg2": "#082f49", "fg": "#f0f9ff", "accent": "#7dd3fc"},
    "forest": {"bg1": "#052e16", "bg2": "#14532d", "fg": "#f0fdf4", "accent": "#4ade80"},
    "sunset": {"bg1": "#431407", "bg2": "#7c2d12", "fg": "#fff7ed", "accent": "#fdba74"},
    "light": {"bg1": "#ffffff", "bg2": "#eef2ff", "fg": "#0f172a", "accent": "#4338ca"},
    "mono": {"bg1": "#0a0a0a", "bg2": "#262626", "fg": "#fafafa", "accent": "#d4d4d4"},
}
FONT_STACK = "Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
MONO_STACK = "'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace"
SUBTITLE_OPACITY = 0.82
PAD = 80
LIMITS = {"title": 90, "subtitle": 160, "badge": 24, "handle": 40, "url": 60}


def hex_rgb(value: str) -> Tuple[float, float, float]:
    h = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}", h):
        raise ValueError(f"invalid hex colour: {value!r}")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(float(int(h[i:i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(rgb: Tuple[float, float, float]) -> float:
    def ch(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg: Tuple[float, float, float], bg: Tuple[float, float, float], alpha: float) -> Tuple[float, float, float]:
    return tuple(f * alpha + b * (1 - alpha) for f, b in zip(fg, bg))  # type: ignore[return-value]


def char_em(ch: str) -> float:
    """Conservative advance-width estimate (em) for a bold geometric sans."""
    if ch == " ":
        return 0.28
    if ch in "il.,:;'|!Ijt":
        return 0.32
    if ch in "frI()[]-":
        return 0.40
    if ch in "mwMW@%":
        return 0.95
    if ch.isupper():
        return 0.72
    if ch.isdigit():
        return 0.62
    if ord(ch) > 0x2E7F:  # CJK and other full-width scripts
        return 1.0
    return 0.58


def measure(text: str, size: float, weight_factor: float = 1.0) -> float:
    return sum(char_em(c) for c in text) * size * weight_factor


def wrap(text: str, size: float, width: float, weight: float) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if measure(candidate, size, weight) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit(text: str, width: float, max_size: int, min_size: int, max_lines: int, weight: float) -> Tuple[int, List[str], bool]:
    for size in range(max_size, min_size - 1, -2):
        lines = wrap(text, size, width, weight)
        if len(lines) <= max_lines and all(measure(ln, size, weight) <= width for ln in lines):
            return size, lines, False
    lines = wrap(text, min_size, width, weight)[:max_lines]
    last = lines[-1]
    while last and measure(last + "…", min_size, weight) > width:
        last = last[:-1].rstrip()
    lines[-1] = last + "…"
    return min_size, lines, True


def build(cfg: Dict[str, str], size_key: str) -> Tuple[str, List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    w, h = SIZES[size_key]
    colors = {k: hex_rgb(cfg[k]) for k in ("bg1", "bg2", "fg", "accent")}
    for stop in ("bg1", "bg2"):
        bg = colors[stop]
        checks = (
            ("title", colors["fg"], 4.5),
            ("subtitle", blend(colors["fg"], bg, SUBTITLE_OPACITY), 4.5),
            ("badge/accent", colors["accent"], 4.5),
        )
        for name, fg, minimum in checks:
            ratio = contrast(fg, bg)
            if ratio < minimum:
                errors.append(f"{name} contrast on {stop} is {ratio:.2f}:1 (needs {minimum}:1)")

    for key, limit in LIMITS.items():
        if len(cfg.get(key, "")) > limit:
            warnings.append(f"{key} is {len(cfg[key])} chars; recommended max {limit}")

    content_w = w - 2 * PAD
    has_badge = bool(cfg.get("badge"))
    footer_h = 56 if (cfg.get("handle") or cfg.get("url")) else 0
    available_top = PAD + (44 if has_badge else 0) + 24
    available_bottom = h - PAD - footer_h - 24
    available_h = available_bottom - available_top

    def block_height(t_size: int, t_n: int, s_size: int, s_n: int) -> float:
        return t_n * t_size * 1.12 + (s_n * s_size * 1.35 + 24 if s_n else 0)

    title_max = 76 if size_key != "square" else 84
    s_size, s_lines, s_trunc = 30, [], False
    if cfg.get("subtitle"):
        s_size, s_lines, s_trunc = fit(cfg["subtitle"], content_w, 32, 24, 2, 1.0)
    t_size, t_lines, truncated = fit(cfg["title"], content_w, title_max, 44, 3, 1.06)
    # Shrink the title (then the subtitle) until the text block fits vertically.
    for t_cap in range(title_max, 43, -2):
        t_size, t_lines, truncated = fit(cfg["title"], content_w, t_cap, 44, 3, 1.06)
        if block_height(t_size, len(t_lines), s_size, len(s_lines)) <= available_h:
            break
    if s_lines and block_height(t_size, len(t_lines), s_size, len(s_lines)) > available_h:
        s_size, s_lines, s_trunc = fit(cfg["subtitle"], content_w, 26, 24, 1, 1.0)
    if block_height(t_size, len(t_lines), s_size, len(s_lines)) > available_h:
        errors.append("text block overflows the safe zone; shorten title/subtitle")
    if truncated:
        warnings.append("title truncated with ellipsis; shorten it")
    if s_trunc:
        warnings.append("subtitle truncated with ellipsis; shorten it")

    y = PAD
    parts: List[str] = []
    if cfg.get("badge"):
        badge = cfg["badge"].upper()
        bw = measure(badge, 20, 1.15) + 20 * 0.12 * len(badge) + 40
        parts.append(
            f'<g transform="translate({PAD} {y})"><rect width="{bw:.0f}" height="44" rx="22" fill="{cfg["accent"]}" '
            f'fill-opacity="0.14" stroke="{cfg["accent"]}" stroke-opacity="0.55" stroke-width="2"/>'
            f'<text x="20" y="29" font-size="20" font-weight="700" letter-spacing="2.4" fill="{cfg["accent"]}">{escape(badge)}</text></g>'
        )
        y += 44
    block_h = block_height(t_size, len(t_lines), s_size, len(s_lines))
    top = available_top + max(0.0, (available_h - block_h) / 2)

    ty = top + t_size
    tspans = "".join(
        f'<tspan x="{PAD}" y="{ty + i * t_size * 1.12:.0f}">{escape(line)}</tspan>' for i, line in enumerate(t_lines))
    parts.append(f'<text id="card-title" font-size="{t_size}" font-weight="800" letter-spacing="-1" fill="{cfg["fg"]}">{tspans}</text>')
    if s_lines:
        sy = ty + (len(t_lines) - 1) * t_size * 1.12 + 24 + s_size * 1.2
        tspans = "".join(
            f'<tspan x="{PAD}" y="{sy + i * s_size * 1.35:.0f}">{escape(line)}</tspan>' for i, line in enumerate(s_lines))
        parts.append(f'<text font-size="{s_size}" font-weight="500" fill="{cfg["fg"]}" fill-opacity="{SUBTITLE_OPACITY}">{tspans}</text>')

    if footer_h:
        fy = h - PAD
        if cfg.get("handle"):
            initial = escape(cfg["handle"].lstrip("@")[:1].upper() or "*")
            parts.append(
                f'<g transform="translate({PAD} {fy - 44})"><rect width="44" height="44" rx="12" fill="{cfg["accent"]}"/>'
                f'<text x="22" y="31" font-size="24" font-weight="800" text-anchor="middle" fill="{cfg["bg1"]}">{initial}</text>'
                f'<text x="60" y="30" font-size="24" font-weight="600" fill="{cfg["fg"]}">{escape(cfg["handle"])}</text></g>')
        if cfg.get("url"):
            parts.append(f'<text x="{w - PAD}" y="{fy - 14}" font-size="22" font-family="{MONO_STACK}" '
                         f'text-anchor="end" fill="{cfg["accent"]}">{escape(cfg["url"])}</text>')

    alt = cfg.get("alt") or ". ".join(v for v in (cfg["title"], cfg.get("subtitle", "")) if v)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="card-alt" font-family="{FONT_STACK}">\n'
        f'<title id="card-alt">{escape(alt)}</title>\n'
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{cfg["bg1"]}"/><stop offset="1" stop-color="{cfg["bg2"]}"/></linearGradient>'
        f'<radialGradient id="glow" cx="0.88" cy="0.12" r="0.6"><stop offset="0" stop-color="{cfg["accent"]}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{cfg["accent"]}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M48 0H0V48" fill="none" '
        f'stroke="{cfg["fg"]}" stroke-opacity="0.05" stroke-width="1"/></pattern></defs>\n'
        f'<rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="{w}" height="{h}" fill="url(#grid)"/>'
        f'<rect width="{w}" height="{h}" fill="url(#glow)"/>\n'
        + "\n".join(parts)
        + f'\n<rect y="{h - 8}" width="{w}" height="8" fill="{cfg["accent"]}"/>\n</svg>\n'
    )
    return svg, errors, warnings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render an OG/social card SVG.")
    ap.add_argument("--config", help="JSON file with any of the options below")
    ap.add_argument("--title")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--badge", default="")
    ap.add_argument("--handle", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--alt", default="", help="alt text; defaults to title + subtitle")
    ap.add_argument("--theme", choices=THEMES)
    for key in ("bg1", "bg2", "fg", "accent"):
        ap.add_argument(f"--{key}")
    ap.add_argument("--size", choices=SIZES)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--strict", action="store_true", help="fail on truncation or length warnings")
    args = ap.parse_args(argv)

    cfg: Dict[str, str] = {}
    if args.config:
        try:
            loaded = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot load config: {exc}", file=sys.stderr)
            return 2
        cfg.update({k: str(v) for k, v in loaded.items() if v is not None})
    theme_name = args.theme or cfg.get("theme") or "midnight"
    size_key = args.size or cfg.get("size") or "og"
    if theme_name not in THEMES or size_key not in SIZES:
        print(f"error: theme must be one of {', '.join(THEMES)}; size one of {', '.join(SIZES)}", file=sys.stderr)
        return 2
    merged: Dict[str, str] = dict(THEMES[theme_name])
    merged.update({k: v for k, v in cfg.items()})
    for key in ("title", "subtitle", "badge", "handle", "url", "alt", "bg1", "bg2", "fg", "accent"):
        val = getattr(args, key)
        if val:
            merged[key] = val
    merged = {k: re.sub(r"\s+", " ", v).strip() for k, v in merged.items()}
    if not merged.get("title"):
        print("error: --title (or config.title) is required", file=sys.stderr)
        return 2
    try:
        svg, errors, warnings = build(merged, size_key)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    if errors or (args.strict and warnings):
        print("FAIL: card not written; fix the issues above.", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({SIZES[size_key][0]}x{SIZES[size_key][1]}, {len(svg) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

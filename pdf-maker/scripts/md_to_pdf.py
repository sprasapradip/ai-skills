#!/usr/bin/env python3
"""Zero-dependency Markdown -> PDF compiler (Python 3.8+ standard library only).

Supports: YAML-style front matter (title/author/subject/lang), headings,
paragraphs, **bold**, *italic*, `code`, [links](https://...), nested bullet and
ordered lists, fenced code blocks, blockquotes, pipe tables, horizontal rules
and explicit page breaks (<!-- pagebreak -->). Output includes running header,
"Page X of Y" footer, document metadata, clickable links and heading bookmarks.

Uses the PDF base-14 fonts (Helvetica/Courier, WinAnsi encoding), so text is
limited to Latin-1/cp1252. For Devanagari, CJK, RTL or embedded images use the
Pro/Enterprise engines described in SKILL.md.

Usage:
    md_to_pdf.py INPUT.md|INPUT.json|- -o OUT.pdf [--title T] [--author A]
                 [--page-size a4|letter] [--base-size 10.5] [--strict]

Exit codes: 0 = written, 1 = written with --strict violations (file removed), 2 = usage/IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- fonts

# Adobe AFM advance widths for printable ASCII 32..126 (units per 1000 em).
_HELV = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015,
    667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778,
    722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333,
    556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556,
    333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)
_HELV_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975,
    722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778,
    722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333,
    556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611,
    389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
assert len(_HELV) == len(_HELV_BOLD) == 95
_CP1252_EXTRA = {0x91: 222, 0x92: 222, 0x93: 333, 0x94: 333, 0x95: 350, 0x96: 556, 0x97: 1000, 0x85: 1000}


def _widths(table: Sequence[int]) -> Dict[int, int]:
    return {32 + i: w for i, w in enumerate(table)}


WIDTHS = {"R": _widths(_HELV), "B": _widths(_HELV_BOLD)}
WIDTHS["I"], WIDTHS["BI"] = WIDTHS["R"], WIDTHS["B"]
FONT_RES = {"R": "F1", "B": "F2", "I": "F3", "BI": "F4", "C": "F5", "CB": "F6"}
BASE_FONTS = {
    "F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique",
    "F4": "Helvetica-BoldOblique", "F5": "Courier", "F6": "Courier-Bold",
}
PAGE_SIZES = {"a4": (595.28, 841.89), "letter": (612.0, 792.0)}

TEXT = (0.13, 0.13, 0.15)
MUTED = (0.38, 0.40, 0.45)
LINK = (0.05, 0.30, 0.75)
RULE = (0.80, 0.82, 0.86)
CODE_BG = (0.95, 0.96, 0.97)
HEAD_BG = (0.90, 0.92, 0.95)
STRIPE_BG = (0.97, 0.975, 0.98)


def encode(text: str) -> bytes:
    return text.encode("cp1252", errors="replace")


def text_width(text: str, style: str, size: float) -> float:
    if style.startswith("C"):
        return len(encode(text)) * 600 * size / 1000
    table = WIDTHS[style]
    return sum(table.get(b, _CP1252_EXTRA.get(b, 556)) for b in encode(text)) * size / 1000


def pdf_string(text: str) -> bytes:
    out = bytearray(b"(")
    for b in encode(text):
        if b in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([b])
        elif b < 32 or b > 126:
            out += b"\\%03o" % b
        else:
            out.append(b)
    out += b")"
    return bytes(out)


def pdf_text_string(text: str) -> bytes:
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"


# --------------------------------------------------------------------------- markdown

@dataclass
class Run:
    text: str
    style: str = "R"
    url: Optional[str] = None


@dataclass
class Block:
    kind: str
    runs: List[Run] = field(default_factory=list)
    level: int = 0
    lines: List[str] = field(default_factory=list)
    rows: List[List[List[Run]]] = field(default_factory=list)
    marker: str = ""


INLINE = re.compile(
    r"(?P<code>`[^`]+`)|(?P<link>\[(?P<ltext>[^\]]+)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\))"
    r"|(?P<img>!\[(?P<alt>[^\]]*)\]\([^)]*\))"
    r"|(?P<bi>\*\*\*(?P<bit>.+?)\*\*\*)|(?P<b>(\*\*|__)(?P<bt>.+?)(\*\*|__))"
    r"|(?P<i>(?<![\w*])[*_](?P<it>[^*_\s][^*_]*?)[*_](?![\w*]))"
)


class Warnings:
    def __init__(self) -> None:
        self.items: List[str] = []

    def add(self, msg: str) -> None:
        if msg not in self.items:
            self.items.append(msg)


def parse_inline(text: str, warn: Warnings, base: str = "R") -> List[Run]:
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", lambda m: "\x00%d\x00" % ord(m.group(1)), text)
    if re.search(r"<(?!!--)[a-zA-Z/][^>]*>", text):
        warn.add("Raw HTML tags were stripped; the stdlib engine renders Markdown only.")
        text = re.sub(r"<br\s*/?>", " ", text)
        text = re.sub(r"<[^>]+>", "", text)
    runs: List[Run] = []
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            runs.append(Run(text[pos:m.start()], base))
        if m.group("code"):
            runs.append(Run(m.group("code")[1:-1], "C"))
        elif m.group("img"):
            warn.add("Images are not embedded by the stdlib engine; rendered as [Image: alt]. Use the Pro engine.")
            runs.append(Run(f"[Image: {m.group('alt') or 'untitled'}]", "I"))
        elif m.group("link"):
            url = m.group("url")
            runs.extend(Run(r.text, r.style, url) for r in parse_inline(m.group("ltext"), warn, base))
        elif m.group("bi"):
            runs.append(Run(m.group("bit"), "BI"))
        elif m.group("b"):
            inner = "BI" if base == "I" else "B"
            runs.extend(parse_inline(m.group("bt"), warn, inner))
        elif m.group("i"):
            runs.append(Run(m.group("it"), "BI" if base == "B" else "I"))
        pos = m.end()
    if pos < len(text):
        runs.append(Run(text[pos:], base))
    for r in runs:
        r.text = re.sub(r"\x00(\d+)\x00", lambda m: chr(int(m.group(1))), r.text)
    return [r for r in runs if r.text]


def split_front_matter(src: str) -> Tuple[Dict[str, str], str]:
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", src, flags=re.S)
    if not m:
        return {}, src
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, src[m.end():]


def split_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def parse_markdown(src: str, warn: Warnings) -> List[Block]:
    lines = src.replace("\r\n", "\n").replace("\t", "    ").split("\n")
    blocks: List[Block] = []
    para: List[str] = []
    i = 0

    def flush() -> None:
        if para:
            blocks.append(Block("para", parse_inline(" ".join(s.strip() for s in para), warn)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        fence = re.match(r"^\s*(```|~~~)", line)
        if fence:
            flush()
            code: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                code.append(lines[i])
                i += 1
            if i >= len(lines):
                warn.add("Unclosed code fence; treated remainder of document as code.")
            blocks.append(Block("code", lines=code))
            i += 1
            continue
        if not stripped:
            flush()
            i += 1
            continue
        if re.fullmatch(r"<!--\s*pagebreak\s*-->|\\pagebreak|\\newpage", stripped):
            flush()
            blocks.append(Block("pagebreak"))
            i += 1
            continue
        if stripped.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        h = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", stripped)
        if h:
            flush()
            blocks.append(Block("heading", parse_inline(h.group(2), warn), level=len(h.group(1))))
            i += 1
            continue
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", stripped):
            flush()
            blocks.append(Block("hr"))
            i += 1
            continue
        if "|" in stripped and i + 1 < len(lines) and re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", lines[i + 1].strip()):
            flush()
            header = split_row(stripped)
            rows = [header]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            width = len(header)
            for r in rows:
                if len(r) != width:
                    warn.add("Table row with mismatched column count was padded/truncated.")
            norm = [(r + [""] * width)[:width] for r in rows]
            blocks.append(Block("table", rows=[[parse_inline(c, warn) for c in r] for r in norm]))
            continue
        if stripped.startswith(">"):
            flush()
            quote: List[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(Block("quote", parse_inline(" ".join(quote), warn, "I")))
            continue
        li = re.match(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$", line)
        if li:
            flush()
            indent = len(li.group(1))
            marker = li.group(2)
            text = [li.group(3)]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^\s*([-*+]|\d{1,9}[.)])\s+", lines[i]) \
                    and len(lines[i]) - len(lines[i].lstrip()) > indent:
                text.append(lines[i].strip())
                i += 1
            task = re.match(r"^\[( |x|X)\]\s+(.*)$", " ".join(text))
            body = " ".join(text)
            if task:
                marker = "[x]" if task.group(1).lower() == "x" else "[ ]"
                body = task.group(2)
            elif not marker[0].isdigit():
                marker = "•"
            else:
                marker = marker[:-1] + "."
            blocks.append(Block("item", parse_inline(body, warn), level=min(indent // 2, 4), marker=marker))
            continue
        para.append(line)
        i += 1
    flush()
    return blocks


# --------------------------------------------------------------------------- layout

@dataclass
class Page:
    ops: List[bytes] = field(default_factory=list)
    links: List[Tuple[Tuple[float, float, float, float], str]] = field(default_factory=list)


class Renderer:
    def __init__(self, size: Tuple[float, float], base: float, title: str) -> None:
        self.w, self.h = size
        self.margin = 54.0
        self.base = base
        self.leading = base * 1.45
        self.title = title
        self.top = self.h - self.margin - 14
        self.bottom = self.margin + 16
        self.left = self.margin
        self.right = self.w - self.margin
        self.pages: List[Page] = []
        self.outline: List[Tuple[str, int, float, int]] = []
        self.y = 0.0
        self.new_page()

    # -- primitives
    @property
    def page(self) -> Page:
        return self.pages[-1]

    def new_page(self) -> None:
        self.pages.append(Page())
        self.y = self.top

    def ensure(self, height: float) -> None:
        if self.y - height < self.bottom:
            self.new_page()

    def color(self, rgb: Sequence[float], stroke: bool = False) -> bytes:
        return ("%.3f %.3f %.3f %s" % (*rgb, "RG" if stroke else "rg")).encode()

    def rect(self, x: float, y: float, w: float, h: float, rgb: Sequence[float]) -> None:
        self.page.ops.append(self.color(rgb) + b" %.2f %.2f %.2f %.2f re f" % (x, y, w, h))

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb: Sequence[float] = RULE, width: float = 0.6) -> None:
        self.page.ops.append(self.color(rgb, True) + b" %.2f w %.2f %.2f m %.2f %.2f l S" % (width, x1, y1, x2, y2))

    def text(self, x: float, y: float, s: str, style: str, size: float, rgb: Sequence[float] = TEXT, page: Optional[Page] = None) -> None:
        target = page or self.page
        target.ops.append(
            b"BT " + self.color(rgb) + b" /%s %.2f Tf 1 0 0 1 %.2f %.2f Tm " % (FONT_RES[style].encode(), size, x, y)
            + pdf_string(s) + b" Tj ET"
        )

    # -- wrapping
    def wrap(self, runs: List[Run], width: float, size: float) -> List[List[Tuple[str, str, Optional[str], float]]]:
        tokens: List[Tuple[str, str, Optional[str]]] = []
        for r in runs:
            for part in re.split(r"(\s+)", r.text):
                if part:
                    tokens.append((" " if part.isspace() else part, r.style, r.url))
        lines: List[List[Tuple[str, str, Optional[str], float]]] = [[]]
        used = 0.0
        for tok, style, url in tokens:
            if tok == " ":
                if lines[-1]:
                    w = text_width(" ", style, size)
                    lines[-1].append((" ", style, url, w))
                    used += w
                continue
            w = text_width(tok, style, size)
            if used + w > width and lines[-1]:
                while lines[-1] and lines[-1][-1][0] == " ":
                    used -= lines[-1].pop()[3]
                lines.append([])
                used = 0.0
            while w > width:  # hard-break a single over-long token
                cut = len(tok)
                while cut > 1 and text_width(tok[:cut], style, size) > width:
                    cut -= 1
                lines[-1].append((tok[:cut], style, url, text_width(tok[:cut], style, size)))
                lines.append([])
                tok = tok[cut:]
                w = text_width(tok, style, size)
            lines[-1].append((tok, style, url, w))
            used += w
        if lines and lines[-1] and lines[-1][-1][0] == " ":
            lines[-1].pop()
        return [ln for ln in lines if ln] or [[]]

    def draw_line(self, line, x: float, y: float, size: float, rgb: Sequence[float]) -> None:
        for tok, style, url, w in line:
            col = LINK if url else rgb
            self.text(x, y, tok, style, size, col)
            if url and re.match(r"^(https?://|mailto:)", url):
                self.page.links.append(((x, y - 2, x + w, y + size), url))
                if tok != " ":
                    self.line(x, y - 1.5, x + w, y - 1.5, LINK, 0.4)
            x += w

    def flow(self, runs: List[Run], x: float, size: float, rgb: Sequence[float] = TEXT, after: float = 0.0, keep: int = 2) -> None:
        lines = self.wrap(runs, self.right - x, size)
        leading = size * 1.45
        if len(lines) > 1 and self.y - leading * min(keep, len(lines)) < self.bottom:
            self.new_page()
        for ln in lines:
            self.ensure(leading)
            self.y -= leading
            self.draw_line(ln, x, self.y + (leading - size) / 2, size, rgb)
        self.y -= after

    # -- blocks
    def render(self, blocks: List[Block]) -> None:
        sizes = {1: 18.0, 2: 14.5, 3: 12.5}
        prev = ""
        for idx, b in enumerate(blocks):
            if b.kind == "heading":
                size = sizes.get(b.level, self.base + 0.5)
                if idx == 0 and b.level == 1:
                    size = 24.0
                self.ensure(size * 1.5 + self.leading * 3)
                if self.y < self.top:
                    self.y -= size * 0.8
                plain = "".join(r.text for r in b.runs)
                if b.level <= 3:
                    self.outline.append((plain, len(self.pages) - 1, self.y, b.level))
                bold = [Run(r.text, "BI" if r.style in ("I", "BI") else ("C" if r.style == "C" else "B"), r.url) for r in b.runs]
                self.flow(bold, self.left, size, TEXT, after=size * 0.45, keep=1)
                if b.level <= 2:
                    self.line(self.left, self.y + size * 0.2, self.right, self.y + size * 0.2, RULE, 0.8 if b.level == 1 else 0.5)
                    self.y -= 4
            elif b.kind == "para":
                self.flow(b.runs, self.left, self.base, after=self.leading * 0.55)
            elif b.kind == "item":
                indent = self.left + 14 + b.level * 16
                lines = self.wrap(b.runs, self.right - indent, self.base)
                self.ensure(self.leading * min(2, len(lines)))
                marker_x = indent - 4 - text_width(b.marker, "R", self.base)
                self.text(marker_x, self.y - self.leading + (self.leading - self.base) / 2, b.marker, "R", self.base)
                self.flow(b.runs, indent, self.base, after=self.leading * 0.15)
                nxt = blocks[idx + 1].kind if idx + 1 < len(blocks) else ""
                if nxt != "item":
                    self.y -= self.leading * 0.4
            elif b.kind == "quote":
                start_page, start_y = len(self.pages), self.y
                self.flow(b.runs, self.left + 14, self.base, MUTED, after=0)
                if len(self.pages) == start_page:
                    self.line(self.left + 3, start_y - 2, self.left + 3, self.y - 3, RULE, 2.5)
                self.y -= self.leading * 0.6
            elif b.kind == "code":
                self.render_code(b.lines)
            elif b.kind == "table":
                self.render_table(b.rows)
            elif b.kind == "hr":
                self.ensure(self.leading)
                self.y -= self.leading * 0.5
                self.line(self.left, self.y, self.right, self.y, RULE, 0.8)
                self.y -= self.leading * 0.5
            elif b.kind == "pagebreak" and prev != "pagebreak" and self.y < self.top:
                self.new_page()
            prev = b.kind

    def render_code(self, lines: List[str]) -> None:
        size = self.base - 1.5
        leading = size * 1.4
        pad = 6.0
        max_chars = max(10, int((self.right - self.left - 2 * pad) / (0.6 * size)))
        wrapped: List[str] = []
        for ln in lines or [""]:
            while len(ln) > max_chars:
                wrapped.append(ln[:max_chars])
                ln = "  " + ln[max_chars:]
            wrapped.append(ln)
        self.ensure(leading * min(3, len(wrapped)) + pad * 2)
        self.rect(self.left, self.y - pad, self.right - self.left, pad, CODE_BG)
        self.y -= pad
        for ln in wrapped:
            if self.y - leading < self.bottom:
                self.new_page()
            self.rect(self.left, self.y - leading, self.right - self.left, leading, CODE_BG)
            self.y -= leading
            self.text(self.left + pad, self.y + (leading - size) / 2 + 0.5, ln, "C", size)
        self.rect(self.left, self.y - pad, self.right - self.left, pad, CODE_BG)
        self.y -= pad + self.leading * 0.6

    def render_table(self, rows: List[List[List[Run]]]) -> None:
        size = self.base - 1
        pad = 5.0
        leading = size * 1.4
        cols = len(rows[0])
        avail = self.right - self.left
        natural = [max(sum(text_width(r.text, "B" if ri == 0 else r.style, size) for r in row[c]) + 2 * pad
                       for ri, row in enumerate(rows)) for c in range(cols)]
        floor = min(avail / cols, 60.0)
        widths = [max(floor, n) for n in natural]
        if sum(widths) > avail:
            flexible = sum(w - floor for w in widths) or 1
            excess = sum(widths) - avail
            widths = [w - (w - floor) / flexible * excess for w in widths]
        else:
            extra = (avail - sum(widths)) / cols
            widths = [w + extra for w in widths]

        def cell_lines(row: List[List[Run]], header: bool):
            out = []
            for c, runs in enumerate(row):
                runs = [Run(r.text, "B" if header and r.style == "R" else r.style, r.url) for r in runs]
                out.append(self.wrap(runs, widths[c] - 2 * pad, size))
            return out

        def draw_row(row: List[List[Run]], ri: int) -> None:
            header = ri == 0
            cells = cell_lines(row, header)
            height = max(len(c) for c in cells) * leading + 2 * pad
            if self.y - height < self.bottom:
                self.new_page()
                if not header:
                    draw_row(rows[0], 0)
            top = self.y
            fill = HEAD_BG if header else (STRIPE_BG if ri % 2 == 0 else None)
            if fill:
                self.rect(self.left, top - height, avail, height, fill)
            x = self.left
            for c, lines in enumerate(cells):
                y = top - pad
                for ln in lines:
                    y -= leading
                    self.draw_line(ln, x + pad, y + (leading - size) / 2, size, TEXT)
                x += widths[c]
            self.line(self.left, top - height, self.right, top - height, RULE, 0.8 if header else 0.4)
            self.y = top - height

        self.ensure(self.leading * 3)
        self.line(self.left, self.y, self.right, self.y, RULE, 0.8)
        for ri, row in enumerate(rows):
            draw_row(row, ri)
        self.y -= self.leading * 0.8

    def decorate(self, footer_note: str) -> None:
        total = len(self.pages)
        for n, page in enumerate(self.pages, 1):
            hy = self.h - self.margin + 2
            if self.title:
                self.text(self.left, hy, self.title[:90], "R", 8, MUTED, page)
            page.ops.append(self.color(RULE, True) + b" 0.5 w %.2f %.2f m %.2f %.2f l S" % (self.left, hy - 5, self.right, hy - 5))
            fy = self.margin - 4
            page.ops.append(self.color(RULE, True) + b" 0.5 w %.2f %.2f m %.2f %.2f l S" % (self.left, fy + 12, self.right, fy + 12))
            label = f"Page {n} of {total}"
            self.text(self.right - text_width(label, "R", 8), fy, label, "R", 8, MUTED, page)
            if footer_note:
                self.text(self.left, fy, footer_note[:80], "R", 8, MUTED, page)


# --------------------------------------------------------------------------- writer

def build_pdf(r: Renderer, meta: Dict[str, str], compress: bool) -> bytes:
    objects: Dict[int, bytes] = {}
    counter = [0]

    def alloc() -> int:
        counter[0] += 1
        return counter[0]

    catalog, pages_id, info = alloc(), alloc(), alloc()
    font_ids = {}
    for res, base in BASE_FONTS.items():
        fid = alloc()
        font_ids[res] = fid
        objects[fid] = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % base.encode()
    font_dict = b"<< " + b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in font_ids.items()) + b" >>"

    page_ids: List[int] = []
    for page in r.pages:
        pid, cid = alloc(), alloc()
        page_ids.append(pid)
        stream = b"\n".join(page.ops)
        if compress:
            stream = zlib.compress(stream, 9)
            objects[cid] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"
        else:
            objects[cid] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        annots = []
        for (x1, y1, x2, y2), url in page.links:
            aid = alloc()
            annots.append(aid)
            objects[aid] = (b"<< /Type /Annot /Subtype /Link /Rect [%.2f %.2f %.2f %.2f] /Border [0 0 0] "
                            b"/A << /S /URI /URI %s >> >>" % (x1, y1, x2, y2, pdf_string(url)))
        annot_ref = b" /Annots [" + b" ".join(b"%d 0 R" % a for a in annots) + b"]" if annots else b""
        objects[pid] = (b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                        b"/Resources << /Font %s >>%s >>" % (pages_id, r.w, r.h, cid, font_dict, annot_ref))

    objects[pages_id] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % p for p in page_ids), len(page_ids))

    outline_ref = b""
    if r.outline:
        root = alloc()
        item_ids = [alloc() for _ in r.outline]
        for n, (title, page_idx, y, _lvl) in enumerate(r.outline):
            links = b""
            if n > 0:
                links += b" /Prev %d 0 R" % item_ids[n - 1]
            if n < len(item_ids) - 1:
                links += b" /Next %d 0 R" % item_ids[n + 1]
            objects[item_ids[n]] = (b"<< /Title %s /Parent %d 0 R%s /Dest [%d 0 R /XYZ 0 %.2f 0] >>"
                                    % (pdf_text_string(title), root, links, page_ids[page_idx], y + 24))
        objects[root] = b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>" % (
            item_ids[0], item_ids[-1], len(item_ids))
        outline_ref = b" /Outlines %d 0 R /PageMode /UseOutlines" % root

    lang = meta.get("lang", "en")
    objects[catalog] = (b"<< /Type /Catalog /Pages %d 0 R /Lang %s /ViewerPreferences << /DisplayDocTitle true >>%s >>"
                        % (pages_id, pdf_string(lang), outline_ref))
    now = _dt.datetime.now(_dt.timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
    info_fields = {"Title": meta.get("title", ""), "Author": meta.get("author", ""),
                   "Subject": meta.get("subject", ""), "Keywords": meta.get("keywords", ""),
                   "Creator": "pdf-maker/md_to_pdf.py", "Producer": "pdf-maker stdlib engine 2.0"}
    objects[info] = (b"<< " + b" ".join(b"/%s %s" % (k.encode(), pdf_text_string(v)) for k, v in info_fields.items() if v)
                     + b" /CreationDate (%s) /ModDate (%s) >>" % (now.encode(), now.encode()))

    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for oid in range(1, counter[0] + 1):
        offsets[oid] = len(out)
        out += b"%d 0 obj\n" % oid + objects[oid] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (counter[0] + 1)
    for oid in range(1, counter[0] + 1):
        out += b"%010d 00000 n \n" % offsets[oid]
    doc_id = hashlib.md5(bytes(out)).hexdigest().encode()
    out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R /ID [<%s> <%s>] >>\nstartxref\n%d\n%%%%EOF\n"
            % (counter[0] + 1, catalog, info, doc_id, doc_id, xref))
    return bytes(out)


# --------------------------------------------------------------------------- CLI

def load_source(path: str) -> Tuple[Dict[str, str], str]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
    if path.lower().endswith(".json"):
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            raise ValueError('JSON input must be an object with a string "content" field (Markdown).')
        meta = {k: str(v) for k, v in data.items() if k != "content" and isinstance(v, (str, int, float))}
        return meta, data["content"]
    return split_front_matter(raw)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compile Markdown to PDF with the Python standard library.")
    ap.add_argument("input", help="Markdown file, JSON file ({title, author, content}) or - for stdin")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--title")
    ap.add_argument("--author")
    ap.add_argument("--subject")
    ap.add_argument("--lang")
    ap.add_argument("--footer-note", default="", help="left footer text, e.g. 'Confidential'")
    ap.add_argument("--page-size", choices=PAGE_SIZES, default="a4")
    ap.add_argument("--base-size", type=float, default=10.5)
    ap.add_argument("--no-compress", action="store_true")
    ap.add_argument("--strict", action="store_true", help="fail on lossy rendering (unsupported glyphs, images, HTML)")
    args = ap.parse_args(argv)

    if not 8 <= args.base_size <= 14:
        print("error: --base-size must be between 8 and 14 pt", file=sys.stderr)
        return 2
    try:
        meta, body = load_source(args.input)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not body.strip():
        print("error: input contains no content to render", file=sys.stderr)
        return 2
    for key in ("title", "author", "subject", "lang"):
        if getattr(args, key):
            meta[key] = getattr(args, key)

    warn = Warnings()
    blocks = parse_markdown(body, warn)
    if not meta.get("title"):
        first_h1 = next((b for b in blocks if b.kind == "heading" and b.level == 1), None)
        meta["title"] = "".join(r.text for r in first_h1.runs) if first_h1 else Path(args.output).stem
    if blocks and not (blocks[0].kind == "heading" and blocks[0].level == 1):
        blocks.insert(0, Block("heading", [Run(meta["title"])], level=1))

    unsupported = sorted({ch for ch in body if ord(ch) > 127 and ch.encode("cp1252", errors="ignore") == b""})
    if unsupported:
        sample = "".join(unsupported[:12])
        warn.add(f"{len(unsupported)} character(s) outside cp1252 rendered as '?' (e.g. {sample!r}). Use the Pro engine with an embedded TTF.")

    renderer = Renderer(PAGE_SIZES[args.page_size], args.base_size, meta["title"])
    renderer.render(blocks)
    renderer.decorate(args.footer_note)
    pdf = build_pdf(renderer, meta, not args.no_compress)

    out = Path(args.output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pdf)
    except OSError as exc:
        print(f"error: cannot write {out}: {exc}", file=sys.stderr)
        return 2
    for w in warn.items:
        print(f"warning: {w}", file=sys.stderr)
    if args.strict and warn.items:
        out.unlink()
        print("FAIL: --strict and lossy rendering detected; output removed.", file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(renderer.pages)} page(s), {len(pdf) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

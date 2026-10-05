#!/usr/bin/env python3
"""Structural and content verification for generated PDFs (standard library only).

Checks: PDF header and %%EOF trailer, xref offsets (classic xref tables),
page count, document metadata (Title), file-size budget, and decompressed
content streams for leaked Markdown syntax, placeholder text and
replacement glyphs ('?' runs) that indicate lossy encoding.

Usage:
    verify_pdf.py FILE.pdf [--expect-pages N | --min-pages N] [--max-kb 5000]
                  [--require-title] [--json]

Exit codes: 0 = pass, 1 = verification failed, 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional

LEAK_PATTERNS = {
    "markdown-bold": rb"\(\s*[^()]*\*\*[^()]+\*\*",
    "markdown-heading": rb"\(\s*#{1,6} [^()]+\)",
    "markdown-link": rb"\]\\?\(https?:",
    "markdown-fence": rb"\(\s*```",
    "placeholder": rb"(?i)lorem ipsum|\bTODO\b|\bFIXME\b|\[placeholder\]",
    "replacement-glyphs": rb"\(\?{3,}\)|\?\?\?\?",
}


def streams(data: bytes) -> List[bytes]:
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", m.end())
        if end == -1:
            continue
        chunk = data[m.end():end].rstrip(b"\r\n")
        try:
            out.append(zlib.decompress(chunk))
        except zlib.error:
            out.append(chunk)
    return out


def check_xref(data: bytes) -> Optional[str]:
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", data)
    if not m:
        return "startxref/%%EOF trailer missing or malformed"
    pos = int(m.group(1))
    if data[pos:pos + 4] != b"xref":
        # Cross-reference streams (PDF 1.5+) are valid; only classic tables are verified.
        return None if re.match(rb"\d+ \d+ obj", data[pos:pos + 20]) else "startxref does not point at an xref section"
    header = re.match(rb"xref\s+(\d+)\s+(\d+)\s+", data[pos:])
    if not header:
        return "xref header malformed"
    first, count = int(header.group(1)), int(header.group(2))
    body = data[pos + header.end():]
    for n in range(count):
        entry = body[n * 20:(n + 1) * 20]
        if len(entry) < 18:
            return "xref table truncated"
        offset, _gen, kind = entry[:10], entry[11:16], entry[17:18]
        if kind == b"n":
            oid = first + n
            off = int(offset)
            if not re.match(rb"%d\s+\d+\s+obj" % oid, data[off:off + 20]):
                return f"xref offset for object {oid} is wrong ({off})"
    return None


def verify(path: Path, args: argparse.Namespace) -> Dict[str, object]:
    data = path.read_bytes()
    errors: List[str] = []
    warnings: List[str] = []
    if not data.startswith(b"%PDF-"):
        errors.append("missing %PDF- header")
    if b"%%EOF" not in data[-1024:]:
        errors.append("missing %%EOF near end of file (truncated?)")
    xref_issue = check_xref(data)
    if xref_issue:
        errors.append(xref_issue)

    page_objs = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    counts = [int(c) for c in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data)]
    counts += [int(c) for c in re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", data)]
    pages = max(counts) if counts else page_objs
    if pages == 0:
        errors.append("document has no pages")
    if args.expect_pages is not None and pages != args.expect_pages:
        errors.append(f"expected {args.expect_pages} page(s), found {pages}")
    if args.min_pages is not None and pages < args.min_pages:
        errors.append(f"expected at least {args.min_pages} page(s), found {pages}")

    title = None
    m = re.search(rb"/Title\s*(<FEFF[0-9A-Fa-f]*>|\((?:\\.|[^\\)])*\))", data)
    if m:
        raw = m.group(1)
        title = (bytes.fromhex(raw[5:-1].decode()).decode("utf-16-be", "replace") if raw.startswith(b"<FEFF")
                 else raw[1:-1].decode("latin-1"))
    if args.require_title and not title:
        errors.append("document metadata /Title is missing")

    size_kb = len(data) / 1024
    if size_kb > args.max_kb:
        errors.append(f"file is {size_kb:.0f} KB; budget is {args.max_kb} KB")

    for content in streams(data):
        for rule, pattern in LEAK_PATTERNS.items():
            if re.search(pattern, content):
                msg = f"content stream contains {rule}"
                (warnings if rule == "replacement-glyphs" else errors).append(msg)
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return {"file": str(path), "pages": pages, "title": title, "size_kb": round(size_kb, 1),
            "errors": errors, "warnings": warnings, "passed": not errors}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verify a generated PDF offline.")
    ap.add_argument("file")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--expect-pages", type=int)
    group.add_argument("--min-pages", type=int)
    ap.add_argument("--max-kb", type=int, default=5000)
    ap.add_argument("--require-title", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        result = verify(path, args)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for e in result["errors"]:  # type: ignore[union-attr]
            print(f"ERROR {e}")
        for w in result["warnings"]:  # type: ignore[union-attr]
            print(f"WARN  {w}")
        print(f"{'PASS' if result['passed'] else 'FAIL'}: {path} | pages={result['pages']} "
              f"size={result['size_kb']}KB title={result['title']!r}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

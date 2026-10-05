#!/usr/bin/env python3
"""Zero-dependency code-smell, security and cleanliness scanner (Python 3.8+ stdlib).

Python files get AST analysis (unused imports, nesting depth, function size,
parameter count, mutable defaults, bare/silent excepts, eval/exec, shell=True,
unsafe deserialisation, missing type hints). Every language (Python, PHP,
JavaScript, TypeScript, plus generic C-like) gets line heuristics: debug
leftovers, hardcoded secrets, SQL built by concatenation, commented-out code,
TODO/FIXME, brace-nesting depth, long lines, trailing whitespace.

Usage:
    scan_smells.py FILE [FILE...] [--lang auto|python|php|js|ts|generic] [--json]
                   [--fail-on error|warn|never]
    scan_smells.py --compare BEFORE AFTER [--lang ...]   # regression gate for a refactor

Exit codes: 0 = clean (per --fail-on), 1 = findings at/above threshold or regression, 2 = usage/IO error.

Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

EXT_LANG = {".py": "python", ".php": "php", ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
            ".ts": "ts", ".tsx": "ts", ".vue": "js", ".svelte": "js"}
MAX_NESTING = 4
MAX_FUNC_LINES = 60
MAX_PARAMS = 5
MAX_LINE = 120


@dataclass
class Finding:
    severity: str  # error | warn | info
    rule: str
    line: int
    message: str


SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "private key"),
    (r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}", "GitHub token"),
    (r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}", "API secret key"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"(?i)\b(password|passwd|secret|api_?key|access_?token|auth_?token)\b[\"']?\s*(=|=>|:)\s*[\"'][^\"'\s]{6,}[\"']",
     "hardcoded credential"),
]
DEBUG_PATTERNS = {
    "python": [r"\bbreakpoint\(\)", r"\bpdb\.set_trace\(\)", r"^\s*ic\("],
    "php": [r"\bvar_dump\s*\(", r"\bprint_r\s*\(", r"(?<![\w>:$])dd\s*\(", r"(?<![\w>:$])dump\s*\(", r"\bray\s*\(",
            r"\bdie\s*\(\s*['\"]", r"\bexit\s*\(\s*['\"]"],
    "js": [r"\bconsole\.(log|debug|trace|dir)\s*\(", r"^\s*debugger\s*;?"],
}
DEBUG_PATTERNS["ts"] = DEBUG_PATTERNS["js"]
SQL_CONCAT = re.compile(
    r"[\"'`]\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE)\b[^\"'`]*[\"'`]\s*(\.|\+)\s*\$?\w"
    r"|[\"'`](SELECT|INSERT|UPDATE|DELETE)\b[^\"'`]*(\$\{|\{\$|\$[a-z_])", re.I)
COMMENTED_CODE = re.compile(
    r"^\s*(#|//)\s*(if\s*\(|for\s*\(|while\s*\(|return\b|\$\w+\s*=|(var|let|const)\s+\w+\s*=|def \w+\(|"
    r"function\s+\w+\s*\(|import\s+\w|from\s+\w+\s+import|\w+\(.*\)\s*;\s*$|echo\s|[\w.\[\]]+\s*=\s*[\w.]+\()")


def detect_lang(path: str, forced: str) -> str:
    if forced != "auto":
        return forced
    return EXT_LANG.get(Path(path).suffix.lower(), "generic")


def strip_strings(line: str) -> str:
    return re.sub(r"\"(\\.|[^\"\\])*\"|'(\\.|[^'\\])*'|`(\\.|[^`\\])*`", '""', line)


# --------------------------------------------------------------------------- generic


def scan_lines(src: str, lang: str) -> List[Finding]:
    out: List[Finding] = []
    depth = 0
    max_depth_line = (0, 0)
    in_block_comment = False
    comment_lines = 0
    lines = src.splitlines()
    for n, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if lang != "python":
            if in_block_comment:
                comment_lines += 1
                if "*/" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith("/*"):
                comment_lines += 1
                in_block_comment = "*/" not in stripped
                continue
        if stripped.startswith(("#", "//")) and not stripped.startswith("#!"):
            comment_lines += 1
        if len(line) > MAX_LINE:
            out.append(Finding("info", "long-line", n, f"{len(line)} chars (max {MAX_LINE})."))
        if line != line.rstrip():
            out.append(Finding("info", "trailing-whitespace", n, "Trailing whitespace."))
        if re.search(r"(#|//|/\*|^\s*\*).*\b(TODO|FIXME|HACK|XXX)\b", strip_strings(line)):
            out.append(Finding("warn", "todo", n, "Unresolved TODO/FIXME marker."))
        if COMMENTED_CODE.match(line):
            out.append(Finding("warn", "commented-code", n, "Commented-out code; delete it (VCS keeps history)."))
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line) and not re.search(r"(?i)(env\(|getenv|os\.environ|process\.env|example|changeme|<.*>)", line):
                out.append(Finding("error", "hardcoded-secret", n, f"Possible {label} committed in source."))
                break
        for pattern in DEBUG_PATTERNS.get(lang, []):
            if re.search(pattern, line) and not stripped.startswith(("#", "//", "*")):
                out.append(Finding("warn", "debug-leftover", n, f"Debug statement: {stripped[:60]}"))
                break
        if SQL_CONCAT.search(line):
            out.append(Finding("error", "sql-injection", n, "SQL built by string concatenation/interpolation; use bound parameters."))
        if re.search(r"(?<![\w.$>])eval\s*\(", strip_strings(line)):
            out.append(Finding("error", "eval", n, "eval() executes arbitrary code."))

        code = strip_strings(line)
        if lang in ("js", "ts"):
            if re.search(r"(?<![=!<>])==(?!=)|!=(?!=)", code) and not re.search(r"==\s*null\b", code):
                out.append(Finding("warn", "loose-equality", n, "Use ===/!== instead of ==/!=."))
            if re.match(r"\s*var\s+\w", code):
                out.append(Finding("warn", "var", n, "Use const/let instead of var."))
            if re.search(r"\.innerHTML\s*=|dangerouslySetInnerHTML", code):
                out.append(Finding("warn", "xss-sink", n, "Unsafe HTML sink; use textContent or sanitize."))
        if lang == "ts" and re.search(r":\s*any\b|\bas\s+any\b|<any>", code):
            out.append(Finding("warn", "ts-any", n, "Avoid `any`; use a precise type or `unknown`."))
        if lang == "ts" and re.search(r"@ts-ignore", line):
            out.append(Finding("warn", "ts-ignore", n, "@ts-ignore hides type errors; prefer @ts-expect-error with reason."))
        if lang == "php":
            if re.search(r"(?<![\w$])@\$?\w+\s*\(|(?<![\w$])@\$\w+", code):
                out.append(Finding("warn", "error-suppression", n, "@ suppresses errors; handle them explicitly."))
            if re.search(r"\bextract\s*\(", code):
                out.append(Finding("error", "extract", n, "extract() injects variables into scope."))
            if re.search(r"\b(echo|print)\b[^;]*\$_(GET|POST|REQUEST|COOKIE)", line):
                out.append(Finding("error", "xss", n, "Echoing request input without escaping (htmlspecialchars/esc_html)."))
            if re.search(r"\bmd5\s*\(|\bsha1\s*\(", code) and re.search(r"(?i)pass", line):
                out.append(Finding("error", "weak-hash", n, "md5/sha1 for passwords; use password_hash()."))
            if re.search(r"\bunserialize\s*\(\s*\$_", code):
                out.append(Finding("error", "unsafe-unserialize", n, "unserialize() on user input enables object injection."))

        if lang != "python":
            depth = max(0, depth + code.count("{") - code.count("}"))
            if depth > max_depth_line[0]:
                max_depth_line = (depth, n)
    if lang != "python" and max_depth_line[0] > MAX_NESTING + 1:
        out.append(Finding("warn", "deep-nesting", max_depth_line[1],
                           f"Brace depth {max_depth_line[0]}; flatten with guard clauses / extraction."))
    if lang == "php" and src.lstrip().startswith("<?php") and "strict_types=1" not in src:
        out.append(Finding("warn", "strict-types", 1, "Missing declare(strict_types=1);"))
    if lang == "php" and "<?php" in src and re.search(r"\?>\s*\Z", src) and "<html" not in src.lower():
        out.append(Finding("warn", "closing-tag", len(lines), "Omit closing ?> in pure-PHP files (PSR-12)."))
    return out


# --------------------------------------------------------------------------- python AST


class PyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: List[Finding] = []
        self.imported: Dict[str, int] = {}
        self.used: Set[str] = set()
        self.all_names: Set[str] = set()
        self.is_cli = False

    def add(self, sev: str, rule: str, node: ast.AST, msg: str) -> None:
        self.findings.append(Finding(sev, rule, getattr(node, "lineno", 0), msg))

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            self.imported[(a.asname or a.name).split(".")[0]] = node.lineno

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__":
            return
        for a in node.names:
            if a.name == "*":
                self.add("warn", "star-import", node, f"from {node.module} import * pollutes the namespace.")
            else:
                self.imported[a.asname or a.name] = node.lineno

    def visit_Name(self, node: ast.Name) -> None:
        self.used.add(node.id)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                self.all_names |= {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        self.generic_visit(node)

    def _function(self, node) -> None:
        length = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1
        if length > MAX_FUNC_LINES:
            self.add("warn", "long-function", node, f"{node.name}() is {length} lines (max {MAX_FUNC_LINES}).")
        params = [a for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs if a.arg not in ("self", "cls")]
        if len(params) > MAX_PARAMS:
            self.add("warn", "too-many-params", node, f"{node.name}() takes {len(params)} params (max {MAX_PARAMS}); use a dataclass.")
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (
                    isinstance(default, ast.Call) and getattr(default.func, "id", "") in ("list", "dict", "set")):
                self.add("error", "mutable-default", default, f"Mutable default argument in {node.name}().")
        if not node.name.startswith("_"):
            missing = [a.arg for a in params if a.annotation is None]
            if missing or node.returns is None:
                self.add("info", "type-hints", node, f"{node.name}() lacks type hints ({', '.join(missing) or 'return'}).")
        depth = self._max_depth(node.body, 0)
        if depth > MAX_NESTING:
            self.add("warn", "deep-nesting", node, f"{node.name}() nests {depth} levels (max {MAX_NESTING}); use guard clauses.")
        self.generic_visit(node)

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def _max_depth(self, body: List[ast.stmt], depth: int) -> int:
        deepest = depth
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            nested = isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try))
            for field in ("body", "orelse", "finalbody", "handlers"):
                children = getattr(stmt, field, None)
                if not children:
                    continue
                if field == "handlers":
                    for h in children:
                        deepest = max(deepest, self._max_depth(h.body, depth + 1))
                    continue
                is_elif = field == "orelse" and len(children) == 1 and isinstance(children[0], ast.If)
                deepest = max(deepest, self._max_depth(children, depth if is_elif else depth + (1 if nested else 0)))
        return deepest

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add("error", "bare-except", node, "Bare except: catches SystemExit/KeyboardInterrupt.")
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.add("error", "silent-except", node, "Exception swallowed with pass; log or re-raise.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else "")
        base = node.func.value.id if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) else ""
        if name in ("eval", "exec") and not base:
            self.add("error", "eval", node, f"{name}() executes arbitrary code.")
        if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
            self.add("error", "shell-true", node, "subprocess with shell=True enables command injection.")
        if base in ("pickle", "marshal") and name in ("load", "loads"):
            self.add("error", "unsafe-deserialize", node, f"{base}.{name} on untrusted data executes code.")
        if base == "yaml" and name == "load" and not any(k.arg == "Loader" for k in node.keywords):
            self.add("error", "yaml-load", node, "yaml.load without SafeLoader; use yaml.safe_load.")
        if name == "print" and not base and not self.is_cli and not any(k.arg == "file" for k in node.keywords):
            self.add("warn", "debug-leftover", node, "print() in library code; use logging.")
        if base == "os" and name == "system":
            self.add("error", "os-system", node, "os.system(); use subprocess.run([...]) with an argument list.")
        if any(k.arg == "verify" and isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):
            self.add("error", "tls-verify", node, "TLS verification disabled (verify=False).")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                self.add("warn", "none-compare", node, "Use `is None` / `is not None`.")
        self.generic_visit(node)

    def finish(self, src: str) -> None:
        # Names referenced only in string annotations or docstrings still count as used.
        for name, line in self.imported.items():
            if name not in self.used and name not in self.all_names and not re.search(rf"[\"'][^\"']*\b{re.escape(name)}\b", src):
                self.findings.append(Finding("warn", "unused-import", line, f"'{name}' imported but unused."))


def scan_python(src: str) -> List[Finding]:
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [Finding("error", "syntax", exc.lineno or 0, f"SyntaxError: {exc.msg}")]
    v = PyVisitor()
    v.is_cli = bool(re.search(r"^if __name__ == ['\"]__main__['\"]", src, flags=re.M))
    v.visit(tree)
    v.finish(src)
    return v.findings


# --------------------------------------------------------------------------- driver


def scan(path: str, lang: str) -> Dict[str, object]:
    src = Path(path).read_text(encoding="utf-8", errors="replace")
    lang = detect_lang(path, lang)
    findings = scan_lines(src, lang)
    if lang == "python":
        findings += scan_python(src)
    unique = {(f.line, f.rule): f for f in findings}
    findings = sorted(unique.values(), key=lambda f: (f.line, f.rule))
    loc = sum(1 for ln in src.splitlines() if ln.strip())
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("error", "warn", "info")}
    return {"file": path, "lang": lang, "loc": loc, "counts": counts, "findings": [asdict(f) for f in findings]}


def print_report(result: Dict[str, object]) -> None:
    for f in result["findings"]:  # type: ignore[union-attr]
        print(f"{result['file']}:{f['line']}: {f['severity'].upper():5} {f['rule']:<20} {f['message']}")
    c = result["counts"]
    print(f"-- {result['file']} [{result['lang']}] loc={result['loc']} "
          f"errors={c['error']} warnings={c['warn']} info={c['info']}")  # type: ignore[index]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Scan source files for smells and security issues.")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--lang", default="auto", choices=["auto", "python", "php", "js", "ts", "generic"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", default="error", choices=["error", "warn", "never"])
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--max-nesting", type=int, default=MAX_NESTING)
    ap.add_argument("--max-func-lines", type=int, default=MAX_FUNC_LINES)
    ap.add_argument("--max-params", type=int, default=MAX_PARAMS)
    args = ap.parse_args(argv)
    globals().update(MAX_NESTING=args.max_nesting, MAX_FUNC_LINES=args.max_func_lines, MAX_PARAMS=args.max_params)

    try:
        if args.compare:
            before, after = (scan(p, args.lang) for p in args.compare)
            bc, ac = before["counts"], after["counts"]
            regress = ac["error"] > 0 or ac["warn"] > bc["warn"]  # type: ignore[index]
            if args.json:
                print(json.dumps({"before": before, "after": after, "regression": regress}, indent=2))
            else:
                print_report(after)
                for key in ("error", "warn", "info"):
                    print(f"   {key:<5} {bc[key]:>4} -> {ac[key]:<4} ({ac[key] - bc[key]:+d})")  # type: ignore[index]
                print(f"   loc   {before['loc']:>4} -> {after['loc']:<4} ({after['loc'] - before['loc']:+d})")  # type: ignore[operator]
                print("FAIL: refactor leaves errors or adds warnings" if regress else "PASS: no regressions")
            return 1 if regress else 0
        if not args.files:
            ap.error("provide FILE(s) or --compare BEFORE AFTER")
        results = [scan(p, args.lang) for p in args.files]
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        for r in results:
            print_report(r)
    if args.fail_on == "never":
        return 0
    keys = ("error",) if args.fail_on == "error" else ("error", "warn")
    return 1 if any(r["counts"][k] for r in results for k in keys) else 0  # type: ignore[index]


if __name__ == "__main__":
    sys.exit(main())

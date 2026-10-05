#!/usr/bin/env python3
"""Detect AI-writing tells and verify fact preservation (Python 3.8+ stdlib only).

scan     Score a text for AI tells: stock vocabulary, formulaic transitions and
         openers, filler/hedging, sycophantic closers, negative parallelisms,
         rule-of-three lists, em-dash density, and low sentence-length variance
         ("burstiness").
compare  Gate a rewrite: every number, date, URL, email, @handle, quoted span,
         code span and proper noun in ORIGINAL must survive in REWRITE, and no
         new numbers/URLs may be invented. Also reports tell reduction.

Usage:
    ai_tells.py scan FILE|- [--json] [--max-score 25]
    ai_tells.py compare ORIGINAL REWRITE [--json] [--max-length-delta 50]

Exit codes: 0 = pass, 1 = gate failed, 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

VOCAB = (
    "delve", "delves", "delving", "tapestry", "testament", "pivotal", "crucial", "seamless", "seamlessly",
    "spearhead", "beacon", "demystify", "fostering", "foster", "leverage", "leveraging", "utilize", "utilizing",
    "robust", "realm", "landscape", "embark", "navigate the", "navigating the", "unlock", "unleash",
    "game-changer", "game changer", "cutting-edge", "ever-evolving", "ever-changing", "paramount", "multifaceted",
    "intricate", "intricacies", "meticulous", "meticulously", "underscore", "underscores", "showcase", "showcasing",
    "bustling", "vibrant", "nestled", "holistic", "synergy", "elevate", "empower", "empowering", "harness",
    "streamline", "transformative", "revolutionize", "commendable", "noteworthy", "invaluable", "plethora",
    "myriad", "in the realm of", "a rich tapestry", "boasts", "resonate", "resonates", "endeavor", "garner",
    "align with", "key takeaway", "deep dive", "dive into", "journey", "enhance", "enhancing",
)
TRANSITIONS = (
    "furthermore", "moreover", "additionally", "in conclusion", "in summary", "to summarize", "overall",
    "ultimately", "notably", "importantly", "consequently", "thus", "hence", "indeed", "that being said",
    "with that said", "all in all", "first and foremost", "last but not least", "in essence",
)
FILLER = (
    "it is worth noting that", "it's worth noting that", "it is important to note", "it's important to note",
    "in today's fast-paced", "in today's digital", "in today's world", "in the ever-evolving", "when it comes to",
    "at the end of the day", "plays a crucial role", "plays a vital role", "plays a pivotal role",
    "serves as a", "stands as a", "a wide range of", "a variety of", "in order to", "due to the fact that",
    "it goes without saying", "needless to say", "the fact that", "whether you're a", "look no further",
    "has become increasingly", "not just about", "it can be said",
)
CLOSERS = (
    "i hope this helps", "let me know if", "feel free to", "happy to help", "great question",
    "certainly!", "absolutely!", "i'd be happy to", "as an ai",
)
HEDGES = ("arguably", "it seems", "potentially", "generally speaking", "to some extent", "in many ways", "can help")
NEG_PARALLEL = re.compile(r"\bnot (just|only|merely)\b[^.?!]{1,80}\bbut( also)?\b|\bit'?s not [^.?!]{1,60}[,;—-]+\s*it'?s\b", re.I)
TRIAD = re.compile(r"\b(\w+(?: \w+)?), (\w+(?: \w+)?),? and (\w+(?: \w+)?)\b")
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(\[])")


def words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9'’-]+", text)


def sentences(text: str) -> List[str]:
    flat = re.sub(r"\s+", " ", re.sub(r"```.*?```", " ", text, flags=re.S)).strip()
    return [s for s in SENT_SPLIT.split(flat) if len(words(s)) >= 2]


def count_phrases(text: str, phrases) -> Dict[str, int]:
    low = text.lower()
    hits = {}
    for p in phrases:
        n = len(re.findall(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", low))
        if n:
            hits[p] = n
    return hits


def scan(text: str) -> Dict[str, object]:
    wc = max(1, len(words(text)))
    sents = sentences(text)
    lengths = [len(words(s)) for s in sents]
    mean = statistics.mean(lengths) if lengths else 0.0
    stdev = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0
    cv = stdev / mean if mean else 0.0
    openers = [s.split()[0].lower().strip(",") for s in sents if s.split()]
    repeated_openers = {w: openers.count(w) for w in set(openers) if openers.count(w) >= 3 and w not in ("the", "a", "i")}
    transition_openers = sum(1 for s in sents if any(s.lower().startswith(t) for t in TRANSITIONS))

    vocab = count_phrases(text, VOCAB)
    filler = count_phrases(text, FILLER)
    closers = count_phrases(text, CLOSERS)
    hedges = count_phrases(text, HEDGES)
    neg = len(NEG_PARALLEL.findall(text))
    triads = len(TRIAD.findall(text))
    em_dashes = text.count("—") + len(re.findall(r"\s--\s", text))
    per100 = 100 / wc

    components = {
        "vocabulary": min(30.0, sum(vocab.values()) * per100 * 6),
        "transitions": min(15.0, transition_openers / max(1, len(sents)) * 60),
        "filler": min(15.0, sum(filler.values()) * per100 * 8),
        "closers": min(10.0, sum(closers.values()) * 5.0),
        "parallelism": min(8.0, neg * 4.0),
        "triads": min(6.0, max(0, triads - 1) * per100 * 10),
        "em_dash": min(6.0, max(0.0, em_dashes * per100 - 0.5) * 4),
        "uniform_rhythm": (10.0 if cv < 0.25 else 5.0 if cv < 0.4 else 0.0) if len(lengths) >= 5 else 0.0,
    }
    score = round(sum(components.values()), 1)
    return {
        "words": wc, "sentences": len(sents),
        "sentence_length": {"mean": round(mean, 1), "stdev": round(stdev, 1), "cv": round(cv, 2)},
        "score": score, "components": {k: round(v, 1) for k, v in components.items()},
        "hits": {"vocabulary": vocab, "filler": filler, "closers": closers, "hedges": hedges,
                 "transition_openers": transition_openers, "negative_parallelisms": neg,
                 "rule_of_three": triads, "em_dashes": em_dashes, "repeated_openers": repeated_openers},
    }


# --------------------------------------------------------------------------- facts

STOP_CAPS = {"The", "A", "An", "This", "That", "These", "Those", "It", "I", "We", "You", "They", "He", "She",
             "In", "On", "At", "For", "But", "And", "Or", "If", "When", "While", "As", "So", "Our", "My", "Your"}


def facts(text: str) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    out["urls"] = {u.rstrip(".,;:!?") for u in re.findall(r"https?://[^\s)>\]\"']+", text)}
    stripped = re.sub(r"https?://\S+", " ", text)
    out["emails"] = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", stripped))
    out["handles"] = set(re.findall(r"(?<![\w@])@\w{2,}", stripped))
    out["code"] = set(re.findall(r"`([^`]+)`", stripped))
    out["quotes"] = {q for q in re.findall(r"[\"“]([^\"”]{3,200})[\"”]", stripped)}
    nums = re.findall(r"(?<![\w.])[$€£₹]?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|[kKmMbB]n?\b|x\b)?", stripped)
    out["numbers"] = {re.sub(r"\s+", "", n).rstrip(",.") for n in nums if re.search(r"\d", n)}
    out["dates"] = set(re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:, \d{4})?\b|\b\d{4}-\d{2}-\d{2}\b",
        stripped))
    proper: Set[str] = set()
    skip_first = STOP_CAPS | {t.split()[0].capitalize() for t in TRANSITIONS}
    for sent in sentences(stripped):
        run: List[str] = []
        prev_end = 0
        for idx, m in enumerate(re.finditer(r"[A-Za-z][\w'’-]*", sent)):
            tok = m.group(0)
            if run and re.search(r"[^\s]", sent[prev_end:m.start()]):
                proper.add(" ".join(run))  # punctuation between tokens ends a name
                run = []
            prev_end = m.end()
            if tok[0].isupper() and not (idx == 0 and tok in skip_first):
                run.append(tok)
            else:
                if run:
                    proper.add(" ".join(run))
                run = []
        if run:
            proper.add(" ".join(run))
        # A lone capitalised first word is just sentence case, not a name.
        first = re.match(r"[A-Za-z][\w'’-]*", sent)
        if first and first.group(0) in proper and not first.group(0).isupper():
            following = sent[first.end():].lstrip()
            if not following[:1].isupper():
                proper.discard(first.group(0))
    out["proper_nouns"] = {p for p in proper if p not in STOP_CAPS and len(p) > 1}
    return out


def normalise(value: str) -> str:
    return re.sub(r"[\s,]", "", value.lower()).replace("percent", "%")


def compare(original: str, rewrite: str, max_delta: float) -> Dict[str, object]:
    f_orig, f_new = facts(original), facts(rewrite)
    rewrite_norm = normalise(rewrite)
    missing: Dict[str, List[str]] = {}
    for kind, values in f_orig.items():
        lost = []
        for v in sorted(values):
            if kind == "proper_nouns":
                if not re.search(r"\b" + re.escape(v) + r"\b", rewrite):
                    lost.append(v)
            elif normalise(v) not in rewrite_norm:
                lost.append(v)
        if lost:
            missing[kind] = lost
    original_norm = normalise(original)
    invented = {k: sorted(v for v in f_new[k] if normalise(v) not in original_norm)
                for k in ("numbers", "urls", "emails", "dates")}
    invented = {k: v for k, v in invented.items() if v}
    wc_o, wc_n = len(words(original)), len(words(rewrite))
    delta = (wc_n - wc_o) / max(1, wc_o) * 100
    before, after = scan(original), scan(rewrite)
    hard_missing = {k: v for k, v in missing.items() if k != "proper_nouns"}
    passed = not hard_missing and not invented and abs(delta) <= max_delta
    return {
        "passed": passed, "missing_facts": missing, "invented_facts": invented,
        "length": {"original_words": wc_o, "rewrite_words": wc_n, "delta_pct": round(delta, 1)},
        "score": {"before": before["score"], "after": after["score"]},
        "rhythm_cv": {"before": before["sentence_length"]["cv"], "after": after["sentence_length"]["cv"]},  # type: ignore[index]
        "remaining_tells": after["hits"],
    }


# --------------------------------------------------------------------------- CLI


def read(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def print_scan(r: Dict[str, object], limit: float) -> None:
    hits = r["hits"]
    print(f"AI-tell score: {r['score']} / 100 (gate {limit}) | words={r['words']} sentences={r['sentences']} "
          f"| sentence length mean={r['sentence_length']['mean']} cv={r['sentence_length']['cv']}")  # type: ignore[index]
    for k, v in r["components"].items():  # type: ignore[union-attr]
        if v:
            print(f"  {k:<15} +{v}")
    for label in ("vocabulary", "filler", "closers", "hedges", "repeated_openers"):
        if hits[label]:  # type: ignore[index]
            items = ", ".join(f"{k}×{n}" for k, n in sorted(hits[label].items(), key=lambda kv: -kv[1]))  # type: ignore[index]
            print(f"  - {label}: {items}")
    for label in ("transition_openers", "negative_parallelisms", "rule_of_three", "em_dashes"):
        if hits[label]:  # type: ignore[index]
            print(f"  - {label}: {hits[label]}")  # type: ignore[index]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="AI-tell scanner and fact-preservation gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.add_argument("--max-score", type=float, default=25.0)
    c = sub.add_parser("compare")
    c.add_argument("original")
    c.add_argument("rewrite")
    c.add_argument("--json", action="store_true")
    c.add_argument("--max-length-delta", type=float, default=50.0, help="allowed word-count change in percent")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "scan":
            text = read(args.file)
            if not text.strip():
                print("error: empty input", file=sys.stderr)
                return 2
            result = scan(text)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print_scan(result, args.max_score)
            return 0 if result["score"] <= args.max_score else 1  # type: ignore[operator]
        original, rewrite = read(args.original), read(args.rewrite)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not original.strip() or not rewrite.strip():
        print("error: empty input", file=sys.stderr)
        return 2
    result = compare(original, rewrite, args.max_length_delta)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for kind, vals in result["missing_facts"].items():  # type: ignore[union-attr]
            sev = "WARN " if kind == "proper_nouns" else "ERROR"
            print(f"{sev} missing {kind}: {', '.join(vals)}")
        for kind, vals in result["invented_facts"].items():  # type: ignore[union-attr]
            print(f"ERROR invented {kind}: {', '.join(vals)}")
        ln = result["length"]
        print(f"length {ln['original_words']} -> {ln['rewrite_words']} words ({ln['delta_pct']:+}%)")  # type: ignore[index]
        print(f"AI-tell score {result['score']['before']} -> {result['score']['after']} | "  # type: ignore[index]
              f"rhythm cv {result['rhythm_cv']['before']} -> {result['rhythm_cv']['after']}")  # type: ignore[index]
        print("PASS: facts preserved" if result["passed"] else "FAIL: fix the issues above")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

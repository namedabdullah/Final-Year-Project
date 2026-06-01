#!/usr/bin/env python3
"""
Quiz experiment runner — Phase 4 (ablation + proxy-quality) and Phase 5 (matrix).

Drives the **running LightRAG server** over HTTP (the exact code path your WebUI
uses), so it needs no in-process rag reconstruction. Pure standard library — run
it with the project's Python; no extra deps.

Prerequisites
-------------
  * The LightRAG server is running (default http://localhost:9621).
  * You have the document IDs to scope quizzes to (3-5 files). Find them in the
    WebUI document list or via GET /documents. Pass them with --docs or
    --docs-file.
  * If your server has auth enabled, pass --api-key (sent as X-API-Key).

Tasks
-----
  matrix    Generate quizzes across arms x difficulties, save raw JSON + a
            holistic-quality summary table. This is the Phase-5 verdict input.
  ablation  Run the deterministic seed-scoring ablation per arm (Phase 4.2).
  compare   Diff two saved matrix summaries (e.g. pedagogical vs random) on the
            quality metrics — the Phase-4.3 proxy-quality evidence.

Proxy-quality workflow (pedagogical vs random)
----------------------------------------------
  1. Run the matrix while the server runs the pedagogical scorer (default):
        python scripts/run_quiz_experiments.py matrix --docs d1,d2,d3 \
            --label pedagogical --out quiz_experiments
  2. Restart the server with QUIZ_SEED_STRATEGY=random, re-run:
        python scripts/run_quiz_experiments.py matrix --docs d1,d2,d3 \
            --label random --out quiz_experiments
  3. Diff them:
        python scripts/run_quiz_experiments.py compare \
            --a quiz_experiments/pedagogical/summaries.json \
            --b quiz_experiments/random/summaries.json

Examples
--------
  python scripts/run_quiz_experiments.py matrix --docs doc-abc,doc-def \
      --num-questions 10 --out quiz_experiments --label pedagogical
  python scripts/run_quiz_experiments.py ablation --docs doc-abc,doc-def \
      --out quiz_experiments --label pedagogical
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

DEFAULT_URL = os.environ.get("QUIZ_API_URL", "http://localhost:9621")
DEFAULT_KEY = os.environ.get("LIGHTRAG_API_KEY") or os.environ.get("QUIZ_API_KEY") or ""
ARM_FOR_MODE = {"mix": "graph", "naive": "naive"}

# Reasoning-depth tiers -- keep in sync with lightrag/quiz/diagnostics.py
# (reasoning_is_appropriate). The three higher-order types collapse to one
# 'deep' tier (3), so a hard question the verifier labels analytical/inferential
# (not exactly the claimed 'causal') still counts as appropriately-reasoned.
# easy/medium tiers are singletons, so this only changes 'hard'.
_REASONING_TIER = {"factual": 1, "comparative": 2, "causal": 3, "inferential": 3, "analytical": 3}
_EXPECTED_TIER = {"easy": 1, "medium": 2, "hard": 3}


def _reasoning_ok(difficulty, actual):
    exp = _EXPECTED_TIER.get((difficulty or "").strip().lower())
    got = _REASONING_TIER.get((actual or "").strip().lower())
    return exp is not None and got is not None and got == exp


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _post(base_url: str, path: str, payload: dict, api_key: str, timeout: float) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code} from {path}: {body}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach {url} ({exc.reason}). Is the server running?"
        ) from None


# ---------------------------------------------------------------------------
# Offline aggregation (mirrors lightrag.quiz.matrix.summarize_quiz on raw JSON)
# ---------------------------------------------------------------------------


def _rate(flags: list[bool]):
    return round(sum(1 for f in flags if f) / len(flags), 4) if flags else None


def _mean(vals: list):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def summarize(resp: dict) -> dict:
    qs = resp.get("questions", []) or []
    req = resp.get("request", {}) or {}
    ver = [q.get("verification") for q in qs if q.get("verification")]
    contribs = resp.get("file_contributions", []) or []
    return {
        "mode": req.get("mode"),
        "arm": ARM_FOR_MODE.get(req.get("mode"), "other"),
        "difficulty": req.get("difficulty"),
        "requested": req.get("num_questions"),
        "generated": len(qs),
        "answerable_rate": _rate([bool(v.get("answerable_from_context")) for v in ver]),
        "complexity_match_rate": _rate([bool(v.get("claimed_complexity_matches")) for v in ver]),
        "reasoning_match_rate": _rate([bool(v.get("claimed_reasoning_matches")) for v in ver]),
        "reasoning_appropriate_rate": _rate([
            _reasoning_ok(q.get("difficulty"), (q.get("verification") or {}).get("actual_reasoning_type"))
            for q in qs if q.get("verification")
        ]),
        "reasoning_types": dict(Counter(v.get("actual_reasoning_type") for v in ver)),
        "mean_figure_dependency": _mean([q.get("generation", {}).get("figure_dependency_estimate") for q in qs]),
        "mean_lexical_overlap": _mean([q.get("generation", {}).get("source_lexical_overlap") for q in qs]),
        "diversity": resp.get("diversity") or {},
        "files_total": len(contribs),
        "files_contributed": sum(1 for c in contribs if c.get("seed_count", 0) > 0),
        "files_zero": [c.get("doc_id") for c in contribs if c.get("seed_count", 0) == 0],
        "warnings": len(resp.get("warnings", []) or []),
        "quiz_id": resp.get("quiz_id"),
    }


_COLS = [
    ("arm", "arm", 6),
    ("difficulty", "diff", 7),
    ("generated", "gen", 4),
    ("answerable_rate", "ans", 6),
    ("complexity_match_rate", "cplx", 6),
    ("reasoning_match_rate", "rsn", 6),
    ("mean_figure_dependency", "figdep", 7),
    ("files_contributed", "files+", 7),
]


def _fmt_table(rows: list[dict]) -> str:
    head = " | ".join(lbl.ljust(w) for _, lbl, w in _COLS)
    out = [head, "-" * len(head)]
    for r in rows:
        out.append(" | ".join(
            ("" if r.get(k) is None else str(r.get(k))).ljust(w) for k, _, w in _COLS
        ))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def _outdir(args) -> Path:
    d = Path(args.out) / args.label
    d.mkdir(parents=True, exist_ok=True)
    (d / "raw").mkdir(exist_ok=True)
    return d


def task_matrix(args) -> int:
    docs = _resolve_docs(args)
    out = _outdir(args)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    diffs = [d.strip() for d in args.difficulties.split(",") if d.strip()]
    summaries: list[dict] = []
    print(f"Matrix: {arms} x {diffs}, n={args.num_questions}, docs={len(docs)} -> {out}")
    for mode in arms:
        for diff in diffs:
            payload = {
                "document_ids": docs,
                "mode": mode,
                "difficulty": diff,
                "num_questions": args.num_questions,
                "run_verification": not args.no_verify,
            }
            label = f"{mode}_{diff}"
            print(f"  generating {label} ...", flush=True)
            try:
                resp = _post(args.base_url, "/quiz/generate", payload, args.api_key, args.timeout)
            except Exception as exc:
                print(f"    ERROR {label}: {exc}", file=sys.stderr)
                summaries.append({"mode": mode, "difficulty": diff, "error": str(exc)})
                continue
            (out / "raw" / f"{label}.json").write_text(json.dumps(resp, indent=2), encoding="utf-8")
            s = summarize(resp)
            summaries.append(s)
            print(f"    {label}: generated {s['generated']}/{s['requested']}, "
                  f"ans={s['answerable_rate']}, figdep={s['mean_figure_dependency']}")
    (out / "summaries.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    ok = [s for s in summaries if "error" not in s]
    print("\n" + _fmt_table(ok))
    print(f"\nSaved {len(ok)} cell(s) to {out}/summaries.json (+ raw/).")
    return 0


def task_ablation(args) -> int:
    docs = _resolve_docs(args)
    out = _outdir(args)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    print(f"Ablation: arms={arms}, n={args.num_questions}, docs={len(docs)} -> {out}")
    for mode in arms:
        payload = {"document_ids": docs, "mode": mode, "num_questions": args.num_questions}
        print(f"  ablating {mode} ...", flush=True)
        try:
            report = _post(args.base_url, "/quiz/ablation", payload, args.api_key, args.timeout)
        except Exception as exc:
            print(f"    ERROR {mode}: {exc}", file=sys.stderr)
            continue
        (out / f"ablation_{mode}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        abl = report.get("ablation", {})
        if abl:
            ranked = sorted(abl.items(), key=lambda kv: kv[1].get("jaccard_vs_full", 1.0))
            print(f"    {mode}: load-bearing signals (most seed-set change when dropped):")
            for sig, info in ranked:
                print(f"       drop {sig}: Jaccard vs full = {info.get('jaccard_vs_full')}")
    print(f"\nSaved ablation reports to {out}/")
    return 0


def task_compare(args) -> int:
    a = {(_k(s)): s for s in json.loads(Path(args.a).read_text(encoding="utf-8")) if "error" not in s}
    b = {(_k(s)): s for s in json.loads(Path(args.b).read_text(encoding="utf-8")) if "error" not in s}
    metrics = [
        "answerable_rate", "complexity_match_rate", "reasoning_match_rate",
        "reasoning_appropriate_rate",
        "mean_figure_dependency", "mean_lexical_overlap",
    ]
    name_a = Path(args.a).parent.name or "A"
    name_b = Path(args.b).parent.name or "B"
    print(f"Compare  A={name_a}  vs  B={name_b}   (delta = A - B)\n")
    header = "cell".ljust(16) + " | " + " | ".join(m[:10].ljust(10) + " dlt".ljust(8) for m in metrics)
    print(header)
    print("-" * len(header))
    for key in sorted(set(a) & set(b)):
        cells = []
        for m in metrics:
            va, vb = a[key].get(m), b[key].get(m)
            delta = "" if (va is None or vb is None) else f"{va - vb:+.3f}"
            cells.append(f"{'' if va is None else va}".ljust(10) + f"{delta}".ljust(8))
        print(key.ljust(16) + " | " + " | ".join(cells))
    only = (set(a) ^ set(b))
    if only:
        print(f"\nCells in only one run: {sorted(only)}")
    print("\nReading: lower figdep/lexical_overlap = less extractive; higher ans/cplx/rsn = better calibrated.")
    return 0


def _k(s: dict) -> str:
    return f"{s.get('mode')}_{s.get('difficulty')}"


def _resolve_docs(args) -> list[str]:
    if args.docs_file:
        docs = [ln.strip() for ln in Path(args.docs_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif args.docs:
        docs = [d.strip() for d in args.docs.split(",") if d.strip()]
    else:
        print("ERROR: provide --docs id1,id2,... or --docs-file path", file=sys.stderr)
        sys.exit(2)
    if not docs:
        print("ERROR: no document IDs resolved", file=sys.stderr)
        sys.exit(2)
    return docs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="task", required=True)

    def _common(sp):
        sp.add_argument("--base-url", default=DEFAULT_URL, help=f"server URL (default {DEFAULT_URL})")
        sp.add_argument("--api-key", default=DEFAULT_KEY, help="X-API-Key (or env LIGHTRAG_API_KEY)")
        sp.add_argument("--docs", default="", help="comma-separated document IDs")
        sp.add_argument("--docs-file", default="", help="file with one document ID per line")
        sp.add_argument("--num-questions", type=int, default=10, choices=[10, 25, 50])
        sp.add_argument("--arms", default="mix,naive")
        sp.add_argument("--out", default="quiz_experiments", help="output directory")
        sp.add_argument("--label", default="run", help="sub-folder/label for this run (e.g. pedagogical)")
        sp.add_argument("--timeout", type=float, default=1800.0, help="per-request timeout seconds")

    m = sub.add_parser("matrix", help="generate arms x difficulties and summarise")
    _common(m)
    m.add_argument("--difficulties", default="easy,medium,hard")
    m.add_argument("--no-verify", action="store_true", help="skip Claude verification (faster/cheaper)")

    ab = sub.add_parser("ablation", help="seed-scoring ablation per arm")
    _common(ab)

    cmp = sub.add_parser("compare", help="diff two matrix summaries.json")
    cmp.add_argument("--a", required=True, help="summaries.json for run A (e.g. pedagogical)")
    cmp.add_argument("--b", required=True, help="summaries.json for run B (e.g. random)")

    args = p.parse_args()
    if args.task == "matrix":
        return task_matrix(args)
    if args.task == "ablation":
        return task_ablation(args)
    if args.task == "compare":
        return task_compare(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

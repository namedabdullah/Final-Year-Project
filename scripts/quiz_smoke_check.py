#!/usr/bin/env python3
"""
Quiz smoke-check — assert the post-quality-plan pass/fail signals on a generated
quiz, so you don't have to eyeball raw JSON.

Validates the two most-recent, not-yet-live-validated changes:
  * Step 2 (LLM educational-importance re-rank + up-weight + soft gate) — did the
    pedagogical scorer actually run, did the LLM signal participate, and did the
    obviously-weak seeds (titles, instance labels, table identifiers) get gated?
  * v7 prompt rule (NO FABRICATED SPECIFICS) — did the fabricated-number failure
    from smoke run #4 (quiz-b363f421: questions citing "30 seconds" / "0 seconds"
    drawn from burst-time TABLES not in the retrieved prose) recur?

Why not trust the verifier: the running server has no ANTHROPIC_API_KEY, so it
silently falls back to gpt-4o-mini grading gpt-4o-mini's own output (self-grading
— lenient, not thesis-valid). So the hard v7 gate checks grounding *directly*:
every digit-bearing specific a question cites (e.g. "30 seconds", "4 GB", "P2")
must appear verbatim in that question's retrieved chunk text (loaded from the
LightRAG text-chunk KV store) — exactly what the v7 rule demands. A specific
absent from the retrieved context is the smoke-#4 fabrication signature and fails.
(`source_lexical_overlap` alone is a poor proxy here: v7 forces abstractive
phrasing, so even grounded questions have low overlap.) When the chunk store is
unavailable it falls back to the overlap proxy as a WARN, never a hard FAIL.

Usage
-----
  python scripts/quiz_smoke_check.py                         # default dir
  python scripts/quiz_smoke_check.py quiz_experiments/smoke/raw
  python scripts/quiz_smoke_check.py a.json b.json

Exit code 0 = all checks PASS (warnings allowed); 1 = at least one FAIL; 2 = no
quiz files found / bad input. Pure standard library.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# --- thresholds (documented; mirror the smoke-#4 evidence) -----------------
LEX_OVERLAP_GROUNDED = 0.12   # >= this => the specific is plausibly in-source
DIVERSITY_MEAN_WARN = 0.85    # mean pairwise cosine above this => quiz orbits one topic
DIVERSITY_MAX_WARN = 0.95     # max pairwise cosine above this => a near-duplicate pair
FIGDEP_AT_RISK = 0.4          # diagnostics.estimate_figure_dependency "one phrase" hit

# Digit-bearing specifics that should only appear if verbatim in context (v7 rule).
_SPECIFIC_RES = [
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:seconds?|secs?|ms|milliseconds?|minutes?|mins?|"
               r"hours?|ns|nanoseconds?|us|microseconds?)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:KB|MB|GB|TB|kb|mb|gb|kib|mib|gib|bytes?|bits?)\b"),
    re.compile(r"\bP\d+\b"),        # process instance label "P2"
    re.compile(r"\bT\d+\b"),        # thread instance label "T3"
    re.compile(r"\bcore\s?\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s?-?\s?bit\b", re.IGNORECASE),
]

# Seeds that Step 2 (+ Step 1 filters) are supposed to keep out of the pool.
_WEAK_SEED_RES = [
    (re.compile(r"^(tb|im|mm)-[0-9a-f]{8,}", re.IGNORECASE), "artifact id"),
    (re.compile(r"\bP_?\d+\b"), "process instance label"),
    (re.compile(r"\bThread[\s_][A-Z0-9]\b"), "thread instance label"),
    (re.compile(r"\bcore[\s_]\d+\b", re.IGNORECASE), "cpu-core instance label"),
    (re.compile(r"\b(CSC\s?\d+|Instructor|Lecture\s?#|Dr\.)\b", re.IGNORECASE), "course metadata"),
    (re.compile(r"_[a-z0-9]+_[a-z0-9]+", re.IGNORECASE), "snake_case identifier"),
]

PEDAGOGICAL_STRATEGIES = {"entity-pedagogical", "chunk-pedagogical"}


def _specifics(text: str) -> list[str]:
    out: list[str] = []
    for rx in _SPECIFIC_RES:
        out.extend(m.group(0) for m in rx.finditer(text or ""))
    return out


def _weak_reason(seed: str) -> str | None:
    for rx, why in _WEAK_SEED_RES:
        if rx.search(seed or ""):
            return why
    return None


def _norm(s: str) -> str:
    """Lowercase + strip spaces/hyphens so '4 GB'/'4GB' and '64-bit'/'64 bit' match."""
    return re.sub(r"[\s\-]+", "", (s or "").lower())


def _load_chunk_store(path: str) -> dict | None:
    """Map chunk_id -> content from the LightRAG text-chunk KV store, or None."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {k: (v.get("content", "") if isinstance(v, dict) else "") for k, v in data.items()}


class Report:
    """Collects PASS/WARN/FAIL lines and tracks whether any hard FAIL occurred."""

    def __init__(self) -> None:
        self.failed = False
        self.lines: list[str] = []

    def add(self, level: str, check: str, msg: str) -> None:
        if level == "FAIL":
            self.failed = True
        self.lines.append(f"  [{level:<4}] {check}: {msg}")


def analyze_quiz(path: Path, chunk_store: dict | None = None) -> Report:
    rep = Report()
    resp = json.loads(path.read_text(encoding="utf-8"))
    req = resp.get("request", {}) or {}
    qs = resp.get("questions", []) or []
    mode = req.get("mode")
    diff = req.get("difficulty")
    requested = req.get("num_questions")

    print(f"\n=== {path.name}  ({mode}/{diff}, requested {requested}) ===")

    if not qs:
        # Could be the legitimate authoritative-empty case — surface, don't crash.
        rep.add("WARN", "generation", f"0 questions generated. warnings={resp.get('warnings')}")
        for ln in rep.lines:
            print(ln)
        return rep

    # ---- CHECK 1: wiring — real pedagogical seeds, v7 prompt loaded ----------
    placeholders = [q for q in qs if re.match(r"^topic_\d+$", q.get("retrieval", {}).get("seed_query", ""))]
    strategies = {q.get("retrieval", {}).get("seed_strategy", "") for q in qs}
    templ = {q.get("generation", {}).get("prompt_template_id", "") for q in qs}
    if placeholders:
        rep.add("FAIL", "wiring", f"{len(placeholders)} question(s) used topic_N placeholder seeds.")
    else:
        rep.add("PASS", "wiring", "no topic_N placeholder seeds.")
    if strategies & PEDAGOGICAL_STRATEGIES and not (strategies - PEDAGOGICAL_STRATEGIES):
        rep.add("PASS", "strategy", f"pedagogical scorer ran ({', '.join(sorted(strategies))}).")
    else:
        rep.add("FAIL", "strategy", f"non-pedagogical strategy in use: {sorted(strategies)} "
                                    "(random baseline? pedagogical path did not run).")
    if all(t.endswith("v7") for t in templ if t):
        rep.add("PASS", "prompt", f"v7 templates active ({', '.join(sorted(templ))}).")
    else:
        rep.add("WARN", "prompt", f"non-v7 prompt template(s): {sorted(templ)} (server may be stale).")

    # ---- CHECK 2: Step 2 — RRF + LLM signal actually participated ------------
    have_scores = [q for q in qs if q.get("retrieval", {}).get("seed_score") is not None]
    have_llm = [q for q in qs
                if "llm" in (q.get("retrieval", {}).get("seed_score_components", {}) or {})]
    if not have_scores:
        rep.add("FAIL", "rrf", "no seed_score on any question — RRF scoring did not run.")
    else:
        rep.add("PASS", "rrf", f"{len(have_scores)}/{len(qs)} questions carry an RRF seed_score.")
    if have_llm:
        rep.add("PASS", "step2-llm", f"LLM re-rank participated ('llm' in components on "
                                     f"{len(have_llm)}/{len(qs)} seeds).")
    else:
        rep.add("WARN", "step2-llm", "no 'llm' signal in any seed_score_components — LLM re-rank "
                                     "did not run (server missing LLM_BINDING_API_KEY in env?).")

    # ---- CHECK 3: Step 2 — weak seeds gated out ------------------------------
    weak = [(q.get("retrieval", {}).get("seed_query", ""), _weak_reason(q.get("retrieval", {}).get("seed_query", "")))
            for q in qs]
    weak = [(s, why) for s, why in weak if why]
    if weak:
        rep.add("WARN", "weak-seeds", f"{len(weak)} seed(s) look weak (Step 2 should demote/gate): "
                + "; ".join(f"{s!r} [{why}]" for s, why in weak[:5]))
    else:
        rep.add("PASS", "weak-seeds", "no obviously-weak seeds (titles/instance-labels/ids) survived.")

    # ---- CHECK 4: v7 — every cited specific must be grounded in context ------
    # Preferred: verbatim grounding against the question's retrieved chunk text
    # (what v7 actually requires). Fallback: blunt overlap proxy as a WARN.
    fabricated, unverifiable, grounded_q = [], [], 0
    for i, q in enumerate(qs):
        gen = q.get("generation", {})
        specifics = sorted(set(_specifics(f"{gen.get('question','')}  {gen.get('reference_answer','')}")))
        if not specifics:
            continue
        overlap = round(gen.get("source_lexical_overlap", 0.0) or 0.0, 3)
        cids = q.get("retrieval", {}).get("chunk_ids", []) or []
        if chunk_store is not None:
            resolved = [c for c in cids if c in chunk_store]
            if cids and not resolved:
                unverifiable.append(i + 1)            # chunk ids not in this store
                continue
            ctx = _norm(" ".join(chunk_store.get(c, "") for c in resolved))
            ungrounded = [s for s in specifics if _norm(s) not in ctx]
            if ungrounded:
                fabricated.append((i + 1, ungrounded, overlap))
            else:
                grounded_q += 1
        elif overlap < LEX_OVERLAP_GROUNDED:           # proxy fallback (no store)
            fabricated.append((i + 1, specifics, overlap))
        else:
            grounded_q += 1

    if chunk_store is None and fabricated:
        rep.add("WARN", "v7-fabrication",
                f"chunk store unavailable -- {len(fabricated)} question(s) cite a specific at "
                f"overlap < {LEX_OVERLAP_GROUNDED}; verify manually: "
                + "; ".join(f"Q{idx}={sp}" for idx, sp, _ in fabricated[:4]))
    elif fabricated:
        rep.add("FAIL", "v7-fabrication",
                f"{len(fabricated)} question(s) cite a specific ABSENT from the retrieved "
                "context (smoke-#4 fabrication signature):")
        for idx, sp, ov in fabricated:
            rep.lines.append(f"           Q{idx}: ungrounded={sp} overlap={ov}")
    else:
        msg = f"all cited specifics grounded in retrieved context ({grounded_q} with in-context specifics)."
        if unverifiable:
            msg += f" {len(unverifiable)} unverifiable (chunk ids not in store: Q{unverifiable})."
        rep.add("PASS", "v7-fabrication", msg)

    # ---- CHECK 5: diversity instrument (Goal 3) ------------------------------
    div = resp.get("diversity", {}) or {}
    mean_s, max_s = div.get("mean_pairwise_similarity"), div.get("max_pairwise_similarity")
    if mean_s is None:
        rep.add("WARN", "diversity", "no diversity metric on the response (instrument did not run).")
    else:
        lvl = "PASS"
        notes = []
        if mean_s > DIVERSITY_MEAN_WARN:
            lvl, _ = "WARN", notes.append(f"mean {mean_s} > {DIVERSITY_MEAN_WARN} (orbits one topic)")
        if (max_s or 0) > DIVERSITY_MAX_WARN:
            lvl = "WARN"; notes.append(f"max {max_s} > {DIVERSITY_MAX_WARN} (near-duplicate pair)")
        rep.add(lvl, "diversity", f"mean={mean_s}, max={max_s}" + ("  " + "; ".join(notes) if notes else ""))

    # ---- CHECK 6: multi-file contribution (Goal 2) ---------------------------
    contribs = resp.get("file_contributions", []) or []
    if not contribs:
        rep.add("WARN", "contribution", "no file_contributions emitted (random baseline?).")
    else:
        bad = [c for c in contribs if c.get("reason") not in
               {"contributed", "below_threshold", "outranked", "capped"}]
        contributed = [c for c in contribs if c.get("seed_count", 0) > 0]
        summary = ", ".join(f"{c.get('doc_id','')[:18]}={c.get('seed_count')}({c.get('reason')})"
                            for c in contribs)
        if bad:
            rep.add("FAIL", "contribution", f"invalid reason(s): {bad}")
        else:
            rep.add("PASS", "contribution",
                    f"{len(contributed)}/{len(contribs)} files contributed. {summary}")

    # ---- CHECK 7: generation health ------------------------------------------
    empties = [i + 1 for i, q in enumerate(qs)
               if (q.get("generation", {}).get("retrieved_chunk_count", 0) or 0) == 0]
    if empties:
        rep.add("FAIL", "grounding", f"questions {empties} generated from EMPTY retrieval "
                                     "(anti-hallucination guard breached).")
    else:
        rep.add("PASS", "grounding", f"all {len(qs)} questions had non-empty retrieval.")
    if len(qs) < (requested or 0):
        rep.add("WARN", "count", f"generated {len(qs)}/{requested} (honoured-smaller or gen failures; "
                                 f"warnings={len(resp.get('warnings', []))}).")
    else:
        rep.add("PASS", "count", f"generated {len(qs)}/{requested}.")

    for ln in rep.lines:
        print(ln)
    return rep


def _collect(args: list[str]) -> list[Path]:
    targets = args or ["quiz_experiments/smoke/raw"]
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        elif p.is_file():
            files.append(p)
    return files


def main(argv: list[str]) -> int:
    files = _collect(argv)
    if not files:
        print("No quiz JSON found. Run the matrix smoke first, or pass a file/dir.", file=sys.stderr)
        return 2
    chunk_path = os.environ.get("QUIZ_SMOKE_CHUNKS", "rag_storage/kv_store_text_chunks.json")
    chunk_store = _load_chunk_store(chunk_path)
    print(f"Smoke-checking {len(files)} quiz file(s): {[f.name for f in files]}")
    print("v7 grounding: " + (f"verbatim vs {chunk_path} ({len(chunk_store)} chunks)"
                              if chunk_store is not None else
                              f"overlap-proxy only (no chunk store at {chunk_path})"))
    any_fail = False
    for f in files:
        try:
            rep = analyze_quiz(f, chunk_store)
            any_fail = any_fail or rep.failed
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== {f.name} ===\n  [FAIL] parse: {exc}")
            any_fail = True
    print("\n" + ("RESULT: FAIL -- at least one hard check failed (see above)."
                  if any_fail else
                  "RESULT: PASS -- no hard failures (review any [WARN] lines)."))
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

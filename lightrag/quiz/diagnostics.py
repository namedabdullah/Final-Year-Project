"""Diagnostic heuristics for the quiz generator's output quality.

These metrics are written to ``GenerationMetadata`` for every question but
do NOT influence generation behavior — no regeneration loops, no
acceptance/rejection. They exist so that:

  - Production analytics can flag questions whose shape suggests
    figure-dependency or extractive surface form, for manual review.
  - The thesis comparison between mix-arm and naive-arm has additional
    columns of evidence beyond the verifier's pass/fail signal.

The current verifier prompt (``verifier_v1``) marks "What is the label of
Thread A?" as *passing* because the answer is trivially in context.
These diagnostics catch what the verifier misses, without changing the
verifier prompt's locked semantics.
"""

from __future__ import annotations

import re
from typing import Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Figure-dependency estimate
# ---------------------------------------------------------------------------

# Phrases whose presence in a question is a strong signal that the question
# is asking the reader to look something up in a figure, table, or diagram
# rather than test conceptual understanding.
_FIGURE_DEPENDENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\blabel\s+of\b", re.IGNORECASE),
    re.compile(r"\bname\s+of\s+the\s+\w+\s+in\s+the\s+diagram\b", re.IGNORECASE),
    re.compile(r"\blabel\s+used\s+to\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+\w+\s+is\s+(labeled|labelled|marked|shown)\b", re.IGNORECASE),
    re.compile(
        r"\b(first|second|third|fourth|fifth)\s+\w+\s+in\s+the\s+(figure|diagram|table)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bin\s+the\s+(figure|diagram|table)\b", re.IGNORECASE),
]

# Reference-answer patterns that suggest the answer is a cell value, label,
# or instance ID (e.g. "P1", "core 3", "C A B", "Page 3") rather than a
# conceptual statement.
_SHORT_CRYPTIC_TOKEN = re.compile(r"\d|[A-Z]{2,}")


def estimate_figure_dependency(question: str, reference_answer: str) -> float:
    """Heuristic score in ``[0, 1]`` for how figure-dependent the question is.

    Adds 0.4 for each figure-dependency phrase in the question, and 0.4 if
    the reference answer is a short cryptic token (1-3 tokens containing a
    digit or all-caps run). Caps at 1.0.

    The thresholds are intentionally coarse — this is a flag for human
    review, not a hard classifier.
    """
    score = 0.0
    for pat in _FIGURE_DEPENDENCY_PATTERNS:
        if pat.search(question or ""):
            score += 0.4
            break  # one phrase is enough; don't double-count near-duplicates

    tokens = (reference_answer or "").strip().split()
    if 1 <= len(tokens) <= 3 and any(_SHORT_CRYPTIC_TOKEN.search(t) for t in tokens):
        score += 0.4

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Source lexical overlap
# ---------------------------------------------------------------------------

# Common stop-words drop; the goal is to compare *content* tokens between
# the question and the source chunk. A small built-in list keeps this
# module dependency-free.
_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have how in is it its of on or
    that the their this to was were what when where which who why will with
    you your an be been being do does did has had having i me my we our us
    not no nor so such than that these those they them then there here
    """.split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z'_-]*")


def _tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _STOPWORDS and len(t) > 2
    }


def source_lexical_overlap(question: str, top_chunk_text: str) -> float:
    """Stopword-filtered Jaccard overlap between question and source chunk.

    Returns 0.0 when either input is empty. Both inputs are tokenised on
    alphabetic runs, lowercased, and filtered against a small stopword
    list before the Jaccard computation.

    A high score is not automatically bad (a comparative question may
    legitimately reuse domain terms from the source). The metric is a
    *signal*, paired with ``estimate_figure_dependency`` to give a more
    complete picture of extraction vs. abstraction.
    """
    q_tokens = _tokens(question)
    c_tokens = _tokens(top_chunk_text)
    if not q_tokens or not c_tokens:
        return 0.0
    intersection = q_tokens & c_tokens
    union = q_tokens | c_tokens
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Quiz-level diversity instrument (quality-plan.md §8.1)
# ---------------------------------------------------------------------------


def pairwise_cosine_stats(vectors: Sequence[Sequence[float]]) -> dict:
    """Mean and max pairwise cosine similarity over a set of vectors.

    Used as the quiz-level diversity metric: embed the N generated questions,
    then report how similar they are to each other. Lower mean/max = more
    diverse quiz. Returns ``{}`` for fewer than two vectors.

    A high *max* flags a near-duplicate pair the seed/question de-dup layers
    missed; a high *mean* flags a quiz that orbits one topic.
    """
    mat = np.asarray(vectors, dtype=float)
    if mat.ndim != 2 or mat.shape[0] < 2:
        return {}
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = mat / norms
    sims = unit @ unit.T
    n = sims.shape[0]
    iu = np.triu_indices(n, k=1)  # upper triangle, exclude self-similarity
    pair_sims = sims[iu]
    if pair_sims.size == 0:
        return {}
    return {
        "mean_pairwise_similarity": round(float(pair_sims.mean()), 6),
        "max_pairwise_similarity": round(float(pair_sims.max()), 6),
        "question_count": int(n),
    }


__all__ = [
    "estimate_figure_dependency",
    "source_lexical_overlap",
    "pairwise_cosine_stats",
]

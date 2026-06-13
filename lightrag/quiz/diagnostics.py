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
# Question clarity / single-focus estimate
# ---------------------------------------------------------------------------

# Connectives whose repeated presence signals a multi-part, over-stuffed
# question (the "hard" questions pile on clauses like "… and what factors must
# be considered, particularly when …"). Coarse on purpose — a flag, not a parser.
_CLARITY_CONNECTIVES = (
    " and ",
    " or ",
    " particularly",
    " considering",
    " while ",
    " whereas ",
    " also ",
    " as well as ",
    " in terms of ",
)


def estimate_clarity(question: str) -> float:
    """Heuristic clarity / single-focus score in ``[0, 1]``.

    IMPORTANT — the direction is the OPPOSITE of the other two diagnostics in
    this module: here **higher = clearer / more single-focus**; lower =
    over-stuffed. (``estimate_figure_dependency`` and ``source_lexical_overlap``
    are higher = worse.)

    Starts at 1.0 and subtracts coarse penalties for over-stuffing:
      - long question text (> 140 chars): up to -0.3
      - more than one sentence: -0.2
      - each multi-clause connective beyond the first: -0.1 (capped at -0.3)
    Floors at 0.0. An empty question returns 0.0 (no question = not clear).

    Thresholds are intentionally coarse and tunable — a review flag, not a
    grammar classifier.
    """
    q = (question or "").strip()
    if not q:
        return 0.0

    score = 1.0

    # Length: questions over ~140 chars are usually multi-part. Ramp to -0.3.
    if len(q) > 140:
        score -= min(0.3, (len(q) - 140) / 400.0)

    # Sentence count: a single focused question is one sentence.
    sentences = [s for s in re.split(r"[.?!]+", q) if s.strip()]
    if len(sentences) > 1:
        score -= 0.2

    # Multi-clause connectives: the first is fine; pile-ons cost.
    low = f" {q.lower()} "
    connectives = sum(low.count(c) for c in _CLARITY_CONNECTIVES)
    if connectives > 1:
        score -= min(0.3, (connectives - 1) * 0.1)

    return round(max(0.0, score), 4)


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


# ---------------------------------------------------------------------------
# Reasoning-type appropriateness (depth-aware, kept discriminating between arms)
# ---------------------------------------------------------------------------

# The verifier classifies actual_reasoning_type into one of five types. A
# question "matches" its claimed reasoning if the actual type is accepted for the
# claim. For 'hard':
#   - causal / analytical always count (cause-effect chains, multi-element analysis);
#   - inferential is KEPT but tightened — the verifier's "inferential" label is
#     broad (any unstated conclusion) and otherwise passes nearly everything, so
#     it counts only as a *genuine multi-piece* inference (actual complexity
#     >= _CONDITIONAL_MIN_PIECES). A single-passage inference does not clear hard.
# This keeps the metric discriminating between the arms (mix's multi-hop synthesis
# skews analytical / multi-piece; naive carries more single-passage inferences).
ACCEPTED_REASONING = {
    "factual": {"factual"},
    "comparative": {"comparative"},
    "causal": {"causal", "analytical"},
}

# The same accepted sets keyed by difficulty (factual=easy / comparative=medium /
# causal=hard mirror generation.REASONING_TYPE).
ACCEPTED_REASONING_BY_DIFFICULTY = {
    "easy": {"factual"},
    "medium": {"comparative"},
    "hard": {"causal", "analytical"},
}

# 'inferential' counts for hard only when the inference spans at least this many
# retrieved pieces — a "little strict" bar, milder than hard's own >=3 floor.
_CONDITIONAL_MIN_PIECES = 2


def _is_multi_piece(actual_complexity) -> bool:
    try:
        return int(actual_complexity) >= _CONDITIONAL_MIN_PIECES
    except (TypeError, ValueError):
        return False


def reasoning_types_match(
    claimed_reasoning_type: str,
    actual_reasoning_type: str,
    actual_complexity=None,
) -> bool:
    """True if the actual reasoning type is accepted for the claimed type.

    Hard's claimed ``causal`` accepts ``causal`` / ``analytical`` outright, and
    ``inferential`` only as a genuine multi-piece inference
    (``actual_complexity >= 2``) — the broad "inferential" label otherwise lets
    almost everything pass. Without complexity info, inferential does not count.
    Unknown inputs return False (conservative).
    """
    claimed = (claimed_reasoning_type or "").strip().lower()
    actual = (actual_reasoning_type or "").strip().lower()
    accepted = ACCEPTED_REASONING.get(claimed)
    if accepted is None:
        return False
    if actual in accepted:
        return True
    if claimed == "causal" and actual == "inferential":
        return _is_multi_piece(actual_complexity)
    return False


def reasoning_is_appropriate(
    difficulty: str,
    actual_reasoning_type: str,
    actual_complexity=None,
) -> bool:
    """Difficulty-keyed companion to :func:`reasoning_types_match`.

    easy→factual, medium→comparative, hard→{causal, analytical} outright, plus
    ``inferential`` for hard only as a multi-piece inference
    (``actual_complexity >= 2``). Unknown inputs return False (conservative).
    """
    diff = (difficulty or "").strip().lower()
    actual = (actual_reasoning_type or "").strip().lower()
    accepted = ACCEPTED_REASONING_BY_DIFFICULTY.get(diff)
    if accepted is None:
        return False
    if actual in accepted:
        return True
    if diff == "hard" and actual == "inferential":
        return _is_multi_piece(actual_complexity)
    return False


# Minimum context pieces a question should require, keyed by its claimed retrieval
# complexity (easy=1 / medium=2 / hard=3): the question must genuinely need at
# least as many pieces as the retrieval depth it claims. 'hard' requires >=3
# (full synthesis) — the bar where mix (multi-hop) and naive (often answerable
# from 1-2 chunks) separate most clearly.
_MIN_PIECES_BY_CLAIM = {1: 1, 2: 2, 3: 3}


def complexity_is_appropriate(claimed_complexity: int, actual_complexity: int) -> bool:
    """True if the measured complexity meets the floor expected for the claim.

    Floor per claim: easy(1)->1, medium(2)->2, hard(3)->3 — the question must need
    at least as many context pieces as the retrieval depth claims. A hard question
    answerable from 1-2 pieces is not appropriately complex.
    """
    try:
        claim = int(claimed_complexity)
        floor = _MIN_PIECES_BY_CLAIM.get(claim, claim)
        return int(actual_complexity) >= floor
    except (TypeError, ValueError):
        return False


__all__ = [
    "estimate_figure_dependency",
    "source_lexical_overlap",
    "estimate_clarity",
    "pairwise_cosine_stats",
    "reasoning_is_appropriate",
    "reasoning_types_match",
    "complexity_is_appropriate",
    "ACCEPTED_REASONING",
    "ACCEPTED_REASONING_BY_DIFFICULTY",
]

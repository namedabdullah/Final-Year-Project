"""Unit tests for Phase 1 quiz-pipeline helpers.

Covers the three new pure functions added by `quiz-fix-plan.md`:

  - :func:`lightrag.quiz.artifacts.is_artifact_id`
  - :func:`lightrag.quiz.artifacts.redact_instance_labels`
  - :func:`lightrag.quiz.diagnostics.estimate_figure_dependency`
  - :func:`lightrag.quiz.diagnostics.source_lexical_overlap`

Seed-diversity behaviour (B+2) is integration-level (depends on live VDB
state) and is verified by the end-to-end checks listed in the plan
rather than by unit tests here.
"""

from __future__ import annotations

import pytest

from lightrag.quiz.artifacts import (
    is_artifact_id,
    is_course_metadata,
    redact_instance_labels,
)
from lightrag.quiz.diagnostics import (
    complexity_is_appropriate,
    estimate_clarity,
    estimate_figure_dependency,
    reasoning_is_appropriate,
    reasoning_types_match,
    source_lexical_overlap,
)


# ---------------------------------------------------------------------------
# is_artifact_id
# ---------------------------------------------------------------------------


_HEX32 = "c570c018fd8c6a90b42b9fd0b61c2443"


@pytest.mark.parametrize(
    "name, expected",
    [
        (f"tb-{_HEX32}-0001", True),     # canonical table ID
        (f"im-{_HEX32}-0042", True),     # image / drawing ID
        (f"mm-{_HEX32}-0007", True),     # other multimodal anchor
        ("Thread 1", False),             # instance label — not an artifact
        ("", False),                     # empty string
        ("tb-short", False),             # malformed (missing digits + hash)
        (f"TB-{_HEX32.upper()}-0001", False),  # uppercase prefix — not matched
        (f"tb-{_HEX32[:-1]}-0001", False),     # 31-char hex instead of 32
    ],
)
def test_is_artifact_id(name: str, expected: bool) -> None:
    assert is_artifact_id(name) is expected


# ---------------------------------------------------------------------------
# is_course_metadata (Step 1c — course-title-slide seed filter)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # Course-title-slide boilerplate that leaked into naive seeds.
        ("1\n\n# CSC 323 - Principles of Operating Systems\nInstructor: Dr. M. Hasan Jamal", True),
        ("Instructor: Dr. M. Hasan Jamal", True),     # instructor line
        ("Lecture# 05: CPU Scheduling", True),         # lecture header (with #)
        ("Lecture 7", True),                           # lecture header (no #)
        ("CSC 323", True),                             # course code (spaced)
        ("CS101", True),                               # course code (joined)
        # Real concepts / prose — never flagged (high-precision keep).
        ("Operating System", False),
        ("CPU Scheduling", False),                     # the lecture *topic*, not its header
        ("Bounded-Buffer Problem", False),
        ("Memory Management", False),
        ("A page fault occurs when a referenced page is not resident in memory.", False),
        ("", False),
    ],
)
def test_is_course_metadata(text: str, expected: bool) -> None:
    assert is_course_metadata(text) is expected


# ---------------------------------------------------------------------------
# redact_instance_labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Thread 1 signals Semaphore Y", "{thread} signals {semaphore}"),
        ("P1 has arrival time 0", "{process} has arrival time 0"),
        ("process_1 maps to physical memory", "{process} maps to physical memory"),
        ("core 3 is the fourth processor", "{cpu_core} is the fourth processor"),
        ("CPU_7 in the diagram", "{cpu_core} in the diagram"),
        ("Page 3 maps to Frame 7", "{memory_page} maps to {memory_frame}"),
        # No-op: prose without any instance labels stays untouched
        (
            "The critical section must execute atomically.",
            "The critical section must execute atomically.",
        ),
        ("", ""),
    ],
)
def test_redact_instance_labels(text: str, expected: str) -> None:
    assert redact_instance_labels(text) == expected


# ---------------------------------------------------------------------------
# estimate_figure_dependency
# ---------------------------------------------------------------------------


def test_figure_dependency_label_question_scores_high() -> None:
    score = estimate_figure_dependency(
        question="What is the label of the fourth processor core?",
        reference_answer="core 3",
    )
    # Both the question pattern AND the cryptic answer fire → ~0.8
    assert score >= 0.7


def test_figure_dependency_conceptual_question_scores_zero() -> None:
    score = estimate_figure_dependency(
        question="What is the role of a semaphore in concurrent programming?",
        reference_answer="A semaphore coordinates access to shared resources between threads.",
    )
    assert score == pytest.approx(0.0)


def test_figure_dependency_short_cryptic_answer_alone() -> None:
    # Question is fine but the answer "P1" looks like a label
    score = estimate_figure_dependency(
        question="Which process arrives first in the schedule?",
        reference_answer="P1",
    )
    assert score == pytest.approx(0.4)


def test_figure_dependency_capped_at_one() -> None:
    score = estimate_figure_dependency(
        question="What is the label of the first process in the diagram?",
        reference_answer="P1",
    )
    assert 0.0 < score <= 1.0


# ---------------------------------------------------------------------------
# source_lexical_overlap
# ---------------------------------------------------------------------------


def test_overlap_empty_inputs() -> None:
    assert source_lexical_overlap("", "anything") == 0.0
    assert source_lexical_overlap("anything", "") == 0.0
    assert source_lexical_overlap("", "") == 0.0


def test_overlap_perfect_match_excluding_stopwords() -> None:
    # "the" is a stopword; "semaphore" and "coordinates" are content tokens
    q = "the semaphore coordinates threads"
    c = "the semaphore coordinates threads"
    assert source_lexical_overlap(q, c) == pytest.approx(1.0)


def test_overlap_disjoint() -> None:
    q = "What conceptual role does mutual exclusion play?"
    c = "Apples and oranges grow on different trees entirely."
    assert source_lexical_overlap(q, c) < 0.1


def test_overlap_partial() -> None:
    q = "How does a semaphore prevent race conditions?"
    c = "A semaphore is a signaling primitive that prevents race conditions in concurrent code."
    score = source_lexical_overlap(q, c)
    # Shared content tokens: semaphore, prevent(s), race, conditions → 4 in
    # common. Score should be moderate (0.3-0.7), not 1.0 or 0.0.
    assert 0.2 < score < 0.8


# ---------------------------------------------------------------------------
# reasoning_is_appropriate (depth-tier reasoning-match reframe)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "difficulty, actual, complexity, expected",
    [
        # HARD: causal/analytical outright; inferential only as a multi-piece inference.
        ("hard", "causal", 3, True),
        ("hard", "analytical", 3, True),
        ("hard", "inferential", 2, True),    # multi-piece inference counts
        ("hard", "inferential", 1, False),   # single-passage inference does not
        ("hard", "inferential", None, False),
        ("hard", "comparative", 3, False),   # too shallow for hard
        ("hard", "factual", 3, False),
        # MEDIUM / EASY are singletons.
        ("medium", "comparative", 2, True),
        ("medium", "causal", 3, False),      # deeper than medium's set
        ("medium", "factual", 1, False),     # too shallow
        ("easy", "factual", 1, True),
        ("easy", "comparative", 1, False),
        # Robustness: unknown / empty inputs are conservative (False).
        ("hard", "", 3, False),
        ("hard", "unknown-type", 3, False),
        ("", "causal", 3, False),
        ("HARD", "ANALYTICAL", 3, True),     # case-insensitive
    ],
)
def test_reasoning_is_appropriate(difficulty: str, actual: str, complexity, expected: bool) -> None:
    assert reasoning_is_appropriate(difficulty, actual, complexity) is expected


# ---------------------------------------------------------------------------
# estimate_clarity (higher = clearer / more single-focus)
# ---------------------------------------------------------------------------


def test_estimate_clarity_focused_question_scores_high() -> None:
    score = estimate_clarity("What is the role of a semaphore in concurrent programming?")
    assert score >= 0.9


def test_estimate_clarity_overstuffed_question_scores_low() -> None:
    # A real over-stuffed "hard" question: long, multi-clause, multiple connectives.
    q = (
        "How does the management of the process control block, including the correct "
        "tracking of a process's state transitions and its resource allocation needs, "
        "influence the overall efficiency of the CPU in a multi-process environment, "
        "particularly when considering varied burst times and the implications of "
        "context switching?"
    )
    assert estimate_clarity(q) <= 0.5


def test_estimate_clarity_empty_is_zero() -> None:
    assert estimate_clarity("") == 0.0
    assert estimate_clarity("   ") == 0.0


def test_estimate_clarity_multi_sentence_is_penalized() -> None:
    one = estimate_clarity("What is paging?")
    two = estimate_clarity("What is paging? How does it differ from segmentation?")
    assert two < one


# ---------------------------------------------------------------------------
# reasoning_types_match (per-question tier match: hard accepts the deep set)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "claimed, actual, complexity, expected",
    [
        ("causal", "causal", 3, True),
        ("causal", "analytical", 3, True),       # hard 'causal' accepts analytical
        ("causal", "inferential", 2, True),      # inferential KEPT, as a multi-piece inference
        ("causal", "inferential", 1, False),     # single-passage inference -> too soft for hard
        ("causal", "inferential", None, False),  # no complexity info -> conservative
        ("causal", "comparative", 3, False),     # not in causal's accepted set
        ("causal", "factual", 3, False),
        ("comparative", "comparative", 1, True),
        ("comparative", "causal", 3, False),     # medium claim, deeper actual
        ("factual", "factual", 1, True),
        ("causal", "", 3, False),                # unknown actual
        ("", "causal", 3, False),                # unknown claim
        ("causal", "analyze", 3, False),         # not a canonical type -> unknown
    ],
)
def test_reasoning_types_match(claimed: str, actual: str, complexity, expected: bool) -> None:
    assert reasoning_types_match(claimed, actual, complexity) is expected


# ---------------------------------------------------------------------------
# complexity_is_appropriate (floor-based: hard needs >=2 pieces, not exactly 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "claimed, actual, expected",
    [
        (3, 3, True),     # hard, needs 3
        (3, 2, False),    # hard now requires >=3 pieces, so 2 is too simple
        (3, 1, False),    # hard, answerable from 1 -> too simple
        (2, 2, True),     # medium
        (2, 1, False),    # medium, too simple
        (1, 1, True),     # easy
        (1, 3, True),     # easy floor is 1, so a deeper question still clears it
        (3, 0, False),
    ],
)
def test_complexity_is_appropriate(claimed: int, actual: int, expected: bool) -> None:
    assert complexity_is_appropriate(claimed, actual) is expected

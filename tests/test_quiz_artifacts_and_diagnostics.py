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

from lightrag.quiz.artifacts import is_artifact_id, redact_instance_labels
from lightrag.quiz.diagnostics import (
    estimate_figure_dependency,
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

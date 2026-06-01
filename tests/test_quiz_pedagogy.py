"""Unit tests for the pedagogy + correctness judges (pure helpers only — no network).

Exercises parsing / normalization / mock helpers in :mod:`lightrag.quiz.pedagogy`.
The async ``judge_*`` entry points hit an LLM and are covered by the live smoke
run, not here.
"""

from __future__ import annotations

import pytest

from lightrag.quiz.pedagogy import (
    _clamp_score,
    _mock_correctness,
    _mock_pedagogy,
    _normalize_bloom,
    _parse_correctness_json,
    _parse_pedagogy_json,
)


# ---------------------------------------------------------------------------
# _normalize_bloom
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("remember", "remember"),
        ("Analyze", "analyze"),          # case-insensitive
        ("ANALYZE", "analyze"),
        ("analyzing", "analyze"),        # gerund alias
        ("analysis", "analyze"),         # noun alias
        ("understanding", "understand"),
        ("comprehension", "understand"),
        ("synthesis", "create"),         # old-taxonomy alias
        ("evaluate (judging the trade-off)", "evaluate"),  # prefix match
        ("", ""),
        ("nonsense", ""),
        (None, ""),
    ],
)
def test_normalize_bloom(raw, expected) -> None:
    assert _normalize_bloom(raw) == expected


# ---------------------------------------------------------------------------
# _clamp_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (1, 1), (3, 3), (5, 5),
        (7, 5),          # clamp above range
        (0, 0),          # unscored
        (-2, 0),         # non-positive -> unscored
        ("4", 4),        # numeric string
        (4.0, 4),        # float
        (None, 0),
        ("oops", 0),     # garbage -> unscored
    ],
)
def test_clamp_score(raw, expected) -> None:
    assert _clamp_score(raw) == expected


# ---------------------------------------------------------------------------
# _parse_pedagogy_json
# ---------------------------------------------------------------------------


def test_parse_pedagogy_full() -> None:
    raw = '{"pedagogical_value": 4, "bloom_level": "Analyze", "answer_completeness": 5, "notes": "good"}'
    m = _parse_pedagogy_json(raw, model="claude-sonnet-4-6")
    assert m.pedagogical_value == 4
    assert m.bloom_level == "analyze"
    assert m.answer_completeness == 5
    assert m.notes == "good"
    assert m.model == "claude-sonnet-4-6"


def test_parse_pedagogy_missing_keys_default_not_raise() -> None:
    # Only one key present — the rest default; must NOT raise (don't discard the row).
    m = _parse_pedagogy_json('{"pedagogical_value": 3}', model="x")
    assert m.pedagogical_value == 3
    assert m.bloom_level == ""
    assert m.answer_completeness == 0


def test_parse_pedagogy_repairs_malformed_json() -> None:
    # Missing closing brace — json_repair should recover the object.
    raw = '{"pedagogical_value": 5, "bloom_level": "evaluate", "answer_completeness": 4, "notes": "ok"'
    m = _parse_pedagogy_json(raw, model="x")
    assert m.pedagogical_value == 5
    assert m.bloom_level == "evaluate"


def test_parse_pedagogy_non_dict_raises() -> None:
    # Valid JSON, but a list — not a judgement object.
    with pytest.raises(ValueError):
        _parse_pedagogy_json("[1, 2, 3]", model="x")


# ---------------------------------------------------------------------------
# _parse_correctness_json
# ---------------------------------------------------------------------------


def test_parse_correctness_full() -> None:
    m = _parse_correctness_json('{"answer_correctness": 2, "notes": "wrong unit"}', model="x")
    assert m.answer_correctness == 2
    assert m.notes == "wrong unit"


def test_parse_correctness_missing_defaults_zero() -> None:
    m = _parse_correctness_json('{"notes": "n/a"}', model="x")
    assert m.answer_correctness == 0


# ---------------------------------------------------------------------------
# mocks (graceful degradation)
# ---------------------------------------------------------------------------


def test_mock_pedagogy_is_unscored() -> None:
    m = _mock_pedagogy()
    assert m.pedagogical_value == 0
    assert m.bloom_level == ""
    assert m.answer_completeness == 0
    assert "mock" in m.notes.lower()


def test_mock_correctness_is_unscored() -> None:
    m = _mock_correctness()
    assert m.answer_correctness == 0
    assert "mock" in m.notes.lower()

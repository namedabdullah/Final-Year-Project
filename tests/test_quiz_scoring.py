"""
Unit tests for the pedagogical seed scorer (lightrag/quiz/scoring.py).

These exercise the *pure* RRF + Cap/Merit/Floor logic and the content-only
naive heuristics — no database, no LLM, no mocking (quality-plan.md §10).
"""

from __future__ import annotations

import math

from lightrag.quiz import scoring
from lightrag.quiz.seeds import _make_rng


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def test_fuse_rrf_assigns_ranks_and_scores():
    rows = [
        {"signals": {"a": 10.0, "b": 1.0}},   # best on a, worst on b
        {"signals": {"a": 1.0, "b": 10.0}},   # worst on a, best on b
        {"signals": {"a": 5.0, "b": 5.0}},    # middle on both
    ]
    scoring.fuse_rrf(rows, ["a", "b"], k=1)

    # row0 ranks: a=1, b=3 ; row1: a=3, b=1 ; row2: a=2, b=2
    assert rows[0]["ranks"] == {"a": 1, "b": 3}
    assert rows[1]["ranks"] == {"a": 3, "b": 1}
    assert rows[2]["ranks"] == {"a": 2, "b": 2}

    # k=1 → row0 = row1 = 1/2 + 1/4 = 0.75 ; row2 = 1/3 + 1/3 ≈ 0.667
    assert math.isclose(rows[0]["rrf_score"], 0.75)
    assert math.isclose(rows[1]["rrf_score"], 0.75)
    assert rows[0]["rrf_score"] > rows[2]["rrf_score"]


def test_fuse_rrf_weights_shift_ranking():
    rows = [
        {"signals": {"a": 10.0, "b": 1.0}},
        {"signals": {"a": 1.0, "b": 10.0}},
    ]
    scoring.fuse_rrf(rows, ["a", "b"], k=1, weights={"a": 10.0, "b": 1.0})
    # Heavy weight on `a` → the a-leader (row0) must win.
    assert rows[0]["rrf_score"] > rows[1]["rrf_score"]


# ---------------------------------------------------------------------------
# Cap + Merit + Floor allocation
# ---------------------------------------------------------------------------


def _row(key, doc, score, *, floor=True, dedup=None):
    return {
        "key": key,
        "seed": key,
        "doc_id": doc,
        "dedup_key": dedup if dedup is not None else key,
        "rrf_score": score,
        "meets_floor": floor,
    }


def test_allocate_merit_order():
    rows = [_row("a", "D1", 0.1), _row("b", "D1", 0.9), _row("c", "D1", 0.5)]
    selected, _ = scoring.allocate(rows, 3, ["D1"])
    assert [r["key"] for r in selected] == ["b", "c", "a"]


def test_allocate_cap_forces_spread():
    # File A has the 4 best candidates; B has 1 weaker. n=3, cap=ceil(0.34*3)=2.
    rows = [
        _row("a1", "A", 0.99), _row("a2", "A", 0.98),
        _row("a3", "A", 0.97), _row("a4", "A", 0.96),
        _row("b1", "B", 0.10),
    ]
    selected, contribs = scoring.allocate(rows, 3, ["A", "B"], cap_fraction=0.34)
    by_doc = {c["doc_id"]: c for c in contribs}
    assert by_doc["A"]["seed_count"] == 2          # capped at 2
    assert by_doc["B"]["seed_count"] == 1          # spread pulled B in
    assert by_doc["A"]["reason"] == "contributed"
    assert by_doc["B"]["reason"] == "contributed"


def test_allocate_cap_relaxes_when_no_alternative():
    # Only one file with capacity; cap must relax in pass 2 rather than under-fill.
    rows = [_row(f"a{i}", "A", 0.9 - i * 0.01) for i in range(5)]
    selected, _ = scoring.allocate(rows, 4, ["A"], cap_fraction=0.5)  # cap=2
    assert len(selected) == 4  # relaxed cap filled the quiz from the single file


def test_allocate_floor_zeroes_a_weak_file():
    rows = [
        _row("a1", "A", 0.9, floor=False),
        _row("a2", "A", 0.8, floor=False),
        _row("b1", "B", 0.5, floor=True),
    ]
    selected, contribs = scoring.allocate(rows, 3, ["A", "B"])
    by_doc = {c["doc_id"]: c for c in contribs}
    assert by_doc["A"]["seed_count"] == 0
    assert by_doc["A"]["reason"] == "below_threshold"
    assert by_doc["B"]["seed_count"] == 1
    assert [r["key"] for r in selected] == ["b1"]


def test_allocate_outranked_reason():
    # B is eligible but loses every seat to A within n.
    rows = [
        _row("a1", "A", 0.99), _row("a2", "A", 0.98),
        _row("b1", "B", 0.10),
    ]
    selected, contribs = scoring.allocate(rows, 2, ["A", "B"], cap_fraction=1.0)
    by_doc = {c["doc_id"]: c for c in contribs}
    assert by_doc["B"]["seed_count"] == 0
    assert by_doc["B"]["reason"] == "outranked"


def test_allocate_no_padding_honours_smaller_quiz():
    rows = [_row("a", "A", 0.9), _row("b", "B", 0.8)]
    selected, _ = scoring.allocate(rows, 5, ["A", "B"])
    assert len(selected) == 2  # never padded up to 5


def test_allocate_dedup_collapses_shared_source():
    rows = [
        _row("a1", "A", 0.9, dedup="chunk-1"),
        _row("a2", "A", 0.8, dedup="chunk-1"),  # same source chunk → dropped
        _row("a3", "A", 0.7, dedup="chunk-2"),
    ]
    selected, _ = scoring.allocate(rows, 3, ["A"])
    keys = [r["key"] for r in selected]
    assert keys == ["a1", "a3"]


# ---------------------------------------------------------------------------
# Naive content-only scorer
# ---------------------------------------------------------------------------


def _fs(text: str) -> str:
    return text[:60]


def test_score_naive_detects_anchor_chunks():
    chunks = [
        {"id": "c1", "full_doc_id": "D1", "content": "[Image Name] Figure of a CPU pipeline."},
        {"id": "c2", "full_doc_id": "D1", "content": "Virtual memory is defined as an abstraction because it decouples address spaces."},
    ]
    rows = scoring.score_naive(chunks, _fs)
    by_key = {r["key"]: r for r in rows}
    assert by_key["c1"]["is_anchor"] is True
    assert by_key["c1"]["signals"]["prose"] == 0.0
    assert by_key["c2"]["is_anchor"] is False
    assert by_key["c2"]["signals"]["prose"] == 1.0
    # The prose chunk uses explanatory connectives ("is defined as", "because").
    assert by_key["c2"]["signals"]["explan"] >= 2.0
    # The prose chunk should out-rank the bare anchor caption.
    assert by_key["c2"]["rrf_score"] > by_key["c1"]["rrf_score"]


def test_score_naive_carries_first_sentence_seed():
    chunks = [{"id": "c1", "full_doc_id": "D1", "content": "Scheduling decides which process runs. More text."}]
    rows = scoring.score_naive(chunks, _fs)
    assert rows[0]["seed"].startswith("Scheduling decides which process runs")


# ---------------------------------------------------------------------------
# Deterministic RNG (reproducibility — quality-plan.md §7.4)
# ---------------------------------------------------------------------------


def test_make_rng_is_deterministic_for_docset_and_mode():
    r1 = _make_rng({"d2", "d1"}, "mix")
    r2 = _make_rng({"d1", "d2"}, "mix")  # order-independent
    assert [r1.random() for _ in range(5)] == [r2.random() for _ in range(5)]


def test_make_rng_differs_by_mode():
    r_mix = _make_rng({"d1"}, "mix")
    r_naive = _make_rng({"d1"}, "naive")
    assert [r_mix.random() for _ in range(5)] != [r_naive.random() for _ in range(5)]


# ---------------------------------------------------------------------------
# Phase 3 — clustering-for-coverage (diversify)
# ---------------------------------------------------------------------------


def test_cluster_by_cosine_groups_near_duplicates():
    vecs = {"k1": [1.0, 0.0], "k2": [0.99, 0.01], "k3": [0.0, 1.0]}
    clusters = scoring.cluster_by_cosine(["k1", "k2", "k3"], vecs, threshold=0.6)
    # k1 & k2 are near-identical → same cluster; k3 separate.
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]
    pair = next(c for c in clusters if len(c) == 2)
    assert set(pair) == {"k1", "k2"}


def test_diversify_spreads_selection_across_clusters():
    # k1,k2 are the same topic; k3,k4 distinct. Highest RRF is in the k1/k2 cluster.
    emb = {"k1": [1, 0, 0], "k2": [0.99, 0.01, 0], "k3": [0, 1, 0], "k4": [0, 0, 1]}
    rows = [
        _row("k1", "A", 0.90), _row("k2", "A", 0.85),
        _row("k3", "A", 0.80), _row("k4", "A", 0.70),
    ]
    scoring.diversify(rows, emb, threshold=0.6)
    selected, _ = scoring.allocate(rows, 3, ["A"])
    keys = {r["key"] for r in selected}
    # Coverage: distinct topics k3 and k4 make the cut; the redundant k2 does not.
    assert "k3" in keys and "k4" in keys
    assert "k2" not in keys


def test_without_diversify_redundant_pair_both_selected():
    # Same rows, but no diversify → pure RRF order keeps both k1 and k2.
    rows = [
        _row("k1", "A", 0.90), _row("k2", "A", 0.85), _row("k3", "A", 0.80),
    ]
    selected, _ = scoring.allocate(rows, 2, ["A"])
    assert [r["key"] for r in selected] == ["k1", "k2"]


# ---------------------------------------------------------------------------
# Phase 4 — diversity metric + ablation primitives
# ---------------------------------------------------------------------------


def test_pairwise_cosine_stats():
    from lightrag.quiz.diagnostics import pairwise_cosine_stats

    stats = pairwise_cosine_stats([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    assert stats["question_count"] == 3
    assert math.isclose(stats["max_pairwise_similarity"], 1.0)
    # pairs: (1,1)=1.0, (1,0)=0, (1,0)=0 → mean = 1/3
    assert math.isclose(stats["mean_pairwise_similarity"], 1 / 3, rel_tol=1e-4)


def test_pairwise_cosine_stats_needs_two():
    from lightrag.quiz.diagnostics import pairwise_cosine_stats

    assert pairwise_cosine_stats([[1.0, 0.0]]) == {}


def test_jaccard():
    from lightrag.quiz.ablation import jaccard

    assert jaccard([], []) == 1.0
    assert math.isclose(jaccard(["a", "b"], ["b", "c"]), 1 / 3)
    assert jaccard(["a"], ["b"]) == 0.0


def test_select_keys_for_signals_is_deterministic():
    from lightrag.quiz.ablation import select_keys_for_signals

    rows = [
        {"key": "a", "seed": "a", "doc_id": "D", "dedup_key": "a", "meets_floor": True,
         "signals": {"x": 9.0, "y": 1.0}},
        {"key": "b", "seed": "b", "doc_id": "D", "dedup_key": "b", "meets_floor": True,
         "signals": {"x": 1.0, "y": 9.0}},
        {"key": "c", "seed": "c", "doc_id": "D", "dedup_key": "c", "meets_floor": True,
         "signals": {"x": 5.0, "y": 5.0}},
    ]
    full = select_keys_for_signals(rows, ["x", "y"], 3, ["D"])
    assert set(full) == {"a", "b", "c"}
    # Dropping y → ranking driven by x alone; `a` (x=9) must lead.
    only_x = select_keys_for_signals(rows, ["x"], 3, ["D"])
    assert only_x[0] == "a"
    # Pure function: original rows untouched (no rrf_score leaked in).
    assert "rrf_score" not in rows[0]


# ---------------------------------------------------------------------------
# Phase 5 — matrix summary (offline aggregation)
# ---------------------------------------------------------------------------


def test_summarize_quiz_aggregates_quality_signals():
    from datetime import datetime, timezone
    from lightrag.quiz.matrix import summarize_quiz
    from lightrag.quiz.schemas import (
        FileContribution, GenerationMetadata, QuizGenerateRequest,
        QuizGenerateResponse, QuizQuestionMetadata, RetrievalMetadata,
        VerificationMetadata,
    )

    def _q(qid, fig, ans, cplx, rsn):
        return QuizQuestionMetadata(
            question_id=qid, arm="graph", difficulty="easy",
            claimed_retrieval_complexity=1, claimed_reasoning_type="factual",
            retrieval=RetrievalMetadata(),
            generation=GenerationMetadata(question=f"Q{qid}?", figure_dependency_estimate=fig),
            verification=VerificationMetadata(
                answerable_from_context=ans,
                claimed_complexity_matches=cplx,
                claimed_reasoning_matches=rsn,
            ),
        )

    resp = QuizGenerateResponse(
        quiz_id="q", created_at=datetime.now(timezone.utc),
        request=QuizGenerateRequest(document_ids=["d1", "d2"], mode="mix",
                                    difficulty="easy", num_questions=10),
        questions=[_q("1", 0.4, True, True, False), _q("2", 0.0, False, False, True)],
        file_contributions=[
            FileContribution(doc_id="d1", seed_count=2, reason="contributed"),
            FileContribution(doc_id="d2", seed_count=0, reason="below_threshold"),
        ],
        diversity={"mean_pairwise_similarity": 0.3, "max_pairwise_similarity": 0.5},
    )
    s = summarize_quiz(resp)
    assert s["arm"] == "graph"
    assert s["generated"] == 2
    assert s["answerable_rate"] == 0.5
    assert s["complexity_match_rate"] == 0.5
    assert s["reasoning_match_rate"] == 0.5
    assert s["mean_figure_dependency"] == 0.2
    assert s["files_contributed"] == 1
    assert s["files_zero"] == ["d2"]

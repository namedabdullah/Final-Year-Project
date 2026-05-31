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
# Step 1 — deterministic floors (suggestions.md A1/A2)
# ---------------------------------------------------------------------------


def test_is_instance_label_entity():
    from lightrag.quiz.artifacts import is_instance_label_entity

    # Clearly-instance, delimited labels → dropped from the seed pool.
    assert is_instance_label_entity("Core 1") is True
    assert is_instance_label_entity("Thread 3") is True
    assert is_instance_label_entity("process 2") is True
    assert is_instance_label_entity("CPU_7") is True
    assert is_instance_label_entity("Semaphore A") is True
    assert is_instance_label_entity("P_0") is True
    assert is_instance_label_entity("S_3") is True
    # Ambiguous bare tokens that double as real OS concepts → KEPT (high
    # precision: never silently delete a legitimate concept).
    assert is_instance_label_entity("S3") is False      # ACPI sleep state
    assert is_instance_label_entity("P0") is False      # ACPI P-state
    assert is_instance_label_entity("Process P2") is False  # weak but kept; LLM layer demotes
    # Real concepts — kept.
    assert is_instance_label_entity("Operating System") is False
    assert is_instance_label_entity("Thread Pool") is False
    assert is_instance_label_entity("Page Table") is False
    assert is_instance_label_entity("Bounded-Buffer Problem") is False
    assert is_instance_label_entity("") is False


def test_redaction_preserves_acpi_states_but_keeps_process_labels():
    from lightrag.quiz.artifacts import redact_instance_labels

    # Bare S-/T-states must survive redaction (no longer eaten by [TS]_?\d).
    assert redact_instance_labels("S3") == "S3"
    assert redact_instance_labels("S3 sleep state") == "S3 sleep state"
    # Underscore instance shorthand still redacts.
    assert redact_instance_labels("T_1") == "{thread}"
    # Bare process labels still redact (burst-time tables rely on this).
    assert redact_instance_labels("P1 has arrival time 0").startswith("{process}")


def test_allocate_all_floor_fail_returns_empty():
    # When every candidate fails the floor, allocate selects nothing and every
    # file is reported below_threshold (this is what makes the pedagogical
    # result authoritative-empty rather than a failure → no random fallback).
    rows = [_row("a", "A", 0.9, floor=False), _row("b", "B", 0.8, floor=False)]
    selected, contribs = scoring.allocate(rows, 5, ["A", "B"])
    assert selected == []
    assert all(c["seed_count"] == 0 and c["reason"] == "below_threshold" for c in contribs)


def test_seed_selection_authoritative_defaults_false():
    from lightrag.quiz.seeds import SeedSelection

    assert SeedSelection(seeds=[], strategy="x").authoritative is False


def test_naive_floor_rejects_embedded_artifact_anchor():
    hexid = "0" * 32
    chunks = [
        # Thin heading + embedded table markup → artifact-dominated → excluded,
        # even though it does NOT start with [Image]/[Table].
        {"id": "embedded", "full_doc_id": "D1",
         "content": f'# Example 3\n10\n<table id="tb-{hexid}-0001">P1 P2 burst times</table>'},
        # Real prose ahead of an embedded table → kept (high precision).
        {"id": "prose_with_table", "full_doc_id": "D1",
         "content": ("# Memory Hierarchy 12 The memory hierarchy orders storage devices by "
                     f'access speed cost and capacity as summarised <table id="tb-{hexid}-0002">x</table>')},
    ]
    rows = scoring.score_naive(chunks, _fs)
    by_key = {r["key"]: r for r in rows}
    assert by_key["embedded"]["is_anchor"] is True
    assert by_key["embedded"]["meets_floor"] is False
    assert by_key["prose_with_table"]["is_anchor"] is False
    assert by_key["prose_with_table"]["meets_floor"] is True


def test_is_embedded_anchor_helper():
    hexid = "a" * 32
    assert scoring._is_embedded_anchor(f'# Linux bcc/BPF Tracing Tools\n19\n<drawing id="im-{hexid}-0002">') is True
    assert scoring._is_embedded_anchor("Paging eliminates external fragmentation by mapping pages.") is False  # no artifact
    # Substantial lead prose before the artifact → not artifact-dominated.
    long_lead = "The translation lookaside buffer caches recent page table entries to speed address translation as the diagram below illustrates "
    assert scoring._is_embedded_anchor(long_lead + f'<drawing id="im-{hexid}-0003">') is False


# ---------------------------------------------------------------------------
# Step 2 — LLM importance re-rank (pure mechanics)
# ---------------------------------------------------------------------------


def test_apply_llm_rerank_adds_signal_and_refuses():
    rows = [{"key": "a", "signals": {"x": 5.0}}, {"key": "b", "signals": {"x": 1.0}}]
    scoring.fuse_rrf(rows, ["x"], k=1)
    scoring.apply_llm_rerank(rows, ["x"], {"a": 9.0, "b": 2.0})
    assert all("llm" in r["signals"] for r in rows)
    assert all("llm" in r["ranks"] for r in rows)
    rd = {r["key"]: r["rrf_score"] for r in rows}
    assert rd["a"] > rd["b"]  # a leads on both x and llm


def test_apply_llm_rerank_neutral_for_unscored():
    rows = [
        {"key": "a", "signals": {"x": 1.0}},
        {"key": "b", "signals": {"x": 1.0}},
        {"key": "c", "signals": {"x": 1.0}},
    ]
    scoring.fuse_rrf(rows, ["x"])
    scoring.apply_llm_rerank(rows, ["x"], {"a": 10.0, "b": 2.0})  # c unscored
    by_key = {r["key"]: r for r in rows}
    assert by_key["c"]["signals"]["llm"] == 6.0  # mean of {10, 2}


def test_apply_llm_rerank_noop_without_scores():
    rows = [{"key": "a", "signals": {"x": 5.0}}]
    scoring.fuse_rrf(rows, ["x"])
    before = rows[0]["rrf_score"]
    scoring.apply_llm_rerank(rows, ["x"], {})
    assert rows[0]["rrf_score"] == before
    assert "llm" not in rows[0]["signals"]


def test_apply_llm_rerank_reapplies_hub_penalty():
    rows = [
        {"key": "hub", "signals": {"x": 9.0}, "is_hub": True},
        {"key": "norm", "signals": {"x": 9.0}, "is_hub": False},
    ]
    scoring.fuse_rrf(rows, ["x"])
    scoring.apply_llm_rerank(rows, ["x"], {"hub": 9.0, "norm": 9.0})
    by_key = {r["key"]: r for r in rows}
    # Hub penalty (0.5×) re-applied after the re-fuse → hub scored below norm.
    assert by_key["hub"]["rrf_score"] < by_key["norm"]["rrf_score"]


def test_llm_importance_parse_scores():
    from lightrag.quiz import llm_importance

    raw = '{"scores":[{"i":1,"score":8},{"i":2,"score":15},{"i":3,"score":"x"}]}'
    out = llm_importance._parse_scores(raw, 3)
    assert out[0] == 8.0        # i=1 → index 0
    assert out[1] == 10.0       # 15 clamped to 10 (i=2 → index 1)
    assert 2 not in out         # non-numeric score skipped
    assert llm_importance._parse_scores("not json", 3) == {}


def test_llm_importance_cache_key_and_prompt():
    from lightrag.quiz import llm_importance

    assert llm_importance._cache_key("docs", "Memory") == llm_importance._cache_key("docs", "Memory")
    assert llm_importance._cache_key("docs", "Memory") != llm_importance._cache_key("other", "Memory")
    p = llm_importance._build_prompt(["Memory", "Scheduling"])
    assert "1. Memory" in p and "2. Scheduling" in p


def test_naive_floor_rejects_anchor_and_title_slides():
    chunks = [
        # Bare table anchor → excluded by default (QUIZ_NAIVE_EXCLUDE_ANCHORS).
        {"id": "anchor", "full_doc_id": "D1",
         "content": "[Table Name]process_burst_time_schedule shows arrival and burst columns."},
        # Title/divider slide → too few content tokens.
        {"id": "title", "full_doc_id": "D1", "content": "CSC 323 Operating Systems Instructor"},
        # Real teachable prose → passes the floor.
        {"id": "prose", "full_doc_id": "D1",
         "content": "Virtual memory is an abstraction that decouples logical address "
                    "spaces from the physical memory installed on the machine."},
    ]
    rows = scoring.score_naive(chunks, _fs)
    floor = {r["key"]: r["meets_floor"] for r in rows}
    assert floor["anchor"] is False
    assert floor["title"] is False
    assert floor["prose"] is True


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

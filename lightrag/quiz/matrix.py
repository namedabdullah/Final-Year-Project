"""
Phase 5 — comparison-matrix runner + holistic quiz-quality metrics
(quality-plan.md §12 Phase 5, §8).

The thesis verdict is a *system-level* comparison: GraphRAG-based vs
NaiveRAG-based quiz generation, across difficulties. Because seeds legitimately
differ between arms (§0), the comparison rests on **output quality metrics**, so
this module:

  - ``summarize_quiz(response)`` — pure aggregation of one quiz's quality
    signals (verifier flags, figure-dependency, lexical overlap, diversity,
    per-file contribution). Unit-tested offline.
  - ``run_matrix(rag, document_ids, …)`` — drives ``generate_quiz`` across
    arms × difficulties and collects the summaries. Needs a live index + API
    keys; pilot on a 3-file set before the full run (§5 note).

``run_matrix`` does NOT itself decide a winner — it produces the table; the
verdict is written up from it.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import List, Optional, Sequence

from lightrag.quiz.pipeline import generate_quiz
from lightrag.quiz.schemas import QuizGenerateRequest, QuizGenerateResponse

logger = logging.getLogger(__name__)

_ARM_FOR_MODE = {"mix": "graph", "naive": "naive"}


def _rate(values: Sequence[bool]) -> Optional[float]:
    vals = list(values)
    return round(sum(1 for v in vals if v) / len(vals), 4) if vals else None


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _agreement_rate(a: Sequence, b: Sequence) -> Optional[float]:
    """Fraction of positions where both sequences have equal non-None values."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    return round(sum(1 for x, y in pairs if x == y) / len(pairs), 4) if pairs else None


def summarize_quiz(response: QuizGenerateResponse) -> dict:
    """Aggregate one quiz into a row of holistic quality metrics.

    Reports per-judge stats for both Claude (primary) and GPT (panel second judge),
    plus a simple inter-judge agreement block for binary metrics.
    """
    qs = response.questions

    # Claude judge readings
    ver_c = [q.verification for q in qs if q.verification is not None]
    ped_c = [q.pedagogy for q in qs if q.pedagogy is not None]
    corr_c = [q.correctness for q in qs if q.correctness is not None]

    # GPT judge readings
    ver_g = [q.verification_gpt for q in qs if q.verification_gpt is not None]
    ped_g = [q.pedagogy_gpt for q in qs if q.pedagogy_gpt is not None]
    corr_g = [q.correctness_gpt for q in qs if q.correctness_gpt is not None]

    contribs = response.file_contributions

    # --- Inter-judge agreement (binary metrics, paired by question position) ---
    answerable_c = [q.verification.answerable_from_context if q.verification else None for q in qs]
    answerable_g = [q.verification_gpt.answerable_from_context if q.verification_gpt else None for q in qs]
    cplx_match_c = [q.verification.claimed_complexity_matches if q.verification else None for q in qs]
    cplx_match_g = [q.verification_gpt.claimed_complexity_matches if q.verification_gpt else None for q in qs]
    rsn_match_c  = [q.verification.claimed_reasoning_matches if q.verification else None for q in qs]
    rsn_match_g  = [q.verification_gpt.claimed_reasoning_matches if q.verification_gpt else None for q in qs]

    inter_judge_agreement = {
        "answerable": _agreement_rate(answerable_c, answerable_g),
        "complexity_match": _agreement_rate(cplx_match_c, cplx_match_g),
        "reasoning_match": _agreement_rate(rsn_match_c, rsn_match_g),
    }

    return {
        "mode": response.request.mode,
        "arm": _ARM_FOR_MODE.get(response.request.mode, "other"),
        "difficulty": response.request.difficulty,
        "requested": response.request.num_questions,
        "generated": len(qs),

        # --- Claude judge (primary) ---
        # Verifier flag rates; None when verification was off.
        # complexity_match / reasoning_match are deterministic in diagnostics.py
        # (floor-based and tier-based respectively — not brittle exact matches).
        "answerable_rate": _rate([v.answerable_from_context for v in ver_c]),
        "complexity_match_rate": _rate([v.claimed_complexity_matches for v in ver_c]),
        "reasoning_match_rate": _rate([v.claimed_reasoning_matches for v in ver_c]),
        "reasoning_types": dict(Counter(v.actual_reasoning_type for v in ver_c)),
        # Pedagogy + optional correctness. Means over *scored* questions (0 = unscored).
        "pedagogical_value_mean": _mean([p.pedagogical_value for p in ped_c if p.pedagogical_value]),
        "bloom_distribution": dict(Counter(p.bloom_level for p in ped_c if p.bloom_level)),
        "answer_completeness_mean": _mean([p.answer_completeness for p in ped_c if p.answer_completeness]),
        "answer_correctness_mean": _mean([c.answer_correctness for c in corr_c if c.answer_correctness]),

        # --- GPT panel judge (second leg) ---
        "answerable_rate_gpt": _rate([v.answerable_from_context for v in ver_g]),
        "complexity_match_rate_gpt": _rate([v.claimed_complexity_matches for v in ver_g]),
        "reasoning_match_rate_gpt": _rate([v.claimed_reasoning_matches for v in ver_g]),
        "reasoning_types_gpt": dict(Counter(v.actual_reasoning_type for v in ver_g)),
        "pedagogical_value_mean_gpt": _mean([p.pedagogical_value for p in ped_g if p.pedagogical_value]),
        "bloom_distribution_gpt": dict(Counter(p.bloom_level for p in ped_g if p.bloom_level)),
        "answer_completeness_mean_gpt": _mean([p.answer_completeness for p in ped_g if p.answer_completeness]),
        "answer_correctness_mean_gpt": _mean([c.answer_correctness for c in corr_g if c.answer_correctness]),

        # --- Inter-judge agreement (% agreement on binary metrics) ---
        "inter_judge_agreement": inter_judge_agreement,

        # --- Deterministic diagnostics (arm-blind, no judge variability) ---
        # figure-dependency / lexical-overlap: lower = better; clarity: HIGHER = better.
        "mean_figure_dependency": _mean([q.generation.figure_dependency_estimate for q in qs]),
        "mean_lexical_overlap": _mean([q.generation.source_lexical_overlap for q in qs]),
        "mean_clarity": _mean([q.generation.clarity_heuristic for q in qs]),

        # --- Diversity and multi-file contribution ---
        "diversity": response.diversity or {},
        "files_total": len(contribs),
        "files_contributed": sum(1 for c in contribs if c.seed_count > 0),
        "files_zero": [c.doc_id for c in contribs if c.seed_count == 0],
        "warnings": len(response.warnings),
    }


async def run_matrix(
    rag,
    document_ids: List[str],
    *,
    arms: Sequence[str] = ("mix", "naive"),
    difficulties: Sequence[str] = ("easy", "medium", "hard"),
    num_questions: int = 25,
    run_verification: bool = True,
    run_correctness_check: bool = True,
) -> List[dict]:
    """Run the full arm × difficulty matrix and return per-cell summaries.

    Live: each cell calls ``generate_quiz`` (retrieval + LLM generation +
    optional verification). Returns a list of ``summarize_quiz`` rows plus the
    ``quiz_id`` of each persisted quiz.
    """
    summaries: List[dict] = []
    for mode in arms:
        for difficulty in difficulties:
            logger.info("run_matrix: generating %s / %s …", mode, difficulty)
            req = QuizGenerateRequest(
                document_ids=document_ids,
                mode=mode,  # type: ignore[arg-type]
                difficulty=difficulty,  # type: ignore[arg-type]
                num_questions=num_questions,  # type: ignore[arg-type]
                run_verification=run_verification,
                run_correctness_check=run_correctness_check,
            )
            response = await generate_quiz(rag, req)
            row = summarize_quiz(response)
            row["quiz_id"] = response.quiz_id
            summaries.append(row)
    return summaries


def format_comparison(summaries: List[dict]) -> str:
    """Render the matrix summaries as a compact text table for quick reading."""
    cols = [
        ("arm", "arm"),
        ("difficulty", "diff"),
        ("generated", "gen"),
        # Claude judge
        ("answerable_rate", "ans_c"),
        ("complexity_match_rate", "cplx_c"),
        ("reasoning_match_rate", "rsn_c"),
        ("pedagogical_value_mean", "pedval_c"),
        # GPT judge
        ("answerable_rate_gpt", "ans_g"),
        ("pedagogical_value_mean_gpt", "pedval_g"),
        # Agreement + diagnostics
        ("mean_figure_dependency", "figdep"),
        ("files_contributed", "files+"),
    ]
    header = " | ".join(label.ljust(8) for _, label in cols)
    lines = [header, "-" * len(header)]
    for s in summaries:
        cells = []
        for key, _ in cols:
            val = s.get(key)
            cells.append(("" if val is None else str(val)).ljust(8))
        lines.append(" | ".join(cells))
        # Append agreement on its own line under each row
        agr = s.get("inter_judge_agreement", {})
        if agr:
            agr_str = "  agreement: " + ", ".join(
                f"{k}={v}" for k, v in agr.items() if v is not None
            )
            lines.append(agr_str)
    return "\n".join(lines)

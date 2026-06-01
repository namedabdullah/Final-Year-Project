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


def summarize_quiz(response: QuizGenerateResponse) -> dict:
    """Aggregate one quiz into a row of holistic quality metrics."""
    qs = response.questions
    ver = [q.verification for q in qs if q.verification is not None]
    ped = [q.pedagogy for q in qs if q.pedagogy is not None]
    corr = [q.correctness for q in qs if q.correctness is not None]
    contribs = response.file_contributions

    return {
        "mode": response.request.mode,
        "arm": _ARM_FOR_MODE.get(response.request.mode, "other"),
        "difficulty": response.request.difficulty,
        "requested": response.request.num_questions,
        "generated": len(qs),
        # Verifier flag rates (None when verification was off).
        "answerable_rate": _rate([v.answerable_from_context for v in ver]),
        # complexity_match / reasoning_match are computed deterministically in
        # verification.py: complexity is FLOOR-based (hard needs >=2 pieces, not
        # exactly 3) and reasoning is TIER-based (hard accepts causal/inferential/
        # analytical) — not brittle exact matches.
        "complexity_match_rate": _rate([v.claimed_complexity_matches for v in ver]),
        "reasoning_match_rate": _rate([v.claimed_reasoning_matches for v in ver]),
        "reasoning_types": dict(Counter(v.actual_reasoning_type for v in ver)),
        # Pedagogy judge (Goal 1) + optional correctness fact-check. Means are over
        # *scored* questions only (0 = unscored mock); None when the judge didn't run.
        "pedagogical_value_mean": _mean([p.pedagogical_value for p in ped if p.pedagogical_value]),
        "bloom_distribution": dict(Counter(p.bloom_level for p in ped if p.bloom_level)),
        "answer_completeness_mean": _mean([p.answer_completeness for p in ped if p.answer_completeness]),
        "answer_correctness_mean": _mean([c.answer_correctness for c in corr if c.answer_correctness]),
        # Diagnostic means. figure-dependency / lexical-overlap: lower = better;
        # clarity: HIGHER = better (more single-focus).
        "mean_figure_dependency": _mean([q.generation.figure_dependency_estimate for q in qs]),
        "mean_lexical_overlap": _mean([q.generation.source_lexical_overlap for q in qs]),
        "mean_clarity": _mean([q.generation.clarity_heuristic for q in qs]),
        # Diversity (quality-plan.md §8.1) and multi-file contribution (§6.2).
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
        ("answerable_rate", "ans"),
        ("complexity_match_rate", "cplx"),
        ("reasoning_match_rate", "rsn"),
        ("pedagogical_value_mean", "pedval"),
        ("mean_figure_dependency", "figdep"),
        ("files_contributed", "files+"),
    ]
    header = " | ".join(label.ljust(7) for _, label in cols)
    lines = [header, "-" * len(header)]
    for s in summaries:
        cells = []
        for key, _ in cols:
            val = s.get(key)
            cells.append(("" if val is None else str(val)).ljust(7))
        lines.append(" | ".join(cells))
    return "\n".join(lines)

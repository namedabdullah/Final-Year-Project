"""
Top-level quiz generation orchestrator.

Phase 1: generate_quiz returns a mock QuizGenerateResponse.
Phase 3: retrieval stubs replaced with real BFS/naive retrieval.
Phase 4: generation stubs replaced with real GPT-4o calls.
Phase 5: verification stubs replaced with real Claude Sonnet calls.
Phase 6: reverify_quiz fully implemented.
Rate-limit fix: concurrency capped at 1 (QUIZ_CONCURRENCY_CAP env var),
  plus a configurable inter-request delay (QUIZ_INTER_REQUEST_DELAY env var,
  default 1.0 s) so parallel requests are staggered in time.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from lightrag.quiz.diagnostics import (
    estimate_clarity,
    estimate_figure_dependency,
    pairwise_cosine_stats,
    source_lexical_overlap,
)
from lightrag.quiz.artifacts import normalize_concept_name
from lightrag.quiz.generation import (
    PROMPT_TEMPLATE_IDS,
    REASONING_TYPE,
    generate_question,
)
from lightrag.quiz.retrieval import (
    RetrievalContext,
    retrieve_fallback,
    retrieve_mix_arm,
    retrieve_naive_arm,
)
from lightrag.quiz.schemas import (
    GenerationMetadata,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionMetadata,
    RetrievalMetadata,
)
from lightrag.quiz.pedagogy import judge_correctness, judge_pedagogy
from lightrag.quiz.seeds import sample_seeds
from lightrag.quiz.storage import load_quiz, save_quiz, save_reverified_quiz
from lightrag.quiz.verification import verify_question

if TYPE_CHECKING:
    from lightrag import LightRAG


# ---------------------------------------------------------------------------
# Helpers / Rate-limit tuning — configurable via environment variables
# ---------------------------------------------------------------------------

# Maximum number of questions generated concurrently.
#
# Default is 1 (fully sequential).  With cap>1 every worker can hit the
# TPM limit at almost the same instant, retry with similar delays, then
# burst again — a resonance that's impossible to break without a shared
# token-bucket limiter.  Sequential generation avoids the problem entirely:
# while one request is in the retry back-off window, no other request fires.
#
# Override via:  QUIZ_CONCURRENCY_CAP=2  (only on Tier-2+ API plans)
_CONCURRENCY_CAP = int(os.environ.get("QUIZ_CONCURRENCY_CAP", "1"))

# Extra sleep injected after each successfully completed question, still inside
# the semaphore.  Useful when concurrency > 1 to add stagger; harmless (but
# slower) when cap=1.  Set to 0 to disable.
_INTER_REQUEST_DELAY = float(os.environ.get("QUIZ_INTER_REQUEST_DELAY", "0.5"))


def _arm_for_mode(mode: str) -> str:
    return {"mix": "graph", "naive": "naive"}.get(mode, "other")


def _retrieval_complexity(mode: str, difficulty: str) -> int:
    if mode == "mix":
        return {"easy": 1, "medium": 2, "hard": 3}[difficulty]
    if mode == "naive":
        return {"easy": 1, "medium": 2, "hard": 3}[difficulty]
    # fallback modes: proxy via chunk_top_k
    return {"easy": 3, "medium": 5, "hard": 10}[difficulty]


def _build_retrieval_metadata(
    ctx: RetrievalContext,
    seed_strategy: str,
    seed_score: dict | None = None,
) -> RetrievalMetadata:
    return RetrievalMetadata(
        entities=[e.get("entity_name", "") for e in ctx.entities],
        relations=ctx.relations,
        bfs_path=ctx.bfs_path,
        chunk_ids=[c.get("id", c.get("chunk_id", "")) for c in ctx.chunks],
        hop_depth=ctx.hop_depth,
        source_documents=ctx.source_documents,
        seed_query=ctx.seed_query,
        seed_strategy=seed_strategy,
        seed_score=(seed_score or {}).get("rrf_score"),
        seed_score_components=(seed_score or {}).get("ranks", {}),
    )


async def _generate_one(
    rag: "LightRAG",
    quiz_id: str,
    seed: str,
    seed_strategy: str,
    req: QuizGenerateRequest,
    *,
    prior_questions: List[str] | None = None,
    seed_score: dict | None = None,
) -> QuizQuestionMetadata:
    """Generate, optionally verify, and return metadata for one question.

    ``prior_questions`` is surfaced to the generator so it can avoid
    repeating or rephrasing earlier questions in the same quiz — see R5
    in quiz-fix-plan.md.
    """

    # 1. Retrieve
    scope_doc_ids = set(req.document_ids)
    if req.mode == "mix":
        ctx = await retrieve_mix_arm(rag, seed, req.difficulty, scope_doc_ids)
    elif req.mode == "naive":
        ctx = await retrieve_naive_arm(rag, seed, req.difficulty, scope_doc_ids)
    else:
        ctx = await retrieve_fallback(rag, seed, req.mode, req.difficulty, scope_doc_ids)

    arm = _arm_for_mode(req.mode)
    claimed_complexity = _retrieval_complexity(req.mode, req.difficulty)
    claimed_reasoning = REASONING_TYPE[req.difficulty]

    # 1.5 Anti-hallucination guard. When retrieval returns nothing, the
    # generator would otherwise fall back on GPT-4o-mini's training data
    # and produce an answer that *looks* plausible but cannot be traced
    # to any selected document — the failure mode seen in
    # quiz-44fbc845-… (5/25 questions with chunks=[] and fabricated
    # answers about ``kill`` system calls). Skip the seed and let the
    # bounded-generate wrapper convert this into a warning, dropping
    # the quiz count rather than emitting an ungrounded question.
    if ctx.is_empty():
        raise RuntimeError(
            f"Refusing to generate from empty retrieval (seed={seed!r}). "
            "Question would be ungrounded in the selected documents."
        )

    # 2. Generate
    # Resolve generation model once (same order as generation.py's internal logic)
    generation_model = (
        os.environ.get("QUIZ_GENERATION_MODEL", "")
        or os.environ.get("LLM_MODEL", "")
        or "gpt-4o-mini"
    )
    # Normalize the seed to a concept noun so the LLM doesn't see
    # ``Target concept: Thread 3`` or ``Target concept: P_0`` — those
    # would feed back into instance-label questions.
    target = normalize_concept_name(seed)
    question, reference_answer = await generate_question(
        ctx,
        req.difficulty,
        model=generation_model,
        target_concept=target,
        prior_questions=prior_questions,
    )

    # 3. Build metadata
    retrieval_meta = _build_retrieval_metadata(ctx, seed_strategy, seed_score)

    # Diagnostic metrics — non-behavioral, surface extraction-like shapes
    # the verifier prompt can't catch. See lightrag/quiz/diagnostics.py.
    top_chunk_text = ""
    if ctx.chunks:
        top_chunk_text = ctx.chunks[0].get("content", ctx.chunks[0].get("text", ""))
    fig_dep = estimate_figure_dependency(question, reference_answer)
    lex_overlap = source_lexical_overlap(question, top_chunk_text)
    clarity = estimate_clarity(question)
    chunk_count = len(ctx.chunks) if ctx.chunks else 0

    generation_meta = GenerationMetadata(
        model=generation_model,
        prompt_template_id=PROMPT_TEMPLATE_IDS[req.difficulty],
        question=question,
        reference_answer=reference_answer,
        figure_dependency_estimate=fig_dep,
        source_lexical_overlap=lex_overlap,
        clarity_heuristic=clarity,
        retrieved_chunk_count=chunk_count,
    )

    # 4. Evaluate (optional). The verifier (the locked instrument), the pedagogy
    # judge, and the opt-in correctness fact-check are independent LLM calls — run
    # whichever are enabled concurrently to keep per-question latency low.
    verification_meta = pedagogy_meta = correctness_meta = None
    jobs = []
    if req.run_verification:
        jobs.append((
            "verification",
            verify_question(
                question=question,
                reference_answer=reference_answer,
                context=ctx,
                claimed_complexity=claimed_complexity,
                claimed_reasoning_type=claimed_reasoning,
            ),
        ))
        jobs.append((
            "pedagogy",
            judge_pedagogy(question=question, reference_answer=reference_answer),
        ))
    if req.run_correctness_check:
        jobs.append((
            "correctness",
            judge_correctness(question=question, reference_answer=reference_answer),
        ))
    if jobs:
        done = await asyncio.gather(*(coro for _, coro in jobs))
        results = dict(zip((name for name, _ in jobs), done))
        verification_meta = results.get("verification")
        pedagogy_meta = results.get("pedagogy")
        correctness_meta = results.get("correctness")

    return QuizQuestionMetadata(
        question_id=str(uuid.uuid4()),
        arm=arm,
        difficulty=req.difficulty,
        claimed_retrieval_complexity=claimed_complexity,
        claimed_reasoning_type=claimed_reasoning,
        retrieval=retrieval_meta,
        generation=generation_meta,
        verification=verification_meta,
        pedagogy=pedagogy_meta,
        correctness=correctness_meta,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_quiz(rag: "LightRAG", req: QuizGenerateRequest) -> QuizGenerateResponse:
    """Full pipeline: seed → retrieve → generate → verify → persist."""
    quiz_id = str(uuid.uuid4())
    scope_doc_ids = set(req.document_ids)
    warnings: List[str] = []

    # Sample seeds
    selection = await sample_seeds(rag, req.mode, req.num_questions, scope_doc_ids)
    seeds = selection.seeds
    seed_strategy = selection.strategy
    # Align per-seed RRF scores with seeds (empty for the random baseline).
    seed_scores: List[dict | None]
    if selection.seed_scores and len(selection.seed_scores) == len(seeds):
        seed_scores = list(selection.seed_scores)
    else:
        seed_scores = [None] * len(seeds)

    if not seeds:
        if selection.authoritative:
            # The pedagogical scorer ran but nothing cleared the meaningfulness
            # floor (typically a figure/table-anchor-dominated file set). Honour
            # the empty quiz — do NOT fabricate topic_N placeholders or revert to
            # random seeds, which would mask the finding (quality-plan.md §6.1).
            warnings.append(
                "Seed selection found no candidates that clear the meaningfulness "
                "floor for the selected documents — returning an empty quiz "
                "(no placeholder padding). The chosen files are likely dominated "
                "by figure/table anchors with little teachable prose."
            )
        else:
            warnings.append(
                "No seeds could be sampled from the selected documents. "
                "Using generic placeholders — question quality may be low."
            )
            seeds = [f"topic_{i+1}" for i in range(req.num_questions)]
            seed_scores = [None] * len(seeds)

    # Transparency: surface files that contributed nothing (quality-plan.md §6.2).
    for fc in selection.file_contributions:
        if fc.get("seed_count", 0) == 0:
            warnings.append(
                f"File '{fc.get('doc_id')}' contributed 0 seeds "
                f"(reason: {fc.get('reason')})."
            )

    # Generate questions with concurrency cap.
    #
    # The prior-question list is read inside the semaphore so it reflects
    # every question that finished *before* this task acquired the lock.
    # With cap=1 (the default) this gives strict sequential ordering and
    # each call sees all earlier results — exactly what R5-1 needs to
    # avoid duplicate / paraphrased questions.
    semaphore = asyncio.Semaphore(_CONCURRENCY_CAP)
    prior_questions_so_far: List[str] = []

    async def _bounded_generate(
        seed: str, seed_score: dict | None
    ) -> QuizQuestionMetadata | None:
        async with semaphore:
            # Snapshot the priors at the moment we hold the semaphore so a
            # later release/acquire doesn't surprise us mid-call.
            priors_snapshot = list(prior_questions_so_far)
            try:
                result = await _generate_one(
                    rag, quiz_id, seed, seed_strategy, req,
                    prior_questions=priors_snapshot,
                    seed_score=seed_score,
                )
                if result is not None and result.generation.question:
                    prior_questions_so_far.append(result.generation.question)
                # Brief sleep after each question to spread TPM consumption
                # over time and avoid synchronised bursts from parallel workers.
                if _INTER_REQUEST_DELAY > 0:
                    await asyncio.sleep(_INTER_REQUEST_DELAY)
                return result
            except Exception as exc:
                warnings.append(f"Failed to generate question for seed '{seed}': {exc}")
                return None

    tasks = [
        _bounded_generate(seed, score) for seed, score in zip(seeds, seed_scores)
    ]
    results = await asyncio.gather(*tasks)
    questions = [q for q in results if q is not None]

    if seeds and not questions:
        warnings.append("All question generations failed — returning empty quiz.")

    # Quiz-level diversity metric (quality-plan.md §8.1). Best-effort: embed the
    # generated questions and report mean/max pairwise cosine similarity. Never
    # fails the quiz — disabled with QUIZ_COMPUTE_DIVERSITY=false.
    diversity: dict = {}
    if questions and os.environ.get("QUIZ_COMPUTE_DIVERSITY", "true").lower() == "true":
        q_texts = [q.generation.question for q in questions if q.generation.question]
        if len(q_texts) >= 2:
            try:
                vecs = await rag.embedding_func(q_texts)
                diversity = pairwise_cosine_stats(vecs)
            except Exception as exc:
                warnings.append(f"Diversity metric computation failed: {exc}")

    response = QuizGenerateResponse(
        quiz_id=quiz_id,
        created_at=datetime.now(timezone.utc),
        request=req,
        questions=questions,
        warnings=warnings,
        file_contributions=selection.file_contributions,
        diversity=diversity,
    )

    # Persist
    try:
        metadata_path = await save_quiz(rag.working_dir, response)
        response.metadata_path = metadata_path
    except Exception as exc:
        warnings.append(f"Failed to persist quiz to disk: {exc}")

    return response


async def reverify_quiz(rag: "LightRAG", quiz_id: str) -> QuizGenerateResponse:
    """Re-run Claude Sonnet verification on a stored quiz.

    Writes a versioned record ({quiz_id}.v2.json) and returns it.
    Phase 6: full implementation.
    Phase 1: load, re-verify with mock, save v2.
    """
    original = await load_quiz(rag.working_dir, quiz_id)
    semaphore = asyncio.Semaphore(_CONCURRENCY_CAP)

    async def _reverify_one(q: QuizQuestionMetadata) -> QuizQuestionMetadata:
        async with semaphore:
            # Reconstruct a minimal RetrievalContext for the verifier prompt
            from lightrag.quiz.retrieval import RetrievalContext

            ctx = RetrievalContext(
                bfs_path=q.retrieval.bfs_path,
                hop_depth=q.retrieval.hop_depth,
                seed_query=q.retrieval.seed_query,
                source_documents=q.retrieval.source_documents,
            )
            verification_meta = await verify_question(
                question=q.generation.question,
                reference_answer=q.generation.reference_answer,
                context=ctx,
                claimed_complexity=q.claimed_retrieval_complexity,
                claimed_reasoning_type=q.claimed_reasoning_type,
            )
            result = q.model_copy(update={"verification": verification_meta})
            if _INTER_REQUEST_DELAY > 0:
                await asyncio.sleep(_INTER_REQUEST_DELAY)
            return result

    tasks = [_reverify_one(q) for q in original.questions]
    reverified_questions = list(await asyncio.gather(*tasks))

    response = original.model_copy(
        update={
            "questions": reverified_questions,
            "created_at": datetime.now(timezone.utc),
        }
    )

    metadata_path = await save_reverified_quiz(rag.working_dir, response)
    response.metadata_path = metadata_path

    return response

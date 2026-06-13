"""Cross-file (folder-level) quiz service.

Reuses the research quiz pipeline read-only (lightrag/quiz/) for mix-arm pedagogical
seeding, diversity, file contributions, and cross-document BFS.  No naive arm, no
verification, no judges — generation is the only LLM cost.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.quiz import (
    FolderQuiz,
    FolderQuizAttempt,
    QuizDifficulty,
    QuizStatus,
)
from lightrag.api.sampai.services.engine_access import get_engine

logger = logging.getLogger("sampai.folder_quiz")

# SAMpai decides how many questions are worthwhile; this is just the upper rail we
# hand the allocator (it never pads, so the real count is usually lower). Stored as
# the quiz's num_questions (30 satisfies the IN (10,20,30) check constraint).
QUESTION_CEILING = 30
# Below this many generated questions, surface a "sparse selection" notice.
SPARSE_BELOW = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def folder_completed_docs(
    db: AsyncSession, folder_id: int, file_ids: list[int] | None = None
) -> list[tuple[int, str, str]]:
    """Return [(file_id, filename, rag_doc_id)] for COMPLETED files in a folder.

    When ``file_ids`` is given, restrict to that selection (the intersection of the
    requested ids and the folder's completed files) — this is what scopes a quiz to
    only the files the user picked. ``None`` means all completed files.
    """
    q = select(File.id, File.filename, File.rag_doc_id).where(
        File.folder_id == folder_id,
        File.processing_status == ProcessingStatus.COMPLETED,
        File.rag_doc_id.isnot(None),
    )
    if file_ids is not None:
        q = q.where(File.id.in_(file_ids))
    rows = (await db.execute(q)).all()
    return [(r.id, r.filename, r.rag_doc_id) for r in rows]


_LADDER = [QuizDifficulty.EASY, QuizDifficulty.MEDIUM, QuizDifficulty.HARD]

# A question counts as "mastered" (correct) at this 0–5 score or above.
CORRECT_THRESHOLD = 4


def _step_difficulty(anchor: QuizDifficulty, avg_score: float) -> QuizDifficulty:
    """Pure ladder step: from `anchor`, go up (avg≥0.8) / down (avg≤0.5) / hold."""
    try:
        idx = _LADDER.index(anchor)
    except ValueError:
        idx = 1
    if avg_score >= 0.8:
        idx = min(idx + 1, len(_LADDER) - 1)
    elif avg_score <= 0.5:
        idx = max(idx - 1, 0)
    return _LADDER[idx]


async def infer_difficulty(
    db: AsyncSession, user_id: int, folder_id: int
) -> tuple[QuizDifficulty, str]:
    """Adaptive ladder, smoothed over the last few *finished* attempts.

    Anchors on the student's most recent completed (SUBMITTED) folder quiz's
    difficulty — their current rung on the ladder — and steps from it using the
    MEAN aggregate score of the last up-to-3 finished attempts. Averaging keeps a
    single noisy quiz from swinging the difficulty, while anchoring on the most
    recent difficulty keeps "0.8 at hard" and "0.8 at easy" distinct. Did well
    (≥0.8) → step up; struggled (≤0.5) → step down; otherwise hold. No history →
    medium baseline.
    """
    rows = (
        await db.execute(
            select(FolderQuiz.difficulty, FolderQuizAttempt.score)
            .join(FolderQuizAttempt, FolderQuizAttempt.quiz_id == FolderQuiz.id)
            .where(
                FolderQuiz.user_id == user_id,
                FolderQuiz.folder_id == folder_id,
                FolderQuiz.status == QuizStatus.SUBMITTED,
                FolderQuizAttempt.score.isnot(None),
            )
            .order_by(FolderQuiz.created_at.desc())
            .limit(3)
        )
    ).all()
    if not rows:
        return QuizDifficulty.MEDIUM, "baseline"

    anchor = rows[0][0]  # most recent finished attempt's difficulty = current rung
    avg = sum(r[1] for r in rows) / len(rows)
    return _step_difficulty(anchor, avg), "inferred"


def _grade_of(ans: dict) -> int | None:
    """The 0–5 score on a stored answer (new per-question flow, or legacy fallback)."""
    if ans is None:
        return None
    if isinstance(ans.get("score"), int):
        return ans["score"]
    g = ans.get("llm_grade")  # legacy "Ask SAMpai" shape
    if isinstance(g, dict) and isinstance(g.get("score"), int):
        return g["score"]
    return None


def build_question_views(quiz: FolderQuiz, attempt: FolderQuizAttempt | None) -> list[dict]:
    """Unified per-question view. Reference answer + grade only on submitted questions."""
    answers_by_qid = {a["question_id"]: a for a in (attempt.answers or [])} if attempt else {}
    out = []
    for q in (quiz.questions or []):
        ans = answers_by_qid.get(q["id"])
        score = _grade_of(ans) if ans else None
        submitted = score is not None
        grade = (ans or {}).get("llm_grade") if isinstance((ans or {}).get("llm_grade"), dict) else {}
        out.append({
            "id": q["id"],
            "question": q["question"],
            "reasoning_type": q.get("reasoning_type", ""),
            "hop_depth": q.get("hop_depth"),
            "source_file_names": q.get("source_file_names", []),
            "submitted": submitted,
            "user_answer": (ans or {}).get("user_answer") if submitted else None,
            "reference_answer": q.get("reference_answer") if submitted else None,
            "score": score,
            "missing": (ans or {}).get("missing", grade.get("missing", [])) if submitted else [],
            "incorrect": (ans or {}).get("incorrect", grade.get("incorrect", [])) if submitted else [],
            "verdict": (ans or {}).get("verdict", grade.get("verdict")) if submitted else None,
        })
    return out


def aggregate_and_topics(
    questions: list[dict], answers: list[dict]
) -> tuple[float | None, int, list[dict]]:
    """Compute the attempt aggregate + per-file (topic) breakdown from graded answers.

    - aggregate = mean over graded questions of (score/5)  → 0–1.  At completion
      every question is graded, so this is the final personalization signal.
    - correct_count = # graded questions scoring ≥ CORRECT_THRESHOLD.
    - topic_scores  = per source file: mean normalized score across the questions
      that draw on it (a cross-file question contributes to each of its files).
    """
    qmeta = {q["id"]: q for q in (questions or [])}
    graded = {}
    for a in (answers or []):
        s = _grade_of(a)
        if s is not None:
            graded[a["question_id"]] = s
    if not graded:
        return None, 0, []

    norm = {qid: s / 5.0 for qid, s in graded.items()}
    agg = round(sum(norm.values()) / len(norm), 4)
    correct = sum(1 for s in graded.values() if s >= CORRECT_THRESHOLD)

    buckets: dict[int, dict] = {}
    for qid, s in graded.items():
        q = qmeta.get(qid, {})
        fids = q.get("source_file_ids", []) or []
        fnames = q.get("source_file_names", []) or []
        for i, fid in enumerate(fids):
            fn = fnames[i] if i < len(fnames) else str(fid)
            b = buckets.setdefault(fid, {"file_id": fid, "filename": fn, "sum": 0.0, "count": 0, "correct": 0})
            b["sum"] += norm[qid]
            b["count"] += 1
            if s >= CORRECT_THRESHOLD:
                b["correct"] += 1

    topic_scores = [
        {
            "file_id": b["file_id"],
            "filename": b["filename"],
            "mean_score": round(b["sum"] / b["count"], 4) if b["count"] else 0.0,
            "question_count": b["count"],
            "correct_count": b["correct"],
        }
        for b in buckets.values()
    ]
    topic_scores.sort(key=lambda t: t["filename"])
    return agg, correct, topic_scores


# ---------------------------------------------------------------------------
# Optional per-question LLM grade ("Ask SAMpai") — grading-time helper, NOT a
# generation-time judge. Compares the student's answer to the trusted reference
# answer and scores 0–5, penalising omissions and factual errors.
# ---------------------------------------------------------------------------

_GRADE_SYSTEM = (
    "You are grading a student's short written answer against a reference answer. "
    "The reference answer is the only ground truth — judge solely against it.\n\n"
    "Score from 0 to 5 using this rubric:\n"
    "5 = complete and fully correct: covers all key points in the reference, no factual errors.\n"
    "4 = minor omission only; no factual errors.\n"
    "3 = missing a key point OR contains a minor factual error.\n"
    "2 = a major omission OR a clear factual error.\n"
    "1 = barely addresses the question / mostly incorrect.\n"
    "0 = blank, irrelevant, or entirely wrong.\n\n"
    "Penalise the score for EVERY key point in the reference that the student's answer omits. "
    "Penalise more harshly for any statement that contradicts the reference (a factual error). "
    "Do NOT penalise correct paraphrasing, correct extra detail, or differences in wording.\n\n"
    'Return ONLY JSON: {"score": <int 0-5>, "missing": [<key points the student left out, short phrases>], '
    '"incorrect": [<statements in the answer that are wrong or contradict the reference>], '
    '"verdict": "<one-sentence summary of how the answer did>"}'
)


def _grade_model() -> str:
    return (
        os.environ.get("QUIZ_GENERATION_MODEL", "")
        or os.environ.get("LLM_MODEL", "")
        or "gpt-4o-mini"
    )


async def grade_answer_llm(question: str, reference_answer: str, user_answer: str) -> dict:
    """Grade one answer against its reference. Returns {score, missing, incorrect, verdict}.

    Blank answers short-circuit to score 0 with no LLM call. Any API/parse failure
    raises — the router surfaces it as a retryable 503 (self-grade remains available).
    """
    import json_repair

    if not (user_answer or "").strip():
        return {
            "score": 0,
            "missing": ["No answer was provided."],
            "incorrect": [],
            "verdict": "No answer was given for this question.",
        }

    api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("LLM_BINDING_API_KEY", "")
    if not api_key:
        raise RuntimeError("No OpenAI API key configured for grading.")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.environ.get("LLM_BINDING_HOST", "https://api.openai.com/v1"),
    )
    user_msg = (
        f"Question:\n{question}\n\n"
        f"Reference answer:\n{reference_answer}\n\n"
        f"Student answer:\n{user_answer}"
    )
    resp = await client.chat.completions.create(
        model=_grade_model(),
        messages=[
            {"role": "system", "content": _GRADE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=600,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json_repair.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Grader returned a non-object response.")

    try:
        score = int(round(float(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(5, score))

    def _strlist(v) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return {
        "score": score,
        "missing": _strlist(data.get("missing")),
        "incorrect": _strlist(data.get("incorrect")),
        "verdict": str(data.get("verdict", "")).strip(),
    }


# ---------------------------------------------------------------------------
# Background generation task
# ---------------------------------------------------------------------------

async def generate_folder_quiz_task(
    quiz_id: int,
    classroom_id: int,
    folder_id: int,
) -> None:
    """Background task: seed → retrieve → generate → persist. No judges."""
    from lightrag.quiz import QuizGenerateRequest, generate_quiz  # read-only reuse

    sm = get_sessionmaker()
    t0 = time.monotonic()

    async with sm() as db:
        quiz = await db.get(FolderQuiz, quiz_id)
        if quiz is None:
            return
        quiz.status = QuizStatus.GENERATING
        await db.commit()

    try:
        # 1. Gather completed docs — scoped to the files the user selected for this quiz.
        async with sm() as db:
            quiz = await db.get(FolderQuiz, quiz_id)
            selected = quiz.selected_file_ids if quiz else None
            docs = await folder_completed_docs(db, folder_id, selected)

        if not docs:
            async with sm() as db:
                quiz = await db.get(FolderQuiz, quiz_id)
                if quiz:
                    quiz.status = QuizStatus.FAILED
                    quiz.error_msg = "No completed files selected for this quiz."
                    await db.commit()
            return

        doc_ids = [d[2] for d in docs]
        doc_id_to_file = {d[2]: (d[0], d[1]) for d in docs}

        # 2. Get engine
        engine = await get_engine(classroom_id)

        # 3. Fetch stored difficulty for this quiz
        async with sm() as db:
            quiz = await db.get(FolderQuiz, quiz_id)
            difficulty_val = quiz.difficulty.value
            num_q = quiz.num_questions

        # 4. Call generate_quiz (mix-only, no judges).
        # model_construct bypasses the Literal[5,10,25,50] num_questions constraint —
        # the pipeline loop uses num_questions as an integer count, not a validated enum.
        req = QuizGenerateRequest.model_construct(
            document_ids=doc_ids,
            mode="mix",
            difficulty=difficulty_val,
            num_questions=num_q,
            run_verification=False,
            run_correctness_check=False,
        )
        resp = await generate_quiz(engine, req)

        elapsed = time.monotonic() - t0

        if not resp.questions:
            warnings_text = "; ".join(resp.warnings) or "No questions generated."
            async with sm() as db:
                quiz = await db.get(FolderQuiz, quiz_id)
                if quiz:
                    quiz.status = QuizStatus.FAILED
                    quiz.error_msg = warnings_text
                    await db.commit()
            return

        # 5. Build stored questions (assign q1..qN; per-question source attribution)
        stored_questions = []
        for i, q in enumerate(resp.questions):
            chunk_ids = q.retrieval.chunk_ids if q.retrieval else []
            contributing_doc_ids = [
                doc_id for doc_id in doc_ids
                if any(cid.startswith(doc_id) for cid in chunk_ids)
            ]
            src_files = [doc_id_to_file[d] for d in contributing_doc_ids if d in doc_id_to_file]
            stored_questions.append({
                "id": f"q{i + 1}",
                "question": q.generation.question,
                "reference_answer": q.generation.reference_answer,
                "reasoning_type": q.claimed_reasoning_type or "",
                "hop_depth": q.retrieval.hop_depth if q.retrieval else None,
                "source_file_ids": [f[0] for f in src_files],
                "source_file_names": [f[1] for f in src_files],
            })

        # 6. Build generation_meta
        # resp.file_contributions is a list of FileContribution Pydantic objects
        fc_with_names = []
        for fc in (resp.file_contributions or []):
            doc_id = fc.doc_id
            finfo = doc_id_to_file.get(doc_id)
            fc_with_names.append({
                "doc_id": doc_id,
                "filename": finfo[1] if finfo else doc_id,
                "file_id": finfo[0] if finfo else None,
                "seed_count": fc.seed_count,
                "reason": fc.reason,
            })

        # Student-facing notices only (curated). Raw research warnings — e.g. per-doc
        # "contributed 0 seeds (reason: outranked)" with raw doc ids — are kept under
        # gen_warnings for the record but NOT shown to the student.
        student_warnings = []
        if len(stored_questions) < SPARSE_BELOW:
            student_warnings.append(
                f"Only {len(stored_questions)} worthwhile question"
                f"{'' if len(stored_questions) == 1 else 's'} could be drawn from the selected "
                "file(s). Select more files for a longer quiz."
            )

        generation_meta = {
            "file_contributions": fc_with_names,
            "diversity": resp.diversity or {},
            "doc_ids": doc_ids,
            "model": os.environ.get("QUIZ_GENERATION_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini",
            "elapsed_s": round(elapsed, 1),
            "warnings": student_warnings,
            "gen_warnings": resp.warnings,
            "seed_strategy": "pedagogical",
        }

        # 7. Persist. Create the (empty) attempt now so per-question submits just
        #    append into it — avoids a get-or-create race on the first submit.
        async with sm() as db:
            quiz = await db.get(FolderQuiz, quiz_id)
            if quiz:
                quiz.status = QuizStatus.READY
                quiz.ready_at = datetime.utcnow()
                quiz.questions = stored_questions
                quiz.generation_meta = generation_meta
                if quiz.attempt is None:
                    db.add(FolderQuizAttempt(
                        quiz_id=quiz.id,
                        user_id=quiz.user_id,
                        folder_id=folder_id,
                        total_count=len(stored_questions),
                        answers=[],
                    ))
                await db.commit()

    except Exception as exc:
        logger.exception("folder quiz generation failed quiz_id=%s", quiz_id)
        async with sm() as db:
            quiz = await db.get(FolderQuiz, quiz_id)
            if quiz:
                quiz.status = QuizStatus.FAILED
                quiz.error_msg = str(exc)
                await db.commit()

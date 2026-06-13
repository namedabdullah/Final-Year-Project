"""Folder-level cross-file quiz routes.

One quiz spanning all completed files in a folder. Mix arm only, no generation
judges. Take flow: 202 generate → poll → submit EACH question (grades it 0–5 vs
its reference, reveals the reference + critique) → quiz auto-completes when every
question is graded. The aggregate LLM score drives the next quiz's auto-difficulty.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.quiz import (
    FolderQuiz,
    FolderQuizAttempt,
    QuizDifficulty,
    QuizStatus,
)
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.folder_quiz import (
    FolderQuizDetail,
    FolderQuizFileInfo,
    FolderQuizHistoryItem,
    FolderQuizHistoryResponse,
    GenerateFolderQuizRequest,
    GenerateFolderQuizResponse,
    SubmitQuestionRequest,
    SubmitQuestionResponse,
)
from lightrag.api.sampai.services import folder_quiz_service as svc

router = APIRouter(prefix="/folder-quiz", tags=["sampai-folder-quiz"])
logger = logging.getLogger("sampai.folder_quiz")

_OPEN = (QuizStatus.PENDING, QuizStatus.GENERATING, QuizStatus.READY)
_STALE_MIN = 5


async def _folder_classroom(db: AsyncSession, folder_id: int) -> tuple[Folder, int]:
    folder = await db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder, folder.classroom_id


async def _owned_quiz(db: AsyncSession, quiz_id: int, user: User) -> FolderQuiz:
    quiz = await db.get(FolderQuiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return quiz


def _detail_files(quiz: FolderQuiz) -> list[FolderQuizFileInfo]:
    if not quiz.generation_meta:
        return []
    return [
        FolderQuizFileInfo(
            file_id=fc.get("file_id"),
            filename=fc.get("filename", ""),
            seed_count=fc.get("seed_count", 0),
            reason=fc.get("reason", ""),
        )
        for fc in quiz.generation_meta.get("file_contributions", [])
    ]


def _detail(quiz: FolderQuiz) -> FolderQuizDetail:
    attempt = quiz.attempt
    qviews = svc.build_question_views(quiz, attempt)
    graded_count = sum(1 for v in qviews if v["submitted"])
    total_count = len(quiz.questions or [])

    if attempt and attempt.topic_scores:
        topics = attempt.topic_scores
        score = attempt.score
        correct = attempt.correct_count
    elif attempt:
        score, correct, topics = svc.aggregate_and_topics(quiz.questions or [], attempt.answers or [])
    else:
        score, correct, topics = None, None, []

    meta = quiz.generation_meta or {}
    return FolderQuizDetail(
        quiz_id=quiz.id,
        status=quiz.status.value,
        difficulty=quiz.difficulty.value,
        difficulty_source=quiz.difficulty_source,
        num_questions=quiz.num_questions,
        error_msg=quiz.error_msg,
        files=_detail_files(quiz),
        diversity=meta.get("diversity", {}),
        warnings=meta.get("warnings", []),
        questions=qviews,
        score=score,
        correct_count=correct,
        total_count=total_count,
        graded_count=graded_count,
        topic_scores=topics or [],
    )


@router.post("/folders/{folder_id}/generate", response_model=GenerateFolderQuizResponse, status_code=202)
async def generate(
    folder_id: int,
    body: GenerateFolderQuizRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder, classroom_id = await _folder_classroom(db, folder_id)
    await require_membership(classroom_id, db, user)

    # Scope to the user's file selection (intersection with the folder's completed
    # files). file_ids=None → all completed files (back-compatible).
    docs = await svc.folder_completed_docs(db, folder_id, body.file_ids)
    if not docs:
        detail = (
            "None of the selected files are ready (completed) yet."
            if body.file_ids
            else "No completed files in this folder yet."
        )
        raise HTTPException(status_code=400, detail=detail)
    selected_file_ids = [d[0] for d in docs]

    # One open quiz per (user, folder); auto-fail a stale GENERATING one.
    open_quiz = (
        await db.execute(
            select(FolderQuiz)
            .where(FolderQuiz.user_id == user.id, FolderQuiz.folder_id == folder_id, FolderQuiz.status.in_(_OPEN))
            .order_by(FolderQuiz.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    if open_quiz is not None:
        age = datetime.now(timezone.utc) - open_quiz.created_at.replace(tzinfo=timezone.utc)
        if open_quiz.status == QuizStatus.GENERATING and age > timedelta(minutes=_STALE_MIN):
            open_quiz.status = QuizStatus.FAILED
            open_quiz.error_msg = "Generation timed out."
            await db.commit()
        else:
            raise HTTPException(status_code=409, detail="A quiz is already open for this folder.")

    if body.difficulty is not None:
        difficulty = QuizDifficulty(body.difficulty)
        difficulty_source = "manual"
    else:
        difficulty, difficulty_source = await svc.infer_difficulty(db, user.id, folder_id)

    quiz = FolderQuiz(
        folder_id=folder_id,
        user_id=user.id,
        status=QuizStatus.PENDING,
        difficulty=difficulty,
        difficulty_source=difficulty_source,
        num_questions=svc.QUESTION_CEILING,  # internal upper rail; allocator returns fewer (no padding)
        selected_file_ids=selected_file_ids,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)

    asyncio.create_task(svc.generate_folder_quiz_task(quiz.id, classroom_id, folder_id))
    return GenerateFolderQuizResponse(quiz_id=quiz.id, status=quiz.status.value)


@router.get("/{quiz_id}", response_model=FolderQuizDetail)
async def get_quiz(
    quiz_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    quiz = await _owned_quiz(db, quiz_id, user)
    return _detail(quiz)


@router.post("/{quiz_id}/questions/{question_id}/submit", response_model=SubmitQuestionResponse)
async def submit_question(
    quiz_id: int,
    question_id: str,
    body: SubmitQuestionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit one answer: grade it 0–5 vs its reference, reveal reference + critique.

    When every question has been submitted the quiz finalizes (status SUBMITTED)
    and the aggregate score + per-topic breakdown are written for personalization.
    """
    quiz = await _owned_quiz(db, quiz_id, user)
    if quiz.status != QuizStatus.READY:
        raise HTTPException(status_code=409, detail="This quiz is not open for answering.")

    questions = quiz.questions or []
    qmap = {q["id"]: q for q in questions}
    question = qmap.get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found in this quiz.")

    attempt = quiz.attempt
    if attempt is None:  # safety net (the generation task normally creates it)
        attempt = FolderQuizAttempt(
            quiz_id=quiz.id, user_id=user.id, folder_id=quiz.folder_id,
            total_count=len(questions), answers=[],
        )
        db.add(attempt)
        await db.flush()

    answers = list(attempt.answers or [])
    already = next((a for a in answers if a.get("question_id") == question_id and svc._grade_of(a) is not None), None)
    if already is not None:
        raise HTTPException(status_code=409, detail="This question has already been submitted.")

    # Grade against the reference. On failure: 503, nothing stored → the student
    # can retry submitting this question.
    try:
        grade = await svc.grade_answer_llm(
            question=question["question"],
            reference_answer=question.get("reference_answer", ""),
            user_answer=body.user_answer,
        )
    except Exception as exc:
        logger.warning("grade failed quiz=%s q=%s: %s", quiz_id, question_id, exc)
        raise HTTPException(status_code=503, detail="Grading is unavailable right now — please retry.")

    answers = [a for a in answers if a.get("question_id") != question_id]
    answers.append({
        "question_id": question_id,
        "user_answer": body.user_answer,
        "score": grade["score"],
        "missing": grade["missing"],
        "incorrect": grade["incorrect"],
        "verdict": grade["verdict"],
        "submitted_at": datetime.utcnow().isoformat(),
    })
    attempt.answers = answers

    score, correct, topics = svc.aggregate_and_topics(questions, answers)
    attempt.score = score
    attempt.correct_count = correct
    attempt.topic_scores = topics

    graded_count = sum(1 for a in answers if svc._grade_of(a) is not None)
    finished = graded_count >= len(questions)
    if finished:
        quiz.status = QuizStatus.SUBMITTED

    await db.commit()

    return SubmitQuestionResponse(
        question_id=question_id,
        score=grade["score"],
        missing=grade["missing"],
        incorrect=grade["incorrect"],
        verdict=grade["verdict"],
        reference_answer=question.get("reference_answer", ""),
        finished=finished,
        aggregate_score=score,
        correct_count=correct,
        graded_count=graded_count,
        total_count=len(questions),
    )


@router.get("/folders/{folder_id}/history", response_model=FolderQuizHistoryResponse)
async def history(
    folder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    folder, classroom_id = await _folder_classroom(db, folder_id)
    await require_membership(classroom_id, db, user)

    docs = await svc.folder_completed_docs(db, folder_id)
    completed_n = len(docs)

    quizzes = (
        await db.execute(
            select(FolderQuiz)
            .where(FolderQuiz.user_id == user.id, FolderQuiz.folder_id == folder_id)
            .order_by(FolderQuiz.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    items = []
    for q in quizzes:
        attempt = q.attempt
        graded = 0
        if attempt:
            graded = sum(1 for a in (attempt.answers or []) if svc._grade_of(a) is not None)
        # n_files = how many files THIS quiz covered (its selection), else folder total.
        n_files = len(q.selected_file_ids) if q.selected_file_ids else completed_n
        items.append(FolderQuizHistoryItem(
            quiz_id=q.id,
            difficulty=q.difficulty.value,
            num_questions=q.num_questions,
            status=q.status.value,
            score=attempt.score if attempt else None,
            graded_count=graded,
            total_count=len(q.questions or []),
            submitted_at=attempt.submitted_at if attempt else None,
            created_at=q.created_at,
            ready_at=q.ready_at,
            n_files=n_files,
        ))

    open_q = next((q for q in quizzes if q.status in _OPEN), None)
    return FolderQuizHistoryResponse(
        items=items,
        has_open_quiz=open_q is not None,
        open_quiz_id=open_q.id if open_q else None,
    )

"""Quiz routes: generate (202), poll, submit, history. Per file, per user.

Mirrors the flashcard async-generation contract: one open quiz per (user, file),
5-minute stale-abandon, poll a GET endpoint, resume from history on tab mount.
Answers are never sent before submission.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user, require_membership
from lightrag.api.sampai.models.classroom import Folder
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.quiz import Quiz, QuizAttempt, QuizDifficulty, QuizStatus
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.quiz import (
    GenerateQuizRequest,
    GenerateQuizResponse,
    QuizAttemptResult,
    QuizDetail,
    QuizHistoryItem,
    QuizHistoryResponse,
    SubmitQuizRequest,
)
from lightrag.api.sampai.services import quiz_service

router = APIRouter(prefix="/quiz", tags=["sampai-quiz"])
logger = logging.getLogger("sampai.quiz")

_OPEN = (QuizStatus.PENDING, QuizStatus.GENERATING, QuizStatus.READY)
_STALE_MIN = 5


async def _file_classroom(db: AsyncSession, file_id: int) -> tuple[File, int]:
    file = await db.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    folder = await db.get(Folder, file.folder_id)
    return file, folder.classroom_id


async def _owned_quiz(db: AsyncSession, quiz_id: int, user: User) -> Quiz:
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return quiz


def _stored(quiz: Quiz) -> list[dict]:
    return (quiz.questions or {}).get("questions", []) if quiz.questions else []


@router.post("/files/{file_id}/generate", response_model=GenerateQuizResponse, status_code=202)
async def generate_quiz(
    file_id: int,
    body: GenerateQuizRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)
    if file.processing_status != ProcessingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="File is still processing")

    # One open quiz per (user, file); auto-fail a stale GENERATING one.
    open_quiz = (
        await db.execute(
            select(Quiz)
            .where(Quiz.user_id == user.id, Quiz.file_id == file_id, Quiz.status.in_(_OPEN))
            .order_by(Quiz.created_at.desc())
        )
    ).scalars().first()
    if open_quiz is not None:
        stale = datetime.utcnow() - timedelta(minutes=_STALE_MIN)
        if open_quiz.status == QuizStatus.GENERATING and open_quiz.created_at < stale:
            open_quiz.status = QuizStatus.FAILED
            open_quiz.error_msg = "abandoned — timed out during generation"
            await db.commit()
        else:
            raise HTTPException(status_code=409, detail="You already have an open quiz for this file. Submit it first.")

    if body.difficulty is not None:
        difficulty, source = QuizDifficulty(body.difficulty), "manual"
    else:
        difficulty, source = await quiz_service.infer_difficulty(db, user.id, file_id)

    quiz = Quiz(
        file_id=file_id,
        user_id=user.id,
        status=QuizStatus.PENDING,
        difficulty=difficulty,
        difficulty_source=source,
        num_questions=body.num_questions,
    )
    db.add(quiz)
    await db.commit()
    await db.refresh(quiz)

    asyncio.create_task(
        quiz_service.generate_quiz_task(quiz.id, classroom_id, file_id, file.rag_doc_id)
    )
    logger.info("quiz %s queued file=%s difficulty=%s(%s)", quiz.id, file_id, difficulty.value, source)
    return GenerateQuizResponse(quiz_id=quiz.id, status="pending")


@router.get("/{quiz_id}", response_model=QuizDetail)
async def poll_quiz(quiz_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    quiz = await _owned_quiz(db, quiz_id, user)

    review = None
    questions = None
    if quiz.status == QuizStatus.SUBMITTED:
        attempt = (
            await db.execute(select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id))
        ).scalar_one_or_none()
        if attempt is not None:
            review = QuizAttemptResult(
                score=attempt.score,
                correct_count=attempt.correct_count,
                total_count=attempt.total_count,
                answers=attempt.answers.get("answers", []) if isinstance(attempt.answers, dict) else attempt.answers,
                submitted_at=attempt.submitted_at,
            )
    elif quiz.status == QuizStatus.READY:
        questions = quiz_service.public_questions(_stored(quiz))

    return QuizDetail(
        quiz_id=quiz.id,
        status=quiz.status.value,
        difficulty=quiz.difficulty.value,
        difficulty_source=quiz.difficulty_source,
        num_questions=quiz.num_questions,
        error_msg=quiz.error_msg,
        questions=questions,
        review=review,
    )


@router.post("/{quiz_id}/submit", response_model=QuizAttemptResult)
async def submit_quiz(
    quiz_id: int,
    body: SubmitQuizRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    quiz = await _owned_quiz(db, quiz_id, user)
    if quiz.status == QuizStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Quiz already submitted")
    if quiz.status != QuizStatus.READY:
        raise HTTPException(status_code=400, detail="Quiz is not ready to submit")

    submitted = {
        a.question_id: {"answer_index": a.answer_index, "answer_bool": a.answer_bool}
        for a in body.answers
    }
    result = quiz_service.grade(_stored(quiz), submitted)

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        file_id=quiz.file_id,
        score=result["score"],
        correct_count=result["correct_count"],
        total_count=result["total_count"],
        answers={"answers": result["answers"]},
    )
    db.add(attempt)
    quiz.status = QuizStatus.SUBMITTED
    await db.commit()
    await db.refresh(attempt)
    return QuizAttemptResult(
        score=attempt.score,
        correct_count=attempt.correct_count,
        total_count=attempt.total_count,
        answers=result["answers"],
        submitted_at=attempt.submitted_at,
    )


@router.get("/files/{file_id}/history", response_model=QuizHistoryResponse)
async def quiz_history(file_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _, classroom_id = await _file_classroom(db, file_id)
    await require_membership(classroom_id, db, user)

    quizzes = (
        await db.execute(
            select(Quiz)
            .where(Quiz.user_id == user.id, Quiz.file_id == file_id)
            .order_by(Quiz.created_at.desc())
        )
    ).scalars().all()
    attempts = {
        a.quiz_id: a
        for a in (
            await db.execute(select(QuizAttempt).where(QuizAttempt.user_id == user.id, QuizAttempt.file_id == file_id))
        ).scalars().all()
    }

    items: list[QuizHistoryItem] = []
    has_open = False
    open_id = None
    for q in quizzes:
        att = attempts.get(q.id)
        items.append(QuizHistoryItem(
            quiz_id=q.id,
            difficulty=q.difficulty.value,
            num_questions=q.num_questions,
            status=q.status.value,
            score=att.score if att else None,
            correct_count=att.correct_count if att else None,
            submitted_at=att.submitted_at if att else None,
            created_at=q.created_at,
            ready_at=q.ready_at,
        ))
        if q.status in _OPEN and not has_open:
            has_open, open_id = True, q.id

    return QuizHistoryResponse(items=items, has_open_quiz=has_open, open_quiz_id=open_id)

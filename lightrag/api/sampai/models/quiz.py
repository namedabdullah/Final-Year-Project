"""Quizzes + attempts (per file, per user). Questions stored as JSONB."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lightrag.api.sampai.models.base import Base


class QuizStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    SUBMITTED = "submitted"


class QuizDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


def _enum(e):
    return SQLEnum(e, values_callable=lambda x: [m.value for m in x])


class Quiz(Base):
    __tablename__ = "quizzes"
    __table_args__ = (
        CheckConstraint("num_questions IN (5, 10, 15)", name="num_questions"),
        Index("ix_quiz_user_file", "user_id", "file_id"),
        Index("ix_quiz_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[QuizStatus] = mapped_column(_enum(QuizStatus), nullable=False, default=QuizStatus.PENDING)
    difficulty: Mapped[QuizDifficulty] = mapped_column(_enum(QuizDifficulty), nullable=False)
    difficulty_source: Mapped[str] = mapped_column(String(20), nullable=False)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    questions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    attempt = relationship(
        "QuizAttempt", back_populates="quiz", uselist=False, cascade="all, delete-orphan"
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (Index("ix_attempt_user_file", "user_id", "file_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    quiz = relationship("Quiz", back_populates="attempt")


# ---------------------------------------------------------------------------
# Cross-file (folder-level) quiz — new tables, fully separate from Quiz above.
# ---------------------------------------------------------------------------


class FolderQuiz(Base):
    __tablename__ = "folder_quizzes"
    __table_args__ = (
        CheckConstraint("num_questions IN (10, 20, 30)", name="fq_num_questions"),
        Index("ix_fq_user_folder", "user_id", "folder_id"),
        Index("ix_fq_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[QuizStatus] = mapped_column(_enum(QuizStatus), nullable=False, default=QuizStatus.PENDING)
    difficulty: Mapped[QuizDifficulty] = mapped_column(_enum(QuizDifficulty), nullable=False)
    difficulty_source: Mapped[str] = mapped_column(String(20), nullable=False)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_file_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # subset of folder files this quiz covers
    questions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    attempt = relationship(
        "FolderQuizAttempt", back_populates="quiz", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )


class FolderQuizAttempt(Base):
    __tablename__ = "folder_quiz_attempts"
    __table_args__ = (Index("ix_fqa_user_folder", "user_id", "folder_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("folder_quizzes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    topic_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    quiz = relationship("FolderQuiz", back_populates="attempt")

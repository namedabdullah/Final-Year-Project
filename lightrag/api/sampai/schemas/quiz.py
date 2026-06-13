"""Quiz schemas — per-file adaptive quiz (MCQ + True/False)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

QuestionType = Literal["mcq", "tf"]


class GenerateQuizRequest(BaseModel):
    num_questions: Literal[5, 10, 15] = 10
    difficulty: Literal["easy", "medium", "hard"] | None = Field(
        None, description="Omit to auto-infer from the student's chat history + recent scores."
    )


class GenerateQuizResponse(BaseModel):
    quiz_id: int
    status: str


class QuizQuestionPublic(BaseModel):
    """A question as shown to the student (no answer)."""
    id: str
    type: QuestionType
    question: str
    options: list[str] = []  # MCQ choices; empty for True/False


class QuizAnswerReview(BaseModel):
    """A question after submission, with the student's answer + correctness."""
    id: str
    type: QuestionType
    question: str
    options: list[str] = []
    user_answer: int | bool | None = None  # MCQ = chosen index; TF = bool
    correct_answer: int | bool
    correct: bool
    explanation: str = ""


class QuizAttemptResult(BaseModel):
    score: float  # 0..1
    correct_count: int
    total_count: int
    answers: list[QuizAnswerReview]
    submitted_at: datetime | None = None


class QuizDetail(BaseModel):
    """Poll payload. Questions appear only when READY+unattempted; review when SUBMITTED."""
    quiz_id: int
    status: Literal["pending", "generating", "ready", "failed", "submitted"]
    difficulty: str
    difficulty_source: str
    num_questions: int
    error_msg: str | None = None
    questions: list[QuizQuestionPublic] | None = None
    review: QuizAttemptResult | None = None


class SubmitAnswer(BaseModel):
    question_id: str
    answer_index: int | None = None  # MCQ = chosen option index
    answer_bool: bool | None = None  # True/False answer


class SubmitQuizRequest(BaseModel):
    answers: list[SubmitAnswer]


class QuizHistoryItem(BaseModel):
    quiz_id: int
    difficulty: str
    num_questions: int
    status: str
    score: float | None = None
    correct_count: int | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    ready_at: datetime | None = None


class QuizHistoryResponse(BaseModel):
    items: list[QuizHistoryItem]
    has_open_quiz: bool
    open_quiz_id: int | None = None

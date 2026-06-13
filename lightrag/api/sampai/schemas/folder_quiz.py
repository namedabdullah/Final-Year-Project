"""Schemas for the cross-file (folder-level) quiz feature.

Take flow: each question is answered and submitted individually. Submitting a
question reveals its reference answer + an LLM critique (what's wrong / missing)
and a 0–5 score. The mean of those scores is the attempt aggregate that drives
auto-difficulty for the next quiz; a per-file (topic) breakdown rolls up into it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GenerateFolderQuizRequest(BaseModel):
    # No num_questions: SAMpai decides how many worthwhile questions exist (capped
    # internally). The allocator never pads, so a thin selection yields fewer.
    difficulty: Literal["easy", "medium", "hard"] | None = None  # None = auto-infer
    file_ids: list[int] | None = None  # subset of the folder's completed files; None = all


class GenerateFolderQuizResponse(BaseModel):
    quiz_id: int
    status: str


class QuestionView(BaseModel):
    """One question in a quiz. Reference answer + grade appear only once submitted."""

    id: str
    question: str
    reasoning_type: str
    hop_depth: int | None = None
    source_file_names: list[str] = []
    submitted: bool = False
    user_answer: str | None = None
    reference_answer: str | None = None  # hidden until this question is submitted
    score: int | None = None  # 0–5
    missing: list[str] = []
    incorrect: list[str] = []
    verdict: str | None = None


class SubmitQuestionRequest(BaseModel):
    user_answer: str = ""


class SubmitQuestionResponse(BaseModel):
    question_id: str
    score: int  # 0–5 for this question
    missing: list[str] = []
    incorrect: list[str] = []
    verdict: str = ""
    reference_answer: str = ""
    # quiz-level progress after this submission
    finished: bool = False
    aggregate_score: float | None = None  # 0–1, mean over graded questions
    correct_count: int | None = None
    graded_count: int = 0
    total_count: int = 0


class TopicScore(BaseModel):
    file_id: int | None = None
    filename: str
    mean_score: float  # 0–1
    question_count: int
    correct_count: int


class FolderQuizFileInfo(BaseModel):
    file_id: int | None = None
    filename: str
    seed_count: int
    reason: str


class FolderQuizDetail(BaseModel):
    quiz_id: int
    status: str
    difficulty: str
    difficulty_source: str
    num_questions: int
    error_msg: str | None = None
    files: list[FolderQuizFileInfo] = []
    diversity: dict = {}
    warnings: list[str] = []
    questions: list[QuestionView] = []
    score: float | None = None  # aggregate 0–1 (running while in progress, final when submitted)
    correct_count: int | None = None
    total_count: int = 0  # number of questions actually generated
    graded_count: int = 0
    topic_scores: list[TopicScore] = []


class FolderQuizHistoryItem(BaseModel):
    quiz_id: int
    difficulty: str
    num_questions: int
    status: str
    score: float | None = None
    graded_count: int = 0
    total_count: int = 0
    submitted_at: datetime | None = None
    created_at: datetime
    ready_at: datetime | None = None
    n_files: int


class FolderQuizHistoryResponse(BaseModel):
    items: list[FolderQuizHistoryItem]
    has_open_quiz: bool
    open_quiz_id: int | None = None

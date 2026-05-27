"""
LightRAG Quiz Generation Module

Implements a difficulty-aware quiz generation pipeline for knowledge graph
and vector RAG comparison (thesis: mix vs naive retrieval arms).

Phases:
  Phase 1 — Backend skeleton (mock endpoint, no LLM calls)
  Phase 2 — Frontend skeleton wired to mock
  Phase 3 — Real retrieval logic (BFS for mix, controlled k for naive)
  Phase 4 — GPT-4o generation
  Phase 5 — Claude Sonnet verification
  Phase 6 — Persistence + list/get/reverify endpoints
"""

from lightrag.quiz.schemas import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionMetadata,
    QuizSummary,
)
from lightrag.quiz.pipeline import generate_quiz, reverify_quiz
from lightrag.quiz.storage import list_quizzes, load_quiz

__all__ = [
    "QuizGenerateRequest",
    "QuizGenerateResponse",
    "QuizQuestionMetadata",
    "QuizSummary",
    "generate_quiz",
    "reverify_quiz",
    "list_quizzes",
    "load_quiz",
]

"""
Per-quiz JSON persistence.

Layout:
  {working_dir}/quizzes/{quiz_id}.json       — primary record
  {working_dir}/quizzes/{quiz_id}.v2.json    — re-verification result (never overwrites original)

Phase 1: save_quiz / list_quizzes / load_quiz implemented.
Phase 6: reverify versioned write implemented.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from lightrag.quiz.schemas import QuizGenerateRequest, QuizGenerateResponse, QuizSummary


def _quizzes_dir(working_dir: str) -> Path:
    path = Path(working_dir) / "quizzes"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_quiz(
    working_dir: str,
    response: QuizGenerateResponse,
) -> str:
    """Persist a quiz response to disk. Returns the file path."""
    dir_path = _quizzes_dir(working_dir)
    file_path = dir_path / f"{response.quiz_id}.json"
    file_path.write_text(
        response.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return str(file_path)


async def load_quiz(working_dir: str, quiz_id: str) -> QuizGenerateResponse:
    """Load a quiz response from disk.  Raises FileNotFoundError if missing."""
    dir_path = _quizzes_dir(working_dir)

    # Try versioned file first (latest re-verification), then original
    for candidate in [f"{quiz_id}.v2.json", f"{quiz_id}.json"]:
        candidate_path = dir_path / candidate
        if candidate_path.exists():
            data = json.loads(candidate_path.read_text(encoding="utf-8"))
            return QuizGenerateResponse(**data)

    raise FileNotFoundError(f"Quiz '{quiz_id}' not found in {dir_path}")


async def list_quizzes(working_dir: str) -> List[QuizSummary]:
    """Scan the quizzes directory and return lightweight summaries."""
    dir_path = _quizzes_dir(working_dir)
    summaries: List[QuizSummary] = []

    for json_file in sorted(dir_path.glob("*.json")):
        # Skip versioned files — they're covered by the primary record's entry
        if json_file.stem.endswith(".v2"):
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            req = data.get("request", {})
            questions = data.get("questions", [])

            # Compute verifier pass rate
            verified = [
                q for q in questions
                if q.get("verification") and q["verification"].get("answerable_from_context")
            ]
            pass_rate: Optional[float] = None
            if questions and any(q.get("verification") for q in questions):
                pass_rate = len(verified) / len(questions)

            summaries.append(
                QuizSummary(
                    quiz_id=data.get("quiz_id", json_file.stem),
                    created_at=datetime.fromisoformat(
                        data.get("created_at", "2000-01-01T00:00:00")
                    ),
                    mode=req.get("mode", ""),
                    difficulty=req.get("difficulty", ""),
                    num_questions=req.get("num_questions", 0),
                    question_count=len(questions),
                    verifier_pass_rate=pass_rate,
                    metadata_path=str(json_file),
                )
            )
        except Exception:
            # Corrupted file — skip gracefully
            continue

    # Most recent first
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


async def save_reverified_quiz(
    working_dir: str,
    response: QuizGenerateResponse,
) -> str:
    """Write a re-verified quiz to a versioned file (never overwrites original)."""
    dir_path = _quizzes_dir(working_dir)
    file_path = dir_path / f"{response.quiz_id}.v2.json"
    file_path.write_text(
        response.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return str(file_path)

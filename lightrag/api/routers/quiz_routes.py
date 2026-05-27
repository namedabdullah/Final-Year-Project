"""
Quiz Generation API router.

Endpoints:
  POST /quiz/generate          — generate a quiz for selected documents
  GET  /quiz/list              — list previously generated quizzes
  GET  /quiz/{quiz_id}         — retrieve a stored quiz by ID
  POST /quiz/{quiz_id}/verify  — re-run verification on a stored quiz

Auth pattern mirrors query_routes.py: every endpoint uses combined_auth
(Bearer JWT + X-API-Key header).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from lightrag import LightRAG
from lightrag.api.utils_api import get_combined_auth_dependency
from lightrag.quiz.pipeline import generate_quiz, reverify_quiz
from lightrag.quiz.schemas import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizSummary,
)
from lightrag.quiz.storage import list_quizzes, load_quiz


def create_quiz_routes(
    rag: LightRAG,
    api_key: Optional[str] = None,
) -> APIRouter:
    """Factory — returns an APIRouter configured for the given LightRAG instance."""
    router = APIRouter(prefix="/quiz", tags=["quiz"])
    combined_auth = get_combined_auth_dependency(api_key)

    # ------------------------------------------------------------------
    # POST /quiz/generate
    # ------------------------------------------------------------------

    @router.post(
        "/generate",
        response_model=QuizGenerateResponse,
        dependencies=[Depends(combined_auth)],
        summary="Generate a quiz",
        description=(
            "Generate quiz questions for the selected documents using the "
            "difficulty-aware retrieval pipeline.  mix and naive modes use "
            "thesis-rigorous mechanics (custom BFS / controlled chunk-k).  "
            "Other modes use top_k scaling as a coarse proxy."
        ),
    )
    async def generate(req: QuizGenerateRequest) -> QuizGenerateResponse:
        if not req.document_ids:
            raise HTTPException(
                status_code=400,
                detail="document_ids must contain at least one document ID.",
            )
        try:
            return await generate_quiz(rag, req)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Quiz generation failed: {exc}",
            )

    # ------------------------------------------------------------------
    # GET /quiz/list
    # ------------------------------------------------------------------

    @router.get(
        "/list",
        response_model=List[QuizSummary],
        dependencies=[Depends(combined_auth)],
        summary="List quizzes",
        description="Return lightweight summaries of all previously generated quizzes.",
    )
    async def list_all() -> List[QuizSummary]:
        try:
            return await list_quizzes(rag.working_dir)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list quizzes: {exc}",
            )

    # ------------------------------------------------------------------
    # GET /quiz/{quiz_id}
    # ------------------------------------------------------------------

    @router.get(
        "/{quiz_id}",
        response_model=QuizGenerateResponse,
        dependencies=[Depends(combined_auth)],
        summary="Get quiz by ID",
        description="Retrieve the full metadata record for a stored quiz.",
    )
    async def get_quiz(quiz_id: str) -> QuizGenerateResponse:
        try:
            return await load_quiz(rag.working_dir, quiz_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Quiz '{quiz_id}' not found.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load quiz: {exc}",
            )

    # ------------------------------------------------------------------
    # POST /quiz/{quiz_id}/verify
    # ------------------------------------------------------------------

    @router.post(
        "/{quiz_id}/verify",
        response_model=QuizGenerateResponse,
        dependencies=[Depends(combined_auth)],
        summary="Re-verify a quiz",
        description=(
            "Re-run Claude Sonnet verification on a stored quiz.  "
            "Writes a versioned record ({quiz_id}.v2.json) and returns it.  "
            "The original file is never overwritten."
        ),
    )
    async def reverify(quiz_id: str) -> QuizGenerateResponse:
        try:
            return await reverify_quiz(rag, quiz_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Quiz '{quiz_id}' not found.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Re-verification failed: {exc}",
            )

    return router

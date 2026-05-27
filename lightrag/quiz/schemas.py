"""
Pydantic schemas for the Quiz Generation module.

These models define the API contract for POST /quiz/generate and its
response shape, plus all the sub-models for retrieval, generation, and
verification metadata.  They mirror the "Metadata Schema (Comprehensive)"
described in claude_review_rag_framework.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class QuizGenerateRequest(BaseModel):
    """Request body for POST /quiz/generate."""

    document_ids: List[str] = Field(
        ...,
        min_length=1,
        description="IDs of the documents to scope the quiz to (at least one required).",
    )
    mode: Literal["local", "global", "hybrid", "mix", "naive"] = Field(
        "mix",
        description=(
            "Retrieval mode.  'mix' and 'naive' use thesis-rigorous difficulty "
            "mechanics (custom BFS / controlled chunk-k). Other modes use "
            "top_k scaling as a coarse proxy."
        ),
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        "medium",
        description="Difficulty level — controls retrieval depth AND reasoning type.",
    )
    num_questions: Literal[10, 25, 50] = Field(
        10, description="Number of questions to generate."
    )
    run_verification: bool = Field(
        True,
        description="Whether to verify each question with Claude Sonnet after generation.",
    )

    # Optional overrides (None = use mode/difficulty defaults)
    top_k: Optional[int] = Field(None, description="Override KG top-k.")
    chunk_top_k: Optional[int] = Field(None, description="Override chunk top-k.")
    max_entity_tokens: Optional[int] = None
    max_relation_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None
    user_prompt: Optional[str] = None


# ---------------------------------------------------------------------------
# Sub-models for per-question metadata
# ---------------------------------------------------------------------------


class RetrievalMetadata(BaseModel):
    """Records exactly what was retrieved for a single question seed."""

    entities: List[str] = Field(default_factory=list)
    relations: List[dict] = Field(default_factory=list)  # {source, target, type}
    bfs_path: List[str] = Field(
        default_factory=list,
        description="Ordered entity chain traversed by BFS (mix arm only).",
    )
    chunk_ids: List[str] = Field(default_factory=list)
    hop_depth: Optional[int] = Field(
        None, description="BFS depth used (mix arm). None for naive/fallback."
    )
    source_documents: List[str] = Field(
        default_factory=list,
        description="Document IDs that contributed chunks/entities.",
    )
    seed_query: str = Field("", description="The seed query used to bootstrap retrieval.")
    seed_strategy: str = Field(
        "entity",
        description="'entity' (degree-weighted) or 'chunk' (first-sentence) sampling.",
    )


class GenerationMetadata(BaseModel):
    """Records the generation call details."""

    model: str = Field("gpt-4o")
    prompt_template_id: str = Field("", description="e.g. 'easy_v1', 'hard_v1'")
    question: str = ""
    reference_answer: str = ""


class VerificationMetadata(BaseModel):
    """Populated when run_verification=True.  Returned by Claude Sonnet."""

    model: str = "claude-sonnet-4-6"
    actual_retrieval_complexity: int = 0
    actual_reasoning_type: str = ""
    answerable_from_context: bool = False
    claimed_complexity_matches: bool = False
    claimed_reasoning_matches: bool = False
    notes: str = ""


class HumanRatingMetadata(BaseModel):
    """Optional; populated offline via exported JSON + spreadsheet workflow."""

    rater_id: str = ""
    rating: int = Field(0, ge=1, le=5)
    notes: str = ""


# ---------------------------------------------------------------------------
# Per-question record
# ---------------------------------------------------------------------------


class QuizQuestionMetadata(BaseModel):
    """Full metadata record for a single generated question."""

    question_id: str
    arm: Literal["graph", "naive", "other"] = Field(
        ...,
        description="Which thesis arm generated this question.",
    )
    difficulty: Literal["easy", "medium", "hard"]

    claimed_retrieval_complexity: int = Field(
        ...,
        description="Hop depth (mix) or chunk count (naive) used during retrieval.",
    )
    claimed_reasoning_type: str = Field(
        ...,
        description="Reasoning type enforced at prompt time (factual/comparative/causal/…).",
    )

    retrieval: RetrievalMetadata
    generation: GenerationMetadata
    verification: Optional[VerificationMetadata] = None
    human_rating: Optional[HumanRatingMetadata] = None


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class QuizGenerateResponse(BaseModel):
    """Response body for POST /quiz/generate and GET /quiz/{quiz_id}."""

    quiz_id: str
    created_at: datetime
    request: QuizGenerateRequest
    questions: List[QuizQuestionMetadata]
    metadata_path: str = Field(
        "",
        description="Server-side path to the persisted JSON file (for archival).",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (e.g. seed sampling fell back to replacement).",
    )


# ---------------------------------------------------------------------------
# List endpoint summary
# ---------------------------------------------------------------------------


class QuizSummary(BaseModel):
    """Lightweight summary returned by GET /quiz/list."""

    quiz_id: str
    created_at: datetime
    mode: str
    difficulty: str
    num_questions: int
    question_count: int
    verifier_pass_rate: Optional[float] = None
    metadata_path: str = ""

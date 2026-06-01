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
    run_correctness_check: bool = Field(
        False,
        description=(
            "Whether to run the independent fact-checker — an extra Claude call per "
            "question that judges factual correctness regardless of context. Off for "
            "cheap pilots; on for the final matrix."
        ),
    )

    # Optional overrides (None = use mode/difficulty defaults)
    top_k: Optional[int] = Field(None, description="Override KG top-k.")
    chunk_top_k: Optional[int] = Field(None, description="Override chunk top-k.")
    max_entity_tokens: Optional[int] = None
    max_relation_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None
    user_prompt: Optional[str] = None


class QuizAblationRequest(BaseModel):
    """Request body for POST /quiz/ablation (Phase-4 ablation harness).

    Runs the deterministic seed-scoring ablation/sensitivity study for one arm
    against the live index — no LLM calls, no quiz generated (quality-plan.md
    §8.2). Used by the experiment runner to produce thesis-appendix evidence.
    """

    document_ids: List[str] = Field(..., min_length=1)
    mode: Literal["mix", "naive"] = "mix"
    num_questions: Literal[10, 25, 50] = 25


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
        description=(
            "Seed sampling strategy actually used, e.g. 'entity'/'chunk' (random "
            "baseline) or 'entity-pedagogical'/'chunk-pedagogical' (RRF scorer)."
        ),
    )
    # Pedagogical-scorer transparency (quality-plan.md §5/§9). None for the
    # random baseline; populated when QUIZ_SEED_STRATEGY=pedagogical.
    seed_score: Optional[float] = Field(
        None, description="RRF fusion score of the seed that produced this question."
    )
    seed_score_components: dict = Field(
        default_factory=dict,
        description="Per-signal ranks behind the RRF score, e.g. {'deg': 3, 'xdoc': 1, 'freq': 5}.",
    )


class GenerationMetadata(BaseModel):
    """Records the generation call details."""

    model: str = Field("gpt-4o")
    prompt_template_id: str = Field("", description="e.g. 'easy_v2', 'hard_v2'")
    question: str = ""
    reference_answer: str = ""
    # Diagnostic — no behavioral impact, used for analytics & thesis reporting.
    # See lightrag/quiz/diagnostics.py for the heuristic definitions.
    figure_dependency_estimate: float = Field(
        0.0,
        description=(
            "0.0 = question is fully concept-based; "
            "1.0 = question reads like a label/cell lookup from a figure."
        ),
    )
    source_lexical_overlap: float = Field(
        0.0,
        description=(
            "Stopword-filtered Jaccard overlap between question tokens and "
            "the top retrieved chunk tokens. Higher = more extractive surface form."
        ),
    )
    retrieved_chunk_count: int = Field(
        0,
        description=(
            "Number of in-scope chunks retrieved for this question. "
            "0 means the question was generated from an empty retrieval — "
            "should never occur after R6-2 (anti-hallucination guard), but "
            "the field gives downstream analytics a column to detect any leak."
        ),
    )
    clarity_heuristic: float = Field(
        0.0,
        description=(
            "0.0..1.0 deterministic clarity / single-focus estimate. NOTE: unlike "
            "figure_dependency_estimate and source_lexical_overlap (higher = worse), "
            "here HIGHER = clearer / more focused; lower = over-stuffed, multi-clause."
        ),
    )


class VerificationMetadata(BaseModel):
    """Populated when run_verification=True.  Returned by Claude Sonnet."""

    model: str = "claude-sonnet-4-6"
    actual_retrieval_complexity: int = 0
    actual_reasoning_type: str = ""
    answerable_from_context: bool = False
    claimed_complexity_matches: bool = False
    claimed_reasoning_matches: bool = False
    notes: str = ""


class PedagogyMetadata(BaseModel):
    """Pedagogical-quality judgement of a question (separate judge call).

    Computed by lightrag/quiz/pedagogy.py with its own LLM call (Claude Sonnet),
    judged from the question + reference answer only — the locked verifier prompt
    is deliberately left untouched. 0 / "" mean unscored (mock or parse failure).
    """

    model: str = "claude-sonnet-4-6"
    pedagogical_value: int = Field(
        0, description="1 = trivia … 5 = foundational concept. 0 = unscored."
    )
    bloom_level: str = Field(
        "",
        description="Bloom's level: remember|understand|apply|analyze|evaluate|create. '' = unscored.",
    )
    answer_completeness: int = Field(
        0, description="1 = does not address … 5 = fully addresses the question. 0 = unscored."
    )
    notes: str = ""


class CorrectnessMetadata(BaseModel):
    """Independent factual-correctness check (optional, separate judge call).

    Run only when ``QuizGenerateRequest.run_correctness_check`` is true. A
    fact-checker prompt judges whether the reference answer is factually correct
    *independent* of whether it is grounded in the retrieved context. 0 = unscored.
    """

    model: str = "claude-sonnet-4-6"
    answer_correctness: int = Field(
        0, description="1 = definitely wrong … 5 = definitely correct. 0 = unscored."
    )
    notes: str = ""


class HumanRatingMetadata(BaseModel):
    """Optional; populated offline via exported JSON + spreadsheet workflow."""

    rater_id: str = ""
    rating: int = Field(0, ge=1, le=5)
    notes: str = ""


class FileContribution(BaseModel):
    """Per-file seed contribution for a quiz (quality-plan.md §6.2).

    Surfaces *which* selected documents actually drove the quiz and *why* a file
    contributed nothing — so "this file added nothing" is visible rather than
    silent. Contribution is earned via the Cap+Merit+Floor allocator, never
    assigned up front.
    """

    doc_id: str
    seed_count: int = 0
    reason: Literal["contributed", "below_threshold", "outranked", "capped"] = Field(
        "outranked",
        description=(
            "contributed = ≥1 seed; below_threshold = all candidates failed the "
            "meaningfulness floor; outranked = lost the global ranking; "
            "capped = hit the per-file cap (see seed_count)."
        ),
    )


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
    pedagogy: Optional[PedagogyMetadata] = None
    correctness: Optional[CorrectnessMetadata] = None
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
    file_contributions: List[FileContribution] = Field(
        default_factory=list,
        description=(
            "Per-file seed contribution (quality-plan.md §6.2). Empty for the "
            "random-baseline seed strategy."
        ),
    )
    diversity: dict = Field(
        default_factory=dict,
        description=(
            "Quiz-level diversity metrics (quality-plan.md §8.1), e.g. "
            "{'mean_pairwise_similarity': .., 'max_pairwise_similarity': ..}. "
            "Populated in Phase 4."
        ),
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

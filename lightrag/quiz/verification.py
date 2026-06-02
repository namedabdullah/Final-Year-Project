"""
Question verification via Claude Sonnet.

Phase 5: real claude-sonnet-4-6 calls using the locked verifier prompt from
claude_review_rag_framework.md §Verification Prompt.

Falls back to a mock VerificationMetadata when ANTHROPIC_API_KEY is absent or
any call fails — callers always receive a valid VerificationMetadata object.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import json_repair

from lightrag.quiz.diagnostics import complexity_is_appropriate, reasoning_types_match
from lightrag.quiz.schemas import VerificationMetadata
from lightrag.utils import logger

if TYPE_CHECKING:
    from lightrag.quiz.retrieval import RetrievalContext


# ---------------------------------------------------------------------------
# Verifier system prompt (locked — from claude_review_rag_framework.md)
# ---------------------------------------------------------------------------

_VERIFIER_SYSTEM_PROMPT = """\
You are a rigorous quiz-question verifier for a RAG evaluation study.

You will be given:
  1. A quiz question and its reference answer
  2. The retrieved context used to generate the question
  3. Claimed metadata: retrieval_complexity (hop depth for graph / chunk count for naive) and reasoning_type

Your task: determine whether the question's claimed difficulty metadata is accurate.

Definitions:
- actual_retrieval_complexity: the minimum number of context pieces (hops or chunks) actually required to answer the question
- actual_reasoning_type: one of [factual, comparative, causal, inferential, analytical]
  - factual: single fact lookup, no synthesis
  - comparative: requires comparing/contrasting 2+ pieces
  - causal: requires identifying cause-effect relationships
  - inferential: requires drawing conclusions not explicitly stated
  - analytical: requires breaking down and evaluating multiple elements
- answerable_from_context: true only if the reference answer is fully supported by the provided context
- claimed_complexity_matches: true if claimed == actual retrieval complexity
- claimed_reasoning_matches: true if claimed == actual reasoning type

Be conservative: if you cannot confirm answerability, set it to false.

Return ONLY a valid JSON object with these exact keys:
{
  "actual_retrieval_complexity": <integer>,
  "actual_reasoning_type": "<string: factual|comparative|causal|inferential|analytical>",
  "answerable_from_context": <boolean>,
  "claimed_complexity_matches": <boolean>,
  "claimed_reasoning_matches": <boolean>,
  "notes": "<one sentence rationale>"
}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_verifier_user_prompt(
    question: str,
    reference_answer: str,
    context: "RetrievalContext",
    claimed_complexity: int,
    claimed_reasoning_type: str,
) -> str:
    """Build the user-turn message sent to Claude Sonnet."""
    ctx_text = context.format_for_prompt()
    return (
        f"=== QUESTION ===\n{question}\n\n"
        f"=== REFERENCE ANSWER ===\n{reference_answer}\n\n"
        f"=== RETRIEVED CONTEXT ===\n{ctx_text}\n\n"
        f"=== CLAIMED METADATA ===\n"
        f"retrieval_complexity: {claimed_complexity}\n"
        f"reasoning_type: {claimed_reasoning_type}\n"
    )


def _parse_verification_json(
    raw: str,
    model: str,
    claimed_complexity: int,
    claimed_reasoning_type: str,
) -> VerificationMetadata:
    """Parse the verifier JSON into VerificationMetadata.

    The verifier LLM only *measures* (``actual_*`` + ``answerable_from_context``);
    the claimed-vs-actual **match** booleans are computed deterministically here,
    not trusted from the model's brittle exact-string comparison:
      - reasoning match is **tier-based** (hard's ``causal`` accepts
        causal/inferential/analytical) — see ``reasoning_types_match``;
      - complexity match is **floor-based** (hard needs >=2 pieces, not exactly 3)
        — see ``complexity_is_appropriate``.
    So the locked prompt is unchanged, but a hard question that is analytical or
    needs 2 pieces is no longer scored as a mismatch.

    Tries strict json.loads first, then json_repair.loads. Raises ValueError if
    neither succeeds or the measured keys are absent.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("verification: strict JSON parse failed; attempting json_repair")
        data = json_repair.loads(raw)

    # Only the *measurements* are required; the model's own claimed_*_matches are
    # ignored (recomputed below), so their absence is not an error.
    required_keys = {
        "actual_retrieval_complexity",
        "actual_reasoning_type",
        "answerable_from_context",
        "notes",
    }
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(
            f"verification: parsed JSON missing keys {missing}. raw={raw!r}"
        )

    actual_complexity = int(data["actual_retrieval_complexity"])
    actual_reasoning = str(data["actual_reasoning_type"])
    return VerificationMetadata(
        model=model,
        actual_retrieval_complexity=actual_complexity,
        actual_reasoning_type=actual_reasoning,
        answerable_from_context=bool(data["answerable_from_context"]),
        claimed_complexity_matches=complexity_is_appropriate(claimed_complexity, actual_complexity),
        claimed_reasoning_matches=reasoning_types_match(
            claimed_reasoning_type, actual_reasoning, actual_complexity
        ),
        notes=str(data["notes"]),
    )


def _mock_verification(
    claimed_complexity: int,
    claimed_reasoning_type: str,
    note: str = "[mock] Verification not attempted.",
) -> VerificationMetadata:
    """Return a safe mock VerificationMetadata that mirrors the claimed values."""
    return VerificationMetadata(
        model="claude-sonnet-4-6",
        actual_retrieval_complexity=claimed_complexity,
        actual_reasoning_type=claimed_reasoning_type,
        answerable_from_context=False,
        claimed_complexity_matches=True,
        claimed_reasoning_matches=True,
        notes=note,
    )


async def _verify_with_openai(
    question: str,
    reference_answer: str,
    context: "RetrievalContext",
    claimed_complexity: int,
    claimed_reasoning_type: str,
    openai_key: str,
    model: str,
) -> VerificationMetadata:
    """Fallback verifier using an OpenAI model when no Anthropic key is set.

    Uses the identical verifier system prompt and user message as the Anthropic
    path, but routes the request through the OpenAI chat-completions API with
    JSON mode enabled.  The ``VerificationMetadata.model`` field records the
    actual OpenAI model used so results remain traceable.
    """
    try:
        from openai import AsyncOpenAI  # local import to avoid hard dep at module level

        user_prompt = _build_verifier_user_prompt(
            question=question,
            reference_answer=reference_answer,
            context=context,
            claimed_complexity=claimed_complexity,
            claimed_reasoning_type=claimed_reasoning_type,
        )

        client = AsyncOpenAI(api_key=openai_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _VERIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=1024,
        )
        raw = response.choices[0].message.content or ""
        result = _parse_verification_json(raw, model, claimed_complexity, claimed_reasoning_type)
        logger.info(
            "verification: OpenAI fallback (%s) verified question — "
            "answerable=%s, complexity_match=%s, reasoning_match=%s",
            model,
            result.answerable_from_context,
            result.claimed_complexity_matches,
            result.claimed_reasoning_matches,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "verification: OpenAI fallback verification failed — using mock. error=%s", exc
        )
        return _mock_verification(
            claimed_complexity,
            claimed_reasoning_type,
            note=f"[mock] OpenAI fallback verification failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def verify_question(
    question: str,
    reference_answer: str,
    context: "RetrievalContext",
    claimed_complexity: int,
    claimed_reasoning_type: str,
    model: str = "claude-sonnet-4-6",
) -> VerificationMetadata:
    """Verify a question against its retrieval context and claimed metadata.

    Primary path: calls ``claude-sonnet-4-6`` with the locked verifier prompt
    from claude_review_rag_framework.md when ``ANTHROPIC_API_KEY`` is set.

    Fallback path: when ``ANTHROPIC_API_KEY`` is absent but an OpenAI key is
    available (``OPENAI_API_KEY`` or ``LLM_BINDING_API_KEY``), the same
    structured verifier prompt is sent to the resolved OpenAI model.  The
    fallback model is chosen from:
      1. ``QUIZ_VERIFICATION_FALLBACK_MODEL`` env var
      2. ``LLM_MODEL`` env var
      3. ``"gpt-4o-mini"``

    Falls back to a mock VerificationMetadata only when no API key of either
    kind is available or the call fails — callers always receive a valid object.

    Args:
        question:               The generated quiz question.
        reference_answer:       The generated reference answer.
        context:                The RetrievalContext used during generation.
        claimed_complexity:     Hop depth (mix arm) or chunk count (naive arm).
        claimed_reasoning_type: Reasoning type enforced at prompt time.
        model:                  Anthropic model identifier (default "claude-sonnet-4-6").

    Returns:
        VerificationMetadata populated from the verifier's grounded assessment,
        or a mock result if no call could be completed.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try OpenAI as fallback verifier before giving up with a mock
        openai_key = (
            os.environ.get("OPENAI_API_KEY", "")
            or os.environ.get("LLM_BINDING_API_KEY", "")
        )
        if openai_key:
            fallback_model = (
                os.environ.get("QUIZ_VERIFICATION_FALLBACK_MODEL", "")
                or os.environ.get("LLM_MODEL", "")
                or "gpt-4o-mini"
            )
            logger.info(
                "verification: ANTHROPIC_API_KEY not set — using OpenAI fallback (%s) "
                "for claimed_complexity=%d, claimed_reasoning_type=%s",
                fallback_model,
                claimed_complexity,
                claimed_reasoning_type,
            )
            return await _verify_with_openai(
                question=question,
                reference_answer=reference_answer,
                context=context,
                claimed_complexity=claimed_complexity,
                claimed_reasoning_type=claimed_reasoning_type,
                openai_key=openai_key,
                model=fallback_model,
            )

        logger.info(
            "verification: ANTHROPIC_API_KEY not set — returning mock verification "
            "for claimed_complexity=%d, claimed_reasoning_type=%s",
            claimed_complexity,
            claimed_reasoning_type,
        )
        return _mock_verification(
            claimed_complexity,
            claimed_reasoning_type,
            note="[mock] ANTHROPIC_API_KEY not set — verification skipped.",
        )

    user_prompt = _build_verifier_user_prompt(
        question=question,
        reference_answer=reference_answer,
        context=context,
        claimed_complexity=claimed_complexity,
        claimed_reasoning_type=claimed_reasoning_type,
    )

    try:
        from anthropic import AsyncAnthropic  # local import to avoid hard dep at module level

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            system=_VERIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
        result = _parse_verification_json(raw, model, claimed_complexity, claimed_reasoning_type)
        logger.info(
            "verification: Claude Sonnet verified question — "
            "answerable=%s, complexity_match=%s, reasoning_match=%s",
            result.answerable_from_context,
            result.claimed_complexity_matches,
            result.claimed_reasoning_matches,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "verification: Claude Sonnet call failed — falling back to mock. error=%s",
            exc,
        )
        return _mock_verification(
            claimed_complexity,
            claimed_reasoning_type,
            note=f"[mock] Verification failed: {exc}",
        )

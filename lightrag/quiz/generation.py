"""
Question generation via GPT-4o.

Phase 4: real GPT-4o calls using JSON mode with locked prompt templates from
claude_review_rag_framework.md §Easy/Medium/Hard Prompts.

Falls back to mock questions when OPENAI_API_KEY is absent or any call fails —
callers always receive a valid (question, reference_answer) tuple.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import TYPE_CHECKING

import json_repair

from lightrag.utils import logger

if TYPE_CHECKING:
    from lightrag.quiz.retrieval import RetrievalContext


# ---------------------------------------------------------------------------
# Prompt templates (locked — do not change without framework doc revision)
# ---------------------------------------------------------------------------

REASONING_TYPE = {
    "easy": "factual",
    "medium": "comparative",
    "hard": "causal",  # also covers inferential / analytical
}

PROMPT_TEMPLATE_IDS = {
    "easy": "easy_v1",
    "medium": "medium_v1",
    "hard": "hard_v1",
}

# Full user-turn prompts from claude_review_rag_framework.md
_PROMPT_TEMPLATES: dict[str, str] = {
    "easy": (
        "You are a quiz question generator for an academic study. Given the context below, "
        "generate exactly ONE question that can be answered directly from a single explicit fact "
        "in the context. The answer must be directly stated — no reasoning or synthesis required.\n\n"
        "Requirements:\n"
        "- The question must be answerable using ONLY the provided context\n"
        "- The answer should be a single fact, name, number, or short phrase\n"
        "- Do NOT ask for comparisons, causes, or multi-step reasoning\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Context:\n{context}"
    ),
    "medium": (
        "You are a quiz question generator for an academic study. Given the context below, "
        "generate exactly ONE question that requires comparing or relating at least two distinct "
        "pieces of information from the context. The answer cannot be found from any single "
        "sentence alone.\n\n"
        "Requirements:\n"
        "- The question must be answerable ONLY using the provided context\n"
        "- The answer must synthesise information from at least 2 different context pieces\n"
        "- Ask for a comparison, relationship, contrast, or synthesis\n"
        "- Do NOT ask for causal chains, predictions, or multi-step inference\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Context:\n{context}"
    ),
    "hard": (
        "You are a quiz question generator for an academic study. Given the context below, "
        "generate exactly ONE question requiring multi-step causal, inferential, or analytical "
        "reasoning across at least three pieces of information from the context. The answer must "
        "NOT be directly stated anywhere in the context — the student must reason to it.\n\n"
        "Requirements:\n"
        "- The question must be answerable ONLY by reasoning over the provided context\n"
        "- The answer requires synthesising at least 3 context pieces through "
        "causal/inferential/analytical reasoning\n"
        "- The answer must NOT be explicitly stated in any single sentence\n"
        "- Do NOT ask factual recall or simple comparison questions\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Context:\n{context}"
    ),
}


# ---------------------------------------------------------------------------
# Mock responses (fallback when API key is absent or a call fails)
# ---------------------------------------------------------------------------

_MOCK_QUESTIONS: dict[str, tuple[str, str]] = {
    "easy": (
        "What is the primary function described in the retrieved context?",
        "The primary function described is the direct lookup of factual information from the knowledge base.",
    ),
    "medium": (
        "How do the two main concepts in the retrieved context relate to each other?",
        "The two concepts are complementary — one provides the structural foundation while the other enables dynamic querying across that structure.",
    ),
    "hard": (
        "Why might the system's performance characteristics change significantly under high-load conditions based on the retrieved context?",
        "Under high load, the retrieval latency increases due to graph traversal depth compounding with vector search overhead, which together create non-linear performance degradation when both arms of the retrieval pipeline are saturated simultaneously.",
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_generation_json(raw: str) -> tuple[str, str]:
    """Parse GPT-4o JSON response to (question, reference_answer).

    Tries strict json.loads first, then json_repair.loads as fallback.
    Raises ValueError if neither succeeds or required keys are absent.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("generation: strict JSON parse failed; attempting json_repair")
        data = json_repair.loads(raw)

    question = data.get("question", "").strip()
    reference_answer = data.get("reference_answer", "").strip()

    if not question or not reference_answer:
        raise ValueError(
            f"generation: parsed JSON missing 'question' or 'reference_answer'. raw={raw!r}"
        )

    return question, reference_answer


def _mock_for(difficulty: str) -> tuple[str, str]:
    return _MOCK_QUESTIONS.get(difficulty, _MOCK_QUESTIONS["medium"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

_RETRY_MAX_ATTEMPTS = int(os.environ.get("QUIZ_GENERATION_RETRY_ATTEMPTS", "5"))
_RETRY_BASE_DELAY   = float(os.environ.get("QUIZ_GENERATION_RETRY_BASE_DELAY", "2.0"))
_RETRY_MAX_DELAY    = float(os.environ.get("QUIZ_GENERATION_RETRY_MAX_DELAY", "60.0"))


def _parse_retry_after(exc: Exception) -> float | None:
    """Extract the suggested wait time (seconds) from an OpenAI 429 response.

    OpenAI returns one of:
      • The ``Retry-After`` header (integer seconds)
      • A message like "Please try again in 1.349s"
    We parse the message string because the async client surfaces it as the
    exception message; the raw headers are not easily accessible here.
    """
    msg = str(exc)
    # "Please try again in 1.349s" / "in 500ms"
    match = re.search(r"try again in\s+([\d.]+)(ms|s)", msg, re.IGNORECASE)
    if match:
        value, unit = float(match.group(1)), match.group(2).lower()
        return value / 1000.0 if unit == "ms" else value
    return None


async def _call_openai_with_retry(
    client: "AsyncOpenAI",
    model: str,
    messages: list[dict],
    difficulty: str,
) -> tuple[str, str]:
    """Call the OpenAI chat-completions endpoint with exponential-backoff retry.

    Retries up to QUIZ_GENERATION_RETRY_ATTEMPTS times on rate-limit (429)
    errors.  For each 429 it waits the time OpenAI suggests (parsed from the
    error message) plus a small jitter, doubling the floor on each attempt.
    All other exceptions are re-raised immediately after a single warning.
    """
    import openai  # already imported by caller; safe to import again

    delay = _RETRY_BASE_DELAY
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=1024,
            )
            raw = response.choices[0].message.content or ""
            return _parse_generation_json(raw)

        except openai.RateLimitError as exc:
            suggested = _parse_retry_after(exc)

            # Strategy:
            #  • If OpenAI gives a Retry-After hint, trust it — it knows exactly
            #    when enough tokens will have expired from the rolling window.
            #    Add 0.5 s jitter so a burst of workers don't all fire at once.
            #  • If no hint, fall back to exponential backoff starting at
            #    _RETRY_BASE_DELAY and doubling each attempt.
            #  • Always cap at _RETRY_MAX_DELAY.
            if suggested is not None:
                wait = min(suggested + 0.5, _RETRY_MAX_DELAY)
            else:
                wait = min(delay, _RETRY_MAX_DELAY)
                delay = min(delay * 2, _RETRY_MAX_DELAY)   # grow for next no-hint attempt

            if attempt == _RETRY_MAX_ATTEMPTS:
                logger.warning(
                    "generation: rate-limited on attempt %d/%d — giving up. error=%s",
                    attempt, _RETRY_MAX_ATTEMPTS, exc,
                )
                raise

            logger.warning(
                "generation: rate-limited (attempt %d/%d) — waiting %.2fs before retry. error=%s",
                attempt, _RETRY_MAX_ATTEMPTS, wait, exc,
            )
            await asyncio.sleep(wait)

        except Exception as exc:
            # Non-rate-limit errors: log and bubble up immediately
            logger.warning(
                "generation: OpenAI call failed on attempt %d — %s", attempt, exc
            )
            raise

    # Should never reach here
    raise RuntimeError("generation: retry loop exhausted without result or exception")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_question(
    context: "RetrievalContext",
    difficulty: str,
    model: str | None = None,
) -> tuple[str, str]:
    """Return (question, reference_answer) for the given retrieval context and difficulty.

    Calls the OpenAI chat-completions API using JSON mode with the locked prompt
    templates from claude_review_rag_framework.md.  Retries up to
    QUIZ_GENERATION_RETRY_ATTEMPTS times on OpenAI 429 rate-limit errors,
    honouring the server-suggested wait time.  Falls back to a mock result if no
    API key is resolvable or if all retry attempts fail — callers always receive a
    usable tuple.

    API key resolution order (first non-empty wins):
      1. ``OPENAI_API_KEY``          — standard OpenAI SDK env var
      2. ``LLM_BINDING_API_KEY``     — LightRAG's unified LLM key

    Model resolution order (first non-empty wins):
      1. ``model`` argument (when not None)
      2. ``QUIZ_GENERATION_MODEL``   — explicit quiz override
      3. ``LLM_MODEL``               — LightRAG's configured model
      4. ``"gpt-4o-mini"``           — safe default for Tier-1 API plans

    Env vars (all optional):
      QUIZ_GENERATION_MODEL           — OpenAI model to use (see above)
      QUIZ_GENERATION_RETRY_ATTEMPTS  — max retries on 429 (default 5)
      QUIZ_GENERATION_RETRY_BASE_DELAY — initial backoff seconds (default 2.0)
      QUIZ_GENERATION_RETRY_MAX_DELAY  — backoff ceiling seconds (default 60.0)

    Args:
        context:    The retrieval context produced by the retrieval arm.
        difficulty: One of "easy", "medium", "hard".
        model:      OpenAI model identifier; ``None`` resolves from env (see above).

    Returns:
        (question, reference_answer) — both non-empty strings.
    """
    # Resolve API key: OPENAI_API_KEY first, then LightRAG's unified key
    api_key = (
        os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("LLM_BINDING_API_KEY", "")
    )
    if not api_key:
        logger.info(
            "generation: no OpenAI API key found (OPENAI_API_KEY / LLM_BINDING_API_KEY) "
            "— returning mock question for difficulty=%s",
            difficulty,
        )
        return _mock_for(difficulty)

    # Resolve model
    if model is None:
        model = (
            os.environ.get("QUIZ_GENERATION_MODEL", "")
            or os.environ.get("LLM_MODEL", "")
            or "gpt-4o-mini"
        )

    template = _PROMPT_TEMPLATES.get(difficulty, _PROMPT_TEMPLATES["medium"])
    formatted_context = context.format_for_prompt()
    user_message = template.format(context=formatted_context)
    messages = [{"role": "user", "content": user_message}]

    try:
        from openai import AsyncOpenAI  # local import to avoid hard dep at module level

        client = AsyncOpenAI(api_key=api_key)
        question, reference_answer = await _call_openai_with_retry(
            client, model, messages, difficulty
        )
        logger.info(
            "generation: produced question for difficulty=%s (len=%d chars)",
            difficulty,
            len(question),
        )
        return question, reference_answer

    except Exception as exc:  # noqa: BLE001 — all retries exhausted or non-429 error
        logger.warning(
            "generation: all attempts failed for difficulty=%s — falling back to mock. error=%s",
            difficulty,
            exc,
        )
        return _mock_for(difficulty)

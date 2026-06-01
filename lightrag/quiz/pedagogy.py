"""
Pedagogy + correctness judges (separate from the locked verifier).

These are *second-opinion* LLM judges that score a question's pedagogical
quality and (optionally) its factual correctness. They run as their own
Claude calls so the locked verifier prompt in ``verification.py`` stays
untouched — its answerability / complexity / reasoning judgements are the
study's primary instrument and must not be perturbed.

Both judges:
  - need only the question + reference answer (no retrieval context → cheap),
  - mirror ``verification.py``'s degradation chain: Claude primary →
    OpenAI fallback (when ANTHROPIC_API_KEY is absent) → conservative mock,
  - never raise — callers always receive a valid metadata object.

``judge_pedagogy`` is run under the same gate as verification; ``judge_correctness``
is opt-in via ``QuizGenerateRequest.run_correctness_check`` (an extra call/question).
"""

from __future__ import annotations

import json
import os

import json_repair

from lightrag.quiz.schemas import CorrectnessMetadata, PedagogyMetadata
from lightrag.utils import logger

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PEDAGOGY_SYSTEM_PROMPT = """\
You are an expert instructional designer assessing the pedagogical quality of a
single quiz question and its reference answer for a university Operating Systems course.

You will be given a QUESTION and its REFERENCE ANSWER. Judge three things:

1. pedagogical_value (1-5): how worth testing the underlying concept is.
   1 = trivia / incidental detail not worth testing
   2 = low-level recall of a minor fact
   3 = a standard course concept
   4 = an important concept whose mastery unlocks other topics
   5 = a foundational, central concept of the course

2. bloom_level: the single Bloom's taxonomy level the question primarily targets.
   One of: remember, understand, apply, analyze, evaluate, create.

3. answer_completeness (1-5): how fully the reference answer addresses the question.
   1 = does not address the question
   3 = addresses the main point but leaves gaps
   5 = fully and directly addresses the question

Judge the question and answer on their own merits — you are NOT checking whether
they are grounded in any source text.

Return ONLY a valid JSON object with these exact keys:
{
  "pedagogical_value": <integer 1-5>,
  "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",
  "answer_completeness": <integer 1-5>,
  "notes": "<one sentence rationale>"
}"""

_CORRECTNESS_SYSTEM_PROMPT = """\
You are a domain-expert fact-checker for a university Operating Systems course.

You will be given a QUESTION and its REFERENCE ANSWER. Judge whether the reference
answer is FACTUALLY CORRECT, using your own authoritative domain knowledge.

Important: this is independent of any source text. An answer can be well-written or
plausible yet still be factually wrong — your job is to catch that. Judge only
factual accuracy, not completeness or writing style.

  5 = definitely correct; matches authoritative knowledge
  4 = likely correct; no identifiable errors
  3 = partially correct; a mix of correct and questionable claims
  2 = likely incorrect; conflicts with known facts
  1 = definitely incorrect; factually wrong

Return ONLY a valid JSON object with these exact keys:
{
  "answer_correctness": <integer 1-5>,
  "notes": "<one sentence rationale, citing the error if any>"
}"""


# ---------------------------------------------------------------------------
# Parsing helpers (tolerant — defaults on omission, never hard-require keys)
# ---------------------------------------------------------------------------

_BLOOM_LEVELS = ("remember", "understand", "apply", "analyze", "evaluate", "create")
_BLOOM_ALIASES = {
    "remembering": "remember",
    "understanding": "understand",
    "comprehend": "understand",
    "comprehension": "understand",
    "applying": "apply",
    "application": "apply",
    "analyzing": "analyze",
    "analysing": "analyze",
    "analyse": "analyze",
    "analysis": "analyze",
    "evaluating": "evaluate",
    "evaluation": "evaluate",
    "creating": "create",
    "synthesis": "create",
    "synthesize": "create",
}


def _normalize_bloom(value) -> str:
    """Map a raw bloom label to one of the 6 canonical lowercase levels, or ''."""
    s = str(value or "").strip().lower()
    if not s:
        return ""
    if s in _BLOOM_LEVELS:
        return s
    if s in _BLOOM_ALIASES:
        return _BLOOM_ALIASES[s]
    # Last resort: a canonical level as a prefix, e.g. "analyze (level 4)".
    for level in _BLOOM_LEVELS:
        if s.startswith(level):
            return level
    return ""


def _clamp_score(value) -> int:
    """Coerce an LLM score to an int in [1, 5]; return 0 (= unscored) on failure."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    return max(1, min(5, n))


def _loads_tolerant(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("pedagogy: strict JSON parse failed; attempting json_repair")
        data = json_repair.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"pedagogy: parsed JSON is not an object. raw={raw!r}")
    return data


def _parse_pedagogy_json(raw: str, model: str) -> PedagogyMetadata:
    """Parse a pedagogy-judge JSON reply. Missing keys default (never discard the rest)."""
    data = _loads_tolerant(raw)
    return PedagogyMetadata(
        model=model,
        pedagogical_value=_clamp_score(data.get("pedagogical_value")),
        bloom_level=_normalize_bloom(data.get("bloom_level")),
        answer_completeness=_clamp_score(data.get("answer_completeness")),
        notes=str(data.get("notes", "") or ""),
    )


def _parse_correctness_json(raw: str, model: str) -> CorrectnessMetadata:
    """Parse a correctness-judge JSON reply. Missing key defaults to 0 (unscored)."""
    data = _loads_tolerant(raw)
    return CorrectnessMetadata(
        model=model,
        answer_correctness=_clamp_score(data.get("answer_correctness")),
        notes=str(data.get("notes", "") or ""),
    )


def _mock_pedagogy(
    note: str = "[mock] pedagogy judge not run (no API key or call failed).",
) -> PedagogyMetadata:
    return PedagogyMetadata(
        pedagogical_value=0, bloom_level="", answer_completeness=0, notes=note
    )


def _mock_correctness(
    note: str = "[mock] correctness check not run (no API key or call failed).",
) -> CorrectnessMetadata:
    return CorrectnessMetadata(answer_correctness=0, notes=note)


def _build_qa_user_prompt(question: str, reference_answer: str) -> str:
    return (
        f"=== QUESTION ===\n{question}\n\n"
        f"=== REFERENCE ANSWER ===\n{reference_answer}\n"
    )


# ---------------------------------------------------------------------------
# Shared LLM call (Claude primary → OpenAI fallback). Returns None on no-key/error.
# ---------------------------------------------------------------------------


async def _call_judge_llm(system_prompt: str, user_prompt: str, anthropic_model: str):
    """Return ``(raw_text, model_used)`` from Claude, else the OpenAI fallback, else None.

    Mirrors ``verification.py``: when ANTHROPIC_API_KEY is set we use Claude and, on
    failure, return None (→ caller mocks); only when the Anthropic key is *absent*
    do we route to an OpenAI model. Returns None when no key is available.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            from anthropic import AsyncAnthropic  # local import — no hard dep at module load

            client = AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=anthropic_model,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text, anthropic_model
        except Exception as exc:  # noqa: BLE001
            logger.warning("pedagogy: Claude judge call failed — %s", exc)
            return None

    openai_key = (
        os.environ.get("OPENAI_API_KEY", "") or os.environ.get("LLM_BINDING_API_KEY", "")
    )
    if openai_key:
        fallback_model = (
            os.environ.get("QUIZ_VERIFICATION_FALLBACK_MODEL", "")
            or os.environ.get("LLM_MODEL", "")
            or "gpt-4o-mini"
        )
        try:
            from openai import AsyncOpenAI  # local import — no hard dep at module load

            client = AsyncOpenAI(api_key=openai_key)
            response = await client.chat.completions.create(
                model=fallback_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
            )
            return (response.choices[0].message.content or ""), fallback_model
        except Exception as exc:  # noqa: BLE001
            logger.warning("pedagogy: OpenAI fallback judge call failed — %s", exc)
            return None

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def judge_pedagogy(
    question: str,
    reference_answer: str,
    model: str = "",
) -> PedagogyMetadata:
    """Score a question's pedagogical value, Bloom level, and answer completeness.

    Separate Claude call (default ``claude-sonnet-4-6``, override via
    ``QUIZ_PEDAGOGY_MODEL``). Judges from the question + reference answer only.
    Falls back to OpenAI when no Anthropic key, then to a conservative mock.
    """
    anthropic_model = model or os.environ.get("QUIZ_PEDAGOGY_MODEL", "") or "claude-sonnet-4-6"
    result = await _call_judge_llm(
        _PEDAGOGY_SYSTEM_PROMPT,
        _build_qa_user_prompt(question, reference_answer),
        anthropic_model,
    )
    if result is None:
        return _mock_pedagogy()
    raw, model_used = result
    try:
        meta = _parse_pedagogy_json(raw, model=model_used)
        logger.info(
            "pedagogy: judged — value=%s bloom=%s completeness=%s",
            meta.pedagogical_value,
            meta.bloom_level or "?",
            meta.answer_completeness,
        )
        return meta
    except Exception as exc:  # noqa: BLE001
        logger.warning("pedagogy: parse failed — using mock. error=%s", exc)
        return _mock_pedagogy(note=f"[mock] pedagogy parse failed: {exc}")


async def judge_correctness(
    question: str,
    reference_answer: str,
    model: str = "",
) -> CorrectnessMetadata:
    """Independently fact-check the reference answer (correctness != groundedness).

    Separate Claude call (default ``claude-sonnet-4-6``, override via
    ``QUIZ_CORRECTNESS_MODEL``). Judges factual correctness from its own domain
    knowledge — no retrieval context is supplied. OpenAI fallback, then mock.
    """
    anthropic_model = model or os.environ.get("QUIZ_CORRECTNESS_MODEL", "") or "claude-sonnet-4-6"
    result = await _call_judge_llm(
        _CORRECTNESS_SYSTEM_PROMPT,
        _build_qa_user_prompt(question, reference_answer),
        anthropic_model,
    )
    if result is None:
        return _mock_correctness()
    raw, model_used = result
    try:
        meta = _parse_correctness_json(raw, model=model_used)
        logger.info("correctness: judged — correctness=%s", meta.answer_correctness)
        return meta
    except Exception as exc:  # noqa: BLE001
        logger.warning("correctness: parse failed — using mock. error=%s", exc)
        return _mock_correctness(note=f"[mock] correctness parse failed: {exc}")

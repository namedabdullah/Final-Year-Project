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
    "easy": "easy_v7",
    "medium": "medium_v7",
    "hard": "hard_v7",
}

# Shared "Avoid" block — appended to every difficulty's template. Concept-
# oriented production constraints: refuses diagram-label questions, table-cell
# extraction, figure-dependent shapes, and fabricated numeric specifics.
# Records the v2 revision (see claude_review_rag_framework.md §Easy/Medium/Hard
# Prompts).
_AVOID_BLOCK = (
    "Avoid (CRITICAL — ALL of the following are HARD rules):\n"
    # Rule 1: placeholders. Moved to top in R4 because LLMs anchor on early
    # items. Doubled braces below are stripped by str.format() so the LLM
    # sees the literal "{thread}", "{process}", etc.
    "- ABSOLUTE RULE — NO BRACE CHARACTERS IN OUTPUT: The retrieved context "
    "contains placeholder tokens like {{thread}}, {{process}}, {{cpu_core}}, "
    "{{memory_page}}, {{memory_frame}}, and {{semaphore}}. These are concept-slot "
    "markers, NOT real words. If your question OR reference_answer contains "
    "ANY brace character ({{ or }}), you have FAILED the task. Always rewrite "
    "in natural English. Example of FAILURE: \"What is the burst time of "
    "{{process}}?\". Example of SUCCESS: \"What does burst time measure for "
    "a process?\".\n"
    # Rule 2: anti-tautology — new in R4 to catch the "embedded OS for embedded
    # systems" failure mode seen in quiz-caaf0e4a Q6.
    "- ABSOLUTE RULE — NO TAUTOLOGIES: The reference_answer must not just "
    "restate the question. Example of FAILURE: Q=\"What kind of OS is "
    "designed for embedded systems?\" A=\"An embedded OS designed for embedded "
    "systems.\" A correct question requires genuine information to answer.\n"
    # Rule 3: anti-meta — new in R4 to catch "What documents are covered?"
    # failures from quiz-caaf0e4a.
    "- Do NOT ask meta-questions about the source material itself (e.g. "
    "\"What documents are covered?\", \"What does the material describe?\", "
    "\"How many documents are in the study?\"). Ask about the SUBJECT MATTER "
    "(operating systems, threads, scheduling, …), not about the documents.\n"
    "- Do NOT ask about diagram labels, table cell values, figure identifiers, "
    "or instance names (e.g., \"P1\", \"Thread A\", \"core 3\", \"CPU_7\", \"Page 3\").\n"
    "- Do NOT ask \"what is the label of…\" or \"what is the name of the … in the diagram\".\n"
    "- Reference the underlying concept (e.g., \"process\", \"thread\", \"CPU core\", "
    "\"memory page\"), not the specific label the figure uses for one instance.\n"
    "- The reference_answer must be a conceptual statement, not a single "
    "token, table cell, or figure label.\n"
    "- If the question would not make sense to a student without seeing the "
    "original figure, REWRITE it so it does.\n"
    # Rule (v7): anti-fabrication grounding rule. Added after quiz-b363f421
    # (mix, medium): Q3/Q9 cited specific numeric values ("30 seconds",
    # "arriving at 0 seconds") drawn from burst/arrival-time TABLES that were
    # not present in the retrieved prose, so the verifier flagged them
    # answerable_from_context=False (source_lexical_overlap 0.02-0.09). The
    # generator filled the gap from GPT-4o-mini's general scheduling knowledge.
    # Symmetric across arms — lives in the shared block, helps mix most because
    # its graph BFS reaches table-derived entities (P1, Burst Time, Timeline).
    "- ABSOLUTE RULE — NO FABRICATED SPECIFICS: Do NOT cite specific "
    "quantitative values — exact times, durations, sizes, counts, memory "
    "addresses, or numbered instances (e.g. \"30 seconds\", \"arriving at 0 "
    "seconds\", \"4 KB\", \"P2\") — UNLESS that exact value appears verbatim in "
    "the Context above. Such numbers usually originate in a figure or table "
    "that is NOT part of the retrieved text, so a question or reference_answer "
    "that cites them cannot be grounded in the context. Ask about the "
    "underlying relationship in conceptual terms instead. Example of FAILURE: "
    "\"How does a process requiring 30 seconds compare to one requiring 40 "
    "seconds?\" Example of SUCCESS: \"How does a process's burst time influence "
    "the order in which it is scheduled?\"\n"
)

# Full user-turn prompts from claude_review_rag_framework.md §Easy/Medium/Hard
# Prompts.
#
# v2 (2026-05-28): added the Avoid block above and softened the easy
#   answer-shape line.
# v3 (2026-05-28): added the placeholder-handling bullet to the Avoid
#   block, after quiz-bd12fd67-… leaked literal ``{process}`` tokens into
#   generated questions because the LLM treated the redaction placeholders
#   as nouns. v2 quiz records remain tagged ``*_v2`` for traceability.
# v4 (2026-05-28): three same-day refinements after quiz-caaf0e4a-…
#   showed residual failures:
#     - Hardened the placeholder rule into an absolute "no braces in output"
#       prohibition with concrete failure/success examples, and moved it to
#       the FIRST position in the Avoid block (LLMs anchor on early items).
#     - Added an explicit anti-tautology rule (the "embedded OS designed for
#       embedded systems" failure shape).
#     - Added an anti-meta-question rule (the "What documents are covered?"
#       failure shape that bypassed Tier B).
#   Pairs with the formatter change in retrieval.py that drops the
#   ``=== Topic ===`` section (which was triggering the meta-questions).
# v5 (2026-05-28): two structural prompt additions after quiz-a712071b-…
#   showed the LLM converging on a handful of "safe" easy concepts
#   regardless of seed diversity (3× "role of CPU", 4× "function of OS"):
#     - Added a ``Target concept: {target}`` line so the LLM anchors each
#       question on the seed entity (normalised via
#       :func:`lightrag.quiz.artifacts.normalize_concept_name` to avoid
#       reintroducing brace leakage).
#     - Added an ``Already asked (DO NOT REPEAT or REPHRASE):`` block
#       populated with every question generated earlier in the same quiz.
#       Read inside the cap=1 semaphore so each call sees all prior
#       results — see ``pipeline.py:_bounded_generate``.
#     - Added an ABSOLUTE NO REPEATS bullet to the Avoid block.
#   Also paired with a seed-pool filter that drops figure-label entities
#   (``Multilevel Queue Scheduling Diagram``) — see
#   :func:`lightrag.quiz.artifacts.is_figure_label_entity`.
# v6 (2026-05-29): positional reorder + anti-hallucination pairing after
#   quiz-44fbc845-… showed the naive arm hallucinating from empty retrieval
#   and the LLM ignoring the Already-asked list once it grew long:
#     - Moved the ``Already asked`` block to appear AFTER the context (the
#       LLM was generating right after reading context — putting the
#       anti-repeat constraint LAST anchors it as the most recent rule).
#     - Added a ``Final reminder`` sentence after the Already-asked block
#       telling the LLM to rewrite drafts that repeat any prior concept.
#   Paired with two non-prompt changes that v6 expects:
#     - ``pipeline.py:_generate_one`` now refuses to call the generator
#       when ``ctx.is_empty()`` (the previous behaviour produced
#       ungrounded answers from the model's general knowledge).
#     - ``seeds.py:_list_chunks_in_scope`` now reads chunks via
#       ``doc_status.chunks_list`` instead of the broken
#       ``chunks_vdb.query("the")``, which was the upstream cause of
#       ``topic_N`` seeds dominating the naive arm.
# v7 (2026-05-31): anti-fabrication grounding rule added to the shared Avoid
#   block after the smoke-run-#4 verifier pass (quiz-b363f421, mix, medium)
#   showed answerable_from_context=False on 3/10 questions. Q3 and Q9 cited
#   specific numeric values ("30 seconds and another 40 seconds", "arriving at
#   0 seconds and another at 1 second") that originate in burst/arrival-time
#   TABLES absent from the retrieved prose — source_lexical_overlap was 0.02
#   and 0.09 respectively, confirming the reference answers were ungrounded
#   general-knowledge fills. The new ABSOLUTE RULE — NO FABRICATED SPECIFICS
#   forbids citing exact quantitative values unless they appear verbatim in
#   the context. Arm-symmetric (shared block), but helps the mix arm most
#   because its graph BFS bridges clean concept-seeds (``Running``, ``Arrival
#   Time``) into table-derived entity neighbourhoods. No paired non-prompt
#   change — the existing empty-retrieval guard does not fire here (retrieval
#   returned 22-35 chunks; the defect was fabricated specifics, not emptiness).
_PROMPT_TEMPLATES: dict[str, str] = {
    "easy": (
        "You are a quiz question generator for an academic study. Given the context below, "
        "generate exactly ONE question that can be answered directly from a single explicit fact "
        "in the context. The answer must be directly stated — no reasoning or synthesis required.\n\n"
        "Requirements:\n"
        "- The question must be answerable using ONLY the provided context\n"
        "- The answer should be a single short conceptual statement (one sentence) "
        "drawn directly from the context, not a verbatim table cell or label\n"
        "- Do NOT ask for comparisons, causes, or multi-step reasoning\n\n"
        f"{_AVOID_BLOCK}\n"
        "- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the \"Already asked\" "
        "section below is non-empty, your question must NOT cover the same "
        "concept, phrasing, or answer as any item in that list. Pick a "
        "different aspect of the target concept, or a different sub-concept "
        "altogether, even if the retrieved context is similar.\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Target concept: {target}\n\n"
        "Context:\n{context}\n\n"
        "Already asked (DO NOT REPEAT or REPHRASE any of these):\n{prior_questions}\n\n"
        "Final reminder: generate ONE question that is NOT semantically "
        "equivalent to any item in the \"Already asked\" list above. If your "
        "first draft repeats any prior question's concept or phrasing, "
        "rewrite it before returning JSON."
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
        "- Do NOT ask for causal chains, predictions, or multi-step inference\n\n"
        f"{_AVOID_BLOCK}\n"
        "- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the \"Already asked\" "
        "section below is non-empty, your question must NOT cover the same "
        "concept, phrasing, or answer as any item in that list. Pick a "
        "different aspect of the target concept, or a different sub-concept "
        "altogether, even if the retrieved context is similar.\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Target concept: {target}\n\n"
        "Context:\n{context}\n\n"
        "Already asked (DO NOT REPEAT or REPHRASE any of these):\n{prior_questions}\n\n"
        "Final reminder: generate ONE question that is NOT semantically "
        "equivalent to any item in the \"Already asked\" list above. If your "
        "first draft repeats any prior question's concept or phrasing, "
        "rewrite it before returning JSON."
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
        "- Do NOT ask factual recall or simple comparison questions\n\n"
        f"{_AVOID_BLOCK}\n"
        "- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the \"Already asked\" "
        "section below is non-empty, your question must NOT cover the same "
        "concept, phrasing, or answer as any item in that list. Pick a "
        "different aspect of the target concept, or a different sub-concept "
        "altogether, even if the retrieved context is similar.\n"
        "- Return valid JSON with keys: \"question\" (string) and \"reference_answer\" (string)\n\n"
        "Target concept: {target}\n\n"
        "Context:\n{context}\n\n"
        "Already asked (DO NOT REPEAT or REPHRASE any of these):\n{prior_questions}\n\n"
        "Final reminder: generate ONE question that is NOT semantically "
        "equivalent to any item in the \"Already asked\" list above. If your "
        "first draft repeats any prior question's concept or phrasing, "
        "rewrite it before returning JSON."
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
    *,
    target_concept: str | None = None,
    prior_questions: list[str] | None = None,
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
        context:         The retrieval context produced by the retrieval arm.
        difficulty:      One of "easy", "medium", "hard".
        model:           OpenAI model identifier; ``None`` resolves from env (see above).
        target_concept:  Optional concept name to anchor the question on. Surfaced
                         to the LLM as a ``Target concept`` line so it focuses on
                         the seed entity rather than drifting to the most generic
                         concept in the retrieval. Defaults to ``context.seed_query``
                         when ``None`` and ``context`` carries one. The caller is
                         expected to have normalised this with
                         :func:`lightrag.quiz.artifacts.normalize_concept_name`
                         so we don't reintroduce ``{thread}`` placeholder leakage.
        prior_questions: List of questions already generated earlier in the same
                         quiz. Surfaced to the LLM as an "Already asked" block so
                         it can avoid duplicates. With ``cap=1`` sequential
                         generation, the caller can simply maintain a shared list.

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

    # Target concept: prefer the explicit argument, fall back to the seed
    # query recorded on the context, then to a generic noun if neither is
    # available. The caller is expected to have normalised any instance
    # labels (Thread 3 → thread) before passing them in.
    target = (target_concept or getattr(context, "seed_query", "") or "the topic at hand").strip()
    if not target:
        target = "the topic at hand"

    # Prior-question list: one per line, numbered. "(none yet)" for the
    # first call so the prompt template doesn't render an empty section
    # that confuses the LLM.
    if prior_questions:
        priors_str = "\n".join(f"{i}. {q}" for i, q in enumerate(prior_questions, 1))
    else:
        priors_str = "(none yet — this is the first question of the quiz)"

    user_message = template.format(
        context=formatted_context,
        target=target,
        prior_questions=priors_str,
    )
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

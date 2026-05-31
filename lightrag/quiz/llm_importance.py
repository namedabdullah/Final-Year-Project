"""
Step 2 — LLM educational-importance signal for seed selection (quality-plan.md
decision D4 / suggestions.md A3).

A semantic refinement layer that the deterministic RRF signals cannot provide:
it scores each candidate seed's *educational importance* (1-10) so weak-but-not-
structurally-detectable seeds (a course-title slide, a filler slide, a snake_case
table identifier, an instance label like "Process P2") sink in the ranking.

Role: **re-rank only** (the user's choice) — the score becomes an additional RRF
signal via ``scoring.apply_llm_rerank``; nothing is hard-dropped here.

Design invariants (quality-plan.md §0, D4):
  - **Top-N only** — bounds cost to one batched call per quiz.
  - **Temperature 0 + disk cache** keyed by (doc-set, text) — the 300-question
    matrix stays reproducible and each concept is judged once.
  - **Symmetric** — identical prompt/model for both arms (mix judges entity
    names, naive judges chunk lead-text); only the candidate *source* differs.
  - **Graceful no-op** — no API key, an API error, or unparseable output returns
    ``{}`` so the deterministic ranking stands unchanged. Never fails a quiz.

Only the async ``score_importance`` touches the network; ``_cache_key``,
``_build_prompt`` and ``_parse_scores`` are pure and unit-tested.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)

_RERANK_ENABLED = os.environ.get("QUIZ_SEED_LLM_RERANK", "true").lower() == "true"
_TOP_N = int(os.environ.get("QUIZ_SEED_LLM_TOPN", "50"))
_CACHE_FILENAME = "quiz_llm_importance_cache.json"
_RETRY_ATTEMPTS = 3

_PROMPT_HEADER = (
    "You are helping build an educational quiz for a university Operating Systems "
    "course. Rate each item below by how valuable it is as a quiz *topic* for "
    "student learning, on a scale of 1 to 10.\n\n"
    "10 = a foundational concept every student must understand; "
    "1 = not worth testing (a slide/section title, author or course metadata, a "
    "figure/table caption or identifier, filler, or an overly specific instance "
    "label such as 'Process 2').\n\n"
    "Judge the underlying concept, not the wording. Return ONLY JSON of the form "
    '{\"scores\": [{\"i\": <item number>, \"score\": <integer 1-10>}, ...]} with '
    "one entry for every item.\n\nItems:\n"
)


def is_enabled() -> bool:
    return _RERANK_ENABLED


def top_n() -> int:
    return _TOP_N


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _cache_key(doc_set_key: str, text: str) -> str:
    return hashlib.md5(f"{doc_set_key}||{text}".encode("utf-8")).hexdigest()


def _build_prompt(items: Sequence[str]) -> str:
    lines = [f"{i}. {t}" for i, t in enumerate(items, 1)]
    return _PROMPT_HEADER + "\n".join(lines)


def _parse_scores(raw: str, n: int) -> Dict[int, float]:
    """Parse ``{"scores": [{"i":1,"score":8}, ...]}`` → ``{0-based index: score}``.

    Tolerant: ignores out-of-range indices/scores, returns whatever it can.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    out: Dict[int, float] = {}
    for entry in (data or {}).get("scores", []):
        try:
            i = int(entry["i"]) - 1  # 1-based → 0-based
            score = float(entry["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n:
            out[i] = max(1.0, min(10.0, score))
    return out


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


def _load_cache(working_dir: str) -> Dict[str, float]:
    try:
        path = Path(working_dir) / _CACHE_FILENAME
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - cache is best-effort
        logger.debug("llm_importance: cache load failed: %s", exc)
    return {}


def _save_cache(working_dir: str, cache: Dict[str, float]) -> None:
    try:
        path = Path(working_dir) / _CACHE_FILENAME
        path.write_text(json.dumps(cache), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - cache is best-effort
        logger.debug("llm_importance: cache save failed: %s", exc)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def score_importance(
    candidates: List[Tuple[str, str]],
    *,
    doc_set_key: str,
    working_dir: str,
    model: str | None = None,
) -> Dict[str, float]:
    """Return ``{candidate_key: importance_score}`` for the given candidates.

    ``candidates`` is a list of ``(key, text)`` — ``key`` is the row key
    (entity name / chunk id), ``text`` is what the LLM judges (entity name /
    chunk lead-text). Cached judgements are reused; only cache-misses hit the
    API in a single batched call. Returns ``{}`` (no-op) on any failure.
    """
    if not candidates:
        return {}

    api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("LLM_BINDING_API_KEY", "")
    if not api_key:
        logger.info("llm_importance: no API key — skipping LLM re-rank (deterministic ranking stands).")
        return {}

    model = model or (
        os.environ.get("QUIZ_SEED_LLM_MODEL", "")
        or os.environ.get("QUIZ_GENERATION_MODEL", "")
        or os.environ.get("LLM_MODEL", "")
        or "gpt-4o-mini"
    )

    cache = _load_cache(working_dir)
    result: Dict[str, float] = {}
    misses: List[Tuple[str, str]] = []
    for key, text in candidates:
        ck = _cache_key(doc_set_key, text)
        if ck in cache:
            result[key] = float(cache[ck])
        else:
            misses.append((key, text))

    if misses:
        miss_scores = await _call_llm(api_key, model, [t for _, t in misses])
        if miss_scores:
            for idx, (key, text) in enumerate(misses):
                if idx in miss_scores:
                    score = miss_scores[idx]
                    result[key] = score
                    cache[_cache_key(doc_set_key, text)] = score
            _save_cache(working_dir, cache)

    return result


async def _call_llm(api_key: str, model: str, items: List[str]) -> Dict[int, float]:
    """One batched, temperature-0 importance call. Returns {} on failure."""
    try:
        from openai import AsyncOpenAI
        import openai
    except Exception as exc:  # pragma: no cover
        logger.warning("llm_importance: openai import failed: %s", exc)
        return {}

    client = AsyncOpenAI(api_key=api_key)
    messages = [{"role": "user", "content": _build_prompt(items)}]
    delay = 2.0
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=2048,
            )
            return _parse_scores(response.choices[0].message.content or "", len(items))
        except openai.RateLimitError as exc:
            if attempt == _RETRY_ATTEMPTS:
                logger.warning("llm_importance: rate-limited, giving up — %s", exc)
                return {}
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
        except Exception as exc:
            logger.warning("llm_importance: scoring call failed (%s) — deterministic ranking stands.", exc)
            return {}
    return {}

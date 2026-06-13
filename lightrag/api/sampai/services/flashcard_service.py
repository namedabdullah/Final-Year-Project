"""Flashcard generation + Leitner spaced-repetition logic.

Generation reuses the scoped retrieval gateway (file-scoped, no leakage) → a broad
context → strict-JSON cards from the engine LLM, with cross-deck dedup and a single
retry to fill any shortfall. Review scheduling is the classic Leitner box system.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

import json_repair
from sqlalchemy import select

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.models.flashcard import (
    Flashcard,
    FlashcardCardType,
    FlashcardDeck,
    FlashcardDeckStatus,
)
from lightrag.api.sampai.services.engine_access import get_engine

logger = logging.getLogger("sampai.flashcards")

# Leitner intervals in days, keyed by box (1..5).
LEITNER_INTERVALS = {1: 0, 2: 1, 3: 3, 4: 7, 5: 14}
_VALID_TYPES = {"definition", "concept", "example", "formula"}
DEDUP_FRONT_CAP = 100
RAG_CHUNK_TOP_K = 25

_BROAD_SEED = (
    "All key terms, definitions, concepts, examples, and formulas in this document. "
    "Cover every major topic uniformly."
)


# ── Leitner (pure) ───────────────────────────────────────────────────────────
def review_card(box: int, result: str) -> tuple[int, datetime]:
    """Return (new_box, next_review_at). know→+1 (max5), unsure→-1 (min1), forgot→1."""
    if result == "know":
        new_box = min(box + 1, 5)
    elif result == "unsure":
        new_box = max(box - 1, 1)
    else:  # forgot
        new_box = 1
    return new_box, datetime.utcnow() + timedelta(days=LEITNER_INTERVALS[new_box])


# ── card validation / parsing ────────────────────────────────────────────────
def _valid_cards(raw: object) -> list[dict]:
    out: list[dict] = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        front, back, ctype = c.get("front", ""), c.get("back", ""), c.get("type", "")
        if (
            isinstance(front, str) and front.strip() and len(front) <= 300
            and isinstance(back, str) and back.strip() and len(back) <= 1000
            and ctype in _VALID_TYPES
        ):
            out.append({"front": front.strip(), "back": back.strip(), "type": ctype})
    return out


def _parse_cards(text: str) -> list:
    t = (text or "").strip()
    if t.startswith("```"):
        t = "\n".join(t.split("\n")[1:])
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    try:
        parsed = json_repair.loads(t)
    except Exception:
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("cards", [])
    return parsed if isinstance(parsed, list) else []


def _system_prompt(n: int, existing_fronts: list[str]) -> str:
    dedup = ""
    if existing_fronts:
        listed = "\n".join(f'  - "{f}"' for f in existing_fronts[:50])
        dedup = (
            "\nDO NOT generate cards whose front is semantically similar to any of these "
            f"already-existing cards:\n{listed}\n"
        )
    return (
        "You create educational flashcards GROUNDED ONLY in the provided context.\n"
        f'Output STRICT JSON only: {{"cards": [...]}}, EXACTLY {n} entries.\n'
        'Each entry: {"front": "...", "back": "...", '
        '"type": "definition"|"concept"|"example"|"formula"}\n'
        "Rules:\n"
        "- front: concise term, question, or scenario (max 20 words)\n"
        "- back: clear answer, 1-4 sentences, no bullet lists\n"
        "- type mix: ~50% definition, ~25% concept, ~25% example; formula when warranted\n"
        "- Cover the document uniformly; never invent facts not in the context\n"
        f"{dedup}"
        "Output JSON only — no markdown fences."
    )


async def _generate_cards(engine, context: str, n: int, existing: list[str]) -> list[dict]:
    raw = await engine.llm_model_func(
        f"N: {n}\nCONTEXT:\n{context}", system_prompt=_system_prompt(n, existing)
    )
    cards = _valid_cards(_parse_cards(raw))
    if len(cards) < n:
        missing = n - len(cards)
        logger.info("flashcards: retry to fill %d missing", missing)
        try:
            raw2 = await engine.llm_model_func(
                f"N: {missing}\nCONTEXT:\n{context}",
                system_prompt=_system_prompt(missing, existing),
            )
            cards += _valid_cards(_parse_cards(raw2))
        except Exception:
            logger.warning("flashcards retry failed", exc_info=True)
    return cards[:n]


# ── background task ──────────────────────────────────────────────────────────
async def generate_deck_task(deck_id: int, classroom_id: int, file_id: int, doc_id: str | None):
    from lightrag.api.sampai.services.rag_gateway import scoped_chunks
    from lightrag.quiz.retrieval import RetrievalContext

    sm = get_sessionmaker()
    async with sm() as db:
        deck = await db.get(FlashcardDeck, deck_id)
        if deck is None:
            return
        deck.status = FlashcardDeckStatus.GENERATING
        user_id, card_count = deck.user_id, deck.card_count
        await db.commit()

    try:
        engine = await get_engine(classroom_id)
        doc_ids = {doc_id} if doc_id else set()
        chunks = await scoped_chunks(engine, _BROAD_SEED, doc_ids, top_k=RAG_CHUNK_TOP_K)
        if not chunks:
            raise RuntimeError("No content retrieved for this file")
        context = RetrievalContext(chunks=chunks, chunk_count=len(chunks)).format_for_prompt()

        async with sm() as db:
            existing = list(
                (
                    await db.execute(
                        select(Flashcard.front)
                        .where(Flashcard.user_id == user_id, Flashcard.file_id == file_id)
                        .order_by(Flashcard.created_at.desc())
                        .limit(DEDUP_FRONT_CAP)
                    )
                ).scalars().all()
            )

        t0 = time.time()
        cards = await _generate_cards(engine, context, card_count, existing)
        if len(cards) < card_count:
            raise RuntimeError(f"LLM produced only {len(cards)} valid cards; expected {card_count}")

        now = datetime.utcnow()
        async with sm() as db:
            deck = await db.get(FlashcardDeck, deck_id)
            db.add_all([
                Flashcard(
                    deck_id=deck_id, file_id=file_id, user_id=user_id,
                    front=c["front"], back=c["back"],
                    card_type=FlashcardCardType(c["type"]), box=1, next_review_at=now,
                )
                for c in cards
            ])
            deck.card_count = len(cards)
            deck.status = FlashcardDeckStatus.READY
            deck.ready_at = now
            deck.generation_meta = {
                "context_chars": len(context),
                "chunk_top_k": RAG_CHUNK_TOP_K,
                "elapsed_s": round(time.time() - t0, 2),
                "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                "dedup_skipped": len(existing),
            }
            await db.commit()
        logger.info("deck %s ready (%d cards)", deck_id, len(cards))
    except Exception as exc:
        logger.exception("deck %s failed", deck_id)
        async with sm() as db:
            deck = await db.get(FlashcardDeck, deck_id)
            if deck is not None:
                deck.status = FlashcardDeckStatus.FAILED
                deck.error_msg = str(exc)[:500]
                await db.commit()

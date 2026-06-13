"""Scoped retrieval gateway — the single place SAMpai talks to a classroom engine.

LightRAG's ``QueryParam`` has NO per-document filter, so file-scoped features must
NOT call ``aquery`` directly (that would leak across the whole classroom workspace).
Instead we reuse the proven scoping idioms from the research module
``lightrag.quiz.retrieval`` (vector overfetch → filter by ``full_doc_id`` → cap) and
drive the LLM ourselves.

Functions:
- ``scoped_chunks``         — file-scoped vector chunks (chat, flashcards)
- ``scoped_answer_stream``  — grounded, streamed answer over a doc scope (chat)
- ``scoped_mix_context``    — KG-flavored scoped context (mindmap, Phase 4)
- ``classroom_answer_stream`` — whole-workspace answer via aquery (@SAMpai, Phase 5)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from lightrag.quiz.retrieval import RetrievalContext, retrieve_mix_arm

logger = logging.getLogger("sampai.rag_gateway")

_CHAT_SYSTEM = (
    "You are SAMpai, a friendly study tutor. Answer the student's question using ONLY "
    "the information in the provided context from their document. Ground every claim in "
    "that context; if the answer is not present, say you couldn't find it in this document "
    "and suggest what the document does cover. Never invent facts. Reply in clear Markdown — "
    "concise but complete."
)

_EMPTY_MSG = (
    "I couldn't find anything in this document to answer that. The file may still be "
    "processing, or this topic may not be covered here."
)


async def scoped_chunks(rag, query: str, doc_ids: set[str], top_k: int = 12) -> list[dict]:
    """File-scoped vector retrieval (the naive-arm idiom, chat-sized top_k).

    Overfetch then keep only chunks whose ``full_doc_id`` is in scope — this is the
    leakage-prevention boundary.
    """
    try:
        results = await rag.chunks_vdb.query(query, top_k=top_k * 10)
    except Exception as exc:
        logger.warning("scoped_chunks: chunks_vdb.query failed: %s", exc)
        return []
    return [c for c in results if c.get("full_doc_id") in doc_ids][:top_k]


def _context_str(chunks: list[dict]) -> str:
    return RetrievalContext(chunks=chunks, chunk_count=len(chunks)).format_for_prompt()


async def scoped_answer_stream(
    rag,
    query: str,
    doc_ids: set[str],
    history: list[dict] | None = None,
    top_k: int = 12,
) -> AsyncIterator[str]:
    """Yield a grounded answer token-by-token, scoped to ``doc_ids`` (mix mode)."""
    context = await scoped_mix_context(rag, query, doc_ids, difficulty="medium")
    if not context or not context.strip():
        yield _EMPTY_MSG
        return

    prompt = f"Context from the document:\n{context}\n\nQuestion: {query}"

    try:
        stream = await rag.llm_model_func(
            prompt,
            system_prompt=_CHAT_SYSTEM,
            history_messages=history or [],
            stream=True,
        )
    except Exception as exc:
        logger.error("scoped_answer_stream: LLM call failed: %s", exc)
        yield "Sorry, I hit an error answering that. Please try again."
        return

    if isinstance(stream, str):  # non-streaming binding fallback
        yield stream
        return
    async for token in stream:
        if token:
            yield token


async def scoped_answer(rag, query: str, doc_ids: set[str], history=None, top_k=12) -> str:
    """Non-streaming convenience wrapper (collects the stream)."""
    parts: list[str] = []
    async for tok in scoped_answer_stream(rag, query, doc_ids, history, top_k):
        parts.append(tok)
    return "".join(parts)


async def scoped_mix_context(
    rag, query: str, doc_ids: set[str], difficulty: str = "medium"
) -> str:
    """KG-flavored scoped context (entities + relations + BFS + chunks) as a prompt
    string. Used by mindmap/flashcards in Phase 4. Reuses the quiz mix arm verbatim."""
    ctx = await retrieve_mix_arm(rag, query, difficulty, set(doc_ids))
    return ctx.format_for_prompt()


async def classroom_answer_stream(
    rag, query: str, history: list[dict] | None = None, mode: str = "mix"
) -> AsyncIterator[str]:
    """Whole-classroom answer (NOT file-scoped) via LightRAG's own query path.

    The workspace IS the classroom, so aquery's scope is exactly right here.
    Used by the @SAMpai group-chat agent (Phase 5).
    """
    from lightrag import QueryParam

    param = QueryParam(
        mode=mode, stream=True, enable_rerank=False, conversation_history=history or []
    )
    result = await rag.aquery(query, param=param)
    if isinstance(result, str):
        yield result
        return
    async for token in result:
        if token:
            yield token

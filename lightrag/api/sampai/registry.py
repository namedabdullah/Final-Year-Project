"""Per-classroom LightRAG engine registry.

One :class:`~lightrag.LightRAG` instance per classroom (``workspace="classroom_{id}"``),
built lazily and reusing the server's shared ``embedding_func`` + the base ``rag``'s LLM
func + the server's storage configuration (``args.*_storage``). The single ``rag`` the
server constructed for the default workspace is left completely untouched.

This mirrors the constructor in ``lightrag/api/lightrag_server.py`` (``create_app``,
~line 1938) but overrides ``workspace`` + ``working_dir``. ``rag.initialize_storages()``
auto-initializes ``pipeline_status`` for the workspace (see ``lightrag.py:1128``), so no
separate ``initialize_pipeline_status`` call is needed here.

Process-bound + single-worker by design (see sampai-plan §8): the registry lives in
memory, so the server must run with a single worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict

from lightrag import LightRAG

logger = logging.getLogger("sampai.registry")


def workspace_for(classroom_id) -> str:
    """Stable workspace name for a classroom id."""
    return f"classroom_{classroom_id}"


class EngineRegistry:
    """Lazy, LRU+TTL-evicting registry of per-classroom LightRAG engines."""

    def __init__(
        self,
        *,
        args,
        base_rag: LightRAG,
        embedding_func,
        idle_ttl: int = 1800,
        max_resident: int = 8,
    ) -> None:
        self._args = args
        self._base_rag = base_rag
        self._embedding_func = embedding_func
        self._idle_ttl = idle_ttl
        self._max_resident = max_resident

        self._engines: "OrderedDict[str, LightRAG]" = OrderedDict()
        self._last_used: dict[str, float] = {}
        self._build_locks: dict[str, asyncio.Lock] = {}
        self._mutex = asyncio.Lock()

    # ── public API ──────────────────────────────────────────────────────────

    async def get_engine(self, classroom_id) -> LightRAG:
        """Return (creating if needed) the LightRAG engine for a classroom."""
        ws = workspace_for(classroom_id)

        # Fast path — already resident.
        engine = self._engines.get(ws)
        if engine is not None:
            self._touch(ws)
            return engine

        # Slow path — build under a per-workspace lock (double-checked).
        lock = await self._lock_for(ws)
        async with lock:
            engine = self._engines.get(ws)
            if engine is not None:
                self._touch(ws)
                return engine
            engine = await self._build(ws)
            self._engines[ws] = engine
            self._touch(ws)
            await self._evict_idle()
            return engine

    async def aclose(self) -> None:
        """Finalize every resident engine (lifespan shutdown)."""
        async with self._mutex:
            for ws, engine in list(self._engines.items()):
                await self._finalize(ws, engine)
            self._engines.clear()
            self._last_used.clear()

    @property
    def resident_count(self) -> int:
        return len(self._engines)

    # ── internals ───────────────────────────────────────────────────────────

    async def _lock_for(self, ws: str) -> asyncio.Lock:
        async with self._mutex:
            lock = self._build_locks.get(ws)
            if lock is None:
                lock = asyncio.Lock()
                self._build_locks[ws] = lock
            return lock

    def _touch(self, ws: str) -> None:
        self._last_used[ws] = time.monotonic()
        self._engines.move_to_end(ws)

    async def _build(self, ws: str) -> LightRAG:
        args = self._args
        working_dir = os.path.join(args.working_dir, ws)
        os.makedirs(working_dir, exist_ok=True)

        logger.info("Building classroom engine (workspace=%s)", ws)
        engine = LightRAG(
            working_dir=working_dir,
            workspace=ws,
            # Reuse the server's already-built shared functions.
            llm_model_func=self._base_rag.llm_model_func,
            llm_model_name=getattr(self._base_rag, "llm_model_name", args.llm_model),
            embedding_func=self._embedding_func,
            # Storage classes come straight from server config (env-driven).
            kv_storage=args.kv_storage,
            vector_storage=args.vector_storage,
            graph_storage=args.graph_storage,
            doc_status_storage=args.doc_status_storage,
            # SAMpai scopes retrieval itself (workspace filter + full_doc_id post-filter),
            # so the engine must NOT impose an absolute cosine floor. The server default
            # (COSINE_THRESHOLD=0.2) silently drops *generic* generator seeds ("key
            # concepts…", "all key terms…") — they embed below 0.2 against specific
            # subject chunks — making quiz/mindmap/flashcard retrieval return EMPTY even
            # though the content is present. 0.0 returns top_k by score; our own filters
            # enforce scope. (Chat survived because real questions clear 0.2.)
            vector_db_storage_cls_kwargs={"cosine_better_than_threshold": 0.0},
            enable_llm_cache=args.enable_llm_cache,
            enable_llm_cache_for_entity_extract=args.enable_llm_cache_for_extract,
            vlm_process_enable=getattr(args, "vlm_process_enable", False),
            max_parallel_insert=args.max_parallel_insert,
            max_graph_nodes=args.max_graph_nodes,
        )
        # Connects storages AND auto-inits pipeline_status for this workspace.
        await engine.initialize_storages()
        return engine

    async def _evict_idle(self) -> None:
        """Evict TTL-expired engines, then LRU-trim down to ``max_resident``."""
        now = time.monotonic()

        # TTL eviction.
        expired = [
            ws
            for ws, last in self._last_used.items()
            if now - last > self._idle_ttl
        ]
        for ws in expired:
            engine = self._engines.pop(ws, None)
            self._last_used.pop(ws, None)
            if engine is not None:
                await self._finalize(ws, engine)

        # LRU trim (OrderedDict is most-recently-used at the end).
        while len(self._engines) > self._max_resident:
            ws, engine = self._engines.popitem(last=False)
            self._last_used.pop(ws, None)
            await self._finalize(ws, engine)

    async def _finalize(self, ws: str, engine: LightRAG) -> None:
        try:
            await engine.finalize_storages()
            logger.info("Finalized classroom engine (workspace=%s)", ws)
        except Exception as exc:  # never let teardown break the loop
            logger.warning("Error finalizing engine %s: %s", ws, exc)

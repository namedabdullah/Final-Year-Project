"""
Seed query sampling for the quiz pipeline.

Each of N questions needs a distinct seed so the generator doesn't
produce N copies of the same question.

Strategy:
  - mix mode  → entity-weighted sampling by degree centrality
  - naive / fallback → first-sentence of a random chunk

Phase 1: stubs that return placeholder seeds.
Phase 3: full implementation using rag.entities_vdb / rag.chunks_vdb.
"""

from __future__ import annotations

import logging
import random
import re
from typing import TYPE_CHECKING, List, Set

from lightrag.constants import GRAPH_FIELD_SEP

if TYPE_CHECKING:
    from lightrag import LightRAG

logger = logging.getLogger(__name__)


def _first_sentence(text: str) -> str:
    """Return the first sentence (up to 200 chars) of a chunk."""
    stripped = text.strip()
    match = re.search(r"[.!?]", stripped[:300])
    if match:
        return stripped[: match.start() + 1].strip()
    return stripped[:200].strip()


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


async def _get_scope_chunk_ids(rag: "LightRAG", scope_doc_ids: Set[str]) -> Set[str]:
    """Return the set of chunk IDs that belong to the given document IDs.

    Uses a broad "the" query with top_k=500 to approximate coverage.
    This is an approximation for Phase 3; Phase 7+ can enumerate properly.
    """
    try:
        results = await rag.chunks_vdb.query("the", top_k=500)
        return {c["id"] for c in results if c.get("full_doc_id") in scope_doc_ids}
    except Exception as exc:
        logger.warning("_get_scope_chunk_ids: chunks_vdb query failed: %s", exc)
        return set()


async def _list_entities_in_scope(
    rag: "LightRAG",
    scope_doc_ids: Set[str],
    scope_chunk_ids: Set[str],
) -> List[dict]:
    """Return all entities whose source chunks belong to selected docs.

    Queries entities_vdb broadly with "the" at top_k=500, then keeps only
    those whose source_id overlaps with scope_chunk_ids.
    """
    try:
        results = await rag.entities_vdb.query("the", top_k=500)
    except Exception as exc:
        logger.warning("_list_entities_in_scope: entities_vdb query failed: %s", exc)
        return []

    filtered: List[dict] = []
    for e in results:
        src = e.get("source_id", "")
        for cid in src.split(GRAPH_FIELD_SEP):
            if cid.strip() in scope_chunk_ids:
                filtered.append(e)
                break
    return filtered


async def _list_chunks_in_scope(
    rag: "LightRAG",
    scope_doc_ids: Set[str],
) -> List[dict]:
    """Return all chunks belonging to selected docs.

    Queries chunks_vdb broadly with "the" at top_k=500, then keeps only
    those whose full_doc_id is in scope_doc_ids.
    """
    try:
        results = await rag.chunks_vdb.query("the", top_k=500)
        return [c for c in results if c.get("full_doc_id") in scope_doc_ids]
    except Exception as exc:
        logger.warning("_list_chunks_in_scope: chunks_vdb query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def sample_seeds(
    rag: "LightRAG",
    mode: str,
    n: int,
    scope_doc_ids: set,
) -> tuple[List[str], str]:
    """Return (seeds, strategy_label).

    strategy_label is 'entity' or 'chunk' — recorded in metadata.

    mix mode  → entity-based sampling (using entity name as seed query).
    naive / fallback → chunk-based sampling (first sentence of a chunk).

    Both strategies use broad VDB queries to approximate the full set of
    in-scope entities/chunks (Phase 3 approximation).
    """
    if mode == "mix":
        strategy = "entity"

        scope_chunk_ids = await _get_scope_chunk_ids(rag, scope_doc_ids)
        entities = await _list_entities_in_scope(rag, scope_doc_ids, scope_chunk_ids)

        if entities:
            names = [
                e.get("entity_name", "")
                for e in entities
                if e.get("entity_name")
            ]
            if names:
                if len(names) >= n:
                    seeds = random.sample(names, n)
                else:
                    # Sampling with replacement when pool is smaller than n
                    seeds = [random.choice(names) for _ in range(n)]
                return seeds, strategy

        # Fallback: generic seeds
        seeds = [f"topic_{i+1}" for i in range(n)]
        return seeds, strategy

    else:
        strategy = "chunk"

        chunks = await _list_chunks_in_scope(rag, scope_doc_ids)

        if chunks:
            sampled = random.sample(chunks, min(n, len(chunks)))
            seeds_list = [
                _first_sentence(c.get("content", f"topic_{i+1}"))
                for i, c in enumerate(sampled)
            ]
            # Pad with replacement draws if pool < n
            while len(seeds_list) < n:
                c = random.choice(chunks)
                seeds_list.append(_first_sentence(c.get("content", "topic")))
            return seeds_list, strategy

        # Fallback
        seeds = [f"topic_{i+1}" for i in range(n)]
        return seeds, strategy

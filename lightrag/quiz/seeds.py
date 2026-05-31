"""
Seed query sampling for the quiz pipeline.

Each of N questions needs a distinct seed so the generator doesn't
produce N copies of the same question.

Two strategies, selected via ``QUIZ_SEED_STRATEGY`` (default ``pedagogical``):

  - ``pedagogical`` — RRF-scored, file-balanced seeds (quality-plan.md §5-6):
      * mix   → graph entities scored by in-scope degree / cross-doc / frequency
      * naive → chunks scored by content-only signals (no graph; §0 trap)
    Both run through the Cap+Merit+Floor allocator so contribution is *earned*.
  - ``random`` — the legacy uniform-random baseline, retained for the Phase-4
    ablation (quality-plan.md §8.3).

Seeds are drawn from a deterministic per-(doc-set, mode) RNG so the thesis
matrix is reproducible (quality-plan.md §7.4).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Set

from lightrag.constants import GRAPH_FIELD_SEP
from lightrag.quiz import llm_importance, scoring
from lightrag.quiz.artifacts import (
    is_artifact_id,
    is_figure_label_entity,
    is_instance_label_entity,
)
from lightrag.utils import compute_mdhash_id

if TYPE_CHECKING:
    from lightrag import LightRAG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type + RNG
# ---------------------------------------------------------------------------


@dataclass
class SeedSelection:
    """Result of seed sampling (quality-plan.md §4).

    ``seeds`` and ``seed_scores`` are parallel lists; ``seed_scores`` is empty
    for the random baseline. ``file_contributions`` is a list of
    ``{doc_id, seed_count, reason}`` dicts (empty for the random baseline).

    ``authoritative`` distinguishes a *legitimately small/empty* pedagogical
    result (candidates existed but the meaningfulness floor emptied the pool)
    from a *true failure* (no candidates at all, or the scorer raised). Only the
    latter may fall back to the random baseline; an authoritative empty result
    must be honoured, so the floor cannot be silently bypassed by re-emitting
    the very anchors it excluded.
    """

    seeds: List[str]
    strategy: str
    file_contributions: List[dict] = field(default_factory=list)
    seed_scores: List[dict] = field(default_factory=list)
    authoritative: bool = False


def _make_rng(scope_doc_ids: set, mode: str) -> random.Random:
    """Deterministic RNG seeded from the doc-set + mode (quality-plan.md §7.4).

    Difficulty is intentionally excluded so easy/medium/hard for the same
    (arm, file-set) share a seed pool. ``QUIZ_SEED_RNG_SEED`` overrides.
    """
    override = os.environ.get("QUIZ_SEED_RNG_SEED")
    if override:
        try:
            return random.Random(int(override))
        except ValueError:
            return random.Random(override)
    key = "|".join([mode, *sorted(str(d) for d in scope_doc_ids)])
    seed_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % (2**32)
    return random.Random(seed_int)


def _first_sentence(text: str) -> str:
    """Return the first sentence (up to 200 chars) of a chunk."""
    stripped = text.strip()
    match = re.search(r"[.!?]", stripped[:300])
    if match:
        return stripped[: match.start() + 1].strip()
    return stripped[:200].strip()


def _primary_source_chunk(entity: dict) -> str:
    """Return the entity's first source chunk ID — its 'home' chunk.

    Used by ``sample_seeds`` to guarantee no two mix-arm seeds resolve to
    the same chunk, which is what produced the duplicate-question
    collisions in quiz-50f66d4a.
    """
    src = entity.get("source_id", "")
    for cid in src.split(GRAPH_FIELD_SEP):
        cid = cid.strip()
        if cid:
            return cid
    return ""


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


async def _get_scope_chunk_ids(rag: "LightRAG", scope_doc_ids: Set[str]) -> Set[str]:
    """Return the set of chunk IDs that belong to the given document IDs.

    Reads ``chunks_list`` directly from ``doc_status`` (deterministic,
    one record per doc) instead of approximating coverage via a broad
    ``chunks_vdb.query("the", top_k=500)``. The query-based approach
    returned ``scope_chunk_ids=0`` in real runs because stop-word
    embeddings don't match concept-chunk embeddings well — and the empty
    set then cascaded into ``_list_entities_in_scope`` returning [],
    forcing the seed sampler into ``topic_N`` placeholders.
    """
    chunk_ids: Set[str] = set()
    for doc_id in scope_doc_ids:
        try:
            status = await rag.doc_status.get_by_id(doc_id)
        except Exception as exc:
            logger.warning(
                "_get_scope_chunk_ids: doc_status.get_by_id(%s) failed: %s",
                doc_id,
                exc,
            )
            continue
        if not status:
            continue
        # DocProcessingStatus may be a dict (from JSON storage) or a
        # dataclass (from richer backends). Handle both shapes.
        chunks_list = (
            status.get("chunks_list") if isinstance(status, dict)
            else getattr(status, "chunks_list", None)
        )
        if chunks_list:
            chunk_ids.update(c for c in chunks_list if c)
    return chunk_ids


async def _list_entities_in_scope(
    rag: "LightRAG",
    scope_doc_ids: Set[str],
    scope_chunk_ids: Set[str],
) -> List[dict]:
    """Return all entities whose source chunks belong to selected docs.

    Uses get_popular_labels (degree-ranked) + get_nodes_batch — same
    approach as _list_entities_unscoped — then keeps only entities whose
    source_id overlaps scope_chunk_ids.  Replaces the old
    entities_vdb.query("the") approach: stop-word embeddings don't match
    concept embeddings well, so that query returned entities from unrelated
    documents rather than from the selected scope.
    """
    try:
        names = await rag.chunk_entity_relation_graph.get_popular_labels(limit=500)
    except Exception as exc:
        logger.warning("_list_entities_in_scope: get_popular_labels failed: %s", exc)
        names = []

    if not names:
        return []

    # Drop artifact IDs and figure-label entities before the batch fetch so
    # we don't burn the round-trip on nodes we'd discard anyway.
    names = [
        n for n in names
        if n
        and not is_artifact_id(n)
        and not is_figure_label_entity(n)
        and not is_instance_label_entity(n)
    ]
    if not names:
        return []

    try:
        node_map = await rag.chunk_entity_relation_graph.get_nodes_batch(names)
    except Exception as exc:
        logger.warning(
            "_list_entities_in_scope: get_nodes_batch failed: %s — "
            "falling back to name-only entities for scope filter.",
            exc,
        )
        node_map = {}

    filtered: List[dict] = []
    for n in names:
        e = {"entity_name": n, **(node_map.get(n) or {})}
        src = e.get("source_id", "")
        for cid in src.split(GRAPH_FIELD_SEP):
            if cid.strip() in scope_chunk_ids:
                filtered.append(e)
                break
    return filtered


async def _list_entities_unscoped(rag: "LightRAG", limit: int = 500) -> List[dict]:
    """Return artifact-filtered entities sourced directly from the graph.

    Used as a fallback by ``sample_seeds`` when ``_list_entities_in_scope``
    returns empty (the scope filter found nothing). Originally this fell
    back to ``entities_vdb.query("the", top_k=500)``, but on real
    corpora that similarity query returned only one or two entities —
    stop-word embeddings don't match concept embeddings well.

    Instead we ask the graph storage for the most-connected entities via
    ``get_popular_labels`` (degree-ranked, much more reliable), then
    fetch their full node data in a single batch call so the diversity
    rule downstream has ``source_id`` to work with.
    """
    try:
        names = await rag.chunk_entity_relation_graph.get_popular_labels(limit=limit)
    except Exception as exc:
        logger.warning(
            "_list_entities_unscoped: get_popular_labels failed: %s — "
            "falling back to entities_vdb.",
            exc,
        )
        names = []

    if not names:
        # Final fallback: try the VDB the old way. Won't help much on
        # corpora where stop-word queries are sparse, but no worse than
        # what we had before.
        try:
            results = await rag.entities_vdb.query("the", top_k=limit)
        except Exception as exc:
            logger.warning("_list_entities_unscoped: entities_vdb fallback failed: %s", exc)
            return []
        return [
            e for e in results
            if e.get("entity_name") and not is_artifact_id(e["entity_name"])
        ]

    # Drop artifact IDs and figure-label entities before batching so we
    # don't burn the get_nodes_batch round-trip on entities we're going
    # to discard anyway.
    names = [
        n for n in names
        if n
        and not is_artifact_id(n)
        and not is_figure_label_entity(n)
        and not is_instance_label_entity(n)
    ]
    if not names:
        return []

    try:
        node_map = await rag.chunk_entity_relation_graph.get_nodes_batch(names)
    except Exception as exc:
        logger.warning(
            "_list_entities_unscoped: get_nodes_batch failed: %s — "
            "returning name-only entities (diversity rule will skip them).",
            exc,
        )
        return [{"entity_name": n, "source_id": ""} for n in names]

    return [
        {"entity_name": n, **(node_map.get(n) or {})}
        for n in names
    ]


async def _list_chunks_in_scope(
    rag: "LightRAG",
    scope_doc_ids: Set[str],
) -> List[dict]:
    """Return all chunks belonging to selected docs.

    Reads chunk IDs deterministically from ``doc_status.chunks_list``
    (mirrors ``_get_scope_chunk_ids`` above) then resolves each chunk's
    content via ``chunks_vdb.get_by_ids``.  Replaces the previous broad
    ``chunks_vdb.query("the", top_k=500)`` approach: stop-word embeddings
    don't reliably match the in-scope chunks, which produced an empty
    seed pool → ``topic_N`` placeholders → single-chunk convergence and
    duplicate questions in quiz-44fbc845-….  See R6-1 in
    ``quiz-fix-plan.md``.
    """
    chunk_ids: Set[str] = set()
    for doc_id in scope_doc_ids:
        try:
            status = await rag.doc_status.get_by_id(doc_id)
        except Exception as exc:
            logger.warning(
                "_list_chunks_in_scope: doc_status.get_by_id(%s) failed: %s",
                doc_id,
                exc,
            )
            continue
        if not status:
            continue
        chunks_list = (
            status.get("chunks_list") if isinstance(status, dict)
            else getattr(status, "chunks_list", None)
        )
        if chunks_list:
            chunk_ids.update(c for c in chunks_list if c)

    if not chunk_ids:
        return []

    try:
        chunks = await rag.chunks_vdb.get_by_ids(list(chunk_ids))
        return [c for c in chunks if c is not None]
    except Exception as exc:
        logger.warning(
            "_list_chunks_in_scope: chunks_vdb.get_by_ids failed: %s", exc
        )
        return []


async def _scope_chunk_ids_by_doc(
    rag: "LightRAG", scope_doc_ids: Set[str]
) -> Dict[str, Set[str]]:
    """Return ``{doc_id: {chunk_id, …}}`` for the selected documents.

    Mirrors ``_get_scope_chunk_ids`` but keeps the per-document grouping so the
    pedagogical scorer can attribute each candidate to its owning file (needed
    for cross-doc presence and the Cap+Merit+Floor allocator).
    """
    out: Dict[str, Set[str]] = {}
    for doc_id in scope_doc_ids:
        try:
            status = await rag.doc_status.get_by_id(doc_id)
        except Exception as exc:
            logger.warning(
                "_scope_chunk_ids_by_doc: doc_status.get_by_id(%s) failed: %s",
                doc_id,
                exc,
            )
            continue
        if not status:
            continue
        chunks_list = (
            status.get("chunks_list") if isinstance(status, dict)
            else getattr(status, "chunks_list", None)
        )
        out[doc_id] = {c for c in (chunks_list or []) if c}
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def sample_seeds(
    rag: "LightRAG",
    mode: str,
    n: int,
    scope_doc_ids: set,
) -> SeedSelection:
    """Sample ``n`` seeds for a quiz, returning a :class:`SeedSelection`.

    Dispatches on ``QUIZ_SEED_STRATEGY`` (default ``pedagogical``). The
    pedagogical path falls back to the random baseline if it raises or yields
    no seeds, so a transient scoring failure never returns an empty quiz.
    """
    strategy_flag = os.environ.get("QUIZ_SEED_STRATEGY", "pedagogical").strip().lower()
    rng = _make_rng(scope_doc_ids, mode)

    if strategy_flag != "random":
        try:
            sel = await _sample_seeds_pedagogical(rag, mode, n, set(scope_doc_ids))
        except Exception as exc:
            logger.warning(
                "sample_seeds(%s): pedagogical selection failed (%s); "
                "falling back to random baseline.",
                mode,
                exc,
                exc_info=True,
            )
            sel = None
        # Honour the pedagogical result if it produced seeds OR if it ran
        # successfully and is authoritative (an empty result because the floor
        # legitimately emptied the pool — NOT a failure). Only a true failure
        # (scorer raised, or no candidates at all → non-authoritative empty)
        # falls back to the floor-less random baseline.
        if sel is not None and (sel.seeds or sel.authoritative):
            return sel
        logger.warning(
            "sample_seeds(%s): pedagogical selection found no candidates; "
            "falling back to random baseline.",
            mode,
        )

    return await _sample_seeds_random(rag, mode, n, set(scope_doc_ids), rng)


async def _build_scored_rows(
    rag: "LightRAG",
    mode: str,
    scope_doc_ids: Set[str],
) -> tuple[List[dict], str, Dict[str, str]]:
    """Build the scored (but not yet allocated) candidate rows for an arm.

    Returns ``(rows, strategy, chunk_to_doc)``. Shared by the pedagogical
    sampler and the Phase-4 ablation harness so both score candidates the same
    way.
    """
    by_doc = await _scope_chunk_ids_by_doc(rag, scope_doc_ids)
    chunk_to_doc: Dict[str, str] = {
        cid: doc for doc, cids in by_doc.items() for cid in cids
    }

    if mode == "mix":
        strategy = "entity-pedagogical"
        scope_chunk_ids = set(chunk_to_doc.keys())
        entities = await _list_entities_in_scope(rag, scope_doc_ids, scope_chunk_ids)
        if not entities:
            entities = await _list_entities_unscoped(rag)
            if entities:
                logger.warning(
                    "sample_seeds(mix, pedagogical): scope resolution returned no "
                    "entities (scope_chunk_ids=%d); falling back to %d unscoped "
                    "entities (cross-doc/contribution will be degraded).",
                    len(scope_chunk_ids),
                    len(entities),
                )
        if not entities:
            return [], strategy, chunk_to_doc
        rows = await scoring.score_mix(rag, entities, chunk_to_doc)
    else:
        strategy = "chunk-pedagogical"
        chunks = await _list_chunks_in_scope(rag, scope_doc_ids)
        if not chunks:
            return [], strategy, chunk_to_doc
        rows = scoring.score_naive(chunks, _first_sentence)

    return rows, strategy, chunk_to_doc


async def _fetch_seed_embeddings(
    rag: "LightRAG", mode: str, rows: List[dict]
) -> Dict[str, list]:
    """Fetch embedding vectors keyed by row ``key`` for the diversity pass.

    Mix rows are keyed by entity name → the entity VDB id is
    ``compute_mdhash_id(name, 'ent-')`` (quality-plan.md §11 trap #2). Naive
    rows are keyed by chunk id, which is already the chunk VDB id. Uses
    ``get_vectors_by_ids`` (``query``/``get_by_ids`` strip the vector — trap #1).
    Returns ``{}`` on any failure so diversify degrades to a no-op.
    """
    try:
        if mode == "mix":
            id_to_key = {
                compute_mdhash_id(r["key"], prefix="ent-"): r["key"]
                for r in rows
                if r.get("key")
            }
            if not id_to_key:
                return {}
            vecs = await rag.entities_vdb.get_vectors_by_ids(list(id_to_key))
            return {id_to_key[i]: v for i, v in (vecs or {}).items() if i in id_to_key}
        else:
            ids = [r["key"] for r in rows if r.get("key")]
            if not ids:
                return {}
            vecs = await rag.chunks_vdb.get_vectors_by_ids(ids)
            return dict(vecs or {})
    except Exception as exc:
        logger.warning(
            "sample_seeds(%s, pedagogical): embedding fetch for diversity failed "
            "(%s); skipping clustering-for-coverage.",
            mode,
            exc,
        )
        return {}


async def _apply_llm_rerank(
    rag: "LightRAG",
    mode: str,
    rows: List[dict],
    scope_doc_ids: Set[str],
) -> None:
    """Step 2: score the top-N candidates for educational importance and fold the
    result in as an extra RRF signal (re-rank only). Best-effort — any failure
    (no API key, API error) leaves the deterministic ranking untouched.
    """
    if not llm_importance.is_enabled():
        return
    base_signals = scoring.MIX_SIGNALS if mode == "mix" else scoring.NAIVE_SIGNALS
    top = sorted(rows, key=lambda r: r.get("rrf_score", 0.0), reverse=True)[
        : llm_importance.top_n()
    ]
    candidates = [
        (r["key"], (r.get("seed") or r.get("key") or ""))
        for r in top
        if r.get("key")
    ]
    if not candidates:
        return
    doc_set_key = "|".join(sorted(str(d) for d in scope_doc_ids))
    try:
        scores = await llm_importance.score_importance(
            candidates,
            doc_set_key=doc_set_key,
            working_dir=rag.working_dir,
        )
    except Exception as exc:
        logger.warning(
            "sample_seeds(%s): LLM re-rank failed (%s); deterministic ranking stands.",
            mode,
            exc,
        )
        return
    if scores:
        scoring.apply_llm_rerank(rows, base_signals, scores)
        logger.info(
            "sample_seeds(%s): applied LLM importance re-rank over %d candidates.",
            mode,
            len(scores),
        )


async def _sample_seeds_pedagogical(
    rag: "LightRAG",
    mode: str,
    n: int,
    scope_doc_ids: Set[str],
) -> SeedSelection:
    """RRF-scored, file-balanced, diversity-spread seed selection (§5-7)."""
    rows, strategy, _ = await _build_scored_rows(rag, mode, scope_doc_ids)

    if not rows:
        return SeedSelection(seeds=[], strategy=strategy)

    # Step 2 — LLM educational-importance re-rank (re-rank only; quality-plan.md
    # D4). Folds a semantic 1-10 importance score in as an extra RRF signal so
    # weak seeds the deterministic signals can't judge (title slides, filler,
    # snake_case table identifiers, instance labels) sink. Graceful no-op without
    # an API key. Runs only on the pedagogical path, so the random baseline and
    # the Phase-4 ablation control stay LLM-free.
    await _apply_llm_rerank(rag, mode, rows, scope_doc_ids)

    # Phase 3 — clustering-for-coverage. Embeddings are best-effort; on failure
    # diversify() is a no-op and allocate falls back to raw RRF order.
    embeddings = await _fetch_seed_embeddings(rag, mode, rows)
    if embeddings:
        scoring.diversify(rows, embeddings)
    else:
        logger.info(
            "sample_seeds(%s, pedagogical): no embeddings available; "
            "skipping clustering-for-coverage.",
            mode,
        )

    selected, contributions = scoring.allocate(rows, n, list(scope_doc_ids))
    selected = [r for r in selected if r.get("seed")]
    seeds = [r["seed"] for r in selected]
    seed_scores = [
        {
            "key": r.get("key", ""),
            "rrf_score": round(r.get("rrf_score", 0.0), 6),
            "ranks": r.get("ranks", {}),
        }
        for r in selected
    ]

    if len(seeds) < n:
        logger.info(
            "sample_seeds(%s, pedagogical): selected %d/%d seeds after floor+cap; "
            "honouring smaller quiz (no padding).",
            mode,
            len(seeds),
            n,
        )

    # Authoritative: candidates existed and were scored/allocated. Even an empty
    # result here is a real "nothing cleared the floor" outcome and must be
    # honoured rather than replaced by the random baseline.
    return SeedSelection(
        seeds=seeds,
        strategy=strategy,
        file_contributions=contributions,
        seed_scores=seed_scores,
        authoritative=True,
    )


async def _sample_seeds_random(
    rag: "LightRAG",
    mode: str,
    n: int,
    scope_doc_ids: Set[str],
    rng: random.Random,
) -> SeedSelection:
    """Legacy uniform-random baseline (quality-plan.md §8.3 ablation control)."""
    if mode == "mix":
        strategy = "entity"

        scope_chunk_ids = await _get_scope_chunk_ids(rag, scope_doc_ids)
        entities = await _list_entities_in_scope(rag, scope_doc_ids, scope_chunk_ids)

        # Fallback: when scope resolution returns an empty entity list, fall back
        # to artifact-filtered entities WITHOUT the scope check (retrieve_mix_arm
        # uses the same pattern). Without it, sample_seeds drops to ``topic_N``
        # placeholders and the duplicate-question collapse (quiz-bd12fd67) returns.
        if not entities:
            entities = await _list_entities_unscoped(rag)
            if entities:
                logger.warning(
                    "sample_seeds(mix): scope resolution returned no entities "
                    "(scope_chunk_ids=%d); falling back to %d unscoped entities.",
                    len(scope_chunk_ids),
                    len(entities),
                )

        if entities:
            # Diversity pass: no two seeds may share a primary source chunk.
            shuffled = rng.sample(entities, len(entities))
            chosen_names: List[str] = []
            used_chunks: set = set()
            for e in shuffled:
                name = e.get("entity_name", "")
                if not name:
                    continue
                chunk = _primary_source_chunk(e)
                if chunk and chunk in used_chunks:
                    continue
                chosen_names.append(name)
                if chunk:
                    used_chunks.add(chunk)
                if len(chosen_names) == n:
                    break

            if chosen_names:
                if len(chosen_names) < n:
                    logger.warning(
                        "sample_seeds(mix): only %d chunk-distinct entity seeds "
                        "available for n=%d; padding with replacement.",
                        len(chosen_names),
                        n,
                    )
                    pool_names = [
                        e.get("entity_name", "") for e in entities if e.get("entity_name")
                    ]
                    while len(chosen_names) < n and pool_names:
                        chosen_names.append(rng.choice(pool_names))
                return SeedSelection(seeds=chosen_names, strategy=strategy)

        seeds = [f"topic_{i+1}" for i in range(n)]
        return SeedSelection(seeds=seeds, strategy=strategy)

    else:
        strategy = "chunk"

        chunks = await _list_chunks_in_scope(rag, scope_doc_ids)

        if chunks:
            sampled = rng.sample(chunks, min(n, len(chunks)))
            seeds_list = [
                _first_sentence(c.get("content", f"topic_{i+1}"))
                for i, c in enumerate(sampled)
            ]
            if len(seeds_list) < n:
                logger.warning(
                    "sample_seeds(naive): only %d distinct chunks available "
                    "for n=%d; padding with replacement.",
                    len(seeds_list),
                    n,
                )
            while len(seeds_list) < n:
                c = rng.choice(chunks)
                seeds_list.append(_first_sentence(c.get("content", "topic")))
            return SeedSelection(seeds=seeds_list, strategy=strategy)

        seeds = [f"topic_{i+1}" for i in range(n)]
        return SeedSelection(seeds=seeds, strategy=strategy)

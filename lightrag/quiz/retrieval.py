"""
Difficulty-aware retrieval for the quiz pipeline.

Three retrieval variants:
  1. mix arm (thesis-rigorous) — custom BFS over chunk_entity_relation_graph
  2. naive arm (thesis-rigorous) — controlled top-k chunk retrieval
  3. fallback (local/global/hybrid) — coarse top_k scaling, NOT thesis-rigorous

Phase 1: All functions are stubs returning empty RetrievalContext objects.
Phase 3: Full BFS and scoped retrieval implementation.

See §3.2 of quiz-plan.md and §Graph Retrieval Controller in
claude_review_rag_framework.md for the locked decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Set

from lightrag.constants import GRAPH_FIELD_SEP
from lightrag.quiz.artifacts import is_artifact_id, redact_instance_labels

if TYPE_CHECKING:
    from lightrag import LightRAG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RetrievalContext — carries everything the generator needs
# ---------------------------------------------------------------------------


@dataclass
class RetrievalContext:
    """Structured retrieval result for a single question seed."""

    # Graph-arm fields (mix)
    entities: List[dict] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)
    bfs_path: List[str] = field(default_factory=list)
    hop_depth: Optional[int] = None

    # Shared fields
    chunks: List[dict] = field(default_factory=list)
    chunk_count: int = 0

    # Provenance
    source_documents: List[str] = field(default_factory=list)
    seed_query: str = ""

    def is_empty(self) -> bool:
        return not self.chunks and not self.entities

    def format_for_prompt(self) -> str:
        """Serialize context for the generator using a pedagogical layout.

        The previous format emitted a graph-database-style listing
        (``=== Entities ===``, ``=== Relations ===``, arrow notation) that
        encouraged extractive questions because the generator was being
        handed a graph, not a teaching outline. This version reformats the
        same retrieval into three pedagogical sections:

          - **Key concepts**: concept-entity descriptions with instance
            labels redacted (``Thread 1`` → ``{thread}``, ``P1`` →
            ``{process}``, etc.).
          - **Conceptual relationships**: relation descriptions, redacted.
          - **Supporting context**: prose chunks, redacted.

        Structural artifacts (``tb-…``, ``im-…``, ``mm-…`` entities and
        relations whose description is "associated with table/drawing in
        section…") are filtered out *before* the truncation cap so the cap
        reflects kept content, not raw count.

        An earlier version (R3) prepended a ``=== Topic ===`` line
        derived from source filenames. It was removed in R4 because
        GPT-4o-mini was generating meta-questions about the *documents*
        themselves (e.g. "What types of documents are covered?") rather
        than the subject matter — see ``quiz-caaf0e4a-…`` for evidence.

        Applied identically to mix-arm and naive-arm retrieval — the only
        permitted asymmetry between the arms is in retrieval itself.
        """
        parts: list[str] = []

        # ---- Key concepts ----
        concept_entities = [
            e for e in self.entities
            if not is_artifact_id(e.get("entity_name", ""))
        ]
        if concept_entities:
            parts.append("\n=== Key concepts ===")
            for e in concept_entities[:20]:
                raw_name = e.get("entity_name", e.get("id", "?"))
                desc = e.get("description", "")
                name = redact_instance_labels(raw_name)
                desc = redact_instance_labels(desc)
                parts.append(f"- {name}: {desc}" if desc else f"- {name}")

        # ---- Conceptual relationships ----
        concept_relations = [r for r in self.relations if not _is_structural_relation(r)]
        if concept_relations:
            parts.append("\n=== Conceptual relationships ===")
            for r in concept_relations[:20]:
                rel_text = self._format_relation(r)
                if rel_text:
                    parts.append(f"- {rel_text}")

        # ---- Supporting context ----
        if self.chunks:
            parts.append("\n=== Supporting context ===")
            for i, c in enumerate(self.chunks[:10]):
                content = c.get("content", c.get("text", ""))
                redacted = redact_instance_labels(content[:1500])
                parts.append(f"[Passage {i+1}]\n{redacted}")

        if not parts:
            return "(no context retrieved)"

        return "\n".join(parts)

    @staticmethod
    def _format_relation(r: dict) -> str:
        """Render a relation as a redacted conceptual sentence.

        Prefers the relation's natural-language ``description`` field;
        falls back to an arrow representation when no description is
        recorded. Instance labels are redacted in both forms so the
        generator can't latch onto specific labels.
        """
        desc = (r.get("description") or "").strip()
        if desc:
            return redact_instance_labels(desc)
        src = r.get("source", "?")
        tgt = r.get("target", "?")
        rel = r.get("type", r.get("relation", "relates to"))
        return redact_instance_labels(f"{src} {rel} {tgt}")


# ---------------------------------------------------------------------------
# Structural-relation detection (for pedagogical formatter)
# ---------------------------------------------------------------------------


_STRUCTURAL_DESC_FRAGMENTS = (
    "associated with table",
    "associated with drawing",
    "contained in section",
)


def _is_structural_relation(r: dict) -> bool:
    """True for relations that describe document structure, not concepts.

    The KG extractor emits relations like *"X is associated with table Y in
    section Z of document foo.pptx"* — these anchor entities to multimodal
    artifacts and are useless (worse, harmful) as pedagogical context.
    Drop them before the prompt sees them.
    """
    desc = (r.get("description") or "").lower()
    if any(p in desc for p in _STRUCTURAL_DESC_FRAGMENTS):
        return True
    if is_artifact_id(r.get("source", "")) or is_artifact_id(r.get("target", "")):
        return True
    return False


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def _entity_in_scope(entity_dict: dict, scope_chunk_ids: Set[str]) -> bool:
    """Return True if any of the entity's source chunk IDs are in scope."""
    src = entity_dict.get("source_id", "")
    for cid in src.split(GRAPH_FIELD_SEP):
        if cid.strip() in scope_chunk_ids:
            return True
    return False


def _entity_node_in_scope(node_data: dict, scope_chunk_ids: Set[str]) -> bool:
    """Return True if any of the graph node's source chunk IDs are in scope."""
    src = node_data.get("source_id", "")
    for cid in src.split(GRAPH_FIELD_SEP):
        if cid.strip() in scope_chunk_ids:
            return True
    return False


async def _get_scope_chunk_ids(rag: "LightRAG", scope_doc_ids: Set[str]) -> Set[str]:
    """Build the set of chunk IDs that belong to the given document IDs.

    Reads ``chunks_list`` directly from ``doc_status`` (deterministic).
    The previous broad-query approach returned an empty set on real
    corpora because stop-word embeddings don't reliably surface in-scope
    chunks — see the matching helper in ``lightrag/quiz/seeds.py``.
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
        chunks_list = (
            status.get("chunks_list") if isinstance(status, dict)
            else getattr(status, "chunks_list", None)
        )
        if chunks_list:
            chunk_ids.update(c for c in chunks_list if c)
    return chunk_ids


# ---------------------------------------------------------------------------
# BFS subgraph (Phase 3: real graph traversal)
# ---------------------------------------------------------------------------


async def _bfs_subgraph(
    rag: "LightRAG",
    start_nodes: List[str],
    max_depth: int,
    per_depth_cap: int,
    scope_chunk_ids: Set[str],
) -> tuple[List[dict], List[dict], List[str]]:
    """BFS over the knowledge graph.  Returns (entities, relations, bfs_path).

    Traverses up to max_depth hops from each start node, collecting neighbouring
    graph nodes and edges that are within the document scope.  At each depth the
    frontier is ranked by node degree and capped at per_depth_cap to bound the
    context size.
    """
    visited: Set[str] = set(start_nodes)
    frontier: List[str] = list(start_nodes)
    all_entities: List[dict] = []
    all_relations: List[dict] = []
    bfs_path: List[str] = list(start_nodes)

    for _depth in range(max_depth):
        next_frontier: List[str] = []

        for node in frontier:
            try:
                edges = await rag.chunk_entity_relation_graph.get_node_edges(node)
            except Exception as exc:
                logger.warning("BFS get_node_edges(%s) failed: %s", node, exc)
                edges = None

            if not edges:
                continue

            for src, tgt in edges:
                neighbor = tgt if src == node else src
                if neighbor in visited:
                    continue

                # Defence-in-depth: skip multimodal anchor IDs entirely so
                # they don't pollute the entity list or bfs_path metadata.
                # The format_for_prompt filter would catch them too, but
                # cleaning them here keeps the BFS path readable.
                if is_artifact_id(neighbor):
                    continue

                # Scope check: node must have source chunks within scope
                try:
                    node_data = await rag.chunk_entity_relation_graph.get_node(neighbor)
                except Exception as exc:
                    logger.warning("BFS get_node(%s) failed: %s", neighbor, exc)
                    continue

                if node_data is None:
                    continue

                if scope_chunk_ids and not _entity_node_in_scope(node_data, scope_chunk_ids):
                    continue

                visited.add(neighbor)
                next_frontier.append(neighbor)
                bfs_path.append(neighbor)

                # Collect the edge
                try:
                    edge_data = await rag.chunk_entity_relation_graph.get_edge(src, tgt)
                except Exception as exc:
                    logger.warning("BFS get_edge(%s, %s) failed: %s", src, tgt, exc)
                    edge_data = None

                if edge_data:
                    all_relations.append({"source": src, "target": tgt, **edge_data})

        # Rank frontier by degree and cap
        degrees: dict[str, int] = {}
        for n in next_frontier:
            try:
                degrees[n] = await rag.chunk_entity_relation_graph.node_degree(n)
            except Exception:
                degrees[n] = 0

        next_frontier.sort(key=lambda n: degrees.get(n, 0), reverse=True)
        frontier = next_frontier[:per_depth_cap]

        # Collect entity data for the new frontier
        for node in frontier:
            try:
                node_data = await rag.chunk_entity_relation_graph.get_node(node)
            except Exception as exc:
                logger.warning("BFS get_node(%s) for collection failed: %s", node, exc)
                continue
            if node_data:
                all_entities.append({"entity_name": node, **node_data})

    return all_entities, all_relations, bfs_path


# ---------------------------------------------------------------------------
# Mix arm — thesis-rigorous (custom BFS)
# ---------------------------------------------------------------------------


async def retrieve_mix_arm(
    rag: "LightRAG",
    seed_query: str,
    difficulty: str,
    scope_doc_ids: Set[str],
) -> RetrievalContext:
    """Custom BFS retrieval for the graph/mix arm.

    Difficulty → hop depth:
      easy   → 1 hop
      medium → 2 hops
      hard   → 3 hops

    Vector chunks are held constant at 5 across all difficulties so that
    difficulty signal is attributable to graph depth, not chunk volume.
    (Locked decision — see framework §3.2.)
    """
    hops = {"easy": 1, "medium": 2, "hard": 3}[difficulty]
    VECTOR_CHUNKS_CONSTANT = 5
    PER_DEPTH_CAP = 5

    # 1. Build scope chunk ID set
    scope_chunk_ids = await _get_scope_chunk_ids(rag, scope_doc_ids)

    # 2. Query entity VDB with the seed to find entry-point entities
    try:
        entry_results = await rag.entities_vdb.query(seed_query, top_k=20)
    except Exception as exc:
        logger.warning("retrieve_mix_arm: entities_vdb.query failed: %s", exc)
        entry_results = []

    # Drop multimodal-anchor synthetic entities (tb-/im-/mm-…) from the
    # entry-point pool before scoping or capping. Without this, an artifact
    # entity ranked highly by the entity VDB ends up as a BFS start node
    # and pollutes the bfs_path metadata even though the BFS-expansion
    # filter would have rejected it as a neighbour.
    entry_results = [
        e for e in entry_results if not is_artifact_id(e.get("entity_name", ""))
    ]

    # Filter to in-scope entities only
    if scope_chunk_ids:
        entry_entities = [
            e for e in entry_results if _entity_in_scope(e, scope_chunk_ids)
        ][:PER_DEPTH_CAP]
    else:
        # If scope resolution failed, use all returned entities
        entry_entities = entry_results[:PER_DEPTH_CAP]

    # 3. BFS from entry-point entity names
    start_nodes = [e["entity_name"] for e in entry_entities if e.get("entity_name")]
    if start_nodes:
        subgraph_entities, subgraph_relations, bfs_path = await _bfs_subgraph(
            rag, start_nodes, hops, PER_DEPTH_CAP, scope_chunk_ids
        )
    else:
        subgraph_entities, subgraph_relations, bfs_path = [], [], []

    # Prepend entry entities to the entity list (they are the depth-0 nodes)
    all_entities = entry_entities + subgraph_entities

    # 4. Fetch chunks referenced by the entity source_ids (graph-linked chunks)
    entity_chunk_ids: Set[str] = set()
    for e in all_entities:
        src = e.get("source_id", "")
        for cid in src.split(GRAPH_FIELD_SEP):
            cid = cid.strip()
            if cid and (not scope_chunk_ids or cid in scope_chunk_ids):
                entity_chunk_ids.add(cid)

    entity_chunks: List[dict] = []
    if entity_chunk_ids:
        try:
            entity_chunks = await rag.chunks_vdb.get_by_ids(list(entity_chunk_ids))
            # get_by_ids may return None entries for missing IDs; filter those out
            entity_chunks = [c for c in entity_chunks if c is not None]
        except Exception as exc:
            logger.warning(
                "retrieve_mix_arm: chunks_vdb.get_by_ids failed: %s", exc
            )
            entity_chunks = []

    # 5. Add VECTOR_CHUNKS_CONSTANT additional vector chunks (scope-filtered)
    try:
        extra_results = await rag.chunks_vdb.query(
            seed_query, top_k=VECTOR_CHUNKS_CONSTANT * 3
        )
        extra_chunks = [
            c for c in extra_results if c.get("full_doc_id") in scope_doc_ids
        ][:VECTOR_CHUNKS_CONSTANT]
    except Exception as exc:
        logger.warning("retrieve_mix_arm: chunks_vdb.query for extra chunks failed: %s", exc)
        extra_chunks = []

    # Deduplicate by chunk id: entity-linked chunks take priority
    seen_ids: Set[str] = {c.get("id", "") for c in entity_chunks if c.get("id")}
    deduped_extra = [c for c in extra_chunks if c.get("id", "") not in seen_ids]
    all_chunks = entity_chunks + deduped_extra

    return RetrievalContext(
        entities=all_entities,
        relations=subgraph_relations,
        bfs_path=bfs_path,
        hop_depth=hops,
        chunks=all_chunks,
        chunk_count=len(all_chunks),
        source_documents=list(scope_doc_ids),
        seed_query=seed_query,
    )


# ---------------------------------------------------------------------------
# Naive arm — thesis-rigorous (controlled chunk-k)
# ---------------------------------------------------------------------------


async def retrieve_naive_arm(
    rag: "LightRAG",
    seed_query: str,
    difficulty: str,
    scope_doc_ids: Set[str],
) -> RetrievalContext:
    """Naive vector retrieval with controlled k for the naive arm.

    Difficulty → chunk count:
      easy   → 1 chunk
      medium → 2 chunks
      hard   → 3 chunks

    (Locked decision — see framework §3.2.)
    """
    k = {"easy": 1, "medium": 2, "hard": 3}[difficulty]

    try:
        # Overscan by 10x to ensure enough in-scope results after filtering
        results = await rag.chunks_vdb.query(seed_query, top_k=k * 10)
        chunks = [
            c for c in results if c.get("full_doc_id") in scope_doc_ids
        ][:k]
    except Exception as exc:
        logger.warning("retrieve_naive_arm: chunks_vdb.query failed: %s", exc)
        chunks = []

    return RetrievalContext(
        chunks=chunks,
        chunk_count=len(chunks),
        source_documents=list(scope_doc_ids),
        seed_query=seed_query,
    )


# ---------------------------------------------------------------------------
# Fallback — coarse top_k scaling (not thesis-rigorous)
# ---------------------------------------------------------------------------


async def retrieve_fallback(
    rag: "LightRAG",
    seed_query: str,
    mode: str,
    difficulty: str,
    scope_doc_ids: Set[str],
) -> RetrievalContext:
    """Coarse top_k scaling for local/global/hybrid modes.

    NOT thesis-rigorous.  The frontend tooltip warns users about this.

    Difficulty → chunk_top_k:
      easy   → 3
      medium → 5
      hard   → 10
    """
    chunk_top_k = {"easy": 3, "medium": 5, "hard": 10}[difficulty]

    try:
        results = await rag.chunks_vdb.query(seed_query, top_k=chunk_top_k * 3)
        chunks = [
            c for c in results if c.get("full_doc_id") in scope_doc_ids
        ][:chunk_top_k]
    except Exception as exc:
        logger.warning(
            "retrieve_fallback: chunks_vdb.query failed (mode=%s): %s", mode, exc
        )
        chunks = []

    return RetrievalContext(
        chunks=chunks,
        chunk_count=len(chunks),
        source_documents=list(scope_doc_ids),
        seed_query=seed_query,
    )

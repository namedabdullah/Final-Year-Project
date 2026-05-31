"""
Pedagogical seed scoring for the quiz pipeline (quality-plan.md, Phases 1-2).

This module turns a pool of *candidate* seeds (graph entities for the mix arm,
chunks for the naive arm) into a *ranked, de-duplicated, file-balanced* seed set
using:

  - **RRF (Reciprocal Rank Fusion)** to combine heterogeneous signals without
    normalising incommensurable scales (quality-plan.md §5.1, decision D2). This
    replaces the broken weighted-sum (``0.4*centrality + 0.2*frequency + …``)
    whose terms lived on different scales.
  - **Cap + Merit + Floor** allocation (quality-plan.md §6) so contribution is
    *earned* not *assigned*: a file with nothing meaningful contributes zero.

Hard separation of arms (quality-plan.md §0):
  - ``score_mix``  may use graph machinery (degree, cross-doc, frequency).
  - ``score_naive`` may use *only* content/vector signals — **never** the graph.

Everything here is deterministic given its inputs (no RNG, no clock), so the
RRF/allocate core is unit-testable without a database.
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Callable, Dict, List, Optional, Sequence, Set

import numpy as np

from lightrag.constants import GRAPH_FIELD_SEP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunable parameters (quality-plan.md §14 — defaults; calibrated in Phase 4)
# ---------------------------------------------------------------------------

_RRF_K = int(os.environ.get("QUIZ_RRF_K", "60"))
_CAP_FRACTION = float(os.environ.get("QUIZ_FILE_CAP_FRACTION", "0.40"))
_HUB_PERCENTILE = float(os.environ.get("QUIZ_HUB_PERCENTILE", "0.90"))
_HUB_PENALTY = float(os.environ.get("QUIZ_HUB_PENALTY", "0.5"))
_HUB_HARD_EXCLUDE = os.environ.get("QUIZ_HUB_HARD_EXCLUDE", "false").lower() == "true"
_MIN_ENTITY_DEGREE = int(os.environ.get("QUIZ_MIN_ENTITY_DEGREE", "0"))
_MIN_CHUNK_DENSITY = float(os.environ.get("QUIZ_MIN_CHUNK_DENSITY", "0.0"))
# Step 1 (suggestions.md A1): exclude bare figure/table anchor chunks from the
# naive *seed* pool by default. This is seed selection, NOT retrieval filtering
# — naive retrieval still spans the full (table-inclusive) chunk space, so the
# arm stays methodologically "naive". May shrink a naive quiz below N when the
# corpus is anchor-dominated; that smaller quiz is honoured (no padding) and is
# itself a reportable finding.
_NAIVE_EXCLUDE_ANCHORS = (
    os.environ.get("QUIZ_NAIVE_EXCLUDE_ANCHORS", "true").lower() == "true"
)
# Minimum content-token count (alphabetic 2+ char tokens) for a chunk to be a
# seed — rejects the shortest title/divider stubs ("CSC 323 … Instructor:").
# Kept deliberately LOW: token count cannot reliably separate terse-but-teachable
# slide bullets ("TLB caches page table entries.") from filler, so a high floor
# would over-prune. Calibrate against the corpus chunk-token histogram in
# Phase 4 (quality-plan.md §14); the Step-2 LLM layer is the real filter for
# low-value-but-long chunks.
_MIN_CHUNK_TOKENS = int(os.environ.get("QUIZ_MIN_CHUNK_TOKENS", "5"))
# Max prose tokens that may precede an embedded artifact tag before the chunk is
# still treated as artifact-dominated (an "embedded anchor"). A chunk with more
# real prose than this ahead of the table/drawing is kept. Keeps the embedded-
# anchor rule HIGH-PRECISION (minimises over-pruning of prose-with-a-figure).
_MAX_PROSE_BEFORE_ARTIFACT = int(os.environ.get("QUIZ_MAX_PROSE_BEFORE_ARTIFACT", "8"))
# Cosine similarity at/above which two seed candidates are treated as the same
# topic cluster (quality-plan.md §7.1). Calibrated in Phase 4.
_DIVERSITY_SIM_THRESHOLD = float(
    os.environ.get("QUIZ_DIVERSITY_SIM_THRESHOLD", "0.6")
)

# Signal sets per arm (also the RRF fusion keys).
MIX_SIGNALS = ("deg", "xdoc", "freq")
NAIVE_SIGNALS = ("prose", "density", "explan")

# Explanatory connectives — a *heuristic* concept-teaching signal for the naive
# arm (quality-plan.md §5.3). Validated on-corpus in Phase 4; the signal simply
# contributes nothing to RRF if it never fires.
_CONNECTIVES = (
    "is defined as",
    "defined as",
    "refers to",
    "because",
    "therefore",
    "consists of",
    "unlike",
    "compared to",
    "in contrast",
    "as a result",
    "due to",
    "known as",
    "that is",
    "in order to",
)

# A chunk whose content opens with a multimodal anchor marker, e.g.
# ``[Image Name] …`` / ``[Table Name] …``. These dominate the corpus (~75-80%)
# and make poor *seeds* (bare captions) even though they remain valid retrieval
# targets — see quality-plan.md §5.3 (down-rank as seed, not filter retrieval).
_ANCHOR_RE = re.compile(r"^\s*\[\s*(image|table|figure)\b", re.IGNORECASE)
# Embedded multimodal-artifact markup, e.g. `<table id="tb-<32hex>-0001">` or
# `<drawing id="im-<32hex>-0002">`. Catches chunks that open with a thin heading
# then embed the artifact as their real payload (which _ANCHOR_RE, leading-only,
# misses). `[^>]*?` stays inside the opening tag and is robust to attribute
# order/quoting.
_EMBEDDED_ARTIFACT_RE = re.compile(
    r"<\s*(?:table|drawing|image|figure)\b[^>]*?(?:tb|im|mm)-[0-9a-f]{32}",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-]+")
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_TITLECASE_PHRASE_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


# ---------------------------------------------------------------------------
# Generic RRF fusion + Cap/Merit/Floor allocation (pure functions)
# ---------------------------------------------------------------------------


def fuse_rrf(
    rows: List[dict],
    signal_keys: Sequence[str],
    *,
    k: int = _RRF_K,
    weights: Optional[Dict[str, float]] = None,
) -> None:
    """Assign ``rrf_score`` and ``ranks`` to each row in place.

    For each signal, rank rows by descending raw value (``rows[i]['signals'][s]``)
    giving rank 1, 2, 3, …; then ``rrf_score = Σ_s w_s / (k + rank_s)``.

    RRF consumes only *order*, so signals on different scales (degree int,
    cross-doc count, log-frequency) combine without normalisation, and
    correlated signals do not double-count as badly as in a linear sum.
    (quality-plan.md §5.1.)
    """
    if not rows:
        return
    weights = weights or {s: 1.0 for s in signal_keys}
    # Rank per signal. Use object identity to map back to rows (rows are
    # distinct dict instances; ties broken by stable sort order).
    rank_by_signal: Dict[str, Dict[int, int]] = {}
    for s in signal_keys:
        ordered = sorted(rows, key=lambda r: r.get("signals", {}).get(s, 0.0), reverse=True)
        rank_by_signal[s] = {id(r): i + 1 for i, r in enumerate(ordered)}
    for r in rows:
        ranks = {s: rank_by_signal[s][id(r)] for s in signal_keys}
        r["ranks"] = ranks
        r["rrf_score"] = sum(weights.get(s, 1.0) / (k + ranks[s]) for s in signal_keys)


def apply_llm_rerank(
    rows: List[dict],
    base_signals: Sequence[str],
    llm_scores: Dict[str, float],
) -> None:
    """Fold an LLM educational-importance score in as an extra RRF signal (Step 2).

    Re-rank ONLY: adds an ``llm`` signal and re-fuses RRF over
    ``base_signals + ['llm']`` in place. Nothing is dropped. Candidates the LLM
    did not score receive the *mean* of the provided scores (a neutral rank), so
    an un-judged candidate is neither boosted nor penalised. No-op when
    ``llm_scores`` is empty (e.g. no API key), leaving the deterministic ranking
    untouched. The mix anti-hub penalty is re-applied after the re-fuse.
    """
    if not rows or not llm_scores:
        return
    neutral = sum(llm_scores.values()) / len(llm_scores)
    for r in rows:
        r["signals"]["llm"] = float(llm_scores.get(r.get("key", ""), neutral))
    fuse_rrf(rows, list(base_signals) + ["llm"])
    for r in rows:
        if r.get("is_hub"):
            r["rrf_score"] *= _HUB_PENALTY


def allocate(
    rows: List[dict],
    n: int,
    scope_doc_ids: Sequence[str],
    *,
    cap_fraction: float = _CAP_FRACTION,
) -> tuple[List[dict], List[dict]]:
    """Cap + Merit + Floor allocation (quality-plan.md §6).

    Returns ``(selected_rows, file_contributions)`` where ``file_contributions``
    is a list of ``{"doc_id", "seed_count", "reason"}`` covering every scope doc.

    - **Merit**: rows are consumed in descending ``rrf_score``.
    - **Floor**: a row with ``meets_floor`` False is skipped; a file whose every
      candidate fails the floor contributes 0 (reason ``below_threshold``).
    - **Cap**: no file may exceed ``ceil(cap_fraction * n)`` seats in the first
      pass; a relaxed second pass fills any shortfall from remaining eligible
      rows (so available capacity is used rather than under-filling *because of*
      the cap). De-duplicates on ``dedup_key`` (primary chunk / chunk id) so two
      seeds never collapse to the same source — the anti-duplicate property that
      the old chunk-distinct rule provided, until clustering lands in Phase 3.
    - **No padding**: if the eligible pool is exhausted before ``n``, the quiz is
      honoured at the smaller size (quality-plan.md §6.1).
    """
    # Respect the diversified order when present (quality-plan.md §7.1):
    # `select_rank` is the round-robin-across-clusters position assigned by
    # diversify(). Falling back to raw RRF order when diversity did not run.
    if any("select_rank" in r for r in rows):
        ranked = sorted(rows, key=lambda r: r.get("select_rank", 10**9))
    else:
        ranked = sorted(rows, key=lambda r: r.get("rrf_score", 0.0), reverse=True)
    cap = max(1, math.ceil(cap_fraction * n)) if n > 0 else 0

    selected: List[dict] = []
    per_file: Dict[str, int] = {}
    blocked: Dict[str, str] = {}  # doc_id -> reason when it has 0 selected so far
    used_dedup: Set[str] = set()
    selected_ids: Set[int] = set()

    def _try_take(row: dict, enforce_cap: bool) -> bool:
        f = row.get("doc_id", "") or ""
        if not row.get("meets_floor", True):
            blocked.setdefault(f, "below_threshold")
            return False
        dk = row.get("dedup_key", "")
        if dk and dk in used_dedup:
            return False  # near-duplicate source; skip silently
        if enforce_cap and per_file.get(f, 0) >= cap:
            if per_file.get(f, 0) > 0:
                blocked.setdefault(f, "capped")
            return False
        selected.append(row)
        selected_ids.add(id(row))
        per_file[f] = per_file.get(f, 0) + 1
        if dk:
            used_dedup.add(dk)
        return True

    # Pass 1 — merit + floor + cap.
    for row in ranked:
        if len(selected) >= n:
            break
        _try_take(row, enforce_cap=True)

    # Pass 2 — relax the cap to use leftover capacity rather than under-fill.
    if len(selected) < n:
        for row in ranked:
            if len(selected) >= n:
                break
            if id(row) in selected_ids:
                continue
            _try_take(row, enforce_cap=False)

    # Build per-file contribution records (quality-plan.md §6.2).
    contributions: List[dict] = []
    for doc_id in scope_doc_ids:
        cnt = per_file.get(doc_id, 0)
        if cnt > 0:
            reason = "contributed"
        elif doc_id in blocked:
            reason = blocked[doc_id]
        else:
            reason = "outranked"
        contributions.append({"doc_id": doc_id, "seed_count": cnt, "reason": reason})

    return selected, contributions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


async def _entity_chunk_record(rag, entity_name: str) -> Optional[dict]:
    """Read the uncapped ``{chunk_ids, count}`` record for an entity.

    Prefers ``rag.entity_chunks`` (uncapped) over the graph node ``source_id``
    (capped at 300 FIFO — quality-plan.md §11 trap #4).
    """
    store = getattr(rag, "entity_chunks", None)
    if store is None:
        return None
    try:
        rec = await store.get_by_id(entity_name)
    except Exception as exc:  # pragma: no cover - storage edge
        logger.debug("entity_chunks.get_by_id(%s) failed: %s", entity_name, exc)
        return None
    return rec if isinstance(rec, dict) else None


def _source_chunks_from_entity(entity: dict) -> List[str]:
    src = entity.get("source_id", "") or ""
    return [c.strip() for c in src.split(GRAPH_FIELD_SEP) if c.strip()]


# ---------------------------------------------------------------------------
# Mix arm — entity scorer (graph machinery allowed)
# ---------------------------------------------------------------------------


async def score_mix(
    rag,
    entities: List[dict],
    chunk_to_doc: Dict[str, str],
) -> List[dict]:
    """Score graph entities for the mix arm (quality-plan.md §5.2).

    Signals: in-scope-subgraph ``deg``, cross-document presence ``xdoc``,
    log distinct-chunk ``freq``. Applies the anti-hub down-rank (over-general
    hubs like "System"/"Process" are prominence, not pedagogy).
    """
    name_set = {e.get("entity_name", "") for e in entities if e.get("entity_name")}
    rows: List[dict] = []

    for e in entities:
        name = e.get("entity_name", "")
        if not name:
            continue

        # In-scope degree: neighbours that are themselves in-scope entities.
        try:
            edges = await rag.chunk_entity_relation_graph.get_node_edges(name) or []
        except Exception as exc:
            logger.debug("score_mix: get_node_edges(%s) failed: %s", name, exc)
            edges = []
        neighbours: Set[str] = set()
        for s, t in edges:
            other = t if s == name else s
            if other != name and other in name_set:
                neighbours.add(other)
        degree = len(neighbours)

        # Frequency + cross-doc from the uncapped entity_chunks record (fallback
        # to graph source_id when the KV record is missing).
        rec = await _entity_chunk_record(rag, name)
        if rec and rec.get("chunk_ids"):
            source_chunks = [c for c in rec["chunk_ids"] if c]
            freq = int(rec.get("count") or len(source_chunks))
        else:
            source_chunks = _source_chunks_from_entity(e)
            freq = len(source_chunks)

        docs = {chunk_to_doc[c] for c in source_chunks if c in chunk_to_doc}
        xdoc = len(docs)
        primary = next((c for c in source_chunks if c in chunk_to_doc), "")
        if not primary and source_chunks:
            primary = source_chunks[0]
        doc_id = chunk_to_doc.get(primary, "") or (next(iter(docs)) if docs else "")

        rows.append(
            {
                "key": name,
                "seed": name,
                "doc_id": doc_id,
                "dedup_key": primary,
                "degree": degree,
                "signals": {
                    "deg": float(degree),
                    "xdoc": float(xdoc),
                    "freq": math.log1p(freq),
                },
            }
        )

    if not rows:
        return rows

    # Anti-hub guard (quality-plan.md §5.2): flag entities above the degree
    # percentile; down-rank (default) or hard-exclude them.
    degs = sorted(r["degree"] for r in rows)
    hub_threshold = _percentile([float(d) for d in degs], _HUB_PERCENTILE)
    for r in rows:
        r["is_hub"] = hub_threshold > 0 and r["degree"] > hub_threshold

    fuse_rrf(rows, MIX_SIGNALS)

    for r in rows:
        if r["is_hub"]:
            r["rrf_score"] *= _HUB_PENALTY
        r["meets_floor"] = (r["degree"] >= _MIN_ENTITY_DEGREE) and not (
            r["is_hub"] and _HUB_HARD_EXCLUDE
        )

    return rows


# ---------------------------------------------------------------------------
# Naive arm — chunk scorer (content/vector signals ONLY, never the graph)
# ---------------------------------------------------------------------------


def _is_embedded_anchor(content: str) -> bool:
    """True if a chunk's body is dominated by an embedded multimodal artifact.

    Catches chunks that open with a thin heading/number then embed the artifact
    markup as their real payload — e.g. ``# Example 3 <table id="tb-…">`` or
    ``# Linux bcc/BPF Tracing Tools <drawing id="im-…">`` — which ``_ANCHOR_RE``
    (leading ``[Image]``/``[Table]`` only) misses. High-precision: a chunk with
    substantial prose (``>= _MAX_PROSE_BEFORE_ARTIFACT`` content tokens) ahead of
    the artifact is kept, so genuine prose-with-a-figure is not over-pruned.
    """
    m = _EMBEDDED_ARTIFACT_RE.search(content or "")
    if not m:
        return False
    prose_before = len(_TOKEN_RE.findall(content[: m.start()]))
    return prose_before < _MAX_PROSE_BEFORE_ARTIFACT


def score_naive(
    chunks: List[dict],
    first_sentence: Callable[[str], str],
) -> List[dict]:
    """Score chunks for the naive arm (quality-plan.md §5.3).

    Content-only signals: ``prose`` (1.0 unless the chunk opens with an
    ``[Image/Table]`` anchor → 0.0), keyphrase ``density`` (length-normalised),
    and explanatory-connective ``explan``. **No graph signals** (§0 trap).
    """
    rows: List[dict] = []
    for c in chunks:
        content = c.get("content", c.get("text", "")) or ""
        cid = c.get("id", c.get("chunk_id", "")) or ""
        doc_id = c.get("full_doc_id", "") or ""

        is_anchor = bool(_ANCHOR_RE.match(content)) or _is_embedded_anchor(content)
        tokens = _TOKEN_RE.findall(content)
        n_tokens = len(tokens)
        ntok = max(1, n_tokens)
        density = (len(_ACRONYM_RE.findall(content)) + len(_TITLECASE_PHRASE_RE.findall(content))) / ntok
        lc = content.lower()
        explan = float(sum(1 for p in _CONNECTIVES if p in lc))

        rows.append(
            {
                "key": cid,
                "seed": first_sentence(content) if content else "",
                "doc_id": doc_id,
                "dedup_key": cid,
                "is_anchor": is_anchor,
                "density": density,
                "n_tokens": n_tokens,
                "signals": {
                    "prose": 0.0 if is_anchor else 1.0,
                    "density": density,
                    "explan": explan,
                },
            }
        )

    if not rows:
        return rows

    fuse_rrf(rows, NAIVE_SIGNALS)

    # Floor (Step 1): a seed chunk must be prose (not a bare anchor, unless
    # exclusion is disabled) and carry enough content tokens to be teachable
    # (rejects the shortest title/divider stubs). The density clause is OFF by
    # default (_MIN_CHUNK_DENSITY=0.0 ⇒ always passes); it only gates when a
    # non-zero QUIZ_MIN_CHUNK_DENSITY is set during Phase-4 calibration.
    for r in rows:
        r["meets_floor"] = (
            (not (r["is_anchor"] and _NAIVE_EXCLUDE_ANCHORS))
            and (r["n_tokens"] >= _MIN_CHUNK_TOKENS)
            and (r["density"] >= _MIN_CHUNK_DENSITY)
        )

    return rows


# ---------------------------------------------------------------------------
# Phase 3 — Clustering-for-coverage (diversity)
# ---------------------------------------------------------------------------


def cluster_by_cosine(
    keys: Sequence[str],
    vectors: Dict[str, Sequence[float]],
    threshold: float,
) -> List[List[str]]:
    """Greedy "leader" clustering by cosine similarity (no sklearn).

    Processes ``keys`` in the given order (callers pass RRF-descending order so
    the highest-scored candidate becomes each cluster's leader). A key joins the
    most-similar existing cluster if that similarity ≥ ``threshold``; otherwise
    it starts a new cluster. Deterministic given the input order.
    """
    normed: Dict[str, np.ndarray] = {}
    for k in keys:
        v = np.asarray(vectors[k], dtype=float)
        norm = float(np.linalg.norm(v))
        normed[k] = v / norm if norm > 0 else v

    leaders: List[np.ndarray] = []
    members: List[List[str]] = []
    for k in keys:
        vk = normed[k]
        best_idx, best_sim = -1, -1.0
        for i, lead in enumerate(leaders):
            sim = float(np.dot(vk, lead))
            if sim > best_sim:
                best_sim, best_idx = sim, i
        if best_idx >= 0 and best_sim >= threshold:
            members[best_idx].append(k)
        else:
            leaders.append(vk)
            members.append([k])
    return members


def diversify(
    rows: List[dict],
    embeddings: Dict[str, Sequence[float]],
    *,
    threshold: float = _DIVERSITY_SIM_THRESHOLD,
) -> None:
    """Assign ``select_rank`` to spread seeds across topic clusters (§7.1).

    Clusters the candidates by embedding, then lays them out round-robin across
    clusters (ordered by cluster pedagogical mass = Σ member RRF), so the top of
    the selection list spans distinct topics rather than piling onto the
    dominant cluster (e.g. the "burst-time table" family). ``allocate`` then
    consumes ``select_rank`` order.

    This re-orders rather than hard-prunes, so it cannot under-fill the quiz —
    sidestepping the over-prune failure mode (§7.3). No-op (leaves rows on raw
    RRF order) when fewer than two candidates have embeddings.
    """
    by_rrf = sorted(rows, key=lambda r: r.get("rrf_score", 0.0), reverse=True)
    embedded_keys = [r["key"] for r in by_rrf if r.get("key") in embeddings]
    if len(embedded_keys) < 2:
        return  # nothing to cluster; allocate falls back to RRF order

    row_by_key = {r["key"]: r for r in rows}
    clusters = cluster_by_cosine(
        embedded_keys, {k: embeddings[k] for k in embedded_keys}, threshold
    )
    # Candidates without an embedding become singleton clusters so they are
    # still ranked (after the embedded ones of equal mass).
    unembedded = [r["key"] for r in by_rrf if r.get("key") not in embeddings]
    all_clusters = clusters + [[k] for k in unembedded]

    def _mass(cluster: List[str]) -> float:
        return sum(row_by_key[k].get("rrf_score", 0.0) for k in cluster)

    all_clusters.sort(key=_mass, reverse=True)

    rank = 0
    max_depth = max((len(c) for c in all_clusters), default=0)
    for depth in range(max_depth):
        for cluster in all_clusters:
            if depth < len(cluster):
                row_by_key[cluster[depth]]["select_rank"] = rank
                rank += 1

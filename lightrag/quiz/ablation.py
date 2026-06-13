"""
Phase 4 — seed-scoring ablation & sensitivity harness (quality-plan.md §8.2).

With no ground-truth labels, the defence for the RRF signal set and its
(uniform) weights is *evidence of robustness*, not a tuned optimum. This module
produces that evidence deterministically, with **no LLM calls** — it only
compares the *seed sets* that different signal subsets / weightings select:

  - **Ablation**: drop each signal in turn, measure how much the selected seed
    set moves (Jaccard vs the full-signal set). A signal whose removal barely
    changes the set is not load-bearing; one that changes it a lot is.
  - **Sensitivity**: up-weight each signal and measure the same. If the seed set
    is stable across reasonable weights, "we used uniform weights" is defensible;
    if one weighting dominates, that is itself a reportable finding.

``run_ablation`` needs a live ``rag`` (to build the candidate rows from the
graph / vector store). The comparison primitives (``jaccard``,
``select_keys_for_signals``) are pure and unit-tested offline.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Set

from lightrag.quiz import scoring
from lightrag.quiz.seeds import _build_scored_rows

logger = logging.getLogger(__name__)


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Jaccard overlap of two key sets (1.0 when both empty)."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def select_keys_for_signals(
    rows: List[dict],
    signal_keys: Sequence[str],
    n: int,
    scope_doc_ids: Sequence[str],
    *,
    weights: Optional[Dict[str, float]] = None,
) -> List[str]:
    """Re-score ``rows`` with a given signal subset/weights and return the
    selected seed keys (RRF order; diversity is intentionally NOT applied so the
    ablation isolates the scoring signals). Operates on copies so the caller's
    rows are untouched.
    """
    copies = [
        {
            "key": r.get("key", ""),
            "seed": r.get("seed", ""),
            "doc_id": r.get("doc_id", ""),
            "dedup_key": r.get("dedup_key", ""),
            "meets_floor": r.get("meets_floor", True),
            "signals": dict(r.get("signals", {})),
        }
        for r in rows
    ]
    scoring.fuse_rrf(copies, list(signal_keys), weights=weights)
    selected, _ = scoring.allocate(copies, n, list(scope_doc_ids))
    return [r["key"] for r in selected]


async def run_ablation(
    rag,
    mode: str,
    n: int,
    scope_doc_ids: Set[str],
) -> dict:
    """Run the ablation + sensitivity study for one arm against a live index.

    Returns a report dict suitable for the thesis appendix.
    """
    rows, strategy, _ = await _build_scored_rows(rag, mode, set(scope_doc_ids))
    signal_keys = list(scoring.MIX_SIGNALS if mode == "mix" else scoring.NAIVE_SIGNALS)

    if not rows:
        return {"mode": mode, "strategy": strategy, "error": "no candidate rows"}

    full = select_keys_for_signals(rows, signal_keys, n, scope_doc_ids)

    ablation: Dict[str, dict] = {}
    for s in signal_keys:
        subset = [k for k in signal_keys if k != s]
        if not subset:
            continue
        sub = select_keys_for_signals(rows, subset, n, scope_doc_ids)
        ablation[s] = {
            "jaccard_vs_full": round(jaccard(full, sub), 4),
            "dropped": sorted(set(full) - set(sub)),
            "added": sorted(set(sub) - set(full)),
        }

    sensitivity: Dict[str, dict] = {}
    for s in signal_keys:
        weights = {k: (2.0 if k == s else 1.0) for k in signal_keys}
        swept = select_keys_for_signals(rows, signal_keys, n, scope_doc_ids, weights=weights)
        sensitivity[s] = {"weight": 2.0, "jaccard_vs_uniform": round(jaccard(full, swept), 4)}

    return {
        "mode": mode,
        "strategy": strategy,
        "candidate_pool_size": len(rows),
        "n": n,
        "full_signal_seed_count": len(full),
        "signals": signal_keys,
        "ablation": ablation,
        "sensitivity": sensitivity,
    }

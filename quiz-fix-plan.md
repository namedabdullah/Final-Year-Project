# Quiz Generator — Fix Plan for Over-Extractive Questions

> Companion document to `quiz-plan.md` and `claude_review_rag_framework.md`.
> Records what is being changed and why to move the quiz pipeline from a
> retrieval-driven graph dump into a concept-oriented educational
> generator suitable for student-facing production use.
>
> **Reference**: see also `suggestion.md` for the broader roadmap of
> ideas that were considered but deferred to Phase 2 / skipped.

---

## Context

### What prompted this plan

A 25-question quiz generated on 2026-05-28 (`quiz-50f66d4a-…json`, mix arm, easy difficulty, 12 OS-course documents) exhibited systematic over-extractive behaviour:

- **9/25** were diagram-label or table-cell lookups (e.g. *"What is the label of the fourth processor core?"* → `"core 3"`)
- **4/25** were verbatim duplicates of *"What is the purpose of memory management in computing?"*
- **3/25** were tautological (*"What is the label used to identify the execution path of Thread A?"* → `"Thread A"`)
- Several reference answers were single tokens (`"P1"`, `"40 seconds"`, `"C A B"`, `"Page 3"`) that are meaningless without the original figure

### Goals

The pipeline has **two** end-uses, and the plan must serve both:

1. **Production**: a student-facing quiz tool that reinforces concepts and supports learning. Questions must be pedagogically sound — testing understanding, not lookup ability.
2. **Thesis**: a clean comparison between mix-arm (graph BFS) and naive-arm (vector top-k) retrieval, to conclude which approach better supports educational generation.

Both goals are met when every generation-side improvement is applied **symmetrically** to both arms. Asymmetric changes contaminate the comparison; symmetric changes preserve it while improving output for both.

### Design principle: symmetric application

A rule that applies to every change in this plan:

> If a change touches the path between `RetrievalContext` and the LLM call,
> it must be applied identically to the mix arm and the naive arm. The only
> permitted asymmetry is in retrieval itself (BFS vs. vector top-k) — that
> is the variable being measured.

This rule lets us aggressively improve generation quality without sacrificing the thesis conclusion.

### Intended outcome

Questions that reference concepts (*process*, *semaphore*, *critical section*, *memory page*) rather than labels of instances in a specific figure (`P1`, `Thread A`, `core 3`), with no verbatim duplicates within a single quiz, and reference answers that stand alone as conceptual statements.

---

## Issues — one-line recap

| # | Issue | Layer | Addressed in |
|---|-------|-------|--------------|
| 1 | Seeds include multimodal artifact IDs (`tb-…`, `im-…`, `mm-…`) | Input | Phase 1 — A |
| 2 | Retrieval context dominated by "associated with table/drawing in section" relations | Retrieval | Phase 1 — A |
| 3 | Easy prompt explicitly rewards single-fact / single-token answers | Prompt | Phase 1 — B |
| 4 | Instance labels (`Thread A`, `P1`, `core 3`) treated as concept entities | KG / Prompt | Phase 1 — B+1 |
| 5 | No cross-seed deduplication; overlapping retrieval collapses to identical questions | Orchestration | Phase 1 — B+2 |
| 6 | Reference answers are single tokens with no rationale | Consequence of #3 | Phase 1 — B |
| 7 | `RetrievalContext.format_for_prompt()` emits graph-database-style listings instead of pedagogical context | Formatter | Phase 1 — B+1 |
| 8 | Verifier marks label-extraction questions as passing; no signal on figure-dependency | Verifier | Phase 1 — B+3 (diagnostic only) |

---

## Phase 1 — Production-Ready Foundation (DO FIRST)

The non-negotiable layer. Each step is mechanical or prompt-level; no methodology-confounding architecture changes; full symmetric application.

### Tier A — Artifact cleanup (no methodology change)

Addresses issues 1, 2, partly 4.

#### A1. Artifact-ID filter utility

**New file**: `lightrag/quiz/artifacts.py`

```python
"""Detection helpers for multimodal artifact entity IDs.

The KG extractor creates synthetic entities for tables (`tb-…`), images
and drawings (`im-…`), and other multimodal anchors (`mm-…`). These are
structural anchors, not pedagogical concepts. The quiz pipeline must not
seed off them or expose them to the generator as concepts.
"""

import re

# tb-<32 hex>-<4 digit slot>  /  im-<32 hex>-<4 digit slot>  /  mm-…
_ARTIFACT_ID_RE = re.compile(r"^(tb|im|mm)-[0-9a-f]{32}-\d{4}$")

def is_artifact_id(name: str) -> bool:
    """True if `name` looks like a multimodal-anchor synthetic entity ID."""
    return bool(_ARTIFACT_ID_RE.match(name or ""))
```

A prior exploration confirmed no such utility exists anywhere in the repo — it must be created fresh, not reused.

#### A2. Wire the filter into seed sampling

**Modify**: `lightrag/quiz/seeds.py:_list_entities_in_scope` (currently lines 58-81)

After the existing scope filter, drop entities whose `entity_name` is an artifact ID. In the loop at line 75-80, add:

```python
if is_artifact_id(e.get("entity_name", "")):
    continue
```

Chunks don't have artifact IDs, so only the entity branch needs it.

#### A3. Wire the filter into retrieval context formatting

**Modify**: `lightrag/quiz/retrieval.py:RetrievalContext.format_for_prompt` (lines 56-84)

Skip entities whose `entity_name` matches `is_artifact_id`. Skip relations whose `source` or `target` matches `is_artifact_id`, **and** skip relations whose `description` matches any of:

- `"associated with table"`
- `"associated with drawing"`
- `"contained in section"`

These descriptions are produced verbatim by the multimodal anchor relation builder; matching by substring is sufficient and stable.

```python
def _is_structural_relation(r: dict) -> bool:
    desc = (r.get("description") or "").lower()
    if any(p in desc for p in (
        "associated with table",
        "associated with drawing",
        "contained in section",
    )):
        return True
    if is_artifact_id(r.get("source", "")) or is_artifact_id(r.get("target", "")):
        return True
    return False
```

Apply this inside `format_for_prompt` before the truncate-to-20 cap so the cap reflects *kept* relations rather than the raw count.

#### A4. Apply the filter at BFS time (defence in depth)

**Modify**: `lightrag/quiz/retrieval.py:_bfs_subgraph` (around line 162-192)

Skip neighbours that are artifact IDs so they never enter the entity list or `bfs_path`. A3 catches them at the prompt boundary; A4 also cleans the `bfs_path` recorded in metadata. Low-risk one-liner.

---

### Tier B — Prompt sharpening

Addresses issues 3, 4, 6. Builds on Tier A.

#### B1. Bump prompt version IDs

**Modify**: `lightrag/quiz/generation.py:37-41`

```python
PROMPT_TEMPLATE_IDS = {
    "easy":   "easy_v2",
    "medium": "medium_v2",
    "hard":   "hard_v2",
}
```

The `GenerationMetadata.prompt_template_id` field (`schemas.py:92`) is the *only* place these flow into; the schema doesn't need a separate `prompt_version` field. Old quizzes keep their `easy_v1`/etc. IDs and remain traceable to the original framework-doc prompts.

#### B2. Update the three prompt strings

**Modify**: `lightrag/quiz/generation.py:_PROMPT_TEMPLATES` (lines 44-83)

Add to **all three** templates a new "Avoid" block immediately before the `Return valid JSON…` line:

```
Avoid (CRITICAL):
- Do NOT ask about diagram labels, table cell values, figure identifiers,
  or instance names (e.g., "P1", "Thread A", "core 3", "CPU_7", "Page 3").
- Do NOT ask "what is the label of…" or "what is the name of the … in the diagram".
- Reference the underlying concept (e.g., "process", "thread", "CPU core",
  "memory page"), not the specific label the figure uses for one instance.
- The reference_answer must be a conceptual statement, not a single
  token, table cell, or figure label.
- If the question would not make sense to a student without seeing the
  original figure, REWRITE it so it does.
```

The final bullet is the verifier heuristic from `suggestion.md` §4 ("would this question still make sense if the original diagram were removed?") promoted into the generator prompt where it actively shapes output.

For **easy** specifically, soften the "single fact, name, number, or short phrase" wording (line 53) to:

```
- The answer should be a single short conceptual statement (one sentence)
  drawn directly from the context, not a verbatim table cell or label.
```

For **medium** and **hard**, no rewording of the existing constraints — only the Avoid block is added.

> **Easy/medium boundary watch**: keep easy questions *factual but conceptual* (e.g. *"What problem does a semaphore solve?"* → *"It coordinates access to shared resources between concurrent threads."*). Do not let easy drift into causal reasoning (*"Why might a semaphore be initialized to 1?"*) — that's medium territory. The line is "single-fact conceptual statement" vs. "multi-step reasoning."

#### B3. Record the revision in the framework doc

**Modify**: `claude_review_rag_framework.md` §Easy Prompt / §Medium Prompt / §Hard Prompt (lines 396-431).

Replace each prompt block with the updated text, and add a short revision note immediately under the heading:

```
> **Revision v2 (2026-05-28)**: Added explicit anti-pattern guidance to
> avoid diagram-label and table-cell extraction questions; promoted the
> figure-independence heuristic into the prompt. Original v1 text
> preserved in git history. Quiz records produced before this date
> remain tagged `easy_v1`/`medium_v1`/`hard_v1` for traceability.
```

#### B4. Note in `quiz-plan.md`

**Modify**: `quiz-plan.md` §5.4 — add a one-sentence pointer that the prompt revision is recorded in `quiz-fix-plan.md` and in the framework doc.

---

### Tier B+ — Pedagogical formatting, seed diversity, diagnostics

The lift that turns this from a "filter out the noise" fix into a genuine concept-oriented pipeline. Each step is symmetric across arms.

#### B+1. Pedagogical context formatter

**Motivation**: even after Tier A removes structural artifacts, `RetrievalContext.format_for_prompt()` still emits a graph-database-style listing:

```
=== Entities ===
- Thread 1: ...
=== Relations ===
- Thread 1 --[wait]--> Semaphore X
=== Text Chunks ===
[Chunk 1] ...
```

This format itself encourages extractive questions. The fix is a **smart formatter** — deterministic, free (no extra LLM call), and symmetric across arms.

**Modify**: `lightrag/quiz/retrieval.py:RetrievalContext.format_for_prompt`

Replace the current bullet-listing output with a pedagogically-structured format:

```
=== Topic ===
<auto-derived from the dominant document / section, e.g. "Thread
synchronization and the wait/signal protocol on semaphores.">

=== Key concepts ===
- <concept name from entity>: <entity description, instance labels redacted>
- ...

=== Conceptual relationships ===
- A <concept> coordinates <concept> via <relation description>.
- ...

=== Supporting context ===
<chunk prose, with instance labels redacted to {thread}, {process}, {core}, etc.>
```

**Critical sub-step — instance-label redaction**: introduce a helper in `lightrag/quiz/artifacts.py` (extends the file from A1):

```python
_INSTANCE_LABEL_PATTERNS = [
    (re.compile(r"\bThread\s+[A-Z0-9]\b"),    "{thread}"),
    (re.compile(r"\bP\d+\b"),                 "{process}"),
    (re.compile(r"\bprocess_\d+\b"),          "{process}"),
    (re.compile(r"\bcore\s+\d+\b", re.I),     "{cpu_core}"),
    (re.compile(r"\bCPU_\d+\b"),              "{cpu_core}"),
    (re.compile(r"\bPage\s+\d+\b"),           "{memory_page}"),
    (re.compile(r"\bSemaphore\s+[A-Z]\b"),    "{semaphore}"),
    (re.compile(r"\b[TS]\d+\b"),              "{thread}"),  # T1, S2 ... ambiguous; use last-resort
]

def redact_instance_labels(text: str) -> str:
    """Replace instance-specific labels with concept placeholders.

    The generator can't ask "What is the label of {thread}?" — there is
    no label to ask about, only the underlying concept.
    """
    for pat, repl in _INSTANCE_LABEL_PATTERNS:
        text = pat.sub(repl, text)
    return text
```

Apply `redact_instance_labels` to:
- Entity descriptions in the "Key concepts" section
- Relation descriptions in the "Conceptual relationships" section
- Chunk prose in the "Supporting context" section

Entity *names* (the keys, like `"Thread 1"`) are also passed through redaction before display — so the prompt sees `{thread}` not `Thread 1`. The original names remain in `RetrievalMetadata.entities` for traceability.

> **Topic derivation**: the simplest implementation is "concatenate the unique section titles from chunk metadata, separated by '; '". A more sophisticated version uses a tiny one-shot LLM call ("Summarize what the following sections cover in one sentence"). Start with the simple version; promote to LLM-based only if Phase 1 evaluation shows it's the bottleneck.

> **Why this preserves the thesis comparison**: the formatter restructures and redacts what was retrieved; it does not *invent* content. Mix-arm and naive-arm get the same formatter, but mix-arm has explicit relations to populate the "Conceptual relationships" section, whereas naive-arm typically has an empty or sparse one. That structural difference is *exactly* the retrieval-quality signal the thesis wants to measure.

#### B+2. Seed diversity (promote from Tier C3)

**Motivation**: production users running multiple quizzes need varied questions. The duplication observed in `quiz-50f66d4a-…json` (4× "purpose of memory management") came from independent seeds collapsing into the same chunk.

**Modify**: `lightrag/quiz/seeds.py:sample_seeds`

After sampling the entity pool, pre-cluster seeds by their *chunk-of-origin* (the chunks they map back to via `source_id`). Enforce: **no two seeds share the same primary chunk**. If the entity pool exhausts before `n` distinct primary chunks are found, fall back to sampling with replacement (current behavior) and log a warning.

```python
def _seed_primary_chunk(e: dict) -> str:
    """First source_id of the entity — its 'home' chunk."""
    src = e.get("source_id", "")
    for cid in src.split(GRAPH_FIELD_SEP):
        cid = cid.strip()
        if cid:
            return cid
    return ""

# In sample_seeds, replace `random.sample(names, n)` with:
shuffled = random.sample(entities, len(entities))
chosen: list[dict] = []
used_chunks: set[str] = set()
for e in shuffled:
    chunk = _seed_primary_chunk(e)
    if chunk and chunk in used_chunks:
        continue
    chosen.append(e)
    used_chunks.add(chunk)
    if len(chosen) == n:
        break
# Pad with replacement if needed; record fallback in metadata warnings.
```

This addresses issue #5 without retry loops, without semantic embedding, and without changing the "one seed → one question" guarantee.

#### B+3. Diagnostic verifier metrics

**Motivation**: the current verifier marks "What is the label of Thread A?" as *passing* (answerable: yes, complexity: matches). The verifier prompt is locked, so the fix is **not** to tighten the verifier — it's to add diagnostic fields that surface the failure mode without changing the pass/fail semantics. This serves both production (analytics on quality) and the thesis (more columns for the mix-vs-naive comparison).

**Modify**: `lightrag/quiz/schemas.py:GenerationMetadata` — add two new fields:

```python
class GenerationMetadata(BaseModel):
    """Records the generation call details."""
    model: str = Field("gpt-4o")
    prompt_template_id: str = Field("", description="e.g. 'easy_v2', 'hard_v2'")
    question: str = ""
    reference_answer: str = ""
    # Diagnostic — no behavioral impact, used for analytics & thesis reporting
    figure_dependency_estimate: float = Field(
        0.0,
        description=(
            "0.0 = question is fully concept-based; "
            "1.0 = question reads like a label/cell lookup from a figure. "
            "Heuristic — see lightrag/quiz/diagnostics.py."
        ),
    )
    source_lexical_overlap: float = Field(
        0.0,
        description=(
            "Jaccard overlap between question tokens and the top retrieved "
            "chunk tokens (stopword-filtered, lowercased). Higher = more "
            "extractive surface form."
        ),
    )
```

**New file**: `lightrag/quiz/diagnostics.py` — contains:

```python
_FIGURE_DEP_PATTERNS = [
    re.compile(r"\blabel\s+of\b", re.I),
    re.compile(r"\bname\s+of\s+the\s+\w+\s+in\s+the\s+diagram\b", re.I),
    re.compile(r"\blabel\s+used\s+to\b", re.I),
    re.compile(r"\bwhich\s+\w+\s+is\s+(labeled|labelled|marked|shown)\b", re.I),
    re.compile(r"\b(first|second|third|fourth|fifth)\s+\w+\s+in\s+the\s+(figure|diagram|table)\b", re.I),
]

def estimate_figure_dependency(question: str, reference_answer: str) -> float:
    """Heuristic score in [0, 1]."""
    score = 0.0
    for pat in _FIGURE_DEP_PATTERNS:
        if pat.search(question):
            score += 0.4
    # Short cryptic answers like "P1", "core 3", "C A B" are figure-dependent
    tokens = reference_answer.strip().split()
    if 1 <= len(tokens) <= 3 and any(re.search(r"\d|[A-Z]{2,}", t) for t in tokens):
        score += 0.4
    return min(score, 1.0)

def source_lexical_overlap(question: str, top_chunk_text: str) -> float:
    """Stopword-filtered Jaccard between question and source chunk."""
    # … standard implementation, ~15 lines …
```

**Modify**: `lightrag/quiz/pipeline.py:_generate_one` — populate the two fields after generation succeeds (before building `GenerationMetadata`).

These fields are **diagnostic only** — no regenerate-on-threshold logic, no verifier behavior change. The verifier prompt stays at `verifier_v1`. The fields appear in the JSON output where the user can post-hoc filter or analyze.

> Why no regenerate loop: per `suggestion.md` §5 and the previous review, regen-on-overlap has too many false positives (legitimate comparative questions share tokens with sources) and complicates the methodology. Diagnostics are strictly additive.

---

## Phase 2 — Conditional Improvements (DO ONLY IF PHASE 1 INSUFFICIENT)

Apply only if a re-run after Phase 1 still shows quality issues that the per-question diagnostics (B+3) confirm.

### P2.1 LLM-based semantic compression

If Phase 1 produces questions that are *clean* (no artifacts, no duplicates, no label-extraction) but still feel *shallow* (factual repetition without insight), add a single LLM call that takes the B+1 formatted context and produces a 1-paragraph "teaching outline" — what concept is at stake, what understanding is being tested, what the student should walk away knowing.

Cost: ~$0.0005/question with `gpt-4o-mini` → ~$0.15 for a 300-question matrix. Trivial.

This is `suggestion.md` §1, promoted only if needed and applied symmetrically.

### P2.2 Question Intent Planning

If user research shows students want to choose what they're quizzed on (e.g. "quiz me on semaphores" rather than getting a random selection from the indexed docs), add an intent-planning step:

```
user_topic → identify_concept → identify_learning_objective → choose_question_style → generate
```

This is a UX-level feature as much as a quality improvement. Worth its own design doc when prioritized. Reference: `suggestion.md` §3.

### P2.3 Concept-oriented chunk reranking

If B+3's `source_lexical_overlap` shows that the surviving label-extraction questions correlate with low-quality chunks (table-dominant, figure-dominant), introduce a lightweight reranker that down-weights structural chunks. **Use embeddings, not lexical heuristics** — `"is defined as"` regex matching is too brittle for slide-deck content. Apply symmetrically to both arms.

Reference: `suggestion.md` §2, with the caveat above.

---

## Skip indefinitely

| Item | Why |
|------|-----|
| Lexical-overlap penalty + automatic regenerate | Token overlap is a noisy signal (comparative questions share tokens by design). Regen loops complicate the methodology with marginal quality gain. Diagnostic field (B+3) captures the same info without behavioral side effects. |
| Tighten the verifier to reject label-extraction questions | The verifier is locked for thesis comparability across already-generated quizzes. The fix lives in the generator (B2 + B+1), where it actively shapes output, not in the verifier where it would just discard work. |
| Instance-label entity merging in the KG (`Thread 1`/`Thread A` → `Thread`) | Requires modifying the KG extraction prompt and re-indexing every document. Multi-day effort. B+1's redaction layer achieves 80% of the same benefit with zero KG changes. |
| Re-running existing quizzes with v2 prompts | Existing JSON keeps its `easy_v1` tag — that's the traceability guarantee. New runs use v2 automatically. Re-running is a user-driven action, not part of this plan. |
| Heavy embedding-based post-generation deduplication (Tier C1) | B+2 (seed diversity by source chunk) prevents duplicates at the input layer, which is cheaper, simpler, and preserves the "one seed → one question" guarantee. |

---

## Recommended Path

Apply **all of Phase 1** (A + B + B+1 + B+2 + B+3) in one sweep.

Rationale:
- **A** is mechanical input cleanup.
- **B** sharpens the prompt to refuse extractive shapes.
- **B+1** changes *what* the generator sees, not just *what it's told*. This is the single highest-leverage change for production quality.
- **B+2** addresses cross-seed duplication at its root.
- **B+3** gives every quiz an analytics layer for ongoing quality monitoring.

A, B, B+2, and B+3 are all under 2-hour changes each. B+1 is bigger (~4-6 hours including the redaction patterns and a small unit-test suite). Total Phase 1 ≈ a day of focused work.

Phase 2 items are only triggered if a post-Phase-1 evaluation surfaces residual issues. Do **not** implement Phase 2 preemptively.

---

## Files Touched (summary)

### Phase 1

**Tier A**:
- `lightrag/quiz/artifacts.py` *(new)* — `is_artifact_id`
- `lightrag/quiz/seeds.py` — apply `is_artifact_id` in `_list_entities_in_scope`
- `lightrag/quiz/retrieval.py` — apply filter in `format_for_prompt` and `_bfs_subgraph`

**Tier B**:
- `lightrag/quiz/generation.py` — bump IDs to `_v2`, add Avoid block + figure-independence bullet, soften easy answer constraint
- `claude_review_rag_framework.md` — record v2 prompt revisions
- `quiz-plan.md` — add §5.4 pointer

**Tier B+**:
- `lightrag/quiz/artifacts.py` *(extend)* — add `redact_instance_labels` and `_INSTANCE_LABEL_PATTERNS`
- `lightrag/quiz/retrieval.py` *(rewrite `format_for_prompt`)* — pedagogical formatter with redaction applied
- `lightrag/quiz/seeds.py` — seed-diversity logic in `sample_seeds`
- `lightrag/quiz/schemas.py` — add `figure_dependency_estimate` and `source_lexical_overlap` to `GenerationMetadata`
- `lightrag/quiz/diagnostics.py` *(new)* — `estimate_figure_dependency`, `source_lexical_overlap`
- `lightrag/quiz/pipeline.py` — populate diagnostic fields in `_generate_one`

### Phase 2 (only if triggered)

- `lightrag/quiz/compression.py` *(new, P2.1)* — LLM-based teaching-outline call
- `lightrag/quiz/intent.py` *(new, P2.2)* — intent-planning step (needs its own design doc)
- `lightrag/quiz/reranker.py` *(new, P2.3)* — embedding-based concept reranker

---

## Verification

End-to-end checks after Phase 1 lands. Run a 25-question quiz with the same 12 OS-course documents, `mode=mix`, `difficulty=easy` — and a **second** 25-question quiz with the same parameters in `mode=naive` — for side-by-side comparison.

**Hard checks** (must pass):

1. **No artifact leakage** — zero `entity_name`/`bfs_path` entries match `^(tb|im|mm)-[0-9a-f]{32}-\d{4}$`.
2. **No label-extraction questions** — zero questions match the regex `(label of|name of the .+ in the diagram|label used to|which .+ is labeled)` (case-insensitive).
3. **No verbatim duplicates** — no two questions in the same quiz share the same first 30 characters.
4. **No single-token answers** — zero reference answers ≤ 3 tokens unless the answer is a proper-noun concept (allowlist: `"FIFO"`, `"LRU"`, `"Banker's algorithm"`, …).
5. **Prompt version recorded** — every `generation.prompt_template_id` reads `"<difficulty>_v2"`.
6. **Framework doc updated** — each of the three prompt sections in `claude_review_rag_framework.md` contains the v2 revision note and the new Avoid block.

**Soft checks** (qualitative):

7. **Diagnostic distribution** — across 25 questions, mean `figure_dependency_estimate` < 0.2 and mean `source_lexical_overlap` < 0.4 (calibrate after first run).
8. **Pedagogical feel** — a 5-question random spot-check should *feel* like quiz questions a student would benefit from (test understanding, not lookup).
9. **Arm distinguishability** — the mix-arm and naive-arm quizzes produced from the same documents should be *visibly different* in question style or coverage. If they look identical, B+1's formatter is doing too much — investigate before declaring Phase 1 done.

**Unit tests** (CI):

10. `test_is_artifact_id` — 5 cases covering positive matches (`tb-<32hex>-0001`, `im-<32hex>-0042`), the negatives (`"Thread 1"`, empty string, `"tb-short"`).
11. `test_redact_instance_labels` — 6 cases covering each `_INSTANCE_LABEL_PATTERNS` entry, plus a no-op case.
12. `test_seed_diversity` — assert that `sample_seeds` never returns two seeds sharing a primary chunk when the entity pool has > `n` distinct chunks.

---

## Open Questions for User

1. **Phase 1 scope confirmation**: implement *all* of Phase 1 in one sweep (Tier A + B + B+1 + B+2 + B+3)? Default is yes.
2. **Re-run policy**: regenerate the existing `quiz-50f66d4a-…json` with v2 prompts and the new formatter after Phase 1 lands, or keep it as a "before" baseline for the thesis? Default is keep as baseline + generate a fresh "after" sample to compare.
3. **B+1 topic derivation**: start with simple section-title concatenation (deterministic, free) or jump straight to a one-shot LLM call for the topic line (more natural, ~$0.0001/question)? Default is simple-first; promote later if needed.
4. **Diagnostic field tuning**: are `figure_dependency_estimate` and `source_lexical_overlap` the right pair of metrics, or do you want a third (e.g. `requires_proper_noun` ratio)? Default is the pair above; easy to extend later.

These are not blockers — listed defaults will be used unless the user redirects.

---

# Round 6 — Naive Arm, Anti-Hallucination, Stronger Anti-Repeat (2026-05-29)

## Context

After R3-R5 stabilised the mix arm, a fresh naive-arm easy quiz
(`quiz-44fbc845-…`, 25 questions) surfaced a cluster of failures that
none of R3-R5 addressed:

1. All 25 seeds were `topic_N` placeholders — the naive seed source
   `seeds.py:_list_chunks_in_scope` still used the broken
   `chunks_vdb.query("the", top_k=500)` pattern that R3 had fixed for
   the mix arm.
2. 5/25 questions had `retrieval.chunk_ids = []` and the generator
   produced answers from GPT-4o-mini's general knowledge (e.g.
   *"kill terminates a Unix process"* never appeared in the user's
   documents).
3. 15/25 questions retrieved the same chunk — `topic_N` queries
   collapse to a tight region of embedding space.
4. The R5-1 Already-asked list was being ignored once it grew long;
   Q9 and Q11 are textually identical.
5. R5-2's `Target concept: topic_N` was meaningless.

Issues 3 and 5 are downstream of 1; fixing 1 eliminates the cascade.

## R6-1 — `_list_chunks_in_scope` reads from `doc_status`

**File**: `lightrag/quiz/seeds.py`

Same fix shape as R3-2b (`_get_scope_chunk_ids`): enumerate chunk IDs
deterministically by iterating `scope_doc_ids` and reading
`doc_status.get_by_id(doc_id).chunks_list`, then resolve each chunk's
content via `chunks_vdb.get_by_ids(ids)` (already used by
`retrieve_mix_arm` line 402).

## R6-2 — Refuse to generate on empty retrieval

**File**: `lightrag/quiz/pipeline.py:_generate_one`

After retrieval and before generation:

```python
if ctx.is_empty():
    raise RuntimeError(
        f"Refusing to generate from empty retrieval (seed={seed!r}). "
        "Question would be ungrounded in the selected documents."
    )
```

The existing `_bounded_generate` try/except converts this into a
warning. Quiz length may drop below the requested N if the seed pool
contains items with no in-scope source chunks — that is the correct
behaviour. Better fewer real questions than hallucinated ones.

## R6-3 — Already-asked block moves AFTER context

**File**: `lightrag/quiz/generation.py:_PROMPT_TEMPLATES`

Old order: instructions → Avoid block → Target concept → Already
asked → Context. The LLM generates right after reading Context — the
anti-repeat constraint is "stale" by the time it picks a question.

New order: instructions → Avoid block → Target concept → Context →
Already asked → **Final reminder** sentence telling the LLM to rewrite
drafts that repeat any prior concept. Standard LLM-prompting pattern
of anchoring the most important constraint last.

## R6-4 — `retrieved_chunk_count` diagnostic

**Files**: `lightrag/quiz/schemas.py`, `lightrag/quiz/pipeline.py`

New `int` field on `GenerationMetadata`, populated in `_generate_one`
from `len(ctx.chunks)`. Purely additive — surfaces retrieval-emptiness
in the JSON for analytics / thesis reporting, even though R6-2 should
already prevent count=0 from reaching this point.

## R6-5 — Bump prompt IDs to v6

**Files**: `lightrag/quiz/generation.py` (`PROMPT_TEMPLATE_IDS`),
`claude_review_rag_framework.md` (v6 revision notes on Easy/Medium/Hard
sections + updated prompt body to show the new positional order),
`lightrag/quiz/generation.py` module docstring (v6 entry mirroring v2-v5).

## Files Touched (R6 summary)

- `lightrag/quiz/seeds.py` — rewrite `_list_chunks_in_scope`
- `lightrag/quiz/pipeline.py` — `is_empty()` guard + `retrieved_chunk_count`
- `lightrag/quiz/generation.py` — template reorder + v6 ID + docstring
- `lightrag/quiz/schemas.py` — `retrieved_chunk_count` field
- `claude_review_rag_framework.md` — v6 revision notes
- `quiz-fix-plan.md` — this section

No new files.

## Verification (R6)

Run a fresh `mode=naive, difficulty=easy, n=25` quiz on the same 12
documents after restart.

**Hard checks**:
1. Every `prompt_template_id` reads `"easy_v6"`.
2. Every `retrieval.seed_query` is a real first-sentence, never
   `topic_N`.
3. Every `generation.retrieved_chunk_count >= 1`. Any 0 means R6-2
   misfired.
4. No two questions have identical `generation.question` text.
   Soft duplicates (5-word prefix collisions) should drop below 2.
5. Spot-check 5 reference answers — phrasing must be traceable to
   source chunks, not generic textbook knowledge.

**Soft checks**:
6. `warnings` may contain `Refusing to generate from empty retrieval`
   entries — this is expected, not a regression.
7. Fewer than 5 of the 25 questions should share the same first
   `chunk_id` (R6-1 spreads retrieval).
8. The mix-arm path should remain green — `mode=mix` quiz on the
   same docs should match the R5 baseline with `prompt_template_id:
   easy_v6` everywhere.

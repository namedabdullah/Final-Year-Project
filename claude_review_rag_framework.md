# RAG Quiz Difficulty Evaluation Framework
## Research-Oriented Design Notes for Claude Code

---

# Objective

This document describes a structured methodology for evaluating quiz generation quality between:

1. **Graph-based RAG (Multi-hop RAG)** — implemented on LightRAG's `mix` mode, augmented with a custom BFS-bounded retrieval controller for exact hop control.
2. **Naive RAG** — implemented on LightRAG's `naive` mode (pure vector retrieval).

The primary goal is to define and enforce quiz difficulty in a measurable, reproducible, and retrieval-aware way.

This framework separates:

- Retrieval Complexity
- Reasoning Complexity

instead of relying on vague prompt instructions like:
> "Generate a hard question."

---

# Core Research Principle

Difficulty should NOT be defined only inside the system prompt.

Difficulty should emerge from:

1. Retrieval structure
2. Context synthesis requirements
3. Reasoning operations

The system prompt should only orchestrate behavior.

---

# Key Design Insight

Traditional approaches often define difficulty subjectively.

Example:
- "easy"
- "medium"
- "hard"

This is weak experimentally because:
- subjective
- inconsistent
- non-reproducible
- not measurable

Instead, difficulty should be operationalized structurally.

---

# Proposed Difficulty Model

Difficulty is composed of TWO dimensions:

| Dimension | Measured By |
|---|---|
| Retrieval Complexity | hops (graph arm) or chunks (naive arm) |
| Reasoning Complexity | reasoning operation |

---

# Difficulty Representation

Each generated question should have explicit metadata.

Example:

```json
{
  "retrieval_complexity": 3,
  "reasoning_type": "causal",
  "difficulty": "hard"
}
```

The full per-question schema (verification fields, BFS path, model IDs, human-rating slot) is defined in *Metadata Schema (Comprehensive)* below.

---

# Important Research Clarification

Hop count does NOT necessarily measure cognitive difficulty.

It measures:
- retrieval complexity
- evidence traversal complexity
- synthesis depth

Example:

## 3-hop but cognitively easy
"Who taught the professor who supervised X?"

## 1-hop but cognitively difficult
"Explain the implications of transformer attention sparsity."

Therefore:

> Difficulty in this framework refers to retrieval and reasoning complexity rather than educational or semantic difficulty.

This distinction should be explicitly stated in the thesis/report.

---

# LightRAG Architecture Mapping

This framework is implemented on top of LightRAG. The mapping from framework concepts to concrete LightRAG components:

| Framework concept | LightRAG component | Notes |
|---|---|---|
| Graph storage | `chunk_entity_relation_graph` | NetworkX-backed by default; entity/relation graph built during `ainsert` |
| Entity vector store | `entities_vdb` | Used to find BFS entry points from a query |
| Chunk vector store | `chunks_vdb` | Used for naive arm + supplementary chunks in mix arm |
| Standard query path | `aquery(mode=...)` | **NOT used directly for the graph arm** — custom BFS replaces it |
| Naive arm | `aquery(mode="naive")` with `chunk_top_k` | Used as-is with controlled chunk count |

**Critical:** LightRAG's `QueryParam` does not expose a `max_hops` parameter. Hop depth is controlled in our custom retrieval pipeline (see *Graph Retrieval Controller*), not via LightRAG's query API. LightRAG is the storage + KG-construction layer; difficulty-aware retrieval sits on top.

---

# Recommended System Architecture

```text
Documents
   ↓
LightRAG ainsert (chunking + entity extraction + graph construction)
   ↓
chunk_entity_relation_graph + entities_vdb + chunks_vdb
   ↓
Difficulty-Aware Retrieval Controller
   ├─ Graph arm: BFS at depth N over chunk_entity_relation_graph + 5 constant vector chunks
   └─ Naive arm: top-N vector chunks via chunks_vdb
   ↓
Reasoning-Type Constraint Prompt
   ↓
GPT-4o Question Generation
   ↓
Claude Sonnet Verification Layer (grounded against retrieved context)
   ↓
Evaluation Metadata Storage (JSON per question)
   ↓
Statistical Analysis + Human-Rated Subsample (n≈50, Cohen's κ)
```

---

# Architectural Principle

The pipeline should separate responsibility across components.

| Component | Responsibility |
|---|---|
| Retrieval Layer | controls evidence complexity (hops or chunks) |
| Prompt Layer | controls reasoning style |
| Generator Model (GPT-4o) | produces questions and reference answers |
| Verifier Model (Claude Sonnet) | grades questions against retrieved context |
| Verification Layer | validates generated question quality |
| Human Rater | anchors verifier reliability on a stratified subsample |

This separation is critical.

---

# Graph RAG Difficulty Design

## Retrieval Complexity Definition

| Difficulty | Graph Definition |
|---|---|
| Easy | 1-hop BFS from entry-point entities |
| Medium | 2-hop BFS from entry-point entities |
| Hard | 3-hop BFS from entry-point entities |

The graph arm uses **mix-mode-style retrieval**: BFS-bounded subgraph PLUS a fixed 5 vector chunks. The 5 chunks are **constant across difficulties** so that chunk volume does not confound the difficulty signal — any difficulty difference is attributable to graph traversal depth, not chunk count.

---

# Graph Retrieval Example

Suppose the graph structure is:

```text
Node A → Node B → Node C
```

## Easy

Retrieve:
```text
[A]
```

## Medium

Retrieve:
```text
[A, B]
```

## Hard

Retrieve:
```text
[A, B, C]
```

---

# Graph Retrieval Controller

The custom BFS replaces LightRAG's standard graph query path. It operates directly on LightRAG's storage layer.

```python
async def retrieve_graph_context(
    rag: LightRAG,
    query: str,
    difficulty: str,
) -> RetrievalContext:
    """
    Custom difficulty-aware retrieval for the graph (mix) arm.
    Does NOT call rag.aquery() — operates on LightRAG's storage layer directly
    so hop depth is exactly controllable.
    """
    hops = {"easy": 1, "medium": 2, "hard": 3}[difficulty]

    # 1. Extract query keywords (reuse LightRAG's existing extraction
    #    pipeline from operate.py — do not reinvent)
    keywords = await extract_keywords_only(query, rag)

    # 2. Find BFS entry points via entity vector search
    entry_entities = await rag.entities_vdb.query(
        " ".join(keywords),
        top_k=5,
    )

    # 3. BFS at the chosen depth over chunk_entity_relation_graph
    subgraph = await bfs_subgraph(
        graph=rag.chunk_entity_relation_graph,
        start_nodes=[e["entity_name"] for e in entry_entities],
        max_depth=hops,
        per_depth_cap=5,  # prevents subgraph explosion at depth 3
    )

    # 4. Pull associated chunks via entity source_ids
    entity_chunks = await fetch_chunks_for_entities(rag, subgraph.entities)

    # 5. Supplement with 5 constant vector chunks (mix-mode flavor)
    extra_chunks = await rag.chunks_vdb.query(query, top_k=5)

    return RetrievalContext(
        entities=subgraph.entities,
        relations=subgraph.relations,
        bfs_path=subgraph.path,
        chunks=dedupe(entity_chunks + extra_chunks),
        hop_depth=hops,
    )
```

Key design points:
- BFS entry points come from entity vector search, **not arbitrary picks**.
- A **per-depth cap** prevents subgraph explosion at depth 3 (default: top 5 per depth by query relevance — open for tuning).
- Vector chunk count is **constant at 5** regardless of difficulty (locked decision).
- The BFS path is captured for metadata storage and traceability.

---

# Naive RAG Difficulty Design

Naive RAG has:
- no explicit graph
- no traversal structure
- chunk-level retrieval only

Therefore:
- hop count cannot be used directly

Instead:
- chunk synthesis count becomes the equivalent metric

---

# Naive Difficulty Mapping

| Difficulty | Naive RAG Definition |
|---|---|
| Easy | answerable from 1 chunk |
| Medium | requires synthesis of 2 chunks |
| Hard | requires synthesis of 3 chunks |

---

# Why This Mapping Works

| Graph RAG | Naive RAG |
|---|---|
| hops traversed | chunks synthesized |
| graph traversal | cross-chunk synthesis |
| connected entities | semantic merging |

This creates a structurally comparable evaluation framework.

---

# Naive Retrieval Controller

```python
async def retrieve_naive_context(
    rag: LightRAG,
    query: str,
    difficulty: str,
) -> RetrievalContext:
    """
    Uses LightRAG's naive query path with controlled chunk_top_k.
    """
    k = {"easy": 1, "medium": 2, "hard": 3}[difficulty]

    chunks = await rag.chunks_vdb.query(query, top_k=k)

    return RetrievalContext(
        chunks=chunks,
        chunk_count=k,
    )
```

Note: this calls into LightRAG's chunk vector store directly rather than going through `aquery(mode="naive")` so we get back the raw chunks (not a pre-formatted prompt) and have full control over what the generator sees.

---

# Critical Architectural Rule

Difficulty should FIRST be enforced at retrieval time.

NOT only in the prompt.

Incorrect approach:
```text
Generate a hard question.
```

Correct approach:
- retrieve difficult evidence structures
- then enforce reasoning behavior through prompting

---

# Reasoning-Type Controller

Difficulty should also include reasoning complexity.

The reasoning layer determines:
- how evidence must be combined
- what cognitive operation is required

---

# Recommended Reasoning Taxonomy

| Reasoning Type | Description |
|---|---|
| factual | direct lookup |
| comparative | compare concepts/entities |
| causal | explain cause-effect |
| temporal | sequence/order reasoning |
| inferential | derive implicit conclusion |
| analytical | synthesize multiple evidence points |

---

# Difficulty Mapping with Reasoning

| Difficulty | Retrieval Complexity | Reasoning Type |
|---|---|---|
| Easy | 1 hop / 1 chunk | factual |
| Medium | 2 hops / 2 chunks | comparative |
| Hard | 3 hops / 3 chunks | causal / inferential / analytical |

---

# Prompt Layer Design

Prompts should:
- enforce reasoning operations
- constrain synthesis behavior

Prompts should NOT solely define difficulty.

---

# Easy Prompt

> **Revision v7 (2026-05-31, follow-up to v6)**: Added an anti-fabrication
> grounding rule (`NO FABRICATED SPECIFICS`) to the Avoid block after the
> smoke-run-#4 verifier pass (`quiz-b363f421`, mix, medium) flagged 3/10
> questions `answerable_from_context=false`. Q3 and Q9 cited specific
> numeric values ("30 seconds and another 40 seconds", "arriving at 0
> seconds and another at 1 second") that originate in burst/arrival-time
> TABLES absent from the retrieved prose — `source_lexical_overlap` was
> 0.09 and 0.02, confirming the reference answers were ungrounded
> general-knowledge fills from GPT-4o-mini. The new rule forbids citing
> exact quantitative values unless they appear verbatim in the context.
> Arm-symmetric (shared Avoid block) but helps the mix arm most, whose
> graph BFS bridges clean concept-seeds (`Running`, `Arrival Time`) into
> table-derived entity neighbourhoods (`P1`, `Burst Time`, `Timeline`).
>
> **Revision v6 (2026-05-29, follow-up to v5)**: Positional reorder of
> the Already-asked block (now AFTER context, with a Final-reminder
> sentence) after `quiz-44fbc845-…` showed GPT-4o-mini ignoring the
> R5-1 anti-repeat list once it grew long. Paired with two non-prompt
> changes: (a) `pipeline.py:_generate_one` refuses to call the
> generator on empty retrievals (was hallucinating Unix command
> answers from training data); (b) `seeds.py:_list_chunks_in_scope`
> reads chunks via `doc_status.chunks_list` instead of the broken
> `chunks_vdb.query("the")` — same fix the entity path got in R3.
>
> **Revision v5 (2026-05-28, same-day follow-up to v4)**: Two
> structural prompt additions after `quiz-a712071b-…` showed the LLM
> converging on a handful of "safe" easy concepts regardless of seed
> diversity (3× "role of CPU", 4× "function of OS"): (a) added a
> `Target concept:` line so the LLM anchors each question on the seed
> entity; (b) added an `Already asked (DO NOT REPEAT or REPHRASE):`
> block populated with every question generated earlier in the same
> quiz, read sequentially under the generation semaphore. Also paired
> with a seed-pool filter that drops figure-label entities (e.g.
> `Multilevel Queue Scheduling Diagram`).
>
> **Revision v4 (2026-05-28, same-day follow-up to v3)**: Three
> refinements after `quiz-caaf0e4a-…` exposed residual failures:
> (a) hardened the placeholder rule into an absolute "no braces in
> output" prohibition with examples, moved to the first position in
> the Avoid block; (b) added an explicit anti-tautology rule (catches
> "What kind of embedded OS is designed for embedded systems?" shapes);
> (c) added an anti-meta-question rule (catches "What documents are
> covered?" shapes). Paired with the formatter change in
> `lightrag/quiz/retrieval.py` that removes the `=== Topic ===`
> section, which was the source of the meta-question failure mode.
>
> **Revision v3 (2026-05-28, same-day follow-up to v2)**: Added a
> placeholder-handling bullet to the Avoid block — the retrieval
> formatter redacts instance labels into braced concept slots
> (`{thread}`, `{process}`, …) and v2 inadvertently let GPT-4o-mini echo
> those tokens into questions (see `quiz-bd12fd67-…`). v3 instructs the
> generator to expand placeholders into natural English.
>
> **Revision v2 (2026-05-28)**: Added explicit anti-pattern guidance to
> avoid diagram-label and table-cell extraction questions; promoted the
> figure-independence heuristic into the prompt. Softened the answer
> shape from "single fact / name / number / short phrase" to "single
> short conceptual statement". Original v1 text preserved in git
> history. Quiz records produced before this date remain tagged
> `easy_v1` for traceability. See `quiz-fix-plan.md` for rationale.

```text
Generate one quiz question answerable directly from the provided context.

Constraints:
- Use factual reasoning only
- Do not require combining multiple ideas
- The answer must exist explicitly in the context
- The answer should be a single short conceptual statement (one sentence)
  drawn directly from the context, not a verbatim table cell or label

Avoid (CRITICAL — ALL of the following are HARD rules):
- ABSOLUTE RULE — NO BRACE CHARACTERS IN OUTPUT: The retrieved context
  contains placeholder tokens like {thread}, {process}, {cpu_core},
  {memory_page}, {memory_frame}, and {semaphore}. These are concept-slot
  markers, NOT real words. If your question OR reference_answer contains
  ANY brace character ({ or }), you have FAILED the task. Always rewrite
  in natural English. Example of FAILURE: "What is the burst time of
  {process}?". Example of SUCCESS: "What does burst time measure for
  a process?".
- ABSOLUTE RULE — NO TAUTOLOGIES: The reference_answer must not just
  restate the question. Example of FAILURE: Q="What kind of OS is
  designed for embedded systems?" A="An embedded OS designed for embedded
  systems." A correct question requires genuine information to answer.
- Do NOT ask meta-questions about the source material itself (e.g.
  "What documents are covered?", "What does the material describe?",
  "How many documents are in the study?"). Ask about the SUBJECT MATTER
  (operating systems, threads, scheduling, …), not about the documents.
- Do NOT ask about diagram labels, table cell values, figure identifiers,
  or instance names (e.g., "P1", "Thread A", "core 3", "CPU_7", "Page 3").
- Do NOT ask "what is the label of…" or "what is the name of the … in the diagram".
- Reference the underlying concept (e.g., "process", "thread", "CPU core",
  "memory page"), not the specific label the figure uses for one instance.
- The reference_answer must be a conceptual statement, not a single
  token, table cell, or figure label.
- If the question would not make sense to a student without seeing the
  original figure, REWRITE it so it does.
- ABSOLUTE RULE — NO FABRICATED SPECIFICS: Do NOT cite specific
  quantitative values — exact times, durations, sizes, counts, memory
  addresses, or numbered instances (e.g. "30 seconds", "arriving at 0
  seconds", "4 KB", "P2") — UNLESS that exact value appears verbatim in
  the Context above. Such numbers usually originate in a figure or table
  that is NOT part of the retrieved text, so a question or
  reference_answer that cites them cannot be grounded. Ask about the
  underlying relationship in conceptual terms instead. Example of
  FAILURE: "How does a process requiring 30 seconds compare to one
  requiring 40 seconds?" Example of SUCCESS: "How does a process's burst
  time influence the order in which it is scheduled?"
- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the "Already asked"
  section below is non-empty, your question must NOT cover the same
  concept, phrasing, or answer as any item in that list.

Target concept: <seed entity name, normalised to concept noun>

Context:
<retrieved context block, with instance labels redacted to {concept-slot} placeholders>

Already asked (DO NOT REPEAT or REPHRASE any of these):
<numbered list of every prior question in this quiz>

Final reminder: generate ONE question that is NOT semantically equivalent
to any item in the "Already asked" list above. If your first draft repeats
any prior question's concept or phrasing, rewrite it before returning JSON.
```

---

# Medium Prompt

> **Revision v7 (2026-05-31, follow-up to v6)**: Same anti-fabrication
> `NO FABRICATED SPECIFICS` rule added as Easy v7 — directly targets the
> medium-arm failure that motivated it (`quiz-b363f421` Q3/Q9 cited
> table-derived second-values absent from the retrieved prose).
>
> **Revision v6 (2026-05-29, follow-up to v5)**: Same positional reorder
> as Easy v6 — Already-asked block moved AFTER context with a
> Final-reminder sentence.
>
> **Revision v5 (2026-05-28, same-day follow-up to v4)**: Same two
> additions as Easy v5 — Target concept line and Already-asked anti-repeat
> block.
>
> **Revision v4 (2026-05-28, same-day follow-up to v3)**: Same three
> refinements applied as Easy v4 — hardened placeholder rule, anti-tautology,
> anti-meta-question.
>
> **Revision v3 (2026-05-28, same-day follow-up to v2)**: Same
> placeholder-handling bullet added as Easy v3.
>
> **Revision v2 (2026-05-28)**: Added the same anti-pattern Avoid block as
> Easy. Comparative-reasoning requirement unchanged. Original v1 text
> preserved in git history. Quiz records produced before this date remain
> tagged `medium_v1`. See `quiz-fix-plan.md`.

```text
Generate one quiz question that requires comparing or connecting information from multiple context sections.

Constraints:
- Use comparative reasoning
- The answer should require synthesizing at least 2 retrieved chunks

Avoid (CRITICAL — ALL of the following are HARD rules):
- ABSOLUTE RULE — NO BRACE CHARACTERS IN OUTPUT: The retrieved context
  contains placeholder tokens like {thread}, {process}, {cpu_core},
  {memory_page}, {memory_frame}, and {semaphore}. These are concept-slot
  markers, NOT real words. If your question OR reference_answer contains
  ANY brace character ({ or }), you have FAILED the task. Always rewrite
  in natural English. Example of FAILURE: "What is the burst time of
  {process}?". Example of SUCCESS: "What does burst time measure for
  a process?".
- ABSOLUTE RULE — NO TAUTOLOGIES: The reference_answer must not just
  restate the question. Example of FAILURE: Q="What kind of OS is
  designed for embedded systems?" A="An embedded OS designed for embedded
  systems." A correct question requires genuine information to answer.
- Do NOT ask meta-questions about the source material itself (e.g.
  "What documents are covered?", "What does the material describe?",
  "How many documents are in the study?"). Ask about the SUBJECT MATTER
  (operating systems, threads, scheduling, …), not about the documents.
- Do NOT ask about diagram labels, table cell values, figure identifiers,
  or instance names (e.g., "P1", "Thread A", "core 3", "CPU_7", "Page 3").
- Do NOT ask "what is the label of…" or "what is the name of the … in the diagram".
- Reference the underlying concept (e.g., "process", "thread", "CPU core",
  "memory page"), not the specific label the figure uses for one instance.
- The reference_answer must be a conceptual statement, not a single
  token, table cell, or figure label.
- If the question would not make sense to a student without seeing the
  original figure, REWRITE it so it does.
- ABSOLUTE RULE — NO FABRICATED SPECIFICS: Do NOT cite specific
  quantitative values — exact times, durations, sizes, counts, memory
  addresses, or numbered instances (e.g. "30 seconds", "arriving at 0
  seconds", "4 KB", "P2") — UNLESS that exact value appears verbatim in
  the Context above. Such numbers usually originate in a figure or table
  that is NOT part of the retrieved text, so a question or
  reference_answer that cites them cannot be grounded. Ask about the
  underlying relationship in conceptual terms instead. Example of
  FAILURE: "How does a process requiring 30 seconds compare to one
  requiring 40 seconds?" Example of SUCCESS: "How does a process's burst
  time influence the order in which it is scheduled?"
- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the "Already asked"
  section below is non-empty, your question must NOT cover the same
  concept, phrasing, or answer as any item in that list.

Target concept: <seed entity name, normalised to concept noun>

Context:
<retrieved context block, with instance labels redacted to {concept-slot} placeholders>

Already asked (DO NOT REPEAT or REPHRASE any of these):
<numbered list of every prior question in this quiz>

Final reminder: generate ONE question that is NOT semantically equivalent
to any item in the "Already asked" list above. If your first draft repeats
any prior question's concept or phrasing, rewrite it before returning JSON.
```

---

# Hard Prompt

> **Revision v7 (2026-05-31, follow-up to v6)**: Same anti-fabrication
> `NO FABRICATED SPECIFICS` rule added as Easy v7.
>
> **Revision v4 (2026-05-28, same-day follow-up to v3)**: Same three
> refinements applied as Easy v4.
>
> **Revision v3 (2026-05-28, same-day follow-up to v2)**: Same
> placeholder-handling bullet added as Easy v3.
>
> **Revision v2 (2026-05-28)**: Added the same anti-pattern Avoid block as
> Easy/Medium. Multi-step reasoning requirement unchanged. Original v1
> text preserved in git history. Quiz records produced before this date
> remain tagged `hard_v1`. See `quiz-fix-plan.md`.

```text
Generate one quiz question requiring multi-step reasoning.

Constraints:
- Use causal, inferential, or analytical reasoning
- The answer should require combining information from at least 3 retrieved context sections
- Avoid direct fact lookup questions

Avoid (CRITICAL — ALL of the following are HARD rules):
- ABSOLUTE RULE — NO BRACE CHARACTERS IN OUTPUT: The retrieved context
  contains placeholder tokens like {thread}, {process}, {cpu_core},
  {memory_page}, {memory_frame}, and {semaphore}. These are concept-slot
  markers, NOT real words. If your question OR reference_answer contains
  ANY brace character ({ or }), you have FAILED the task. Always rewrite
  in natural English. Example of FAILURE: "What is the burst time of
  {process}?". Example of SUCCESS: "What does burst time measure for
  a process?".
- ABSOLUTE RULE — NO TAUTOLOGIES: The reference_answer must not just
  restate the question. Example of FAILURE: Q="What kind of OS is
  designed for embedded systems?" A="An embedded OS designed for embedded
  systems." A correct question requires genuine information to answer.
- Do NOT ask meta-questions about the source material itself (e.g.
  "What documents are covered?", "What does the material describe?",
  "How many documents are in the study?"). Ask about the SUBJECT MATTER
  (operating systems, threads, scheduling, …), not about the documents.
- Do NOT ask about diagram labels, table cell values, figure identifiers,
  or instance names (e.g., "P1", "Thread A", "core 3", "CPU_7", "Page 3").
- Do NOT ask "what is the label of…" or "what is the name of the … in the diagram".
- Reference the underlying concept (e.g., "process", "thread", "CPU core",
  "memory page"), not the specific label the figure uses for one instance.
- The reference_answer must be a conceptual statement, not a single
  token, table cell, or figure label.
- If the question would not make sense to a student without seeing the
  original figure, REWRITE it so it does.
- ABSOLUTE RULE — NO FABRICATED SPECIFICS: Do NOT cite specific
  quantitative values — exact times, durations, sizes, counts, memory
  addresses, or numbered instances (e.g. "30 seconds", "arriving at 0
  seconds", "4 KB", "P2") — UNLESS that exact value appears verbatim in
  the Context above. Such numbers usually originate in a figure or table
  that is NOT part of the retrieved text, so a question or
  reference_answer that cites them cannot be grounded. Ask about the
  underlying relationship in conceptual terms instead. Example of
  FAILURE: "How does a process requiring 30 seconds compare to one
  requiring 40 seconds?" Example of SUCCESS: "How does a process's burst
  time influence the order in which it is scheduled?"
- ABSOLUTE RULE — NO REPEATS OR REPHRASES: If the "Already asked"
  section below is non-empty, your question must NOT cover the same
  concept, phrasing, or answer as any item in that list.

Target concept: <seed entity name, normalised to concept noun>

Context:
<retrieved context block, with instance labels redacted to {concept-slot} placeholders>

Already asked (DO NOT REPEAT or REPHRASE any of these):
<numbered list of every prior question in this quiz>

Final reminder: generate ONE question that is NOT semantically equivalent
to any item in the "Already asked" list above. If your first draft repeats
any prior question's concept or phrasing, rewrite it before returning JSON.
```

---

# Verification Layer (CRITICAL)

LLMs frequently violate constraints silently.

Example failure modes:
- generating shallow questions labeled as "hard"
- ignoring synthesis requirements
- producing single-fact lookup questions

Therefore:
- generated questions must be verified automatically

The verification model is **Claude Sonnet** — deliberately a different model family from the GPT-4o generator. This cross-family pairing is the standard mitigation against generator-grader circularity in LLM-as-judge setups, and is reviewer-defensible in the thesis methodology.

---

# Verification Prompt

The verifier must see the *retrieved context*, not just the question. Without grounding, it cannot reliably trace which entities/chunks the question actually depends on.

```text
You are evaluating a quiz question for a controlled research comparison.

[Retrieved context]
{retrieved_entities_and_relations}   # for graph arm
OR
{retrieved_chunks}                    # for naive arm

[Claimed metadata]
- Difficulty: {claimed_difficulty}
- Retrieval complexity (hops or chunks required): {claimed_retrieval_complexity}
- Reasoning type: {claimed_reasoning_type}

[Question]
{question}

[Reference answer]
{generated_answer}

Determine and return JSON only:
{
  "actual_retrieval_complexity": <int>,
  "actual_reasoning_type": "<factual|comparative|causal|temporal|inferential|analytical>",
  "answerable_from_context": <bool>,
  "claimed_complexity_matches": <bool>,
  "claimed_reasoning_matches": <bool>,
  "notes": "<one-sentence rationale>"
}
```

Trace which entities/chunks are *actually required* to answer. Do not score based on the question's surface appearance.

---

# Verification Goals

The verification layer enables:

- automatic auditing
- consistency checking
- quality validation
- measurable evaluation metrics

---

# Model Pair (Locked)

| Role | Model | Rationale |
|---|---|---|
| Question Generation | GPT-4o | Strong reasoning baseline, widely cited in RAG literature |
| Verification | Claude Sonnet | Different family from generator → avoids same-family circularity |
| Human Rater | You (single rater) | Stratified ~50-question subsample → Cohen's κ vs LLM verifier |

A single human rater is acceptable for FYP scope but should be acknowledged as a methodology limitation; multi-rater designs (with inter-annotator agreement among humans) are stronger but typically out of scope at this scale.

---

# Metadata Storage Design

Each generated question should store structured metadata.

---

# Metadata Schema (Comprehensive)

Single JSON record per question, written to disk on generation and updated on verification + human rating:

```json
{
  "question_id": "uuid",
  "arm": "graph" | "naive",
  "difficulty": "easy" | "medium" | "hard",

  "claimed_retrieval_complexity": 1 | 2 | 3,
  "claimed_reasoning_type": "factual" | "comparative" | "causal" | "temporal" | "inferential" | "analytical",

  "retrieval": {
    "entities": ["..."],
    "relations": [{"source": "...", "target": "...", "type": "..."}],
    "bfs_path": ["A", "B", "C"],
    "chunk_ids": ["..."],
    "hop_depth": 1 | 2 | 3 | null,
    "source_documents": ["..."]
  },

  "generation": {
    "model": "gpt-4o",
    "prompt_template_id": "easy_v1" | "medium_v1" | "hard_v1",
    "question": "...",
    "reference_answer": "..."
  },

  "verification": {
    "model": "claude-sonnet-4-6",
    "actual_retrieval_complexity": <int>,
    "actual_reasoning_type": "...",
    "answerable_from_context": <bool>,
    "claimed_complexity_matches": <bool>,
    "claimed_reasoning_matches": <bool>,
    "notes": "..."
  },

  "human_rating": null | {
    "rater_id": "...",
    "actual_retrieval_complexity": <int>,
    "actual_reasoning_type": "...",
    "answerable_from_context": <bool>,
    "claimed_complexity_matches": <bool>,
    "claimed_reasoning_matches": <bool>,
    "agree_with_verifier": <bool>
  }
}
```

The `bfs_path`, `entities`, and `relations` fields are populated for graph-arm rows only; `chunk_ids` is populated for both arms.

---

# Graph Metadata Example

```json
{
  "difficulty": "hard",
  "retrieval_type": "graph",
  "hop_count": 3,
  "path": ["TCP", "Packet Loss", "Video Streaming"],
  "reasoning_type": "causal"
}
```

---

# Naive Metadata Example

```json
{
  "difficulty": "hard",
  "retrieval_type": "naive",
  "chunks_used": 3,
  "reasoning_type": "comparative",
  "source_documents": [
    "tcp_chunk",
    "udp_chunk",
    "streaming_chunk"
  ]
}
```

---

# Example Hard Question (Graph RAG)

## Retrieved Path

```text
Hop 1: TCP
Hop 2: Packet Loss
Hop 3: Video Streaming
```

---

## Prompt Constraint

```text
Use causal reasoning.
Require synthesis across all context nodes.
```

---

## Generated Question

> Why might UDP be preferred over TCP in live video streaming despite packet loss risks?

This question is:
- multi-hop
- causal
- synthesis-heavy
- structurally difficult

---

# Example Hard Question (Naive RAG)

## Retrieved Chunks

```text
Chunk 1: TCP reliability
Chunk 2: UDP latency
Chunk 3: Streaming systems
```

---

## Prompt Constraint

```text
Generate a causal reasoning question requiring synthesis across at least 3 chunks.
```

---

# Experimental Matrix (Locked)

| Arm | Difficulty | Questions | Subtotal |
|---|---|---|---|
| mix (graph) | easy | 50 | |
| mix (graph) | medium | 50 | |
| mix (graph) | hard | 50 | 150 |
| naive | easy | 50 | |
| naive | medium | 50 | |
| naive | hard | 50 | 150 |
| **Total** | | | **300** |

Human-rated subsample: ~50 questions, stratified random sampling across the 6 cells (~8 per cell), drawn after generation + LLM verification are complete.

---

# Statistical Analysis Plan

| Research question | Test |
|---|---|
| Does mix produce higher verifier-pass rates than naive at each difficulty? | Chi-square test of independence (pass/fail × arm), one test per difficulty level |
| Does the verifier-actual-complexity match the claimed complexity more often in mix vs naive? | McNemar's test (paired) or chi-square |
| Does mix produce different reasoning-type distributions than naive at the hard level? | Chi-square goodness-of-fit |
| How reliable is the LLM verifier itself? | Cohen's κ between human rater and Claude Sonnet on the 50-sample subset |
| Effect sizes | Cramér's V for chi-square tests; report alongside p-values |

Target α = 0.05. The analysis plan should be **pre-registered** (written down before generation runs) to avoid post-hoc cherry-picking and to make the result reviewer-defensible.

---

# Final Experimental Framework

| Retrieval System | LightRAG Realization | Retrieval Complexity Metric | Reasoning Complexity |
|---|---|---|---|
| Graph (mix) RAG | Custom BFS over `chunk_entity_relation_graph` + 5 constant `chunks_vdb` chunks | hop depth (1 / 2 / 3) | reasoning operation |
| Naive RAG | `chunks_vdb.query` with controlled top_k | chunk count (1 / 2 / 3) | reasoning operation |

---

# Most Important Research Insight

The experiment should explicitly distinguish:

| Type | Meaning |
|---|---|
| Retrieval Difficulty | amount of evidence needed |
| Reasoning Difficulty | cognitive operation required |

Most RAG evaluation pipelines fail to separate these cleanly.

Separating them creates:
- stronger methodology
- measurable evaluation
- better reproducibility
- clearer comparison between retrieval systems

---

# Open Items (TBD)

These were raised during design but not yet locked. Resolve before code drops:

| Item | Working default | Why it matters |
|---|---|---|
| Corpus | Whatever is in the current `rag_storage/` working dir | Determines question domain; affects whether quality differences generalize |
| Question format | Short-answer (SAQ) | MCQ unlocks KG-distractor advantage and a richer evaluation dimension at the cost of more eval complexity |
| BFS per-depth cap | Top 5 entities per depth, ranked by query relevance | Prevents subgraph explosion at depth 3; tunable based on observed subgraph sizes |

---

# Recommended Implementation Summary

## Retrieval Layer
Controls:
- hop count (graph arm — via custom BFS)
- chunk count (naive arm — via `chunks_vdb.query` top_k)

## Prompt Layer
Controls:
- reasoning behavior
- synthesis requirements

## Model Layer
- Generation: GPT-4o
- Verification: Claude Sonnet (different family)

## Verification Layer
Controls:
- auditing
- consistency validation
- difficulty verification
- grounded against retrieved context (not blind classification)

## Human-Rating Layer
- Stratified ~50-question subsample
- Cohen's κ vs LLM verifier
- Anchors the reliability of the LLM-as-judge result

---

# Final Recommendation

Implement difficulty structurally, not linguistically.

DO:
- enforce retrieval constraints
- enforce reasoning constraints
- verify generated outputs (grounded, cross-family verifier)
- log metadata
- human-anchor the verifier on a stratified subsample

DO NOT:
- rely solely on prompts like:
  "generate a hard question"

because this produces weak and non-measurable evaluation.

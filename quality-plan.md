# Quiz Quality Plan — Pedagogical Seed Selection, Multi-File Contribution, Diversity & Validation

> **Status**: Design + implementation spec. Supersedes the sketch in
> `pedagogical_seed_strategy_for_claude.md` (kept for history).
> **Implemented (code-complete)**: Phase 1 (RRF scorers, mix + naive), Phase 2
> (Cap+Merit+Floor allocator + `FileContribution` schema + transparency),
> Phase 3 (clustering-for-coverage via `scoring.diversify` + RNG seeding +
> cross-difficulty policy), Phase 4 tooling (diversity metric
> `pairwise_cosine_stats` wired into the response + ablation/sensitivity harness
> `ablation.py`), Phase 5 tooling (matrix runner + `summarize_quiz` in
> `matrix.py`). Code in `scoring.py` / `seeds.py` / `schemas.py` / `pipeline.py`
> / `diagnostics.py` / `ablation.py` / `matrix.py`, behind `QUIZ_SEED_STRATEGY`
> (default `pedagogical`, `random` baseline retained). Unit-tested in
> `tests/test_quiz_scoring.py` (21 tests, all passing).
> **Still requires a live run (not code)**: the Phase 5 matrix generation and
> the Phase 4 ablation/proxy-quality *runs* need the indexed corpus + API keys.
> **Known gaps & deviations**: see `suggestions.md`.
> **Scope**: How the quiz pipeline chooses *what to ask about* (seeds), how it
> guarantees *meaningful multi-file contribution*, how it enforces *diversity*,
> and how the design is *validated* — for the thesis comparison of the two
> systems as wholes.
> **Companion docs**: `quiz-plan.md` (locked architecture), `quiz-fix-plan.md`
> (Rounds 1–6 history), `claude_review_rag_framework.md` (prompt evolution).

---

## 0. The research framing (read this first — everything else depends on it)

We are running a **system-level (black-box) comparison**, not a component-level
ablation. The deliverable is a verdict on the **quality of the generated
quizzes** produced by two complete pipelines:

- **Graph system (`mix` arm)** — entity seeds → custom BFS over the knowledge
  graph → generation.
- **Naive system (`naive` arm)** — chunk seeds → vector top-k retrieval →
  generation.

### Consequence 1 — seeds may legitimately differ between arms

Graph seeds are **entities**; naive seeds are **chunks**. This is **not a
confound** under a system-level comparison — the way each system decides what to
ask about is *part of that system's identity*. We therefore do **not** build a
shared topic front-end. (This reverses an earlier recommendation that only
applied to a component-level study.)

### Consequence 2 — what we may and may not conclude

| May conclude | May NOT conclude |
|---|---|
| "GraphRAG-based generation produces higher-quality quizzes than NaiveRAG-based generation on this corpus." | *Why* the gap exists (e.g. "it's the multi-hop retrieval") — seed source co-varies, so the difference belongs to the whole system, not any one component. |

This limitation must be stated explicitly in the methodology section to avoid
overclaiming.

### Consequence 3 — the fairness contract (two rules)

Because seeds differ, fairness is no longer "same seeds." It becomes:

1. **Own-machinery, used well.** Each arm may use *only its own methodology's*
   machinery, but engineered to a comparable standard.
   - `mix` may use the graph: entities, degree, relations, BFS.
   - `naive` may use **only** vectors + chunk content: embeddings, chunk text,
     clustering, document structure.
   - We compare *each archetype at its best*, never one optimised and one left
     as uniform-random.
2. **Hold non-intrinsic factors constant.** Same corpus, same selected
   documents, same difficulty definitions, same generation LLM, same prompts,
   same verifier, same `num_questions`.

### Consequence 4 — the one trap

**The naive seed scorer must not read the knowledge graph.** Both arms sit on
the same LightRAG index (which always builds a KG), so it is tempting to score
chunks by, say, how many KG entities they contain. Don't. If naive uses graph
structure to choose seeds it stops being "naive RAG" and becomes a hybrid — an
examiner will reject the label. Naive's scorer uses embedding + content signals
only. This is the correct extension of the locked rule "do not filter
tables/images from naive *retrieval*": **naive stays naive**.

> Note the asymmetry this *preserves* works *for* the thesis: GraphRAG's entity
> extraction naturally yields a cleaner concept inventory than raw chunks. Under
> a system-level comparison this counts in the graph system's favour — it is
> part of *why* it wins — and should be reported, not erased.

---

## 1. Design decisions (locked)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Shared vs separate seeds | **Separate** (per arm) | System-level comparison; seed source is part of each system (§0). |
| D2 | Weight scheme for combining signals | **Reciprocal Rank Fusion (RRF)** | Signals are on incommensurable scales; RRF uses only rank order, needs no normalisation, no labels, is robust to correlated signals, and is citable (Cormack, Clarke & Büttcher 2009). Replaces the broken weighted sum. |
| D3 | Multi-file contribution | **Cap + Merit + Floor** | "Earned, not assigned." Only design that honours "a file with nothing meaningful contributes 0." |
| D4 | Pedagogy method | **Deterministic RRF first; optional cached LLM re-rank of top-N** | Cheap, explainable, reproducible; LLM is a refinement layer, never the primary selector. |
| D5 | Centrality measure | **In-scope-subgraph degree** (default); PageRank optional & deferred | Only degree exists in the Python backend today; degree-within-selected-files is more meaningful than global degree. |

**Governing principle** (resolves every future micro-decision): with **no
ground-truth labels**, prefer *explainable + reproducible + justified-by-ablation*
over *learned-but-unvalidated*. This is why RRF beats learned weights, why
deterministic-first beats LLM-only, and why a logged cap/floor beats an opaque
sampler.

---

## 2. Current state (what the code does today)

So the plan is grounded, here is the as-built behaviour. All references verified
against the repo.

- **Single seed entry point**: `sample_seeds()` in `lightrag/quiz/seeds.py:265`,
  called once per quiz at `lightrag/quiz/pipeline.py:222`.
- **Mix branch** (`seeds.py:281`): `random.sample(entities, …)` (line 312) —
  **uniform random** over a degree-*gated* but unweighted pool — then a
  chunk-distinctness dedup (315–326), pad-with-replacement when short
  (329–343), and a `topic_N` placeholder fallback (347).
- **Naive branch** (`seeds.py:350`): `random.sample(chunks, …)` (358) →
  `_first_sentence()` (360); pad-with-replacement (363–373); `topic_N`
  fallback (377).
- **Candidate pool (mix)**: `_list_entities_in_scope()` (`seeds.py:95`) calls
  `get_popular_labels(limit=500)` (line 110) — **global** degree-ranked, then
  scope-filtered (138–144). Already drops artifacts + figure-labels via
  `is_artifact_id` / `is_figure_label_entity` (120–123).
- **Candidate pool (naive)**: `_list_chunks_in_scope()` (`seeds.py:212`) reads
  `doc_status.chunks_list` then `chunks_vdb.get_by_ids()` (250–252).
- **RNG**: module-level `random`, **no `random.seed()` anywhere** → runs are
  non-reproducible across the 300-question matrix.
- **Question-level anti-repeat already exists**: `prior_questions_so_far`
  accumulates inside the `cap=1` semaphore (`pipeline.py:238–251`) and is
  injected as the "Already asked (DO NOT REPEAT or REPHRASE)" block in
  `generation.py`.
- **No per-file contribution signal**: all three arms set
  `source_documents=list(scope_doc_ids)` (`retrieval.py:435/475/517`) — every
  selected doc echoed back, contributed or not.
- **No importance scoring exists** — the work below is net-new behaviour, not a
  refinement of an existing scorer.

---

## 3. Available signals & feasibility (verified)

| Signal | Source in code | Status | Notes |
|---|---|---|---|
| Degree centrality | `node_degree` (`networkx_impl.py:111`, raw int), `get_popular_labels` (degree-ranked) | ✅ today | Raw unbounded int → **needs normalisation** (RRF handles via rank). Use **in-scope subgraph** degree, not global. |
| PageRank / betweenness | none in Python (`nx` is imported at `networkx_impl.py:9`) | ⚠️ small-change | Run `nx.pagerank` on `graph.subgraph(scope_nodes)`. NetworkX backend only. **Deferred** — degree is the default. |
| Cross-document presence | entity `file_path` (`operate.py:1416`) / map `source_id`→chunk→`full_doc_id` (`lightrag.py:1033`) | ✅ today | Count distinct selected files an entity appears in. |
| Frequency | `self.entity_chunks[name]['count']` (`lightrag.py:999`, read at `:2419`) | ✅ today | **Distinct-chunk count, NOT raw mentions.** Use this (uncapped), **not** `len(source_id.split(SEP))` which is **capped at 300, FIFO** (`constants.py:55,62`). Log-scale it. |
| LLM educational importance | new LLM call (cached) | ✅ today | Apply only to top-N candidates; refinement layer. |
| Chunk embeddings (diversity + naive centrality) | `get_vectors_by_ids` (`base.py:350`; Nano impl `nano_vector_db_impl.py:364`) | ✅ today | **Must use `get_vectors_by_ids`** — `query()`/`get_by_ids()` strip the vector field. Chunk dicts carry `id` directly. |
| Entity embeddings | same | ✅ today | **Trap**: entity VDB id = `compute_mdhash_id(entity_name, prefix='ent-')` (`operate.py:1425`). Name/casing drift → silent miss. |
| Per-chunk NER / concept density | none (`import re` only in quiz module) | ❌ needs dep | **Do not add an NER dependency.** For naive, use embedding-cluster centrality + lightweight statistical keyphrase heuristics instead. (Graph-entity-density proxy is forbidden for naive — §0 Consequence 4.) |
| Per-file contribution reporting | no schema field | ❌ schema work | `source_documents` cannot serve (echoes all docs). New response field required. |
| Relation cross-file paths | `relation_chunks` (`operate.py:1656`) carries source_id/file_path | ✅ today | A *difficulty* mechanism for hard questions, **not** a contribution mechanism. Out of scope here. |

---

## 4. Architecture overview

```
sample_seeds(rag, mode, n, scope_doc_ids)
  │
  ├─ build candidate pool (per arm)         ── §2 helpers, fixed to be scope-exhaustive (§5.4)
  │
  ├─ score candidates  ──────────────────►  scoring.py : per-signal ranks → RRF fuse   (Phase 1, §5)
  │                                          + anti-hub guard (mix) / anchor down-rank (naive)
  │
  ├─ diversity filter  ──────────────────►  scoring.py : cluster-for-coverage           (Phase 3, §7)
  │
  ├─ contribution allocator  ────────────►  scoring.py : floor → cap → fill              (Phase 2, §6)
  │                                          emits FileContribution records
  │
  └─ return (seeds, strategy, file_contributions, seed_scores)
```

New module **`lightrag/quiz/scoring.py`** holds the signal computation, RRF,
clustering, and allocation logic. `seeds.py` becomes a thin orchestrator.
`retrieval.py` is **unchanged** (retrieval symmetry preserved — `format_for_prompt`
rule at `retrieval.py:83–84` stays intact).

---

## 5. Phase 1 — Pedagogical seed scorers (the core)

### 5.1 RRF fusion (shared mechanism, separate inputs per arm)

For an arm with candidate set `C` and signal set `S`:

```
for each signal s in S:
    rank_s = candidates sorted DESC by raw signal value  → rank_s(c) ∈ {1,2,3,…}
RRF(c) = Σ_{s in S}  w_s · 1 / (k + rank_s(c))            # k = 60, default w_s = 1.0
```

- `k=60` is the standard RRF constant.
- Default weights are **uniform** (`w_s=1`). Any non-uniform weights must be
  justified by the Phase 4 ablation — never hand-set blind.
- RRF consumes only *order*, so the centrality-vs-frequency scale mismatch and
  signal correlation both stop mattering. **This is the fix for the
  0.4/0.3/0.2/0.1 problem.**

### 5.2 Mix arm — entity scorer

Signals (graph machinery — allowed):

| Signal | Computation |
|---|---|
| `deg` | In-scope-subgraph degree: build subgraph of in-scope entities, count edges to other in-scope entities. (Fallback: `node_degrees_batch`, `base.py:515`.) |
| `xdoc` | Number of distinct selected files the entity appears in (via `file_path` / `source_id`→`full_doc_id`). |
| `freq` | `log(1 + entity_chunks[name]['count'])` — uncapped distinct-chunk count. |
| `llm` *(optional)* | Cached LLM educational-importance score (1–10) over the top-N candidates only. |

**Anti-hub guard** (mandatory): degree is a *prominence prior, not a pedagogy
measure*. Over-general hubs ("System", "Process", "Memory") have the highest
degree but make empty questions ("What is a system?"). Mitigation: **exclude or
heavily down-rank entities whose in-scope degree is above the 90th percentile**
of the in-scope pool (configurable `QUIZ_HUB_PERCENTILE=0.90`). Document this as
"centrality is a prominence prior, capped to avoid generic hubs."

Candidate pool already artifact-free (`seeds.py:120–123`).

### 5.3 Naive arm — chunk scorer

Signals (content/vector machinery **only** — no graph, §0):

| Signal | Computation |
|---|---|
| `cov` (primary) | Embedding-cluster centrality: embed in-scope chunks via `get_vectors_by_ids`, cluster (§7), score by closeness to cluster centroid (medoid-ness). Doubles as the diversity backbone. |
| `density` | Length-normalised keyphrase density — lightweight statistical heuristic (capitalised multi-word terms + noun-phrase-ish regex + term frequency over a stoplist). **Heuristic; validated in Phase 4.** |
| `explan` | Presence of explanatory connectives ("is defined as", "because", "consists of", "unlike", …). **Must be validated on this corpus first** — slide decks are terse and may rarely use connectives; drop the signal if it doesn't fire. |

**Anchor down-rank** (mandatory): chunks whose content begins with
`[Image Name]` / `[Table Name]` are down-ranked **as seeds** (not removed from
retrieval). On this corpus ~75–80% of chunks are anchors, so without this the
naive seed pool is dominated by captions. This is seed-scoring, not
retrieval-filtering — it keeps naive's retrieval space intact (fair) while
letting a *well-built* naive system avoid asking about a bare caption.

### 5.4 Candidate-pool fixes (prerequisite for both arms)

- **Mix pool starvation**: `get_popular_labels(limit=500)` is **global** then
  scope-filtered (`seeds.py:138–144`) — on a large corpus few of the 500 fall in
  the 3–5 selected files, starving the pool *before* scoring. Fix: build the
  in-scope entity set directly from `doc_status.chunks_list` → entities whose
  `source_id` intersects scope, or raise/remove the limit for the scoped query.
- **Degree scope**: compute degree on the **in-scope subgraph**, not the global
  graph (an entity that is a global hub but peripheral in the selected files
  should not win).

---

## 6. Phase 2 — Multi-file contribution (Cap + Merit + Floor)

Layered on each arm's ranked candidates. Contribution is a **consequence** of the
global ranking, never a per-file budget assigned up front.

### 6.1 Algorithm

```
ranked       = rrf_rank(candidates)            # MERIT  (Phase 1)
ranked       = diversity_filter(ranked)        # Phase 3
cap          = ceil(CAP_FRACTION * N)          # CAP_FRACTION default 0.40
selected     = []
per_file     = defaultdict(int)
reasons      = {}                              # doc_id -> reason

for c in ranked:
    f = primary_file(c)
    if signal_below_floor(c):                  # FLOOR: absolute meaningfulness bar
        reasons.setdefault(f, "below_threshold"); continue
    if per_file[f] >= cap:
        reasons[f] = "capped"; continue
    selected.append(c); per_file[f] += 1
    reasons[f] = "contributed"
    if len(selected) == N: break

# Files in scope with zero selected and no other reason -> "outranked"
for f in scope_doc_ids:
    if per_file[f] == 0 and f not in reasons: reasons[f] = "outranked"
```

- **FLOOR** = absolute candidate quality bar. Mix: in-scope degree ≥ `MIN_DEGREE`
  and not a flagged hub. Naive: not an anchor-only chunk and `density` ≥
  `MIN_DENSITY`. A file whose every candidate fails the floor contributes **0**,
  reason `below_threshold`. **This is "nothing meaningful → no contribution."**
- **CAP** = no single file exceeds `ceil(0.40·N)` seats; excess spills to the
  next-best candidates from other files. Prevents one rich file monopolising.
- **No padding.** If `len(selected) < N` after exhausting the pool, **honour the
  smaller quiz** — do *not* pad-with-replacement or fall to `topic_N`. This
  requires overriding the current fallback at `seeds.py:329–343, 347, 363–377`.

### 6.2 Transparency (new schema — see §9)

Emit a `FileContribution` per selected doc: `{doc_id, seed_count, reason}` where
`reason ∈ {contributed, below_threshold, outranked, capped}`. Surface in the quiz
JSON and (later) the UI: *"Covers 3 of 4 selected files; `lecture-03.pptx`
contributed 0 — predominantly figure/table content."*

---

## 7. Phase 3 — Diversity & reproducibility

### 7.1 Clustering-for-coverage (seed-level)

The corpus concentrates on a few topics (the "burst-time table" cluster). Greedy
"reject-too-similar" can still take every seed from the dominant cluster's
outskirts. Instead:

1. Embed candidates (entities via `ent-` id; chunks via their `id`) with
   `get_vectors_by_ids`.
2. Cluster (agglomerative on cosine, or k-means with `k≈N`).
3. Draw seeds **across** clusters, per-cluster count proportional to cluster
   pedagogical mass (sum of member RRF scores). A dominant cluster is naturally
   capped — this composes with the §6 file cap.

**Naive seed has no VDB id**: a naive seed is `_first_sentence(chunk)` — a
free-text string. Run the diversity/clustering over **chunk-ids first**, select
the chunks, *then* extract first sentences. Do not try to look up an embedding
for the sentence.

### 7.2 Division of labour with the existing question-level guard

Two layers, different jobs — **keep both, document the split**:

- **Seed diversity** (new, this phase) → distinct *inputs*.
- **`prior_questions` guard** (existing, `pipeline.py:238–251`,
  `generation.py`) → distinct *outputs*. Necessary because distinct seeds can
  still yield near-identical questions (mix appends 5 seed-similar chunks at
  `retrieval.py:347,411–418`; the v5 prompt comment documents the LLM collapsing
  to generic concepts despite seed diversity).

Seed diversity is **necessary but not sufficient**; `prior_questions` remains the
real backstop.

### 7.3 Over-prune fallback

If diversity filtering shrinks the pool below `N`, **relax the similarity
threshold** rather than pad-with-replacement or drop to `topic_N`. Log in
`warnings` that diversity pruning shrank the pool (transparency, §6.2).

### 7.4 Reproducibility (matrix-critical)

- **Seed the RNG.** Derive a deterministic seed from
  `hash(tuple(sorted(document_ids)), mode)` (optionally + `difficulty`). Add
  `QUIZ_SEED_RNG_SEED` env override. Without this the 300-question matrix is not
  reproducible.
- **Cross-difficulty policy** (recommended): for a given `(arm, file-set)`, fix
  the seed pool **across** easy/medium/hard so the three difficulties ask about
  the *same concepts at different depths*. Makes the within-arm difficulty axis a
  clean variable. (These are separate quizzes/requests, so a student taking one
  difficulty never sees the repetition.) Implement by *excluding* `difficulty`
  from the RNG seed derivation.

---

## 8. Phase 4 — Validation (what makes the design defensible)

No ground-truth labels → validate with the system's own outputs + existing
diagnostics. This *is* the thesis evidence that the scoring works.

### 8.1 Diversity instrument

Add a quiz-level diversity metric: embed the `N` final questions, report
**mean and max pairwise cosine similarity**. Quantifies the §7 claim and gives a
reportable result.

### 8.2 Ablation + sensitivity (answers "why these signals/weights?")

- **Ablation**: drop each RRF signal in turn; report how the top-N seed set
  shifts (Jaccard overlap / Kendall-τ). Identifies the load-bearing signal.
- **Sensitivity**: sweep non-uniform RRF weights over a coarse grid; report seed-set
  stability. Argument becomes either "robust to weight choice" or "signal X is
  load-bearing" — both publishable, neither needs labels.
- **Proxy quality**: tie seed sets to existing diagnostics —
  `figure_dependency_estimate`, `source_lexical_overlap` (`diagnostics.py`), and
  the verifier pass-rate (`VerificationMetadata`) — to show pedagogical seeds
  reduce figure-dependency vs the uniform-random baseline.

### 8.3 Baseline retention

Keep the current uniform-random sampler available behind a flag
(`QUIZ_SEED_STRATEGY=random|pedagogical`) so the ablation has a baseline arm to
compare against.

---

## 9. Schema changes (consolidated)

`lightrag/quiz/schemas.py`:

```python
class FileContribution(BaseModel):
    doc_id: str
    seed_count: int = 0
    reason: Literal["contributed", "below_threshold", "outranked", "capped"]

class SeedScore(BaseModel):                       # optional, for transparency/audit
    candidate: str                                # entity name or chunk id
    rrf_score: float
    component_ranks: dict                          # {signal: rank}

# RetrievalMetadata: extend
    seed_score: Optional[float] = None
    seed_score_components: dict = Field(default_factory=dict)

# QuizGenerateResponse: extend
    file_contributions: List[FileContribution] = Field(default_factory=list)
    diversity: dict = Field(default_factory=dict)  # {mean_pairwise_similarity, max_pairwise_similarity}
```

(`HumanRatingMetadata` already exists at `schemas.py:134` for the optional human
rating pass in Phase 5.)

---

## 10. Files touched (consolidated)

| File | Change |
|---|---|
| `lightrag/quiz/scoring.py` *(new)* | RRF, per-signal computation, anti-hub guard, anchor down-rank, clustering-for-coverage, cap+merit+floor allocator. |
| `lightrag/quiz/seeds.py` | Rewrite `sample_seeds` as a thin orchestrator calling `scoring.py`; fix candidate-pool starvation (§5.4); remove pad-with-replacement / `topic_N` fallbacks; seed the RNG. |
| `lightrag/quiz/pipeline.py` | Thread `file_contributions` + diversity metric into the response; honour smaller-than-`N`; derive RNG seed; keep `prior_questions` guard. |
| `lightrag/quiz/schemas.py` | `FileContribution`, `SeedScore`, extend `RetrievalMetadata` + `QuizGenerateResponse` (§9). |
| `lightrag/quiz/diagnostics.py` | Add inter-question pairwise-similarity helper (Phase 4). |
| `lightrag/kg/networkx_impl.py` *(optional, deferred)* | Thin in-scope-subgraph / PageRank accessor — only if D5 escalates beyond degree. |
| `lightrag/quiz/retrieval.py` | **No change** — retrieval symmetry preserved. |
| `tests/test_quiz_scoring.py` *(new)* | Unit tests for RRF, anti-hub, floor/cap, clustering; **never mock the database** (use a real in-memory LightRAG fixture). |

---

## 11. Implementation traps (verified — do not rediscover these)

1. **Embeddings**: use `get_vectors_by_ids` (`base.py:350`). `query()` and
   `get_by_ids()` strip the `vector` field.
2. **Entity id derivation**: entity VDB id = `compute_mdhash_id(name, prefix='ent-')`
   (`operate.py:1425`). Casing/normalisation drift between graph name and the
   hashed string → silent empty return.
3. **Naive seed has no id**: it's a sentence; diversify over chunk-ids first,
   then extract first sentences (§7.1).
4. **Frequency**: `entity_chunks['count']` is uncapped and correct; the graph
   node `source_id` is capped at 300 FIFO (`constants.py:55,62`) and is the wrong
   source. Also FIFO-vs-KEEP differs between code paths (`operate.py:1471`) — one
   more reason to read `entity_chunks`, not `source_id`.
5. **It's distinct-chunk count, not raw mentions** — an entity mentioned 5× in
   one chunk counts as 1. Frame the signal honestly in the thesis.
6. **Degree is global by default** — scope it to the selected files' subgraph
   (§5.4).
7. **No NER dependency** — naive concept-density is a heuristic + embedding
   clustering, validated in Phase 4. Do not import spaCy/NLTK.
8. **No graph signals in the naive scorer** (§0 Consequence 4).

---

## 12. Sequencing & milestones

| Phase | Deliverable | Depends on |
|---|---|---|
| **0** | This doc (methodology locked). | — |
| **1** | `scoring.py` RRF scorers (mix + naive) wired into `sample_seeds`, behind `QUIZ_SEED_STRATEGY` flag. | §5.4 pool fix |
| **2** | Cap+merit+floor allocator + `FileContribution` schema + transparency output. | Phase 1 |
| **3** | Clustering-for-coverage, RNG seeding, cross-difficulty policy. | Phase 1 |
| **4** | Diversity metric + ablation/sensitivity study + proxy-quality report. | Phases 1–3 |
| **5** | Generate the matrix; compute holistic quiz-quality metrics (verifier flags, diversity, figure-dependency, optional human ratings) for the GraphRAG-vs-NaiveRAG verdict. | Phase 4 |

**Phase 5 note**: because seeds legitimately differ between arms (§0), the entire
comparison rests on the **output quality metrics**. Invest there: verifier flags
(answerable / complexity-match / reasoning-match), the new diversity metric,
figure-dependency, lexical overlap, and a small human-rating pass via the existing
`HumanRatingMetadata`. Pilot on a 3-file set before the full 300-question run.

---

## 13. Out of scope / deferred

| Item | Why deferred |
|---|---|
| Shared topic front-end | Reversed by the system-level framing (§0). |
| PageRank / betweenness | Degree suffices for v1; only NetworkX backend supports it; revisit if the ablation shows degree is the weak signal. |
| Learned weights (RankSVM/LambdaMART) | No ground-truth labels; would overfit 4 weights and invite the exact criticism RRF avoids. |
| Relation-path "hard question" generator | A difficulty mechanism, not a contribution mechanism; separate workstream. |
| Within-quiz difficulty mixing | Difficulty is one Literal per request (`schemas.py:38`); matrix-level, not quiz-level. |

---

## 14. Open parameters (set via Phase 4, never hand-tuned blind)

| Parameter | Default | Set by |
|---|---|---|
| RRF `k` | 60 | Standard; sensitivity-checked. |
| RRF per-signal weights | uniform 1.0 | Ablation (§8.2). |
| `CAP_FRACTION` | 0.40 | Sensitivity sweep. |
| `QUIZ_HUB_PERCENTILE` | 0.90 | Inspect top-degree entities on the corpus. |
| `MIN_DEGREE` / `MIN_DENSITY` (floor) | TBD | Calibrate on the corpus so genuinely-empty files hit 0. |
| Diversity similarity threshold | TBD | Phase 4; relax-on-over-prune (§7.3). |
| `QUIZ_SEED_RNG_SEED` | derived from doc-set | Reproducibility (§7.4). |

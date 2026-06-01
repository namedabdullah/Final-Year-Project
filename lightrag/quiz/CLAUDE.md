# Quiz generation subsystem (`lightrag/quiz/`)

Scoped guidance for the quiz feature built **on top of** LightRAG. This file is loaded
in addition to the repo-root `AGENTS.md` (architecture, storage layers, query modes,
dev/test commands, code style) — it does **not** replace it. Read the root `AGENTS.md`
for anything about core LightRAG; read this for anything under `lightrag/quiz/`.

> Status as of 2026-05-31 · branch `quiz/pedagogical-seed-scoring`. This is FYP /
> thesis work and is intentionally kept out of upstream `HKUDS/LightRAG` PRs.

---

## 1. What this is

A difficulty-aware quiz-generation pipeline whose purpose is a **thesis-grade retrieval
comparison**: generate graded quiz questions from a document set under two retrieval
**arms** and compare quiz quality.

- **mix arm** (`arm="graph"`): KG + vector retrieval — custom BFS over the knowledge graph.
- **naive arm** (`arm="naive"`): vector-only retrieval — controlled chunk-`k`, no graph.
- Other modes (`local`/`global`/`hybrid`) use coarse `top_k` scaling and are **not**
  thesis-rigorous (fallback path only).

The comparison is **system-level** (black-box): seeds legitimately differ per arm because
each arm uses only its own machinery — that difference is part of each system's identity.
The valid conclusion is "GraphRAG produces better/worse quizzes," **not** a component-level
claim about why.

## 2. Locked experimental design

Three decisions are locked (see `claude_review_rag_framework.md`, `quality-plan.md §0`):

1. **300-question matrix** = 2 arms (mix, naive) × 3 difficulties (easy, medium, hard) ×
   50 questions per cell.
2. **RRF-based pedagogical seeding** with symmetric filtering applied identically to both arms.
3. **Generator = GPT-4o (v7 prompts); Verifier = Claude Sonnet (`claude-sonnet-4-6`)** —
   cross-family pairing avoids self-grading circularity. Plus a ~50-question stratified
   human-rated subsample for Cohen's κ vs the LLM verifier.

**Difficulty is structural, not linguistic** — it is operationalized at retrieval time:
- mix: BFS hop depth `easy→1 / medium→2 / hard→3` (vector chunks held **constant at 5**).
- naive: chunk count `easy→1 / medium→2 / hard→3`.
- fallback modes: `chunk_top_k` `easy→3 / medium→5 / hard→10`.
Reasoning type is set in the prompt: easy→factual, medium→comparative, hard→causal
(also inferential/analytical).

## 3. Module map (`lightrag/quiz/`)

Dependency direction: `schemas` ← everything; `artifacts`, `scoring`, `llm_importance`,
`diagnostics`, `storage` are leaves; `seeds`/`retrieval`/`generation`/`verification`/`pedagogy`
sit in the middle; `pipeline` orchestrates; `matrix`/`ablation` drive experiments.

| File | Lines | Responsibility |
|---|---|---|
| `schemas.py` | ~270 | Pydantic request/response + per-question metadata models. Foundational; imports nothing. |
| `seeds.py` | ~680 | Seed sampling. `sample_seeds()` dispatches on `QUIZ_SEED_STRATEGY` → `_sample_seeds_pedagogical` (RRF + diversity + allocate, with optional LLM re-rank) or `_sample_seeds_random` (legacy baseline). `_build_scored_rows` fetches in-scope entities (mix) / chunks (naive). |
| `scoring.py` | ~600 | Pure functions: `fuse_rrf`, `apply_llm_rerank`, `allocate` (Cap+Merit+Floor), `score_mix`/`score_naive` (per-arm signals), `diversify`/`cluster_by_cosine`. `MIX_SIGNALS=(deg,xdoc,freq)`, `NAIVE_SIGNALS=(prose,density,explan)`. |
| `retrieval.py` | ~520 | `RetrievalContext` + `retrieve_mix_arm` (BFS via `_bfs_subgraph`), `retrieve_naive_arm` (controlled-k vector), `retrieve_fallback`. `format_for_prompt()` builds the pedagogical context (key concepts / relationships / supporting prose; instance labels redacted, artifact relations filtered). |
| `generation.py` | ~520 | `generate_question()` → GPT-4o JSON mode with locked v7 templates + shared "avoid block" (no braces / no tautologies / no fabricated specifics / no repeats). 429 backoff retry; mock fallback when no API key. |
| `verification.py` | ~320 | `verify_question()` → Claude Sonnet grounded verifier (answerability + claimed-vs-actual complexity/reasoning match). OpenAI fallback, then conservative mock. **Locked prompt — leave untouched.** |
| `pedagogy.py` | ~260 | `judge_pedagogy()` (pedagogical value 1–5 + Bloom level + answer completeness 1–5) and `judge_correctness()` (independent factual check). Separate Claude calls (Q+A only) so the locked verifier stays pristine. Same Claude→OpenAI→mock degradation. |
| `llm_importance.py` | ~210 | **Step 2** signal: `score_importance()` scores top-N candidates 1–10 for educational importance, temperature 0, disk-cached at `{working_dir}/quiz_llm_importance_cache.json`. Graceful no-op without a key. |
| `pipeline.py` | ~390 | Orchestrator: `generate_quiz()` (seed→retrieve→generate→verify→persist) and `reverify_quiz()`. Empty-retrieval anti-hallucination guard; concurrency cap + inter-request delay for rate limiting. |
| `storage.py` | ~110 | `save_quiz`/`load_quiz`/`list_quizzes`/`save_reverified_quiz`. JSON under `{working_dir}/quizzes/`. `.v2.json` for re-verification — never overwrites the original. |
| `artifacts.py` | ~220 | Structural-noise handling: `is_artifact_id` (`tb/im/mm-<hex>-<n>`), `redact_instance_labels` (`Thread 1`→`{thread}`), `normalize_concept_name`, `is_instance_label_entity`, `is_figure_label_entity`. |
| `matrix.py` | ~125 | **Phase 5**: `run_matrix` drives `generate_quiz` over arms×difficulties; `summarize_quiz` (pure) + `format_comparison` build the verdict table. |
| `ablation.py` | ~115 | **Phase 4**: `run_ablation` deterministically re-scores seeds dropping/up-weighting each signal and reports Jaccard shift. No LLM, no quiz generated. |
| `diagnostics.py` | ~160 | Non-behavioral quality heuristics written to metadata: `estimate_figure_dependency`, `source_lexical_overlap`, `pairwise_cosine_stats`. |
| `__init__.py` | ~35 | Public API: `generate_quiz`, `reverify_quiz`, `list_quizzes`, `load_quiz` + the four public schemas. |

**API router**: `lightrag/api/routers/quiz_routes.py` (`create_quiz_routes`, registered in
`lightrag/api/lightrag_server.py`). Endpoints: `POST /quiz/generate`, `POST /quiz/ablation`,
`GET /quiz/list`, `GET /quiz/{quiz_id}`, `POST /quiz/{quiz_id}/verify`.

## 4. End-to-end flow (`generate_quiz`)

```
sample_seeds (seeds.py)
  pedagogical: score (score_mix/score_naive) → optional LLM re-rank (Step 2)
               → diversify (cluster) → allocate (Cap+Merit+Floor)  → SeedSelection
  random:      uniform sample, RNG seeded by (mode, doc-set), no two seeds share a chunk
for each seed (capped at QUIZ_CONCURRENCY_CAP, prior-questions snapshot for dedup):
  retrieve (mix BFS / naive k / fallback)  → RetrievalContext
  guard: refuse if context empty           (anti-hallucination)
  generate_question (GPT-4o, v7 prompt, target_concept = normalized seed)
  build metadata + diagnostics (figure-dependency, lexical overlap, chunk count)
  verify_question (Claude Sonnet) if run_verification
compute quiz-level diversity (pairwise cosine) → save_quiz → QuizGenerateResponse
```

## 5. Pedagogical seed scoring

Solves the random baseline's problems: duplicate questions, poor concept coverage, and no
per-file contribution signal. Pipeline: **RRF fusion → diversity clustering → Cap+Merit+Floor allocation**.

- **Mix signals** (`scoring.score_mix`): `deg` (in-scope subgraph degree), `xdoc` (distinct
  docs in source chunks), `freq` (log1p distinct-chunk count). Anti-hub guard down-ranks
  ≥90th-percentile-degree entities so generic hubs ("System", "Process") don't dominate.
- **Naive signals** (`scoring.score_naive`, content-only — never the graph): `prose` (not a
  bare `[Image/Table]` anchor), `density` (acronym + title-case phrase density), `explan`
  (explanatory connectives). Embedded-anchor detection catches thin-heading + markup chunks.
- **RRF**: `score = Σ_s w_s / (k + rank_s)`, uniform weights, `k=60` — fuses heterogeneous
  signals without normalization.
- **Diversity** (`diversify`): greedy cosine "leader" clustering, round-robin layout across
  clusters by mass → assigns `select_rank` to spread topics. Best-effort (no-op w/o embeddings).
- **Allocate** (`allocate`): Merit (RRF/`select_rank` order) + Floor (`meets_floor`) + Cap
  (≤40% of N per file, relaxed in pass 2) + dedup by source chunk. **No padding** — a small
  pool yields a smaller quiz. Emits `file_contributions` with reason
  (`contributed`/`below_threshold`/`outranked`/`capped`).
- **Step 2 LLM re-rank** (`apply_llm_rerank` + `llm_importance`): adds an `llm` 1–10 signal
  weighted `2.0`; soft bottom gate fails candidates scored ≤ `QUIZ_LLM_GATE_SCORE`. Re-rank
  only — temperature 0 + disk cache keep it reproducible; no-op without a key.

## 6. Key invariants (don't break these)

- **Arm separation**: naive scorer/retriever has zero graph knowledge; mix may use degree/
  cross-doc/BFS. Enforced by separate functions. Keep it that way.
- **Symmetry**: artifact filters, prompt versions, LLM-importance scoring, anti-patterns,
  diagnostics — apply identically to both arms. The only intended difference is retrieval.
- **Reproducibility**: RNG seeded from `(mode, doc-set)` (difficulty excluded); LLM scoring
  temp 0 + disk cache; prompt versions tagged in `prompt_template_id`. The matrix is reproducible.
- **Anti-hallucination**: empty-retrieval guard refuses generation; instance labels redacted
  to `{slot}` placeholders; quantitative values must appear verbatim in context; verifier is
  conservative ("if unsure, answerable=false").
- **Graceful degradation**: missing API keys / embeddings / parse failures degrade to
  deterministic ranking or mock output — never crash the pipeline.

## 7. Persistence & metadata

```
{working_dir}/quizzes/{quiz_id}.json       # original
{working_dir}/quizzes/{quiz_id}.v2.json    # re-verified (original never overwritten)
{working_dir}/quiz_llm_importance_cache.json
```
Each question records `retrieval` (entities/relations/`bfs_path`/`hop_depth`/`seed_query`/
`seed_score` + per-signal `seed_score_components`), `generation` (model, `prompt_template_id`,
diagnostics incl. `clarity_heuristic`), and optional `verification`, `pedagogy`
(`pedagogical_value`/`bloom_level`/`answer_completeness`), and `correctness`
(`answer_correctness` — only when `run_correctness_check`). Top level adds
`file_contributions`, `diversity`, and `warnings`.

## 8. Environment variables

Seeding: `QUIZ_SEED_STRATEGY` (pedagogical|random), `QUIZ_SEED_RNG_SEED`.
Scoring: `QUIZ_RRF_K` (60), `QUIZ_FILE_CAP_FRACTION` (0.40), `QUIZ_HUB_PERCENTILE` (0.90),
`QUIZ_HUB_PENALTY` (0.5), `QUIZ_HUB_HARD_EXCLUDE` (false), `QUIZ_MIN_ENTITY_DEGREE` (0),
`QUIZ_MIN_CHUNK_DENSITY` (0.0), `QUIZ_NAIVE_EXCLUDE_ANCHORS` (true), `QUIZ_MIN_CHUNK_TOKENS` (5),
`QUIZ_MAX_PROSE_BEFORE_ARTIFACT` (8), `QUIZ_DIVERSITY_SIM_THRESHOLD` (0.6).
LLM re-rank (Step 2): `QUIZ_SEED_LLM_RERANK` (true), `QUIZ_SEED_LLM_TOPN` (50),
`QUIZ_SEED_LLM_MODEL`, `QUIZ_LLM_WEIGHT` (2.0), `QUIZ_LLM_GATE_SCORE` (2.0).
Pipeline: `QUIZ_CONCURRENCY_CAP` (1), `QUIZ_INTER_REQUEST_DELAY` (0.5s), `QUIZ_COMPUTE_DIVERSITY` (true).
Generation: `QUIZ_GENERATION_MODEL`, `QUIZ_GENERATION_RETRY_{ATTEMPTS=5,BASE_DELAY=2.0,MAX_DELAY=60.0}`,
`OPENAI_API_KEY`/`LLM_BINDING_API_KEY`, `LLM_MODEL`.
Verification: `ANTHROPIC_API_KEY`, `QUIZ_VERIFICATION_FALLBACK_MODEL`.
Pedagogy/correctness judges: `QUIZ_PEDAGOGY_MODEL`, `QUIZ_CORRECTNESS_MODEL` (both default
`claude-sonnet-4-6`; reuse the verifier's key + OpenAI fallback). The correctness fact-check
is gated per-request by `run_correctness_check` (default off), not an env var.

> Note: deterministic floors default to no-op (`QUIZ_MIN_ENTITY_DEGREE=0`,
> `QUIZ_MIN_CHUNK_DENSITY=0.0`) — they must be calibrated from the corpus before the matrix run.

## 9. Current state & open work

Progression (see git log + `suggestions.md`):
- **Prompt rounds 1–6 → v7** (`quiz-fix-plan.md`): artifact filtering, anti-repeat, pedagogical
  formatter, anti-fabrication rule.
- **Step 1**: deterministic seed floors + decoupled instance-label entity filter.
- **Step 1b**: exclude embedded-artifact anchor chunks from naive seeds.
- **Step 2**: LLM educational-importance re-rank signal, then tuning (up-weight LLM signal +
  soft bottom gate). **Built, not yet validated live.**

Open TODOs (priority order, from `suggestions.md`):
1. Live smoke run on both arms against the real index (confirm wiring, no `topic_N` placeholders).
2. Turn on + calibrate deterministic floors and hub/cap/diversity thresholds from the corpus.
3. Validate Step 2 live (confirm weak seeds are gated out).
4. Run ablation (`/quiz/ablation`) + proxy-quality vs random baseline.
5. Run the 300-question matrix and compute the verdict; rate the ~50-question subsample (Cohen's κ).
6. Add a fixture-based integration test for `score_mix` / `_fetch_seed_embeddings`.

## 10. Design & planning docs (repo root — read on demand)

Not auto-loaded (kept out of context until needed). Read the relevant one when the task calls for it:

- `claude_review_rag_framework.md` — **research backbone**: difficulty operationalization, BFS/naive
  controllers, prompt layers, verifier design, metadata schema, the 300-question matrix. Start here.
- `quality-plan.md` — pedagogical seed-scoring spec: RRF (§5), Cap+Merit+Floor (§6), diversity (§7),
  validation/ablation (§8). The locked seeding design.
- `quiz-plan.md` — full feature/implementation plan (endpoints, WebUI tab, backend, storage).
- `quiz-fix-plan.md` — history of prompt/retrieval fix rounds 1–6 (→ v7). Traceability.
- `pedagogical_seed_strategy_for_claude.md` — original design sketch (superseded by `quality-plan.md`).
- `suggestions.md` — status report: what's built vs not, calibration TODOs (most current state doc).
- `suggestion.md` — deferred architectural ideas (semantic compression, intent planning, verifier upgrades).

(To make any of these always-loaded with this file instead of read-on-demand, add an `@`-import line,
e.g. `@../../quality-plan.md` — but that re-enlarges the context footprint, so prefer on-demand reads.)

## 11. Running it

Server (loads `/quiz` routes): see root `AGENTS.md` → API Server. Then `POST /quiz/generate`
with `{document_ids, mode, difficulty, num_questions}`. Programmatic: `from lightrag.quiz import
generate_quiz` (requires an initialized `LightRAG` — `await rag.initialize_storages()` first).
Experiments: `lightrag.quiz.matrix.run_matrix(...)` and the `/quiz/ablation` endpoint
(`lightrag.quiz.ablation.run_ablation`). Follow the Python code style in root `AGENTS.md`.

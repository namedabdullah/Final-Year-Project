# Suggestions & Known Gaps — Quiz Quality Implementation

> Companion to `quality-plan.md`. The original plan is now **code-complete**
> (Phases 1–5 tooling, 21 passing unit tests). This file records what the
> implementation does **not** yet do, where it **deviates** from the plan, what
> still needs a **live run / calibration**, and the **reliability** caveats we
> discussed — so nothing is silently assumed "done."
>
> Priority key: **P1** = do before trusting the thesis numbers · **P2** =
> quality/robustness · **P3** = nice-to-have / future.

---

## A. The big one — reliability of the "meaningful or not" judgment + the LLM layer

This is the gap we discussed directly and it is the most important.

### A1 — The absolute FLOOR ships OFF; meaningfulness is currently *relative*  · **P1**
The Cap+Merit+**Floor** allocator is implemented, but the floor thresholds
default to no-op:
```
QUIZ_MIN_ENTITY_DEGREE = 0      QUIZ_HUB_HARD_EXCLUDE = false   # mix floor → always passes
QUIZ_MIN_CHUNK_DENSITY = 0.0    QUIZ_NAIVE_EXCLUDE_ANCHORS = false  # naive floor → always passes
```
**Consequence**: with stock config a file gets 0 seeds by being **outranked**
(relative), not by an **absolute** "nothing meaningful" bar — so the
`below_threshold` reason is effectively unreachable, and "meaningful" today means
"non-artifact + competitive in the RRF ranking," nothing semantic.
**Suggestion**: calibrate and turn on a modest floor (`MIN_ENTITY_DEGREE=1`, a
small `MIN_CHUNK_DENSITY`) by inspecting which entities/chunks fall below it on
the real corpus. Cheap, deterministic, no LLM. This makes "nothing meaningful →
0" an actual judgment rather than a side-effect of competition.

### A2 — Reliability of the signals: structural, shallow, **unvalidated**  · **P1**
What the current signals reliably capture vs not:

| Signal | Reliable at | NOT reliable at |
|---|---|---|
| artifact/anchor filter | "is this a caption/diagram marker" | anchors not at the chunk start |
| graph degree (mix) | prominence / connectedness | **pedagogical importance** (hubs over-score, foundational leaves under-score; only *down-ranked*, not fixed) |
| cross-doc + frequency (mix) | recurrence across corpus | importance vs verbosity; correlated with degree (partial double-count) |
| density heuristic (naive) | rough prose-vs-caption | real concept density — it is acronym+TitleCase counting; crude, gameable, style-dependent, **not validated** |
| explanatory connectives (naive) | textbook-style prose | terse slide bullets (**may rarely fire** on this corpus) |

Nothing in the code *understands* content. The judgment is reliable for
structural distinctions, weak and **unmeasured** for the semantic distinction
that actually matters. **Suggestion**: run the Phase-4 validation (A6) to put a
number on it, and add the LLM layer (A3) to raise the ceiling.

### A3 — The LLM reinforcement/confirmation layer is NOT implemented  · **P1**
`quality-plan.md` *names* an LLM importance signal (decision D4, §5.2, §3) but
the original plan's sequencing (§12) has **no phase that builds it**, and it is
not implemented. Today there is **zero LLM confirmation** of meaningfulness.
**Suggestion** (recommended design, from our discussion):
- Add `llm` as an RRF **re-rank signal** over the top-N candidates (the safe,
  "refinement-not-selector" role), and optionally a **soft gate on borderline
  candidates only** (those near the deterministic floor) — not a blanket gate.
- **Symmetric across both arms** (or it becomes a confound).
- **Temperature 0 + cached by (candidate text + doc-set)** so the 300-question
  matrix stays reproducible and cost stays bounded (judge each concept once).
- The LLM is a stronger signal, **not ground truth** — still validate it against
  a small human-rated sample (A6).
- A clean insertion point exists: the signal sets `MIX_SIGNALS` /
  `NAIVE_SIGNALS` in `scoring.py` are extensible, and `_build_scored_rows` is the
  single place to attach an `llm` signal before `fuse_rrf`.

---

## B. Deviations from the plan as written

### B1 — Naive `cov` (embedding-cluster centrality) is a *diversity* mechanism, not a *scoring* signal  · **P2**
`quality-plan.md` §5.3 lists `cov` as the **primary naive RRF signal**. As built,
embeddings drive **clustering-for-coverage** (`scoring.diversify` → `select_rank`)
but the naive RRF signal set is `{prose, density, explan}` — `cov` is **not** a
ranking signal. So "centrality within the embedding space" influences *spread*,
not *score*. **Suggestion**: if you want `cov` as a ranking signal, add
"closeness to cluster medoid" as a 4th naive signal; otherwise update §5.3 to
match (clustering = diversity only). Low urgency — the diversity use is the more
defensible one.

### B2 — Over-prune fallback (§7.3) is moot by construction  · **P3**
The plan describes relaxing the similarity threshold if diversity pruning shrinks
the pool below N. The implementation **re-orders rather than hard-prunes**
(`diversify` assigns `select_rank`; nothing is dropped), so under-filling from
diversity cannot happen and the relax-threshold path was not needed. **Note for
the write-up**: this is a deliberate, safer choice — document it as such rather
than as an unimplemented item.

### B3 — PageRank / betweenness not implemented (degree only)  · **P3**
Per decision D5 this was deferred; `D5` centrality = in-scope-subgraph degree.
The NetworkX subgraph accessor for `nx.pagerank` was **not** added. Revisit only
if the ablation (A6) shows degree is the weak signal.

### B4 — `SeedScore` standalone model not added  · **P3**
§9 listed an optional `SeedScore` audit model. Implemented instead as
`seed_score` + `seed_score_components` fields directly on `RetrievalMetadata`
(which §9 also specified). The standalone model was optional; skipped.

---

## C. Validation exists as tooling but has NOT been run  · **P1**

The Phase-4 / Phase-5 *logic* is implemented and unit-tested, but the *runs* that
produce the thesis evidence need the live index + API keys. A one-command runner
now drives them over the running server's HTTP API:
``scripts/run_quiz_experiments.py {matrix|ablation|compare}`` (matrix → Phase 5;
ablation → Phase 4.2 via the new `POST /quiz/ablation` endpoint; compare → Phase
4.3 pedagogical-vs-random proxy-quality diff). Outstanding *runs*:

- **Ablation / sensitivity** (`lightrag/quiz/ablation.py:run_ablation`) — never
  executed against the real corpus. Run it per arm to identify the load-bearing
  signal and to justify uniform RRF weights.
- **Proxy-quality** (§8.2) — not computed. Tie selected seeds to the existing
  diagnostics (`figure_dependency_estimate`, `source_lexical_overlap`, verifier
  pass-rate) and compare `pedagogical` vs `random` baseline. This is the evidence
  that the new scorer is actually better than uniform-random.
- **Matrix run** (`lightrag/quiz/matrix.py:run_matrix`) — not executed; this is
  the actual GraphRAG-vs-NaiveRAG verdict. Pilot on a 3-file set first (§5 note).
- **Human-rated sample** — `HumanRatingMetadata` exists but no rating pass has
  been done; it is the only thing that grounds the LLM judge / scorer against
  human pedagogical judgment.

---

## D. Calibration & operational TODOs  · **P2**

Every threshold currently uses a placeholder default and should be set from the
corpus (quality-plan.md §14), not left blind:

| Parameter | Default | Action |
|---|---|---|
| `QUIZ_MIN_ENTITY_DEGREE` / `QUIZ_MIN_CHUNK_DENSITY` | 0 / 0.0 | turn on + calibrate (A1) |
| `QUIZ_HUB_PERCENTILE` / `QUIZ_HUB_PENALTY` | 0.90 / 0.5 | inspect top-degree entities; confirm hubs are demoted not deleted |
| `QUIZ_FILE_CAP_FRACTION` | 0.40 | sensitivity-sweep on real file counts |
| `QUIZ_DIVERSITY_SIM_THRESHOLD` | 0.6 | tune so true near-duplicates cluster without merging distinct concepts |
| `QUIZ_RRF_K` | 60 | standard; sanity-check |

Also operational:
- **Live smoke run needed**: `score_mix` makes real `get_node_edges` /
  `entity_chunks` / `get_vectors_by_ids` calls that the unit tests cannot
  exercise. Run one `mode=mix` and one `mode=naive` quiz on the real index and
  confirm: seeds are real concepts (no `topic_N`), `file_contributions` looks
  sane, `diversity` populated, no exceptions in logs.
- **Embedding cost**: the diversity metric embeds the N questions per quiz and
  `diversify` fetches candidate vectors. Both are guarded
  (`QUIZ_COMPUTE_DIVERSITY`, best-effort embedding fetch) but add latency/cost on
  large runs — watch it during the matrix run.
- **Mix pool starvation (§5.4)**: `_list_entities_in_scope` still seeds its pool
  from `get_popular_labels(limit=500)` (global, then scope-filtered). On a large
  corpus this can under-populate the in-scope pool before scoring. Verify the
  in-scope entity count is healthy in the smoke run; if low, build the in-scope
  set directly from `doc_status.chunks_list`.

---

## E. Testing gaps  · **P2**

- Unit tests cover the **pure** logic (RRF, allocate, diversify, clustering,
  diversity metric, ablation primitives, matrix summary) — 21 tests, no DB.
- **No integration test** exercises `score_mix` / `_fetch_seed_embeddings` /
  `_sample_seeds_pedagogical` end-to-end against a **real in-memory LightRAG
  fixture** (the plan's §10 intent). The live smoke run (D) substitutes for now,
  but a proper fixture-based async test would catch regressions in the graph/VDB
  wiring. Recommended: add `tests/test_quiz_seeds_integration.py` with a tiny
  real index (never mock the DB).

---

## F. Methodology notes (for the thesis write-up, not bugs)

- **Seed-source confound is intentional** under the system-level framing (§0).
  State explicitly in the methodology that the comparison is whole-system; you
  may conclude "GraphRAG produces better quizzes," not "because of retrieval."
- **Distinct-chunk count ≠ mention frequency** — the `freq` signal is distinct
  source-chunk count (an entity mentioned 5× in one chunk counts as 1). Describe
  it honestly.
- **Naive stays naive** — the naive scorer uses no graph signals by design; keep
  it that way if anyone proposes the entity-density proxy.

---

## G. Step 1 implemented + adversarially reviewed (2026-05) — fixes applied & residuals

Step 1 (deterministic seed filters) shipped and was reviewed by two adversarial
agents. **Applied fixes** from the review:

- **S-state false-positive (HIGH)** — the `\b[TS]_?\d\b` redaction pattern ate
  ACPI sleep states (S0–S5; S3 = suspend-to-RAM). Tightened to `\b[TS]_\d\b`
  (underscore-required); bare `S3`/`T1` now survive.
- **P-state false-positive (HIGH)** — entity-dropping is now **decoupled** from
  redaction: `is_instance_label_entity` uses a high-precision pattern subset
  (`_ENTITY_INSTANCE_PATTERNS`) that excludes bare `P0`–`P4`/`S0`–`S5`, so
  ACPI P-/S-state *concepts* are never dropped from the mix pool. Redaction
  stays aggressive (bare `P1` still redacted — burst-time tables need it).
- **Silent random fallback (HIGH)** — added `SeedSelection.authoritative`. When
  the naive floor legitimately empties the pool, the result is honoured (empty/
  smaller quiz with a clear warning) instead of silently reverting to the
  floor-less random baseline. `pipeline.py` no longer placeholder-pads an
  authoritative-empty result.
- **Token floor over-prune (MED)** — `QUIZ_MIN_CHUNK_TOKENS` default lowered
  10 → 5 (token count can't separate terse-teachable bullets from filler;
  Phase-4 calibration still pending).

**Residual / accepted limitations (documented, not fixed):**

- **P-state-in-prose redaction** — bare `P0`/`P1` in *retrieved prose* is still
  redacted to `{process}` (kept for burst-time tables). So genuine "P0 power
  state" text in a passage is over-redacted. Accepted: rare vs. the burst-table
  need; note in the methodology appendix.
- **Bare `P1`/`P2`/`S3` entities are kept** — they may be weak instance-y seeds
  ("Process P2"). This is the deliberate safe-error direction (keep-not-drop);
  the **Step-2 LLM layer** is the intended demoter.
- **`is_instance_label_entity` reshapes the random mix baseline too** (shared
  listers). Intended and consistent with the existing artifact/figure filters —
  note in methodology that the ablation control shares these filters.
- **`MIN_CHUNK_TOKENS` calibration** still deferred to Phase 4 (corpus
  histogram). **P1**
- **Integration test for the all-floor-fail naive case** — can't be unit-tested
  without a real in-memory LightRAG fixture (no DB mocking). The allocate-level
  and dataclass behaviour are locked by pure tests; the end-to-end "no anchor
  seeds re-emitted" path needs the fixture (gap E). **P2**

---

## H. Step 2 implemented (2026-05) — LLM importance re-rank

The A3 gap (LLM reinforcement layer) is now built in `lightrag/quiz/llm_importance.py`
and wired into the pedagogical sampler:

- **Role: re-rank only** (user's choice) — a 1–10 educational-importance score is
  folded in as an extra RRF signal (`scoring.apply_llm_rerank`); nothing is
  hard-dropped. Un-scored candidates get the *mean* (neutral).
- **Top-N only** (`QUIZ_SEED_LLM_TOPN`, default 50) → one batched call per quiz.
- **Temperature 0 + disk cache** (`quiz_llm_importance_cache.json` in the working
  dir, keyed by doc-set + text) → reproducible matrix, each concept judged once.
- **Symmetric** across arms; **pedagogical path only** (random baseline stays
  LLM-free, so the ablation control is clean).
- **Graceful no-op** without an API key / on API error → deterministic ranking
  stands; a quiz never fails because of this layer.
- Config: `QUIZ_SEED_LLM_RERANK` (default true), `QUIZ_SEED_LLM_TOPN`,
  `QUIZ_SEED_LLM_MODEL`.

**Step-2 R3 smoke finding + follow-up (applied):** the LLM judged accurately
(weak seeds → llm ranks 60–79; foundational → 1–13) but **re-rank-only with
equal weights did not evict them** — they were out-voted 3-to-1 by deg/xdoc/freq
and still made the top-10. Fixed by: (a) **up-weighting** the `llm` signal
(`QUIZ_LLM_WEIGHT`, default 2.0) and (b) a **soft bottom gate** that excludes
candidates the LLM *actually scored* ≤ `QUIZ_LLM_GATE_SCORE` (default 2.0; set 0
for pure re-rank). The gate is safe here because the smoke scores are bimodal.
Config: `QUIZ_LLM_RERANK`, `QUIZ_LLM_TOPN`, `QUIZ_SEED_LLM_MODEL`,
`QUIZ_LLM_WEIGHT`, `QUIZ_LLM_GATE_SCORE`.

**Residual for Step 2 (P1/P2):**
- **Up-weight + gate not yet validated live** — confirm the weak seeds are now
  gone (and that the gate doesn't over-prune) in one more smoke run. **P1**
- **Gate reason not distinguished** — an LLM-gated file reports
  `below_threshold` (same as the deterministic floor). Accurate but conflated;
  a distinct `llm_gated` reason would need a schema enum addition. **P2**
- **No live test of the API call** — `_parse_scores`/`_cache_key`/`_build_prompt`,
  `apply_llm_rerank` (incl. weight + gate) are unit-tested; the network call is
  exercised only by the live smoke run (no DB/API mocking). **P2**
- **No live test of the API call** — `_parse_scores`/`_cache_key`/`_build_prompt`
  and `apply_llm_rerank` are unit-tested; the network call is exercised only by
  the live smoke run (no DB/API mocking). **P2**
- **Prompt validation** — the importance rubric is OS-course-tuned; confirm it
  generalises before using on other corpora. **P2**

---

## Recommended next steps (in order)

1. **(P1)** Live smoke run, both arms — confirm the new scorer works on the real
   index (D).
2. **(P1)** Turn on + calibrate the deterministic floor (A1) so "meaningful" is
   absolute, not just relative.
3. **(P1)** Implement the cached, symmetric LLM re-rank signal (A3).
4. **(P1)** Run ablation + proxy-quality + a small human-rated sample (C) to
   validate the scorer and the LLM judge.
5. **(P1)** Run the matrix and write up the verdict (C).
6. **(P2)** Add the integration test (E) and finish threshold calibration (D).

# LLM-as-Judge Evaluation Methodology
## Quiz Generation Quality Comparison: Graph-RAG vs Naive-RAG

> **Status**: Locked design (as of 2026-06-02). This document governs the
> evaluation phase of the quiz comparison study. Read alongside
> `claude_review_rag_framework.md` (retrieval architecture, prompt evolution,
> difficulty model) and `quality-plan.md` (seed selection, RRF fusion,
> allocation). Where this document contradicts the older framework doc, this
> document takes precedence — specifically: (a) the human-rating subsample
> (n≈50, Cohen's κ) described in `claude_review_rag_framework.md` **is
> dropped**; (b) a second LLM judge (`gpt-5-mini`) is added beside Claude
> Sonnet; (c) scoring is pointwise only (no pairwise comparison).

---

## 1. Scope of this document

This document specifies:

1. The **evaluation question** and pre-registered directional hypotheses
2. The **two-judge panel** configuration (which models, what roles, what prompts)
3. The **metric set** being evaluated (existing metrics only — no new metrics)
4. The **reliability strategy** that replaces human evaluation
5. The **statistical analysis plan** (tests, effect sizes, corrections)
6. The **bias controls** and their rationale
7. The **step-by-step execution protocol** for the 300-question matrix run
8. An explicit **limitations statement** for the thesis

It does **not** re-specify the retrieval architecture, prompt templates, seed
selection, or schema — those are already locked in the companion docs. It
**does** show where judge outputs map onto the schema (`schemas.py`) so the
implementation is unambiguous.

---

## 2. Research question

> **Does Graph-RAG-based quiz generation (LightRAG `mix` arm with custom BFS)
> produce higher-quality quizzes than Naive-RAG-based generation (`naive` arm,
> pure vector retrieval), as measured by a two-judge LLM panel across a
> structured 2 × 3 difficulty matrix on a 12-document course corpus?**

This is a **system-level, black-box comparison**. The two arms differ in seed
source (entities vs chunks) *and* retrieval mechanism (graph BFS vs vector
top-k). Any measured quality gap is attributable to the whole pipeline, not to
any single component. This scope constraint must be stated explicitly in the
thesis to prevent overclaiming. See `quality-plan.md §0` for the full
consequence analysis.

---

## 3. Pre-registered hypotheses

These hypotheses are stated before any matrix run. Deciding them after seeing
results would constitute p-hacking and must be explicitly avoided.

| ID | Hypothesis | Direction | Primary metric | Expected if graph wins |
|----|------------|-----------|----------------|------------------------|
| H1 | Groundedness | mix > naive | `answerable_from_context` rate | Graph BFS assembles more complete supporting context per question |
| H2 | Multi-hop complexity | mix > naive | `actual_retrieval_complexity` mean; `claimed_complexity_matches` rate | Graph depth enforces genuine multi-piece questions |
| H3 | Reasoning depth | mix > naive | share of causal / inferential / analytical in `actual_reasoning_type` | Graph structure surfaces relational questions rather than isolated facts |
| H4 | Cognitive depth | mix ≥ naive | Bloom level distribution skewed toward analyze / evaluate | Deeper retrieval context enables higher-order questions |
| H5 | Diversity & coverage | mix > naive | `mean_pairwise_similarity` (lower = better); `files_contributed` count | Entity seeds span the graph's cross-document structure |
| H6 | Pedagogical value | mix ≥ naive | `pedagogical_value` mean | May be a wash — report honestly either way |
| H0a | Factual correctness | mix ≈ naive | `answer_correctness` mean | Same generator on both arms — a difference flags a confound |
| H0b | Clarity | mix ≈ naive | `clarity_heuristic` mean | Same generator — a difference flags a confound |

H0a and H0b are **control hypotheses**: because both arms use the same GPT-4o
generator, their scores on source-independent correctness and surface clarity
should be statistically indistinguishable. A significant difference on a
control metric is a red flag requiring investigation before reporting the
discriminating metrics.

---

## 4. Experimental setup (summary)

Full specifications live in the companion documents. This section records what
the evaluation phase depends on.

### 4.1 Corpus

| Property | Value |
|----------|-------|
| Documents | 12 (indexed in `rag_storage/`) |
| Domain | Operating systems course material (lectures, slides) |
| Entities in graph | ~50 MB vector store |
| Relations in graph | ~101 MB vector store |
| Chunks | ~826 KB chunk store |

Both arms query the **same LightRAG index**. The corpus is not changed between
the mix and naive runs.

### 4.2 Retrieval arms

| Property | mix (Graph-RAG) | naive (Naive-RAG) |
|----------|-----------------|--------------------|
| Seed type | Entities (graph nodes) | Chunks (vector store) |
| Retrieval mechanism | Custom BFS over `chunk_entity_relation_graph` + 5 constant vector chunks | `chunks_vdb.query` with controlled `top_k` |
| Easy | BFS depth 1 | top_k = 1 |
| Medium | BFS depth 2 | top_k = 2 |
| Hard | BFS depth 3 | top_k = 3 |
| Per-depth BFS cap | 5 entities (prevents subgraph explosion) | n/a |
| Constant vector chunks | 5 (invariant across difficulties) | 0 |
| Seed strategy | Pedagogical RRF (entity signals: deg, xdoc, freq, llm) | Pedagogical RRF (chunk signals: prose, density, explan, llm) |

### 4.3 Quiz generation

| Property | Value |
|----------|-------|
| Generator model | GPT-4o |
| Prompt templates | `easy_v7`, `medium_v7`, `hard_v7` (versioned; see `claude_review_rag_framework.md`) |
| Question format | Short-answer (SAQ) — one `question` + one `reference_answer` per record |
| Anti-fabrication | Locked NO FABRICATED SPECIFICS rule in all three prompts (v7) |
| Anti-repeat | `Already asked` block injected into each prompt within a quiz |

### 4.4 Experimental matrix

| Arm | Easy | Medium | Hard | Arm total |
|-----|------|--------|------|-----------|
| mix | 50 | 50 | 50 | 150 |
| naive | 50 | 50 | 50 | 150 |
| **Matrix total** | | | | **300** |

50 questions per cell (2 arms × 3 difficulties × 50) is the minimum for the
arm-level comparison to detect moderate effects (Δ ≈ 0.16 on proportions, d ≈
0.32 on means, at 80% power with n=150 per arm). Per-cell (n=50) analysis is
treated as **descriptive profiling** of the difficulty × arm interaction, not
primary hypothesis testing (it only detects large effects: Δ ≈ 0.26,
d ≈ 0.57).

---

## 5. Evaluation architecture

### 5.1 Design rationale

Quiz questions in a short-answer format cannot be evaluated by string matching
alone. Measuring whether an answer is *grounded*, *pedagogically valuable*, and
*factually correct* requires semantic understanding. LLM-as-judge is the
standard approach for this class of evaluation task and is the method used
throughout recent RAG benchmarking literature.

The framework adopts **pointwise scoring**: each question is evaluated
independently on all metrics. This avoids the complexity of matched-pair
construction (which requires same-topic pairs across arms that may not exist
cleanly) and is the appropriate design for a *profiling* question — measuring
each arm's absolute quality across the full metric spectrum — rather than a
preference question.

### 5.2 The two-judge panel

A single LLM judge introduces an unquantified reliability uncertainty. Using
two judges from **different model families** provides:

- An **inter-judge agreement estimate** (the reliability measure that replaces
  the human gold standard)
- A **cross-family bracket**: both judges must agree for a finding to be
  considered robust
- A **self-preference measurement**: because the generator is GPT-4o and one
  judge is also from the GPT family, any in-family score inflation can be
  estimated as the *gap* between the two judges' absolute scores on the same
  arm

| Role | Model | Family | Rationale |
|------|-------|--------|-----------|
| Primary judge | `claude-sonnet-4-6` | Anthropic (out-family) | Cross-family pairing — the standard mitigation for generator–grader circularity |
| Second judge | `gpt-5-mini` | OpenAI (in-family with generator) | Second independent opinion; enables inter-judge reliability statistics; in-family gap quantifies self-preference bias |

Both judges score **every question** on **every applicable metric**. Results
are stored separately (e.g. `verification.claude`, `verification.gpt`) and
aggregated with explicit per-judge and panel-consensus statistics. Neither
judge is treated as a fallback for the other — the degradation chain
(`ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → mock) is used only when one API is
*unavailable*, not as normal operation.

### 5.3 Self-preference bias: framing and mitigation

`gpt-5-mini` is in-family with the GPT-4o generator. This creates a risk that
it evaluates GPT-generated answers more favourably than Claude does. Two
features of the design bound this risk:

1. **Symmetric exposure**: both arms use the same GPT-4o generator. Any
   in-family inflation applies *equally* to mix and naive questions. Therefore
   the **relative difference** (mix vs naive) is unaffected by self-preference;
   only the *absolute scores* are potentially inflated.
2. **Measurable gap**: the mean difference between Claude and GPT-5-mini scores
   on the same questions is the empirical bias estimate. Report this in the
   thesis as the "cross-family score gap" and frame it as a calibration
   measurement rather than an anomaly.

The thesis headline should lead with the **relative** (mix > naive?) finding,
which is robust to self-preference, before reporting absolute scores, which
carry the caveat.

### 5.4 Judge isolation (arm blindness)

Judge prompts must never reveal which arm a question came from. Concretely:

- No mention of "mix", "naive", "graph", "BFS", "hop count", or "naive
  retrieval" in any judge prompt.
- The `verification` prompt includes the *retrieved context* (entities,
  relations, or chunks) but not the arm label. The judge sees raw content, not
  the metadata field `arm`.
- The `pedagogy` and `correctness` prompts see only the question text and
  reference answer — no retrieval metadata at all.

If any future prompt revision would expose the arm, it must be blocked. This is
a non-negotiable methodological requirement: a judge that can infer the arm
does not measure question quality, it measures arm identity.

### 5.5 Reproducibility controls

| Control | Implementation |
|---------|----------------|
| Temperature | `temperature=0` for Claude Sonnet (deterministic). `gpt-5-mini` only supports its fixed default (temperature=1) and rejects any other value — temperature is omitted for it automatically. |
| Model version logging | Every judge response logs the exact `model` string returned by the API (not the input string). Store in `verification.model` / `pedagogy.model` etc. as already designed. |
| Prompt version logging | Generator prompt template ID (`easy_v7` etc.) and verifier prompt hash stored per question. |
| Seed RNG | Deterministic seed derived from `hash(tuple(sorted(document_ids)), mode)` — difficulty excluded (cross-difficulty policy). Override with `QUIZ_SEED_RNG_SEED`. |
| Cache judge outputs | Raw judge response JSON (including `notes` rationale) stored in the quiz JSON alongside computed metric values. Never discard rationales — they are audit evidence. |

---

## 6. Metric set

All metrics listed here are **already implemented** in the codebase. No new
metrics are added. The table below consolidates them for the thesis and maps
each to the schema field, judge role, and hypothesis it evidences.

### 6.1 Grounding & faithfulness (Verifier judge role)

These metrics are computed by the verifier judge, which sees the question,
reference answer, **and** the retrieved context.

| Metric | Schema field | Scale | Meaning | Hypothesis |
|--------|-------------|-------|---------|------------|
| Groundedness | `verification.answerable_from_context` | boolean | Answer fully supported by retrieved context; judge instructed to be conservative (default false if uncertain) | H1 |
| Actual retrieval complexity | `verification.actual_retrieval_complexity` | int (≥1) | Minimum number of context pieces the judge determined were actually required | H2 |
| Actual reasoning type | `verification.actual_reasoning_type` | enum {factual, comparative, causal, inferential, analytical} | Reasoning operation the question actually required, per judge | H3 |
| Complexity match | `verification.claimed_complexity_matches` | boolean | **Deterministic** (not LLM-judged): claimed complexity meets the floor threshold for the difficulty tier (hard ≥ 2 pieces, etc.) | H2 |
| Reasoning match | `verification.claimed_reasoning_matches` | boolean | **Deterministic** (not LLM-judged): claimed reasoning type falls within the accepted set for the difficulty tier | H3 |

The match booleans are computed in `diagnostics.py` using floor-based
(complexity) and tier-based (reasoning) rules, not by the LLM, to keep the
locked verifier prompt unchanged.

**Aggregated to quiz level** (reported per arm × difficulty cell):
- `answerable_rate` — proportion of questions with `answerable_from_context = true`
- `complexity_match_rate` — proportion of questions with `claimed_complexity_matches = true`
- `reasoning_match_rate` — proportion of questions with `claimed_reasoning_matches = true`
- `reasoning_type_distribution` — histogram of `actual_reasoning_type` values

### 6.2 Pedagogical quality (Pedagogy judge role)

These metrics are computed by the pedagogy judge, which sees only the question
and reference answer (no retrieved context, no arm label). This is a
cheap, retrieval-independent assessment of educational value.

| Metric | Schema field | Scale | Meaning | Hypothesis |
|--------|-------------|-------|---------|------------|
| Pedagogical value | `pedagogy.pedagogical_value` | 1–5 (1=trivia, 5=foundational) | Worth testing this concept on students | H6 |
| Bloom's level | `pedagogy.bloom_level` | enum {remember, understand, apply, analyze, evaluate, create} | Cognitive depth per Bloom's taxonomy | H4 |
| Answer completeness | `pedagogy.answer_completeness` | 1–5 (1=doesn't address, 5=fully addresses) | How completely the reference answer answers the question | H5 (partial) |

**Aggregated to quiz level**:
- `pedagogical_value_mean` — mean over scored questions (exclude score=0 i.e. unscored)
- `bloom_distribution` — histogram of Bloom levels
- `answer_completeness_mean` — mean over scored questions

### 6.3 Factual correctness (Correctness judge role — optional)

This metric is computed by the correctness judge, which sees only the question
and reference answer and assesses from domain knowledge, independent of the
retrieved context. It is a control metric: because both arms use the same
generator, scores should be statistically equal.

| Metric | Schema field | Scale | Meaning | Hypothesis |
|--------|-------------|-------|---------|------------|
| Answer correctness | `correctness.answer_correctness` | 1–5 (1=definitely wrong, 5=definitely correct) | Factual accuracy from domain knowledge (source-independent) | H0a (control) |

This role is gated by `QuizGenerateRequest.run_correctness_check`. Enable it
for the full 300-question matrix run (`run_correctness_check=true`).

**Aggregated to quiz level**:
- `answer_correctness_mean` — mean over scored questions

### 6.4 Deterministic diagnostic metrics

These metrics are computed entirely within `diagnostics.py` without any LLM
call. They are not subject to judge variability and serve as the non-LLM
validation leg for triangulation (see §7.3).

| Metric | Schema field | Range | Meaning | Direction | Hypothesis |
|--------|-------------|-------|---------|-----------|------------|
| Figure/table dependency | `generation.figure_dependency_estimate` | [0, 1] | 0=concept-based, 1=figure-label lookup | Lower is better | H1 partial |
| Lexical overlap with source | `generation.source_lexical_overlap` | [0, 1] | Stopword-filtered Jaccard(question tokens, top chunk) | Lower = more abstract | Discriminates arms — naive expected higher |
| Clarity | `generation.clarity_heuristic` | [0, 1] | Single-focus clarity (length penalty + sentence count + connective pile-on) | **Higher is better** | H0b (control) |
| Retrieved chunk count | `generation.retrieved_chunk_count` | int | Number of chunks in context for this question | Tracking / sanity | n/a |
| Pairwise similarity (quiz-level) | `diversity.mean_pairwise_similarity` | [0, 1] | Average cosine similarity across all question pairs in the quiz | Lower = more diverse | H5 |
| Max pairwise similarity | `diversity.max_pairwise_similarity` | [0, 1] | Maximum pairwise cosine — flags near-duplicates | Flag only | H5 |
| Files contributed | `file_contributions[*].seed_count > 0` | count | Number of documents that contributed at least one seed | Higher = better coverage | H5 |

---

## 7. Reliability strategy

Human evaluation is not conducted in this study due to time and resource
constraints. The reliability argument therefore rests on four independent
mechanisms. All four must be reported in the thesis to make the reliability
claim defensible.

### 7.1 Inter-judge agreement (primary reliability measure)

For every metric where two judge readings exist (one Claude, one GPT-5-mini),
compute inter-judge agreement statistics. This measures whether the two judges
are measuring the *same* construct consistently — a reliability check, not a
validity check (see §11, Limitation 1).

| Metric type | Agreement statistic |
|-------------|---------------------|
| Ordinal 1–5 (pedagogical_value, answer_completeness, answer_correctness) | **Cohen's quadratic-weighted κ** + Spearman ρ + % exact agreement + % within-1 agreement. Quadratic weighting penalises large disagreements proportionally — the correct default for 5-point scales. |
| Nominal enum (bloom_level, actual_reasoning_type) | **Cohen's unweighted κ** + % agreement per class |
| Binary (answerable_from_context) | **Cohen's κ** + % agreement + **McNemar's test** for systematic directional bias (does one judge say "answerable" more often?) |

**Interpretation frame**: do not compare κ to an absolute benchmark in
isolation. The correct comparison is "judge-judge agreement relative to
expected agreement given the task difficulty." A κ of 0.5 on
`pedagogical_value` may be entirely appropriate if the construct is genuinely
subjective. Report confidence intervals on κ (bootstrap or asymptotic).

### 7.2 Self-consistency reruns (intra-judge reliability)

Select a random stratified subsample of **~30 questions** (5 per cell: 2 arms
× 3 difficulties). Run both judges **3× on the same questions** (at temperature
0). Report:

- % identical responses per metric per judge (test-retest agreement)
- Cases of inconsistency → examine rationales and flag as anomalies

This is cheap (30 questions × 3 runs × 2 judges = 180 judge calls) and produces
a real intra-judge reliability number for the thesis.

### 7.3 Deterministic triangulation

The deterministic diagnostics (§6.4) provide a **second evidence channel** that
shares no failure modes with LLM judges. Correlated findings across LLM and
deterministic metrics strengthen the conclusion; divergences require
investigation.

Specifically:
- If LLM-judged `answerable_from_context` rates differ between arms, check
  whether `figure_dependency_estimate` and `source_lexical_overlap` move in the
  same direction. Convergence is convergent validity.
- If `diversity` (pairwise cosine, H5) favours mix in LLM-judged
  `reasoning_type_distribution`, check whether it is also reflected in the
  deterministic `mean_pairwise_similarity` metric.
- If both LLM and deterministic indicators agree, the conclusion is
  well-triangulated. If they disagree, do not cherry-pick — report both and
  acknowledge the inconsistency.

### 7.4 Author face-validity audit

Select approximately 20–30 question records covering all 6 cells (3–5 per cell)
and read the full per-question judge output including the `notes` rationale
fields. Record:

- How many rationales are coherent and domain-appropriate
- Any rationales that are clearly wrong or off-topic
- Whether the two judges' rationales tell the same story on agreed questions
  and diverge meaningfully on disagreed questions

This is an **informal qualitative check**, not a formal inter-rater study.
Label it explicitly as a "qualitative audit" in the thesis. Do not report it as
equivalent to human evaluation. Its function is to catch systematic prompt
failures that agreement statistics alone cannot detect (e.g. both judges giving
confident but domain-incorrect rationales).

---

## 8. Statistical analysis plan

### 8.1 Primary inference: arm-level comparison (n = 150 vs 150)

All primary hypothesis tests pool across difficulty levels (i.e. compare 150
mix vs 150 naive questions). This is where statistical power is sufficient to
detect moderate effects.

| Metric type | Primary test | Effect size | Notes |
|-------------|-------------|-------------|-------|
| Binary rates (answerable, match booleans) | Two-proportion z-test or χ² test of independence | Cramér's V; risk difference + 95% Wilson CI | Report as "X% vs Y% (95% CI Z–W%), p=…, Cramér's V=…" |
| Ordinal 1–5 scores | Mann–Whitney U | Cliff's δ (rank-biserial) | Non-parametric; report medians and IQRs alongside means |
| Nominal distributions (bloom_level, reasoning_type) | χ² goodness-of-fit or Kruskal–Wallis for distribution shift | Cramér's V | Report as histogram + test |
| Continuous [0,1] diagnostics (similarity, overlap, clarity) | Mann–Whitney U | Cliff's δ | Same as ordinal |

Report **both** Claude and GPT-5-mini judge readings per metric, then
report the **panel consensus** (e.g. "results consistent across both judges"
or "Claude shows Δ = X, GPT-5-mini shows Δ = Y; both in the same direction").

### 8.2 Per-cell descriptive profiling (n = 50 per cell)

For each of the 6 cells, report summary statistics (mean, SD, median, IQR) per
metric per judge. Present as a 2×3 table per metric.

Do **not** run hypothesis tests per cell as primary results — n=50 can only
detect large effects (d ≈ 0.57). Only report per-cell tests in the appendix as
supplementary, and only if the arm-level test is significant and you need to
characterise where the difference arises.

### 8.3 Confidence intervals and effect sizes

Every reported comparison must include:
- A **95% confidence interval** on the difference (risk difference for
  proportions; difference of medians or means for ordinal/continuous)
- An **effect size** (Cramér's V for χ², Cliff's δ for Mann–Whitney U)
- The **p-value** (two-tailed, α = 0.05)

Never report p-values alone. An examiner will ask "how large is the
difference?" — report the CI and effect size first.

### 8.4 Multiple comparisons correction

The analysis tests approximately 8 discriminating metrics × 2 judges = 16
primary tests plus additional control checks. Apply **Benjamini–Hochberg FDR
correction** (q = 0.05) across the family of primary tests. Report both
uncorrected and FDR-corrected p-values. BH is the appropriate correction for
exploratory hypothesis testing where some true effects are expected (as opposed
to Bonferroni, which is overly conservative in this setting).

### 8.5 Handling document nesting (optional robustness check)

Questions are not independent: multiple questions come from the same 12
documents (both arms). This nesting structure can inflate test statistics. For
the primary analysis, treat questions as independent (standard in quiz
evaluation literature). For the thesis appendix, run a **logistic mixed model**
`outcome ~ arm + difficulty + (1|source_doc)` on the binary and ordinal
outcomes and verify that the fixed-effects estimates are consistent with the
simple tests. If they diverge substantially, use the mixed model as the primary
result.

---

## 9. Bias controls

### 9.1 Judge blindness to arm (mandatory)

Verified before any production run. Checklist:
- [ ] Verifier prompt (`verification.py`): no arm label, no "mix"/"naive"/"graph"/"BFS"
- [ ] Pedagogy prompt (`pedagogy.py`): no arm label, no retrieval metadata
- [ ] Correctness prompt (`pedagogy.py`): no arm label, no retrieval metadata
- [ ] `QuizQuestionMetadata` sent to judge: strip the `arm` field before serialising to prompt context

### 9.2 Self-preference / in-family bias

Managed and measured, not eliminated (see §5.3). Reporting protocol:

- Always report Claude and GPT-5-mini scores separately before any aggregate
- Report the mean score gap (Claude absolute − GPT-5-mini absolute) per metric as the
  bias measurement
- Lead with the **relative** finding (mix > naive by Δ) because it is symmetric
  and therefore robust to self-preference
- Note in every comparison table whether the direction is consistent across both
  judges (strong finding) or only in one judge (flag as uncertain)

### 9.3 Verbosity bias

LLM judges are known to favour longer reference answers. Check at run time:
compute `len(reference_answer.split())` per arm and test for a distribution
difference (Mann–Whitney U). If mix answers are systematically longer, include
answer length as a covariate in the mixed model analysis (§8.5) and report the
length-adjusted effect.

### 9.4 Stochasticity and reproducibility

- Claude Sonnet runs at **temperature = 0** (deterministic output).
- `gpt-5-mini` only supports its fixed default temperature (1) and rejects any
  other value — the code auto-detects this and omits the `temperature` parameter
  for the entire `gpt-5` model family. This means gpt-5-mini outputs are
  **non-deterministic** across calls. For the thesis, report this as a known
  limitation: gpt-5-mini reproducibility cannot be guaranteed at the call level.
  Mitigate by running the self-consistency check (§10, Step 4) to measure
  empirical test-retest agreement; if agreement is high, the practical impact is low.
- Both judges use `max_completion_tokens` (the current OpenAI parameter name;
  `max_tokens` is deprecated for newer models).

---

## 10. Execution protocol

### Step 1 — Environment preparation

```
ANTHROPIC_API_KEY=<key>                         # Claude judge
OPENAI_API_KEY=<key>                            # GPT-5-mini judge
QUIZ_GENERATION_MODEL=gpt-4o                    # generator (locked)
QUIZ_PEDAGOGY_MODEL=claude-sonnet-4-6           # primary judge
QUIZ_CORRECTNESS_MODEL=claude-sonnet-4-6        # primary judge
QUIZ_VERIFICATION_FALLBACK_MODEL=gpt-5-mini     # NOTE: this is a fallback, not the panel

# For the panel, a code change is required (§5.2):
# both judges must be called explicitly, not via a fallback chain.
# Confirm with the implementation before this step.

QUIZ_SEED_STRATEGY=pedagogical
QUIZ_COMPUTE_DIVERSITY=true
```

Confirm that the judge-panel code change (wire gpt-5-mini as a parallel judge,
not a fallback) is implemented and tested before proceeding to the pilot.

### Step 2 — Pilot run (30 questions)

Run the matrix for 5 questions per cell (5 × 6 = 30 total):

```python
run_matrix(rag, document_ids,
           arms=["mix", "naive"],
           difficulties=["easy", "medium", "hard"],
           num_questions=5,
           run_verification=True,
           run_correctness_check=True)
```

Pilot goals:
1. Verify end-to-end wiring (both judges fire, outputs stored in both schema
   slots, no fallback-chain bypass)
2. Confirm `gpt-5-mini` temperature handling (see §9.4) — run the 5 questions
   twice and compare outputs
3. Compute preliminary inter-judge κ on the 30 questions (expect n too small
   for significance — this is a sanity check only)
4. Read 10–15 judge rationales (qualitative sanity — are they domain-coherent?
   Is the verifier actually grounding against the context?)
5. Confirm no arm label leaks (audit 5 prompts directly from logs)
6. Record pilot timing → project full matrix duration

Do **not** include pilot questions in the final analysis.

### Step 3 — Calibrate deterministic floors

Before the full run, calibrate the floors in `diagnostics.py` (open TODO from
`lightrag/quiz/CLAUDE.md`):

- `QUIZ_MIN_CHUNK_TOKENS` — minimum content tokens per chunk
- `QUIZ_MIN_ENTITY_DEGREE` — minimum entity degree floor
- `QUIZ_MIN_CHUNK_DENSITY` — minimum keyphrase density

Inspect the pilot quiz records and the corpus statistics to set these so
genuinely empty files hit zero contribution (Cap+Merit+Floor invariant).

### Step 4 — Self-consistency reruns

Before the full matrix run, select 30 questions stratified across cells (pilot
questions may be reused for this). Run both judges **3× on the same questions**.
Compute test-retest agreement (% identical per metric per judge). If any metric
shows < 70% test-retest agreement at temperature 0, investigate before the full
run (possible cause: structured output parsing issues, JSON extraction
fragility).

### Step 5 — Full matrix run (300 questions)

```python
run_matrix(rag, document_ids,
           arms=["mix", "naive"],
           difficulties=["easy", "medium", "hard"],
           num_questions=50,
           run_verification=True,
           run_correctness_check=True)
```

Monitor:
- Both judge slots populated in every record (no silent fallbacks)
- `file_contributions` coverage — confirm both arms are drawing from multiple
  documents
- `diversity.mean_pairwise_similarity` visible per quiz
- Warning counts per quiz (high warnings = potential retrieval problems)

If a run fails mid-way, re-run from the failed cell. Do not re-run completed
cells (quiz IDs are unique; completed cells stay in the JSON store).

### Step 6 — Analysis

Run the analysis script (`scripts/` — to be implemented) which reads all 300
quiz JSON records and produces:

1. **Per-judge, per-metric, per-arm tables** (means, medians, SDs, CIs)
2. **Arm comparison tests** (Mann–Whitney U / χ², Cliff's δ, Wilson CIs)
3. **Inter-judge agreement tables** (weighted κ, % agreement, McNemar on
   binary metrics, Spearman ρ on ordinal)
4. **Cross-family bias table** (mean score gap Claude vs GPT-5-mini per metric
   per arm)
5. **Bloom distribution histogram** (mix vs naive, stacked bars)
6. **Reasoning type distribution** (mix vs naive)
7. **Diagnostic correlation check** (LLM metrics vs deterministic metrics —
   does `answerable_rate` covary with `figure_dependency_estimate`?)
8. **Control metric check** (H0a and H0b tests — confirm mix ≈ naive on
   correctness and clarity)
9. **FDR-corrected p-value table**

---

## 11. Limitations

These must appear in the thesis methodology chapter verbatim or substantially
paraphrased. Pre-acknowledging them demonstrates methodological maturity.

**Limitation 1 — Reliability without validity.**
This study establishes **inter-judge reliability** (the two LLM judges agree)
but not **validity** (they are measuring what we claim to measure). Two LLMs
can be correlated in their errors — both models may share biases from common
pretraining data. The deterministic diagnostic triangulation (§7.3) partially
mitigates this, but cannot rule out correlated systematic failure. Human
evaluation against a ground truth remains the only path to full validity
evidence; that is left as future work.

**Limitation 2 — In-family self-preference.**
The GPT-5-mini judge is in-family with the GPT-4o generator. Its absolute
scores on GPT-generated text may be inflated relative to Claude's. This is
mitigated by the symmetric design (same generator on both arms) and measured
explicitly as the cross-family score gap. The relative mix-vs-naive finding is
the robust primary result; absolute score magnitudes should be interpreted
conservatively.

**Limitation 3 — Single domain.**
The 12-document corpus covers a single university course (operating systems).
Results may not generalise to other domains (e.g. law, medicine, mathematics),
document styles (e.g. papers vs textbooks), or corpus sizes. Framing the study
as a **domain case study** is methodologically correct and appropriate for an
FYP scope. A multi-domain replication is future work.

**Limitation 4 — Capability tier mismatch.**
`gpt-5-mini` is a smaller model than `claude-sonnet-4-6`. Some inter-judge
disagreements may reflect capability differences rather than genuine construct
disagreement. Where the two judges diverge, Claude Sonnet's rating is taken as
the more reliable estimate, given its larger capacity and out-family status.

**Limitation 5 — Short-answer format.**
Both arms generate short-answer questions. Evaluation metrics (especially
`answerable_from_context`) are designed for this format. Multiple-choice formats
would unlock additional evaluation dimensions (e.g. distractor quality) but
introduce distinct failure modes; that comparison is out of scope.

**Limitation 6 — System-level scope.**
The two arms differ in both seed selection and retrieval mechanism. A measured
quality difference is attributable to the whole pipeline, not to any specific
component. Claims about *why* graph-RAG wins (if it does) — e.g. "it is the
multi-hop retrieval specifically" — cannot be made from this design alone.
Component-level ablation is out of scope for this study.

---

## 12. Relationship to companion documents

| Document | What it covers | Where this doc supersedes it |
|----------|---------------|------------------------------|
| `claude_review_rag_framework.md` | Difficulty model, retrieval architecture, prompt evolution, original verification prompt, original schema | §"Human Rater" row in the architecture table and §"Human-Rated Subsample" in the experimental matrix are **replaced** by this document's §7 reliability strategy. The "claude-sonnet-4-6" entry under Model Pair is now the *primary* judge (not the only one). |
| `quality-plan.md` | Seed selection, RRF fusion, allocation, diversity, ablation | Unchanged. The evaluation phase begins after seeds are selected and quizzes are generated. |
| `lightrag/quiz/CLAUDE.md` | Implementation module map, env vars, open TODOs | Three TODOs from that file are addressed here: (a) smoke-run validation → §10 Step 2; (b) floor calibration → §10 Step 3; (c) matrix generation → §10 Step 5. Human-rating TODO is formally dropped. |

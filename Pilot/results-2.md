# Quiz-Quality Results: Mix Arm vs Naive Arm Comparison

This document summarises the quiz-generation runs that compare two retrieval arms
of LightRAG (`mix` and `naive`) on three difficulty levels (`easy`, `medium`,
`hard`), with each cell containing 50 generated questions. Every question was
independently judged by two LLM judges (Claude Sonnet 4.6 and GPT-5-mini) on
verification, pedagogy, and correctness.

Total: 2 arms x 3 difficulties x 50 questions = **300 questions** judged by 2 judges
= **600 judge-records** per metric.

### Per-question table headings (abbreviations)

The per-question tables in section 3 use short column headers so they fit cleanly
when the document is exported to docx. The mapping below shows each abbreviation
and the corresponding heading in long form (the long-form headings match the
metric names exactly).

| Abbreviation | Heading in long form / what it means |
|---|---|
| Q | Question number (1-50 within the cell) |
| CC | Claim cmpx — claimed retrieval complexity (1=easy, 2=medium, 3=hard) |
| AC C / G | Act C / G — actual retrieval complexity, judged by Claude / GPT |
| CM C / G | Cmpx-match C / G — complexity match (1=match, 0=mismatch), Claude / GPT |
| CR | Claim reas — claimed reasoning type |
| AR C / G | Act reas C / G — actual reasoning type, judged by Claude / GPT |
| RM C / G | Reas-match C / G — reasoning match (1=match, 0=mismatch), Claude / GPT |
| AN C / G | Answerable C / G — answerable from context (1=yes, 0=no), Claude / GPT |
| PV C / G | Ped C / G — pedagogical value (1-5), Claude / GPT |
| BL C / G | Bloom C / G — Bloom level, Claude / GPT |
| CP C / G | Compl C / G — answer completeness (1-5), Claude / GPT |
| CT C / G | Correct C / G — answer correctness (1-5; 0 = unscored), Claude / GPT |
| LO | Lex overlap — source lexical overlap (0-1) |
| CL | Clarity — clarity heuristic (0-1) |
| RC | Retr. chunks — number of retrieved chunks fed to the generator |

---

## 1. Experimental setup

### 1.1 The two arms

| Arm | JSON `mode` | Per-question `arm` | What it does |
|---|---|---|---|
| Mix | `mix` | `graph` | Knowledge-graph BFS over entities/relations + vector chunks. Difficulty drives BFS hop depth (easy=1 hop, medium=2 hops, hard=3 hops); vector chunks held constant at 5. |
| Naive | `naive` | `naive` | Vector-only retrieval, no graph. Difficulty drives chunk count (easy=1 chunk, medium=2 chunks, hard=3 chunks). |

Source documents are the same for both arms (3 OS-course slide decks: `1-Introduction.pptx`,
`2-OS Structure.pptx`, `3a-Process Management.pptx`). Both arms use the same generator
(`gpt-4o-mini`, prompt template `easy_v7`) and the same judges. The only difference is
**how context is retrieved before generation**.

### 1.2 The judging panel

Each question is judged twice in parallel:

- **Judge A — Claude Sonnet 4.6** (`claude-sonnet-4-6`): the primary verifier. Its
  outputs live in the JSON fields `verification`, `pedagogy`, `correctness`.
- **Judge B — GPT-5-mini** (`gpt-5-mini`): the second leg of the panel. Its outputs
  live in the fields `verification_gpt`, `pedagogy_gpt`, `correctness_gpt`.

The two judges share identical scales and prompts; only the underlying model differs.

### 1.3 Generation-time diagnostics (model-free)

These are computed deterministically from the question/context, not by a judge.
They live under `generation` in the JSON.

---

## 2. Metric definitions

### 2.1 Verification metrics (judged from retrieved context)

| Metric | Type / Scale | What it measures | How it is computed |
|---|---|---|---|
| `claimed_retrieval_complexity` | Integer 1-3 | The complexity the system **claimed** when it generated the question (1=easy, 2=medium, 3=hard). | Set by the pipeline from the requested difficulty. |
| `actual_retrieval_complexity` | Integer 1-3 | Number of distinct context pieces actually needed to answer (judged). | Judge reads the retrieved context and labels 1 / 2 / 3. |
| `claimed_complexity_matches` | Boolean | Whether the question is genuinely as deep as it claims. | Deterministically: `actual >= floor[claimed]` where floor is `{1:1, 2:2, 3:3}`. A `hard` claim answerable from 1-2 pieces fails. |
| `claimed_reasoning_type` | Categorical (`factual`, `comparative`, `causal`, `inferential`, `analytical`) | The reasoning the system claimed (easy=factual, medium=comparative, hard=causal). | Set by the pipeline from the requested difficulty. |
| `actual_reasoning_type` | Categorical (same set) | The reasoning the judge actually observed. | Judge labels from the same set. |
| `claimed_reasoning_matches` | Boolean | Whether actual reasoning is in the accepted tier for the claim. | Deterministically (tier-based): factual->{factual}; comparative->{comparative}; causal->{causal, analytical}, plus inferential **only if `actual_complexity >= 2`** (a true multi-piece inference). |
| `answerable_from_context` | Boolean | Whether the reference answer is fully grounded in the retrieved context. | Conservative judge call ("if unsure, false"). |

### 2.2 Pedagogy metrics (judged from question + reference answer)

| Metric | Scale | What it measures |
|---|---|---|
| `pedagogical_value` | 1-5 | 1 = trivia / incidental detail; 3 = standard course concept; 5 = foundational, central concept. |
| `bloom_level` | Categorical: `remember`, `understand`, `apply`, `analyze`, `evaluate`, `create` | Which level of Bloom's taxonomy the question targets. |
| `answer_completeness` | 1-5 | 1 = does not address the question; 3 = main point but with gaps; 5 = fully and directly addresses the question. |

### 2.3 Correctness metric (judged from question + answer, no context)

| Metric | Scale | What it measures |
|---|---|---|
| `answer_correctness` | 1-5 (0 = unscored) | Independent factual check against general domain knowledge: 1 = definitely wrong; 3 = partially correct or mixed; 5 = definitely correct. Crucially **does not use the retrieved context** — it is a "is this true in the world?" check, not a "is this supported by context?" check. |

A score of **0** signals an unscored result (API failure or opt-in disabled). A
small number of such records appear in the mix_hard cell.

### 2.4 Generation-time diagnostics (deterministic, written at generation)

| Metric | Scale | Direction | What it measures |
|---|---|---|---|
| `figure_dependency_estimate` | 0.0 - 1.0 | Lower is better | Heuristic estimate of whether the answer depends on a figure/diagram/table. +0.4 for figure-dependency phrasing in the question; +0.4 for a short cryptic answer (1-3 tokens, digits/caps); capped at 1.0. |
| `source_lexical_overlap` | 0.0 - 1.0 | Lower is better (for non-trivial questions) | Stopword-filtered Jaccard overlap between question tokens and the top retrieved chunk's tokens. High values indicate the question is near-extracted from the source. |
| `clarity_heuristic` | 0.0 - 1.0 | Higher is better | Single-focus / brevity score. Starts at 1.0; penalties for long text (>140 chars), multiple sentences, and multi-clause connectives. |
| `retrieved_chunk_count` | Integer >=0 | Diagnostic | Number of context chunks fed to the generator. A value of 0 triggers the anti-hallucination guard. |

### 2.5 Quiz-level diversity (across the 50 questions in a cell)

| Metric | Scale | What it measures |
|---|---|---|
| `mean_pairwise_similarity` | 0.0 - 1.0 | Lower is better | Mean cosine similarity between all pairs of question embeddings in the cell. |
| `max_pairwise_similarity` | 0.0 - 1.0 | Lower is better | Highest pairwise cosine similarity; flags near-duplicate pairs. |

---

## 3. Per-question results

The tables below show every metric for every question. Boolean fields are shown as
1/0. "C" = Claude Sonnet 4.6 judge, "G" = GPT-5-mini judge. Column headers are
abbreviated; the legend at the top of this document explains each one.


### 3.1 Mix arm, easy (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 2 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 3 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 4 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 5 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 6 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 7 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 8 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 9 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 10 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 11 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 12 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 13 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 14 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 15 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 16 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 17 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 18 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 19 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 20 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 21 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 22 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 23 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 24 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 25 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 26 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 27 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 28 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 29 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 30 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 31 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 32 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 33 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 34 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 35 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 36 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 37 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 38 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 39 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 40 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 41 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 42 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 43 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |
| 44 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 45 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 46 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 2 / 3 | remember / remember | 4 / 5 | 5 / 5 | 0.031 | 1.000 | 18 |
| 47 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 5 / 5 | 5 / 5 | 0.042 | 1.000 | 20 |
| 48 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 4 / 5 | 5 / 5 | 0.030 | 1.000 | 10 |
| 49 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 5 | understand / understand | 3 / 4 | 5 / 5 | 0.033 | 1.000 | 22 |
| 50 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / understand | 4 / 4 | 5 / 5 | 0.000 | 1.000 | 9 |

Diversity (cell): mean pairwise = **0.305**, max pairwise = **0.557**.

### 3.2 Mix arm, medium (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 2 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 3 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 4 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 5 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 6 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 7 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 8 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 9 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 10 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 11 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 12 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 13 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 14 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 15 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 16 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 17 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 18 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 19 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 20 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 21 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 22 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 23 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 24 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 25 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 26 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 27 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 28 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 29 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 30 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 31 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 32 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 33 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 34 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 35 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 36 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 37 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 38 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 39 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 40 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 41 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 42 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 43 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 44 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 45 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |
| 46 | 2 | 2 / 1 | 1 / 0 | comparative | inferential / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.045 | 0.985 | 16 |
| 47 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.025 | 0.887 | 24 |
| 48 | 2 | 2 / 1 | 1 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 2 / 2 | 3 / 5 | 0.120 | 0.762 | 25 |
| 49 | 2 | 2 / 1 | 1 / 0 | comparative | analytical / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 4 / 4 | 5 / 5 | 0.056 | 0.805 | 15 |
| 50 | 2 | 3 / 1 | 1 / 0 | comparative | analytical / inferential | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.109 | 0.797 | 27 |

Diversity (cell): mean pairwise = **0.354**, max pairwise = **0.717**.

### 3.3 Mix arm, hard (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 2 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 3 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 4 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 5 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 6 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 7 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 8 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 9 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 10 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 11 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 12 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 13 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 14 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 15 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 16 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 17 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 18 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 19 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 20 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 21 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 22 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 23 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 24 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 25 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 26 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 27 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 28 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 29 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 30 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 31 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 32 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 33 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 34 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 35 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 36 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 37 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 38 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 39 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 40 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 41 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 42 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 43 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 44 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 45 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |
| 46 | 3 | 2 / 2 | 0 / 0 | causal | inferential / causal | 1 / 1 | 0 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 3 / 3 | 0.037 | 0.958 | 36 |
| 47 | 3 | 3 / 2 | 1 / 0 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 5 | analyze / understand | 3 / 3 | 0 / 3 | 0.000 | 0.652 | 30 |
| 48 | 3 | 3 / 2 | 1 / 0 | causal | inferential / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 4 / 4 | 0.106 | 0.927 | 34 |
| 49 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / analyze | 3 / 3 | 4 / 5 | 0.075 | 0.652 | 26 |
| 50 | 3 | 3 / 3 | 1 / 1 | causal | analytical / causal | 1 / 1 | 1 / 0 | 4 / 4 | analyze / analyze | 3 / 3 | 3 / 3 | 0.069 | 0.750 | 33 |

Diversity (cell): mean pairwise = **0.603**, max pairwise = **0.779**.

### 3.4 Naive arm, easy (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 2 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 3 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 4 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 5 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 6 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 7 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 8 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 9 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 10 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 11 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 12 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 13 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 14 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 15 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 16 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 17 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 18 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 19 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 20 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 21 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 22 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 23 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 24 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 25 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 26 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 27 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 28 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 29 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 30 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 31 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 32 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 33 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 34 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 35 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 36 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 37 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 38 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 39 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 40 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 41 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 42 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 43 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 44 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |
| 45 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 46 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 4 | remember / remember | 5 / 3 | 5 / 5 | 0.085 | 1.000 | 1 |
| 47 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | understand / understand | 2 / 3 | 3 / 5 | 0.023 | 1.000 | 1 |
| 48 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 4 / 3 | remember / remember | 2 / 2 | 3 / 3 | 0.119 | 1.000 | 1 |
| 49 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 4 | remember / remember | 5 / 5 | 5 / 5 | 0.196 | 1.000 | 1 |
| 50 | 1 | 1 / 1 | 1 / 1 | factual | factual / factual | 1 / 1 | 1 / 1 | 3 / 3 | remember / understand | 3 / 3 | 5 / 5 | 0.011 | 1.000 | 1 |

Diversity (cell): mean pairwise = **0.307**, max pairwise = **0.450**.

### 3.5 Naive arm, medium (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 2 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 3 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 4 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 5 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 6 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 7 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 8 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 9 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 10 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 11 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 12 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 13 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 14 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 15 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 16 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 17 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 18 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 19 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 20 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 21 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 22 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 23 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 24 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 25 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 26 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 27 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 28 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 29 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 30 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 31 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 32 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 33 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 34 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 35 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 36 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 37 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 38 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 39 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 40 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 41 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |
| 42 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 43 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 44 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 45 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 46 | 2 | 1 / 1 | 0 / 0 | comparative | causal / factual | 0 / 0 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 3 | 0.131 | 0.978 | 2 |
| 47 | 2 | 1 / 1 | 0 / 0 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | understand / understand | 4 / 3 | 5 / 5 | 0.079 | 0.900 | 2 |
| 48 | 2 | 2 / 2 | 1 / 1 | comparative | comparative / comparative | 1 / 1 | 1 / 1 | 3 / 4 | analyze / analyze | 2 / 2 | 3 / 2 | 0.065 | 0.940 | 2 |
| 49 | 2 | 2 / 2 | 1 / 1 | comparative | analytical / comparative | 0 / 1 | 1 / 1 | 3 / 4 | analyze / understand | 3 / 3 | 4 / 5 | 0.021 | 0.973 | 2 |
| 50 | 2 | 2 / 2 | 1 / 1 | comparative | causal / causal | 0 / 0 | 1 / 1 | 5 / 4 | understand / understand | 3 / 3 | 5 / 5 | 0.022 | 1.000 | 2 |

Diversity (cell): mean pairwise = **0.370**, max pairwise = **0.521**.

### 3.6 Naive arm, hard (50 questions)

| Q | CC | AC C / G | CM C / G | CR | AR C / G | RM C / G | AN C / G | PV C / G | BL C / G | CP C / G | CT C / G | LO | CL | RC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 2 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 3 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 4 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 5 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 6 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 7 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 8 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 9 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 10 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 11 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 12 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 13 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 14 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 15 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 16 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 17 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 18 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 19 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 20 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 21 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 22 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 23 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 24 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 25 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 26 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 27 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 28 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 29 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 30 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 31 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 32 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 33 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 34 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 35 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 36 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 37 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 38 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 39 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 40 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 41 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 42 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 43 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |
| 44 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 45 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 46 | 3 | 2 / 2 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | understand / understand | 3 / 3 | 4 / 5 | 0.058 | 0.627 | 3 |
| 47 | 3 | 1 / 1 | 0 / 0 | causal | inferential / analytical | 0 / 1 | 1 / 1 | 3 / 3 | analyze / understand | 3 / 3 | 3 / 5 | 0.101 | 0.688 | 3 |
| 48 | 3 | 3 / 2 | 1 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 4 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.048 | 0.682 | 3 |
| 49 | 3 | 2 / 1 | 0 / 0 | causal | causal / causal | 1 / 1 | 1 / 1 | 5 / 4 | analyze / understand | 3 / 3 | 5 / 5 | 0.034 | 0.945 | 3 |
| 50 | 3 | 1 / 1 | 0 / 0 | causal | inferential / causal | 0 / 1 | 1 / 1 | 4 / 4 | evaluate / understand | 3 / 3 | 4 / 5 | 0.024 | 0.650 | 3 |

Diversity (cell): mean pairwise = **0.488**, max pairwise = **0.583**.

---

## 4. Per-cell aggregates

The next two tables roll up each cell (50 questions) into mean values per judge.
Booleans are shown as rates in 0.0-1.0 (i.e. proportion of questions where the
flag was True). `figure_dependency_estimate` is **0.000 in every question across all
cells** and is therefore omitted from per-cell tables (constant zero).

### 4.1 Mix arm aggregates (means over 50 questions per cell)

| Metric | Easy | Medium | Hard |
|---|---|---|---|
| Mean retrieved chunks | 15.8 | 21.4 | 31.8 |
| Mean source lexical overlap | 0.0273 | 0.0710 | 0.0576 |
| Mean clarity heuristic | 1.000 | 0.848 | 0.788 |
| Complexity-match rate (Claude) | 1.000 | 1.000 | 0.800 |
| Complexity-match rate (GPT) | 1.000 | 0.200 | 0.400 |
| Reasoning-match rate (Claude) | 1.000 | 0.400 | 1.000 |
| Reasoning-match rate (GPT) | 1.000 | 0.400 | 1.000 |
| Answerable rate (Claude) | 1.000 | 1.000 | 0.800 |
| Answerable rate (GPT) | 1.000 | 1.000 | 0.800 |
| Mean pedagogical value (Claude, 0-1) | 0.640 | 0.760 | 0.800 |
| Mean pedagogical value (GPT, 0-1) | 0.760 | 0.800 | 0.840 |
| Mean answer completeness (Claude, 0-1) | 0.800 | 0.640 | 0.600 |
| Mean answer completeness (GPT, 0-1) | 0.920 | 0.640 | 0.600 |
| Mean answer correctness (Claude, 0-1) | 1.000 | 0.840 | 0.560\* |
| Mean answer correctness (GPT, 0-1) | 1.000 | 1.000 | 0.720 |
| Diversity: mean pairwise similarity | 0.305 | 0.354 | 0.603 |
| Diversity: max pairwise similarity | 0.557 | 0.717 | 0.779 |

\* Includes Claude's unscored mix_hard records (treated as 0). Excluding those,
Claude's correctness on mix_hard rises to 0.700.

### 4.2 Naive arm aggregates (means over 50 questions per cell)

| Metric | Easy | Medium | Hard |
|---|---|---|---|
| Mean retrieved chunks | 1.0 | 2.0 | 3.0 |
| Mean source lexical overlap | 0.0866 | 0.0638 | 0.0530 |
| Mean clarity heuristic | 1.000 | 0.958 | 0.719 |
| Complexity-match rate (Claude) | 1.000 | 0.600 | 0.200 |
| Complexity-match rate (GPT) | 1.000 | 0.600 | 0.000 |
| Reasoning-match rate (Claude) | 1.000 | 0.400 | 0.600 |
| Reasoning-match rate (GPT) | 1.000 | 0.600 | 1.000 |
| Answerable rate (Claude) | 1.000 | 1.000 | 1.000 |
| Answerable rate (GPT) | 1.000 | 1.000 | 1.000 |
| Mean pedagogical value (Claude, 0-1) | 0.680 | 0.720 | 0.800 |
| Mean pedagogical value (GPT, 0-1) | 0.680 | 0.800 | 0.760 |
| Mean answer completeness (Claude, 0-1) | 0.680 | 0.600 | 0.600 |
| Mean answer completeness (GPT, 0-1) | 0.640 | 0.560 | 0.600 |
| Mean answer correctness (Claude, 0-1) | 0.840 | 0.840 | 0.840 |
| Mean answer correctness (GPT, 0-1) | 0.920 | 0.800 | 1.000 |
| Diversity: mean pairwise similarity | 0.307 | 0.370 | 0.488 |
| Diversity: max pairwise similarity | 0.450 | 0.521 | 0.583 |

---

## 5. Direct head-to-head comparisons (mix minus naive)

The table below subtracts naive from mix at each difficulty, then over the whole
matrix. Positive numbers mean mix is higher. Rates (0.0-1.0) and 0-1 normalised
scores are directly comparable.

### 5.1 Easy

| Metric | Mix | Naive | Delta (mix - naive) |
|---|---|---|---|
| Complexity-match rate (Claude) | 1.000 | 1.000 | 0.000 |
| Complexity-match rate (GPT) | 1.000 | 1.000 | 0.000 |
| Reasoning-match rate (Claude) | 1.000 | 1.000 | 0.000 |
| Reasoning-match rate (GPT) | 1.000 | 1.000 | 0.000 |
| Answerable rate (Claude) | 1.000 | 1.000 | 0.000 |
| Answerable rate (GPT) | 1.000 | 1.000 | 0.000 |
| Pedagogical value (panel avg, 0-1) | 0.700 | 0.680 | +0.020 |
| Answer completeness (panel avg, 0-1) | 0.860 | 0.660 | +0.200 |
| Answer correctness (panel avg, 0-1) | 1.000 | 0.880 | +0.120 |
| Source lexical overlap | 0.0273 | 0.0866 | -0.0593 |
| Clarity heuristic | 1.000 | 1.000 | 0.000 |
| Retrieved chunks | 15.8 | 1.0 | +14.8 |
| Diversity: mean pairwise | 0.305 | 0.307 | -0.002 |
| Diversity: max pairwise | 0.557 | 0.450 | +0.107 |

Easy verdict: both arms hit a structural ceiling (perfect complexity / reasoning /
answerable). Mix produces measurably more complete (+0.20) and slightly more
correct (+0.12) answers. Mix questions also paraphrase the source more (lower lexical
overlap) but contain a near-duplicate pair (max pairwise 0.557 vs naive's 0.450).

### 5.2 Medium

| Metric | Mix | Naive | Delta (mix - naive) |
|---|---|---|---|
| Complexity-match rate (Claude) | 1.000 | 0.600 | +0.400 |
| Complexity-match rate (GPT) | 0.200 | 0.600 | -0.400 |
| Reasoning-match rate (Claude) | 0.400 | 0.400 | 0.000 |
| Reasoning-match rate (GPT) | 0.400 | 0.600 | -0.200 |
| Answerable rate (Claude) | 1.000 | 1.000 | 0.000 |
| Answerable rate (GPT) | 1.000 | 1.000 | 0.000 |
| Pedagogical value (panel avg, 0-1) | 0.780 | 0.760 | +0.020 |
| Answer completeness (panel avg, 0-1) | 0.640 | 0.580 | +0.060 |
| Answer correctness (panel avg, 0-1) | 0.920 | 0.820 | +0.100 |
| Source lexical overlap | 0.0710 | 0.0638 | +0.0072 |
| Clarity heuristic | 0.848 | 0.958 | -0.110 |
| Retrieved chunks | 21.4 | 2.0 | +19.4 |
| Diversity: mean pairwise | 0.354 | 0.370 | -0.016 |
| Diversity: max pairwise | 0.717 | 0.521 | +0.196 |

Medium verdict: claimed-vs-actual labelling disagrees sharply between judges. Claude
backs mix's claimed complexity (1.00 vs naive 0.60), GPT does the opposite (0.20 vs
0.60). Both judges agree reasoning is mislabeled at similar rates (mix often slides
to `analytical`/`inferential`; naive often slides to `causal`). Mix still wins on
pedagogy, completeness, and correctness. Mix has clearly worse clarity (-0.110)
and a near-duplicate pair (0.717).

### 5.3 Hard

| Metric | Mix | Naive | Delta (mix - naive) |
|---|---|---|---|
| Complexity-match rate (Claude) | 0.800 | 0.200 | +0.600 |
| Complexity-match rate (GPT) | 0.400 | 0.000 | +0.400 |
| Reasoning-match rate (Claude) | 1.000 | 0.600 | +0.400 |
| Reasoning-match rate (GPT) | 1.000 | 1.000 | 0.000 |
| Answerable rate (Claude) | 0.800 | 1.000 | -0.200 |
| Answerable rate (GPT) | 0.800 | 1.000 | -0.200 |
| Pedagogical value (panel avg, 0-1) | 0.820 | 0.780 | +0.040 |
| Answer completeness (panel avg, 0-1) | 0.600 | 0.600 | 0.000 |
| Answer correctness (panel avg, 0-1) | 0.640\* | 0.920 | -0.280 |
| Source lexical overlap | 0.0576 | 0.0530 | +0.0046 |
| Clarity heuristic | 0.788 | 0.719 | +0.069 |
| Retrieved chunks | 31.8 | 3.0 | +28.8 |
| Diversity: mean pairwise | 0.603 | 0.488 | +0.115 |
| Diversity: max pairwise | 0.779 | 0.583 | +0.196 |

\* Mix-hard correctness is depressed by Claude's unscored records (treated as 0).
Recomputed with those excluded, mix-hard panel-average correctness is 0.71, still
below naive's 0.92.

Hard verdict: this is the cell the matrix was designed to discriminate, and it does.
Mix wins decisively on complexity-match (Claude: +0.60, GPT: +0.40) — when the
pipeline claims `hard`, mix questions genuinely need 3 pieces of context and naive
questions usually need only 1-2. Mix also wins reasoning-match on Claude (+0.40).
However: (a) mix answerability dips to 0.80 (a fraction of questions where one judge
said the reference answer is not fully supported by context), (b) mix correctness
drops below naive (-0.28 panel avg), and (c) mix's quiz contains a near-duplicate
pair (0.779 max pairwise vs naive's 0.583).

### 5.4 Matrix-wide (all 150 questions per arm)

| Metric | Mix | Naive | Delta (mix - naive) |
|---|---|---|---|
| Complexity-match rate (Claude) | 0.933 | 0.600 | +0.333 |
| Complexity-match rate (GPT) | 0.533 | 0.533 | 0.000 |
| Reasoning-match rate (Claude) | 0.800 | 0.667 | +0.133 |
| Reasoning-match rate (GPT) | 0.800 | 0.867 | -0.067 |
| Answerable rate (Claude) | 0.933 | 1.000 | -0.067 |
| Answerable rate (GPT) | 0.933 | 1.000 | -0.067 |
| Pedagogical value (Claude, 0-1) | 0.733 | 0.733 | 0.000 |
| Pedagogical value (GPT, 0-1) | 0.800 | 0.747 | +0.053 |
| Answer completeness (Claude, 0-1) | 0.680 | 0.627 | +0.053 |
| Answer completeness (GPT, 0-1) | 0.720 | 0.600 | +0.120 |
| Answer correctness (Claude, 0-1) | 0.800 | 0.840 | -0.040 |
| Answer correctness (GPT, 0-1) | 0.907 | 0.907 | 0.000 |
| Pedagogical value (panel avg, 0-1) | 0.767 | 0.740 | +0.027 |
| Answer completeness (panel avg, 0-1) | 0.700 | 0.613 | +0.087 |
| Answer correctness (panel avg, 0-1) | 0.853 | 0.873 | -0.020 |
| Source lexical overlap | 0.0520 | 0.0678 | -0.0158 |
| Clarity heuristic | 0.879 | 0.892 | -0.013 |
| Retrieved chunks | 23.0 | 2.0 | +21.0 |
| Diversity: mean pairwise | 0.421 | 0.388 | +0.032 |
| Diversity: max pairwise | 0.685 | 0.518 | +0.167 |

---

## 6. Cross-arm difficulty trajectories

Tracking how each arm changes as difficulty escalates from easy to hard
(panel-averaged, 0-1 scale).

| Metric | Mix easy -> medium -> hard | Naive easy -> medium -> hard |
|---|---|---|
| Complexity-match (Claude) | 1.00 -> 1.00 -> 0.80 | 1.00 -> 0.60 -> 0.20 |
| Complexity-match (GPT) | 1.00 -> 0.20 -> 0.40 | 1.00 -> 0.60 -> 0.00 |
| Reasoning-match (Claude) | 1.00 -> 0.40 -> 1.00 | 1.00 -> 0.40 -> 0.60 |
| Reasoning-match (GPT) | 1.00 -> 0.40 -> 1.00 | 1.00 -> 0.60 -> 1.00 |
| Answerable (Claude) | 1.00 -> 1.00 -> 0.80 | 1.00 -> 1.00 -> 1.00 |
| Answerable (GPT) | 1.00 -> 1.00 -> 0.80 | 1.00 -> 1.00 -> 1.00 |
| Pedagogical value (panel) | 0.70 -> 0.78 -> 0.82 | 0.68 -> 0.76 -> 0.78 |
| Answer completeness (panel) | 0.86 -> 0.64 -> 0.60 | 0.66 -> 0.58 -> 0.60 |
| Answer correctness (panel) | 1.00 -> 0.92 -> 0.64* | 0.88 -> 0.82 -> 0.92 |
| Clarity heuristic | 1.00 -> 0.85 -> 0.79 | 1.00 -> 0.96 -> 0.72 |
| Retrieved chunks (mean) | 15.8 -> 21.4 -> 31.8 | 1.0 -> 2.0 -> 3.0 |
| Diversity: mean pairwise | 0.31 -> 0.35 -> 0.60 | 0.31 -> 0.37 -> 0.49 |
| Diversity: max pairwise | 0.56 -> 0.72 -> 0.78 | 0.45 -> 0.52 -> 0.58 |

\* Depressed by Claude's unscored mix_hard records (treated as 0). Without those,
the trajectory reads 1.00 -> 0.92 -> 0.71.

Key trajectory observations:
- **Pedagogical value rises with difficulty for both arms**, but mix climbs higher
  and ends higher (0.82 vs 0.78 at hard).
- **Completeness drops with difficulty**, with the biggest drop in mix
  (-0.26 easy->hard), because the harder questions demand multi-piece syntheses
  that the reference answers do not always fully cover.
- **Clarity degrades with difficulty** on both arms; mix's medium dip is larger
  than naive's, but mix's hard cell remains slightly clearer than naive's hard cell
  (0.79 vs 0.72).
- **Retrieved chunks grow as designed**: mix scales 16 -> 21 -> 32; naive scales
  1 -> 2 -> 3 — confirming the experimental knob was correctly applied.
- **Diversity tightens (gets worse) as difficulty increases**, more steeply for mix.
  Hard mix has a near-duplicate pair at 0.78 cosine similarity.

---

## 7. Inter-judge agreement

For every binary judgement, counting rows where Claude and GPT agree (over all
300 questions in the matrix).

| Field | Agreement rate | Notes |
|---|---|---|
| `answerable_from_context` | 0.933 (280/300) | Disagreements concentrate in mix_hard. |
| `claimed_reasoning_matches` | 0.900 (270/300) | Disagreements: a slice of naive_medium and naive_hard — all cases where Claude rejects a hard-claimed `causal` and GPT accepts `causal` or `analytical`. |
| `claimed_complexity_matches` | 0.767 (230/300) | Lowest agreement metric. Most disagreements are in mix_medium and mix_hard, where GPT consistently labels the actual complexity one step lower than Claude. |

For ordinal 1-5 metrics (`pedagogical_value`, `answer_completeness`, `answer_correctness`),
panel deltas |Claude - GPT| stay small in absolute terms:

| Metric | Mean abs diff (Claude vs GPT) over 300 Qs |
|---|---|
| Pedagogical value | 0.467 / 5.0 = 0.093 normalised |
| Answer completeness | 0.233 / 5.0 = 0.047 normalised |
| Answer correctness | 0.567 / 5.0 = 0.113 normalised (driven by Claude's unscored records in mix_hard and a handful of low scores in mix_medium and naive_medium) |

---

## 8. Combined verdict per dimension

A compact summary of which arm wins on each dimension across the matrix. "Wins" =
the arm with the higher value on a higher-is-better metric (or lower value on a
lower-is-better metric) at panel average, with the easy/medium/hard split.

| Dimension | Wins easy | Wins medium | Wins hard | Matrix-wide winner |
|---|---|---|---|---|
| Complexity-match (claimed vs actual) | Tie | Mixed (Claude: mix; GPT: naive) | Mix | **Mix** (large margin at hard) |
| Reasoning-match | Tie | Tie | Mix (Claude only) | **Mix** (small margin) |
| Answerable from context | Tie | Tie | Naive | **Naive** (mix dips at hard) |
| Pedagogical value | Mix | Mix | Mix | **Mix** (consistent small margin) |
| Answer completeness | Mix (+0.20) | Mix (+0.06) | Tie | **Mix** (driven by easy gap) |
| Answer correctness | Mix (+0.12) | Mix (+0.10) | Naive (-0.28) | **Roughly tied** — mix at easy/medium, naive at hard |
| Source lexical overlap (lower better) | Mix | Naive | Naive (-) | **Mix** at easy; naive at medium/hard |
| Clarity heuristic (higher better) | Tie | Naive | Mix | **Naive** (slight average margin) |
| Diversity: mean pairwise (lower better) | Tie | Mix | Naive | **Naive** at hard |
| Diversity: max pairwise (lower better) | Naive | Naive | Naive | **Naive** (all three cells) |

### 8.1 What this matrix actually shows

1. **The retrieval-depth knob works.** Mix scales from 16 -> 32 chunks; naive
   scales from 1 -> 3 chunks. Both arms reach perfect complexity-match at easy.
2. **Mix produces harder questions at the hard tier.** Complexity-match rates
   diverge most at hard: Claude scores mix at 0.80 vs naive at 0.20; GPT at 0.40 vs
   0.00. The matrix's whole point — separating multi-hop questions from
   single-passage ones — shows up here.
3. **Naive remains the safer arm for grounding.** Naive's answerable rate is 1.00
   in every cell; mix dips to 0.80 at hard. Naive's correctness is also higher at
   hard (panel avg 0.92 vs mix's 0.64-0.71).
4. **Pedagogical value and completeness favour mix overall**, but completeness
   collapses for both arms at medium/hard because reference answers compress
   multi-piece syntheses.
5. **Mix has a diversity problem at hard.** Mean pairwise similarity of 0.60 and
   max of 0.78 indicate the BFS is orbiting the same sub-graph at depth 3.
6. **The two judges disagree most on complexity labelling** (77% agreement),
   particularly for mix_medium where GPT consistently labels the actual context-need
   lower than Claude. This is the metric most worth careful follow-up before
   the human-rated subsample is locked.
7. **`figure_dependency_estimate` is 0.000 for every question across the matrix**,
   so it provides no signal here. Either the seeds avoided figure-dependent
   entities, or the heuristic's two triggers (figure-dependency phrase + cryptic
   short answer) were never both present enough to register; this needs revisiting
   once the seed distribution changes.

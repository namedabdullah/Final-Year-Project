# Quiz Feature — Implementation Plan

> **Companion document:** [`claude_review_rag_framework.md`](./claude_review_rag_framework.md). That doc defines *how difficulty works* (custom BFS, retrieval-vs-reasoning separation, verification, statistical plan). This doc defines *how the feature is built* (endpoint, page, navbar, storage, sequencing).

---

## 1. Overview

Add a **Quiz** tab to the WebUI, alongside Documents / Knowledge Graph / Retrieval / API. The page mirrors the Retrieval page visually (same flex layout, same sidebar pattern with mode + top_k + chunk_top_k + token budgets) and adds three new controls:

- **Document multi-select** — pick which uploaded documents the quiz is scoped to.
- **Number of questions** — dropdown: `10` / `25` / `50`.
- **Difficulty level** — dropdown: `easy` / `medium` / `hard`.

Submitting the form calls a new backend endpoint (`POST /quiz/generate`) that runs the difficulty-aware retrieval pipeline defined in the framework doc, generates questions with GPT-4o, optionally verifies them with Claude Sonnet, persists metadata as JSON, and returns the questions to the UI.

This feature serves two purposes:

1. **Thesis comparison data collection** — generate 50 questions per (mode × difficulty) cell across mix and naive modes → 300 questions total → statistical analysis per the framework's analysis plan.
2. **General quiz generation** — any user can pick documents, difficulty, and count to generate study questions on the fly.

For (1) the *thesis-rigorous* difficulty mechanics apply only in **mix** and **naive** modes (the framework's locked arms). Other modes (local / global / hybrid) are supported in the UI but use a coarser `top_k` scaling proxy — flagged with a tooltip so users know the difference.

---

## 2. User Flow

1. User clicks the **Quiz** tab in the navbar.
2. Page renders with the document list on the left as a checkbox table (reusing DocumentManager's pattern), the main content area in the middle, and the sidebar with all settings on the right (mirroring Retrieval).
3. User:
   - Selects one or more documents (checkbox).
   - Picks retrieval mode (default: `mix`).
   - Picks difficulty (default: `medium`).
   - Picks number of questions (default: `10`).
   - Optionally tweaks `top_k`, `chunk_top_k`, token budgets (same as Retrieval).
   - Toggles "Run verification" (default: `on`).
   - Clicks **Generate Quiz**.
4. Backend runs:
   - Resolves scope: only entities/chunks belonging to selected docs are eligible.
   - For each of N questions, runs the difficulty-aware retrieval pipeline (BFS for mix, top-k chunks for naive, mode-specific fallback for others).
   - Calls GPT-4o to generate (question, reference_answer) given the retrieved context + difficulty + reasoning-type prompt.
   - If verification is on, calls Claude Sonnet with the question + retrieved context + claimed metadata; verifier returns actual complexity, actual reasoning type, answerability, match flags.
   - Persists each question's metadata as a JSON record under `rag_storage/quizzes/{quiz_id}.json`.
5. Frontend renders the questions in the main area with per-question metadata (path / chunks used, reasoning type, verifier match), and provides:
   - **Download JSON** — full metadata file.
   - **Copy questions only** — plain text.
   - **Re-verify** — re-run the verifier on stored questions (cheap retry).

---

## 3. Difficulty Mechanics (Self-Contained Reference)

> Full rationale lives in `claude_review_rag_framework.md`. This section restates the mechanics that the implementation must enforce.

### 3.1 Difficulty is two-dimensional

| Dimension | Source |
|---|---|
| **Retrieval complexity** | Structural — controlled at retrieval time (hops or chunks) |
| **Reasoning complexity** | Cognitive — controlled at prompt time (factual / comparative / causal / inferential / analytical) |

A "hard" question must satisfy *both* dimensions: retrieved from a structurally rich context AND prompted to require multi-step reasoning. Neither alone is sufficient — see the framework doc's "1-hop but cognitively hard" and "3-hop but cognitively easy" examples.

### 3.2 Per-mode retrieval rules

**`mix` mode (graph arm of the thesis comparison) — rigorous:**

| Difficulty | Hops (BFS depth) | Vector chunks | Reasoning type |
|---|---|---|---|
| easy | 1 | 5 (constant) | factual |
| medium | 2 | 5 (constant) | comparative |
| hard | 3 | 5 (constant) | causal / inferential / analytical |

Chunks are constant at 5 across difficulties so the difficulty signal is attributable to graph traversal depth, not chunk volume. (Locked decision.)

The retrieval algorithm:
1. Extract keywords from the seed query (reuse LightRAG's `extract_keywords_only` from `operate.py`).
2. Resolve BFS entry points via `entities_vdb.query(keywords, top_k=5)`.
3. Run BFS at `depth = {easy: 1, medium: 2, hard: 3}` over `chunk_entity_relation_graph`, restricted to entities whose source chunks belong to the selected document set, with a **per-depth cap of 5** (top-K by query relevance) to prevent subgraph explosion at depth 3.
4. Pull chunks associated with the BFS subgraph via entity `source_id` fields.
5. Add 5 constant vector chunks via `chunks_vdb.query(query, top_k=5)` (also scope-filtered).
6. Return `RetrievalContext(entities, relations, bfs_path, chunks, hop_depth)`.

**`naive` mode (naive arm of the thesis comparison) — rigorous:**

| Difficulty | Chunks | Reasoning type |
|---|---|---|
| easy | 1 | factual |
| medium | 2 | comparative |
| hard | 3 | causal / inferential / analytical |

Retrieval:
1. `chunks_vdb.query(query, top_k=k)` where `k = {easy: 1, medium: 2, hard: 3}`.
2. Scope-filter results to selected documents.
3. Return `RetrievalContext(chunks, chunk_count)`.

**`local` / `global` / `hybrid` modes — coarse fallback (not thesis-rigorous):**

These modes do not implement custom BFS. They use LightRAG's standard `aquery()` with `top_k` scaled by difficulty as a proxy:

| Difficulty | `top_k` | `chunk_top_k` | Reasoning type |
|---|---|---|---|
| easy | 10 | 3 | factual |
| medium | 30 | 5 | comparative |
| hard | 60 | 10 | causal / inferential / analytical |

A tooltip on the difficulty selector warns: *"Rigorous difficulty mechanics apply only in mix and naive modes. Other modes use top_k scaling as a coarse proxy and should not be used for thesis-grade comparison."*

### 3.3 Prompt-layer reasoning constraint

For all modes, the prompt sent to the generator enforces the reasoning type. Prompts are exactly those defined in the framework doc:

- **Easy:** factual reasoning only, no synthesis required.
- **Medium:** comparative reasoning, synthesis across at least 2 context pieces.
- **Hard:** causal / inferential / analytical reasoning, synthesis across at least 3 context pieces, no direct fact lookup.

### 3.4 Seed query

The retrieval pipeline needs a "seed query" to bootstrap keyword extraction / entity-vdb lookup / chunk search. For the quiz feature there's no user-typed query — so we synthesize seed queries internally:

- For each of N questions, sample a *seed topic* from the selected documents. Two strategies, switchable:
  - **Entity-sampling seed** (default for mix): pick a random entity from the selected docs' entity set (weighted by degree centrality, so well-connected entities are more likely seeds). The seed query is `entity_name`.
  - **Chunk-sampling seed** (default for naive): pick a random chunk from the selected docs, take its first sentence as the seed query.

This is described in §5.4. It's a deliberate design choice — not user-facing — and is logged in metadata.

### 3.5 Verification (Claude Sonnet)

If enabled (default on), each generated (question, answer) tuple is sent to Claude Sonnet with the retrieved context + claimed metadata. Verifier returns:

```json
{
  "actual_retrieval_complexity": <int>,
  "actual_reasoning_type": "<one of the 6 types>",
  "answerable_from_context": <bool>,
  "claimed_complexity_matches": <bool>,
  "claimed_reasoning_matches": <bool>,
  "notes": "<one-sentence rationale>"
}
```

These fields are merged into the per-question metadata record.

---

## 4. Frontend Implementation

All paths under `D:/FYP/LightRAG/lightrag_webui/`.

### 4.1 Navbar tab

Add a new tab between **Retrieval** and **API**.

| File | Change |
|---|---|
| `src/stores/settings.ts` (line 9) | Extend `type Tab = 'documents' \| 'knowledge-graph' \| 'retrieval' \| 'quiz' \| 'api'` |
| `src/features/SiteHeader.tsx` (lines 34–56, `TabsNavigation()`) | Add a `<TabsTrigger value="quiz">` with i18n key `header.quiz` |
| `src/App.tsx` (lines 202, 209–220) | Add a `<TabsContent value="quiz">` rendering `<QuizGeneration />` |
| `src/AppRouter.tsx` (lines 69–75) | Add a `<Route path="/quiz" element={<QuizGeneration />} />` if routing is used directly |

### 4.2 Page component

**New file:** `src/features/QuizGeneration.tsx`

Layout structure mirrors `RetrievalTesting.tsx`:

```tsx
<div className="flex h-full gap-4">
  {/* Left: document selector (new) */}
  <QuizDocumentSelector />

  {/* Middle: generated questions area */}
  <div className="flex-1 flex flex-col">
    <QuizResultsList questions={questions} />
    <QuizForm onSubmit={generate} />
  </div>

  {/* Right: settings sidebar */}
  <QuizSettings />
</div>
```

**Components to build:**

| Component | Path | Purpose |
|---|---|---|
| `QuizGeneration` | `src/features/QuizGeneration.tsx` | Top-level page |
| `QuizSettings` | `src/components/quiz/QuizSettings.tsx` | Right sidebar — copy of `QuerySettings.tsx` + new fields |
| `QuizDocumentSelector` | `src/components/quiz/QuizDocumentSelector.tsx` | Left panel — checkbox table reusing DocumentManager's patterns |
| `QuizResultsList` | `src/components/quiz/QuizResultsList.tsx` | Middle area — renders generated questions with metadata badges |
| `QuizForm` | `src/components/quiz/QuizForm.tsx` | Generate button + status indicator |

### 4.3 `QuizSettings.tsx` — sidebar fields

Start from a copy of `src/components/retrieval/QuerySettings.tsx`. Keep all existing fields (mode, top_k, chunk_top_k, max_entity_tokens, max_relation_tokens, max_total_tokens, response_type, user_prompt, enable_rerank). Add:

```tsx
// New section: Quiz Settings

<Select value={difficulty} onValueChange={setDifficulty}>
  <SelectItem value="easy">{t('quizPanel.settings.difficultyEasy')}</SelectItem>
  <SelectItem value="medium">{t('quizPanel.settings.difficultyMedium')}</SelectItem>
  <SelectItem value="hard">{t('quizPanel.settings.difficultyHard')}</SelectItem>
</Select>

<Select value={numQuestions} onValueChange={setNumQuestions}>
  <SelectItem value="10">10</SelectItem>
  <SelectItem value="25">25</SelectItem>
  <SelectItem value="50">50</SelectItem>
</Select>

<Checkbox checked={runVerification} onCheckedChange={setRunVerification}>
  {t('quizPanel.settings.runVerification')}
</Checkbox>
```

Tooltip on the mode field when value is `local`/`global`/`hybrid`:

> "Rigorous difficulty mechanics apply only in mix and naive modes. Other modes use top_k scaling as a coarse proxy."

### 4.4 Settings store extension

**File:** `src/stores/settings.ts`

Add a new persistent slice:

```ts
quizSettings: {
  selectedDocumentIds: string[]
  difficulty: 'easy' | 'medium' | 'hard'
  numQuestions: 10 | 25 | 50
  runVerification: boolean
  // mode + top_k + chunk_top_k + etc. reuse querySettings (read-through)
}
updateQuizSettings: (partial: Partial<QuizSettings>) => void
```

Defaults: `difficulty: 'medium'`, `numQuestions: 10`, `runVerification: true`, `selectedDocumentIds: []`.

### 4.5 API client

**File:** `src/api/lightrag.ts`

Add the function and types:

```ts
export interface QuizGenerateRequest {
  document_ids: string[]
  mode: 'local' | 'global' | 'hybrid' | 'mix' | 'naive'
  difficulty: 'easy' | 'medium' | 'hard'
  num_questions: 10 | 25 | 50
  run_verification: boolean
  // Optional overrides for advanced users — same fields as QueryRequest
  top_k?: number
  chunk_top_k?: number
  max_entity_tokens?: number
  max_relation_tokens?: number
  max_total_tokens?: number
  user_prompt?: string
}

export interface QuizQuestion {
  question_id: string
  question: string
  reference_answer: string
  difficulty: string
  claimed_retrieval_complexity: number
  claimed_reasoning_type: string
  retrieval: {
    entities?: string[]
    relations?: { source: string; target: string; type: string }[]
    bfs_path?: string[]
    chunk_ids: string[]
    hop_depth: number | null
    source_documents: string[]
  }
  generation: { model: string; prompt_template_id: string }
  verification?: {
    model: string
    actual_retrieval_complexity: number
    actual_reasoning_type: string
    answerable_from_context: boolean
    claimed_complexity_matches: boolean
    claimed_reasoning_matches: boolean
    notes: string
  }
}

export interface QuizGenerateResponse {
  quiz_id: string
  questions: QuizQuestion[]
  metadata_path: string  // server-side path for archival
}

export async function generateQuiz(req: QuizGenerateRequest): Promise<QuizGenerateResponse> {
  // POST /quiz/generate
}

export async function listQuizzes(): Promise<{ quiz_id: string; created_at: string; ... }[]> {
  // GET /quiz/list
}

export async function getQuiz(quiz_id: string): Promise<QuizGenerateResponse> {
  // GET /quiz/{quiz_id}
}
```

### 4.6 i18n keys

**Files:** `src/locales/en.json` (and all other locale files, English-only initially).

Add a `quizPanel` namespace:

```json
{
  "header": {
    "quiz": "Quiz"
  },
  "quizPanel": {
    "settings": {
      "difficultyTitle": "Difficulty",
      "difficultyEasy": "Easy (1-hop / 1-chunk, factual)",
      "difficultyMedium": "Medium (2-hop / 2-chunk, comparative)",
      "difficultyHard": "Hard (3-hop / 3-chunk, causal+)",
      "numQuestionsTitle": "Number of Questions",
      "runVerification": "Run verification (Claude Sonnet)",
      "modeWarning": "Rigorous difficulty applies only in mix and naive modes."
    },
    "documentSelector": {
      "title": "Documents",
      "selectAll": "Select all",
      "selectedCount": "{{count}} selected"
    },
    "results": {
      "generating": "Generating {{n}} questions...",
      "verifying": "Verifying...",
      "downloadJson": "Download metadata (JSON)",
      "copyQuestions": "Copy questions only"
    }
  }
}
```

Add the same keys to the other 10 locale files with `en.json` values as placeholders (translation can come later).

---

## 5. Backend Implementation

All paths under `D:/FYP/LightRAG/lightrag/`.

### 5.1 New module: `lightrag/quiz/`

Create a dedicated module:

```
lightrag/quiz/
├── __init__.py
├── schemas.py        # Pydantic models for request/response/metadata
├── retrieval.py      # Difficulty-aware retrieval (BFS for mix, controlled chunks for naive, fallback for others)
├── generation.py     # GPT-4o call + prompt templates
├── verification.py   # Claude Sonnet verifier
├── seeds.py          # Seed query sampling (entity-weighted, chunk-sampled)
├── storage.py        # Per-quiz JSON persistence under rag_storage/quizzes/
└── pipeline.py       # Top-level orchestrator: generate_quiz()
```

This keeps quiz logic out of `operate.py` (which is already large) and isolated from LightRAG's core API.

### 5.2 New router: `lightrag/api/routers/quiz_routes.py`

Pattern follows `query_routes.py` (the closest neighbor):

```python
def create_quiz_routes(rag: LightRAG, api_key: Optional[str] = None) -> APIRouter:
    router = APIRouter(prefix="/quiz", tags=["quiz"])
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post("/generate", dependencies=[Depends(combined_auth)])
    async def generate(req: QuizGenerateRequest) -> QuizGenerateResponse:
        return await quiz_pipeline.generate_quiz(rag, req)

    @router.get("/list", dependencies=[Depends(combined_auth)])
    async def list_quizzes() -> list[QuizSummary]:
        return await quiz_storage.list_quizzes(rag.working_dir)

    @router.get("/{quiz_id}", dependencies=[Depends(combined_auth)])
    async def get_quiz(quiz_id: str) -> QuizGenerateResponse:
        return await quiz_storage.load_quiz(rag.working_dir, quiz_id)

    @router.post("/{quiz_id}/verify", dependencies=[Depends(combined_auth)])
    async def reverify(quiz_id: str) -> QuizGenerateResponse:
        return await quiz_pipeline.reverify_quiz(rag, quiz_id)

    return router
```

### 5.3 Server registration

**File:** `lightrag/api/lightrag_server.py` (lines 2012–2014, where other routers are included)

```python
from lightrag.api.routers.quiz_routes import create_quiz_routes
...
app.include_router(create_quiz_routes(rag, api_key))
```

### 5.4 Pydantic schemas — `lightrag/quiz/schemas.py`

```python
class QuizGenerateRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    mode: Literal["local", "global", "hybrid", "mix", "naive"] = "mix"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    num_questions: Literal[10, 25, 50] = 10
    run_verification: bool = True

    # Optional overrides (None = use mode-default)
    top_k: Optional[int] = None
    chunk_top_k: Optional[int] = None
    max_entity_tokens: Optional[int] = None
    max_relation_tokens: Optional[int] = None
    max_total_tokens: Optional[int] = None
    user_prompt: Optional[str] = None


class QuizQuestionMetadata(BaseModel):
    question_id: str
    arm: Literal["graph", "naive", "other"]
    difficulty: Literal["easy", "medium", "hard"]

    claimed_retrieval_complexity: int
    claimed_reasoning_type: str

    retrieval: RetrievalMetadata
    generation: GenerationMetadata
    verification: Optional[VerificationMetadata] = None
    human_rating: Optional[HumanRatingMetadata] = None


class QuizGenerateResponse(BaseModel):
    quiz_id: str
    created_at: datetime
    request: QuizGenerateRequest
    questions: list[QuizQuestionMetadata]
    metadata_path: str
```

Submodels (`RetrievalMetadata`, `GenerationMetadata`, `VerificationMetadata`, `HumanRatingMetadata`) match exactly the framework's `Metadata Schema (Comprehensive)` section.

### 5.5 Retrieval layer — `lightrag/quiz/retrieval.py`

Implements the three retrieval variants:

```python
async def retrieve_mix_arm(
    rag: LightRAG,
    seed_query: str,
    difficulty: str,
    scope_doc_ids: set[str],
) -> RetrievalContext:
    """Custom BFS for the graph/mix arm. See framework §Graph Retrieval Controller."""
    hops = {"easy": 1, "medium": 2, "hard": 3}[difficulty]

    keywords = await extract_keywords_only(seed_query, rag)
    entry_entities = await rag.entities_vdb.query(" ".join(keywords), top_k=5)
    entry_entities = filter_by_scope(entry_entities, scope_doc_ids)  # only seed from selected docs

    subgraph = await bfs_subgraph(
        graph=rag.chunk_entity_relation_graph,
        start_nodes=[e["entity_name"] for e in entry_entities],
        max_depth=hops,
        per_depth_cap=5,
        scope_filter=lambda node: node_in_scope(node, scope_doc_ids),
    )

    entity_chunks = await fetch_chunks_for_entities(rag, subgraph.entities)
    extra_chunks = await rag.chunks_vdb.query(seed_query, top_k=5)
    extra_chunks = filter_chunks_by_scope(extra_chunks, scope_doc_ids)

    return RetrievalContext(
        entities=subgraph.entities,
        relations=subgraph.relations,
        bfs_path=subgraph.path,
        chunks=dedupe(entity_chunks + extra_chunks),
        hop_depth=hops,
    )


async def retrieve_naive_arm(
    rag: LightRAG,
    seed_query: str,
    difficulty: str,
    scope_doc_ids: set[str],
) -> RetrievalContext:
    """Naive vector retrieval with controlled k. See framework §Naive Retrieval Controller."""
    k = {"easy": 1, "medium": 2, "hard": 3}[difficulty]
    chunks = await rag.chunks_vdb.query(seed_query, top_k=k * 3)  # overscan then filter
    chunks = filter_chunks_by_scope(chunks, scope_doc_ids)[:k]
    return RetrievalContext(chunks=chunks, chunk_count=len(chunks))


async def retrieve_fallback(
    rag: LightRAG,
    seed_query: str,
    mode: str,
    difficulty: str,
    scope_doc_ids: set[str],
) -> RetrievalContext:
    """Coarse top_k scaling for local/global/hybrid. Not thesis-rigorous."""
    top_k = {"easy": 10, "medium": 30, "hard": 60}[difficulty]
    chunk_top_k = {"easy": 3, "medium": 5, "hard": 10}[difficulty]
    # Call LightRAG's standard query path. Scope filtering applied post-hoc.
    ...
```

#### BFS implementation note

`bfs_subgraph` is new code. It must:
- Use the graph storage's adjacency API (NetworkX default exposes `.neighbors()`; the abstract `BaseGraphStorage` has `get_edges()`).
- Cap per-depth expansion to top 5 by query relevance (rank candidate nodes by their entity vector similarity to the seed query, or by chunk overlap with the seed).
- Track the path: at each depth, record `(parent → child)` edges so the metadata `bfs_path` field can be populated.
- Skip nodes outside `scope_doc_ids`.

### 5.6 Seed sampling — `lightrag/quiz/seeds.py`

Each of N questions needs a distinct seed so we don't generate N copies of the same question.

```python
async def sample_seeds(
    rag: LightRAG,
    mode: str,
    n: int,
    scope_doc_ids: set[str],
) -> list[str]:
    if mode == "mix":
        # Entity-weighted sampling by degree centrality
        entities = await list_entities_in_scope(rag, scope_doc_ids)
        weights = await compute_degree_centrality(rag, entities)
        sampled = weighted_sample_without_replacement(entities, weights, n)
        return [e["entity_name"] for e in sampled]

    if mode == "naive":
        # First-sentence-of-random-chunk
        chunks = await list_chunks_in_scope(rag, scope_doc_ids)
        sampled = random.sample(chunks, min(n, len(chunks)))
        return [first_sentence(c["content"]) for c in sampled]

    # Other modes — same as naive
    return await sample_seeds(rag, "naive", n, scope_doc_ids)
```

If `n > available_entities/chunks`, fall back to sampling with replacement and warn in the response.

### 5.7 Generation — `lightrag/quiz/generation.py`

Wraps a GPT-4o call. Prompt templates live as constants:

```python
PROMPT_TEMPLATES = {
    "easy": "Generate one quiz question answerable directly...",   # full text from framework
    "medium": "Generate one quiz question that requires comparing...",
    "hard": "Generate one quiz question requiring multi-step reasoning...",
}

async def generate_question(
    context: RetrievalContext,
    difficulty: str,
    model: str = "gpt-4o",
) -> tuple[str, str]:
    """Returns (question, reference_answer)."""
    prompt = PROMPT_TEMPLATES[difficulty]
    formatted_context = format_context_for_prompt(context)
    response = await call_openai(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": formatted_context},
        ],
        response_format={"type": "json_object"},
    )
    return parse_question_answer(response)
```

Use OpenAI's structured-output / JSON mode to guarantee parseable responses.

GPT-4o credentials come from the same `OPENAI_API_KEY` env var LightRAG already uses for OpenAI bindings — see `lightrag/llm/openai.py`. No new config needed.

### 5.8 Verification — `lightrag/quiz/verification.py`

```python
async def verify_question(
    question: str,
    reference_answer: str,
    context: RetrievalContext,
    claimed: ClaimedMetadata,
    model: str = "claude-sonnet-4-6",
) -> VerificationMetadata:
    prompt = build_verifier_prompt(question, reference_answer, context, claimed)
    response = await call_anthropic(model=model, prompt=prompt)
    return parse_verifier_response(response)
```

Verifier prompt is the grounded version from the framework's §Verification Prompt. Anthropic credentials come from `ANTHROPIC_API_KEY` (already used by `lightrag/llm/anthropic.py`).

### 5.9 Pipeline orchestrator — `lightrag/quiz/pipeline.py`

```python
async def generate_quiz(rag: LightRAG, req: QuizGenerateRequest) -> QuizGenerateResponse:
    quiz_id = str(uuid.uuid4())
    scope_doc_ids = set(req.document_ids)
    seeds = await sample_seeds(rag, req.mode, req.num_questions, scope_doc_ids)

    questions = []
    for seed in seeds:
        # 1. Retrieve
        if req.mode == "mix":
            ctx = await retrieve_mix_arm(rag, seed, req.difficulty, scope_doc_ids)
            arm = "graph"
        elif req.mode == "naive":
            ctx = await retrieve_naive_arm(rag, seed, req.difficulty, scope_doc_ids)
            arm = "naive"
        else:
            ctx = await retrieve_fallback(rag, seed, req.mode, req.difficulty, scope_doc_ids)
            arm = "other"

        # 2. Generate
        question, answer = await generate_question(ctx, req.difficulty)

        # 3. Build metadata
        meta = build_question_metadata(quiz_id, arm, req.difficulty, ctx, question, answer)

        # 4. Verify (optional)
        if req.run_verification:
            meta.verification = await verify_question(question, answer, ctx, meta.claimed())

        questions.append(meta)

    # 5. Persist
    metadata_path = await save_quiz(rag.working_dir, quiz_id, req, questions)

    return QuizGenerateResponse(
        quiz_id=quiz_id, created_at=datetime.utcnow(),
        request=req, questions=questions, metadata_path=metadata_path,
    )
```

Run questions concurrently (`asyncio.gather`) with a configurable concurrency cap (default 5) to keep API rate limits sane.

### 5.10 Storage — `lightrag/quiz/storage.py`

One JSON file per quiz at `{rag.working_dir}/quizzes/{quiz_id}.json`. The directory is created on demand. List endpoint scans the directory and returns summary metadata; load endpoint reads and returns the full record.

```python
async def save_quiz(working_dir: str, quiz_id: str, req: QuizGenerateRequest,
                    questions: list[QuizQuestionMetadata]) -> str:
    path = Path(working_dir) / "quizzes" / f"{quiz_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = QuizGenerateResponse(...).model_dump_json(indent=2)
    path.write_text(payload, encoding="utf-8")
    return str(path)
```

For workspace-aware deployments, prefix the directory with the workspace name (mirrors LightRAG's existing pattern for file-based storage).

### 5.11 Auth

Every quiz endpoint uses `dependencies=[Depends(combined_auth)]` from `lightrag/api/utils_api.py` — same as `query_routes.py`.

---

## 6. Document Scoping

Selected documents drive a scope filter applied at *every* retrieval step. This prevents entities/chunks from non-selected docs leaking into the quiz.

### 6.1 Resolving the scope

User supplies `document_ids: list[str]` in the request. From this we derive:

- `scope_chunk_ids: set[str]` — all chunks whose `full_doc_id` is in `document_ids`.
- `scope_entity_names: set[str]` — all entities whose `source_id` includes any chunk in `scope_chunk_ids`.

Both are computed once at the start of `generate_quiz` and reused.

### 6.2 Where scope filtering is applied

| Step | Filter |
|---|---|
| Seed sampling (entity-weighted) | Sample only from `scope_entity_names` |
| Seed sampling (chunk-based) | Sample only from `scope_chunk_ids` |
| `entities_vdb.query` results | Keep only entities in `scope_entity_names` |
| `chunks_vdb.query` results | Keep only chunks in `scope_chunk_ids` |
| BFS expansion | At each depth, skip neighbors not in `scope_entity_names` |

Note on graph traversal: BFS *can* still cross document boundaries — but only within the selected set. This preserves graph mode's cross-document advantage while keeping the quiz scoped.

### 6.3 Edge cases

| Case | Behavior |
|---|---|
| `document_ids` empty | Return 400 — explicit selection required |
| Some IDs unknown | Return 404 with list of unknown IDs |
| Scope yields <N entities/chunks for seeding | Fall back to sampling-with-replacement, warn in response |
| BFS produces empty subgraph (rare) | Skip seed, try next; if all N fail, return partial quiz + warning |

---

## 7. Storage & Persistence

### 7.1 On-disk layout

```
{working_dir}/
└── quizzes/
    ├── {quiz_id_1}.json
    ├── {quiz_id_2}.json
    └── ...
```

Each file is a `QuizGenerateResponse` JSON with full per-question metadata (see framework's `Metadata Schema (Comprehensive)`).

### 7.2 Why filesystem, not the DB

- Simple, transparent, easy to inspect during thesis development.
- No schema migration when metadata fields evolve.
- Each quiz is a self-contained record — good for sharing / archival / appendix in the thesis report.
- If scale becomes an issue (>10k quizzes), migration to a KV store is straightforward.

### 7.3 No metadata mutation in place

When `POST /quiz/{quiz_id}/verify` re-runs verification, write to a versioned filename (`{quiz_id}.v2.json`) and update the index — never overwrite the original. This preserves the audit trail.

---

## 8. API Contract

### 8.1 `POST /quiz/generate`

**Request:**
```json
{
  "document_ids": ["doc-abc", "doc-def"],
  "mode": "mix",
  "difficulty": "hard",
  "num_questions": 25,
  "run_verification": true
}
```

**Response (200):**
```json
{
  "quiz_id": "uuid",
  "created_at": "2026-05-25T...",
  "request": { /* echoed */ },
  "questions": [
    {
      "question_id": "uuid",
      "arm": "graph",
      "difficulty": "hard",
      "claimed_retrieval_complexity": 3,
      "claimed_reasoning_type": "causal",
      "retrieval": {
        "entities": ["TCP", "Packet Loss", "Video Streaming"],
        "relations": [{"source": "TCP", "target": "Packet Loss", "type": "causes"}],
        "bfs_path": ["TCP", "Packet Loss", "Video Streaming"],
        "chunk_ids": ["..."],
        "hop_depth": 3,
        "source_documents": ["doc-abc", "doc-def"]
      },
      "generation": {
        "model": "gpt-4o",
        "prompt_template_id": "hard_v1",
        "question": "Why might UDP be preferred over TCP in live video streaming despite packet loss risks?",
        "reference_answer": "..."
      },
      "verification": {
        "model": "claude-sonnet-4-6",
        "actual_retrieval_complexity": 3,
        "actual_reasoning_type": "causal",
        "answerable_from_context": true,
        "claimed_complexity_matches": true,
        "claimed_reasoning_matches": true,
        "notes": "..."
      }
    }
  ],
  "metadata_path": "rag_storage/quizzes/{quiz_id}.json"
}
```

### 8.2 `GET /quiz/list`

Returns `[{ quiz_id, created_at, request_summary, question_count, verifier_pass_rate }]`.

### 8.3 `GET /quiz/{quiz_id}`

Returns the full `QuizGenerateResponse` (same shape as the generate response).

### 8.4 `POST /quiz/{quiz_id}/verify`

Re-runs Claude Sonnet verification on a stored quiz (cheap retry if the verifier was off originally or failed). Writes a new versioned record and returns it.

### 8.5 Error responses

- `400` — invalid request (empty `document_ids`, invalid mode/difficulty)
- `404` — unknown document IDs or quiz ID
- `422` — Pydantic validation failed
- `500` — LLM call failed (retryable; returns partial questions if some succeeded)
- `503` — rate limited by OpenAI/Anthropic (returns partial questions)

---

## 9. Thesis Comparison Workflow

Once the feature is live, the 300-question dataset (per framework §Experimental Matrix) is built by running:

| Run | Mode | Difficulty | Count |
|---|---|---|---|
| 1 | `mix` | easy | 50 |
| 2 | `mix` | medium | 50 |
| 3 | `mix` | hard | 50 |
| 4 | `naive` | easy | 50 |
| 5 | `naive` | medium | 50 |
| 6 | `naive` | hard | 50 |

All six runs use the same `document_ids`. Each yields a quiz JSON under `rag_storage/quizzes/`. A small offline analysis script (separate, not in scope of this plan) aggregates the six JSONs and runs the statistical tests from the framework's §Statistical Analysis Plan.

The human-rated subsample (~50 stratified questions) is handled outside the UI for v1 — export the quizzes as JSON, rate them in a spreadsheet, merge ratings back via a CLI. A future UI iteration can add an in-app rating interface.

---

## 10. Implementation Sequence

Suggested phasing — each phase is independently testable.

### Phase 1 — Backend skeleton (no LLM calls)
- Create `lightrag/quiz/` module with stubs for retrieval, generation, verification, storage.
- Create `quiz_routes.py` and wire it into `lightrag_server.py`.
- `POST /quiz/generate` returns a hardcoded mock response.
- **Acceptance:** can hit the endpoint with curl and get a valid `QuizGenerateResponse`.

### Phase 2 — Frontend skeleton
- Extend `Tab` type, add navbar entry, route, page component.
- Build `QuizSettings` (copy of `QuerySettings` + new fields) and `QuizDocumentSelector`.
- Wire to the mock backend endpoint.
- **Acceptance:** navigate to Quiz tab, see the page, select docs, click Generate, see mock questions render.

### Phase 3 — Retrieval logic (the framework's locked decisions)
- Implement `retrieve_naive_arm` (easiest — just `chunks_vdb.query` with scope filtering).
- Implement `bfs_subgraph` + `retrieve_mix_arm`.
- Implement seed sampling.
- Implement `retrieve_fallback` for local/global/hybrid.
- **Acceptance:** unit tests for each retrieval function; manual verification that BFS at depth 3 returns plausible subgraphs.

### Phase 4 — Generation
- Implement `generate_question` with GPT-4o.
- Wire prompt templates exactly as in framework §Easy/Medium/Hard Prompts.
- Connect pipeline end-to-end: generate quiz → see real questions in UI.
- **Acceptance:** generate a 10-question easy quiz from a small doc set; questions are plausible and grounded in the docs.

### Phase 5 — Verification
- Implement `verify_question` with Claude Sonnet.
- Build the grounded verifier prompt per framework §Verification Prompt.
- Wire `run_verification` toggle; persist verification metadata.
- **Acceptance:** generate a quiz with verification on; verifier metadata is populated and plausible.

### Phase 6 — Persistence + list/get/reverify endpoints
- Implement `save_quiz`, `list_quizzes`, `load_quiz`, `reverify`.
- Add quiz-history UI (optional in v1 — can be Phase 7).
- **Acceptance:** generate a quiz, restart the server, retrieve it via `GET /quiz/{id}`.

### Phase 7 — Thesis data collection
- Run the 6 quiz generations (mix×{e,m,h}, naive×{e,m,h}, 50 each).
- Export JSON metadata.
- Write the offline analysis script (separate task).
- Pull the stratified ~50-question human-rating sample, rate in a spreadsheet, compute Cohen's κ.

### Phase 8 — Polish (optional)
- Streaming generation (SSE) so questions appear one-by-one rather than all at once.
- In-app human-rating interface.
- MCQ support (unlocks KG-distractor analysis from framework §Open Items).
- Mixed-difficulty quizzes (single run produces 10 easy + 25 medium + 15 hard, for example).

---

## 11. Open Decisions (deferred from framework)

These were flagged in the framework doc's §Open Items and remain unresolved. They do not block Phase 1–2 but must be answered before Phase 3.

| Item | Working default | Where it lives in this plan |
|---|---|---|
| Corpus | Whatever is in current `rag_storage/` | The UI lets the user pick docs from whatever's loaded — no separate "corpus" decision needed for the *feature*; the *thesis* decision is which docs to use for the 6 runs. |
| Question format | Short-answer (SAQ) | Phase 4. MCQ deferred to Phase 8. |
| BFS per-depth cap | Top 5 entities per depth | Phase 3. Tunable based on observed subgraph sizes. |

---

## 12. Non-Goals (v1)

Explicitly *not* in scope for the initial implementation — flagged here to prevent scope creep:

- **In-UI human rating** — humans rate via exported JSON / spreadsheet in v1.
- **Quiz-history page with search/filter** — basic list is fine for v1.
- **Streaming question generation** — synchronous batch is fine for v1.
- **MCQ with KG-mined distractors** — SAQ only in v1.
- **Mixed-difficulty quizzes in one run** — separate runs per difficulty in v1.
- **Quiz sharing / public links** — local-only in v1.
- **Quiz re-takes / scoring** — generation only; no test-taking UX in v1.

---

## 13. Cross-References

- **Difficulty definitions, prompts, verification protocol, metadata schema:** [`claude_review_rag_framework.md`](./claude_review_rag_framework.md)
- **LightRAG module layout:** `AGENTS.md` § *Module Layout*
- **WebUI testing conventions:** `AGENTS.md` § *Frontend Debugging via Playwright*
- **Auth pattern:** `lightrag/api/utils_api.py` :: `get_combined_auth_dependency`
- **Template router:** `lightrag/api/routers/query_routes.py` :: `create_query_routes`
- **Template page:** `lightrag_webui/src/features/RetrievalTesting.tsx`
- **Template sidebar:** `lightrag_webui/src/components/retrieval/QuerySettings.tsx`

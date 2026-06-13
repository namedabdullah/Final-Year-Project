# Cross-File Quiz — Folder-Level Implementation Plan

> Status: planned 2026-06-10. A **new, separate feature** added after the SAMpai dev build reached
> feature-complete through Phase 7. Distinct from the per-file MCQ/TF quiz (which is untouched).
>
> Ground rules (unchanged from the rest of SAMpai): all new code lives in `lightrag/api/sampai/`
> and `sampai/frontend/`. The research quiz module `lightrag/quiz/` is reused **read-only** — zero
> edits there (diff budget). `CLAUDE.md` / `AGENTS.md` are never touched.

---

## 1. Goal & scope

A quiz that spans the **completed documents the user selects inside a folder** (default: all of them) —
testing *cross-file synthesis*, not a single document. It is a deliberately separate feature from the
per-file quiz:

| | Per-file quiz (Phase 7) | **Cross-file quiz (this doc)** |
|---|---|---|
| Scope | one file | **the COMPLETED files the user selects in a folder** (default all; §9) |
| Lives on | FilePage → "Quiz" tab | **FolderPage → "Cross-file quiz" section** |
| Output | MCQ + True/False | **open-ended SAQ** (question + reference answer) |
| Grading | deterministic exact-match | **per-question LLM grade 0–5** at submit (§8 — superseded the original self-assessment) |
| Retrieval | mix arm, single doc | **mix arm, folder-wide, cross-document BFS** |
| Seeding | broad single seed | **research pedagogical RRF seeding** (diversity + file contributions) |
| Verification/judges | none | **none at generation** (grading-time grader is separate, §8) |

Decisions locked with the user:

- **Mix arm only** — no naive arm.
- **No verification, no judges at generation** — no Claude verifier, no GPT panel judge, no pedagogy
  judge, no correctness fact-check. (The §8 grader runs at *grading* time, not generation.)
- **Reuse the research pipeline** for everything else: mix-arm pedagogical seeding (RRF over
  deg/xdoc/freq), diversity clustering, per-file contributions, and the cross-document BFS — exactly
  "the same as the research."
- **Output = open-ended SAQ** (question + reference answer), verbatim from the research generator.
- **Difficulty** = manual (easy / medium / hard) **+** an *Auto* option. Auto uses an **adaptive ladder**
  smoothed over the student's last few finished attempts (§8). Difficulty drives BFS **hop depth**
  easy→1 / medium→2 / hard→3.
- **Question count** = removed as a user choice (§10). SAMpai returns however many worthwhile,
  non-duplicate questions the selection yields (internal ceiling 30, no padding).
- **Take UX (current, §8)** = **per-question submit**: answer a question, hit its Submit button →
  the reference answer + an LLM critique (missing / wrong) + a 0–5 score are revealed; that score is
  the personalization signal. Each question shows **"draws on files X & Y"** source attribution.
  *(The original self-assessment + optional "Ask SAMpai" flow was replaced — see §8.)*

---

## 2. How it reuses the research pipeline (the core)

The whole generation backbone is a **single call** to the research entry point, inside a background task:

```python
from lightrag.quiz import generate_quiz, QuizGenerateRequest

resp = await generate_quiz(engine, QuizGenerateRequest(
    document_ids=folder_completed_doc_ids,   # all COMPLETED files' rag_doc_ids in the folder
    mode="mix",                              # mix arm only
    difficulty=difficulty,                   # easy|medium|hard → BFS hops 1|2|3
    num_questions=num_questions,             # 10 | 20 | 30
    run_verification=False,                  # OFF → no Claude verifier, no GPT panel, no pedagogy
    run_correctness_check=False,             # OFF → no correctness fact-check
))
```

**Verified facts that make this clean (this session):**

- With `run_verification=False, run_correctness_check=False` the pipeline's judge job-list is empty,
  so **none** of `verify_question` / `verify_question_gpt` / `judge_pedagogy` / `judge_pedagogy_gpt` /
  `judge_correctness` / `judge_correctness_gpt` are ever instantiated or awaited
  (`lightrag/quiz/pipeline.py:207-244`). Generation is the **only** LLM cost. All `verification*`,
  `pedagogy*`, `correctness*` fields on each question stay `None`.
- `mode="mix"` hard-selects the graph arm: pedagogical entity seeding via `score_mix` (deg/xdoc/freq),
  `diversify` (greedy cosine clustering → round-robin spread), and `allocate` (Cap+Merit+Floor) →
  `file_contributions`. The cross-doc **`xdoc`** signal up-ranks *bridge* entities that appear in ≥2
  docs, and the BFS (`retrieve_mix_arm`) walks **across document boundaries** within the folder →
  genuine synthesis questions.
- `generate_quiz` returns a `QuizGenerateResponse`:
  - `.questions[]` — each a `QuizQuestionMetadata` with `.generation.question`,
    `.generation.reference_answer`, `.claimed_reasoning_type` (factual/comparative/causal…),
    `.retrieval.hop_depth`, `.retrieval.chunk_ids`.
  - `.file_contributions[]` — `{doc_id, seed_count, reason∈contributed|below_threshold|outranked|capped}`.
  - `.diversity{}` — mean/max pairwise cosine of the questions.
  - `.warnings[]` — e.g. "File X contributed 0 seeds", or "no candidates cleared the meaningfulness floor".
  - It also persists a JSON under `{engine.working_dir}/quizzes/` — harmless; we additionally store
    everything in Postgres (our source of truth).

**Generation speed (important for 30-question quizzes).** `_CONCURRENCY_CAP` and
`_INTER_REQUEST_DELAY` are read at **module import** (`pipeline.py:74,79`). The research default
(cap=1, 0.5 s delay) is intentionally sequential and would take minutes for 30 questions. For the
product we set, in root `.env` (read before server start):

```
QUIZ_CONCURRENCY_CAP=4
QUIZ_INTER_REQUEST_DELAY=0.0
```

→ ~20-30 s for 30 SAQ questions on gpt-4o-mini. **This only affects `generate_quiz`** — the per-file
MCQ quiz uses its own generator and is unaffected. (Confirm the OpenAI tier tolerates concurrency 4;
keep `QUIZ_SEED_STRATEGY=pedagogical`, the default, so RRF + diversity + contributions run.)

**Per-question source attribution ("draws on files X & Y").** `retrieval.source_documents` is the
*whole* scope (not useful per-question), but `retrieval.chunk_ids` are per-question and each chunk id
is prefixed with its `doc-<hash>` document id. We derive the contributing files in our service with a
cheap prefix match — no extra LLM/DB cost:

```python
contributing = [doc_id for doc_id in folder_doc_ids
                if any(cid.startswith(doc_id) for cid in q.retrieval.chunk_ids)]
# map doc_id -> File.filename for display
```

---

## 3. Backend

### 3a. Data model — new tables
Append to `lightrag/api/sampai/models/quiz.py` (reuse the existing `QuizStatus`, `QuizDifficulty`, `_enum`):

- **`FolderQuiz`** (`folder_quizzes`): `id`; `folder_id` FK→`folders` CASCADE; `user_id` FK→`users`
  CASCADE; `status` (QuizStatus); `difficulty` (QuizDifficulty); `difficulty_source` `str(20)`;
  `num_questions` int **CHECK IN (10, 20, 30)**; `questions` JSONB; `generation_meta` JSONB;
  `error_msg` Text; `created_at`; `ready_at`; indexes `(user_id, folder_id)` + `(status)`; 1-1
  `attempt` relationship.
- **`FolderQuizAttempt`** (`folder_quiz_attempts`): `id`; `quiz_id` FK→`folder_quizzes` UNIQUE;
  `user_id`; `folder_id`; `score` Float **NULL** (self-assessed; null until the student self-grades);
  `correct_count` int NULL; `total_count` int; `answers` JSONB; `submitted_at`.

`questions` JSONB item shape:
```json
{ "id": "q1", "question": "...", "reference_answer": "...",
  "reasoning_type": "causal", "hop_depth": 3,
  "source_file_ids": [12, 13], "source_file_names": ["A.pdf", "B.pptx"] }
```
`answers` JSONB item shape: `{ "question_id": "q1", "user_answer": "...", "self_mark": "got|partial|missed" }`.

A new Alembic migration (autogenerate) under `lightrag/api/sampai/alembic/versions/`, then
`alembic upgrade head`. Why a new table pair rather than reusing `Quiz` with a nullable `file_id`:
clean separation (per-file logic untouched), efficient indexes, no `file_id IS NULL` branching.

### 3b. Schemas — `lightrag/api/sampai/schemas/folder_quiz.py`
- `GenerateFolderQuizRequest { num_questions: Literal[10,20,30] = 10, difficulty: easy|medium|hard | None }`
- `GenerateFolderQuizResponse { quiz_id, status }`
- `FolderQuizQuestionPublic { id, question, reasoning_type, hop_depth, source_file_names[] }` — **no reference_answer**
- `SubmitAnswer { question_id, user_answer: str }` · `SubmitFolderQuizRequest { answers[] }`
- `SelfGradeItem { question_id, mark: Literal["got","partial","missed"] }` · `SelfGradeRequest { marks[] }`
- `FolderQuizReviewQuestion { id, question, reasoning_type, source_file_names[], user_answer, reference_answer, self_mark }`
- `FolderQuizResult { score: float|None, correct_count: int|None, total_count, answers[] }`
- `FolderQuizFileInfo { file_id, filename, seed_count, reason }`
- `FolderQuizDetail { quiz_id, status, difficulty, difficulty_source, num_questions, error_msg,
  files: FolderQuizFileInfo[], diversity, questions: FolderQuizQuestionPublic[] | None,
  review: FolderQuizResult | None, warnings[] }`
- `FolderQuizHistoryItem { quiz_id, difficulty, num_questions, status, score?, submitted_at?,
  created_at, ready_at?, n_files }` · `FolderQuizHistoryResponse { items[], has_open_quiz, open_quiz_id }`

### 3c. Service — `lightrag/api/sampai/services/folder_quiz_service.py`
- `folder_completed_docs(db, folder_id)` → `[(file_id, filename, rag_doc_id)]` for COMPLETED files
  with a non-null `rag_doc_id` (reuse the `select(File).where(folder_id==, processing_status==COMPLETED)` idiom).
- `infer_difficulty(db, user_id, folder_id)` → from the last 3 **non-null** `FolderQuizAttempt.score`
  values in this folder: ≥0.8→hard, ≤0.5→easy, else medium → `"inferred"`; no signal → `(medium, "baseline")`.
- `generate_folder_quiz_task(quiz_id, classroom_id, folder_id)` (background `asyncio.create_task`):
  1. set GENERATING;
  2. gather completed docs (≥1 else FAILED "no completed files in this folder");
  3. `engine = await get_engine(classroom_id)`;
  4. `resp = await generate_quiz(engine, QuizGenerateRequest(..., mode="mix", run_verification=False, run_correctness_check=False))`;
  5. if `not resp.questions` → FAILED with `error_msg` = joined `resp.warnings` (honour the empty-floor finding; no padding);
  6. build stored questions (assign `q1..qN`; per-question `source_file_ids/names` via chunk-id prefix match → File);
  7. `generation_meta` = `{ file_contributions (mapped to filenames + reasons), diversity, doc_ids,
     model, elapsed_s, warnings, seed_strategy }`;
  8. status READY, `ready_at`, persist. Any exception → FAILED + `error_msg`.
- `public_questions(stored)` → strip `reference_answer`.
- `build_review(stored, attempt)` → merge reference answers + the student's written answers + self_marks.
- `score_from_marks(marks)` → got=1.0 / partial=0.5 / missed=0.0; `score`=mean, `correct_count`=#got.

### 3d. Router — `lightrag/api/sampai/routers/folder_quizzes.py` (prefix `/folder-quiz`)
Wire into the `mount_sampai` include list in `lightrag/api/sampai/__init__.py`.
- `POST /folders/{folder_id}/generate` → **202**. `require_membership(classroom)`; ≥1 COMPLETED file
  else 400; **one-open-per-(user, folder)** + 5-minute stale-abandon (mirror `routers/quizzes.py`);
  difficulty manual or inferred; create `FolderQuiz` PENDING; spawn task; return `{quiz_id, status}`.
- `GET /{quiz_id}` (poll, owner-only) → `FolderQuizDetail`; public questions when READY+unattempted;
  review when SUBMITTED; `files[]` from `generation_meta`.
- `POST /{quiz_id}/submit` (owner) → quiz READY + no attempt; store written answers; create
  `FolderQuizAttempt` (score null); status SUBMITTED; return the review payload **with** reference
  answers + per-question source files.
- `POST /{quiz_id}/self-grade` (owner) → quiz SUBMITTED + attempt exists; set per-question `self_mark`;
  compute `score` + `correct_count`; return `FolderQuizResult`.
- `GET /folders/{folder_id}/history` (member) → items newest-first + `has_open_quiz` / `open_quiz_id` + `n_files`.

### 3e. Env — root `.env` + `env.example`
Add `QUIZ_CONCURRENCY_CAP=4` and `QUIZ_INTER_REQUEST_DELAY=0.0` with a comment noting they tune
`generate_quiz` (the cross-file quiz) only.

---

## 4. Frontend

> **Note (2026-06-11):** §4b below describes the *original* self-assessment UI. The shipped UI is the
> **per-question submit-and-grade** flow — see §8 for the authoritative description. API surface is now
> `folderQuizApi { generate, get, submitQuestion(quizId, questionId, userAnswer), history }`.

### 4a. API + types — `sampai/frontend/src/api/sampai.ts`
`folderQuizApi { generate(folderId, {num_questions, difficulty?}), get(quizId),
submitQuestion(quizId, questionId, userAnswer), history(folderId) }` + the folder-quiz types
(`FolderQuizQuestionView`, `TopicScore`, `SubmitQuestionResponse`, `FolderQuizDetail`, history).

### 4b. Component — `sampai/frontend/src/components/FolderQuizPanel.tsx`  *(superseded by §8)*
States: **idle → generating (poll 2 s) → in-progress/completed**; resume an open quiz from history on mount.
- **Idle:** count pills (10/20/30), difficulty pills (Auto/Easy/Medium/Hard), Generate button;
  "N completed files"; **clickable** past-quiz history (open any quiz read-only / resume).
- **Generating:** spinner.
- **In-progress:** each question = prompt + reasoning-type chip + **source-file badges** + a textarea
  and its own **Submit** button. On submit the card flips to show the reference answer + LLM critique +
  0–5 score pill. Header shows `graded/total · running %`.
- **Completed:** header with the aggregate %, "mastered" count, and the note that it sets the next Auto
  difficulty; a **`TopicBreakdown`** (per-file bars); all question cards in graded/read-only form.
- Helpers: `Pill`, `ReasoningChip`, `FileSourceBadge`, `ScorePill`, `GradeBlock`, `TopicBreakdown`.

### 4c. Entry point — `sampai/frontend/src/pages/FolderPage.tsx`
A "Cross-file quiz" section **above the file list**. The Generate control is enabled only when ≥1 file
is COMPLETED ("Includes N completed files"); clicking expands `FolderQuizPanel` **inline** (no new
route — matches the per-file quiz-as-tab pattern). The page already polls file statuses, so the
completed-count gate is free.

---

## 5. Verification

- **Backend** — `sampai/docker/scripts/verify_cross_file_quiz.py` (live `:9621`, owner token):
  a folder with ≥2 completed files; `generate(20, "hard")` → poll READY; assert: N open-ended questions,
  `reference_answer` hidden in the pre-submit payload, **≥1 question whose `source_file_names` spans ≥2
  files** (the cross-file proof), `file_contributions` + `diversity` present, **no** verification/pedagogy
  fields anywhere; `submit` → review reveals reference answers; `self-grade` → score computed; history +
  resume; one-open → 409; manual vs auto difficulty (hop depth easy < hard via `generation_meta`); and
  that generation at cap=4 finishes in a reasonable time.
- **Frontend** — `tsc -b` clean + `vite build` succeeds; manual click-through on FolderPage
  (generate → answer → reveal → self-grade → history/resume).
- **Cleanliness gate** — `git diff` touches only `lightrag/api/sampai/**`, `sampai/frontend/**`, and
  root `.env`/`env.example`. `lightrag/quiz/**` unchanged.

---

## 6. Risks & notes

1. **Empty/low-yield folders.** If the folder's docs are figure/table-anchor-dominated with little
   teachable prose, the meaningfulness floor can yield 0 seeds → an empty quiz. We surface this as a
   FAILED quiz with the research's own warning text (no placeholder padding) so the cause is visible.
2. **Concurrency vs. rate limits.** cap=4 is safe for low-volume gpt-4o-mini usage; if the OpenAI tier
   throttles, lower it (the only knob is the env var; no code change).
3. **Grading is LLM-judged at submit (§8).** Each answer is scored 0–5 vs its reference by the grader;
   the score is machine-derived, not self-reported. (Superseded the original got/partial/missed flow.)
4. **SAQ ≠ MCQ.** This feature deliberately diverges from the per-file MCQ UX; the two coexist and
   share no take/grade code.
5. **The grader is grading-time, not a generation judge (see §8).** It compares the student's answer to
   the trusted reference and scores 0–5 — it never validates or filters questions, so the "no judges at
   generation" rule is untouched.

---

## 7. Build order (phase-by-phase, on go-ahead)
1. Models + Alembic migration (`folder_quizzes`, `folder_quiz_attempts`).
2. Schemas + `folder_quiz_service.py` (incl. the `generate_quiz` integration + chunk-id→file mapping).
3. Router + `__init__.py` wiring + `.env` tuning.
4. `verify_cross_file_quiz.py` → run green.
5. Frontend: `folderQuizApi` + types → `FolderQuizPanel` → FolderPage entry point.
6. `tsc -b` + `vite build` + live click-through.

**Built & live-verified 2026-06-11** against folder 11 (3 HUM111 lectures): 23/23 backend checks PASS,
all 8 generated questions cross-file (every one drew on all 3 lectures), gen ~36 s at cap=4. Two fixes
during bring-up: `FileContribution` is a Pydantic object (attribute access, not `.get()`); `ready_at`
must be `datetime.utcnow()` (naive) for the tz-naive `DateTime` column. `attempt` relationship is
`lazy="selectin"` so the async router can read it without a lazy-load fault.

---

## 8. Per-question submit + LLM grading + adaptive difficulty (redesigned 2026-06-11)

The original take flow (bulk "submit all" → self-assess got/partial/missed, with an optional "Ask
SAMpai" button) was **replaced** at the user's direction. The current flow:

**Per-question submit.** Each question has its **own Submit button**. Submitting one question:
locks that answer, grades it **0–5 against its reference**, and reveals the **reference answer + an LLM
critique** (what's *missing*, what's *incorrect*, a one-line verdict) + the **score**. The manual
got/partial/missed buttons and the separate "Ask SAMpai" button are gone. Single synchronous call per
question (no background task). The quiz **auto-completes** (status → SUBMITTED) once every question is
graded.

**The grader** (`grade_answer_llm`, unchanged from the first cut):
- **Model** = generation model (`QUIZ_GENERATION_MODEL` → `LLM_MODEL` → `gpt-4o-mini`), env-overridable.
- **Grades against the reference answer only** (trusted ground truth) — never re-feeds source chunks.
- **Rubric** (temp 0, JSON-mode + `json_repair`): 5 = complete & correct · 4 = minor omission ·
  3 = a missing key point **or** a minor factual error · 2 = major omission **or** clear factual error ·
  1 = barely addresses · 0 = blank/irrelevant/wrong. "Deduct for every reference key point omitted;
  deduct harder for any contradiction." **Blank answers short-circuit to 0** with no LLM call.
- **On failure** → `503`; the question's Submit shows "grading unavailable — retry". Nothing is stored,
  so retry is clean.

**Scoring & personalization (the point of the redesign):**
- **Per-question** score 0–5 → normalized `/5`.
- **Aggregate** (`attempt.score`, 0–1) = mean of the per-question normalized scores. This is the
  signal that drives Auto difficulty. `correct_count` = #questions scoring **≥4** ("mastered").
- **Per-topic** (`attempt.topic_scores`, new JSONB column via migration `fqa_topic_scores_01`): a
  per-**file** breakdown — each question's score is attributed to *every* file it draws on (cross-file
  questions count toward all their files). Stored at finalize, shown as a "Performance by file" bar list.
- **Adaptive difficulty ladder** (`infer_difficulty`, rewritten): Auto **anchors on the most recent
  finished attempt's difficulty** (the current rung) and steps from it using the **mean aggregate score
  of the last up-to-3 finished attempts** — averaging smooths a single noisy quiz, while anchoring on
  the latest difficulty keeps "0.8 at hard" and "0.8 at easy" distinct. mean ≥0.8 → step up
  (easy→medium→hard), ≤0.5 → step down, else hold. No history → medium baseline. The pure stepping is
  factored into `_step_difficulty(anchor, avg)` for testing.

**State machine:** the (empty) attempt is created when the quiz reaches READY (avoids a get-or-create
race on the first submit). READY = in progress (some questions may be graded); SUBMITTED = all graded
(final aggregate + topic_scores written). One-open-per-(user,folder) still holds while READY.

**Past quizzes are clickable** — history items open the quiz read-only (finished → full review with all
references/critiques/scores + topic breakdown; in-progress → resume answering).

**Backend:** `schemas/folder_quiz.py` (`QuestionView`, `SubmitQuestionRequest/Response`, `TopicScore`,
redesigned `FolderQuizDetail`); `folder_quiz_service` (`build_question_views`, `aggregate_and_topics`,
ladder `infer_difficulty`, attempt-at-READY); `routers/folder_quizzes.py` →
`POST /folder-quiz/{id}/questions/{question_id}/submit` (replaces the old `/submit`, `/self-grade`,
`/grade-question`). Migration `fqa_topic_scores_01` adds `folder_quiz_attempts.topic_scores`.
**Frontend:** `folderQuizApi.submitQuestion`; `FolderQuizPanel` rewritten — per-question textarea+Submit,
inline `GradeBlock` (reference + critique + score pill), completed header (aggregate %, mastered count,
"this sets your next Auto difficulty"), `TopicBreakdown` bars, clickable history.

**Verified 2026-06-11 (folder 11, 3 HUM111 lectures): 39/39 live checks PASS** — per-question reference
reveal + 0–5 score + critique; blank→0; `finished` flips on the last question; re-submit→409;
one-open→409; completed detail has aggregate + per-file topic_scores + visible references; **adaptive
ladder: a weak medium attempt → next Auto quiz = easy**; history exposes score + graded/total.
(Grader rubric discrimination — correct→5 / partial→1 / wrong→0 — was verified the prior session.)
`verify_cross_file_quiz.py` updated to the per-question flow.

**Smoothing added 2026-06-12:** the ladder now averages the last up-to-3 finished attempts (anchored on
the most recent difficulty) instead of keying off one quiz. Verified end-to-end: seeded finished medium
attempts scoring `[1.0, 1.0, 0.5]` (most recent weak) → mean 0.833 → next Auto = **HARD** (single-quiz
logic would have given easy), proving the average is in effect. Pure logic unit-checked via
`_step_difficulty`.

---

## 9. File selection (added 2026-06-12)

The quiz is built from the **completed files the user selects** in the folder, not unconditionally all
of them. The idle panel shows a checkbox list of the folder's completed files with a **Select all /
Deselect all** toggle; Generate is disabled until ≥1 is selected and is labelled with the count.

**Soundness — the selection is the *only* scope.** The chosen `file_ids` are resolved to completed
docs (`folder_completed_docs(folder_id, file_ids)` = intersection of the request with the folder's
completed files), stored on the quiz row (`folder_quizzes.selected_file_ids`, migration
`fq_selected_files_02`), and the generation task re-reads them so **only those docs' `rag_doc_id`s are
passed to `generate_quiz`**. Because `document_ids` scopes seeding, BFS retrieval, chunk_ids, file
contributions, and the per-file topic breakdown, an unselected file cannot leak into any question.

- `file_ids=None` → all completed (back-compatible). Empty list or an all-invalid selection → **400**.
- Invalid / not-yet-completed ids in the list are silently dropped (intersection); the stored
  `selected_file_ids` reflects what was actually used.
- History `n_files` now reports **that quiz's** selection size, not the folder's current completed count.
- Frontend keeps the selection in sync with live file statuses: newly-completed files default to
  selected; removed files drop out; explicit deselections are preserved across status polls.

**Verified 2026-06-12 (folder 11):** selecting Lecture06+07 (excluding Lecture08) → 5 questions, **every**
source ⊆ the two selected files, **Lecture08 never appears** in any question or in file_contributions;
empty/invalid selection → 400; valid generate while one open → 409; history `n_files`=2. 10/10 live PASS.
Selection coverage folded into `verify_cross_file_quiz.py` (subset generate + leak assertion).

---

## 10. Question count removed — SAMpai decides (2026-06-12)

The user-facing **10/20/30 selector is gone.** `num_questions` was never a target the seeder hit — the
allocator ranks concepts, drops near-duplicates, caps per file, and **stops when the worthwhile pool is
exhausted (no padding)**, which is why "20" routinely produced 8. So the count is now driven purely by
how much teachable, non-overlapping content the selected files hold.

- Backend hands the allocator an internal **ceiling of 30** (`folder_quiz_service.QUESTION_CEILING`,
  stored as the quiz's `num_questions` — 30 satisfies the `IN (10,20,30)` check). The real count is
  whatever the allocator returns (`total_count` = `len(questions)`).
- `GenerateFolderQuizRequest.num_questions` was removed; the request is just `{difficulty?, file_ids?}`.
- **Sparse notice:** when fewer than `SPARSE_BELOW` (5) questions are produced, the generation task adds
  a friendly student-facing warning ("Only N worthwhile questions … select more files"). Raw research
  warnings (per-doc "0 seeds" lines with raw doc ids) are kept under `generation_meta.gen_warnings`
  **and not shown** — only the curated `warnings` reach the UI.
- **Important nuance (documented for honesty):** seed selection is **deterministic and
  difficulty-independent**, with **no cross-quiz memory**. Same files → same concepts every regeneration
  (only wording may drift); changing difficulty re-asks the *same* concepts at a different depth. The
  only lever that surfaces new concepts is **changing the file selection**. True "cover what hasn't been
  asked before" would need cross-quiz seed exclusion (a first edit to the read-only `lightrag/quiz/`
  seeder) — explicitly deferred; the user chose to accept repetition for now.
- **Diversity/contributions reliability:** a strong deterministic *heuristic* (RRF importance + cosine
  dedup + Cap/Merit/Floor) — trustworthy for "no junk, no dupes, spread across files, no padding", but
  not a guarantee of an objectively optimal set. Good enough to trust for this product.

UI: the count pills are replaced by a one-line explainer ("SAMpai picks the most worthwhile questions …
up to 30"); the generating screen shows difficulty only; history shows the *actual* `total_count`; a
sparse `warnings` banner renders above the question list.

**Verified live 2026-06-12 (folder 11):** generate with no count → ready, stored `num_questions`=30,
`total_count`=8 (all 3 files), no warning; single-file selection → 3 questions + the sparse notice fires.

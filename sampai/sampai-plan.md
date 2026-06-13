# The Learning SAMpai — Development Plan & Locked Tech Stack

> **Companion to:** `sampai/SAMpai.md` (the complete feature & schema extraction — the WHAT).
> **This document:** the HOW — locked tech stack, architecture, docker topology, and phased implementation plan for rebuilding The Learning SAMpai by **modifying this repo's LightRAG server in place**.
>
> **Ground rules:**
> - **We modify this repo's actual LightRAG FastAPI server** (`lightrag/api/`) to become the SAMpai backend. We do **not** import LightRAG as a separate library.
> - **All new backend code is isolated in one subpackage: `lightrag/api/sampai/`.** Edits to existing upstream files are **surgical, comment-fenced, and logged** (`lightrag/api/sampai/CHANGES.md`). The original pipeline and the original API routes must keep working.
> - **Off-limits forever:** `CLAUDE.md`, `AGENTS.md`. **Now editable** (decided 2026-06-07): root `pyproject.toml` (a `[sampai]` extras group) and root `.env`/`env.example`.
> - The old app (`The-Learning-SAMpai/`) is reference-only; **none of its architecture or pipeline is reused**.
> - **The quiz phase is deliberately LAST** (Phase 7): per-file quiz details + the cross-file quiz feature require a design discussion first (§7 has the agenda).

Locked decisions (2026-06-07): **modify-the-server** (not embed-as-library) · **MinerU local via Docker, GPU-aware, for PDFs** + Docling for office docs · **PostgreSQL 16** app DB · **single feature-gate at `PROCESSED`** · **React + Vite** frontend (not Next.js) · hybrid visual look.

---

## 1. Locked Tech Stack

### 1.1 RAG engine & how we attach to it (the heart)

| Layer | Choice | Why |
|---|---|---|
| RAG engine | **This repo's LightRAG server, modified in place** (`lightrag/api/lightrag_server.py` + a new `lightrag/api/sampai/` subpackage). NOT a separate app, NOT an imported library. | Reuses the server's existing config/args, LLM+embedding builders, doc pipeline, doc-status tracking, and the in-tree `lightrag/quiz/` module directly. Keeps everything in one process/repo. |
| Multi-tenancy | **Per-classroom engine registry** beside the server's existing single `rag`, each `LightRAG(workspace=f"classroom_{id}", …)` | The bundled server is single-workspace; we add a registry that reuses the in-scope `embedding_func`/`config_cache`. The original `rag` + its 4 routers stay byte-for-byte intact → original pipeline unaffected. Verified safe: shared-storage namespaces are `f"{workspace}:{ns}"` with per-workspace pipeline status + locks (`lightrag/kg/shared_storage.py:1176, 1267`). |
| Graph store | **Neo4j 5.26 community** (`Neo4JStorage`) | Workspace isolation = node label per classroom (`lightrag/kg/neo4j_impl.py:67`). |
| Vector store | **Qdrant v1.12** (`QdrantVectorDBStorage`) | Workspace isolation = `workspace_id` payload filter (`lightrag/kg/qdrant_impl.py:63`). |
| KV + doc status | **Redis 7.4** (`RedisKVStorage`, `RedisDocStatusStorage`) | Key-prefix isolation (`lightrag/kg/redis_impl.py:128`). Triple-duty: LightRAG KV/status + app rate limiting + WS pub/sub fan-out. |
| Required storage env (`lightrag/kg/__init__.py:49`) | `NEO4J_URI/USERNAME/PASSWORD`, `QDRANT_URL`, `REDIS_URI` | — |

### 1.2 External (cloud) services

| Service | Used for | Notes |
|---|---|---|
| **Cloudflare R2** | Original file storage (uploads) + presigned GET downloads (1 h TTL) | S3-compatible via `boto3`. Key: `classrooms/{cid}/folders/{fid}/{filename}`. The object URL is the **citation key** (`files.file_url` ⇄ LightRAG `file_paths`). |
| **OpenAI API** | LLM `gpt-4o-mini` · embeddings `text-embedding-3-large` (**dim 3072 — pinned**) · VLM for multimodal | Same binding as the repo's `.env` (`LLM_BINDING=openai`). |
| **Cloudflare Tunnel** *(optional, demo day)* | Public URL for the local stack | `cloudflared` → `web:80`; tighten CORS to the tunnel origin. |
| Rerank (Cohere/Jina) *(deferred)* | Retrieval quality | **Disabled v1** (`RERANK_BINDING=null`, `enable_rerank=False`). |

### 1.3 Backend

| Concern | Choice |
|---|---|
| Process | **The modified LightRAG server** (`uvicorn lightrag.api.lightrag_server:app`), Python 3.12, uv. ⚠️ **1 worker** (in-process registry + WS hub; gunicorn would fork N broken copies). |
| App database | **PostgreSQL 16** + **SQLAlchemy 2.0 async** (asyncpg) + **Alembic** (migrations under `lightrag/api/sampai/alembic/`) |
| Auth | **Our own DB-user auth**: PyJWT HS256 + passlib[argon2], under our prefix, via `Depends(sampai_current_user)`. Coexists with the server's env-account `/login` (we don't touch it). SAMpai system user + reserved `sampai` username seeded via Alembic data migration |
| Config | Our `SampaiSettings` (pydantic-settings, `APP_*`/`R2_*`) reads the same root `.env` the server already loads |
| Realtime | FastAPI native WebSockets + **Redis pub/sub fan-out**; events per SAMpai.md §2.9 |
| Rate limiting | Redis sliding window — 10 msgs/10 s per (user, thread); 3 @SAMpai calls/60 s per (user, thread) |
| Background work | `asyncio.create_task` (agent replies, summaries, notifications) + a lifespan-managed bounded `asyncio.Queue` worker for ingestion. **No Celery/arq v1.** |
| HTML sanitization | **nh3** on announcement write (fixes the old XSS hole) |
| Structured LLM output | **OpenAI structured outputs** (`response_format: json_schema`) for mindmap trees & quiz JSON |
| Object storage client | boto3 (R2 S3 API) |

### 1.4 Document parsing & multimodal — **MinerU (PDF) + Docling (office)**

| Concern | Choice |
|---|---|
| PDF parser | **MinerU, run locally via Docker, GPU-aware** — `MINERU_API_MODE=local`, `MINERU_LOCAL_ENDPOINT=http://mineru:8000`. GPU present → `MINERU_LOCAL_BACKEND=hybrid-auto-engine` + `MINERU_LOCAL_IMAGE_ANALYSIS=true`; else CPU `pipeline` + image-analysis off. Chosen by the GPU-probe script (§4.5). Mirrors the repo's existing `.env`. |
| Office parser | **docling-serve container** (docx/pptx/xlsx; OCR, tables, images) — `DOCLING_ENDPOINT=http://docling:5001` |
| Routing | `LIGHTRAG_PARSER=pdf:mineru-iteR,docx:docling-iteR,pptx:docling-iteR,xlsx:docling-iteR,*:legacy-R` (`lightrag/parser/routing.py`; flags `i`=images `t`=tables `e`=equations `R`=recursive chunking). Parser/service failure → doc goes `FAILED` with `error_msg` (retryable). |
| Multimodal | LightRAG `VLM_PROCESS_ENABLE=true`, `VLM_LLM_MODEL=gpt-4o-mini` — an **independent** ANALYZING pass, separate from MinerU's own image analysis. |
| Fallback | `.txt` / unmatched → `legacy` parser (no external service). |

### 1.5 Frontend

| Concern | Choice |
|---|---|
| Framework | **React 19 + TypeScript + Vite** (NOT Next.js) — SPA served by nginx at `/`; API proxied to the LightRAG server at `/api/*` |
| Routing / state | react-router-dom 7 · **TanStack Query** (server state, `refetchInterval` polling, `useInfiniteQuery`) · zustand (UI/WS-ephemeral only) |
| HTTP / WS | axios (Bearer interceptor, 401→logout) + native WebSocket with reconnect/backoff/gap-fill |
| Styling / components | Tailwind CSS 4 + **shadcn-style kit copied from `lightrag_webui/src/components/ui`** |
| Feature libs | TipTap (announcements) · `@xyflow/react`+dagre (mindmap) · react-markdown+remark-gfm (chat; lift `lightrag_webui` ChatMessage) · sonner · lucide-react |
| Visual identity | **Hybrid** — clean shadcn base + ported WebGL signature components from `The-Learning-SAMpai/frontend/components/backgrounds` (plasma, orbs, 3D folder/file; strip `"use client"`, `next/dynamic`→`React.lazy`, `next/navigation`→react-router) |
| Package manager | **bun** |

### 1.6 Explicitly NOT used

Next.js · ChromaDB · the old hand-rolled LightRAG port (`backend/app/rag/`) · the old custom multimodal pipeline · LangChain · `instructor` · python-jose · **and: LightRAG-as-an-imported-library** (we modify the server instead).

---

## 2. Repository Layout

> Backend now lives **inside the LightRAG tree** (`lightrag/api/sampai/`). Frontend, docker, and docs stay under `sampai/`.

```
lightrag/api/
├── lightrag_server.py             # UPSTREAM — ~3 surgical, fenced edits only (§4.0)
└── sampai/                        # ← ALL new backend code (one isolated subpackage)
    ├── __init__.py                # exports mount_sampai(), sampai_startup(), sampai_shutdown()
    ├── CHANGES.md                 # ledger of every edited upstream line (for clean rebases)
    ├── config.py                  # SampaiSettings (pydantic-settings: APP_*, R2_*)
    ├── registry.py                # per-classroom LightRAG engine registry  ← core
    ├── db.py  deps.py  security.py
    ├── models/                    # SQLAlchemy ORM — 19 tables per SAMpai.md §3
    ├── schemas/                   # Pydantic request/response per feature
    ├── routers/
    │   ├── auth.py classrooms.py folders.py files.py chat.py
    │   ├── flashcards.py mindmaps.py groupchat.py announcements.py
    │   ├── quizzes.py             # Phase 7
    │   └── ws.py                  # /api/sampai/ws/user + /ws/group-chat/{id}
    ├── services/
    │   ├── rag_gateway.py         # scoped retrieval gateway              ← core
    │   ├── ingestion.py           # upload→R2→ainsert(MinerU/Docling)→status→summary ← core
    │   ├── chat_service.py flashcard_service.py mindmap_service.py
    │   ├── groupchat_service.py groupchat_agent.py
    │   ├── announcement_service.py quiz_service.py   # P7
    ├── realtime/ hub.py fanout.py events.py ratelimit.py
    ├── integrations/ r2.py sanitize.py
    ├── alembic.ini  alembic/versions/
    └── tests/

sampai/
├── SAMpai.md  sampai-plan.md
├── frontend/  (React 19 + Vite SPA — src/api, stores, components/{ui,backgrounds,layout}, features/*)
└── docker/
    ├── docker-compose.yml           # full stack (profiles: data, parsing, app)
    ├── docker-compose.dev.yml       # data + parsing only (host dev)
    ├── docker-compose.mineru-gpu.yml# GPU overlay (device reservation) — selected by probe
    ├── Dockerfile.api  Dockerfile.web  nginx.conf  .env.example
    └── scripts/mineru-autoselect.{sh,ps1}
```

All SAMpai routers are mounted under a single prefix (`/api/sampai/...`) so they never collide with the server's own routes (`/documents`, `/query`, `/graph`, `/quiz`, `/login`, `/webui`).

---

## 3. Docker Topology

### 3.1 Services

| Service | Image | Port(s) | Volume | Healthcheck | Profile |
|---|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | `pgdata` | `pg_isready` | data |
| `neo4j` | `neo4j:5.26-community` | 7474, 7687 | `neo4jdata` | `wget /` | data |
| `qdrant` | `qdrant/qdrant:v1.12.4` | 6333 | `qdrantdata` | `/healthz` | data |
| `redis` | `redis:7.4-alpine` | 6379 | `redisdata` | `redis-cli ping` | data |
| `docling` | `quay.io/docling-project/docling-serve` (pin digest) | 5001 | `doclingcache` | `/health` | parsing |
| `mineru` | **mineru-api** (image TBD — confirm the one you ran earlier; CPU build for `pipeline`, sglang/vllm GPU build for `hybrid-auto-engine`) | 8000 | `mineru_models` | `POST /tasks` reachable | parsing |
| `api` | built `Dockerfile.api` = **the modified LightRAG server**, 1 worker | 9621 | `ragworkdir` | `curl /health` | app |
| `web` | built `Dockerfile.web` (nginx, our SPA) | 80 | — | `wget /` | app |
| `cloudflared` *(opt)* | `cloudflare/cloudflared` | — | — | — | tunnel |

- **depends_on:** `api` waits for postgres/neo4j/qdrant/redis `service_healthy`; docling + mineru `service_started` (slow cold start — `api` retries via readiness loop). `web` → `api`.
- **GPU overlay:** `docker-compose.mineru-gpu.yml` adds `deploy.resources.reservations.devices: [{capabilities: [gpu]}]` to `mineru`; the probe script decides whether to include it.
- **profiles:** `data` · `parsing` · `app` · `tunnel`.

### 3.2 nginx
- SPA: `try_files $uri /index.html`. `location /api/ → http://api:9621/`. **WS upgrade** on `/api/sampai/ws` (`Upgrade`/`Connection`, `proxy_read_timeout 3600s`). `client_max_body_size 100m`. (`/webui` on the server stays reachable for debugging the raw LightRAG UI.)

### 3.3 `Dockerfile.api`
Build context = repo root (we're in-tree). `pip install -e .[sampai]` (the new extras group) so the server boots with SAMpai mounted. `CMD ["uvicorn","lightrag.api.lightrag_server:app","--host","0.0.0.0","--port","9621","--workers","1"]`.

### 3.4 Dev workflow (Windows-friendly)
```powershell
sampai/docker/scripts/mineru-autoselect.ps1            # picks GPU vs CPU mineru backend → writes env + overlay choice
docker compose -f sampai/docker/docker-compose.dev.yml up -d   # stores + docling + mineru
# venv: pip install -e D:\FYP\LightRAG -e D:\FYP\LightRAG[sampai]
uvicorn lightrag.api.lightrag_server:app --reload --port 9621  # 1 worker
bun run dev                                             # vite :5173, VITE_API_BASE=http://localhost:9621
```

### 3.5 Environment (root `.env` / `env.example` — now editable, additive)
```
# ── SAMpai app ──
APP_DATABASE_URL=postgresql+asyncpg://sampai:***@postgres:5432/sampai
APP_JWT_SECRET=...   APP_JWT_EXPIRE_MIN=1440   APP_CORS_ORIGINS=http://localhost:5173
APP_ENGINE_IDLE_TTL=1800   APP_MAX_RESIDENT_ENGINES=8   APP_UPLOAD_MAX_MB=100
R2_ENDPOINT=...  R2_ACCESS_KEY_ID=...  R2_SECRET_ACCESS_KEY=...  R2_BUCKET=sampai-files  R2_PRESIGN_TTL=3600
# ── LightRAG storage ──
NEO4J_URI=bolt://neo4j:7687  NEO4J_USERNAME=neo4j  NEO4J_PASSWORD=***
QDRANT_URL=http://qdrant:6333   REDIS_URI=redis://redis:6379
# ── LLM / embedding / rerank ──
LLM_BINDING=openai  LLM_MODEL=gpt-4o-mini  LLM_BINDING_API_KEY=sk-...
EMBEDDING_BINDING=openai  EMBEDDING_MODEL=text-embedding-3-large  EMBEDDING_DIM=3072  RERANK_BINDING=null
# ── Parsing (MinerU pdf + Docling office) — MINERU backend vars set by the probe ──
LIGHTRAG_PARSER=pdf:mineru-iteR,docx:docling-iteR,pptx:docling-iteR,xlsx:docling-iteR,*:legacy-R
MINERU_API_MODE=local  MINERU_LOCAL_ENDPOINT=http://mineru:8000
MINERU_LOCAL_BACKEND=pipeline  MINERU_LOCAL_IMAGE_ANALYSIS=false   # ← overwritten by mineru-autoselect when a GPU is found
DOCLING_ENDPOINT=http://docling:5001  DOCLING_DO_OCR=true
VLM_PROCESS_ENABLE=true  VLM_LLM_MODEL=gpt-4o-mini
WORKING_DIR=/data/ragworkdir
```

---

## 4. Backend Architecture

### 4.0 Modification surface — the ONLY upstream edits (surgical, fenced, logged)

Everything else lives in `lightrag/api/sampai/`. Edits to existing files are wrapped in `# --- SAMpai --- … # --- end SAMpai ---` and recorded in `lightrag/api/sampai/CHANGES.md`.

1. **`lightrag/api/lightrag_server.py`** — three fenced spots:
   - top: `from lightrag.api.sampai import mount_sampai, sampai_startup, sampai_shutdown`
   - inside `lifespan` (`:806-836`): `await sampai_startup(app, args, embedding_func, config_cache, rag)` before `yield`; `await sampai_shutdown(app)` after. *(A `lifespan=` is set, so Starlette ignores `add_event_handler` — these two `await`s are the one unavoidable edit to an existing function.)*
   - after the router includes (`:2013-2020`): `mount_sampai(app, args=args, embedding_func=embedding_func, config_cache=config_cache)`.
2. **Root `pyproject.toml`** — add `[project.optional-dependencies] sampai = ["sqlalchemy[asyncio]","asyncpg","alembic","pyjwt","passlib[argon2]","boto3","nh3","redis","python-multipart"]`.
3. **Root `env.example`** — add the `APP_*`/`R2_*` block (above). Never touch `CLAUDE.md`/`AGENTS.md`.

Diff budget (clean-source acceptance gate): **≤ ~20 changed lines in `lightrag_server.py`; 0 lines in `lightrag/lightrag.py`, `operate.py`, `kg/`, `parser/`, `quiz/`.**

### 4.1 `sampai/registry.py` — per-classroom engine registry
- `sampai_startup` builds the registry, the asyncpg pool, the Redis client, the R2 client; reuses the server's in-scope `embedding_func` + `config_cache` + `create_llm_model_func` (no re-derivation).
- `await get_engine(classroom_id)`: double-checked per-key `asyncio.Lock`; on miss, construct `LightRAG(workspace=f"classroom_{id}", working_dir=…/classroom_{id}, kv_storage="RedisKVStorage", vector_storage="QdrantVectorDBStorage", graph_storage="Neo4JStorage", doc_status_storage="RedisDocStatusStorage", embedding_func=shared, llm_model_func=shared, enable_llm_cache=True)` → `await rag.initialize_storages()` → `await initialize_pipeline_status(workspace=rag.workspace)` (base `rag` only inits its own workspace — easy to miss).
- LRU + TTL eviction (`APP_ENGINE_IDLE_TTL`, cap `APP_MAX_RESIDENT_ENGINES`) → `await rag.finalize_storages()`. `sampai_shutdown` finalizes all + closes pools.

### 4.2 `sampai/services/rag_gateway.py` — scoped retrieval (the critical design)
`QueryParam` has **no per-file filter** (`lightrag/base.py:85-177`) → scoped features never call `aquery` directly; they reuse the in-tree `lightrag/quiz/retrieval.py` idioms (now a clean intra-repo import):

| Gateway fn | Used by | Reuse |
|---|---|---|
| `scoped_chunks(rag, q, doc_ids, top_k)` | chat, flashcards | `retrieve_naive_arm` idiom (`retrieval.py:445`): `chunks_vdb.query(q, top_k*10)` → keep `full_doc_id ∈ doc_ids` → `[:top_k]` |
| `scoped_answer(rag, q, doc_ids, history, stream)` | per-file chat, mindmap chat | scoped_chunks → `RetrievalContext.format_for_prompt()` (`retrieval.py:36`) → `PROMPTS["naive_rag_response"]` (`lightrag/prompt.py:532`) + history → `rag.llm_model_func(...)` → SSE |
| `scoped_mix_context(rag, q, doc_ids, difficulty)` | mindmap tree, node summaries | direct reuse of `retrieve_mix_arm` (`retrieval.py:329`) — entity seeds → scope filter → `_bfs_subgraph` (per-depth cap 5) |
| `classroom_answer(rag, q, history, stream)` | @SAMpai, "ask the classroom" | plain `rag.aquery(QueryParam(mode="mix"/"naive", stream=True, enable_rerank=False, conversation_history=…))` — workspace = classroom |

**Doc identity:** `doc_id = sha256(content)` app-side → `files.rag_doc_id`; `ainsert(ids=[doc_id], file_paths=[file_url], track_id=…)` (`lightrag/lightrag.py:1266`).

### 4.3 `sampai/services/ingestion.py` — upload → R2 → pipeline → gate
Upload (member-gated, ext pdf/docx/pptx/txt) → R2 → `files` row → bounded queue → `track_id = await engine.ainsert(...)` (PDF routes through **MinerU**, office through **Docling**, per `LIGHTRAG_PARSER`). Status poll via `engine.aget_docs_by_ids([doc_id])`:

| `DocStatus` | UI |
|---|---|
| PENDING | Queued |
| PARSING | "Parsing document…" (MinerU/Docling) |
| ANALYZING | "Analyzing images & tables…" |
| PROCESSING | "Building knowledge graph…" |
| **PROCESSED** | **Ready → ALL AI tabs unlock (single gate)** |
| FAILED | Error + Retry |

On PROCESSED → summary LLM call → `files.description`. Delete (owner) → R2 `delete_object` + `engine.adelete_by_doc_id(doc_id)` + DB cascade.

> **Conscious deviation:** no `naive_ready` early-chat state (this pipeline indexes at PROCESSED). Compensation: staged progress + honest copy. Documented tradeoff.

### 4.4 Realtime, agent, auth
- WS hub (in-process rooms + presence) + Redis fan-out (`PUBLISH room:{id}`); events ported 1:1 from SAMpai.md §2.9.
- @SAMpai (respond-only, 3/60 s, gate on PROCESSED, manipulation pre-filter ported verbatim) → `gateway.scoped_answer` (file-scoped) with tutor framing → streamed reply as the seeded SAMpai system user.
- Auth: our DB-user JWT (`Depends(sampai_current_user)`); `require_membership`/`require_owner`; coexists with the server's `combined_auth` (per-route, no collision).

### 4.5 MinerU ingestion + GPU autoselect
`sampai/docker/scripts/mineru-autoselect.{sh,ps1}`: probe for an NVIDIA GPU (`nvidia-smi` success, or `docker info` nvidia runtime). **GPU →** write `MINERU_LOCAL_BACKEND=hybrid-auto-engine`, `MINERU_LOCAL_IMAGE_ANALYSIS=true`, and signal compose to include `docker-compose.mineru-gpu.yml` (device reservation). **No GPU →** `MINERU_LOCAL_BACKEND=pipeline`, `MINERU_LOCAL_IMAGE_ANALYSIS=false`, no overlay. The probe writes a small generated env fragment the compose `mineru` service reads; LightRAG's parser already routes PDFs to the local MinerU endpoint. Open item: **pin the exact mineru-api image** you ran earlier (CPU vs sglang/vllm GPU build).

---

## 5. Implementation Phases

> infra+server-graft → identity → ingestion → chat (leakage-gated) → generators → realtime → news feed → **quiz last**.

### Phase 0 — Server graft + infra scaffold
**Build:** the `lightrag/api/sampai/` subpackage skeleton (`__init__` with `mount_sampai`/`sampai_startup`/`sampai_shutdown` no-op stubs, `config.py`, `registry.py`, empty routers) + the **3 fenced edits** to `lightrag_server.py` + `CHANGES.md` + `[sampai]` extras in root `pyproject.toml` + `APP_*`/`R2_*` in `env.example`; both compose files + `mineru` + `docling` services + GPU overlay + probe script + `Dockerfile.api/web` + nginx; alembic init; frontend scaffold (Vite+Tailwind+router+copied `ui/`+axios/TanStack Query).
**Accept:** **regression first** — the unmodified LightRAG routes still boot and `/query` works on the default workspace (original pipeline intact). Then: SAMpai mounts under `/api/sampai`, `/api/sampai/health` 200; a throwaway `get_engine("smoke")` initializes against Neo4j/Qdrant/Redis; MinerU+Docling containers reachable; probe picks the right backend.

### Phase 1 — Auth, classrooms, folders
19-table Alembic baseline (SAMpai.md §3, fixes: per-owner classroom-name uniqueness; clean announcement routes); SAMpai system-user seed; DB-user JWT auth; classrooms (6-char code, join, list, get, guards) + leave/delete; folders CRUD. Frontend: auth pages, dashboard, classroom shell, folder grid.
**Accept:** A creates / B joins by code; owner-only routes 403 for members; `sampai` username rejected.

### Phase 2 — Engine registry, ingestion (MinerU+Docling), gating
Finish `registry.py` (locks+eviction), `integrations/r2.py`, `ingestion.py` (queue, status map, summary, reprocess, delete), files router. Frontend: upload + staged progress polling + AI-tab locks + retry + download.
**Accept:** upload pdf (→MinerU) / docx/pptx (→Docling) / txt (→legacy) → PROCESSED; Neo4j nodes carry `classroom_{id}` label, Qdrant points the workspace payload; failed doc retries; delete clears KB (entity count drops) + R2 + rows.

### Phase 3 — Scoped gateway + per-file chat
`rag_gateway.py` (all 4 fns) + chat router (SSE stream, per-user history, stats). Frontend: chat tab (markdown, streaming, pinned summary, history, clear).
**Accept:** **leakage test (merge gate):** fact unique to file B is NOT answerable when chatting file A; per-user history; incremental streaming.

### Phase 4 — Flashcards + mindmaps
Flashcards (scoped context → strict-JSON cards, validation+retry, cross-deck dedup, Leitner, due query); mindmaps (`scoped_mix_context` → RootTopic+tree via json_schema, shared tree, explore-node MARKER/placeholder, per-user node chat). Frontend: flashcard stack + mastery bar; `@xyflow/react`+dagre canvas + node chat.
**Accept:** valid card mix; Leitner box transitions + intervals (clock-mock); tree within depth/children bounds; node summaries fill; tree shared, chat per-user.

### Phase 5 — Group chats + presence + @SAMpai
Thread/invite/member services (full §2.9: seq under `SELECT…FOR UPDATE`, `client_msg_id` idempotency, write-time mention parse), WS + hub + fan-out, rate limits, agent. Frontend: thread UI (optimistic, reconnect/gap-fill, typing, presence, replies, mention autocomplete), bell + invite toasts.
**Accept:** two clients live; presence/typing/receipts; 11th msg/10 s → 429; @SAMpai grounded + 3/60 s + refuses manipulation; invite lifecycle incl. cancel-dismisses-toast.

### Phase 6 — Announcements + comments + bell
CRUD (owner-post, member-comment, author/owner delete) + **nh3 sanitize on write**; bell aggregation. Frontend: TipTap editor, feed, threads.
**Accept:** `<script>` stripped server-side; member can't post (403); deletion rules; pagination.

### Phase 7 — Quizzes: per-file + cross-file ⚠️ DESIGN DISCUSSION FIRST (last)

**Per-file (SAMpai.md §2.6):** 202+poll+resume; one-open-quiz + 5-min stale abandon; difficulty manual/auto (last 20 chat turns + last 3 scores); MCQ/TF; deterministic grading + review; history. Difficulty → breadth via `retrieve_mix_arm` `max_depth` 1/2/3 + `top_k`/`chunk_top_k` scaling. Attempts in Postgres.

**Cross-file (headline new feature) — nearly free, the in-tree `lightrag/quiz/` was built multi-doc:**
- `QuizGenerateRequest.document_ids[]` accepts any docs in the classroom workspace; `_get_scope_chunk_ids` unions their `chunks_list`.
- Seed scoring carries a cross-doc RRF `xdoc` signal → **bridge entities** (in ≥2 docs) rank as seeds.
- `_bfs_subgraph` walks the classroom KG **across document boundaries** → forces synthesis questions.
- Per-question `source_documents[]`/`file_contributions` already exist → "draws on files X & Y" UI.

**Shape:** scope selector (this file / multiple / folder / whole classroom) → `doc_ids[]` (PROCESSED only) → `lightrag.quiz.generate_quiz(classroom_engine, req)` → quiz JSON in `{working_dir}/quizzes/`, attempts in Postgres (join on `quiz_id`).

**Open questions (decide before building):** (1) MCQ/TF native vs SAQ→MCQ convert; (2) grading (deterministic vs LLM judge for SAQ); (3) keep/strip the research verifier; (4) which metadata survives (keep `hop_depth`+`source_documents`); (5) difficulty UX; (6) mix-only vs naive flag; (7) quiz JSON vs full-Postgres; (8) concurrency/cost caps (`QUIZ_CONCURRENCY_CAP=1` too slow for product?).

**Accept:** quiz scoped to 1 file / a folder / whole classroom; sources ⊆ scope; hard > easy `hop_depth`; cross-file quiz has ≥1 question spanning ≥2 docs.

---

## 6. Risk Register

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Upstream fork divergence** (HKUDS/LightRAG fork; our edits conflict on every pull, must never PR up) | All code in `lightrag/api/sampai/`; `# --- SAMpai ---` fences on the ~3 server edits; `CHANGES.md` ledger; diff-size budget (§4.0) |
| 2 | **Breaking the original pipeline** | Registry is additive; original `rag` + 4 routers untouched; **Phase 0 regression test** verifies default `/query` still works; 0-line budget on core modules |
| 3 | **Scoped-retrieval leakage** | Reuse `_get_scope_chunk_ids`/`full_doc_id`/`source_id` filters verbatim; Phase 3 leakage merge-gate; content-hash doc_ids |
| 4 | **Must run 1 worker** (in-proc registry + WS hub) | Enforce `--workers 1`; Redis fan-out = future scaling seam; documented |
| 5 | **MinerU GPU/cold-start/throughput** | GPU-probe overlay; CPU `pipeline` fallback; model-weight volume; bounded ingestion queue; per-file timeout→FAILED; **pin the mineru-api image** |
| 6 | **Auth duality confusion** | SAMpai routes use `sampai_current_user` under `/api/sampai`; server's `combined_auth`/`/login` untouched |
| 7 | **PROCESSED-only gating feels slow** | Staged progress + duration copy + summary on ready |
| 8 | **Per-classroom engine memory** | Lazy create, LRU+TTL eviction, shared embed/LLM funcs, `APP_MAX_RESIDENT_ENGINES` |
| 9 | **Embedding dim mismatch** | Pin `EMBEDDING_DIM=3072`; assert at engine init; never swap model without dropping Qdrant collections |
| 10 | **OpenAI cost** | `enable_llm_cache`; cached summaries; agent + quiz caps; per-classroom token logging |

---

## 7. Verification

**Per phase:** acceptance criteria above; pytest per service (grading, Leitner, mentions, sanitization, scope filters with a fake vdb); **Phase 0 original-pipeline regression** + **Phase 3 leakage** + **Phase 5 rate-limit** are explicit merge gates.

**E2E demo:** `docker compose --profile data --profile parsing --profile app up` → signup teacher → create classroom → student joins → upload PDF (MinerU staged progress) → PROCESSED unlocks → scoped streamed chat → flashcards → mindmap → group chat + @SAMpai → announcement+comment → *(P7)* cross-chapter quiz with per-question sources spanning files.

---

## 8. Difficulties & Things To Be Aware Of

1. **Single-workspace → multi-tenant is the core surgery.** The server is built around one global `rag` (`lightrag_server.py:1938`). We add a registry beside it and resolve a per-classroom engine per request; the original `rag` and its four routers stay byte-for-byte intact, so the **original pipeline is unaffected**. The easy-to-miss detail: each classroom engine must get its own `initialize_pipeline_status(workspace=…)` — `rag.initialize_storages()` only inits the base workspace.
2. **Fork divergence is the biggest long-term cost.** This repo is a fork of `HKUDS/LightRAG` (AGENTS.md: PRs target upstream). Our changes must **never** be PR'd upstream and **will** conflict whenever you pull from upstream. Discipline keeps it cheap: 100% of new code in `lightrag/api/sampai/`, the ~3 edits in `lightrag_server.py` comment-fenced, and a `CHANGES.md` ledger so a future rebase is mechanical. Treat "small, fenced, logged core diff" as a hard rule.
3. **Auth duality — don't unify.** The server ships its own env-account `/login` + `combined_auth`. Our app needs real DB users (signup). These coexist cleanly because auth is a **per-route dependency**, not global middleware: SAMpai routes use `Depends(sampai_current_user)` under `/api/sampai`; the server's routes keep theirs. Trying to merge them would be the messy path.
4. **One worker, always.** The engine registry and WS hub live in process memory; uvicorn already forces a single worker, and running gunicorn with N workers would create N independent (broken) registries and split WS rooms. Run 1 worker; Redis fan-out is the only thing that would later allow scaling out.
5. **MinerU local is heavy and GPU-conditional.** The image is large; the GPU backend (`hybrid-auto-engine`) needs the NVIDIA Container Toolkit plus a first-run model-weight download (minutes); the CPU `pipeline` backend is reliable but slow per PDF. Docker Compose can't conditionally reserve a GPU, so the probe script selects an overlay file. You still need to **pin the exact mineru-api image** you used before — that's the one open infra item.
6. **WebUI coexistence is a non-issue if nginx owns `/`.** The server serves its own UI at `/webui` and redirects `/`; behind our nginx that redirect never fires (nginx serves our SPA at `/` and proxies `/api/*`). `/webui` stays available for debugging the raw LightRAG graph UI. No edit to the bundled webui.
7. **Clean source is an acceptance criterion, not a vibe.** Enforce a diff budget: ≤ ~20 changed lines in `lightrag_server.py`, **zero** changes in `lightrag/lightrag.py`, `operate.py`, `kg/`, `parser/`, `quiz/`. If a feature seems to need a core edit, push the logic into the subpackage instead.
8. **Config/env entanglement.** The server parses `global_args` and loads the root `.env` once at import. We add `APP_*`/`R2_*` vars it simply ignores, and read them via a `SampaiSettings` (pydantic-settings) in the subpackage. Don't route SAMpai config through the server's argparse — keep the two config systems side by side.

---

*Next step: Phase 0 (server graft + infra). The Phase 7 quiz discussion can happen any time before Phase 6 completes.*

# The Learning SAMpai

**SAMpai** is an AI-powered classroom learning platform. Teachers create virtual
classrooms and upload course materials; students join via a 6-character code and
learn from those materials through AI features that are **grounded in the uploaded
documents** — not the open internet.

The platform is built on a graph-based Retrieval-Augmented Generation (RAG) engine:
uploaded files are parsed, chunked, embedded, and organized into a knowledge graph,
so every page becomes instantly queryable.

## Features

- **Per-file AI chat** — RAG question-answering over a document, with conversation memory.
- **Adaptive quizzes** — difficulty inferred from the student's chat history and past scores; questions adapt until the student reaches mastery.
- **Spaced-repetition flashcards** — Leitner-box review scheduling.
- **Interactive mind maps** — a hierarchical topic tree with per-node AI explanations and contextual chat.
- **Real-time group study chats** — per-document group chats over WebSockets, with an AI tutor (**@SAMpai**) that answers when mentioned.
- **Announcements** — a classroom news feed with rich-text posts and comments.

Owners (classroom creators) manage folders, files, announcements, and the join code;
members join via code and use all the learning features. Chat history, quiz attempts,
flashcard decks, and mindmap chats are per-user private state, even when the underlying
file is shared classroom-wide.

## Architecture

| Layer | Technology |
|---|---|
| **Backend / API** | FastAPI (`lightrag/api/`, SAMpai layer under `lightrag/api/sampai/`) |
| **RAG engine** | Graph-based RAG with `mix` / `naive` retrieval modes |
| **App database** | PostgreSQL (users, classrooms, files, quizzes, chats, …) via SQLAlchemy + Alembic |
| **Knowledge graph** | Neo4j |
| **Vector store** | Qdrant |
| **KV / doc status** | Redis |
| **File storage** | Cloudflare R2 (S3-compatible) |
| **Document parsing** | docling and MinerU |
| **Web frontend** | React + Vite SPA (`sampai/frontend/`) |
| **Mobile app** | React Native + Expo (`sampai/mobile/`) |

## Repository layout

```
lightrag/            RAG engine + API server
  api/sampai/        SAMpai classroom layer (auth, classrooms, files, chat, quizzes, …)
  quiz/              quiz generation
sampai/
  frontend/          React + Vite web app
  mobile/            React Native (Expo) app
  docker/            deployment: compose files, Dockerfiles, nginx
  SAMpai.md          full feature & schema specification
  sampai-plan.md     build plan
```

## Running the stack

The full stack runs via Docker Compose using profiles:

- `data` — PostgreSQL, Neo4j, Qdrant, Redis
- `parsing` — docling, MinerU
- `app` — the API server and the web SPA

See **[Getting Started](#getting-started)** below for the full step-by-step setup.

## Getting Started

This is a guide for setting the project up **from a fresh copy** (e.g. from a USB
drive, with `.venv/` and `node_modules/` removed). Two paths are described — the
**local development** path is the most reliable to demonstrate; the **all-in-Docker**
path is a one-shot alternative.

### Prerequisites

| Tool | Used for |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Running the data stores (PostgreSQL, Neo4j, Qdrant, Redis) and parsers |
| [uv](https://docs.astral.sh/uv/) (Python ≥ 3.10) | Backend dependency management and running the server |
| [Bun](https://bun.sh/) (or Node.js ≥ 18) | Building / running the web frontend |

> **Important:** the project is configured by a `.env` file in the **repository root**.
> It holds the LLM/embedding API keys, the app database URL, the JWT secret, and the
> Cloudflare R2 (file storage) credentials. The AI features call external services, so
> a valid `.env` is required for the app to actually work. Copy the template
> `.env.example` to `.env` in the repository root and fill in the values marked `<...>`.

### Local development (recommended for a demo)

**1. Start the backing data stores** (and parsers) with Docker:

```bash
cd sampai/docker
docker compose --profile data --profile parsing up -d
```

This starts PostgreSQL, Neo4j, Qdrant, Redis, and the docling parser. (MinerU is
optional — its image is built locally; docling alone is enough to ingest documents.)

**2. Install backend dependencies and apply database migrations** — from the
**repository root**:

```bash
uv sync --extra sampai
uv run alembic -c lightrag/api/sampai/alembic.ini upgrade head
```

Migrations create the application schema **and seed the required `SAMpai` system
user** — the server will not function without this step. (Alembic must be run from
the repo root so it can find `.env` and the `lightrag` package.)

**3. Start the API server** — from the repository root:

```bash
uv run sampai-server
```

The API is served at <http://localhost:9621> (health check: `/api/sampai/health`).

**4. Start the web frontend** — in a second terminal:

```bash
cd sampai/frontend
bun install
bun run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to the backend on
`http://localhost:9621`, so the SPA and API share an origin (no CORS setup needed).

### All-in-Docker (alternative)

Build and run the entire stack — data stores, parsers, API, and web — in containers:

```bash
cd sampai/docker
docker compose --profile data --profile parsing --profile app up --build
```

Then apply migrations once (the API container does not auto-migrate):

```bash
docker compose exec api alembic -c lightrag/api/sampai/alembic.ini upgrade head
```

Service URLs:

| Service | URL |
|---|---|
| Web app | <http://localhost:8080> |
| API | <http://localhost:9621> |
| Neo4j browser | <http://localhost:7474> |
| Qdrant | <http://localhost:6333> |

GPU-accelerated MinerU is enabled by layering `docker-compose.mineru-gpu.yml`.

### Mobile app (optional)

```bash
cd sampai/mobile
npm install
npx expo start
```

Then open the project in the Expo Go app or an emulator. Point it at the running API
via the mobile app's configuration.

### Troubleshooting

- **`program not found: sampai-server`** — the dependencies aren't installed in the
  environment. Run `uv sync --extra sampai` (the plain `uv run` only installs base
  dependencies, not the `sampai` extra where FastAPI/uvicorn live).
- **Login fails / "system user" errors** — the database migrations haven't been
  applied. Run the `alembic ... upgrade head` step above.
- **AI features return errors** — check the LLM/embedding API keys and the storage
  connection settings in the root `.env`.

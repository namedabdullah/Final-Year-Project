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

```bash
cd sampai/docker

# copy and edit environment configuration first (see .env)
docker compose --profile data --profile parsing --profile app up
```

Services (default ports):

| Service | URL |
|---|---|
| Web app | http://localhost:8080 |
| API | http://localhost:9621 |
| Neo4j browser | http://localhost:7474 |
| Qdrant | http://localhost:6333 |

For host-side development (API and web on the host), use
`sampai/docker/docker-compose.dev.yml`. GPU-accelerated MinerU is enabled by layering
`docker-compose.mineru-gpu.yml`.

## Development

Backend (Python ≥ 3.10):

```bash
pip install ".[sampai]"   # installs the API server + SAMpai dependencies
sampai-server             # start the API server
```

Web frontend:

```bash
cd sampai/frontend
bun install
bun run dev
```

# 💼 ai-career-assistant-realworld

> **A production-grade RAG chatbot that answers questions about a professional profile
> with factual, cited answers — running locally or in the cloud with no paid LLM required.**

[![CI](https://github.com/fredericoahb/ai-career-assistant-realworld/actions/workflows/ci.yml/badge.svg)](https://github.com/fredericoahb/ai-career-assistant-realworld/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/fredericoahb/ai-career-assistant-realworld?quickstart=1)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack & Design Decisions](#tech-stack--design-decisions)
- [Quick Start (Docker — 1 command)](#quick-start-docker--1-command)
- [Manual Setup (Local Dev)](#manual-setup-local-dev)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Switching LLM Providers](#switching-llm-providers)
- [Switching Vector Store (DEV → PROD)](#switching-vector-store-dev--prod)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [Cloud Deployment (Free)](#cloud-deployment-free)
- [Contributing](#contributing)

---

## Features

| Category | Details |
|---|---|
| **RAG Pipeline** | Chunk → Embed → Store → Retrieve → Context → LLM → Cited answer |
| **Local LLM** | Ollama (llama3 default) — no API key, no cost |
| **Cloud LLM** | Groq free tier (llama-3.1-8b-instant) — recommended for cloud deployment |
| **Local Embeddings** | `all-MiniLM-L6-v2` via sentence-transformers — no API required |
| **Strict Mode** | Refuses answers when no evidence exists in the knowledge base |
| **Citations** | Every claim is annotated with `[Source N]` and the exact source document/section |
| **Two Vector Stores** | DEV: SQLite + FAISS &nbsp;/&nbsp; PROD: Postgres + pgvector |
| **Auth & RBAC** | JWT, admin role can ingest docs, user role can only chat |
| **Admin Panel** | Streamlit UI for uploading, listing, and deleting documents |
| **RealWorld-inspired API** | User registration/login, profile updates, tags — mirroring the [RealWorld spec](https://github.com/gothinkster/realworld) |
| **Observability** | Structured JSON logs (structlog), `/health` endpoint |
| **CI/CD** | GitHub Actions: lint → unit tests → integration tests → Docker build → Trivy scan |
| **One-command start** | `docker compose up --build` |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│                                                                  │
│  ┌─────────────┐   REST/JSON   ┌──────────────────────────────┐ │
│  │  Streamlit  │ ────────────► │       FastAPI Backend         │ │
│  │  (Chat UI + │               │                               │ │
│  │  Admin UI)  │               │  ┌────────┐  ┌─────────────┐ │ │
│  └─────────────┘               │  │  Auth  │  │   Ingest    │ │ │
│                                │  │ (JWT)  │  │  (admin)    │ │ │
│                                │  └────────┘  └──────┬──────┘ │ │
│                                │                     │        │ │
│                                │         ┌───────────▼──────┐ │ │
│                                │         │   RAG Pipeline   │ │ │
│                                │         │                  │ │ │
│                                │         │ 1. Chunker       │ │ │
│                                │         │ 2. Embedder      │ │ │
│                                │         │    (local model) │ │ │
│                                │         │ 3. Vector Store  │ │ │
│                                │         │    DEV:  FAISS   │ │ │
│                                │         │    PROD: pgvec   │ │ │
│                                │         │ 4. Retriever     │ │ │
│                                │         │ 5. LLM Client    │ │ │
│                                │         └────────┬─────────┘ │ │
│                                └──────────────────┼───────────┘ │
│                                                   │             │
│  ┌──────────────┐                    ┌────────────▼──────────┐  │
│  │   SQLite /   │◄───── ORM ────────│      SQLAlchemy       │  │
│  │  PostgreSQL  │                    └───────────────────────┘  │
│  └──────────────┘                                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  Ollama/Groq │◄──── HTTP ──── LLM Client                    │
│  │  (llama3)    │                                               │
│  └──────────────┘                                               │
└──────────────────────────────────────────────────────────────────┘
```

### RAG Flow (per query)

```
User question
     │
     ▼
embed_query()          ← sentence-transformers, always local, no API
     │
     ▼
vector_store.search()  ← FAISS (DEV) or pgvector (PROD)
     │
     ▼
filter by SIMILARITY_THRESHOLD
     │ no results + STRICT_MODE=true
     ├─────────────────────────────► "No evidence found" (safe refusal)
     │
     ▼ results found
assemble context block  ← "[Source N] (filename § Section)\n<chunk text>"
     │
     ▼
LLM.complete(system_prompt, context + question)
     │
     ▼
Answer with inline citations [Source 1], [Source 2]…
     │
     ▼
Return to client with full citation metadata
```

---

## Tech Stack & Design Decisions

### Why FastAPI (Python) over ASP.NET Core?

| Reason | Detail |
|---|---|
| **ML ecosystem** | sentence-transformers, FAISS, LangChain, and ollama-python are all Python-native. Using .NET would require subprocess calls or HTTP proxies. |
| **Async-first** | FastAPI's `async/await` model maps naturally to I/O-heavy RAG workloads (vector search + LLM calls). |
| **Dev velocity** | Pydantic v2 provides excellent schema validation, serialization, and OpenAPI generation out of the box. |
| **Community** | FastAPI + Python is the de facto standard for AI/ML API backends. Recruiters evaluating AI projects expect to see Python. |

### Why Streamlit over Next.js?

Streamlit was chosen because it keeps the codebase homogeneous (Python end-to-end), deploys for free on Hugging Face Spaces, and lets the backend sophistication be the focus rather than UI polish. If you prefer React, the FastAPI backend is a drop-in REST API — just replace `frontend/`.

### Why Groq for cloud deployment?

Ollama requires too much RAM for free cloud tiers. Groq offers a generous free tier with llama3 support (~500 tok/s), no credit card required, and is API-compatible with OpenAI's SDK format.

---

## Quick Start (Docker — 1 command)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) v2 (included in Docker Desktop)
- ~8 GB RAM free (for Ollama + llama3)
- ~8 GB disk (for the llama3 model)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/fredericoahb/ai-career-assistant-realworld.git
cd ai-career-assistant-realworld

# 2. Create your .env from the example
cp .env.example .env
# Edit .env and set a strong SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 3. Start everything (Ollama will auto-pull llama3 on first run — ~4 GB)
docker compose up --build

# 4. Wait for services to be healthy (~2-5 min on first run)
#    Watch the logs: docker compose logs -f ollama

# 5. Open the app
#    Frontend (chat):  http://localhost:8501
#    Backend API docs: http://localhost:8000/docs
#    Health check:     http://localhost:8000/health
```

### Seed the knowledge base

```bash
# 1. Register admin user
cat > /tmp/reg.json << 'EOF'
{"username":"admin","email":"admin@example.com","password":"admin123"}
EOF
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d @/tmp/reg.json

# 2. Promote to admin
docker compose exec backend python -c "
import asyncio
from app.models.database import AsyncSessionLocal
from app.models.db import User
from sqlalchemy import update

async def promote():
    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.username=='admin').values(is_admin=True))
        await s.commit()
        print('Admin promoted!')
asyncio.run(promote())
"

# 3. Login and get token
cat > /tmp/login.json << 'EOF'
{"email":"admin@example.com","password":"admin123"}
EOF
TOKEN=$(curl -s -X POST http://localhost:8000/api/users/login \
  -H "Content-Type: application/json" \
  -d @/tmp/login.json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 4. Ingest the sample CV
curl -X POST http://localhost:8000/api/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample_cv.md"
```

Now open http://localhost:8501, register a regular user, and start chatting!

---

## Manual Setup (Local Dev)

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and configure env
cp ../.env.example ../.env
# Set VECTOR_STORE_MODE=dev, OLLAMA_BASE_URL=http://localhost:11434

# Start Ollama (install from https://ollama.com)
ollama serve &
ollama pull llama3

# Run backend
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
pip install -r requirements.txt
API_BASE_URL=http://localhost:8000 streamlit run app.py --server.port 8501
```

---

## API Reference

Full interactive docs available at **http://localhost:8000/docs** (Swagger UI).

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/users` | ✗ | Register new user |
| `POST` | `/api/users/login` | ✗ | Login, returns JWT |
| `GET` | `/api/users/me` | ✓ | Get current user profile |
| `PUT` | `/api/users/me` | ✓ | Update bio/avatar |

### Chat (RAG)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/chat` | ✓ | Ask a question; returns cited answer |
| `GET` | `/api/chat/sessions/{id}/history` | ✓ | Get full conversation history |

#### `POST /api/chat` — Example

```json
// Request
{
  "question": "What cloud certifications does the candidate hold?",
  "session_id": null
}

// Response
{
  "answer": "The candidate holds three certifications: Google Professional Cloud Architect (2023) [Source 1], CKA from CNCF (2022) [Source 2], and AWS Solutions Architect – Associate (2020) [Source 3].",
  "citations": [
    { "index": 1, "source_label": "sample_cv.md § Certifications", "excerpt": "Google Professional Cloud Architect (2023)..." },
    { "index": 2, "source_label": "sample_cv.md § Certifications", "excerpt": "Certified Kubernetes Administrator (CKA)..." },
    { "index": 3, "source_label": "sample_cv.md § Certifications", "excerpt": "AWS Solutions Architect – Associate (2020)..." }
  ],
  "has_evidence": true,
  "session_id": 1
}
```

### Ingest (Admin only)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/ingest` | Admin | Upload and index a document |
| `GET` | `/api/ingest` | Admin | List all ingested documents |
| `DELETE` | `/api/ingest/{id}` | Admin | Remove document and its vectors |

### Utility

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | ✗ | System health check |
| `GET` | `/api/tags` | ✗ | List available tags |

---

## Environment Variables

See [`.env.example`](.env.example) for the full list with comments.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | ⚠️ **CHANGE ME** | JWT signing secret |
| `VECTOR_STORE_MODE` | `dev` | `dev` (SQLite+FAISS) or `prod` (Postgres+pgvector) |
| `LLM_PROVIDER` | `ollama` | `ollama` \| `groq` \| `openai` \| `anthropic` |
| `OLLAMA_MODEL` | `llama3` | Any model available in your Ollama instance |
| `GROQ_API_KEY` | `` | Free key from https://console.groq.com |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model to use |
| `STRICT_MODE` | `true` | Refuse answers without evidence |
| `SIMILARITY_THRESHOLD` | `0.30` | Minimum cosine similarity to include a chunk |
| `CHUNK_SIZE` | `400` | Tokens per chunk |

---

## Switching LLM Providers

The LLM is swappable at runtime via environment variables — no code changes needed.

```bash
# Use Groq (recommended for cloud — free tier, fast)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant

# Use OpenAI GPT-4o-mini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Use Anthropic Claude Haiku
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-haiku-20240307
```

---

## Switching Vector Store (DEV → PROD)

```bash
# 1. Start Postgres with pgvector
docker compose -f docker-compose.prod.yml up postgres -d

# 2. Update .env
VECTOR_STORE_MODE=prod
POSTGRES_DSN=postgresql+asyncpg://career:secret@localhost:5432/career_db

# 3. Restart backend — tables and indexes are auto-created
docker compose -f docker-compose.prod.yml up --build backend
```

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

| File | Description |
|---|---|
| `tests/test_chunker.py` | Unit tests: chunking, dedup, section parsing |
| `tests/test_integration.py` | Integration tests: /auth, /ingest, /chat, /health |

```bash
# With coverage report
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

---

## Project Structure

```
ai-career-assistant-realworld/
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory + lifespan
│   │   ├── config.py               # Pydantic settings (all env vars)
│   │   ├── observability.py        # Structured logging (structlog)
│   │   │
│   │   ├── auth/
│   │   │   ├── service.py          # JWT creation/verification, bcrypt
│   │   │   ├── dependencies.py     # FastAPI deps: get_current_user, require_admin
│   │   │   └── router.py           # /api/users endpoints (RealWorld-inspired)
│   │   │
│   │   ├── rag/
│   │   │   ├── chunker.py          # Markdown-aware sliding-window chunker + dedup
│   │   │   ├── embedder.py         # sentence-transformers (always local, no API)
│   │   │   ├── vector_store.py     # FAISS (DEV) + pgvector (PROD) adapters
│   │   │   ├── llm.py              # Ollama / Groq / OpenAI / Anthropic clients
│   │   │   └── pipeline.py         # Full RAG flow: query → cited answer
│   │   │
│   │   ├── api/
│   │   │   ├── chat.py             # POST /api/chat — RAG Q&A
│   │   │   ├── ingest.py           # POST /api/ingest — admin doc upload
│   │   │   └── health.py           # GET /health, GET /api/tags
│   │   │
│   │   └── models/
│   │       ├── db.py               # SQLAlchemy ORM: User, Document, Chunk, Chat
│   │       └── database.py         # Engine factory (SQLite or Postgres)
│   │
│   ├── tests/
│   │   ├── test_chunker.py         # Unit tests for RAG chunker
│   │   └── test_integration.py     # Integration tests (httpx + mocked RAG)
│   │
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
│
├── frontend/
│   ├── app.py                      # Streamlit chat UI (main page)
│   ├── pages/
│   │   └── 1_Admin.py              # Admin panel: upload / list / delete docs
│   ├── Dockerfile
│   └── requirements.txt
│
├── data/
│   └── sample_cv.md                # Fictional CV for demo (no real PII)
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # lint → test → docker build → trivy scan
│
├── .devcontainer/
│   └── devcontainer.json           # GitHub Codespaces configuration
│
├── docker-compose.yml              # DEV stack (SQLite + FAISS + Ollama)
├── docker-compose.prod.yml         # PROD stack (Postgres + pgvector + Ollama)
├── railway.toml                    # Railway deployment configuration
├── .env.example                    # Environment variable template
├── .gitignore
└── README.md
```

---

## Cloud Deployment (Free)

> ⚠️ Free tier limits may vary. Always check the provider's current terms.

### Recommended architecture

```
User → Hugging Face Spaces (Streamlit UI) → Railway Backend (FastAPI + FAISS)
                                                      ↓
                                             Groq API (free LLM)
```

### Step 1 — Get a free Groq API key

1. Go to **https://console.groq.com** and sign up (no credit card required)
2. Navigate to **API Keys → Create API Key**
3. Copy the key (starts with `gsk_...`)

### Step 2 — Deploy the backend on Railway

1. Go to **https://railway.app** and log in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select `ai-career-assistant-realworld`
4. In the service **Settings**, set **Root Directory** to `backend`
5. Go to **Variables** and add:

```
SECRET_KEY          → python -c "import secrets; print(secrets.token_hex(32))"
LLM_PROVIDER        → groq
GROQ_API_KEY        → gsk_...your key...
GROQ_MODEL          → llama-3.1-8b-instant
VECTOR_STORE_MODE   → dev
SQLITE_PATH         → /app/data/dev.db
FAISS_INDEX_PATH    → /app/data/faiss.index
FAISS_META_PATH     → /app/data/faiss_meta.json
STRICT_MODE         → true
EMBEDDING_MODEL     → all-MiniLM-L6-v2
CORS_ORIGINS        → ["https://YOUR_HF_USERNAME.hf.space","http://localhost:8501"]
```

6. In **Settings → Networking**, click **Generate Domain**
7. Test: `curl https://your-app.railway.app/health`

> Railway offers ~$5 free credit/month — sufficient for a portfolio project with light traffic.

### Step 3 — Seed the knowledge base on Railway

```bash
BACKEND="https://your-app.railway.app"

# Register admin
cat > /tmp/reg.json << 'EOF'
{"username":"admin","email":"admin@example.com","password":"admin123"}
EOF
curl -X POST $BACKEND/api/users -H "Content-Type: application/json" -d @/tmp/reg.json

# Login
cat > /tmp/login.json << 'EOF'
{"email":"admin@example.com","password":"admin123"}
EOF
TOKEN=$(curl -s -X POST $BACKEND/api/users/login \
  -H "Content-Type: application/json" -d @/tmp/login.json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Ingest CV
curl -X POST $BACKEND/api/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample_cv.md"
```

To promote admin, use the Railway shell (service → `...` → Shell):
```python
import asyncio
from app.models.database import AsyncSessionLocal
from app.models.db import User
from sqlalchemy import update

async def run():
    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.username=='admin').values(is_admin=True))
        await s.commit()
        print('Done!')
asyncio.run(run())
```

### Step 4 — Deploy the frontend on Hugging Face Spaces

1. Go to **https://huggingface.co/new-space**
2. Fill in: Space name `ai-career-assistant`, SDK `Streamlit`, Visibility `Public`
3. Add the HF remote and push:

```bash
git remote add hf https://huggingface.co/spaces/YOUR_HF_USERNAME/ai-career-assistant
git subtree push --prefix frontend hf main
```

4. In the Space **Settings → Variables and secrets**, add:
   - `API_BASE_URL` = `https://your-app.railway.app`

### Alternative providers

| Provider | Service | Free Tier | Notes |
|---|---|---|---|
| [Render](https://render.com) | Backend | Yes (sleeps on inactivity) | Alternative to Railway |
| [Fly.io](https://fly.io) | Backend | Yes (256 MB RAM) | Requires credit card |
| [Koyeb](https://koyeb.com) | Backend | Yes (512 MB RAM) | Good alternative |
| [Streamlit Cloud](https://share.streamlit.io) | Frontend | Yes | Alternative to HF Spaces |

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Add tests for any new logic
4. Run `ruff check . && black . && pytest` before pushing
5. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built to demonstrate real-world RAG engineering practices: chunking, embeddings, vector search, cited answers, JWT auth, RBAC, and cloud deployment.*

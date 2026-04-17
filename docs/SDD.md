# Software Design Document (SDD)
## AI Career Assistant — RealWorld

**Version:** 1.0  
**Date:** April 2026  
**Author:** Frederico Homobono  
**Status:** Active

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Architecture Design](#3-architecture-design)
4. [Component Design](#4-component-design)
5. [Data Design](#5-data-design)
6. [API Design](#6-api-design)
7. [RAG Pipeline Design](#7-rag-pipeline-design)
8. [Security Design](#8-security-design)
9. [Deployment Architecture](#9-deployment-architecture)
10. [Design Decisions & Trade-offs](#10-design-decisions--trade-offs)
11. [Non-Functional Requirements](#11-non-functional-requirements)

---

## 1. Introduction

### 1.1 Purpose

This document describes the software design of the **AI Career Assistant**, a production-grade RAG (Retrieval-Augmented Generation) chatbot that answers questions about a professional profile with factual, cited answers. It serves as the authoritative reference for architecture, component design, data models, and design decisions made throughout the project.

### 1.2 Scope

The system covers:
- A **FastAPI backend** handling authentication, document ingestion, and the RAG pipeline
- A **Streamlit frontend** providing a chat interface and admin panel
- A **pluggable LLM layer** supporting Ollama, Groq, OpenAI, and Anthropic
- A **dual-mode vector store** (SQLite+FAISS for dev, PostgreSQL+pgvector for prod)
- A **CI/CD pipeline** via GitHub Actions

### 1.3 Definitions

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation — retrieves relevant context before generating an answer |
| **Chunk** | A fixed-size segment of a document, the unit of vector indexing |
| **Embedding** | Dense numerical vector representing semantic meaning of text |
| **pgvector** | PostgreSQL extension for vector similarity search |
| **FAISS** | Facebook AI Similarity Search — in-memory vector index |
| **RBAC** | Role-Based Access Control |
| **JWT** | JSON Web Token — stateless authentication mechanism |

---

## 2. System Overview

The AI Career Assistant is a portfolio showcase system designed to demonstrate real-world AI engineering practices. A user can ask natural-language questions about a professional profile, and the system returns grounded, cited answers sourced from indexed documents.

### 2.1 Goals

- Demonstrate production-quality RAG engineering (chunking, embedding, retrieval, citation)
- Provide a fully local-first option (no paid API required)
- Be straightforwardly deployable to free cloud tiers
- Follow the [RealWorld](https://github.com/gothinkster/realworld) API spec for auth/user management

### 2.2 Non-Goals

- Real-time chat streaming (out of scope for v1)
- Multi-tenant support (single knowledge base per deployment)
- Mobile-native clients

### 2.3 User Roles

```
┌─────────────┐     ┌─────────────┐
│  Anonymous  │     │    User     │     ┌─────────────┐
│             │     │             │     │    Admin    │
│  Register   │────▶│   Chat      │     │             │
│  Login      │     │  View history│────▶│  Chat       │
└─────────────┘     └─────────────┘     │  Ingest docs│
                                        │  Delete docs│
                                        └─────────────┘
```

---

## 3. Architecture Design

### 3.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         User Browser                         │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼──────────────────────────────────┐
│              Streamlit Frontend (port 8501)                   │
│         Chat UI  │  Admin Panel (document management)        │
└───────────────────────────┬──────────────────────────────────┘
                            │ REST API (HTTP/JSON)
┌───────────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (port 8000)                      │
│                                                               │
│   ┌───────────┐  ┌─────────────┐  ┌────────────────────┐    │
│   │   Auth    │  │   Ingest    │  │     RAG Pipeline   │    │
│   │  (JWT)    │  │  (chunker + │  │  (embed → search   │    │
│   │  (bcrypt) │  │   embedder) │  │   → LLM → cite)   │    │
│   └───────────┘  └──────┬──────┘  └────────┬───────────┘    │
│                         │                   │                 │
└─────────────────────────┼───────────────────┼─────────────────┘
                          │                   │
        ┌─────────────────▼───────────────────▼─────────────┐
        │                 Data Layer                         │
        │                                                    │
        │   DEV: SQLite + FAISS index (local files)         │
        │   PROD: PostgreSQL + pgvector (ANN index)         │
        └─────────────────────────────────────┬──────────────┘
                                              │
                         ┌────────────────────▼────────────────┐
                         │           LLM Provider               │
                         │  Ollama (local) │ Groq │ OpenAI      │
                         │                 │      │ Anthropic   │
                         └─────────────────────────────────────┘
```

### 3.2 Docker Compose Services

| Service | Image | Port | Depends On |
|---|---|---|---|
| `backend` | `./backend/Dockerfile` | 8000 | db (prod), ollama (if local) |
| `frontend` | `./frontend/Dockerfile` | 8501 | backend |
| `ollama` | `ollama/ollama` | 11434 | — |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | — (prod only) |

### 3.3 Runtime Environment

- **Language:** Python 3.11
- **ASGI server:** Uvicorn
- **Container runtime:** Docker 24+
- **Orchestration:** Docker Compose v2 (dev/prod variants)

---

## 4. Component Design

### 4.1 Backend Components

#### 4.1.1 Auth Module (`app/auth/`)

Responsibility: stateless JWT authentication and bcrypt password hashing.

```
auth/
├── service.py       — create_token(), verify_token(), hash_password(), verify_password()
├── dependencies.py  — get_current_user(), require_admin()  [FastAPI DI]
└── router.py        — POST /api/users, POST /api/users/login, GET/PUT /api/users/me
```

Key design choice: tokens carry `user_id` and `is_admin` claims — no database lookup on each request for the common case (chat endpoint). Admin operations re-validate `is_admin` from the DB to handle revocation.

#### 4.1.2 RAG Module (`app/rag/`)

```
rag/
├── chunker.py       — Markdown-aware sliding-window segmentation + SHA-256 dedup
├── embedder.py      — sentence-transformers singleton (all-MiniLM-L6-v2, local only)
├── vector_store.py  — FAISSVectorStore / PgVectorStore behind a common interface
├── llm.py           — LLMClient factory (Ollama / Groq / OpenAI / Anthropic)
└── pipeline.py      — orchestrates the full query → cited answer flow
```

#### 4.1.3 API Module (`app/api/`)

```
api/
├── chat.py    — POST /api/chat, GET /api/chat/sessions/{id}/history
├── ingest.py  — POST /api/ingest, GET /api/ingest, DELETE /api/ingest/{id}
└── health.py  — GET /health, GET /api/tags
```

#### 4.1.4 Models (`app/models/`)

```
models/
├── db.py        — SQLAlchemy ORM: User, Document, Chunk, ChatSession, ChatMessage
└── database.py  — async engine factory, session lifecycle
```

### 4.2 Frontend Components

```
frontend/
├── app.py           — Chat page: session management, message stream, citation display
└── pages/
    └── 1_Admin.py   — Admin panel: file upload, document list table, delete action
```

The frontend is intentionally thin — all business logic lives in the backend. Streamlit `st.session_state` stores the JWT token and current session ID client-side.

---

## 5. Data Design

### 5.1 Entity-Relationship Overview

```
User ──< ChatSession ──< ChatMessage
  │
  └──< (admin) Document ──< Chunk
                              │
                              └── [vector index: FAISS / pgvector]
```

### 5.2 Table Definitions

#### `users`
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK, autoincrement |
| username | VARCHAR(50) | UNIQUE, NOT NULL |
| email | VARCHAR(100) | UNIQUE, NOT NULL |
| hashed_password | VARCHAR(200) | NOT NULL |
| bio | TEXT | nullable |
| image | VARCHAR(200) | nullable |
| is_admin | BOOLEAN | DEFAULT false |
| created_at | TIMESTAMP | DEFAULT now() |

#### `documents`
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| filename | VARCHAR(255) | NOT NULL |
| content_hash | VARCHAR(64) | UNIQUE (SHA-256 dedup) |
| uploaded_by | INTEGER | FK → users.id |
| uploaded_at | TIMESTAMP | DEFAULT now() |

#### `chunks`
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| document_id | INTEGER | FK → documents.id, CASCADE DELETE |
| content | TEXT | NOT NULL |
| chunk_hash | VARCHAR(64) | UNIQUE (SHA-256 dedup) |
| section | VARCHAR(255) | nullable (Markdown heading) |
| chunk_index | INTEGER | position within document |

#### `chat_sessions`
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| user_id | INTEGER | FK → users.id |
| created_at | TIMESTAMP | DEFAULT now() |

#### `chat_messages`
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| session_id | INTEGER | FK → chat_sessions.id |
| role | VARCHAR(10) | 'user' or 'assistant' |
| content | TEXT | NOT NULL |
| citations | JSON | nullable |
| created_at | TIMESTAMP | DEFAULT now() |

### 5.3 Vector Index Schema

**DEV (FAISS):** vectors stored in a `.index` file; metadata (chunk_id, document filename, section) serialized to a parallel JSON file.

**PROD (pgvector):**
```sql
CREATE TABLE chunk_vectors (
    id          SERIAL PRIMARY KEY,
    chunk_id    INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
    embedding   VECTOR(384),               -- all-MiniLM-L6-v2 dimension
    created_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX ON chunk_vectors USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

## 6. API Design

### 6.1 Conventions

- Base path: `/api`
- Content-Type: `application/json` (except file upload: `multipart/form-data`)
- Auth header: `Authorization: Bearer <JWT>`
- Error format: `{"detail": "<message>"}`
- HTTP status codes follow REST semantics (200, 201, 400, 401, 403, 404, 422, 500)

### 6.2 Auth Endpoints

| Method | Path | Body | Response | Auth |
|---|---|---|---|---|
| POST | `/api/users` | `{username, email, password}` | `{id, username, email, token}` | — |
| POST | `/api/users/login` | `{email, password}` | `{id, username, email, token}` | — |
| GET | `/api/users/me` | — | `{id, username, email, bio, image}` | ✓ |
| PUT | `/api/users/me` | `{bio?, image?}` | updated user | ✓ |

### 6.3 Chat Endpoints

| Method | Path | Body | Response | Auth |
|---|---|---|---|---|
| POST | `/api/chat` | `{question, session_id?}` | `{answer, citations, has_evidence, session_id}` | ✓ |
| GET | `/api/chat/sessions/{id}/history` | — | `[{role, content, citations}]` | ✓ |

**Chat response schema:**
```json
{
  "answer": "string",
  "citations": [
    {
      "index": 1,
      "source_label": "document.md § Section",
      "excerpt": "relevant text snippet..."
    }
  ],
  "has_evidence": true,
  "session_id": 42
}
```

### 6.4 Ingest Endpoints (Admin)

| Method | Path | Body | Response | Auth |
|---|---|---|---|---|
| POST | `/api/ingest` | `file: multipart` | `{document_id, chunks_created}` | Admin |
| GET | `/api/ingest` | — | `[{id, filename, uploaded_at}]` | Admin |
| DELETE | `/api/ingest/{id}` | — | `204 No Content` | Admin |

### 6.5 Utility Endpoints

| Method | Path | Response | Auth |
|---|---|---|---|
| GET | `/health` | `{status, vector_store, llm_provider}` | — |
| GET | `/api/tags` | `["tag1", "tag2"]` | — |

---

## 7. RAG Pipeline Design

### 7.1 Ingestion Flow

```
File Upload (multipart)
        │
        ▼
   SHA-256 dedup check ──── duplicate? ──▶ 409 Conflict
        │
        ▼
   Markdown-aware chunker
   (sliding window, 400 tokens, 50-token overlap)
        │
        ▼
   Per-chunk SHA-256 dedup (skip already-indexed chunks)
        │
        ▼
   sentence-transformers embed_batch()
   (all-MiniLM-L6-v2, 384 dimensions)
        │
        ▼
   Vector store add() ──── FAISS (dev) / pgvector (prod)
        │
        ▼
   DB: insert Document + Chunk rows
        │
        ▼
   Return {document_id, chunks_created}
```

### 7.2 Query Flow

```
POST /api/chat {question}
        │
        ▼
   Embed question → vector (384-dim)
        │
        ▼
   Vector store search(top_k=5)
   cosine similarity against all indexed chunks
        │
        ▼
   Similarity threshold filter (default: 0.30)
        │
   No chunks pass? ──── STRICT_MODE=true ──▶ safe refusal response
        │
        ▼
   Context assembly:
   "[Source 1] (filename § Section)\n{chunk_text}\n..."
        │
        ▼
   LLM prompt construction:
   system: "Answer using ONLY the provided sources. Cite each claim."
   user:   "{context}\n\nQuestion: {question}"
        │
        ▼
   LLM generate() → raw answer
        │
        ▼
   Citation extraction: parse [Source N] references
        │
        ▼
   Persist to chat_messages
        │
        ▼
   Return {answer, citations, has_evidence, session_id}
```

### 7.3 Chunker Design

The Markdown chunker uses a **heading-aware sliding window**:

1. Splits on Markdown headings (`##`, `###`) to preserve section context
2. Within each section, applies a 400-token sliding window with 50-token overlap
3. Each chunk carries its `section` label (used in citations as `filename § Section`)
4. Deduplication via SHA-256 of normalized chunk content prevents re-indexing on re-upload

### 7.4 LLM Provider Abstraction

```python
class LLMClient(Protocol):
    async def generate(self, system: str, user: str) -> str: ...

# Factory resolves at startup via LLM_PROVIDER env var:
# "ollama"    → OllamaClient    (local, no cost)
# "groq"      → GroqClient      (free tier, fast)
# "openai"    → OpenAIClient    (GPT-4o-mini recommended)
# "anthropic" → AnthropicClient (Claude Haiku recommended)
```

All clients implement the same `generate()` interface — the pipeline is provider-agnostic.

---

## 8. Security Design

### 8.1 Authentication

- **Algorithm:** HMAC-SHA256 (HS256) JWT
- **Token expiry:** 7 days
- **Payload claims:** `sub` (user_id), `is_admin`, `exp`
- **Password hashing:** bcrypt with default work factor (12 rounds)

### 8.2 Authorization

FastAPI dependency injection enforces RBAC at the route level:

```
Route handler
     │
     └── Depends(get_current_user)  ─── decodes JWT, loads User from DB
              │
              └── Depends(require_admin)  ─── asserts user.is_admin == True
```

Admin status is verified from the database (not just the token claim) on admin routes, allowing revocation by flipping `is_admin=False`.

### 8.3 Input Validation

- All request bodies validated by **Pydantic v2** with strict types
- File uploads limited to `.md`, `.txt`, `.pdf` extensions (configurable)
- SQL injection prevented by SQLAlchemy ORM with parameterized queries
- No raw SQL strings anywhere in the codebase

### 8.4 CORS

`CORS_ORIGINS` env var controls the allowed-origins list. In production, this is locked to the exact Hugging Face Spaces URL. Defaults to `["http://localhost:8501"]` for dev.

### 8.5 Secrets Management

- `SECRET_KEY` must be a random 256-bit hex string — the app refuses to start if it equals the default placeholder
- All secrets injected via environment variables; no secrets committed to git
- `.env` is in `.gitignore`; `.env.example` contains only safe placeholder values

---

## 9. Deployment Architecture

### 9.1 Dev Environment

```
docker compose up --build
├── backend  (FastAPI + FAISS + SQLite)
├── frontend (Streamlit)
└── ollama   (llama3 pulled on first run)
```

### 9.2 Production Environment (Free Tier)

```
Hugging Face Spaces          Railway                    Groq API
┌──────────────────┐        ┌──────────────┐           ┌──────────┐
│  Streamlit UI    │──HTTP──▶  FastAPI      │──HTTPS───▶│  LLM     │
│  (HF Spaces)     │        │  + FAISS     │           │  (Free)  │
└──────────────────┘        │  + SQLite    │           └──────────┘
                            └──────────────┘
```

### 9.3 Production Environment (Scaled)

```
Hugging Face Spaces          Railway                    Groq / OpenAI
┌──────────────────┐        ┌──────────────┐           ┌──────────┐
│  Streamlit UI    │──HTTP──▶  FastAPI      │──HTTPS───▶│  LLM     │
└──────────────────┘        │  + pgvector  │           └──────────┘
                            └──────┬───────┘
                                   │
                            ┌──────▼───────┐
                            │  PostgreSQL  │
                            │  + pgvector  │
                            └──────────────┘
```

### 9.4 CI/CD Pipeline

```
Push to main / PR
        │
        ▼
┌──────────────────────────────────────────────┐
│              GitHub Actions CI               │
│                                              │
│  1. ruff check + black --check (lint)        │
│  2. pytest unit tests (test_chunker)         │
│  3. pytest integration tests (mocked RAG)    │
│  4. Docker build (backend + frontend)        │
│  5. Trivy image vulnerability scan           │
└──────────────────────────────────────────────┘
```

---

## 10. Design Decisions & Trade-offs

### 10.1 Why FAISS over Chroma or Weaviate for DEV?

| Option | Pros | Cons |
|---|---|---|
| **FAISS (chosen)** | Zero dependencies, in-memory, battle-tested at Meta scale | No persistence (mitigated with `.index` file), no metadata filtering |
| Chroma | Built-in persistence, metadata filtering | Extra service or embedded SQLite variant adds complexity |
| Weaviate | Full-featured, HTTP API | Too heavy for a dev/CI environment |

FAISS was chosen because it has zero external dependencies and runs fully in-process, making CI fast and reproducible.

### 10.2 Why pgvector over Qdrant or Pinecone for PROD?

pgvector keeps the stack uniform (one database for both relational and vector data), eliminates a separate vector DB service, and is free on Railway. The IVFFLAT index handles the expected document volume (< 100K chunks) with excellent performance.

### 10.3 Why sentence-transformers (local) instead of OpenAI Embeddings?

Embedding with a local model (`all-MiniLM-L6-v2`) means:
- Zero cost at any scale
- No API key required for the core RAG flow
- Consistent embeddings regardless of provider API changes
- Works in air-gapped or offline environments

The 384-dimension model is a deliberate trade-off against larger models (1536-dim) — latency and storage are lower, and quality is sufficient for domain-specific CV/portfolio documents.

### 10.4 Why Streamlit over React/Next.js?

Streamlit keeps the codebase 100% Python, deploys for free on Hugging Face Spaces, and allows backend sophistication to be the portfolio focus. The FastAPI backend is a clean REST API — swapping the frontend for React is a one-day task if needed.

### 10.5 Why the RealWorld API spec for Auth?

The [RealWorld](https://github.com/gothinkster/realworld) spec is a well-known benchmark for full-stack implementations. Using it signals familiarity with real-world API design patterns and makes the auth layer immediately familiar to reviewers who know the spec.

### 10.6 Strict Mode

When `STRICT_MODE=true` and no chunks exceed the similarity threshold, the system returns a safe refusal instead of hallucinating an answer. This is the correct behavior for a system whose job is to answer factual questions about a specific person — fabricated answers are worse than "I don't know."

---

## 11. Non-Functional Requirements

### 11.1 Performance

| Metric | Target | Notes |
|---|---|---|
| Chat response time (Groq) | < 3s p95 | Network + LLM latency |
| Chat response time (Ollama/local) | < 15s p95 | Depends on hardware |
| Embedding latency (per query) | < 100ms | Local model, CPU |
| Vector search latency | < 50ms | FAISS/pgvector, < 100K chunks |
| Ingest throughput | > 5 pages/sec | CPU-bound, chunking + embedding |

### 11.2 Reliability

- FastAPI lifespan hooks initialize the vector store and embedding model at startup — if either fails, the service refuses to start rather than serving partial functionality
- `/health` endpoint reports the status of vector store connectivity and LLM availability for use by load balancers and uptime monitors

### 11.3 Observability

- **Structured JSON logs** via `structlog` on every request, ingest event, and RAG pipeline stage
- **Request ID** injected into log context via middleware for distributed tracing
- **Log fields:** `event`, `duration_ms`, `user_id`, `endpoint`, `llm_provider`, `chunks_retrieved`

### 11.4 Testability

- Dependency injection via FastAPI's `Depends()` system allows mocking at the route level
- Integration tests use `httpx.AsyncClient` with a real SQLite DB and mocked LLM/embedder
- Unit tests for the chunker are fully deterministic (no external dependencies)

### 11.5 Portability

- All configuration via environment variables (12-factor app)
- Docker Compose for local reproducibility
- No OS-specific assumptions in the codebase (runs on Linux, macOS, Windows via Docker)

---

*This document reflects the design as implemented in v1.0. Proposed changes to architecture or data models should be reviewed against this document before implementation.*

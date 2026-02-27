"""Integration tests for /chat and /ingest endpoints.

Uses an in-memory SQLite DB and mocked vector store + LLM.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.database import AsyncSessionLocal, create_db_and_tables, engine
from app.models.db import Base


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create fresh tables for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    """Register an admin user and return its JWT. Admin flag set directly in DB."""
    resp = await client.post("/api/users", json={
        "username": "admin",
        "email": "admin@example.com",
        "password": "adminpass123",
    })
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]

    # Promote to admin directly in DB
    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        from app.models.db import User
        await session.execute(update(User).where(User.username == "admin").values(is_admin=True))
        await session.commit()

    # Re-login to get token with is_admin=True
    resp2 = await client.post("/api/users/login", json={
        "email": "admin@example.com",
        "password": "adminpass123",
    })
    return resp2.json()["token"]


@pytest_asyncio.fixture
async def user_token(client: AsyncClient):
    resp = await client.post("/api/users", json={
        "username": "regularuser",
        "email": "user@example.com",
        "password": "userpass123",
    })
    assert resp.status_code == 201
    return resp.json()["token"]


# ── Auth Tests ────────────────────────────────────────────────────────────────

class TestAuth:
    async def test_register_success(self, client):
        resp = await client.post("/api/users", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "secret",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert "token" in data

    async def test_register_duplicate_email(self, client):
        payload = {"username": "u1", "email": "dup@example.com", "password": "pass"}
        await client.post("/api/users", json=payload)
        resp = await client.post("/api/users", json={**payload, "username": "u2"})
        assert resp.status_code == 422

    async def test_login_wrong_password(self, client):
        await client.post("/api/users", json={"username": "u", "email": "u@e.com", "password": "right"})
        resp = await client.post("/api/users/login", json={"email": "u@e.com", "password": "wrong"})
        assert resp.status_code == 401


# ── Ingest Tests ──────────────────────────────────────────────────────────────

class TestIngest:
    @patch("app.api.ingest.get_vector_store")
    @patch("app.api.ingest.embed_texts")
    async def test_ingest_markdown(self, mock_embed, mock_store, client, admin_token):
        import numpy as np

        mock_embed.return_value = np.random.rand(5, 384).astype("float32")
        store = AsyncMock()
        store.add = AsyncMock()
        store.flush = AsyncMock()
        mock_store.return_value = store

        content = b"# Experience\nSoftware engineer at Acme Corp for 5 years.\n\n# Skills\nPython, FastAPI, Docker."
        resp = await client.post(
            "/api/ingest",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("cv.md", io.BytesIO(content), "text/markdown")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["chunks_created"] > 0
        assert data["deduplicated"] is False

    async def test_ingest_requires_admin(self, client, user_token):
        content = b"Some content"
        resp = await client.post(
            "/api/ingest",
            headers={"Authorization": f"Bearer {user_token}"},
            files={"file": ("file.md", io.BytesIO(content), "text/markdown")},
        )
        assert resp.status_code == 403

    async def test_ingest_requires_auth(self, client):
        content = b"Some content"
        resp = await client.post(
            "/api/ingest",
            files={"file": ("file.md", io.BytesIO(content), "text/markdown")},
        )
        assert resp.status_code == 401

    @patch("app.api.ingest.get_vector_store")
    @patch("app.api.ingest.embed_texts")
    async def test_ingest_deduplication(self, mock_embed, mock_store, client, admin_token):
        import numpy as np

        mock_embed.return_value = np.random.rand(2, 384).astype("float32")
        store = AsyncMock()
        store.add = AsyncMock()
        store.flush = AsyncMock()
        mock_store.return_value = store

        content = b"# Skills\nPython, Docker."
        file_args = ("cv.md", io.BytesIO(content), "text/markdown")

        # First ingest
        r1 = await client.post(
            "/api/ingest",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": file_args},
        )
        assert r1.status_code == 201

        # Second ingest of identical content
        r2 = await client.post(
            "/api/ingest",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("cv2.md", io.BytesIO(content), "text/markdown")},
        )
        assert r2.status_code == 201
        assert r2.json()["deduplicated"] is True


# ── Chat Tests ────────────────────────────────────────────────────────────────

class TestChat:
    @patch("app.api.chat.run_rag")
    async def test_chat_success(self, mock_rag, client, user_token):
        from app.rag.pipeline import Citation, RAGResponse, SearchResult

        mock_rag.return_value = RAGResponse(
            answer="The candidate has 5 years of experience at Acme Corp [Source 1].",
            citations=[Citation(index=1, source_label="cv.md § Experience", excerpt="5 years at Acme")],
            retrieved_chunks=[],
            has_evidence=True,
        )

        resp = await client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"question": "How many years of experience does the candidate have?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_evidence"] is True
        assert len(data["citations"]) == 1
        assert "session_id" in data

    @patch("app.api.chat.run_rag")
    async def test_chat_no_evidence_strict_mode(self, mock_rag, client, user_token):
        from app.rag.pipeline import RAGResponse

        mock_rag.return_value = RAGResponse(
            answer="I don't have enough information in the knowledge base to answer that question.",
            citations=[],
            retrieved_chunks=[],
            has_evidence=False,
        )

        resp = await client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"question": "What is the candidate's bank account number?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_evidence"] is False
        assert data["citations"] == []

    async def test_chat_requires_auth(self, client):
        resp = await client.post("/api/chat", json={"question": "Hello?"})
        assert resp.status_code == 401

    async def test_chat_empty_question(self, client, user_token):
        resp = await client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"question": "   "},
        )
        assert resp.status_code == 422

    @patch("app.api.chat.run_rag")
    async def test_chat_session_continuity(self, mock_rag, client, user_token):
        from app.rag.pipeline import RAGResponse

        mock_rag.return_value = RAGResponse(
            answer="Yes [Source 1].", citations=[], retrieved_chunks=[], has_evidence=True
        )

        r1 = await client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"question": "First question?"},
        )
        session_id = r1.json()["session_id"]

        r2 = await client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"question": "Follow-up?", "session_id": session_id},
        )
        assert r2.json()["session_id"] == session_id


# ── Health Tests ──────────────────────────────────────────────────────────────

class TestHealth:
    async def test_health_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "version" in data

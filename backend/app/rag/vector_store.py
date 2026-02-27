"""Vector store abstraction with two adapters.

* DEV  – FAISS flat index persisted as a local file (SQLite stores metadata).
* PROD – pgvector via SQLAlchemy (requires the pgvector extension).
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from app.config import VectorStoreMode, settings
from app.observability import get_logger

log = get_logger(__name__)


@dataclass
class SearchResult:
    chunk_id: int        # DocumentChunk.id in SQL
    text: str
    source_label: str
    score: float         # cosine similarity [0, 1]


# ── Abstract interface ────────────────────────────────────────────────────────

class VectorStore(ABC):
    @abstractmethod
    async def add(self, chunk_id: int, text: str, source_label: str, vector: np.ndarray) -> None: ...

    @abstractmethod
    async def search(self, query_vector: np.ndarray, top_k: int) -> list[SearchResult]: ...

    @abstractmethod
    async def delete_by_document(self, chunk_ids: list[int]) -> None: ...

    @abstractmethod
    async def flush(self) -> None:
        """Persist to disk / commit (no-op for DB adapters)."""


# ── FAISS adapter (DEV) ───────────────────────────────────────────────────────

class FAISSVectorStore(VectorStore):
    """In-memory FAISS flat-IP index backed by a JSON metadata file."""

    def __init__(self) -> None:
        import faiss  # noqa: PLC0415

        self._faiss = faiss
        self._index: faiss.IndexFlatIP | None = None
        self._meta: list[dict] = []   # parallel list to FAISS vectors
        self._dim: int = 0
        self._load()

    def _load(self) -> None:
        if os.path.exists(settings.FAISS_INDEX_PATH) and os.path.exists(settings.FAISS_META_PATH):
            import faiss  # noqa: PLC0415

            log.info("faiss_loading_index", path=settings.FAISS_INDEX_PATH)
            self._index = faiss.read_index(settings.FAISS_INDEX_PATH)
            with open(settings.FAISS_META_PATH) as f:
                self._meta = json.load(f)
            self._dim = self._index.d
        else:
            self._index = None

    def _ensure_index(self, dim: int) -> None:
        if self._index is None:
            import faiss  # noqa: PLC0415

            self._dim = dim
            self._index = faiss.IndexFlatIP(dim)

    async def add(self, chunk_id: int, text: str, source_label: str, vector: np.ndarray) -> None:
        self._ensure_index(vector.shape[0])
        vec = vector.reshape(1, -1).astype(np.float32)
        self._index.add(vec)  # type: ignore[attr-defined]
        self._meta.append({"chunk_id": chunk_id, "text": text, "source_label": source_label})

    async def search(self, query_vector: np.ndarray, top_k: int) -> list[SearchResult]:
        if self._index is None or self._index.ntotal == 0:  # type: ignore[attr-defined]
            return []
        k = min(top_k, self._index.ntotal)  # type: ignore[attr-defined]
        q = query_vector.reshape(1, -1).astype(np.float32)
        distances, indices = self._index.search(q, k)  # type: ignore[attr-defined]
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            meta = self._meta[idx]
            results.append(
                SearchResult(
                    chunk_id=meta["chunk_id"],
                    text=meta["text"],
                    source_label=meta["source_label"],
                    score=float(dist),
                )
            )
        return results

    async def delete_by_document(self, chunk_ids: list[int]) -> None:
        # FAISS flat index does not support deletion; rebuild without those IDs
        if self._index is None:
            return
        import faiss  # noqa: PLC0415

        ids_to_remove = set(chunk_ids)
        new_meta = []
        new_vectors = []
        for i, meta in enumerate(self._meta):
            if meta["chunk_id"] not in ids_to_remove:
                new_meta.append(meta)
                vec = self._index.reconstruct(i)  # type: ignore[attr-defined]
                new_vectors.append(vec)

        self._index = faiss.IndexFlatIP(self._dim)
        self._meta = new_meta
        if new_vectors:
            self._index.add(np.vstack(new_vectors))  # type: ignore[attr-defined]

    async def flush(self) -> None:
        if self._index is None:
            return
        import faiss  # noqa: PLC0415

        os.makedirs(os.path.dirname(settings.FAISS_INDEX_PATH) or ".", exist_ok=True)
        faiss.write_index(self._index, settings.FAISS_INDEX_PATH)
        with open(settings.FAISS_META_PATH, "w") as f:
            json.dump(self._meta, f)
        log.info("faiss_index_saved", path=settings.FAISS_INDEX_PATH, total=self._index.ntotal)


# ── pgvector adapter (PROD) ───────────────────────────────────────────────────

class PGVectorStore(VectorStore):
    """pgvector adapter using raw asyncpg queries for performance."""

    def __init__(self) -> None:
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg  # noqa: PLC0415
            from app.config import settings as s

            dsn = s.POSTGRES_DSN.replace("postgresql+asyncpg://", "postgresql://")
            self._pool = await asyncpg.create_pool(dsn)
            await self._ensure_table()
        return self._pool

    async def _ensure_table(self) -> None:
        pool = self._pool
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    chunk_id    INTEGER PRIMARY KEY,
                    text        TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    embedding   vector(384)
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS vector_chunks_embedding_idx
                ON vector_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

    async def add(self, chunk_id: int, text: str, source_label: str, vector: np.ndarray) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO vector_chunks(chunk_id, text, source_label, embedding) "
                "VALUES($1, $2, $3, $4::vector) ON CONFLICT (chunk_id) DO UPDATE "
                "SET text=EXCLUDED.text, source_label=EXCLUDED.source_label, embedding=EXCLUDED.embedding",
                chunk_id, text, source_label, vector.tolist(),
            )

    async def search(self, query_vector: np.ndarray, top_k: int) -> list[SearchResult]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT chunk_id, text, source_label, "
                "1 - (embedding <=> $1::vector) AS score "
                "FROM vector_chunks "
                "ORDER BY embedding <=> $1::vector "
                "LIMIT $2",
                query_vector.tolist(), top_k,
            )
        return [
            SearchResult(chunk_id=r["chunk_id"], text=r["text"], source_label=r["source_label"], score=float(r["score"]))
            for r in rows
        ]

    async def delete_by_document(self, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM vector_chunks WHERE chunk_id = ANY($1)", chunk_ids)

    async def flush(self) -> None:
        pass  # DB is always consistent


# ── Factory ───────────────────────────────────────────────────────────────────

_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        if settings.VECTOR_STORE_MODE == VectorStoreMode.DEV:
            _store = FAISSVectorStore()
        else:
            _store = PGVectorStore()
    return _store

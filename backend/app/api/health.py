"""Health check + tags endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db
from app.models.db import Tag
from app.rag.vector_store import get_vector_store

router = APIRouter(tags=["utility"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + readiness probe."""
    # DB ping
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    # Vector store info
    store = get_vector_store()
    store_info = type(store).__name__

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": settings.APP_VERSION,
        "vector_store": store_info,
        "vector_store_mode": settings.VECTOR_STORE_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.OLLAMA_MODEL if settings.LLM_PROVIDER == "ollama" else settings.OPENAI_MODEL,
        "db": db_status,
    }


@router.get("/api/tags")
async def list_tags(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag))
    tags = result.scalars().all()
    return {"tags": [t.name for t in tags]}

"""Chat endpoint: accepts a question, runs RAG, returns a cited answer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.models.database import get_db
from app.models.db import ChatMessage, ChatSession, User
from app.observability import get_logger
from app.rag.pipeline import RAGResponse, run_rag

log = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    session_id: int | None = None   # pass to continue existing session


class CitationOut(BaseModel):
    index: int
    source_label: str
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    has_evidence: bool
    session_id: int


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    # Session management
    if payload.session_id:
        from sqlalchemy import select
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == payload.session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        session: ChatSession | None = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = ChatSession(user_id=current_user.id)
        db.add(session)
        await db.flush()

    # Run RAG
    try:
        rag_result: RAGResponse = await run_rag(payload.question)
    except Exception as exc:
        log.error("rag_error", error=str(exc), question=payload.question[:80])
        raise HTTPException(status_code=502, detail=f"RAG pipeline error: {exc}") from exc

    # Persist messages
    db.add(ChatMessage(session_id=session.id, role="user", content=payload.question))
    db.add(ChatMessage(session_id=session.id, role="assistant", content=rag_result.answer))
    await db.commit()

    return ChatResponse(
        answer=rag_result.answer,
        citations=[
            CitationOut(index=c.index, source_label=c.source_label, excerpt=c.excerpt)
            for c in rag_result.citations
        ],
        has_evidence=rag_result.has_evidence,
        session_id=session.id,
    )


@router.get("/sessions/{session_id}/history", response_model=list[dict])
async def session_history(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    msgs = sorted(session.messages, key=lambda m: m.created_at)
    return [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in msgs]

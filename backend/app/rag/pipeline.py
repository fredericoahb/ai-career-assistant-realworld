"""Full RAG pipeline: query → retrieve → assemble context → LLM → cited answer."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.observability import get_logger
from app.rag.embedder import embed_query
from app.rag.llm import get_llm_client
from app.rag.vector_store import SearchResult, get_vector_store

log = get_logger(__name__)

SYSTEM_PROMPT = """\
You are a factual career assistant. You ONLY answer questions about the professional \
profile described in the provided context passages.

Rules:
1. Base every claim on the context below. If the information is not present, say so explicitly.
2. End each factual statement with a citation in the form [Source N].
3. If no relevant context is found and strict mode is active, respond with:
   "I don't have enough information in the knowledge base to answer that question."
4. Do NOT fabricate, guess, or add information not present in the context.
5. Respond in the same language as the question.
"""


@dataclass
class Citation:
    index: int
    source_label: str
    excerpt: str


@dataclass
class RAGResponse:
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[SearchResult]
    has_evidence: bool


async def run_rag(query: str) -> RAGResponse:
    """Execute the full RAG pipeline for a user query."""
    log.info("rag_query", query=query[:120])

    # 1. Embed query
    q_vec = embed_query(query)

    # 2. Retrieve
    store = get_vector_store()
    results = await store.search(q_vec, top_k=settings.TOP_K)

    # 3. Filter by similarity threshold
    filtered = [r for r in results if r.score >= settings.SIMILARITY_THRESHOLD]
    has_evidence = bool(filtered)

    if not has_evidence and settings.STRICT_MODE:
        log.warning("rag_no_evidence", query=query[:80])
        return RAGResponse(
            answer="I don't have enough information in the knowledge base to answer that question.",
            citations=[],
            retrieved_chunks=results,
            has_evidence=False,
        )

    # 4. Build context string
    context_lines: list[str] = []
    citations: list[Citation] = []
    for i, chunk in enumerate(filtered, start=1):
        context_lines.append(f"[Source {i}] ({chunk.source_label})\n{chunk.text}")
        citations.append(Citation(index=i, source_label=chunk.source_label, excerpt=chunk.text[:200]))

    context_block = "\n\n---\n\n".join(context_lines)
    user_message = f"Context:\n\n{context_block}\n\n---\n\nQuestion: {query}"

    # 5. LLM call
    llm = get_llm_client()
    answer = await llm.complete(system=SYSTEM_PROMPT, user=user_message)

    log.info("rag_answer_generated", sources=len(citations), answer_len=len(answer))
    return RAGResponse(answer=answer, citations=citations, retrieved_chunks=results, has_evidence=True)

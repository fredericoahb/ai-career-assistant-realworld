"""LLM abstraction: Ollama (local, default) | OpenAI | Anthropic.

Provider is chosen at runtime via LLM_PROVIDER env var.
All providers implement the same `complete(prompt) -> str` interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import LLMProvider, settings
from app.observability import get_logger

log = get_logger(__name__)


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


# ── Ollama ────────────────────────────────────────────────────────────────────

class OllamaClient(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        import httpx  # noqa: PLC0415

        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(base_url=settings.OLLAMA_BASE_URL, timeout=120) as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["message"]["content"]


# ── OpenAI (optional) ─────────────────────────────────────────────────────────

class OpenAIClient(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# ── Anthropic (optional) ──────────────────────────────────────────────────────

class AnthropicClient(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        import anthropic  # noqa: PLC0415

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text


# ── Factory ───────────────────────────────────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        match settings.LLM_PROVIDER:
            case LLMProvider.OLLAMA:
                _client = OllamaClient()
            case LLMProvider.OPENAI:
                _client = OpenAIClient()
            case LLMProvider.ANTHROPIC:
                _client = AnthropicClient()
    return _client

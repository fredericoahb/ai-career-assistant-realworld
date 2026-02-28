"""LLM abstraction: Ollama (local, default) | Groq (free cloud) | OpenAI | Anthropic.

Provider is chosen at runtime via LLM_PROVIDER env var.
All providers implement the same `complete(prompt) -> str` interface.

Recommended for cloud deployment: Groq (free tier, fast, llama3 support).
Get a free key at: https://console.groq.com
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import LLMProvider, settings
from app.observability import get_logger

log = get_logger(__name__)


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


# ── Ollama (local) ────────────────────────────────────────────────────────────

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


# ── Groq (free cloud) ─────────────────────────────────────────────────────────

class GroqClient(LLMClient):
    """Groq offers a generous free tier with very fast inference.
    Supports: llama-3.1-8b-instant, llama-3.3-70b-versatile, mixtral-8x7b-32768.
    Get a free API key at: https://console.groq.com
    """

    async def complete(self, system: str, user: str) -> str:
        import httpx  # noqa: PLC0415

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


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
            case LLMProvider.GROQ:
                _client = GroqClient()
            case LLMProvider.OPENAI:
                _client = OpenAIClient()
            case LLMProvider.ANTHROPIC:
                _client = AnthropicClient()
    return _client

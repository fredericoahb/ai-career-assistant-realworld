"""Central configuration loaded from environment variables / .env file."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorStoreMode(str, Enum):
    DEV = "dev"   # SQLite + FAISS (in-process)
    PROD = "prod"  # Postgres + pgvector


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"      # optional paid provider
    ANTHROPIC = "anthropic"  # optional paid provider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ─────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Career Assistant"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_in_production_use_openssl_rand_hex_32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 h

    # ── Database ─────────────────────────────────────────────────────────────
    VECTOR_STORE_MODE: VectorStoreMode = VectorStoreMode.DEV

    # SQLite (DEV)
    SQLITE_PATH: str = "./data/dev.db"

    # Postgres (PROD) – only required when VECTOR_STORE_MODE=prod
    POSTGRES_DSN: str = "postgresql+asyncpg://user:pass@localhost:5432/career_db"

    # ── RAG ───────────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 400        # tokens per chunk
    CHUNK_OVERLAP: int = 80
    TOP_K: int = 5               # retrieved chunks per query
    SIMILARITY_THRESHOLD: float = 0.30   # discard below this (strict mode)
    STRICT_MODE: bool = True     # refuse answer when no evidence is found

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"   # local sentence-transformers model
    FAISS_INDEX_PATH: str = "./data/faiss.index"
    FAISS_META_PATH: str = "./data/faiss_meta.json"

    # ── LLM ───────────────────────────────────────────────────────────────────
    LLM_PROVIDER: LLMProvider = LLMProvider.OLLAMA

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3"

    # OpenAI (optional, only if LLM_PROVIDER=openai)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic (optional, only if LLM_PROVIDER=anthropic)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:8501", "http://frontend:8501"]


settings = Settings()

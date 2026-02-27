"""Local embedding generation using sentence-transformers.

The model is downloaded on first use and cached in ~/.cache/huggingface.
No API key required.
"""

from __future__ import annotations

import numpy as np
from functools import lru_cache

from app.config import settings
from app.observability import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer  # lazy import

    log.info("loading_embedding_model", model=settings.EMBEDDING_MODEL)
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return float32 numpy array of shape (N, D)."""
    if not texts:
        return np.empty((0,), dtype=np.float32)
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """Return float32 1-D array of shape (D,)."""
    return embed_texts([query])[0]

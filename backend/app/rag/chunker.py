"""Document chunking with overlap and section-aware labelling.

Strategy
--------
1. Split on markdown headings to produce semantically coherent sections.
2. Within each section, apply a sliding-window token chunker.
3. Each chunk carries a human-readable ``source_label`` used as citation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class Chunk:
    text: str
    source_label: str           # e.g.  "cv.md § Experience > Senior Engineer"
    document_filename: str
    chunk_index: int
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()


# ── helpers ──────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


def _naive_token_count(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars (BPE proxy)."""
    return max(1, len(text) // 4)


def _split_by_tokens(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Sliding window over words respecting max_tokens budget."""
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        token_count = 0
        while end < len(words) and token_count < max_tokens:
            token_count += max(1, len(words[end]) // 4)
            end += 1
        chunk_text = " ".join(words[start:end]).strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end >= len(words):
            break
        # step back by overlap
        overlap_chars = 0
        step_end = end
        while step_end > start and overlap_chars < overlap_tokens * 4:
            step_end -= 1
            overlap_chars += len(words[step_end])
        start = max(start + 1, step_end)
    return chunks


# ── public API ────────────────────────────────────────────────────────────────

def chunk_document(text: str, filename: str) -> list[Chunk]:
    """Return deduplicated chunks for the given raw document text."""
    sections = _extract_sections(text)
    chunks: list[Chunk] = []
    idx = 0
    seen_hashes: set[str] = set()

    for section_title, section_body in sections:
        label = f"{filename} § {section_title}"
        token_chunks = _split_by_tokens(
            section_body,
            max_tokens=settings.CHUNK_SIZE,
            overlap_tokens=settings.CHUNK_OVERLAP,
        )
        for raw in token_chunks:
            c = Chunk(
                text=raw,
                source_label=label,
                document_filename=filename,
                chunk_index=idx,
            )
            if c.content_hash in seen_hashes:
                continue  # deduplicate
            seen_hashes.add(c.content_hash)
            chunks.append(c)
            idx += 1

    return chunks


def _extract_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown by headings; falls back to treating the whole text as one section."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("document", text)]

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = _WHITESPACE_RE.sub(" ", text[body_start:body_end]).strip()
        if body:
            sections.append((title, body))

    # Content before first heading
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.insert(0, ("preamble", preamble))

    return sections

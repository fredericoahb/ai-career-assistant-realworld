"""Unit tests for the RAG chunker module."""

from __future__ import annotations

import pytest

from app.rag.chunker import Chunk, chunk_document, _extract_sections, _split_by_tokens


# ── _extract_sections ─────────────────────────────────────────────────────────

class TestExtractSections:
    def test_single_heading(self):
        text = "# Introduction\nThis is the intro.\n"
        sections = _extract_sections(text)
        assert len(sections) == 1
        assert sections[0][0] == "Introduction"
        assert "intro" in sections[0][1]

    def test_multiple_headings(self):
        text = "# Section A\nContent A\n\n## Section B\nContent B\n"
        sections = _extract_sections(text)
        assert len(sections) == 2
        assert sections[0][0] == "Section A"
        assert sections[1][0] == "Section B"

    def test_no_headings_fallback(self):
        text = "Just some plain text without any headings."
        sections = _extract_sections(text)
        assert len(sections) == 1
        assert sections[0][0] == "document"

    def test_preamble_before_first_heading(self):
        text = "Preamble content here.\n\n# Main Section\nBody text.\n"
        sections = _extract_sections(text)
        titles = [s[0] for s in sections]
        assert "preamble" in titles
        assert "Main Section" in titles


# ── _split_by_tokens ──────────────────────────────────────────────────────────

class TestSplitByTokens:
    def test_small_text_single_chunk(self):
        text = "Hello world this is a short sentence."
        chunks = _split_by_tokens(text, max_tokens=200, overlap_tokens=20)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_large_text_multiple_chunks(self):
        # ~400 words → should produce multiple chunks with max_tokens=50
        text = " ".join([f"word{i}" for i in range(400)])
        chunks = _split_by_tokens(text, max_tokens=50, overlap_tokens=5)
        assert len(chunks) > 1

    def test_overlap_content(self):
        words = [f"w{i}" for i in range(100)]
        text = " ".join(words)
        chunks = _split_by_tokens(text, max_tokens=20, overlap_tokens=5)
        if len(chunks) > 1:
            # Last words of chunk N should appear in the beginning of chunk N+1
            last_words_of_first = set(chunks[0].split()[-5:])
            first_words_of_second = set(chunks[1].split()[:10])
            assert last_words_of_first & first_words_of_second, "No overlap found between consecutive chunks"


# ── chunk_document ────────────────────────────────────────────────────────────

class TestChunkDocument:
    def test_basic_markdown(self):
        text = "# Experience\nWorked at Acme Corp.\n\n# Education\nBS Computer Science."
        chunks = chunk_document(text, "cv.md")
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all("cv.md" in c.source_label for c in chunks)

    def test_deduplication(self):
        # Same section content repeated should yield only one chunk
        repeated_section = "# Skills\nPython, FastAPI, Docker.\n"
        text = repeated_section + repeated_section  # intentional dup
        chunks = chunk_document(text, "dup.md")
        texts = [c.text for c in chunks]
        assert len(texts) == len(set(texts)), "Duplicate chunks not removed"

    def test_empty_document_returns_empty(self):
        chunks = chunk_document("", "empty.md")
        assert chunks == []

    def test_chunk_index_sequential(self):
        text = "# A\n" + " ".join([f"w{i}" for i in range(500)])
        chunks = chunk_document(text, "long.md")
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_content_hash_unique(self):
        text = "# Work\nDifferent content in each section.\n\n# Life\nOther unique content here."
        chunks = chunk_document(text, "unique.md")
        hashes = [c.content_hash for c in chunks]
        assert len(hashes) == len(set(hashes))

    def test_source_label_contains_section(self):
        text = "# Projects\nBuilt a RAG system.\n"
        chunks = chunk_document(text, "portfolio.md")
        assert any("Projects" in c.source_label for c in chunks)

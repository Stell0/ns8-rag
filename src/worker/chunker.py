"""Simple character-based chunking with overlap.

This is intentionally minimal and deterministic so retrieval verification is
reproducible. Token-aware chunking can replace this later without changing
DB or query contracts.
"""
from __future__ import annotations

CHUNKER_VERSION = "char-v1"


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks

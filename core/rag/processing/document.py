"""
Document Processing & Text Chunking Pipeline for EdgeMind RAG.

Handles text normalization, sliding-window chunking with overlap,
SHA-256 cryptographic fingerprints, source tracking, and metadata extraction.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.config import get_settings
from core.sanitization import (
    MAX_TITLE_CHARS,
    normalize_unicode,
    sanitize_text,
    strip_null_bytes,
    strip_unsafe_control_characters,
)


@dataclass
class ProcessedChunk:
    """A single chunk produced by chunking a document."""
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    content_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    is_global: bool = False
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None
    vector_dim: Optional[int] = None


@dataclass
class ProcessedDocument:
    """A normalized document and its metadata."""
    id: uuid.UUID
    title: str
    content: str
    content_hash: str
    source_uri: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    is_global: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentProcessor:
    """
    Normalizes, hashes, and chunks text documents with configurable overlap.
    """

    def __init__(
        self,
        default_chunk_size: Optional[int] = None,
        default_chunk_overlap: Optional[int] = None,
    ):
        settings = get_settings()
        self.chunk_size = default_chunk_size or settings.rag_chunk_size
        self.chunk_overlap = default_chunk_overlap or settings.rag_chunk_overlap

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text:
        - Safe Unicode normalization (NFC + surrogate handling)
        - Replace CRLF / CR with LF
        - Strip null bytes and unsafe control characters
        - Collapse consecutive spaces while preserving paragraph breaks
        """
        if not text:
            return ""
        s = normalize_unicode(text)
        s = strip_null_bytes(s)
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        s = strip_unsafe_control_characters(s, keep_newlines=True, keep_tabs=True)
        # Normalize multiple horizontal spaces/tabs
        s = re.sub(r"[ \t]+", " ", s)
        # Collapse 3+ newlines into 2
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    @staticmethod
    def compute_sha256(text: str) -> str:
        """Compute SHA-256 cryptographic fingerprint."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def chunk_text(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[str]:
        """
        Split text into overlapping character chunks respecting boundary breaks.
        """
        size = chunk_size if chunk_size is not None else self.chunk_size
        overlap = chunk_overlap if chunk_overlap is not None else self.chunk_overlap

        if size <= 0:
            raise ValueError(f"chunk_size must be positive, got {size}")
        if overlap < 0:
            raise ValueError(f"chunk_overlap must be non-negative, got {overlap}")
        if overlap >= size:
            raise ValueError(f"chunk_overlap ({overlap}) must be strictly less than chunk_size ({size})")

        normalized = self.normalize_text(text)
        if not normalized:
            return []

        if len(normalized) <= size:
            return [normalized]

        chunks: List[str] = []
        step = size - overlap
        start = 0

        while start < len(normalized):
            end = start + size
            chunk = normalized[start:end]

            # If not at the very end of the text, attempt to find a clean break (newline or space)
            if end < len(normalized):
                # Search backwards for last newline or space within the last 20% of the chunk
                lookback = int(size * 0.2)
                sub = chunk[-lookback:]
                break_idx = -1
                for delim in ("\n\n", "\n", ". ", " "):
                    pos = sub.rfind(delim)
                    if pos != -1:
                        break_idx = len(chunk) - lookback + pos + len(delim.rstrip())
                        break

                if break_idx > 0:
                    chunk = chunk[:break_idx]
                    start += len(chunk) - overlap
                else:
                    start += step
            else:
                start += step

            clean_chunk = chunk.strip()
            if clean_chunk:
                chunks.append(clean_chunk)

        return chunks

    def process_document(
        self,
        title: str,
        content: str,
        source_uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        is_global: bool = False,
        document_id: Optional[uuid.UUID] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Tuple[ProcessedDocument, List[ProcessedChunk]]:
        """
        Process a document: normalize, fingerprint, and produce indexed chunks.
        """
        normalized_content = self.normalize_text(content)
        content_hash = self.compute_sha256(normalized_content)
        doc_id = document_id or uuid.uuid4()
        meta = dict(metadata or {})

        safe_title = sanitize_text(title, max_length=MAX_TITLE_CHARS, allow_newlines=False)
        doc = ProcessedDocument(
            id=doc_id,
            title=safe_title or "Untitled Document",
            content=normalized_content,
            content_hash=content_hash,
            source_uri=source_uri,
            metadata=meta,
            user_id=user_id,
            project_id=project_id,
            is_global=is_global,
        )

        raw_chunks = self.chunk_text(
            normalized_content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        chunks: List[ProcessedChunk] = []
        for idx, chunk_text in enumerate(raw_chunks):
            chunk_hash = self.compute_sha256(chunk_text)
            chunk_meta = dict(meta)
            chunk_meta.update({
                "chunk_index": idx,
                "total_chunks": len(raw_chunks),
                "source_title": title,
            })
            if source_uri:
                chunk_meta["source_uri"] = source_uri

            chunk = ProcessedChunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                chunk_index=idx,
                content=chunk_text,
                content_hash=chunk_hash,
                metadata=chunk_meta,
                user_id=user_id,
                project_id=project_id,
                is_global=is_global,
            )
            chunks.append(chunk)

        return doc, chunks

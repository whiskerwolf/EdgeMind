"""
Knowledge Document & Chunk Repository for EdgeMind RAG.

Provides asynchronous SQLAlchemy 2.0 operations for vector storage,
fingerprint-based deduplication, tenant isolation, and similarity search.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database.models.knowledge_chunk import KnowledgeChunk
from core.database.models.knowledge_document import KnowledgeDocument
from core.rag.processing.document import ProcessedChunk, ProcessedDocument


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0

    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class KnowledgeRepository:
    """
    Repository for managing knowledge documents and vector chunks.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_document_by_id(
        self,
        document_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[KnowledgeDocument]:
        """Fetch a document by ID with tenant isolation check."""
        stmt = (
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks))
            .where(KnowledgeDocument.id == document_id)
        )
        if user_id is not None:
            stmt = stmt.where(
                or_(
                    KnowledgeDocument.is_global.is_(True),
                    KnowledgeDocument.user_id == user_id,
                )
            )
        else:
            stmt = stmt.where(KnowledgeDocument.is_global.is_(True))

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_document_by_hash(
        self,
        content_hash: str,
        user_id: Optional[uuid.UUID] = None,
        is_global: bool = False,
    ) -> Optional[KnowledgeDocument]:
        """Lookup document by content hash to detect duplicate content."""
        stmt = (
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks))
            .where(KnowledgeDocument.content_hash == content_hash)
        )
        if is_global:
            stmt = stmt.where(KnowledgeDocument.is_global.is_(True))
        elif user_id is not None:
            stmt = stmt.where(KnowledgeDocument.user_id == user_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def store_document(
        self,
        doc: ProcessedDocument,
        chunks: List[ProcessedChunk],
        overwrite_existing: bool = True,
    ) -> KnowledgeDocument:
        """
        Store a document and its vector chunks with duplicate content detection.
        """
        existing = await self.get_document_by_hash(
            content_hash=doc.content_hash,
            user_id=doc.user_id,
            is_global=doc.is_global,
        )

        if existing and not overwrite_existing:
            return existing

        if existing and overwrite_existing:
            # Update metadata and replace chunks
            existing.title = doc.title
            existing.source_uri = doc.source_uri
            existing.doc_metadata = doc.metadata
            await self.session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.document_id == existing.id)
            )
            doc_id = existing.id
            db_doc = existing
        else:
            doc_id = doc.id
            db_doc = KnowledgeDocument(
                id=doc_id,
                title=doc.title,
                source_uri=doc.source_uri,
                content_hash=doc.content_hash,
                doc_metadata=doc.metadata,
                user_id=doc.user_id,
                project_id=doc.project_id,
                is_global=doc.is_global,
            )
            self.session.add(db_doc)

        for chunk in chunks:
            db_chunk = KnowledgeChunk(
                id=chunk.id,
                document_id=doc_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                embedding_model=chunk.embedding_model,
                vector_dim=chunk.vector_dim,
                embedding=chunk.embedding,
                chunk_metadata=chunk.metadata,
                user_id=doc.user_id,
                project_id=doc.project_id,
                is_global=doc.is_global,
            )
            self.session.add(db_chunk)

        await self.session.flush()
        return db_doc

    async def search_chunks(
        self,
        query_embedding: List[float],
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        top_k: int = 3,
        similarity_threshold: float = 0.5,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        Search vector store for chunks matching query_embedding, enforcing tenant isolation.
        Returns list of (KnowledgeChunk, similarity_score) sorted descending by similarity.
        """
        if not query_embedding:
            return []

        # Build tenant isolation filter
        # Rule: A user can access:
        # 1. Any global chunk (is_global == True)
        # 2. Their own private chunks (user_id == current_user.id)
        # Anonymous users can ONLY access global chunks.
        if user_id is not None:
            tenant_condition = or_(
                KnowledgeChunk.is_global.is_(True),
                KnowledgeChunk.user_id == user_id,
            )
        else:
            tenant_condition = KnowledgeChunk.is_global.is_(True)

        stmt = (
            select(KnowledgeChunk)
            .options(selectinload(KnowledgeChunk.document))
            .where(tenant_condition)
            .where(KnowledgeChunk.embedding.isnot(None))
        )

        if project_id is not None:
            # If a project is specified, include global, project-specific, or user chunks
            stmt = stmt.where(
                or_(
                    KnowledgeChunk.is_global.is_(True),
                    KnowledgeChunk.project_id == project_id,
                    KnowledgeChunk.user_id == user_id,
                )
            )

        result = await self.session.execute(stmt)
        all_candidate_chunks = result.scalars().all()

        if not all_candidate_chunks:
            return []

        # Score and rank candidates by cosine similarity
        scored_chunks: List[Tuple[KnowledgeChunk, float]] = []
        for chunk in all_candidate_chunks:
            chunk_vec = chunk.embedding
            if not chunk_vec or not isinstance(chunk_vec, list):
                continue
            sim = compute_cosine_similarity(query_embedding, chunk_vec)
            if sim >= similarity_threshold:
                scored_chunks.append((chunk, round(sim, 6)))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]

    async def delete_document(
        self,
        document_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        is_admin: bool = False,
    ) -> bool:
        """Delete a document and its cascading chunks if tenant permission is granted."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        res = await self.session.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return False

        # Tenant isolation check
        if not is_admin:
            if doc.is_global:
                return False  # Non-admin cannot delete global documents
            if user_id is None or doc.user_id != user_id:
                return False  # Cannot delete another user's document

        await self.session.delete(doc)
        await self.session.flush()
        return True

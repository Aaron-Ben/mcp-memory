from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.models.base import get_china_time
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L1MemoryCreate, L1MemoryExtracted

__all__ = ["EmbeddingProvider", "L1MemoryService", "l1_memory_service"]


EXTRACTOR_VERSION = "l1_v1"


class EmbeddingProvider(Protocol):
    """Protocol for optional embedding providers aligned with yuanxi-memory."""

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for text."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for texts."""

    def get_dimensions(self) -> int:
        """Return vector dimensions."""


class L1MemoryService:
    """Service for persisting L1 atomic memories."""

    async def save_extracted(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_conversation_id: str,
        source_session_key: str,
        memory: L1MemoryExtracted,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> str:
        memory_id = self.resolve_memory_id(user_id=user_id, memory=memory)
        embedding = await self._embed(memory.content, embedding_provider)
        now = get_china_time()
        item = L1MemoryCreate(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory.memory_type,
            content=memory.content,
            priority=memory.priority,
            scene_name=memory.scene_name,
            source_conversation_id=source_conversation_id,
            source_session_key=source_session_key,
            embedding=embedding,
            metadata=self._build_metadata(memory),
            created_at=now,
            updated_at=now,
        )
        await memory_item_repository.upsert_l1(db, obj_in=item)
        return memory_id

    def resolve_memory_id(self, *, user_id: str, memory: L1MemoryExtracted) -> str:
        source_ids = sorted(set(memory.source_memory_ids))
        normalized_content = " ".join(memory.content.split())
        raw = "\x1f".join(
            [
                user_id,
                ",".join(source_ids),
                EXTRACTOR_VERSION,
                memory.memory_type,
                normalized_content,
            ]
        )
        return f"l1_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    async def _embed(self, text: str, embedding_provider: EmbeddingProvider | None) -> list[float] | None:
        if embedding_provider is None:
            return None
        try:
            return await embedding_provider.embed(text)
        except Exception:
            return None

    def _build_metadata(self, memory: L1MemoryExtracted) -> dict[str, object]:
        metadata: dict[str, object] = dict(memory.metadata)
        metadata["source_memory_ids"] = memory.source_memory_ids
        metadata["source_message_ids"] = memory.source_message_ids
        metadata["extractor_version"] = EXTRACTOR_VERSION
        metadata["extracted_at"] = get_china_time().isoformat()
        if memory.confidence is not None:
            metadata["confidence"] = memory.confidence
        return metadata


l1_memory_service = L1MemoryService()

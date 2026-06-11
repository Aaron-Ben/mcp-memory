from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.adapters import (
    create_embedding_provider_from_settings,
    create_llm_runner_from_settings,
)
from mcp_memory.config import settings
from mcp_memory.extractors import L1Extractor, PromptL1Extractor
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L0MemoryRow, L0ToL1Result
from mcp_memory.services import EmbeddingProvider, l1_memory_service

__all__ = ["L0ToL1Pipeline", "create_l0_to_l1_pipeline_from_settings"]


class L0ToL1Pipeline:
    """Pipeline for extracting L1 atomic memories from stored L0 messages."""

    def __init__(
        self,
        *,
        extractor: L1Extractor,
        embedding_provider: EmbeddingProvider | None = None,
        max_new_messages: int = 10,
        max_background_messages: int = 5,
        max_memories_per_run: int = 10,
    ) -> None:
        self.extractor = extractor
        self.embedding_provider = embedding_provider
        self.max_new_messages = max_new_messages
        self.max_background_messages = max_background_messages
        self.max_memories_per_run = max_memories_per_run

    async def run(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        after_timestamp_ms: int | None = None,
        previous_scene_name: str | None = None,
        query_limit: int = 500,
    ) -> L0ToL1Result:
        rows = await memory_item_repository.query_l0_for_l1(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            after_timestamp_ms=after_timestamp_ms,
            limit=query_limit,
        )
        if not rows:
            return L0ToL1Result(input_count=0, extracted_count=0, stored_count=0)

        background_messages, new_messages = self._split_rows(rows)
        extracted = await self.extractor.extract(
            new_messages=new_messages,
            background_messages=background_messages,
            previous_scene_name=previous_scene_name,
        )
        if self.max_memories_per_run > 0:
            extracted = extracted[: self.max_memories_per_run]

        stored_ids: list[str] = []
        for memory in extracted:
            source_rows = self._resolve_source_rows(memory.source_memory_ids, new_messages)
            source_conversation_id = self._resolve_source_conversation_id(source_rows, new_messages)
            memory_id = await l1_memory_service.save_extracted(
                db,
                user_id=user_id,
                source_conversation_id=source_conversation_id,
                source_session_key=source_session_key,
                memory=memory,
                embedding_provider=self.embedding_provider,
            )
            stored_ids.append(memory_id)

        return L0ToL1Result(
            input_count=len(rows),
            extracted_count=len(extracted),
            stored_count=len(stored_ids),
            memory_ids=stored_ids,
        )

    def _split_rows(self, rows: list[L0MemoryRow]) -> tuple[list[L0MemoryRow], list[L0MemoryRow]]:
        new_messages = rows[-self.max_new_messages :] if self.max_new_messages > 0 else rows
        background_end = len(rows) - len(new_messages)
        background_start = max(0, background_end - self.max_background_messages)
        background_messages = rows[background_start:background_end]
        return background_messages, new_messages

    def _resolve_source_rows(
        self,
        source_memory_ids: list[str],
        fallback_rows: list[L0MemoryRow],
    ) -> list[L0MemoryRow]:
        if not source_memory_ids:
            return fallback_rows
        row_by_id = {row.memory_id: row for row in fallback_rows}
        resolved = [row_by_id[memory_id] for memory_id in source_memory_ids if memory_id in row_by_id]
        return resolved or fallback_rows

    def _resolve_source_conversation_id(
        self,
        source_rows: list[L0MemoryRow],
        fallback_rows: list[L0MemoryRow],
    ) -> str:
        rows = source_rows or fallback_rows
        if not rows:
            return ""
        return rows[0].source_conversation_id


def create_l0_to_l1_pipeline_from_settings() -> L0ToL1Pipeline | None:
    if not settings.MEMORY_EXTRACTION_ENABLED:
        return None
    llm_runner = create_llm_runner_from_settings()
    if llm_runner is None:
        return None
    return L0ToL1Pipeline(
        extractor=PromptL1Extractor(llm_runner),
        embedding_provider=create_embedding_provider_from_settings(),
        max_memories_per_run=settings.MEMORY_MAX_MEMORIES_PER_SESSION,
    )

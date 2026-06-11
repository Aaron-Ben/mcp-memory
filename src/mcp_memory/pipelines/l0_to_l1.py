from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.adapters import (
    create_embedding_provider_from_settings,
    create_llm_runner_from_settings,
)
from mcp_memory.config import settings
from mcp_memory.extractors import L1Extractor, PromptL1Extractor
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L0MemoryRow, L0ToL1Result, L1MemoryExtracted
from mcp_memory.services.l1_memory import EmbeddingProvider, l1_memory_service

__all__ = ["L0ToL1Pipeline", "create_l0_to_l1_pipeline_from_settings"]

logger = logging.getLogger(__name__)


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
        query_limit = max(query_limit, self.max_new_messages * 2)
        logger.info(
            "[L0->L1] 开始查询 L0: user_id=%s session=%s after_cursor=%s limit=%s",
            user_id,
            source_session_key,
            after_timestamp_ms,
            query_limit,
        )
        rows = await memory_item_repository.query_l0_for_l1(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            after_timestamp_ms=after_timestamp_ms,
            limit=query_limit,
        )
        if not rows:
            logger.info("[L0->L1] 没有待处理 L0: user_id=%s session=%s", user_id, source_session_key)
            return L0ToL1Result(input_count=0, processed_count=0, extracted_count=0, stored_count=0)

        processed_rows = self._slice_process_rows(rows)
        has_unprocessed = len(rows) > len(processed_rows)
        has_full_backlog = len(rows) >= query_limit and has_unprocessed
        has_more = has_unprocessed
        latest_cursor = max((row.timestamp_ms for row in processed_rows), default=None)
        logger.info(
            "[L0->L1] 准备抽取 L1: user_id=%s session=%s queried=%s processed=%s latest_cursor=%s has_more=%s",
            user_id,
            source_session_key,
            len(rows),
            len(processed_rows),
            latest_cursor,
            has_more,
        )

        background_messages, new_messages = self._split_rows(processed_rows)
        extracted = await self.extractor.extract(
            new_messages=new_messages,
            background_messages=background_messages,
            previous_scene_name=previous_scene_name,
        )
        if self.max_memories_per_run > 0:
            extracted = extracted[: self.max_memories_per_run]
        logger.info(
            "[L0->L1] LLM 抽取完成: user_id=%s session=%s extracted=%s",
            user_id,
            source_session_key,
            len(extracted),
        )

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
        logger.info(
            "[L0->L1] L1 写入完成: user_id=%s session=%s stored=%s memory_ids=%s",
            user_id,
            source_session_key,
            len(stored_ids),
            stored_ids,
        )

        return L0ToL1Result(
            input_count=len(rows),
            processed_count=len(processed_rows),
            extracted_count=len(extracted),
            stored_count=len(stored_ids),
            latest_cursor=latest_cursor,
            last_scene_name=self._last_scene_name(extracted),
            has_more=has_more,
            has_full_backlog=has_full_backlog,
            memory_ids=stored_ids,
        )

    def _slice_process_rows(self, rows: list[L0MemoryRow]) -> list[L0MemoryRow]:
        if self.max_new_messages <= 0 or len(rows) <= self.max_new_messages:
            return rows
        slice_end = self.max_new_messages
        boundary_ms = rows[slice_end - 1].timestamp_ms
        while slice_end < len(rows) and rows[slice_end].timestamp_ms == boundary_ms:
            slice_end += 1
        return rows[:slice_end]

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

    def _last_scene_name(self, memories: list[L1MemoryExtracted]) -> str | None:
        for memory in reversed(memories):
            if memory.scene_name:
                return memory.scene_name
        return None


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

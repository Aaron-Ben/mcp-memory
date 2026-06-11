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
from mcp_memory.schemas import L0MemoryRow, L0ToL1Result, L1MemoryDedupDecision, L1MemoryExtracted
from mcp_memory.services.l1_dedup import L1DedupService
from mcp_memory.services.l1_memory import EmbeddingProvider, l1_memory_service
from mcp_memory.utils.filters import should_extract_l1

__all__ = ["L0ToL1Pipeline", "create_l0_to_l1_pipeline_from_settings"]

logger = logging.getLogger(__name__)


class L0ToL1Pipeline:
    """Pipeline for extracting L1 atomic memories from stored L0 messages."""

    def __init__(
        self,
        *,
        extractor: L1Extractor,
        embedding_provider: EmbeddingProvider | None = None,
        dedup_service: L1DedupService | None = None,
        enable_extract_filter: bool = True,
        max_new_messages: int = 10,
        max_background_messages: int = 5,
        max_memories_per_run: int = 10,
    ) -> None:
        self.extractor = extractor
        self.embedding_provider = embedding_provider
        self.dedup_service = dedup_service
        self.enable_extract_filter = enable_extract_filter
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

        qualified_rows = self._filter_qualified_rows(processed_rows)
        logger.info(
            "[L0->L1] 准备抽取 L1: user_id=%s session=%s queried=%s processed=%s qualified=%s "
            "latest_cursor=%s has_more=%s",
            user_id,
            source_session_key,
            len(rows),
            len(processed_rows),
            len(qualified_rows),
            latest_cursor,
            has_more,
        )

        if not qualified_rows:
            logger.info("[L0->L1] 所有消息未通过质量过滤: user_id=%s session=%s", user_id, source_session_key)
            return L0ToL1Result(
                input_count=len(rows),
                processed_count=len(processed_rows),
                extracted_count=0,
                stored_count=0,
                latest_cursor=latest_cursor,
                has_more=has_more,
                has_full_backlog=has_full_backlog,
            )

        background_messages, new_messages = self._split_rows(qualified_rows)
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

        record_ids = [l1_memory_service.resolve_memory_id(user_id=user_id, memory=memory) for memory in extracted]
        decisions = await self._dedup(db, user_id=user_id, memories=extracted, record_ids=record_ids)

        stored_ids: list[str] = []
        skipped_count = 0
        for memory, record_id, decision in zip(extracted, record_ids, decisions, strict=True):
            if decision.action == "skip":
                skipped_count += 1
                continue

            memory_to_save = self._apply_dedup_decision(memory, decision)
            if decision.action in {"update", "merge"}:
                await memory_item_repository.archive_l1_batch(
                    db,
                    user_id=user_id,
                    memory_ids=decision.target_ids,
                )

            source_rows = self._resolve_source_rows(memory.source_memory_ids, new_messages)
            source_conversation_id = self._resolve_source_conversation_id(source_rows, new_messages)
            memory_id = await l1_memory_service.save_extracted(
                db,
                user_id=user_id,
                source_conversation_id=source_conversation_id,
                source_session_key=source_session_key,
                memory=memory_to_save,
                memory_id=record_id,
                embedding_provider=self.embedding_provider,
            )
            stored_ids.append(memory_id)
        logger.info(
            "[L0->L1] L1 写入完成: user_id=%s session=%s stored=%s skipped=%s memory_ids=%s",
            user_id,
            source_session_key,
            len(stored_ids),
            skipped_count,
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

    async def _dedup(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        memories: list[L1MemoryExtracted],
        record_ids: list[str],
    ) -> list[L1MemoryDedupDecision]:
        if self.dedup_service is None:
            return [L1MemoryDedupDecision(record_id=record_id, action="store") for record_id in record_ids]
        return await self.dedup_service.dedup(
            db,
            user_id=user_id,
            memories=memories,
            record_ids=record_ids,
        )

    def _apply_dedup_decision(
        self,
        memory: L1MemoryExtracted,
        decision: L1MemoryDedupDecision,
    ) -> L1MemoryExtracted:
        if decision.action not in {"update", "merge"}:
            return memory

        metadata = dict(memory.metadata)
        metadata["dedup_action"] = decision.action
        metadata["dedup_target_ids"] = decision.target_ids
        return memory.model_copy(
            update={
                "content": decision.merged_content or memory.content,
                "memory_type": decision.merged_type or memory.memory_type,
                "priority": decision.merged_priority if decision.merged_priority is not None else memory.priority,
                "metadata": metadata,
            }
        )

    def _filter_qualified_rows(self, rows: list[L0MemoryRow]) -> list[L0MemoryRow]:
        """Filter out L0 messages that don't pass quality checks.

        When extract filtering is disabled, all rows pass through unchanged.
        """
        if not self.enable_extract_filter:
            return rows
        return [row for row in rows if should_extract_l1(row.content)]

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
    embedding_provider = create_embedding_provider_from_settings()
    dedup_service = (
        L1DedupService(llm_runner=llm_runner, embedding_provider=embedding_provider)
        if settings.MEMORY_ENABLE_DEDUP
        else None
    )
    return L0ToL1Pipeline(
        extractor=PromptL1Extractor(llm_runner),
        embedding_provider=embedding_provider,
        dedup_service=dedup_service,
        enable_extract_filter=settings.MEMORY_ENABLE_EXTRACT_FILTER,
        max_memories_per_run=settings.MEMORY_MAX_MEMORIES_PER_SESSION,
    )

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

from mcp_memory.config import settings
from mcp_memory.db import async_db_session
from mcp_memory.models.base import get_china_time
from mcp_memory.pipelines import create_l0_to_l1_pipeline_from_settings, create_l1_to_l2_pipeline_from_settings
from mcp_memory.repositories import pipeline_state_repository

__all__ = ["PipelineScheduler", "pipeline_scheduler"]

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Minimal in-process scheduler for L0 to L1 extraction."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._idle_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}
        self._l2_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}

    async def notify_conversation(
        self,
        *,
        user_id: str,
        source_session_key: str,
        rounds: int = 1,
    ) -> None:
        if not settings.MEMORY_CAPTURE_ENABLED or not settings.MEMORY_EXTRACTION_ENABLED:
            logger.info(
                "[L0->L1] 跳过调度: capture_enabled=%s extraction_enabled=%s user=%s session=%s",
                settings.MEMORY_CAPTURE_ENABLED,
                settings.MEMORY_EXTRACTION_ENABLED,
                user_id,
                source_session_key,
            )
            return

        async with async_db_session() as db:
            notify_result = await pipeline_state_repository.notify_conversation(
                db,
                user_id=user_id,
                source_session_key=source_session_key,
                rounds=rounds,
                every_n_conversations=settings.PIPELINE_EVERY_N_CONVERSATIONS,
                enable_warmup=settings.PIPELINE_ENABLE_WARMUP,
            )
        logger.info(
            "[L0->L1] 收到 L0 通知: user=%s session=%s rounds=%s count=%s threshold=%s should_run=%s",
            user_id,
            source_session_key,
            rounds,
            notify_result.conversation_count,
            notify_result.threshold,
            notify_result.should_run_l1,
        )

        if notify_result.should_run_l1:
            self._cancel_idle(user_id=user_id, source_session_key=source_session_key)
            logger.info("[L0->L1] 阈值触发 L1: user=%s session=%s", user_id, source_session_key)
            self._spawn(self.run_l1(user_id=user_id, source_session_key=source_session_key))
        else:
            self._schedule_idle(user_id=user_id, source_session_key=source_session_key)

    async def run_l1(self, *, user_id: str, source_session_key: str) -> None:
        pipeline = create_l0_to_l1_pipeline_from_settings()
        if pipeline is None:
            await self._mark_failed(user_id=user_id, source_session_key=source_session_key)
            logger.warning("[L0->L1] L1 pipeline 未配置，跳过: user=%s session=%s", user_id, source_session_key)
            return

        try:
            async with async_db_session() as db:
                state = await pipeline_state_repository.get_for_update(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                )
                if state is None:
                    logger.info("[L0->L1] 未找到 pipeline_state，跳过: user=%s session=%s", user_id, source_session_key)
                    return
                after_cursor = state.last_l1_cursor or None
                previous_scene_name = state.last_scene_name or None
            logger.info(
                "[L0->L1] 后台任务开始: user=%s session=%s after_cursor=%s previous_scene=%s",
                user_id,
                source_session_key,
                after_cursor,
                previous_scene_name,
            )

            async with async_db_session() as db:
                result = await pipeline.run(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                    after_timestamp_ms=after_cursor,
                    previous_scene_name=previous_scene_name,
                    query_limit=max(pipeline.max_new_messages * 2, 1),
                )

            async with async_db_session() as db:
                should_continue = await pipeline_state_repository.mark_l1_complete(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                    processed_count=result.processed_count,
                    latest_cursor=result.latest_cursor,
                    last_scene_name=result.last_scene_name,
                    has_more=result.has_more,
                )
            logger.info(
                "[L0->L1] 后台任务完成: user=%s session=%s input=%s processed=%s extracted=%s stored=%s latest_cursor=%s has_more=%s",
                user_id,
                source_session_key,
                result.input_count,
                result.processed_count,
                result.extracted_count,
                result.stored_count,
                result.latest_cursor,
                result.has_more,
            )

            if result.stored_count > 0:
                await self.advance_l2_after_l1(user_id=user_id, source_session_key=source_session_key)

            if should_continue:
                logger.info("[L0->L1] 检测到 backlog，继续下一轮: user=%s session=%s", user_id, source_session_key)
                self._spawn(self.run_l1(user_id=user_id, source_session_key=source_session_key))
        except Exception:
            logger.exception("[L0->L1] 后台任务失败: user=%s session=%s", user_id, source_session_key)
            await self._mark_failed(user_id=user_id, source_session_key=source_session_key)

    async def shutdown(self) -> None:
        if not self._tasks:
            active_tasks: list[asyncio.Task[Any]] = []
        else:
            active_tasks = list(self._tasks)
        for task in self._idle_tasks.values():
            task.cancel()
        self._idle_tasks.clear()
        for task in self._l2_tasks.values():
            task.cancel()
        self._l2_tasks.clear()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _schedule_idle(self, *, user_id: str, source_session_key: str) -> None:
        self._cancel_idle(user_id=user_id, source_session_key=source_session_key)
        key = (user_id, source_session_key)
        task = asyncio.create_task(self._idle_then_run(user_id=user_id, source_session_key=source_session_key))
        self._idle_tasks[key] = task
        task.add_done_callback(lambda _task: self._idle_tasks.pop(key, None))
        logger.info(
            "[L0->L1] 设置 idle 触发器: user=%s session=%s timeout_seconds=%s",
            user_id,
            source_session_key,
            settings.PIPELINE_L1_IDLE_TIMEOUT_SECONDS,
        )

    def _cancel_idle(self, *, user_id: str, source_session_key: str) -> None:
        task = self._idle_tasks.pop((user_id, source_session_key), None)
        if task is not None:
            task.cancel()

    async def _idle_then_run(self, *, user_id: str, source_session_key: str) -> None:
        try:
            await asyncio.sleep(max(settings.PIPELINE_L1_IDLE_TIMEOUT_SECONDS, 1))
            async with async_db_session() as db:
                acquired = await pipeline_state_repository.acquire_l1_for_idle(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                )
            if acquired:
                logger.info("[L0->L1] idle 触发 L1: user=%s session=%s", user_id, source_session_key)
                self._spawn(self.run_l1(user_id=user_id, source_session_key=source_session_key))
            else:
                logger.info("[L0->L1] idle 到期但无需触发: user=%s session=%s", user_id, source_session_key)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[L0->L1] idle 触发失败: user=%s session=%s", user_id, source_session_key)

    async def _mark_failed(self, *, user_id: str, source_session_key: str) -> None:
        async with async_db_session() as db:
            await pipeline_state_repository.mark_l1_failed(
                db,
                user_id=user_id,
                source_session_key=source_session_key,
            )

    async def advance_l2_after_l1(self, *, user_id: str, source_session_key: str) -> None:
        async with async_db_session() as db:
            result = await pipeline_state_repository.schedule_l2_after_l1(
                db,
                user_id=user_id,
                source_session_key=source_session_key,
                delay_seconds=settings.PIPELINE_L2_DELAY_AFTER_L1_SECONDS,
                min_interval_seconds=settings.PIPELINE_L2_MIN_INTERVAL_SECONDS,
            )
        if result.next_run_at is None:
            return
        logger.info(
            "[L1->L2] L1 完成后设置 L2 timer: user=%s session=%s pending=%s next_run_at=%s scheduled=%s",
            user_id,
            source_session_key,
            result.pending_count,
            result.next_run_at,
            result.scheduled,
        )
        self._schedule_l2_at(user_id=user_id, source_session_key=source_session_key, run_at=result.next_run_at)

    def _schedule_l2_at(self, *, user_id: str, source_session_key: str, run_at: datetime) -> None:
        key = (user_id, source_session_key)
        existing = self._l2_tasks.pop(key, None)
        if existing is not None:
            existing.cancel()
        delay_seconds = max((run_at - get_china_time()).total_seconds(), 0.0)
        task = asyncio.create_task(
            self._l2_timer_then_run(user_id=user_id, source_session_key=source_session_key, delay_seconds=delay_seconds)
        )
        self._l2_tasks[key] = task
        task.add_done_callback(lambda _task: self._l2_tasks.pop(key, None))

    async def _l2_timer_then_run(self, *, user_id: str, source_session_key: str, delay_seconds: float) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            self._spawn(self.run_l2(user_id=user_id, source_session_key=source_session_key))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[L1->L2] L2 timer 触发失败: user=%s session=%s", user_id, source_session_key)

    async def run_l2(self, *, user_id: str, source_session_key: str) -> None:
        pipeline = create_l1_to_l2_pipeline_from_settings()
        if pipeline is None:
            await self._mark_l2_failed(user_id=user_id, source_session_key=source_session_key)
            logger.warning("[L1->L2] L2 pipeline 未配置，跳过: user=%s session=%s", user_id, source_session_key)
            return

        try:
            async with async_db_session() as db:
                after_cursor, acquired = await pipeline_state_repository.acquire_l2_for_timer(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                )
            if not acquired:
                logger.info("[L1->L2] L2 timer 到期但无需触发: user=%s session=%s", user_id, source_session_key)
                return

            logger.info(
                "[L1->L2] 后台任务开始: user=%s session=%s after_cursor=%s",
                user_id,
                source_session_key,
                after_cursor,
            )
            async with async_db_session() as db:
                result = await pipeline.run(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                    after_updated_at=after_cursor,
                )
            async with async_db_session() as db:
                await pipeline_state_repository.mark_l2_complete(
                    db,
                    user_id=user_id,
                    source_session_key=source_session_key,
                    latest_cursor=result.latest_cursor,
                )
            logger.info(
                "[L1->L2] 后台任务完成: user=%s session=%s input=%s stored=%s skipped=%s latest_cursor=%s",
                user_id,
                source_session_key,
                result.input_count,
                result.stored_count,
                result.skipped,
                result.latest_cursor,
            )
        except Exception:
            logger.exception("[L1->L2] 后台任务失败: user=%s session=%s", user_id, source_session_key)
            await self._mark_l2_failed(user_id=user_id, source_session_key=source_session_key)

    async def _mark_l2_failed(self, *, user_id: str, source_session_key: str) -> None:
        async with async_db_session() as db:
            await pipeline_state_repository.mark_l2_failed(
                db,
                user_id=user_id,
                source_session_key=source_session_key,
            )


pipeline_scheduler = PipelineScheduler()

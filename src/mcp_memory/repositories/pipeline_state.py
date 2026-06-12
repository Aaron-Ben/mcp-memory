from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.models.base import get_china_time
from mcp_memory.models.pipeline_state import PipelineState

__all__ = ["L2ScheduleResult", "NotifyResult", "PipelineStateRepository", "pipeline_state_repository"]


@dataclass(frozen=True)
class NotifyResult:
    should_run_l1: bool
    conversation_count: int
    threshold: int


@dataclass(frozen=True)
class L2ScheduleResult:
    scheduled: bool
    next_run_at: datetime | None
    pending_count: int


class PipelineStateRepository:
    """Database access for pipeline_state."""

    async def notify_conversation(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        rounds: int,
        every_n_conversations: int,
        enable_warmup: bool,
    ) -> NotifyResult:
        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=enable_warmup,
        )
        state.conversation_count += max(rounds, 0)
        state.updated_at = get_china_time()

        threshold = self.effective_threshold(
            warmup_threshold=state.warmup_threshold,
            every_n_conversations=every_n_conversations,
            enable_warmup=enable_warmup,
        )
        should_run = state.conversation_count >= threshold and not state.l1_running
        if should_run:
            state.l1_running = True
            self.advance_warmup_threshold(
                state,
                every_n_conversations=every_n_conversations,
                enable_warmup=enable_warmup,
            )
        await db.flush()
        return NotifyResult(
            should_run_l1=should_run,
            conversation_count=state.conversation_count,
            threshold=threshold,
        )

    async def get_or_create_for_update(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        enable_warmup: bool,
    ) -> PipelineState:
        state = await self.get_for_update(db, user_id=user_id, source_session_key=source_session_key)
        if state is not None:
            return state

        now = get_china_time()
        state = PipelineState(
            user_id=user_id,
            source_session_key=source_session_key,
            conversation_count=0,
            warmup_threshold=1 if enable_warmup else 0,
            last_l1_cursor=0,
            last_scene_name="",
            l1_running=False,
            l2_pending_l1_count=0,
            last_l2_cursor=None,
            l2_last_extraction_time=None,
            l2_running=False,
            l2_next_run_at=None,
            created_at=now,
            updated_at=now,
            is_deleted=False,
        )
        db.add(state)
        await db.flush()
        return state

    async def get_for_update(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
    ) -> PipelineState | None:
        result = await db.execute(
            select(PipelineState)
            .where(
                PipelineState.user_id == user_id,
                PipelineState.source_session_key == source_session_key,
                PipelineState.is_deleted.is_(False),
            )
            .with_for_update()
        )
        return result.scalars().first()

    async def mark_l1_complete(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        processed_count: int,
        latest_cursor: int | None,
        last_scene_name: str | None,
        has_more: bool,
    ) -> bool:
        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=True,
        )
        state.conversation_count = 0
        if latest_cursor is not None and latest_cursor > state.last_l1_cursor:
            state.last_l1_cursor = latest_cursor
        if last_scene_name:
            state.last_scene_name = last_scene_name
        state.l1_running = has_more
        state.updated_at = get_china_time()
        await db.flush()
        return has_more

    async def schedule_l2_after_l1(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        delay_seconds: int,
        min_interval_seconds: int,
    ) -> L2ScheduleResult:
        """Mark L2 pending after L1 and set the earliest allowed L2 timer."""

        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=True,
        )
        now = get_china_time()
        state.l2_pending_l1_count += 1

        desired = now + timedelta(seconds=max(delay_seconds, 1))
        if state.l2_last_extraction_time is not None:
            desired = max(desired, state.l2_last_extraction_time + timedelta(seconds=max(min_interval_seconds, 1)))

        scheduled = state.l2_next_run_at is None or desired < state.l2_next_run_at
        if scheduled:
            state.l2_next_run_at = desired
        state.updated_at = now
        await db.flush()
        return L2ScheduleResult(
            scheduled=scheduled,
            next_run_at=state.l2_next_run_at,
            pending_count=state.l2_pending_l1_count,
        )

    async def acquire_l2_for_timer(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
    ) -> tuple[datetime | None, bool]:
        """Acquire L2 execution for a due timer and return the current L2 cursor."""

        state = await self.get_for_update(db, user_id=user_id, source_session_key=source_session_key)
        now = get_china_time()
        if state is None or state.l2_running or state.l2_pending_l1_count <= 0:
            return None, False
        if state.l2_next_run_at is not None and state.l2_next_run_at > now:
            return state.last_l2_cursor, False
        state.l2_running = True
        state.updated_at = now
        await db.flush()
        return state.last_l2_cursor, True

    async def mark_l2_complete(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        latest_cursor: datetime | None,
    ) -> None:
        """Mark one L2 run complete and advance its L1 updated_at cursor."""

        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=True,
        )
        now = get_china_time()
        state.l2_pending_l1_count = 0
        state.l2_running = False
        state.l2_next_run_at = None
        if latest_cursor is not None and (state.last_l2_cursor is None or latest_cursor > state.last_l2_cursor):
            state.last_l2_cursor = latest_cursor
        state.l2_last_extraction_time = now
        state.updated_at = now
        await db.flush()

    async def mark_l2_failed(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
    ) -> None:
        """Release the L2 running flag after a failed run."""

        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=True,
        )
        state.l2_running = False
        state.updated_at = get_china_time()
        await db.flush()

    async def acquire_l1_for_idle(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
    ) -> bool:
        state = await self.get_for_update(db, user_id=user_id, source_session_key=source_session_key)
        if state is None or state.l1_running or state.conversation_count <= 0:
            return False
        state.l1_running = True
        state.updated_at = get_china_time()
        await db.flush()
        return True

    async def mark_l1_failed(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
    ) -> None:
        state = await self.get_or_create_for_update(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            enable_warmup=True,
        )
        state.l1_running = False
        state.updated_at = get_china_time()
        await db.flush()

    def effective_threshold(self, *, warmup_threshold: int, every_n_conversations: int, enable_warmup: bool) -> int:
        if not enable_warmup:
            return max(every_n_conversations, 1)
        if warmup_threshold <= 0:
            return max(every_n_conversations, 1)
        return min(warmup_threshold, max(every_n_conversations, 1))

    def advance_warmup_threshold(
        self,
        state: PipelineState,
        *,
        every_n_conversations: int,
        enable_warmup: bool,
    ) -> None:
        if not enable_warmup or state.warmup_threshold <= 0:
            return
        next_threshold = state.warmup_threshold * 2
        if next_threshold >= max(every_n_conversations, 1):
            state.warmup_threshold = 0
        else:
            state.warmup_threshold = next_threshold


pipeline_state_repository = PipelineStateRepository()

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.adapters import create_llm_runner_from_settings
from mcp_memory.config import settings
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L1ToL2Result
from mcp_memory.services.l2_scene import L2SceneService

__all__ = ["L1ToL2Pipeline", "create_l1_to_l2_pipeline_from_settings"]

logger = logging.getLogger(__name__)


class L1ToL2Pipeline:
    """DB-native pipeline for consolidating L1 memories into L2 scene blocks."""

    def __init__(
        self,
        *,
        scene_service: L2SceneService,
        max_scenes: int = 15,
        query_limit: int = 100,
    ) -> None:
        self.scene_service = scene_service
        self.max_scenes = max_scenes
        self.query_limit = query_limit

    async def run(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        after_updated_at,
    ) -> L1ToL2Result:
        logger.info(
            "[L1->L2] 开始查询 L1: user_id=%s session=%s after_cursor=%s limit=%s",
            user_id,
            source_session_key,
            after_updated_at,
            self.query_limit,
        )
        memories = await memory_item_repository.query_l1_for_l2(
            db,
            user_id=user_id,
            source_session_key=source_session_key,
            updated_after=after_updated_at,
            limit=self.query_limit,
        )
        if not memories:
            logger.info("[L1->L2] 没有待处理 L1: user_id=%s session=%s", user_id, source_session_key)
            return L1ToL2Result(input_count=0, stored_count=0, skipped=True)

        existing_scenes = await memory_item_repository.query_l2_scenes(
            db,
            user_id=user_id,
            limit=self.max_scenes,
        )
        logger.info(
            "[L1->L2] 准备生成 L2: user_id=%s session=%s l1_count=%s existing_scenes=%s",
            user_id,
            source_session_key,
            len(memories),
            len(existing_scenes),
        )
        scene = await self.scene_service.generate_scene(
            user_id=user_id,
            source_session_key=source_session_key,
            memories=memories,
            existing_scenes=existing_scenes,
        )
        latest_cursor = max((memory.updated_at for memory in memories), default=None)
        if scene is None:
            logger.warning("[L1->L2] L2 生成为空，跳过写入: user_id=%s session=%s", user_id, source_session_key)
            return L1ToL2Result(
                input_count=len(memories),
                stored_count=0,
                skipped=True,
                latest_cursor=latest_cursor,
            )

        await memory_item_repository.upsert_l2_scene(db, obj_in=scene)
        logger.info(
            "[L1->L2] L2 写入完成: user_id=%s session=%s scene_id=%s scene_name=%s",
            user_id,
            source_session_key,
            scene.memory_id,
            scene.scene_name,
        )
        return L1ToL2Result(
            input_count=len(memories),
            stored_count=1,
            latest_cursor=latest_cursor,
            scene_id=scene.memory_id,
            scene_name=scene.scene_name,
        )


def create_l1_to_l2_pipeline_from_settings() -> L1ToL2Pipeline | None:
    if not settings.MEMORY_EXTRACTION_ENABLED:
        return None
    llm_runner = create_llm_runner_from_settings()
    if llm_runner is None:
        return None
    return L1ToL2Pipeline(
        scene_service=L2SceneService(llm_runner=llm_runner, max_scenes=settings.MEMORY_MAX_SCENES),
        max_scenes=settings.MEMORY_MAX_SCENES,
    )

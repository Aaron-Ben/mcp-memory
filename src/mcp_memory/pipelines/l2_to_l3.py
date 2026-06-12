from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.adapters import create_llm_runner_from_settings
from mcp_memory.config import settings
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L2ToL3Result
from mcp_memory.services.l3_persona import L3PersonaService

__all__ = ["L2ToL3Pipeline", "create_l2_to_l3_pipeline_from_settings"]

logger = logging.getLogger(__name__)


class L2ToL3Pipeline:
    """DB-native pipeline for consolidating L2 scene blocks into one L3 persona."""

    def __init__(
        self,
        *,
        persona_service: L3PersonaService,
        max_scenes: int = 15,
        trigger_every_n: int = 50,
    ) -> None:
        self.persona_service = persona_service
        self.max_scenes = max_scenes
        self.trigger_every_n = max(trigger_every_n, 1)

    async def run(self, db: AsyncSession, *, user_id: str) -> L2ToL3Result:
        existing_persona = await memory_item_repository.get_l3_persona(db, user_id=user_id)
        all_scenes = await memory_item_repository.query_all_l2_scenes_for_l3(
            db,
            user_id=user_id,
            limit=self.max_scenes,
        )
        if not all_scenes:
            logger.info("[L2->L3] 没有 L2 场景，跳过 L3: user=%s", user_id)
            return L2ToL3Result(input_count=0, changed_count=0, skipped=True)

        if existing_persona is None:
            changed_scenes = all_scenes
            trigger_reason = "cold_start"
        else:
            changed_scenes = await memory_item_repository.query_l2_for_l3(
                db,
                user_id=user_id,
                updated_after=existing_persona.updated_at,
                limit=max(self.max_scenes, self.trigger_every_n),
            )
            trigger_reason = "threshold"

        latest_cursor = max((scene.updated_at for scene in changed_scenes), default=None)
        if not changed_scenes:
            logger.info("[L2->L3] 没有 L3 需要消费的 L2 变化: user=%s", user_id)
            return L2ToL3Result(
                input_count=len(all_scenes),
                changed_count=0,
                skipped=True,
                latest_cursor=latest_cursor,
            )

        if existing_persona is not None and len(changed_scenes) < self.trigger_every_n:
            logger.info(
                "[L2->L3] L2 变化未达到 L3 阈值，跳过: user=%s changed=%s threshold=%s",
                user_id,
                len(changed_scenes),
                self.trigger_every_n,
            )
            return L2ToL3Result(
                input_count=len(all_scenes),
                changed_count=len(changed_scenes),
                skipped=True,
                latest_cursor=latest_cursor,
            )

        logger.info(
            "[L2->L3] 准备生成 L3: user=%s mode=%s all_scenes=%s changed_scenes=%s",
            user_id,
            "incremental" if existing_persona else "first",
            len(all_scenes),
            len(changed_scenes),
        )
        persona = await self.persona_service.generate_persona(
            user_id=user_id,
            changed_scenes=changed_scenes,
            all_scenes=all_scenes,
            existing_persona=existing_persona,
            trigger_reason=trigger_reason,
        )
        if persona is None:
            logger.warning("[L2->L3] L3 生成为空，跳过写入: user=%s", user_id)
            return L2ToL3Result(
                input_count=len(all_scenes),
                changed_count=len(changed_scenes),
                skipped=True,
                latest_cursor=latest_cursor,
            )

        await memory_item_repository.upsert_l3_persona(db, obj_in=persona)
        logger.info("[L2->L3] L3 写入完成: user=%s memory_id=%s", user_id, persona.memory_id)
        return L2ToL3Result(
            input_count=len(all_scenes),
            changed_count=len(changed_scenes),
            stored=True,
            latest_cursor=latest_cursor,
            memory_id=persona.memory_id,
        )


def create_l2_to_l3_pipeline_from_settings() -> L2ToL3Pipeline | None:
    if not settings.MEMORY_EXTRACTION_ENABLED or not settings.MEMORY_PERSONA_ENABLED:
        return None
    llm_runner = create_llm_runner_from_settings()
    if llm_runner is None:
        return None
    return L2ToL3Pipeline(
        persona_service=L3PersonaService(
            llm_runner=llm_runner,
            max_length=settings.MEMORY_PERSONA_MAX_LENGTH,
        ),
        max_scenes=settings.MEMORY_MAX_SCENES,
        trigger_every_n=settings.MEMORY_PERSONA_TRIGGER_EVERY_N,
    )

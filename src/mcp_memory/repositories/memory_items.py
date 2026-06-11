import json

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.models.memory_items import MemoryItem
from mcp_memory.schemas.memory_items import MemoryItemCreate

__all__ = ["MemoryItemRepository", "memory_item_repository"]


class MemoryItemRepository:
    """Database access for memory_items."""

    async def get_by_memory_id(
        self,
        db: AsyncSession,
        *,
        memory_id: str,
        user_id: str | None = None,
    ) -> MemoryItem | None:
        conditions = [
            MemoryItem.memory_id == memory_id,
            MemoryItem.is_deleted.is_(False),
        ]
        if user_id is not None:
            conditions.append(MemoryItem.user_id == user_id)

        result = await db.execute(select(MemoryItem).where(and_(*conditions)))
        return result.scalars().first()

    async def upsert_l0(self, db: AsyncSession, *, obj_in: MemoryItemCreate) -> None:
        """Insert or update one L0 raw conversation message."""

        data = obj_in.model_dump(by_alias=False)
        await db.execute(
            text(
                """
                INSERT INTO memory_items (
                    memory_id, user_id, layer, memory_type, content, embedding,
                    priority, scene_name, source_conversation_id, source_session_key,
                    metadata, status, created_at, updated_at
                ) VALUES (
                    :memory_id, :user_id, 0, :memory_type, :content, NULL,
                    :priority, :scene_name, :source_conversation_id, :source_session_key,
                    CAST(:metadata_json AS jsonb), :status, :created_at, :updated_at
                )
                ON CONFLICT (memory_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    memory_type = EXCLUDED.memory_type,
                    source_conversation_id = EXCLUDED.source_conversation_id,
                    source_session_key = EXCLUDED.source_session_key,
                    metadata = EXCLUDED.metadata,
                    status = 'active',
                    is_deleted = false,
                    deleted_at = NULL,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "memory_id": data["memory_id"],
                "user_id": data["user_id"],
                "memory_type": data["memory_type"],
                "content": data["content"],
                "priority": data["priority"],
                "scene_name": data["scene_name"],
                "source_conversation_id": data["source_conversation_id"],
                "source_session_key": data["source_session_key"],
                "metadata_json": json.dumps(data["meta_data"], ensure_ascii=False, separators=(",", ":")),
                "status": data["status"],
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
            },
        )
        await db.flush()


memory_item_repository = MemoryItemRepository()

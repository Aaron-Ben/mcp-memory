import json
from datetime import datetime

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.models.memory_items import MemoryItem
from mcp_memory.schemas.memory_items import (
    L0MemoryRow,
    L1MemoryCreate,
    L1MemoryForL2,
    L1MemorySearchResult,
    L2SceneCreate,
    L2SceneRow,
    MemoryItemCreate,
)

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

    async def query_l0_for_l1(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        after_timestamp_ms: int | None = None,
        limit: int = 500,
    ) -> list[L0MemoryRow]:
        """Query L0 messages for L1 extraction in natural time order."""

        time_expr = self._l0_time_ms_expr()
        params: dict[str, object] = {
            "user_id": user_id,
            "source_session_key": source_session_key,
            "limit": limit,
        }
        time_filter = ""
        if after_timestamp_ms is not None and after_timestamp_ms > 0:
            time_filter = f"AND {time_expr} > :after_timestamp_ms"
            params["after_timestamp_ms"] = after_timestamp_ms

        result = await db.execute(
            text(
                f"""
                SELECT
                    memory_id,
                    user_id,
                    source_conversation_id,
                    source_session_key,
                    content,
                    metadata,
                    COALESCE(metadata->>'_role', memory_type) AS role,
                    {time_expr} AS timestamp_ms,
                    COALESCE(metadata->>'recorded_at', '') AS recorded_at
                FROM memory_items
                WHERE layer = 0
                  AND status = 'active'
                  AND is_deleted = false
                  AND user_id = :user_id
                  AND (
                    source_conversation_id = :source_session_key
                    OR source_session_key = :source_session_key
                  )
                  {time_filter}
                ORDER BY {time_expr} ASC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.mappings().all()
        return [
            L0MemoryRow(
                memory_id=str(row["memory_id"]),
                user_id=str(row["user_id"]),
                source_conversation_id=str(row["source_conversation_id"] or ""),
                source_session_key=str(row["source_session_key"] or ""),
                role=str(row["role"] or ""),
                content=str(row["content"] or ""),
                timestamp_ms=int(float(row["timestamp_ms"] or 0)),
                recorded_at=str(row["recorded_at"] or ""),
                metadata=dict(row["metadata"] or {}),
            )
            for row in rows
        ]

    async def upsert_l1(self, db: AsyncSession, *, obj_in: L1MemoryCreate) -> None:
        """Insert or update one L1 atomic memory."""

        data = obj_in.model_dump()
        vector_text = self._vector_to_text(data["embedding"])
        await db.execute(
            text(
                """
                INSERT INTO memory_items (
                    memory_id, user_id, layer, memory_type, content, embedding,
                    priority, scene_name, source_conversation_id, source_session_key,
                    metadata, status, created_at, updated_at
                ) VALUES (
                    :memory_id, :user_id, 1, :memory_type, :content,
                    CASE
                        WHEN CAST(:embedding_text AS text) IS NULL THEN NULL
                        ELSE CAST(CAST(:embedding_text AS text) AS vector)
                    END,
                    :priority, :scene_name, :source_conversation_id, :source_session_key,
                    CAST(:metadata_json AS jsonb), 'active', :created_at, :updated_at
                )
                ON CONFLICT (memory_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    memory_type = EXCLUDED.memory_type,
                    embedding = COALESCE(EXCLUDED.embedding, memory_items.embedding),
                    priority = EXCLUDED.priority,
                    scene_name = EXCLUDED.scene_name,
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
                "embedding_text": vector_text,
                "priority": data["priority"],
                "scene_name": data["scene_name"],
                "source_conversation_id": data["source_conversation_id"],
                "source_session_key": data["source_session_key"],
                "metadata_json": json.dumps(data["metadata"], ensure_ascii=False, separators=(",", ":")),
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
            },
        )
        await db.flush()

    async def count_l1(self, db: AsyncSession, *, user_id: str) -> int:
        """Count active L1 memories for one user."""

        result = await db.execute(
            text(
                """
                SELECT COUNT(*)::int AS count
                FROM memory_items
                WHERE layer = 1
                  AND status = 'active'
                  AND is_deleted = false
                  AND user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        return int(result.scalar_one() or 0)

    async def search_l1_vector(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        embedding: list[float],
        limit: int = 10,
    ) -> list[L1MemorySearchResult]:
        """Search active L1 memories by pgvector cosine distance."""

        vector_text = self._vector_to_text(embedding)
        if vector_text is None:
            return []
        result = await db.execute(
            text(
                """
                SELECT
                    memory_id,
                    user_id,
                    memory_type,
                    content,
                    priority,
                    scene_name,
                    source_conversation_id,
                    source_session_key,
                    metadata,
                    1 - (embedding <=> CAST(CAST(:embedding_text AS text) AS vector)) AS score
                FROM memory_items
                WHERE layer = 1
                  AND status = 'active'
                  AND is_deleted = false
                  AND user_id = :user_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(CAST(:embedding_text AS text) AS vector)
                LIMIT :limit
                """
            ),
            {
                "user_id": user_id,
                "embedding_text": vector_text,
                "limit": limit,
            },
        )
        return [
            L1MemorySearchResult(
                memory_id=str(row["memory_id"]),
                user_id=str(row["user_id"]),
                memory_type=str(row["memory_type"]),
                content=str(row["content"]),
                priority=int(row["priority"] or 50),
                scene_name=str(row["scene_name"] or ""),
                source_conversation_id=str(row["source_conversation_id"] or ""),
                source_session_key=str(row["source_session_key"] or ""),
                metadata=dict(row["metadata"] or {}),
                score=float(row["score"]) if row["score"] is not None else None,
            )
            for row in result.mappings().all()
        ]

    async def archive_l1_batch(self, db: AsyncSession, *, user_id: str, memory_ids: list[str]) -> None:
        """Archive old L1 memories replaced by update/merge decisions."""

        if not memory_ids:
            return
        await db.execute(
            text(
                """
                UPDATE memory_items
                SET status = 'archived',
                    is_deleted = true,
                    deleted_at = now(),
                    updated_at = now()
                WHERE layer = 1
                  AND user_id = :user_id
                  AND memory_id = ANY(CAST(:memory_ids AS text[]))
                """
            ),
            {
                "user_id": user_id,
                "memory_ids": memory_ids,
            },
        )
        await db.flush()

    async def query_l1_for_l2(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        source_session_key: str,
        updated_after: datetime | None = None,
        limit: int = 100,
    ) -> list[L1MemoryForL2]:
        """Query active L1 memories that L2 has not consumed yet."""

        params: dict[str, object] = {
            "user_id": user_id,
            "source_session_key": source_session_key,
            "limit": limit,
        }
        updated_filter = ""
        if updated_after is not None:
            updated_filter = "AND updated_at > :updated_after"
            params["updated_after"] = updated_after

        result = await db.execute(
            text(
                f"""
                SELECT
                    memory_id,
                    user_id,
                    memory_type,
                    content,
                    priority,
                    scene_name,
                    source_conversation_id,
                    source_session_key,
                    metadata,
                    created_at,
                    updated_at
                FROM memory_items
                WHERE layer = 1
                  AND status = 'active'
                  AND is_deleted = false
                  AND user_id = :user_id
                  AND (
                    source_conversation_id = :source_session_key
                    OR source_session_key = :source_session_key
                  )
                  {updated_filter}
                ORDER BY updated_at ASC
                LIMIT :limit
                """
            ),
            params,
        )
        return [
            L1MemoryForL2(
                memory_id=str(row["memory_id"]),
                user_id=str(row["user_id"]),
                memory_type=str(row["memory_type"]),
                content=str(row["content"]),
                priority=int(row["priority"] or 50),
                scene_name=str(row["scene_name"] or ""),
                source_conversation_id=str(row["source_conversation_id"] or ""),
                source_session_key=str(row["source_session_key"] or ""),
                metadata=dict(row["metadata"] or {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in result.mappings().all()
        ]

    async def query_l2_scenes(self, db: AsyncSession, *, user_id: str, limit: int = 50) -> list[L2SceneRow]:
        """Query active DB-native L2 scene blocks."""

        result = await db.execute(
            text(
                """
                SELECT
                    memory_id,
                    user_id,
                    scene_name,
                    content,
                    metadata,
                    created_at,
                    updated_at
                FROM memory_items
                WHERE layer = 2
                  AND memory_type = 'scene_block'
                  AND status = 'active'
                  AND is_deleted = false
                  AND user_id = :user_id
                ORDER BY updated_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
        scenes: list[L2SceneRow] = []
        for row in result.mappings().all():
            metadata = dict(row["metadata"] or {})
            scene_name = str(row["scene_name"] or "")
            filename = str(metadata.get("filename") or self._scene_filename(scene_name))
            scenes.append(
                L2SceneRow(
                    memory_id=str(row["memory_id"]),
                    user_id=str(row["user_id"]),
                    filename=filename,
                    scene_name=scene_name,
                    content=str(row["content"] or ""),
                    metadata=metadata,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return scenes

    async def upsert_l2_scene(self, db: AsyncSession, *, obj_in: L2SceneCreate) -> None:
        """Insert or update one DB-native L2 scene block."""

        data = obj_in.model_dump()
        metadata = dict(data["metadata"])
        metadata["filename"] = data["filename"]
        await db.execute(
            text(
                """
                INSERT INTO memory_items (
                    memory_id, user_id, layer, memory_type, content, embedding,
                    priority, scene_name, source_conversation_id, source_session_key,
                    metadata, status, created_at, updated_at
                ) VALUES (
                    :memory_id, :user_id, 2, 'scene_block', :content, NULL,
                    50, :scene_name, :source_conversation_id, :source_session_key,
                    CAST(:metadata_json AS jsonb), 'active', :created_at, :updated_at
                )
                ON CONFLICT (memory_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    scene_name = EXCLUDED.scene_name,
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
                "content": data["content"],
                "scene_name": data["scene_name"],
                "source_conversation_id": data["source_conversation_id"],
                "source_session_key": data["source_session_key"],
                "metadata_json": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                "created_at": data["created_at"],
                "updated_at": data["updated_at"],
            },
        )
        await db.flush()

    def _l0_time_ms_expr(self) -> str:
        return "COALESCE(NULLIF(metadata->>'message_ts_ms', '')::double precision, EXTRACT(EPOCH FROM created_at) * 1000)"

    def _vector_to_text(self, embedding: list[float] | None) -> str | None:
        if not embedding:
            return None
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    def _scene_filename(self, scene_name: str) -> str:
        return scene_name if scene_name.endswith(".md") else f"{scene_name or 'scene'}.md"


memory_item_repository = MemoryItemRepository()

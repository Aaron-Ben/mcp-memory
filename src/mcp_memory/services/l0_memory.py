import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.models.base import get_china_time
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas.memory_items import L0MessageCreate, MemoryItemCreate

__all__ = ["L0MemoryService", "l0_memory_service"]


META_ROLE_KEY = "_role"
META_SESSION_KEY = "_session_key"
SYSTEM_REMINDER_PATTERN = re.compile(
    r"<system-reminder\b[^>]*>.*?</system-reminder>",
    flags=re.IGNORECASE | re.DOTALL,
)


class L0MemoryService:
    """Service for saving raw conversation messages as L0 memories."""

    async def save_message(self, db: AsyncSession, *, obj_in: L0MessageCreate) -> str:
        if obj_in.role == "tool":
            return self._resolve_memory_id(obj_in)

        content = self._strip_system_reminders(obj_in.content)
        memory_id = self._resolve_memory_id(obj_in, content=content)
        if not content:
            return memory_id

        now = get_china_time()
        metadata = self._build_metadata(obj_in)
        item = MemoryItemCreate(
            memory_id=memory_id,
            user_id=obj_in.user_id,
            layer=0,
            memory_type=obj_in.role or "message",
            content=content,
            priority=0,
            scene_name="",
            source_conversation_id=obj_in.source_conversation_id,
            source_session_key=obj_in.source_session_key,
            metadata=metadata,
            status="active",
            created_at=now,
            updated_at=now,
        )
        await memory_item_repository.upsert_l0(db, obj_in=item)
        return memory_id

    def _resolve_memory_id(self, message: L0MessageCreate, *, content: str | None = None) -> str:
        if message.memory_id:
            return message.memory_id
        if message.message_id:
            return message.message_id

        normalized_content = message.content if content is None else content
        raw = "\x1f".join(
            [
                message.user_id,
                message.source_conversation_id,
                message.source_session_key,
                message.role,
                str(message.timestamp_ms or ""),
                normalized_content,
            ]
        )
        return f"l0_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    def _strip_system_reminders(self, content: str) -> str:
        stripped = SYSTEM_REMINDER_PATTERN.sub("", content)
        return re.sub(r"\n{3,}", "\n\n", stripped).strip()

    def _build_metadata(self, message: L0MessageCreate) -> dict[str, Any]:
        metadata = dict(message.metadata)
        metadata[META_ROLE_KEY] = message.role
        metadata[META_SESSION_KEY] = message.source_session_key
        if message.timestamp_ms is not None:
            metadata["message_ts_ms"] = message.timestamp_ms
        metadata["recorded_at"] = message.recorded_at or self._recorded_at(message.timestamp_ms)
        return metadata

    def _recorded_at(self, timestamp_ms: int | None) -> str:
        if timestamp_ms is None:
            return datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC).isoformat().replace("+00:00", "Z")


l0_memory_service = L0MemoryService()

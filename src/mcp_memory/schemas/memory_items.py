from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["L0MessageCreate", "MemoryItemCreate"]


class MemoryItemCreate(BaseModel):
    """Schema for creating or upserting a memory item."""

    model_config = ConfigDict(populate_by_name=True)

    memory_id: str
    user_id: str
    layer: int
    memory_type: str = "memory"
    content: str = ""
    embedding: list[float] | None = None
    priority: int = 50
    scene_name: str = ""
    source_conversation_id: str = ""
    source_session_key: str = ""
    meta_data: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    status: str = "active"
    created_at: datetime
    updated_at: datetime


class L0MessageCreate(BaseModel):
    """Raw conversation message to be saved as L0 memory."""

    user_id: str
    source_conversation_id: str
    source_session_key: str = ""
    role: str = "message"
    content: str
    message_id: str | None = None
    memory_id: str | None = None
    timestamp_ms: int | None = None
    recorded_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

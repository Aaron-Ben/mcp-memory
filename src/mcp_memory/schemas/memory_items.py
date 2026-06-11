from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "L0MessageCreate",
    "L0MemoryRow",
    "L0ToL1Result",
    "L1MemoryCreate",
    "L1MemoryExtracted",
    "MemoryItemCreate",
]


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


class L0MemoryRow(BaseModel):
    """L0 row used as input for L1 extraction."""

    memory_id: str
    user_id: str
    source_conversation_id: str
    source_session_key: str
    role: str
    content: str
    timestamp_ms: int
    recorded_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class L1MemoryExtracted(BaseModel):
    """One L1 memory extracted from L0 messages before persistence."""

    content: str
    memory_type: Literal["persona", "episodic", "instruction"]
    priority: int = Field(default=50, ge=-1, le=100)
    scene_name: str = ""
    source_memory_ids: list[str] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class L1MemoryCreate(BaseModel):
    """Schema for creating or upserting one L1 memory."""

    memory_id: str
    user_id: str
    memory_type: Literal["persona", "episodic", "instruction"]
    content: str
    priority: int = Field(default=50, ge=-1, le=100)
    scene_name: str = ""
    source_conversation_id: str = ""
    source_session_key: str = ""
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L0ToL1Result(BaseModel):
    """Result of one L0 to L1 pipeline run."""

    input_count: int
    extracted_count: int
    stored_count: int
    memory_ids: list[str] = Field(default_factory=list)

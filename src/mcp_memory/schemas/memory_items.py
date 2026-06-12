from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "L0MessageCreate",
    "L0MemoryRow",
    "L0ToL1Result",
    "L1MemoryCreate",
    "L1MemoryDedupDecision",
    "L1MemoryExtracted",
    "L1MemorySearchResult",
    "L1MemoryForL2",
    "L1ToL2Result",
    "L2SceneCreate",
    "L2SceneRow",
    "L2ToL3Result",
    "L3PersonaCreate",
    "L3PersonaRow",
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


class L1MemorySearchResult(BaseModel):
    """One existing L1 memory recalled as a dedup candidate."""

    memory_id: str
    user_id: str
    memory_type: str
    content: str
    priority: int
    scene_name: str
    source_conversation_id: str
    source_session_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None


class L1MemoryDedupDecision(BaseModel):
    """Decision for one extracted L1 memory."""

    record_id: str
    action: Literal["store", "update", "merge", "skip"]
    target_ids: list[str] = Field(default_factory=list)
    merged_content: str | None = None
    merged_type: Literal["persona", "episodic", "instruction"] | None = None
    merged_priority: int | None = None


class L1MemoryForL2(BaseModel):
    """One active L1 memory used as input for L2 scene generation."""

    memory_id: str
    user_id: str
    memory_type: str
    content: str
    priority: int
    scene_name: str
    source_conversation_id: str
    source_session_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L2SceneRow(BaseModel):
    """One active L2 scene block stored in memory_items."""

    memory_id: str
    user_id: str
    filename: str
    scene_name: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L2SceneCreate(BaseModel):
    """Payload for creating or updating one L2 DB-native scene block."""

    memory_id: str
    user_id: str
    filename: str
    scene_name: str
    content: str
    source_conversation_id: str = ""
    source_session_key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L3PersonaRow(BaseModel):
    """One active L3 persona stored in memory_items."""

    memory_id: str
    user_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L3PersonaCreate(BaseModel):
    """Payload for creating or updating one DB-native L3 persona."""

    memory_id: str
    user_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class L1ToL2Result(BaseModel):
    """Result of one L1 to L2 pipeline run."""

    input_count: int
    stored_count: int
    skipped: bool = False
    latest_cursor: datetime | None = None
    scene_id: str | None = None
    scene_name: str | None = None


class L2ToL3Result(BaseModel):
    """Result of one L2 to L3 pipeline run."""

    input_count: int
    changed_count: int
    stored: bool = False
    skipped: bool = False
    latest_cursor: datetime | None = None
    memory_id: str | None = None


class L0ToL1Result(BaseModel):
    """Result of one L0 to L1 pipeline run."""

    input_count: int
    processed_count: int = 0
    extracted_count: int
    stored_count: int
    latest_cursor: int | None = None
    last_scene_name: str | None = None
    has_more: bool = False
    has_full_backlog: bool = False
    memory_ids: list[str] = Field(default_factory=list)

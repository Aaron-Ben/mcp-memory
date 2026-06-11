from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from .base import Base, TimestampSoftDeleteMixin

__all__ = ["MemoryItem", "Vector"]


class Vector(UserDefinedType):
    """PostgreSQL pgvector column type."""

    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **_kw: Any) -> str:
        return f"vector({self.dimensions})"


class MemoryItem(TimestampSoftDeleteMixin, Base):
    """Memory item table."""

    __tablename__ = "memory_items"

    memory_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False, comment="记忆ID")
    user_id: Mapped[str] = mapped_column(Text, nullable=False, comment="用户ID")
    layer: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="记忆层级")
    memory_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="memory",
        comment="记忆类型",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="记忆内容")
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
        comment="记忆内容的向量表示",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
        comment="记忆优先级，数值越小优先级越高",
    )
    scene_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="场景名称",
    )
    source_conversation_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="记忆来源的对话ID",
    )
    source_session_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="记忆来源的会话ID",
    )
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        comment="元数据信息",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="active",
        comment="记忆状态",
    )

    __table_args__ = (
        CheckConstraint("layer BETWEEN 0 AND 3", name="memory_items_layer_check"),
        CheckConstraint("status IN ('active', 'archived')", name="memory_items_status_check"),
        CheckConstraint("is_deleted = (deleted_at IS NOT NULL)", name="memory_items_deleted_state_check"),
        Index("idx_memory_items_user_layer_status", "user_id", "layer", "status"),
        Index("idx_memory_items_user_source", "user_id", "source_conversation_id"),
        Index("idx_memory_items_type_status", "memory_type", "status"),
        Index("idx_memory_items_updated_at", "updated_at"),
        Index(
            "idx_memory_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<MemoryItem(memory_id='{self.memory_id}', user_id='{self.user_id}')>"

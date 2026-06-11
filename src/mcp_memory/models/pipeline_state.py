from sqlalchemy import BigInteger, Boolean, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampSoftDeleteMixin

__all__ = ["PipelineState"]


class PipelineState(TimestampSoftDeleteMixin, Base):
    """Pipeline state for incremental L0 to L1 extraction."""

    __tablename__ = "pipeline_state"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False, comment="用户ID")
    source_session_key: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False, comment="来源会话ID")
    conversation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="待处理会话轮次数")
    warmup_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="预热触发阈值")
    last_l1_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="L1 已处理 L0 时间游标")
    last_scene_name: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="上一次 L1 情境名称")
    l1_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="L1 是否正在运行")

    __table_args__ = (
        Index("idx_pipeline_state_updated_at", "updated_at"),
        Index("idx_pipeline_state_l1_running", "l1_running"),
    )

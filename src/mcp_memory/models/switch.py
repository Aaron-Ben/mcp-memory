from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

__all__ = ["Switch"]


class Switch(Base):
    """User memory and dream switch table."""

    __tablename__ = "switch"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False, comment="用户ID")
    memory_switch: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="记忆开关",
    )
    dream_switch: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="梦境开关",
    )

    def __repr__(self) -> str:
        return f"<Switch(user_id='{self.user_id}')>"

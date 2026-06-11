from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

__all__ = [
    "Base",
    "BaseModel",
    "CHINA_TZ",
    "TimestampSoftDeleteMixin",
    "get_china_time",
]


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


CHINA_TZ = timezone(timedelta(hours=8))


def get_china_time() -> datetime:
    """Return naive UTC+8 local time for database storage."""

    return datetime.now(CHINA_TZ).replace(tzinfo=None)


class TimestampSoftDeleteMixin:
    """Common timestamp and soft-delete columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=get_china_time,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=get_china_time,
        onupdate=get_china_time,
        comment="更新时间",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否删除",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        default=None,
        comment="删除时间",
    )

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = get_china_time()

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None

    @validates("created_at", "updated_at", "deleted_at")
    def validate_datetime(self, _key: str, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(CHINA_TZ).replace(tzinfo=None)
        return value

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for prop in inspect(self).mapper.column_attrs:
            column = prop.columns[0]
            value = getattr(self, prop.key)
            result[column.name] = value.isoformat() if hasattr(value, "isoformat") else value
        return result


class BaseModel(TimestampSoftDeleteMixin, Base):
    """Base model for tables that use an integer id primary key."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        nullable=False,
        index=True,
        comment="主键ID",
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from mcp_memory.config import settings

__all__ = ["AsyncSessionLocal", "async_db_session", "async_engine", "check_db_health"]

logger = logging.getLogger(__name__)


def json_serializer(obj: Any) -> str:
    """Serialize JSON values without escaping Chinese characters."""

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_deserializer(data: str) -> Any:
    """Deserialize JSON values from PostgreSQL."""

    return json.loads(data)


async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URI,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=30,
    pool_timeout=30,
    echo=False,
    echo_pool=False,
    json_serializer=json_serializer,
    json_deserializer=json_deserializer,
    connect_args={
        "server_settings": {
            "timezone": "Asia/Shanghai",
            "client_encoding": "UTF8",
            "application_name": "mcp_memory",
        },
        "timeout": 10.0,
        "command_timeout": 60.0,
        "statement_cache_size": 0,
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@asynccontextmanager
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session with automatic commit or rollback."""

    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def check_db_health() -> bool:
    """Return whether the database accepts a simple query."""

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("数据库健康检查失败: %s", exc)
        return False

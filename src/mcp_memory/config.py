from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["CONFIG_PATH", "Settings", "settings"]


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "local.yaml"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _set_if_present(values: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        values[key] = value


def _timeout_ms_to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    return float(value) / 1000


def _load_yaml_settings(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load nested yuanxi-memory style YAML into flat Settings fields."""

    if not path.exists():
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件必须是 YAML object: {path}")

    grpc = _as_dict(raw.get("grpc"))
    llm = _as_dict(raw.get("llm"))
    memory = _as_dict(raw.get("memory"))
    pgsql = _as_dict(memory.get("pgsql"))
    capture = _as_dict(memory.get("capture"))
    extraction = _as_dict(memory.get("extraction"))
    l1 = _as_dict(memory.get("l1"))
    pipeline = _as_dict(memory.get("pipeline"))
    embedding = _as_dict(memory.get("embedding"))

    values: dict[str, Any] = {}

    _set_if_present(values, "GRPC_HOST", grpc.get("host"))
    _set_if_present(values, "GRPC_PORT", grpc.get("port"))

    _set_if_present(values, "POSTGRES_SERVER", pgsql.get("host"))
    _set_if_present(values, "POSTGRES_PORT", pgsql.get("port"))
    _set_if_present(values, "POSTGRES_USER", pgsql.get("user"))
    _set_if_present(values, "POSTGRES_PASSWORD", pgsql.get("password"))
    _set_if_present(values, "POSTGRES_DB", pgsql.get("database"))
    _set_if_present(values, "POSTGRES_POOL_SIZE", pgsql.get("max"))

    _set_if_present(values, "LLM_API_KEY", llm.get("apiKey"))
    _set_if_present(values, "LLM_BASE_URL", llm.get("baseUrl"))
    _set_if_present(values, "LLM_MODEL", llm.get("model"))
    _set_if_present(values, "LLM_MAX_TOKENS", llm.get("maxTokens"))
    _set_if_present(values, "LLM_TIMEOUT_SECONDS", _timeout_ms_to_seconds(llm.get("timeoutMs")))

    _set_if_present(values, "MEMORY_CAPTURE_ENABLED", capture.get("enabled"))
    _set_if_present(values, "MEMORY_EXTRACTION_ENABLED", extraction.get("enabled"))
    _set_if_present(values, "MEMORY_ENABLE_EXTRACT_FILTER", l1.get("extract"))
    _set_if_present(values, "MEMORY_ENABLE_DEDUP", extraction.get("enableDedup"))
    _set_if_present(values, "MEMORY_ENABLE_DEDUP", l1.get("dedup"))
    _set_if_present(values, "MEMORY_MAX_MEMORIES_PER_SESSION", extraction.get("maxMemoriesPerSession"))
    _set_if_present(values, "PIPELINE_EVERY_N_CONVERSATIONS", pipeline.get("everyNConversations"))
    _set_if_present(values, "PIPELINE_ENABLE_WARMUP", pipeline.get("enableWarmup"))
    _set_if_present(values, "PIPELINE_L1_IDLE_TIMEOUT_SECONDS", pipeline.get("l1IdleTimeoutSeconds"))

    _set_if_present(values, "EMBEDDING_ENABLED", embedding.get("enabled"))
    _set_if_present(values, "EMBEDDING_API_KEY", embedding.get("apiKey"))
    _set_if_present(values, "EMBEDDING_BASE_URL", embedding.get("baseUrl"))
    _set_if_present(values, "EMBEDDING_MODEL", embedding.get("model"))
    _set_if_present(values, "EMBEDDING_DIMENSIONS", embedding.get("dimensions"))
    _set_if_present(values, "EMBEDDING_TIMEOUT_SECONDS", _timeout_ms_to_seconds(embedding.get("timeoutMs")))
    _set_if_present(values, "EMBEDDING_SEND_DIMENSIONS", embedding.get("sendDimensions"))
    _set_if_present(values, "EMBEDDING_MAX_INPUT_CHARS", embedding.get("maxInputChars"))

    return values


class Settings(BaseModel):
    """Application settings loaded from config/local.yaml."""

    model_config = ConfigDict(extra="ignore")

    POSTGRES_SERVER: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "SecurePassword123!"
    POSTGRES_DB: str = "mcp_memory"
    POSTGRES_POOL_SIZE: int = 20

    GRPC_HOST: str = "127.0.0.1"
    GRPC_PORT: int = 50051

    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str | None = None
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_MAX_TOKENS: int = 4096

    MEMORY_CAPTURE_ENABLED: bool = True
    MEMORY_EXTRACTION_ENABLED: bool = True
    MEMORY_ENABLE_EXTRACT_FILTER: bool = True
    MEMORY_ENABLE_DEDUP: bool = True
    MEMORY_MAX_MEMORIES_PER_SESSION: int = 20
    PIPELINE_EVERY_N_CONVERSATIONS: int = 5
    PIPELINE_ENABLE_WARMUP: bool = True
    PIPELINE_L1_IDLE_TIMEOUT_SECONDS: int = 600

    EMBEDDING_ENABLED: bool = True
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    EMBEDDING_SEND_DIMENSIONS: bool = True
    EMBEDDING_MAX_INPUT_CHARS: int | None = None

    SQLALCHEMY_DATABASE_URI: str | None = Field(default=None)
    ASYNC_DATABASE_URI: str | None = Field(default=None)

    @field_validator(
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_MAX_INPUT_CHARS",
        mode="before",
    )
    @classmethod
    def empty_string_as_none(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def build_database_uris(self) -> "Settings":
        if self.SQLALCHEMY_DATABASE_URI is None:
            self.SQLALCHEMY_DATABASE_URI = (
                f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        if self.ASYNC_DATABASE_URI is None:
            self.ASYNC_DATABASE_URI = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        return self


settings = Settings(**_load_yaml_settings())

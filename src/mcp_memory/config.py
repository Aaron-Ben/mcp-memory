from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    POSTGRES_SERVER: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "SecurePassword123!"
    POSTGRES_DB: str = "mcp_memory"

    GRPC_HOST: str = "127.0.0.1"
    GRPC_PORT: int = 50051

    SQLALCHEMY_DATABASE_URI: str | None = Field(default=None)
    ASYNC_DATABASE_URI: str | None = Field(default=None)

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


settings = Settings()

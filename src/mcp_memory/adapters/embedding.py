from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from mcp_memory.config import settings

__all__ = ["OpenAICompatibleEmbeddingProvider", "create_embedding_provider_from_settings"]


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """OpenAI-compatible embedding provider matching yuanxi-memory's EmbeddingService shape."""

    api_key: str
    model: str
    base_url: str | None = None
    dimensions: int = 1024
    timeout_seconds: float = 60.0
    send_dimensions: bool = True
    max_input_chars: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_client",
            AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url or None,
                timeout=self.timeout_seconds,
            ),
        )

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        input_texts = [self._truncate(text) for text in texts]
        kwargs = {"dimensions": self.dimensions} if self.send_dimensions else {}
        response = await self._client.embeddings.create(
            model=self.model,
            input=input_texts,
            timeout=self.timeout_seconds,
            **kwargs,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def get_dimensions(self) -> int:
        return self.dimensions

    async def aclose(self) -> None:
        await self._client.close()

    def _truncate(self, text: str) -> str:
        if self.max_input_chars is None or self.max_input_chars <= 0:
            return text
        return text[: self.max_input_chars]


def create_embedding_provider_from_settings() -> OpenAICompatibleEmbeddingProvider | None:
    if not settings.EMBEDDING_ENABLED or not settings.EMBEDDING_API_KEY or not settings.EMBEDDING_MODEL:
        return None
    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL,
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
        timeout_seconds=settings.EMBEDDING_TIMEOUT_SECONDS,
        send_dimensions=settings.EMBEDDING_SEND_DIMENSIONS,
        max_input_chars=settings.EMBEDDING_MAX_INPUT_CHARS,
    )

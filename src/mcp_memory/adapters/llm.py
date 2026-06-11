from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from mcp_memory.config import settings

__all__ = ["OpenAICompatibleLLMRunner", "create_llm_runner_from_settings"]


@dataclass(frozen=True)
class OpenAICompatibleLLMRunner:
    """OpenAI-compatible LLM runner matching yuanxi-memory's LLMRunner boundary."""

    api_key: str
    model: str
    base_url: str | None = None
    timeout_seconds: float = 120.0
    max_tokens: int = 4096

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

    async def run(
        self,
        *,
        prompt: str,
        task_id: str,
        system_prompt: str | None = None,
        timeout_ms: int | None = None,
        max_tokens: int | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
            timeout=(timeout_ms / 1000) if timeout_ms else self.timeout_seconds,
            stream=False,
        )
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""

    async def aclose(self) -> None:
        await self._client.close()


def create_llm_runner_from_settings() -> OpenAICompatibleLLMRunner | None:
    if not settings.LLM_API_KEY or not settings.LLM_MODEL:
        return None
    return OpenAICompatibleLLMRunner(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        max_tokens=settings.LLM_MAX_TOKENS,
    )

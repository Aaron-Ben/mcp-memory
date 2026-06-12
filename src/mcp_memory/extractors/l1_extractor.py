from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from mcp_memory.prompts import L1_EXTRACTION_SYSTEM_PROMPT, build_l1_extraction_prompt
from mcp_memory.schemas import L0MemoryRow, L1MemoryExtracted

__all__ = ["L1Extractor", "LLMRunner", "PromptL1Extractor", "parse_l1_extraction_response"]


ALLOWED_MEMORY_TYPES = {"persona", "episodic", "instruction"}
logger = logging.getLogger(__name__)


class LLMRunner(Protocol):
    """Minimal LLM runner interface aligned with yuanxi-memory."""

    async def run(
        self,
        *,
        prompt: str,
        task_id: str,
        system_prompt: str | None = None,
        timeout_ms: int | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Execute one LLM prompt and return raw text output."""


class L1Extractor(Protocol):
    """Protocol for L1 extractors."""

    async def extract(
        self,
        *,
        new_messages: list[L0MemoryRow],
        background_messages: list[L0MemoryRow] | None = None,
        previous_scene_name: str | None = None,
    ) -> list[L1MemoryExtracted]:
        """Extract L1 memories from L0 rows."""


class PromptL1Extractor:
    """Prompt-based L1 extractor using an injected LLM client."""

    def __init__(self, llm_runner: LLMRunner, *, timeout_ms: int = 180_000):
        self.llm_runner = llm_runner
        self.timeout_ms = timeout_ms

    async def extract(
        self,
        *,
        new_messages: list[L0MemoryRow],
        background_messages: list[L0MemoryRow] | None = None,
        previous_scene_name: str | None = None,
    ) -> list[L1MemoryExtracted]:
        user_prompt = build_l1_extraction_prompt(
            new_messages=new_messages,
            background_messages=background_messages,
            previous_scene_name=previous_scene_name,
        )
        raw = await self.llm_runner.run(
            prompt=user_prompt,
            system_prompt=L1_EXTRACTION_SYSTEM_PROMPT,
            task_id="l1-extraction",
            timeout_ms=self.timeout_ms,
        )
        memories = parse_l1_extraction_response(raw)
        if not memories:
            logger.warning("[L0->L1] LLM 返回未解析出 L1 记忆，raw_preview=%s", _preview_raw(raw))
        return memories


def parse_l1_extraction_response(raw: str) -> list[L1MemoryExtracted]:
    """Parse LLM scene-segmented L1 extraction response."""

    try:
        parsed = json.loads(_extract_json_payload(raw))
    except json.JSONDecodeError as exc:
        logger.warning("[L0->L1] L1 抽取结果不是合法 JSON: error=%s raw_preview=%s", exc, _preview_raw(raw))
        return []

    parsed = _normalize_scene_payload(parsed)
    if not isinstance(parsed, list):
        logger.warning("[L0->L1] L1 抽取结果不是情境数组: payload_type=%s", type(parsed).__name__)
        return []

    memories: list[L1MemoryExtracted] = []
    candidate_count = 0
    skipped_invalid_type = 0
    skipped_empty_content = 0
    for scene in parsed:
        if not isinstance(scene, dict):
            continue
        scene_name = _string(scene.get("scene_name"))
        scene_message_ids = _string_list(scene.get("message_ids"))
        scene_memories = scene.get("memories")
        if not isinstance(scene_memories, list):
            continue

        for item in scene_memories:
            candidate_count += 1
            if not isinstance(item, dict):
                continue
            content = _string(item.get("content")).strip()
            memory_type = _string(item.get("type")).strip()
            if not content:
                skipped_empty_content += 1
                continue
            if memory_type not in ALLOWED_MEMORY_TYPES:
                skipped_invalid_type += 1
                continue
            source_message_ids = _string_list(item.get("source_message_ids")) or scene_message_ids
            memories.append(
                L1MemoryExtracted(
                    content=content,
                    memory_type=memory_type,
                    priority=_int(item.get("priority"), default=50),
                    scene_name=scene_name,
                    source_memory_ids=source_message_ids,
                    source_message_ids=source_message_ids,
                    confidence=_float_or_none(item.get("confidence")),
                    metadata=_dict(item.get("metadata")),
                )
            )
    if not memories:
        logger.info(
            "[L0->L1] L1 解析完成但没有可保存记忆: scenes=%s candidates=%s skipped_empty=%s skipped_invalid_type=%s",
            len(parsed),
            candidate_count,
            skipped_empty_content,
            skipped_invalid_type,
        )
    return memories


def _extract_json_payload(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.startswith("{") and text.endswith("}"):
        return text
    if text.startswith("[") and text.endswith("]"):
        return text
    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match is not None:
        return object_match.group(0)
    match = re.search(r"\[[\s\S]*\]", text)
    if match is None:
        return "[]"
    return match.group(0)


def _normalize_scene_payload(parsed: Any) -> Any:
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return parsed

    for key in ("scenes", "result", "data"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    if isinstance(parsed.get("memories"), list):
        return [parsed]
    return parsed


def _preview_raw(raw: str, *, limit: int = 1200) -> str:
    compact = re.sub(r"\s+", " ", (raw or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "...<truncated>"


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int(value: Any, *, default: int) -> int:
    return value if isinstance(value, int) else default


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mcp_memory.extractors import LLMRunner
from mcp_memory.prompts import L1_DEDUP_SYSTEM_PROMPT, build_l1_dedup_prompt
from mcp_memory.repositories.memory_items import memory_item_repository
from mcp_memory.schemas import L1MemoryDedupDecision, L1MemoryExtracted, L1MemorySearchResult
from mcp_memory.services.l1_memory import EmbeddingProvider

__all__ = ["L1DedupService"]

logger = logging.getLogger(__name__)


class L1DedupService:
    """Deduplicate extracted L1 memories against existing active L1 memories."""

    def __init__(
        self,
        *,
        llm_runner: LLMRunner,
        embedding_provider: EmbeddingProvider | None,
        top_k: int = 10,
        timeout_ms: int = 180_000,
    ) -> None:
        self.llm_runner = llm_runner
        self.embedding_provider = embedding_provider
        self.top_k = top_k
        self.timeout_ms = timeout_ms

    async def dedup(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        memories: list[L1MemoryExtracted],
        record_ids: list[str],
    ) -> list[L1MemoryDedupDecision]:
        if not memories:
            return []
        if len(memories) != len(record_ids):
            return self._store_all(record_ids)
        if self.embedding_provider is None:
            logger.info("[L0->L1] L1 去重跳过: embedding_provider 未配置")
            return self._store_all(record_ids)

        l1_count = await memory_item_repository.count_l1(db, user_id=user_id)
        if l1_count <= 0:
            logger.info("[L0->L1] L1 去重跳过: 当前用户还没有历史 L1")
            return self._store_all(record_ids)

        try:
            embeddings = await self.embedding_provider.embed_batch([memory.content for memory in memories])
        except Exception:
            logger.exception("[L0->L1] L1 去重跳过: 新记忆 embedding 生成失败")
            return self._store_all(record_ids)

        record_id_set = set(record_ids)
        matches: list[tuple[str, L1MemoryExtracted, list[L1MemorySearchResult]]] = []
        for record_id, memory, embedding in zip(record_ids, memories, embeddings, strict=True):
            candidates = await memory_item_repository.search_l1_vector(
                db,
                user_id=user_id,
                embedding=embedding,
                limit=max(self.top_k, 1),
            )
            candidates = [candidate for candidate in candidates if candidate.memory_id not in record_id_set]
            matches.append((record_id, memory, candidates))

        candidate_count = sum(len(candidates) for _record_id, _memory, candidates in matches)
        if candidate_count <= 0:
            logger.info("[L0->L1] L1 去重跳过: 向量召回没有命中候选")
            return self._store_all(record_ids)

        logger.info(
            "[L0->L1] 开始 L1 去重: new=%s candidates=%s",
            len(memories),
            candidate_count,
        )
        prompt = build_l1_dedup_prompt(matches)
        try:
            raw = await self.llm_runner.run(
                prompt=prompt,
                system_prompt=L1_DEDUP_SYSTEM_PROMPT,
                task_id="l1-dedup",
                timeout_ms=self.timeout_ms,
            )
            decisions = parse_l1_dedup_response(raw, record_ids=record_ids)
        except Exception:
            logger.exception("[L0->L1] L1 去重失败: fallback 为全部 store")
            return self._store_all(record_ids)

        action_counts: dict[str, int] = {}
        for decision in decisions:
            action_counts[decision.action] = action_counts.get(decision.action, 0) + 1
        logger.info("[L0->L1] L1 去重完成: %s", action_counts)
        return decisions

    def _store_all(self, record_ids: list[str]) -> list[L1MemoryDedupDecision]:
        return [L1MemoryDedupDecision(record_id=record_id, action="store") for record_id in record_ids]


def parse_l1_dedup_response(raw: str, *, record_ids: list[str]) -> list[L1MemoryDedupDecision]:
    """Parse LLM dedup response and fill missing decisions as store."""

    record_id_set = set(record_ids)
    try:
        parsed = json.loads(_extract_json_array(raw))
    except json.JSONDecodeError:
        return [L1MemoryDedupDecision(record_id=record_id, action="store") for record_id in record_ids]

    if not isinstance(parsed, list):
        return [L1MemoryDedupDecision(record_id=record_id, action="store") for record_id in record_ids]

    by_record_id: dict[str, L1MemoryDedupDecision] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        record_id = str(item.get("record_id") or "")
        if record_id not in record_id_set or record_id in by_record_id:
            continue
        decision = _build_decision(item)
        if decision is not None:
            by_record_id[record_id] = decision

    return [
        by_record_id.get(record_id, L1MemoryDedupDecision(record_id=record_id, action="store"))
        for record_id in record_ids
    ]


def _build_decision(item: dict[str, Any]) -> L1MemoryDedupDecision | None:
    action = str(item.get("action") or "store")
    if action not in {"store", "update", "merge", "skip"}:
        action = "store"

    target_ids = _string_list(item.get("target_ids"))
    if action in {"update", "merge"} and not target_ids:
        action = "store"

    merged_content = _optional_string(item.get("merged_content"))
    merged_type = _optional_memory_type(item.get("merged_type"))
    merged_priority = _optional_priority(item.get("merged_priority"))
    if action in {"update", "merge"} and (not merged_content or merged_type is None or merged_priority is None):
        action = "store"
        target_ids = []
        merged_content = None
        merged_type = None
        merged_priority = None

    return L1MemoryDedupDecision(
        record_id=str(item.get("record_id") or ""),
        action=action,
        target_ids=target_ids if action in {"update", "merge"} else [],
        merged_content=merged_content,
        merged_type=merged_type,
        merged_priority=merged_priority,
    )


def _extract_json_array(raw: str) -> str:
    text_value = raw.strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value)
        text_value = re.sub(r"\s*```$", "", text_value)
    match = re.search(r"\[[\s\S]*\]", text_value)
    if match is None:
        return "[]"
    return match.group(0)


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _optional_memory_type(value: Any) -> str | None:
    text_value = _optional_string(value)
    if text_value in {"persona", "episodic", "instruction"}:
        return text_value
    return None


def _optional_priority(value: Any) -> int | None:
    if not isinstance(value, int):
        return None
    return max(0, min(100, value))

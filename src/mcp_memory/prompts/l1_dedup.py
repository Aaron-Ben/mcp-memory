import json

from mcp_memory.schemas import L1MemoryExtracted, L1MemorySearchResult

from ._loader import PromptLoader

__all__ = ["L1_DEDUP_SYSTEM_PROMPT", "build_l1_dedup_prompt"]


L1_DEDUP_SYSTEM_PROMPT = PromptLoader.load_module("l1_dedup_system")


def build_l1_dedup_prompt(
    matches: list[tuple[str, L1MemoryExtracted, list[L1MemorySearchResult]]],
) -> str:
    """Build one batch dedup prompt from new memories and candidate pools."""

    pool: dict[str, L1MemorySearchResult] = {}
    related_by_record_id: dict[str, list[str]] = {}
    for record_id, _memory, candidates in matches:
        related_ids: list[str] = []
        for candidate in candidates:
            pool[candidate.memory_id] = candidate
            related_ids.append(candidate.memory_id)
        related_by_record_id[record_id] = related_ids

    pool_payload = [
        {
            "record_id": candidate.memory_id,
            "content": candidate.content,
            "type": candidate.memory_type,
            "priority": candidate.priority,
            "scene_name": candidate.scene_name,
            "score": candidate.score,
        }
        for candidate in pool.values()
    ]
    new_payload = [
        {
            "record_id": record_id,
            "content": memory.content,
            "type": memory.memory_type,
            "priority": memory.priority,
            "scene_name": memory.scene_name,
            "related_candidate_ids": related_by_record_id.get(record_id, []),
        }
        for record_id, memory, _candidates in matches
    ]

    return "\n\n".join(
        [
            "## 统一候选记忆池",
            json.dumps(pool_payload, ensure_ascii=False, indent=2),
            "## 待判断的新记忆",
            json.dumps(new_payload, ensure_ascii=False, indent=2),
            "请逐条判断并输出决策 JSON 数组。候选列表为空的新记忆直接输出 action=store。",
        ]
    )

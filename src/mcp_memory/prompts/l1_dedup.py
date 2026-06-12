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
    if pool_payload:
        pool_section = f"## 统一候选记忆池（共 {len(pool_payload)} 条已有记忆）\n\n" + json.dumps(
            pool_payload,
            ensure_ascii=False,
            indent=2,
        )
    else:
        pool_section = "## 统一候选记忆池\n\n（空，没有已有记忆，所有新记忆直接 store）"

    memory_sections = []
    for idx, (record_id, memory, _candidates) in enumerate(matches, start=1):
        related_ids = related_by_record_id.get(record_id, [])
        memory_payload = {
            "record_id": record_id,
            "content": memory.content,
            "type": memory.memory_type,
            "priority": memory.priority,
            "scene_name": memory.scene_name,
        }
        related_note = json.dumps(related_ids, ensure_ascii=False) if related_ids else "[]（无相似候选，直接 store）"
        memory_sections.append(
            "\n".join(
                [
                    f"### 第 {idx} 条新记忆 (record_id: {record_id})",
                    json.dumps(memory_payload, ensure_ascii=False, indent=2),
                    "",
                    f"【关联候选 ID】{related_note}",
                ]
            )
        )

    return "\n\n".join(
        [
            "输出语言：`merged_content` 使用与候选池中已有记忆相同的语言。",
            pool_section,
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"## 待判断的新记忆（共 {len(matches)} 条）",
            "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n".join(memory_sections),
            "请逐条判断并输出决策 JSON 数组。候选列表为空的新记忆直接输出 action=store。",
        ]
    )

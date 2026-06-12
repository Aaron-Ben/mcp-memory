import json

from mcp_memory.schemas import L1MemoryForL2, L2SceneRow

from ._loader import PromptLoader

__all__ = ["build_l2_scene_prompt"]


def build_l2_scene_prompt(
    *,
    target_filename: str,
    existing_content: str | None,
    existing_scenes: list[L2SceneRow],
    memories: list[L1MemoryForL2],
    now_iso: str,
    max_scenes: int,
) -> tuple[str, str]:
    """Build DB-native L2 scene prompt aligned with yuanxi-memory buildDbL2Prompt."""

    system_prompt = PromptLoader.load_module("l2_scene_system").format(now_iso=now_iso)
    scene_count_warning = _scene_count_warning(len(existing_scenes), max_scenes)
    scene_list = _format_scene_list(
        target_filename=target_filename,
        existing_scenes=existing_scenes,
        max_scenes=max_scenes,
    )
    memories_json = json.dumps(
        [
            {
                "id": memory.memory_id,
                "content": memory.content,
                "type": memory.memory_type,
                "priority": memory.priority,
                "scene_name": memory.scene_name,
                "created_at": memory.created_at.isoformat(),
                "updated_at": memory.updated_at.isoformat(),
            }
            for memory in memories
        ],
        ensure_ascii=False,
        indent=2,
    )

    user_prompt = "\n".join(
        [
            f"当前时间: {now_iso}",
            f"目标逻辑文件名: {target_filename}",
            f"场景数量上限: {max_scenes}",
            f"场景数量提示: {scene_count_warning}",
            "",
            "## 目标场景当前内容",
            _markdown_block(existing_content) if existing_content else "(new scene)",
            "",
            "## 已有场景参考",
            scene_list,
            "",
            "## 新增 L1 记忆",
            f"```json\n{memories_json}\n```",
            "",
            f"请输出更新后的 {target_filename} Markdown body。",
        ]
    )
    return system_prompt, user_prompt


def _format_scene_list(
    *,
    target_filename: str,
    existing_scenes: list[L2SceneRow],
    max_scenes: int,
) -> str:
    parts: list[str] = []
    for index, scene in enumerate(existing_scenes[:max_scenes], start=1):
        marker = " (target)" if scene.filename == target_filename else ""
        parts.append(
            "\n\n".join(
                [
                    f"### {index}. {scene.filename}{marker}",
                    _markdown_block(_truncate(scene.content, 2200)),
                ]
            )
        )
    return "\n\n".join(parts) if parts else "(none)"


def _markdown_block(content: str) -> str:
    return f"```markdown\n{_escape_prompt_block(content)}\n```"


def _escape_prompt_block(content: str) -> str:
    return content.replace("```", "'''").strip()


def _truncate(content: str, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars].rstrip() + "\n..."


def _scene_count_warning(scene_count: int, max_scenes: int) -> str:
    if scene_count >= max_scenes:
        return "当前场景数量已达到或超过上限，必须优先更新或合并已有场景，不要创建新场景。"
    if scene_count == max_scenes - 1:
        return "当前场景数量距离上限只差 1 个，本次应优先更新已有场景，除非新增记忆完全无法融入。"
    if scene_count >= max(max_scenes - 3, 0):
        return "当前场景数量接近上限，应优先更新已有场景。"
    return "当前场景数量未接近上限，但仍应优先整合到已有相关场景。"

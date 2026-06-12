import json

from mcp_memory.schemas import L2SceneRow

from ._loader import PromptLoader

__all__ = ["build_l3_persona_prompt"]


def build_l3_persona_prompt(
    *,
    existing_persona: str | None,
    changed_scenes: list[L2SceneRow],
    all_scenes: list[L2SceneRow],
    incremental: bool,
    now_iso: str,
    max_length: int,
) -> tuple[str, str]:
    """Build DB-native L3 persona prompt."""

    system_prompt = PromptLoader.load_module("l3_persona_system").format(max_length=max_length)
    changed_scene_blocks = _format_scene_blocks(changed_scenes)
    scene_index_json = json.dumps(
        [_scene_index_payload(scene) for scene in all_scenes],
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = "\n".join(
        [
            f"当前时间: {now_iso}",
            f"更新模式: {'incremental' if incremental else 'first'}",
            f"变化场景数: {len(changed_scenes)}",
            f"全部场景数: {len(all_scenes)}",
            "",
            "## 当前 Persona",
            _markdown_block(existing_persona) if existing_persona else "(none)",
            "",
            "## 变化 L2 场景完整内容",
            changed_scene_blocks if changed_scene_blocks else "(none)",
            "",
            "## 全部 L2 场景索引",
            f"```json\n{scene_index_json}\n```",
            "",
            "请输出更新后的 persona Markdown body。不要添加 Scene Navigation。",
        ]
    )
    return system_prompt, user_prompt


def _format_scene_blocks(scenes: list[L2SceneRow]) -> str:
    parts: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        parts.append(
            "\n\n".join(
                [
                    f"### [{index}] {scene.filename}",
                    _markdown_block(_truncate(scene.content, 3200)),
                ]
            )
        )
    return "\n\n".join(parts)


def _scene_index_payload(scene: L2SceneRow) -> dict[str, object]:
    return {
        "memory_id": scene.memory_id,
        "filename": scene.filename,
        "scene_name": scene.scene_name,
        "summary": scene.metadata.get("summary") or "",
        "heat": scene.metadata.get("heat") or 0,
        "created_at": scene.created_at.isoformat(),
        "updated_at": scene.updated_at.isoformat(),
    }


def _markdown_block(content: str | None) -> str:
    return f"```markdown\n{_escape_prompt_block(content or '')}\n```"


def _escape_prompt_block(content: str) -> str:
    return content.replace("```", "'''").strip()


def _truncate(content: str, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars].rstrip() + "\n..."

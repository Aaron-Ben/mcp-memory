from mcp_memory.schemas import L0MemoryRow

from ._loader import PromptLoader

__all__ = ["L1_EXTRACTION_SYSTEM_PROMPT", "build_l1_extraction_prompt"]


L1_EXTRACTION_SYSTEM_PROMPT = PromptLoader.load_module("l1_extraction_system")


def build_l1_extraction_prompt(
    *,
    new_messages: list[L0MemoryRow],
    background_messages: list[L0MemoryRow] | None = None,
    previous_scene_name: str | None = None,
) -> str:
    background = background_messages or []
    bg_text = _format_messages(background) if background else "无"
    new_text = _format_messages(new_messages) if new_messages else "无"
    return PromptLoader.load_module("l1_extraction_user").format(
        previous_scene_name=previous_scene_name or "无",
        background_messages=bg_text,
        new_messages=new_text,
    )


def _format_messages(messages: list[L0MemoryRow]) -> str:
    return "\n\n".join(
        f"[{message.memory_id}] [{message.role}] [{message.recorded_at or message.timestamp_ms}]: {message.content}"
        for message in messages
    )

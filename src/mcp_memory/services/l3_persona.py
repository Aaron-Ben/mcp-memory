from __future__ import annotations

import re
from hashlib import sha256

from mcp_memory.extractors import LLMRunner
from mcp_memory.models.base import get_china_time
from mcp_memory.prompts import build_l3_persona_prompt
from mcp_memory.schemas import L2SceneRow, L3PersonaCreate, L3PersonaRow

__all__ = ["L3PersonaService"]


GENERATOR_VERSION = "l3_db_v1"
DB_NAV_HEADER = "## Scene Navigation (Memory Store Index)"
LOCAL_NAV_HEADER = "## Scene Navigation (Scene Index)"


class L3PersonaService:
    """Generate DB-native L3 persona from L2 scenes."""

    def __init__(self, *, llm_runner: LLMRunner, max_length: int = 2000, timeout_ms: int = 180_000) -> None:
        self.llm_runner = llm_runner
        self.max_length = max_length
        self.timeout_ms = timeout_ms

    async def generate_persona(
        self,
        *,
        user_id: str,
        changed_scenes: list[L2SceneRow],
        all_scenes: list[L2SceneRow],
        existing_persona: L3PersonaRow | None,
        trigger_reason: str,
    ) -> L3PersonaCreate | None:
        if not changed_scenes:
            return None

        now = get_china_time()
        existing_body = self.strip_scene_navigation(existing_persona.content) if existing_persona else None
        system_prompt, user_prompt = build_l3_persona_prompt(
            existing_persona=existing_body,
            changed_scenes=changed_scenes,
            all_scenes=all_scenes,
            incremental=existing_persona is not None,
            now_iso=now.isoformat(),
            max_length=self.max_length,
        )
        raw = await self.llm_runner.run(
            prompt=user_prompt,
            system_prompt=system_prompt,
            task_id="persona-db-generation",
            timeout_ms=self.timeout_ms,
        )
        body = self.sanitize_persona_body(self.strip_markdown_fence(raw))
        if not body:
            return None

        navigation = self.generate_db_scene_navigation(all_scenes)
        content = f"{body}\n\n{navigation}\n" if navigation else body
        metadata = self._build_metadata(
            content=body,
            changed_scenes=changed_scenes,
            all_scenes=all_scenes,
            existing_persona=existing_persona,
            trigger_reason=trigger_reason,
        )
        return L3PersonaCreate(
            memory_id=existing_persona.memory_id if existing_persona else self.resolve_persona_id(user_id),
            user_id=user_id,
            content=content,
            metadata=metadata,
            created_at=existing_persona.created_at if existing_persona else now,
            updated_at=now,
        )

    def resolve_persona_id(self, user_id: str) -> str:
        raw = "\x1f".join([user_id, "l3", "persona.md"])
        return f"l3_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    def strip_markdown_fence(self, raw: str) -> str:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def strip_scene_navigation(self, content: str) -> str:
        cut_positions = [pos for pos in (content.find(DB_NAV_HEADER), content.find(LOCAL_NAV_HEADER)) if pos >= 0]
        if not cut_positions:
            return content.strip()
        return content[: min(cut_positions)].strip()

    def sanitize_persona_body(self, content: str) -> str:
        text = self.strip_scene_navigation(content).strip()
        text = text.replace("<system-reminder>", "&lt;system-reminder&gt;")
        text = text.replace("</system-reminder>", "&lt;/system-reminder&gt;")
        return text

    def generate_db_scene_navigation(self, scenes: list[L2SceneRow]) -> str:
        if not scenes:
            return ""
        sorted_scenes = sorted(scenes, key=lambda scene: (-self._scene_heat(scene), scene.filename))
        blocks = []
        for scene in sorted_scenes:
            updated = scene.updated_at.isoformat() if scene.updated_at else ""
            heat = self._scene_heat(scene)
            summary = str(scene.metadata.get("summary") or self._first_content_line(scene.content))
            suffix_parts = []
            if updated:
                suffix_parts.append(f"Updated: {updated}")
            if heat > 0:
                suffix_parts.append(f"Heat: {heat}")
            suffix = f" | {' | '.join(suffix_parts)}" if suffix_parts else ""
            blocks.append(f"### {scene.filename.removesuffix('.md')}\nSummary: {summary}{suffix}")
        return "\n\n".join(
            [
                DB_NAV_HEADER,
                "*The following scene profiles are indexed in the memory store for this user. "
                "Use the names as retrieval hints; do not treat them as files or paths.*",
                "",
                "\n\n".join(blocks),
            ]
        )

    def _build_metadata(
        self,
        *,
        content: str,
        changed_scenes: list[L2SceneRow],
        all_scenes: list[L2SceneRow],
        existing_persona: L3PersonaRow | None,
        trigger_reason: str,
    ) -> dict[str, object]:
        latest_scene = max((scene.updated_at for scene in changed_scenes), default=None)
        return {
            "filename": "persona.md",
            "summary": self._summary_from_persona(content),
            "generator_version": GENERATOR_VERSION,
            "mode": "incremental" if existing_persona else "first",
            "trigger_reason": trigger_reason,
            "source_l2_ids": [scene.memory_id for scene in changed_scenes],
            "source_l2_filenames": [scene.filename for scene in changed_scenes],
            "scene_count": len(all_scenes),
            "changed_scene_count": len(changed_scenes),
            "last_scene_updated_at": latest_scene.isoformat() if latest_scene else None,
            "navigation_appended": bool(all_scenes),
        }

    def _summary_from_persona(self, content: str) -> str:
        line = self._first_content_line(content)
        return line[:120] if line else "用户长期画像"

    def _first_content_line(self, content: str) -> str:
        return (
            next(
                (
                    line.replace("#", "").strip()
                    for line in content.splitlines()
                    if line.replace("#", "").strip()
                    and not line.strip().startswith(">")
                    and not line.strip().startswith("-")
                ),
                "",
            )
            or ""
        )

    def _scene_heat(self, scene: L2SceneRow) -> int:
        heat = scene.metadata.get("heat")
        return heat if isinstance(heat, int) else 0

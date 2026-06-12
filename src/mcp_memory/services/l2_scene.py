from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from mcp_memory.extractors import LLMRunner
from mcp_memory.models.base import get_china_time
from mcp_memory.prompts import build_l2_scene_prompt
from mcp_memory.schemas import L1MemoryForL2, L2SceneCreate, L2SceneRow

__all__ = ["L2SceneService", "SceneTarget"]


GENERATOR_VERSION = "l2_db_v1"
META_START = "-----META-START-----"
META_END = "-----META-END-----"


@dataclass(frozen=True)
class SceneTarget:
    filename: str
    scene_name: str
    existing: L2SceneRow | None = None


class L2SceneService:
    """Generate DB-native L2 scene blocks from L1 memories."""

    def __init__(self, *, llm_runner: LLMRunner, max_scenes: int = 15, timeout_ms: int = 180_000) -> None:
        self.llm_runner = llm_runner
        self.max_scenes = max_scenes
        self.timeout_ms = timeout_ms

    async def generate_scene(
        self,
        *,
        user_id: str,
        source_session_key: str,
        memories: list[L1MemoryForL2],
        existing_scenes: list[L2SceneRow],
    ) -> L2SceneCreate | None:
        if not memories:
            return None

        target = self.choose_scene_target(
            source_session_key=source_session_key,
            memories=memories,
            existing_scenes=existing_scenes,
        )
        now = get_china_time()
        now_iso = now.isoformat()
        system_prompt, user_prompt = build_l2_scene_prompt(
            target_filename=target.filename,
            existing_content=target.existing.content if target.existing else None,
            existing_scenes=existing_scenes,
            memories=memories,
            now_iso=now_iso,
            max_scenes=self.max_scenes,
        )
        raw = await self.llm_runner.run(
            prompt=user_prompt,
            system_prompt=system_prompt,
            task_id="scene-db-extract",
            timeout_ms=self.timeout_ms,
        )
        body = self.strip_markdown_fence(raw)
        if not body:
            return None

        summary = self._summary_from_memories(memories)
        created_at = target.existing.created_at if target.existing else now
        content = self.ensure_scene_markdown_body(
            body=body,
            created_at=created_at,
            updated_at=now,
            summary=summary,
            heat=self._next_heat(target.existing),
        )
        metadata = self._build_metadata(
            filename=target.filename,
            content=content,
            source_session_key=source_session_key,
            memories=memories,
            existing=target.existing,
        )
        return L2SceneCreate(
            memory_id=target.existing.memory_id if target.existing else self.resolve_scene_id(user_id, target.filename),
            user_id=user_id,
            filename=target.filename,
            scene_name=target.scene_name,
            content=content,
            source_conversation_id=memories[0].source_conversation_id,
            source_session_key=source_session_key,
            metadata=metadata,
            created_at=target.existing.created_at if target.existing else now,
            updated_at=now,
        )

    def choose_scene_target(
        self,
        *,
        source_session_key: str,
        memories: list[L1MemoryForL2],
        existing_scenes: list[L2SceneRow],
    ) -> SceneTarget:
        scene_name = next(
            (
                memory.scene_name.strip()
                for memory in memories
                if memory.scene_name.strip() and memory.scene_name.strip() not in {"default", "unknown"}
            ),
            source_session_key,
        )
        filename = self.safe_scene_filename(scene_name)
        exact = next((scene for scene in existing_scenes if scene.filename == filename), None)
        if exact is not None:
            return SceneTarget(filename=exact.filename, scene_name=exact.scene_name, existing=exact)
        if len(existing_scenes) == 1 or len(existing_scenes) >= self.max_scenes:
            existing = existing_scenes[0]
            return SceneTarget(filename=existing.filename, scene_name=existing.scene_name, existing=existing)
        return SceneTarget(filename=filename, scene_name=filename.removesuffix(".md"))

    def resolve_scene_id(self, user_id: str, filename: str) -> str:
        raw = "\x1f".join([user_id, "l2", filename])
        return f"l2_{sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    def safe_scene_filename(self, scene_name: str) -> str:
        normalized = scene_name.strip() or "scene"
        normalized = re.sub(r"\s+", "-", normalized)
        normalized = re.sub(r"[^0-9A-Za-z_\-.\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", "", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
        if not normalized:
            normalized = "scene"
        if not normalized.endswith(".md"):
            normalized = f"{normalized}.md"
        return normalized

    def strip_markdown_fence(self, raw: str) -> str:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def ensure_scene_markdown_body(
        self,
        *,
        body: str,
        created_at: datetime,
        updated_at: datetime,
        summary: str,
        heat: int,
    ) -> str:
        if META_START in body and META_END in body:
            return body.strip()
        meta = "\n".join(
            [
                META_START,
                f"created: {created_at.isoformat()}",
                f"updated: {updated_at.isoformat()}",
                f"summary: {summary}",
                f"heat: {heat}",
                META_END,
            ]
        )
        return f"{meta}\n\n{body.strip()}"

    def _build_metadata(
        self,
        *,
        filename: str,
        content: str,
        source_session_key: str,
        memories: list[L1MemoryForL2],
        existing: L2SceneRow | None,
    ) -> dict[str, object]:
        version = int((existing.metadata.get("version") if existing else 0) or 0) + 1
        return {
            "filename": filename,
            "summary": self._extract_meta_field(content, "summary") or self._summary_from_memories(memories),
            "heat": self._extract_heat(content),
            "version": version,
            "source_l1_ids": [memory.memory_id for memory in memories],
            "source_session_key": source_session_key,
            "latest_l1_updated_at": max(memory.updated_at for memory in memories).isoformat(),
            "generator_version": GENERATOR_VERSION,
        }

    def _summary_from_memories(self, memories: list[L1MemoryForL2]) -> str:
        text = memories[0].content.strip() if memories else "场景记忆"
        return text[:80]

    def _next_heat(self, existing: L2SceneRow | None) -> int:
        if existing is None:
            return 1
        heat = existing.metadata.get("heat")
        return int(heat) + 1 if isinstance(heat, int) else 2

    def _extract_heat(self, content: str) -> int:
        raw = self._extract_meta_field(content, "heat")
        try:
            return max(int(raw or "1"), 1)
        except ValueError:
            return 1

    def _extract_meta_field(self, content: str, field: str) -> str:
        match = re.search(rf"^{re.escape(field)}:\s*(.*)$", content, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

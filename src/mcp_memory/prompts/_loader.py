from pathlib import Path
from typing import ClassVar

__all__ = ["PromptLoader"]


class PromptLoader:
    """Load prompt text from Markdown files under the prompts directory."""

    BASE_DIR: ClassVar[Path] = Path(__file__).parent
    _cache: ClassVar[dict[str, str]] = {}

    @classmethod
    def load(cls, relative_path: str) -> str:
        if relative_path in cls._cache:
            return cls._cache[relative_path]

        file_path = cls.BASE_DIR / relative_path
        if not file_path.exists():
            raise FileNotFoundError(f"提示词文件不存在: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        cls._cache[relative_path] = content
        return content

    @classmethod
    def load_module(cls, module_name: str) -> str:
        return cls.load(f"modules/{module_name}.md")

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

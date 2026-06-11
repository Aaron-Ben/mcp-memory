"""Quality filters for L0 messages entering L1 extraction.

Applies content-quality rules to raw L0 messages before they are sent to
the LLM extraction step.  This avoids wasting LLM tokens on noise, very
short utterances, or prompt-injection-like payloads.
"""

from __future__ import annotations

import re

__all__ = ["should_extract_l1"]

# ---------------------------------------------------------------------------
# Pre-compiled patterns (module-level for reuse)
# ---------------------------------------------------------------------------

_FRAMEWORK_NOISE_PATTERN = re.compile(
    r"^\s*"
    r"(?:"
    r"\(session bootstrap\)"
    r"|A new session was started via /new or /reset"
    r"|New session started"
    r"|Pre-compaction memory flush"
    r"|NO_REPLY"
    r")\s*$",
    re.IGNORECASE,
)

_PURE_SYMBOLS_PATTERN = re.compile(
    r"^[^\w\s一-鿿぀-ヿ가-힯]{1,5}$"
)

_QUESTION_MARKS_ONLY_PATTERN = re.compile(r"^[?？]+$")

_PROMPT_INJECTION_PATTERN = re.compile(
    r"(?i)"
    r"(?:"
    # English injection patterns
    r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)"
    r"|you\s+are\s+now\b"
    r"|new\s+instructions?\s*:"
    r"|system\s*(?::|prompt)\b"
    r"|disregard\s+(?:all\s+)?(?:previous|above)\s+(?:instructions?|rules?)"
    r"|forget\s+(?:all\s+)?(?:previous|above)\s+(?:instructions?|rules?)"
    r"|\[/?system\]"
    r"|\beval\s*\("
    r"|prompt_injection"
    r"|jailbreak"
    # Chinese injection patterns
    r"|忽略(?:所有)?(?:之前的|上面的)?(?:指令|提示|规则)"
    r"|你现在是"
    r"|新指令\s*："
    r"|忘记(?:所有)?(?:之前的|上面的)?(?:指令|规则)"
    r")"
)

# Minimum meaningful content length (in characters).
# Messages shorter than this are very unlikely to carry extractable facts.
_MIN_CONTENT_LENGTH = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_extract_l1(text: str) -> bool:
    """Decide whether an L0 message is worth sending to the L1 extractor.

    This is the **strict** quality gate.  It is a superset of the L0 capture
    filter — in addition to structural checks, it also rejects content that
    is technically valid but carries no extractable information.

    Args:
        text: Raw L0 message content.

    Returns:
        True if the message should proceed to LLM extraction.
    """
    if not text or not text.strip():
        return False

    stripped = text.strip()

    # Reject slash commands (e.g. /new, /reset)
    if stripped.startswith("/"):
        return False

    # Reject framework noise emitted by the session management layer
    if _FRAMEWORK_NOISE_PATTERN.match(stripped):
        return False

    # Reject pure punctuation / symbols (e.g. "!", "...", "👋")
    if _PURE_SYMBOLS_PATTERN.match(stripped):
        return False

    # Reject question-marks-only strings (e.g. "?", "？？")
    if _QUESTION_MARKS_ONLY_PATTERN.match(stripped):
        return False

    # Reject obvious prompt-injection attempts
    if _PROMPT_INJECTION_PATTERN.search(stripped):
        return False

    # Reject very short content unlikely to carry facts
    if len(stripped) < _MIN_CONTENT_LENGTH:
        return False

    return True

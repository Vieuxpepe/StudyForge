"""
Remove scratchpad / chain-of-thought noise from automated audit model output.
"""

from __future__ import annotations

import re

# Line starts (after stripping list markers) that indicate scratchpad, not audit content.
_SCRATCHPAD_STARTS = (
    "wait,",
    "wait:",
    "wait ",
    "let me",
    "let's",
    "lets ",
    "self-correction",
    "self correction",
    "final plan",
    "final decision",
    "ready to output",
    "i should",
    "i will",
    "i'll ",
    "one more check",
    "double check",
    "re-reading",
    "re-reading",
    "reviewing the",
    "reviewing ",
    "intermediate auditor",
    "audit the local digest",
    "goal:",
    "output format:",
    "rules:",
    "check for:",
    "content:",
    "key data points:",
    "final check on",
    "the digest is flawless",
)

# Nested bullet scratchpad: "*   *Wait" etc.
_NESTED_BULLET_SCRATCHPAD = re.compile(
    r"^\s*[\*\-]\s+[\*\-]\s*(Wait|Self-Correction|Self Correction|Final|Let's|Let me|I should|I will|One more|Double check|Reviewing|Re-reading)",
    re.IGNORECASE,
)

_AUDIT_START = re.compile(
    r"^#+\s*Audit(?:\s+Report)?\s*(?:[—\-]|$)",
    re.IGNORECASE,
)

# Standalone scratchpad "Conclusion:" not inside a structured issue block
_SCRATCHPAD_CONCLUSION = re.compile(
    r"^conclusion:\s*(the digest|i will|ready|no major|overall|final)",
    re.IGNORECASE,
)

_PRESERVE_MARKERS = (
    "## audit",
    "### issue",
    "**original claim:**",
    "**verdict:**",
    "**corrected version:**",
    "**source support:**",
    "**why this matters:**",
    "no major issues found",
    "### minor improvements",
)


def _word_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def _normalize_line_for_check(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^[\*\-]\s+", "", text)
    text = re.sub(r"^[\*\-]\s+", "", text)
    text = re.sub(r"^\d+[\.\)]\s+", "", text)
    return text.strip().lower()


def _is_scratchpad_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    lower = _normalize_line_for_check(line)
    if not lower:
        return False

    if _NESTED_BULLET_SCRATCHPAD.match(stripped):
        return True

    for marker in _PRESERVE_MARKERS:
        if marker in lower:
            return False

    for start in _SCRATCHPAD_STARTS:
        if lower.startswith(start):
            return True

    if _SCRATCHPAD_CONCLUSION.match(lower):
        return True

    if lower.startswith("*") and any(
        phrase in lower
        for phrase in ("wait,", "let me", "let's", "self-correction", "final plan")
    ):
        return True

    return False


def _find_audit_start_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if _AUDIT_START.match(line.strip()):
            return index
    return 0


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                result.append("")
                blank = True
            continue
        result.append(line)
        blank = False
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def sanitize_audit_output(text: str) -> str:
    """
    Remove obvious scratchpad lines and keep structured audit report content.

    If a clean ``## Audit`` / ``## Audit Report`` section exists, content before it
    is dropped when safe.
    """
    cleaned, _stats = sanitize_audit_output_with_stats(text)
    return cleaned


def sanitize_audit_output_with_stats(text: str) -> tuple[str, dict]:
    """
    Sanitize audit text and return word/character removal statistics.
    """
    raw = text or ""
    raw_words = _word_count(raw)
    raw_chars = len(raw)

    lines = raw.splitlines()
    start = _find_audit_start_index(lines)
    lines = lines[start:]

    kept: list[str] = []
    for line in lines:
        if _is_scratchpad_line(line):
            continue
        kept.append(line.rstrip())

    kept = _collapse_blank_lines(kept)
    cleaned = "\n".join(kept)
    if cleaned:
        cleaned += "\n"

    cleaned_words = _word_count(cleaned)
    cleaned_chars = len(cleaned)

    return cleaned, {
        "raw_word_count": raw_words,
        "cleaned_word_count": cleaned_words,
        "sanitizer_removed_words": max(0, raw_words - cleaned_words),
        "sanitizer_removed_characters": max(0, raw_chars - cleaned_chars),
    }

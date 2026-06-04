"""
Shared helpers for required local digest Markdown sections.
"""

from __future__ import annotations

import re

DEFAULT_REQUIRED_SECTIONS = [
    "Big Picture",
    "Key Ideas",
    "Definitions",
    "Formulas / Rules / Methods",
    "Worked Examples from the Source",
    "Practice Questions",
    "Uncertain Claims",
    "Source References",
]


def check_required_sections(
    text: str, required_sections: list[str] | None = None
) -> dict:
    """
    Check which required Markdown sections appear in ``text``.

    Looks for headings like ``## Big Picture`` or ``# Big Picture``.

    Returns:
        {
            "required_sections": [...],
            "present": [...],
            "missing": [...],
        }
    """
    sections = required_sections or DEFAULT_REQUIRED_SECTIONS
    present: list[str] = []
    missing: list[str] = []

    for section in sections:
        pattern = re.compile(
            rf"^#{{1,2}}\s+{re.escape(section)}\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        if pattern.search(text):
            present.append(section)
        else:
            missing.append(section)

    return {
        "required_sections": list(sections),
        "present": present,
        "missing": missing,
    }


def digest_has_required_sections(text: str) -> bool:
    """True when all required ## sections appear in a chunk digest."""
    return not check_required_sections(text)["missing"]

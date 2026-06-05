"""
Streamlit sidebar navigation structure (UI-only).
"""

from __future__ import annotations

NAVIGATION_PAGES: tuple[dict[str, str], ...] = (
    {"group": "Today", "label": "Today", "key": "today"},
    {"group": "Build Study Material", "label": "Dashboard", "key": "dashboard"},
    {"group": "Build Study Material", "label": "Sources", "key": "sources"},
    {"group": "Build Study Material", "label": "Pipeline", "key": "pipeline"},
    {"group": "Build Study Material", "label": "Audits", "key": "audits"},
    {"group": "Build Study Material", "label": "Study Units", "key": "study_units"},
    {"group": "Study / Review", "label": "Study Session", "key": "study_session"},
    {"group": "Study / Review", "label": "Active Recall", "key": "active_recall"},
    {"group": "Study / Review", "label": "Flashcards", "key": "flashcards"},
    {"group": "Study / Review", "label": "Mock Tests", "key": "mock_tests"},
    {"group": "Study / Review", "label": "Exam Prep", "key": "exam_prep"},
    {"group": "Study / Review", "label": "Review Tracker", "key": "review_tracker"},
    {"group": "Quality / Trust", "label": "Course Quality", "key": "course_quality"},
    {"group": "Quality / Trust", "label": "Evidence Trace", "key": "evidence_trace"},
    {"group": "Course Tools", "label": "Courses", "key": "courses"},
    {"group": "Settings", "label": "Settings", "key": "settings"},
)

PAGE_DESCRIPTIONS: dict[str, str] = {
    "today": "What should I review right now?",
    "dashboard": "Source pipeline overview for the selected course.",
    "sources": "Register PDF source files for the selected course.",
    "pipeline": (
        "Build study material from source files: extract, chunk, digest, audit, "
        "and generate study packs."
    ),
    "audits": "Export/import intermediate and final audits.",
    "study_units": "Group related sources into a topic, chapter, or exam target.",
    "study_session": (
        "Work through review items, active recall questions, flashcards, "
        "mistakes, and weak points."
    ),
    "active_recall": "Practice active recall questions with self-grading (no AI).",
    "flashcards": "Review flashcards with lightweight due scheduling (no AI).",
    "mock_tests": "Generate practice tests from study packs and record self-graded scores.",
    "exam_prep": "Define exam targets and generate deterministic prep plans.",
    "review_tracker": "Track mistakes, weak points, and daily review plans.",
    "course_quality": "Check whether sources are trustworthy and ready to study.",
    "evidence_trace": "Inspect source chunks, digests, and audits side by side.",
    "courses": "Create courses and back up/verify course data.",
    "settings": "Project paths and basic configuration.",
}

WHERE_TO_GO_HELP = """## Where should I go?

- Need to process a PDF? Go to **Pipeline**.
- Need to study now? Start **Study Session**.
- Need to check if a source is trustworthy? Go to **Course Quality**.
- Need to inspect evidence? Go to **Evidence Trace**.
- Need to back up your data? Go to **Courses**.
"""


def get_navigation_pages() -> list[dict[str, str]]:
    """Return ordered navigation page definitions."""
    return [dict(page) for page in NAVIGATION_PAGES]


def flatten_navigation_pages() -> list[str]:
    """Return sidebar selectbox labels in navigation order."""
    return [format_navigation_option(page) for page in NAVIGATION_PAGES]


def format_navigation_option(page: dict[str, str]) -> str:
    """Build a grouped sidebar label such as ``Build Study Material · Pipeline``."""
    group = page.get("group", "")
    label = page.get("label", "")
    if group and group != label:
        return f"{group} · {label}"
    return label


def get_page_by_key(page_key: str) -> dict[str, str] | None:
    """Return navigation metadata for a page key."""
    normalized = page_key.strip().lower()
    for page in NAVIGATION_PAGES:
        if page["key"] == normalized:
            return dict(page)
    return None


def get_page_description(page_key: str) -> str:
    """Return the short page role description."""
    return PAGE_DESCRIPTIONS.get(page_key.strip().lower(), "")


def navigation_keys() -> list[str]:
    """Return page keys in sidebar order."""
    return [page["key"] for page in NAVIGATION_PAGES]


def option_to_page_key(option_label: str) -> str | None:
    """Map a flattened sidebar option label back to a page key."""
    for page in NAVIGATION_PAGES:
        if format_navigation_option(page) == option_label:
            return page["key"]
    return None

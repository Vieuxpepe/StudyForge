"""
Study Unit Dashboard v1 — aggregate readiness and review data for a unit (no AI).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from studyforge.core.pipeline_status import get_pipeline_status
from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.flashcard_review import collect_due_flashcards
from studyforge.study.flashcards import get_flashcard_output_paths
from studyforge.study.review_planner import (
    collect_active_recall_needs_review,
    collect_open_mistakes,
    collect_open_weak_points,
    prioritize_review_items,
)
from studyforge.study.review_schedule import today_date_str
from studyforge.study.study_units import (
    StudyUnitNotFoundError,
    _normalize_source_id,
    _normalize_unit_id,
    _source_has_study_activity,
    get_study_unit_summary,
    load_study_units,
)
from studyforge.study.unit_study_pack import (
    load_unit_study_pack_quality,
    unit_has_study_pack,
)
from studyforge.study.unit_review import (
    collect_due_unit_flashcards_for_unit,
    collect_unit_active_recall_needs_review_for_unit,
    collect_unanswered_unit_active_recall,
    collect_unreviewed_unit_flashcards,
)
from studyforge.study.unit_synthesis_import import (
    get_latest_synthesis_quality,
    unit_has_synthesis,
)

APP_DATA_DIR = Path("08_App_Data")
REPORTS_DIR = APP_DATA_DIR / "reports" / "study_units"
MY_WORK_DIR = Path("07_My_Work")
REVIEW_SESSIONS_DIR = "review_sessions"
STUDY_OUTPUTS_BASE = Path("06_Study_Outputs")


class UnitReviewPlanExistsError(Exception):
    """Raised when a unit review plan exists and overwrite was not requested."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _local_today_str() -> str:
    return date.today().isoformat()


def _normalize_unit_id(unit_id: str) -> str:
    return unit_id.strip().upper()


def _filter_by_source_ids(items: list[dict], source_ids: set[str]) -> list[dict]:
    """Keep items whose source_id is in the unit."""
    filtered: list[dict] = []
    for item in items:
        sid = _normalize_source_id(str(item.get("source_id", "")))
        if sid in source_ids:
            filtered.append(item)
    return filtered


def _load_unit_pack_synthesis_id(manifest_path: str | Path) -> str:
    """Return ``based_on_unit_synthesis_id`` from a unit study pack manifest."""
    path = Path(manifest_path)
    if not path.is_file():
        return ""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = str(manifest.get("based_on_unit_synthesis_id", "")).strip()
    return value


def get_unit_reports_dir(course_path: Path) -> Path:
    """Return ``08_App_Data/reports/study_units/``."""
    path = course_path / REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_unit_dashboard_paths(course_path: Path, unit_id: str) -> tuple[Path, Path]:
    """Return Markdown and JSON paths for a unit dashboard export."""
    normalized = _normalize_unit_id(unit_id)
    report_dir = get_unit_reports_dir(course_path)
    return (
        report_dir / f"{normalized}_unit_dashboard.md",
        report_dir / f"{normalized}_unit_dashboard.json",
    )


def get_unit_review_plan_path(
    course_path: Path, unit_id: str, date_str: str | None = None
) -> Path:
    """Return Markdown path for a unit-specific review plan."""
    day = date_str or _local_today_str()
    normalized = _normalize_unit_id(unit_id)
    sessions_dir = course_path / MY_WORK_DIR / REVIEW_SESSIONS_DIR
    return sessions_dir / f"{normalized}_{day}_review_plan.md"


def get_unit_review_plan_json_path(
    course_path: Path, unit_id: str, date_str: str | None = None
) -> Path:
    """Return JSON path for a unit-specific review plan."""
    day = date_str or _local_today_str()
    normalized = _normalize_unit_id(unit_id)
    sessions_dir = course_path / MY_WORK_DIR / REVIEW_SESSIONS_DIR
    return sessions_dir / f"{normalized}_{day}_review_plan.json"


def get_unit_source_ids(
    course_name: str, unit_id: str, root: Path | None = None
) -> list[str]:
    """Load a study unit and return its normalized source IDs."""
    data = load_study_units(course_name, root)
    target = _normalize_unit_id(unit_id)
    for unit in data.get("units", []):
        if _normalize_unit_id(str(unit.get("unit_id", ""))) == target:
            return [
                _normalize_source_id(str(sid))
                for sid in unit.get("source_ids", [])
            ]
    raise StudyUnitNotFoundError(f"Study unit not found: {unit_id}")


def _resolve_source_output_paths(
    course_path: Path, source_id: str
) -> dict[str, str | None]:
    """Return study output file paths when they exist on disk."""
    normalized = _normalize_source_id(source_id)
    guide = (
        course_path
        / STUDY_OUTPUTS_BASE
        / "study_guides"
        / f"{normalized}_final_study_guide.md"
    )
    recall = (
        course_path
        / STUDY_OUTPUTS_BASE
        / "active_recall"
        / f"{normalized}_active_recall.md"
    )
    flashcards = get_flashcard_output_paths(course_path, normalized)["markdown"]
    return {
        "final_study_guide_path": str(guide.resolve()) if guide.is_file() else None,
        "flashcards_path": (
            str(flashcards.resolve()) if flashcards.is_file() else None
        ),
        "active_recall_path": str(recall.resolve()) if recall.is_file() else None,
    }


def _source_recommended_action(
    course_name: str,
    source_id: str,
    has_study_pack: bool,
    root: Path | None,
) -> str:
    if has_study_pack:
        return "ready"
    try:
        pipeline = get_pipeline_status(course_name, source_id, root)
        return str(pipeline.get("next_action", {}).get("key", "process_source"))
    except Exception:
        return "process_source"


def _unit_has_activity(
    course_path: Path,
    source_ids: set[str],
    registry: dict[str, dict],
) -> bool:
    for sid in source_ids:
        entry = registry.get(sid)
        if entry and _source_has_study_activity(course_path, sid):
            return True
    return False


def _build_dashboard_recommended_action(
    *,
    source_count: int,
    incomplete_count: int,
    review_summary: dict,
    has_activity: bool,
    has_unit_synthesis: bool,
    has_unit_study_pack: bool,
    stale_unit_study_pack: bool,
    unit_pack_quality: str,
) -> dict[str, str]:
    if source_count == 0:
        return {
            "key": "add_sources",
            "label": "Add sources to this unit",
            "reason": "This unit has no sources yet.",
        }
    if incomplete_count > 0:
        noun = "source" if incomplete_count == 1 else "sources"
        return {
            "key": "process_incomplete_sources",
            "label": "Process incomplete sources",
            "reason": (
                f"{incomplete_count} {noun} "
                f"{'does' if incomplete_count == 1 else 'do'} not have a study pack yet."
            ),
        }

    review_total = (
        review_summary.get("due_flashcards", 0)
        + review_summary.get("active_recall_needs_review", 0)
        + review_summary.get("open_mistakes", 0)
        + review_summary.get("open_weak_points", 0)
    )

    if not has_unit_synthesis and incomplete_count == 0:
        return {
            "key": "export_or_import_unit_synthesis",
            "label": "Create unit synthesis",
            "reason": (
                "All sources are ready; export a synthesis packet and import "
                "the unified unit guide."
            ),
        }

    if has_unit_synthesis and not has_unit_study_pack:
        return {
            "key": "generate_unit_study_pack",
            "label": "Generate unit study pack",
            "reason": (
                "A unit synthesis exists but no unit study pack has been generated."
            ),
        }

    if stale_unit_study_pack:
        return {
            "key": "generate_unit_study_pack",
            "label": "Regenerate unit study pack",
            "reason": (
                "A newer unit synthesis exists than the one used for the current "
                "unit study pack."
            ),
        }

    if has_unit_study_pack and unit_pack_quality in {"needs_review", "failed"}:
        return {
            "key": "inspect_unit_study_pack",
            "label": "Inspect unit study pack",
            "reason": "Unit study pack quality needs review.",
        }

    if has_unit_synthesis and review_total > 0:
        return {
            "key": "generate_unit_review_plan",
            "label": "Generate unit review plan",
            "reason": (
                "This unit has due flashcards, recall gaps, mistakes, "
                "or weak points to review."
            ),
        }

    if has_unit_synthesis and review_total == 0:
        if not has_activity:
            return {
                "key": "start_unit_study_session",
                "label": "Start unit study session",
                "reason": (
                    "Unit synthesis is imported; start practicing with a "
                    "unit-focused study session."
                ),
            }
        return {
            "key": "unit_ready",
            "label": "Unit ready",
            "reason": "Unit synthesis is in place and no urgent review items are waiting.",
        }

    if review_total > 0:
        return {
            "key": "generate_unit_review_plan",
            "label": "Generate unit review plan",
            "reason": (
                "This unit has due flashcards, recall gaps, mistakes, "
                "or weak points to review."
            ),
        }
    if not has_activity:
        return {
            "key": "start_unit_study_session",
            "label": "Start unit study session",
            "reason": (
                "All sources have study packs but no study activity yet "
                "for this unit."
            ),
        }
    return {
        "key": "unit_ready",
        "label": "Unit ready",
        "reason": "Sources are ready and no urgent review items are waiting.",
    }


def get_study_unit_dashboard(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Build a full dashboard dict for one study unit."""
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    source_id_list = get_unit_source_ids(course_name, unit_id, root)
    source_id_set = set(source_id_list)

    registry = {
        _normalize_source_id(str(entry.get("id", ""))): entry
        for entry in list_sources(course_name, root)
        if entry.get("id")
    }

    day = today_date_str()
    mistakes = _filter_by_source_ids(
        collect_open_mistakes(course_name, root), source_id_set
    )
    weak_points = _filter_by_source_ids(
        collect_open_weak_points(course_name, root), source_id_set
    )
    recall_items = _filter_by_source_ids(
        collect_active_recall_needs_review(course_name, root), source_id_set
    )
    due_flashcards = _filter_by_source_ids(
        collect_due_flashcards(course_name, root, today=day), source_id_set
    )

    review_summary = {
        "due_flashcards": len(due_flashcards),
        "active_recall_needs_review": len(recall_items),
        "open_mistakes": len(mistakes),
        "open_weak_points": len(weak_points),
    }

    sources: list[dict] = []
    for raw in summary.get("sources") or []:
        sid = _normalize_source_id(str(raw.get("source_id", "")))
        entry = registry.get(sid, {})
        has_pack = bool(raw.get("has_study_pack"))
        output_paths = _resolve_source_output_paths(course_path, sid)
        sources.append(
            {
                "source_id": sid,
                "title": raw.get("title", sid),
                "status": raw.get("status", "unknown"),
                "has_study_pack": has_pack,
                "final_study_guide_path": output_paths["final_study_guide_path"],
                "flashcards_path": output_paths["flashcards_path"],
                "active_recall_path": output_paths["active_recall_path"],
                "recommended_action": _source_recommended_action(
                    course_name, sid, has_pack, root
                ),
            }
        )

    has_activity = _unit_has_activity(course_path, source_id_set, registry)

    units_data = load_study_units(course_name, root)
    unit_entry = next(
        (
            u
            for u in units_data.get("units", [])
            if _normalize_unit_id(str(u.get("unit_id", "")))
            == _normalize_unit_id(unit_id)
        ),
        {},
    )
    latest_synthesis_id = str(unit_entry.get("latest_synthesis_id", ""))
    latest_synthesis_path = str(unit_entry.get("latest_synthesis_path", ""))
    has_synthesis = unit_has_synthesis(unit_entry, course_path)
    latest_synthesis_quality = ""
    if has_synthesis and latest_synthesis_id:
        latest_synthesis_quality = get_latest_synthesis_quality(
            course_path, unit_id, latest_synthesis_id
        )

    has_pack = unit_has_study_pack(unit_entry)
    manifest_path = str(unit_entry.get("latest_unit_study_pack_manifest_path", ""))
    pack_quality = ""
    manifest_synthesis_id = ""
    if has_pack and manifest_path:
        pack_quality = load_unit_study_pack_quality(manifest_path)
        manifest_synthesis_id = _load_unit_pack_synthesis_id(manifest_path)

    stale_unit_study_pack = bool(
        has_pack
        and latest_synthesis_id
        and manifest_synthesis_id
        and manifest_synthesis_id != latest_synthesis_id
    )

    recommended_action = _build_dashboard_recommended_action(
        source_count=summary.get("source_count", 0),
        incomplete_count=summary.get("incomplete_sources", 0),
        review_summary=review_summary,
        has_activity=has_activity,
        has_unit_synthesis=has_synthesis,
        has_unit_study_pack=has_pack,
        stale_unit_study_pack=stale_unit_study_pack,
        unit_pack_quality=pack_quality,
    )

    warnings = list(summary.get("warnings") or [])
    if stale_unit_study_pack:
        warnings.append(
            "Unit study pack may be stale: generated from "
            f"{manifest_synthesis_id}, but latest unit synthesis is "
            f"{latest_synthesis_id}. Regenerate the unit study pack."
        )

    return {
        "course": course_path.name,
        "unit_id": summary.get("unit_id", ""),
        "title": summary.get("title", ""),
        "description": summary.get("description", ""),
        "status": summary.get("status", "active"),
        "tags": list(summary.get("tags", [])),
        "source_count": summary.get("source_count", 0),
        "ready_sources": summary.get("ready_sources", 0),
        "incomplete_sources": summary.get("incomplete_sources", 0),
        "sources": sources,
        "review_summary": review_summary,
        "recommended_action": recommended_action,
        "warnings": warnings,
        "latest_synthesis_id": latest_synthesis_id,
        "latest_synthesis_path": latest_synthesis_path,
        "latest_synthesis_quality": latest_synthesis_quality,
        "has_unit_synthesis": has_synthesis,
        "has_unit_study_pack": has_pack,
        "latest_unit_study_pack_quality": pack_quality,
        "latest_unit_study_pack_manifest_path": manifest_path,
        "based_on_unit_study_pack_synthesis_id": manifest_synthesis_id,
        "stale_unit_study_pack": stale_unit_study_pack,
        "latest_unit_study_guide_path": str(
            unit_entry.get("latest_unit_study_guide_path", "")
        ),
        "latest_unit_flashcards_path": str(
            unit_entry.get("latest_unit_flashcards_path", "")
        ),
        "latest_unit_active_recall_path": str(
            unit_entry.get("latest_unit_active_recall_path", "")
        ),
        "based_on_unit_synthesis_id": latest_synthesis_id,
    }


def build_unit_dashboard_markdown(dashboard: dict) -> str:
    """Render a study unit dashboard as Markdown."""
    lines = [
        f"# Study Unit Dashboard — {dashboard.get('unit_id', '')}",
        "",
        "Course:",
        dashboard.get("course", ""),
        "",
        "Unit:",
        dashboard.get("title", ""),
        "",
        "Status:",
        dashboard.get("status", ""),
        "",
        f"Description: {dashboard.get('description') or '(none)'}",
        "",
        "## Source Readiness",
        "",
        "| Source | Title | Status | Study pack | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]

    for source in dashboard.get("sources") or []:
        pack = "yes" if source.get("has_study_pack") else "no"
        title = str(source.get("title", "")).replace("|", "\\|")
        lines.append(
            f"| {source.get('source_id', '')} | {title} | "
            f"{source.get('status', '')} | {pack} | "
            f"{source.get('recommended_action', '')} |"
        )

    review = dashboard.get("review_summary") or {}
    lines.extend(
        [
            "",
            "## Review Summary",
            "",
            f"- Due flashcards: {review.get('due_flashcards', 0)}",
            f"- Active recall needing review: {review.get('active_recall_needs_review', 0)}",
            f"- Open mistakes: {review.get('open_mistakes', 0)}",
            f"- Open weak points: {review.get('open_weak_points', 0)}",
            "",
            "## Unit Synthesis",
            "",
            f"- Has synthesis: {'yes' if dashboard.get('has_unit_synthesis') else 'no'}",
        ]
    )
    if dashboard.get("latest_synthesis_id"):
        lines.append(f"- Latest synthesis ID: {dashboard.get('latest_synthesis_id', '')}")
        if dashboard.get("latest_synthesis_quality"):
            lines.append(
                f"- Quality: {dashboard.get('latest_synthesis_quality', '')}"
            )
        if dashboard.get("latest_synthesis_path"):
            lines.append(
                f"- Path: `{dashboard.get('latest_synthesis_path', '')}`"
            )
    lines.extend(
        [
            f"- Has unit study pack: {'yes' if dashboard.get('has_unit_study_pack') else 'no'}",
        ]
    )
    if dashboard.get("has_unit_study_pack"):
        if dashboard.get("latest_unit_study_pack_quality"):
            lines.append(
                f"- Unit pack quality: {dashboard.get('latest_unit_study_pack_quality', '')}"
            )
        if dashboard.get("latest_unit_study_pack_manifest_path"):
            lines.append(
                f"- Manifest: `{dashboard.get('latest_unit_study_pack_manifest_path', '')}`"
            )
    lines.extend(["", "## Recommended Action", ""])
    action = dashboard.get("recommended_action") or {}
    lines.append(f"- **{action.get('label', '')}** — {action.get('reason', '')}")
    lines.extend(["", "## Source Output Paths", ""])

    for source in dashboard.get("sources") or []:
        lines.append(f"### {source.get('source_id', '')} — {source.get('title', '')}")
        guide = source.get("final_study_guide_path")
        flashcards = source.get("flashcards_path")
        recall = source.get("active_recall_path")
        if guide:
            lines.append(f"- Final study guide: `{guide}`")
        if flashcards:
            lines.append(f"- Flashcards: `{flashcards}`")
        if recall:
            lines.append(f"- Active recall: `{recall}`")
        if not guide and not flashcards and not recall:
            lines.append("- No study pack outputs yet.")
        lines.append("")

    lines.extend(["## Warnings", ""])
    warnings = dashboard.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def export_unit_dashboard(
    course_name: str, unit_id: str, root: Path | None = None
) -> dict:
    """Write unit dashboard Markdown and JSON; return paths."""
    course_path = resolve_course_path(course_name, root)
    dashboard = get_study_unit_dashboard(course_name, unit_id, root)
    md_path, json_path = get_unit_dashboard_paths(course_path, unit_id)

    md_path.write_text(build_unit_dashboard_markdown(dashboard), encoding="utf-8")
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(dashboard, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return {
        "unit_id": dashboard.get("unit_id", ""),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "dashboard": dashboard,
    }


def build_unit_review_plan_markdown(
    *,
    course_name: str,
    unit_id: str,
    unit_title: str,
    source_ids: list[str],
    mistakes: list[dict],
    weak_points: list[dict],
    recall_items: list[dict],
    flashcard_items: list[dict],
    priority_items: list[dict],
    unit_recall_items: list[dict] | None = None,
    unit_flashcard_items: list[dict] | None = None,
    unit_new_practice_items: list[dict] | None = None,
    date_str: str,
) -> str:
    """Build Markdown for a unit-specific review plan."""
    generated = _now_iso()
    lines = [
        f"# Study Unit Review Plan — {unit_id} — {date_str}",
        "",
        "Course:",
        course_name,
        "",
        "Unit:",
        unit_title,
        "",
        "Sources:",
        ", ".join(source_ids) if source_ids else "(none)",
        "",
        "Generated:",
        generated,
        "",
        "---",
        "",
        "## Today's Top Priorities",
        "",
    ]

    if priority_items:
        for index, item in enumerate(priority_items, start=1):
            lines.append(f"{index}. **{item.get('type', '')}** — `{item.get('id', '')}`")
            lines.append(f"   - Source: {item.get('source_id', '')}")
            lines.append(f"   - Title: {item.get('title', '')}")
            lines.append(f"   - Reason: {item.get('priority_reason', '')}")
            if item.get("details"):
                lines.append(f"   - Details: {item.get('details', '')}")
            lines.append("")
    else:
        lines.append("No priority items for this unit today.")
        lines.append("")

    lines.extend(["---", "", "## Open Mistakes", ""])
    if mistakes:
        for entry in mistakes:
            lines.extend(
                [
                    f"### {entry.get('mistake_id', 'MISTAKE')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Status:** {entry.get('status', 'new')}",
                    "",
                ]
            )
    else:
        lines.append("No open mistakes for this unit.")
        lines.append("")

    lines.extend(["## Weak Points", ""])
    if weak_points:
        for entry in weak_points:
            lines.extend(
                [
                    f"### {entry.get('weak_point_id', 'WEAK')} — {entry.get('concept', '')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Confidence:** {entry.get('confidence_level', '')}",
                    "",
                ]
            )
    else:
        lines.append("No open weak points for this unit.")
        lines.append("")

    unit_recall_items = unit_recall_items or []
    unit_flashcard_items = unit_flashcard_items or []
    unit_new_practice_items = unit_new_practice_items or []

    lines.extend(["## Unit Active Recall", ""])
    if unit_recall_items:
        for entry in unit_recall_items:
            lines.extend(
                [
                    f"### {entry.get('question_id', 'question')}",
                    "",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Last grade:** {entry.get('grade', '')}",
                    "",
                ]
            )
    else:
        lines.append("No unit active recall items needing review.")
        lines.append("")

    lines.extend(["## Unit Flashcards Due", ""])
    if unit_flashcard_items:
        for entry in unit_flashcard_items:
            lines.extend(
                [
                    f"### {entry.get('card_id', 'card')}",
                    "",
                    f"- **Front:** {entry.get('front', '')}",
                    f"- **Due date:** {entry.get('due_date', '')}",
                    "",
                ]
            )
    else:
        lines.append("No unit flashcards due.")
        lines.append("")

    lines.extend(["## Unit-Level New Practice", ""])
    if unit_new_practice_items:
        for entry in unit_new_practice_items:
            item_type = str(entry.get("type", ""))
            if item_type == "unit_active_recall_unanswered":
                lines.extend(
                    [
                        f"### {entry.get('question_id', 'question')}",
                        "",
                        f"- **Question:** {entry.get('question', '')}",
                        "",
                    ]
                )
            elif item_type == "unit_flashcard_unreviewed":
                lines.extend(
                    [
                        f"### {entry.get('card_id', 'card')}",
                        "",
                        f"- **Front:** {entry.get('front', '')}",
                        "",
                    ]
                )
    else:
        lines.append("No new unit-level practice items.")
        lines.append("")

    lines.extend(["## Active Recall Redo", ""])
    if recall_items:
        for entry in recall_items:
            lines.extend(
                [
                    f"### {entry.get('question_id', 'question')}",
                    "",
                    f"- **Question:** {entry.get('question', '')}",
                    f"- **Last grade:** {entry.get('grade', '')}",
                    "",
                ]
            )
    else:
        lines.append("No active recall redo items for this unit.")
        lines.append("")

    lines.extend(["## Flashcards Due", ""])
    if flashcard_items:
        for entry in flashcard_items:
            lines.extend(
                [
                    f"### {entry.get('card_id', 'card')}",
                    "",
                    f"- **Source:** {entry.get('source_id', '')}",
                    f"- **Front:** {entry.get('front', '')}",
                    f"- **Due date:** {entry.get('due_date', '')}",
                    "",
                ]
            )
    else:
        lines.append("No flashcards due for this unit.")
        lines.append("")

    return "\n".join(lines)


def generate_unit_review_plan(
    course_name: str,
    unit_id: str,
    limit: int = 10,
    overwrite: bool = False,
    root: Path | None = None,
) -> dict:
    """
    Collect unit-filtered review items and write unit-specific plan files.

    Does not replace the course-wide daily review plan.
    """
    course_path = resolve_course_path(course_name, root)
    summary = get_study_unit_summary(course_name, unit_id, root)
    source_ids = get_unit_source_ids(course_name, unit_id, root)
    source_id_set = set(source_ids)
    day = _local_today_str()

    md_path = get_unit_review_plan_path(course_path, unit_id, day)
    json_path = get_unit_review_plan_json_path(course_path, unit_id, day)

    if (md_path.is_file() or json_path.is_file()) and not overwrite:
        raise UnitReviewPlanExistsError(
            f"Unit review plan already exists for {unit_id} on {day}:\n"
            f"  - {md_path}\n"
            f"  - {json_path}\n"
            "Use --overwrite to replace."
        )

    mistakes = _filter_by_source_ids(
        collect_open_mistakes(course_name, root), source_id_set
    )
    weak_points = _filter_by_source_ids(
        collect_open_weak_points(course_name, root), source_id_set
    )
    recall_items = _filter_by_source_ids(
        collect_active_recall_needs_review(course_name, root), source_id_set
    )
    flashcard_items = _filter_by_source_ids(
        collect_due_flashcards(course_name, root, today=day), source_id_set
    )
    normalized_unit = _normalize_unit_id(unit_id)
    unit_recall_items = collect_unit_active_recall_needs_review_for_unit(
        course_name, normalized_unit, root
    )
    unit_flashcard_items = collect_due_unit_flashcards_for_unit(
        course_name, normalized_unit, root, today=day
    )
    has_unit_review_items = bool(unit_recall_items or unit_flashcard_items)
    unit_new_practice_items: list[dict] = []
    if not has_unit_review_items:
        unit_new_practice_items = (
            collect_unanswered_unit_active_recall(
                course_name, normalized_unit, root
            )
            + collect_unreviewed_unit_flashcards(
                course_name, normalized_unit, root
            )
        )
    priority_items = prioritize_review_items(
        mistakes,
        weak_points,
        recall_items,
        flashcard_items,
        limit=limit,
    )

    markdown = build_unit_review_plan_markdown(
        course_name=course_path.name,
        unit_id=normalized_unit,
        unit_title=summary.get("title", ""),
        source_ids=source_ids,
        mistakes=mistakes,
        weak_points=weak_points,
        recall_items=recall_items,
        flashcard_items=flashcard_items,
        priority_items=priority_items,
        unit_recall_items=unit_recall_items,
        unit_flashcard_items=unit_flashcard_items,
        unit_new_practice_items=unit_new_practice_items,
        date_str=day,
    )

    sessions_dir = course_path / MY_WORK_DIR / REVIEW_SESSIONS_DIR
    sessions_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")

    generated = _now_iso()
    result = {
        "course": course_path.name,
        "unit_id": _normalize_unit_id(unit_id),
        "unit_title": summary.get("title", ""),
        "date": day,
        "source_ids": source_ids,
        "mistake_count": len(mistakes),
        "weak_point_count": len(weak_points),
        "active_recall_review_count": len(recall_items),
        "flashcards_due_count": len(flashcard_items),
        "unit_active_recall_review_count": len(unit_recall_items),
        "unit_flashcards_due_count": len(unit_flashcard_items),
        "unit_new_practice_count": len(unit_new_practice_items),
        "priority_count": len(priority_items),
        "markdown_path": str(md_path.resolve()),
        "json_path": str(json_path.resolve()),
        "generated": generated,
    }

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return result

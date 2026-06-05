"""
Course Quality Report v1 — trust/readiness summary across all sources (no AI).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from studyforge.core.chunking_jobs import get_chunk_manifest_path
from studyforge.core.digest_jobs import get_local_digest_dir
from studyforge.core.pipeline_status import get_pipeline_status
from studyforge.core.sources import list_sources, resolve_course_path
from studyforge.study.active_recall import (
    get_active_recall_log_path,
    load_active_recall_log,
)
from studyforge.study.flashcard_review import (
    collect_due_flashcards,
    get_flashcard_review_log_path,
    load_flashcard_review_log,
)
from studyforge.study.mistakes import get_mistakes_log_path, load_mistakes_log
from studyforge.study.review_planner import collect_active_recall_needs_review
from studyforge.study.review_schedule import today_date_str
from studyforge.study.study_units import list_study_units
from studyforge.study.weak_points import get_weak_points_path, load_weak_points

APP_DATA_DIR = Path("08_App_Data")
REPORTS_DIR = APP_DATA_DIR / "reports"
COURSE_QUALITY_JSON = "course_quality_report.json"
COURSE_QUALITY_MD = "course_quality_report.md"

Score = str  # ok | needs_review | failed | missing | none

_ACTION_PRIORITY = (
    "fix_source",
    "extract_pdf",
    "inspect_extraction",
    "chunk_source",
    "run_local_digest",
    "review_local_digest",
    "inspect_digest",
    "export_or_run_intermediate_audit",
    "export_final_audit_packet",
    "generate_study_pack",
    "normalize_final_audit",
    "start_study",
    "review_study_items",
    "ready",
)

_ACTION_LABELS: dict[str, str] = {
    "fix_source": "Fix or re-register source file",
    "extract_pdf": "Extract PDF",
    "inspect_extraction": "Inspect extraction quality report",
    "chunk_source": "Chunk source",
    "run_local_digest": "Run local digest",
    "review_local_digest": "Review local digest",
    "inspect_digest": "Inspect digest review report",
    "export_or_run_intermediate_audit": "Run or import intermediate audit",
    "export_final_audit_packet": "Export or import final audit",
    "generate_study_pack": "Generate study pack",
    "normalize_final_audit": "Normalize final audit or regenerate study pack",
    "start_study": "Start active recall / flashcards",
    "review_study_items": "Review mistakes, weak points, or due flashcards",
    "ready": "Ready to study",
}


def _today() -> str:
    return today_date_str()


def _file_exists(path_str: str | None) -> bool:
    if not path_str:
        return False
    return Path(path_str).is_file()


def _normalize_source_id(source_id: str) -> str:
    return source_id.strip().upper()


def get_course_quality_report_dir(course_path: Path) -> Path:
    """Return ``08_App_Data/reports/`` for a course."""
    path = course_path / REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_course_quality_report_paths(course_path: Path) -> tuple[Path, Path]:
    report_dir = get_course_quality_report_dir(course_path)
    return report_dir / COURSE_QUALITY_JSON, report_dir / COURSE_QUALITY_MD


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _score_extraction(entry: dict) -> Score:
    extracted_path = entry.get("extracted_text_path", "")
    if not _file_exists(extracted_path):
        return "missing"
    status = str(entry.get("extraction_quality_status", "")).lower()
    if status == "failed":
        return "failed"
    if status == "needs_review":
        return "needs_review"
    if status == "ok":
        return "ok"
    return "needs_review"


def _score_local_digest(entry: dict, course_path: Path, source_id: str) -> Score:
    normalized = _normalize_source_id(source_id)
    combined = Path(entry.get("local_digest_path", ""))
    if not combined.is_file():
        digest_dir = get_local_digest_dir(course_path, normalized)
        combined = digest_dir / f"{normalized}_combined_local_digest.md"
    if not combined.is_file():
        return "missing"

    review_json = get_local_digest_dir(course_path, normalized) / (
        f"{normalized}_local_digest_review.json"
    )
    review = _load_json(review_json)
    if not review:
        return "missing"
    overall = str(review.get("overall_status", "missing")).lower()
    if overall in {"ok", "needs_review", "failed"}:
        return overall
    return "needs_review"


def _score_intermediate_audit(entry: dict) -> Score:
    if _file_exists(entry.get("latest_intermediate_audit_path", "")):
        return "ok"
    return "missing"


def _score_final_audit(entry: dict) -> Score:
    if _file_exists(entry.get("latest_final_audit_path", "")):
        return "ok"
    return "missing"


def _score_study_pack(entry: dict, course_path: Path, source_id: str) -> Score:
    normalized = _normalize_source_id(source_id)
    manifest_path = Path(entry.get("study_pack_manifest_path", ""))
    if not manifest_path.is_file():
        default = course_path / "06_Study_Outputs" / f"{normalized}_study_pack_manifest.json"
        manifest_path = default if default.is_file() else manifest_path
    if not manifest_path.is_file():
        return "missing"

    manifest = _load_json(manifest_path)
    if not manifest:
        return "needs_review"
    quality = manifest.get("quality") or {}
    status = str(quality.get("quality_status", "")).lower()
    if status in {"ok", "needs_review", "failed"}:
        return status
    return "ok"


def _open_mistakes_for_source(course_path: Path, source_id: str) -> list[dict]:
    log = load_mistakes_log(get_mistakes_log_path(course_path))
    normalized = _normalize_source_id(source_id)
    return [
        item
        for item in log.get("mistakes", [])
        if str(item.get("source_id", "")).upper() == normalized
        and str(item.get("status", "new")).lower() != "mastered"
    ]


def _open_weak_points_for_source(course_path: Path, source_id: str) -> list[dict]:
    log = load_weak_points(get_weak_points_path(course_path))
    normalized = _normalize_source_id(source_id)
    return [
        item
        for item in log.get("weak_points", [])
        if str(item.get("source_id", "")).upper() == normalized
        and str(item.get("status", "new")).lower() != "mastered"
    ]


def _score_study_activity(
    entry: dict,
    course_path: Path,
    course_name: str,
    source_id: str,
    root: Path | None,
) -> Score:
    normalized = _normalize_source_id(source_id)
    manifest_path = entry.get("study_pack_manifest_path", "")
    if not _file_exists(manifest_path):
        default = course_path / "06_Study_Outputs" / f"{normalized}_study_pack_manifest.json"
        if not default.is_file():
            return "none"

    recall_log = load_active_recall_log(
        get_active_recall_log_path(course_path, normalized)
    )
    flashcard_log = load_flashcard_review_log(
        get_flashcard_review_log_path(course_path, normalized),
        normalized,
    )
    attempts = len(recall_log.get("attempts", []))
    reviews = len(flashcard_log.get("reviews", []))

    open_mistakes = _open_mistakes_for_source(course_path, normalized)
    open_weak = _open_weak_points_for_source(course_path, normalized)
    due_cards = collect_due_flashcards(
        course_name, root=root, source_id=normalized
    )
    weak_recall = [
        item
        for item in collect_active_recall_needs_review(course_name, root=root)
        if str(item.get("source_id", "")).upper() == normalized
    ]

    if open_mistakes or open_weak or due_cards or weak_recall:
        return "needs_review"
    if attempts == 0 and reviews == 0:
        return "none"
    return "ok"


def _build_recommended_action(
    *,
    entry: dict,
    course_path: Path,
    course_name: str,
    source_id: str,
    scores: dict[str, Score],
    root: Path | None,
) -> dict[str, str]:
    normalized = _normalize_source_id(source_id)
    stored_path = Path(entry.get("stored_path", ""))

    if entry.get("stored_path") and not stored_path.is_file():
        return {
            "key": "fix_source",
            "label": _ACTION_LABELS["fix_source"],
            "reason": "Stored source file is missing on disk.",
        }

    if scores["extraction"] == "missing":
        return {
            "key": "extract_pdf",
            "label": _ACTION_LABELS["extract_pdf"],
            "reason": "Source has not been extracted yet.",
        }

    if scores["extraction"] == "failed":
        return {
            "key": "inspect_extraction",
            "label": _ACTION_LABELS["inspect_extraction"],
            "reason": "Extraction quality failed — inspect before chunking.",
        }

    if scores["extraction"] == "needs_review":
        return {
            "key": "inspect_extraction",
            "label": _ACTION_LABELS["inspect_extraction"],
            "reason": "Extraction quality needs review.",
        }

    if scores["study_pack"] != "missing":
        if scores["study_pack"] in {"failed", "needs_review"}:
            return {
                "key": "normalize_final_audit",
                "label": _ACTION_LABELS["normalize_final_audit"],
                "reason": f"Study pack quality is {scores['study_pack']}.",
            }
        if scores["study_activity"] == "needs_review":
            return {
                "key": "review_study_items",
                "label": _ACTION_LABELS["review_study_items"],
                "reason": "Open mistakes, weak points, due flashcards, or weak recall attempts.",
            }
        if scores["study_activity"] == "none":
            return {
                "key": "start_study",
                "label": _ACTION_LABELS["start_study"],
                "reason": "Study pack exists but no active recall or flashcard activity yet.",
            }
        return {
            "key": "ready",
            "label": _ACTION_LABELS["ready"],
            "reason": "Pipeline complete and no urgent study items flagged.",
        }

    if scores["final_audit"] != "missing":
        return {
            "key": "generate_study_pack",
            "label": _ACTION_LABELS["generate_study_pack"],
            "reason": "Study pack has not been generated.",
        }

    if scores["intermediate_audit"] != "missing":
        return {
            "key": "export_final_audit_packet",
            "label": _ACTION_LABELS["export_final_audit_packet"],
            "reason": "Final audit has not been imported.",
        }

    manifest_path = get_chunk_manifest_path(course_path, normalized)
    if not manifest_path.is_file():
        return {
            "key": "chunk_source",
            "label": _ACTION_LABELS["chunk_source"],
            "reason": "Extracted text has not been chunked yet.",
        }

    if scores["local_digest"] == "missing":
        combined = get_local_digest_dir(course_path, normalized) / (
            f"{normalized}_combined_local_digest.md"
        )
        if not combined.is_file():
            return {
                "key": "run_local_digest",
                "label": _ACTION_LABELS["run_local_digest"],
                "reason": "Local digest has not been run yet.",
            }
        return {
            "key": "review_local_digest",
            "label": _ACTION_LABELS["review_local_digest"],
            "reason": "Local digest exists but review has not been run.",
        }

    if scores["local_digest"] in {"failed", "needs_review"}:
        return {
            "key": "inspect_digest",
            "label": _ACTION_LABELS["inspect_digest"],
            "reason": f"Local digest review status is {scores['local_digest']}.",
        }

    if scores["intermediate_audit"] == "missing":
        return {
            "key": "export_or_run_intermediate_audit",
            "label": _ACTION_LABELS["export_or_run_intermediate_audit"],
            "reason": "Intermediate audit has not been imported.",
        }

    return {
        "key": "export_final_audit_packet",
        "label": _ACTION_LABELS["export_final_audit_packet"],
        "reason": "Final audit has not been imported.",
    }


def _overall_quality_status(scores: dict[str, Score], action_key: str) -> str:
    if scores["extraction"] == "failed" or scores["local_digest"] == "failed":
        return "failed"
    if scores["study_pack"] == "failed":
        return "failed"
    if action_key == "ready":
        return "ok"
    if action_key in {
        "fix_source",
        "extract_pdf",
        "chunk_source",
        "run_local_digest",
        "review_local_digest",
        "export_or_run_intermediate_audit",
        "export_final_audit_packet",
        "generate_study_pack",
    }:
        return "incomplete"
    return "needs_review"


def _collect_source_warnings(
    entry: dict,
    scores: dict[str, Score],
    course_path: Path,
    course_name: str,
    source_id: str,
    root: Path | None,
) -> list[str]:
    warnings: list[str] = []
    normalized = _normalize_source_id(source_id)
    title = entry.get("title", normalized)

    if scores["extraction"] == "failed":
        warnings.append(f"{normalized} ({title}): extraction quality failed.")
    elif scores["extraction"] == "needs_review":
        warnings.append(f"{normalized} ({title}): extraction quality needs review.")
    elif scores["extraction"] == "missing":
        warnings.append(f"{normalized} ({title}): not extracted yet.")

    if scores["local_digest"] == "failed":
        warnings.append(f"{normalized} ({title}): local digest review failed.")
    elif scores["local_digest"] == "needs_review":
        warnings.append(f"{normalized} ({title}): local digest needs review.")
    elif scores["local_digest"] == "missing" and scores["extraction"] == "ok":
        if _file_exists(entry.get("local_digest_path", "")) or (
            get_local_digest_dir(course_path, normalized)
            / f"{normalized}_combined_local_digest.md"
        ).is_file():
            warnings.append(f"{normalized} ({title}): digest review not run.")
        elif get_chunk_manifest_path(course_path, normalized).is_file():
            warnings.append(f"{normalized} ({title}): local digest not run.")

    if scores["intermediate_audit"] == "missing" and scores["local_digest"] == "ok":
        warnings.append(f"{normalized} ({title}): intermediate audit missing.")
    if scores["final_audit"] == "missing" and scores["intermediate_audit"] == "ok":
        warnings.append(f"{normalized} ({title}): final audit missing.")
    if scores["study_pack"] in {"missing", "failed", "needs_review"}:
        warnings.append(
            f"{normalized} ({title}): study pack {scores['study_pack']}."
        )
    if scores["study_activity"] == "needs_review":
        warnings.append(f"{normalized} ({title}): open study items need review.")
    elif scores["study_activity"] == "none" and scores["study_pack"] == "ok":
        warnings.append(f"{normalized} ({title}): no study activity yet.")

    try:
        pipeline = get_pipeline_status(course_name, source_id, root)
        for warning in pipeline.get("warnings") or []:
            if warning not in warnings:
                warnings.append(warning)
    except Exception:
        pass

    return warnings


def evaluate_source_quality(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict:
    """Evaluate trust/readiness for one course source."""
    course_path = resolve_course_path(course_name, root)
    sources = list_sources(course_name, root)
    normalized = _normalize_source_id(source_id)
    entry = next(
        (item for item in sources if str(item.get("id", "")).upper() == normalized),
        None,
    )
    if entry is None:
        raise ValueError(f"Source not found: {source_id}")

    scores = {
        "extraction": _score_extraction(entry),
        "local_digest": _score_local_digest(entry, course_path, normalized),
        "intermediate_audit": _score_intermediate_audit(entry),
        "final_audit": _score_final_audit(entry),
        "study_pack": _score_study_pack(entry, course_path, normalized),
        "study_activity": _score_study_activity(
            entry, course_path, course_name, normalized, root
        ),
    }
    recommended_action = _build_recommended_action(
        entry=entry,
        course_path=course_path,
        course_name=course_name,
        source_id=normalized,
        scores=scores,
        root=root,
    )
    quality_status = _overall_quality_status(scores, recommended_action["key"])
    warnings = _collect_source_warnings(
        entry, scores, course_path, course_name, normalized, root
    )

    return {
        "source_id": normalized,
        "title": entry.get("title", normalized),
        "source_type": entry.get("source_type", ""),
        "registry_status": str(entry.get("status", "added")),
        "quality_status": quality_status,
        "scores": scores,
        "warnings": warnings,
        "recommended_action": recommended_action,
    }


def get_course_quality_report(
    course_name: str,
    root: Path | None = None,
) -> dict:
    """Build a course-level quality report across all registered sources."""
    course_path = resolve_course_path(course_name, root)
    sources = list_sources(course_name, root)
    evaluated = [
        evaluate_source_quality(course_name, str(entry.get("id", "")), root=root)
        for entry in sources
    ]

    ready_count = sum(1 for item in evaluated if item["quality_status"] == "ok")
    needs_review_count = sum(
        1 for item in evaluated if item["quality_status"] == "needs_review"
    )
    failed_count = sum(1 for item in evaluated if item["quality_status"] == "failed")

    top_warnings: list[str] = []
    for item in evaluated:
        for warning in item.get("warnings") or []:
            if warning not in top_warnings:
                top_warnings.append(warning)

    action_map: dict[str, dict] = {}
    for item in evaluated:
        action = item.get("recommended_action") or {}
        key = action.get("key", "")
        if key and key != "ready" and key not in action_map:
            action_map[key] = {
                "key": key,
                "label": action.get("label", key),
                "reason": action.get("reason", ""),
                "source_ids": [],
            }
        if key and key != "ready" and key in action_map:
            action_map[key]["source_ids"].append(item["source_id"])

    recommended_next_actions = sorted(
        action_map.values(),
        key=lambda action: _ACTION_PRIORITY.index(action["key"])
        if action["key"] in _ACTION_PRIORITY
        else 999,
    )

    from studyforge.study.exam_prep import get_nearest_active_exam_target
    from studyforge.study.exam_targets import list_active_exam_targets

    study_units = list_study_units(course_name, root)
    study_units_count = len(study_units)
    units_with_synthesis_count = sum(
        1
        for unit in study_units
        if str(unit.get("latest_synthesis_id", "")).strip()
    )
    units_with_unit_pack_count = sum(
        1
        for unit in study_units
        if str(unit.get("latest_unit_study_pack_manifest_path", "")).strip()
    )
    if evaluated and study_units_count == 0:
        top_warnings.append(
            "No study units defined. Group related sources into study units "
            "for easier planning."
        )

    active_exam_targets = list_active_exam_targets(course_name, root)
    nearest_exam = get_nearest_active_exam_target(course_name, root)
    nearest_exam_payload = None
    if nearest_exam:
        nearest_exam_payload = {
            "exam_id": nearest_exam.get("exam_id"),
            "title": nearest_exam.get("title"),
            "exam_date": nearest_exam.get("exam_date"),
            "days_until_exam": nearest_exam.get("days_until_exam"),
        }
        try:
            from studyforge.study.exam_readiness import get_exam_readiness_report

            readiness_report = get_exam_readiness_report(
                course_name, str(nearest_exam.get("exam_id", "")), root
            )
            readiness = readiness_report.get("readiness", {})
            nearest_exam_payload["readiness_score"] = readiness.get("score")
            nearest_exam_payload["readiness_status"] = readiness.get("status")
        except Exception:
            pass

    return {
        "course": course_path.name,
        "date": _today(),
        "source_count": len(evaluated),
        "study_units_count": study_units_count,
        "units_with_synthesis_count": units_with_synthesis_count,
        "units_with_unit_pack_count": units_with_unit_pack_count,
        "active_exam_targets_count": len(active_exam_targets),
        "nearest_exam": nearest_exam_payload,
        "ready_count": ready_count,
        "needs_review_count": needs_review_count,
        "failed_count": failed_count,
        "sources": evaluated,
        "top_warnings": top_warnings[:20],
        "recommended_next_actions": recommended_next_actions,
    }


def build_course_quality_markdown(report: dict) -> str:
    """Render a course quality report as Markdown."""
    lines = [
        f"# Course Quality Report — {report.get('course', '')}",
        "",
        f"Date: {report.get('date', '')}",
        "",
        "## Summary",
        "",
        f"- Sources: {report.get('source_count', 0)}",
        f"- Study units: {report.get('study_units_count', 0)}",
        f"- Units with imported synthesis: {report.get('units_with_synthesis_count', 0)}",
        f"- Units with unit study pack: {report.get('units_with_unit_pack_count', 0)}",
        f"- Active exam targets: {report.get('active_exam_targets_count', 0)}",
        f"- Ready: {report.get('ready_count', 0)}",
        f"- Needs review: {report.get('needs_review_count', 0)}",
        f"- Failed: {report.get('failed_count', 0)}",
    ]
    nearest_exam = report.get("nearest_exam")
    if nearest_exam:
        lines.append(
            f"- Nearest exam: {nearest_exam.get('title', '')} "
            f"({nearest_exam.get('exam_date', '')}) — "
            f"{nearest_exam.get('days_until_exam', '')} day(s) away"
        )
        if nearest_exam.get("readiness_score") is not None:
            lines.append(
                f"- Nearest exam readiness: {nearest_exam.get('readiness_score')}% "
                f"({nearest_exam.get('readiness_status', '')})"
            )
    lines.extend(
        [
            "",
            "## Source Health Table",
            "",
            "| Source | Title | Status | Extraction | Digest | Int. Audit | Final Audit | Study Pack | Activity | Next Action |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for source in report.get("sources") or []:
        scores = source.get("scores") or {}
        action = source.get("recommended_action") or {}
        lines.append(
            "| {source_id} | {title} | {status} | {extraction} | {digest} | {ia} | {fa} | {pack} | {activity} | {action} |".format(
                source_id=source.get("source_id", ""),
                title=str(source.get("title", "")).replace("|", "\\|"),
                status=source.get("quality_status", ""),
                extraction=scores.get("extraction", ""),
                digest=scores.get("local_digest", ""),
                ia=scores.get("intermediate_audit", ""),
                fa=scores.get("final_audit", ""),
                pack=scores.get("study_pack", ""),
                activity=scores.get("study_activity", ""),
                action=action.get("label", ""),
            )
        )

    lines.extend(["", "## Sources Needing Attention", ""])
    attention = [
        item
        for item in report.get("sources") or []
        if item.get("quality_status") != "ok"
    ]
    if attention:
        for source in attention:
            action = source.get("recommended_action") or {}
            lines.append(f"### {source.get('source_id')} — {source.get('title', '')}")
            for warning in source.get("warnings") or []:
                lines.append(f"- Warning: {warning}")
            lines.append(
                f"- Recommended action: {action.get('label', '')} — "
                f"{action.get('reason', '')}"
            )
            lines.append("")
    else:
        lines.append("- None — all sources are ready.")

    lines.extend(["", "## Ready to Study", ""])
    ready = [
        item
        for item in report.get("sources") or []
        if item.get("quality_status") == "ok"
    ]
    if ready:
        for source in ready:
            lines.append(f"- {source.get('source_id')} — {source.get('title', '')}")
    else:
        lines.append("- None yet.")

    lines.extend(["", "## Course-Level Recommendations", ""])
    actions = report.get("recommended_next_actions") or []
    if actions:
        for action in actions:
            sources_text = ", ".join(action.get("source_ids") or [])
            lines.append(
                f"- **{action.get('label', '')}** ({sources_text}): "
                f"{action.get('reason', '')}"
            )
    else:
        lines.append("- All sources look ready to study.")

    lines.append("")
    return "\n".join(lines)


def export_course_quality_report(
    course_name: str,
    root: Path | None = None,
) -> dict:
    """Write course quality Markdown/JSON reports and return paths."""
    course_path = resolve_course_path(course_name, root)
    report = get_course_quality_report(course_name, root)
    json_path, md_path = get_course_quality_report_paths(course_path)

    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(build_course_quality_markdown(report), encoding="utf-8")

    return {
        "course": course_path.name,
        "report_json_path": str(json_path.resolve()),
        "report_markdown_path": str(md_path.resolve()),
        "report": report,
    }

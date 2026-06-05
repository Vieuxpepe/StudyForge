"""
StudyForge Streamlit GUI — wraps existing CLI backend functions.
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import streamlit as st

from studyforge.audits.final_audit_normalizer import (
    NormalizedAuditExistsError,
    RepairPacketExistsError,
    build_final_audit_repair_packet,
    normalize_latest_final_audit,
)
from studyforge.audits.final_import import import_final_audit
from studyforge.audits.final_packet import build_final_audit_packet
from studyforge.audits.intermediate_import import import_intermediate_audit
from studyforge.audits.intermediate_packet import build_intermediate_audit_packet
from studyforge.core.chunking_jobs import chunk_registered_source
from studyforge.core.courses import create_course, list_courses
from studyforge.core.digest_jobs import (
    DEFAULT_DIGEST_MAX_TOKENS,
    run_local_digest_for_source,
)
from studyforge.core.extraction_jobs import extract_registered_source
from studyforge.extraction.extraction_quality import run_extraction_quality_check
from studyforge.core.intermediate_audit_jobs import run_intermediate_audit_for_source
from studyforge.core.guided_workflow import (
    UnsupportedGuidedActionError,
    default_guided_options,
    get_guided_next_action,
    run_guided_next_step,
)
from studyforge.core.pipeline_status import STEP_ORDER, get_pipeline_status
from studyforge.core.app_settings import (
    get_app_settings_path,
    get_default_app_settings,
    load_app_settings,
    save_app_settings,
    validate_app_settings,
)
from studyforge.core.paths import find_project_root, get_courses_dir, load_config
from studyforge.core.secrets import get_google_api_key, set_google_api_key
from studyforge.core.backup import (
    BackupExistsError,
    create_course_backup,
    format_bytes,
    list_course_backups,
)
from studyforge.core.backup_restore import (
    InvalidBackupError,
    RestoreTargetExistsError,
    preview_restore_backup,
    restore_backup_to_new_course,
    verify_backup,
)
from studyforge.core.sources import add_source, list_sources, resolve_course_path
from studyforge.llm.google_genai_client import (
    DEFAULT_GEMMA_4_26B_MODEL,
    DEFAULT_GEMMA_4_31B_MODEL,
)
from studyforge.llm.lm_studio_client import (
    DEFAULT_BASE_URL,
    check_lm_studio_connection,
    choose_default_model,
)
from studyforge.study.course_quality import (
    export_course_quality_report,
    get_course_quality_report,
    get_course_quality_report_paths,
)
from studyforge.study.evidence_trace import (
    export_chunk_trace,
    get_chunk_trace,
    get_source_trace_summary,
    list_source_chunks,
)
from studyforge.study.active_recall import (
    ActiveRecallNotReadyError,
    InvalidGradeError,
    export_active_recall_summary_markdown,
    get_active_recall_log_path,
    get_first_unanswered_question,
    load_active_recall_log,
    load_questions_for_source,
    record_active_recall_attempt,
    summarize_active_recall_log,
)
from studyforge.study.mistakes import (
    InvalidMistakeStatusError,
    MistakeNotFoundError,
    add_mistake,
    export_mistakes_markdown,
    list_mistakes,
    update_mistake_status,
)
from studyforge.study.flashcards import (
    FlashcardExportExistsError,
    export_flashcards_from_sections,
)
from studyforge.study.flashcard_review import (
    FlashcardsNotReadyError,
    InvalidFlashcardGradeError,
    collect_due_flashcards,
    get_first_unreviewed_card,
    get_flashcard_review_log_path,
    load_flashcards_for_source,
    load_flashcard_review_log,
    record_flashcard_review,
    summarize_flashcard_reviews,
)
from studyforge.study.study_pack import (
    FinalAuditNotFoundError,
    StudyPackOutputExistsError,
    _SECTION_HEADINGS,
    diagnose_study_pack,
    extract_sections,
    generate_study_pack,
    get_latest_final_audit,
)
from studyforge.study.review_planner import (
    ReviewPlanExistsError,
    generate_review_plan,
    get_review_plan_path,
)
from studyforge.study.study_session import (
    InvalidSessionResultError,
    StudySessionItemNotFoundError,
    complete_study_session,
    export_study_session_summary,
    get_latest_study_session,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.digest_review import review_local_digest_for_source
from studyforge.study.study_unit_dashboard import (
    UnitReviewPlanExistsError,
    export_unit_dashboard,
    generate_unit_review_plan,
    get_study_unit_dashboard,
    get_unit_dashboard_paths,
)
from studyforge.study.unit_study_pack import (
    UnitStudyPackOutputExistsError,
    diagnose_unit_study_pack,
    generate_unit_study_pack,
)
from studyforge.study.unit_synthesis_import import import_unit_synthesis
from studyforge.study.unit_synthesis_packet import (
    UnitSynthesisPacketExistsError,
    build_unit_synthesis_packet,
    get_unit_synthesis_packet_paths,
)
from studyforge.study.study_units import (
    InvalidSourceIdError,
    InvalidStudyUnitStatusError,
    StudyUnitNotFoundError,
    add_sources_to_unit,
    create_study_unit,
    list_study_units,
    remove_sources_from_unit,
    update_study_unit,
)
from studyforge.study.exam_prep import (
    ExamPrepPlanExistsError,
    collect_exam_prep_state,
    generate_exam_prep_plan,
    recommend_exam_prep_actions,
)
from studyforge.study.exam_readiness import (
    ExamReadinessReportExistsError,
    build_exam_readiness_markdown,
    export_exam_readiness_report,
    get_exam_readiness_report,
)
from studyforge.study.exam_targets import (
    ExamTargetNotFoundError,
    InvalidExamDateError,
    InvalidExamTargetStatusError,
    InvalidExamUnitIdError,
    InvalidTargetScoreError,
    create_exam_target,
    list_active_exam_targets,
    list_exam_targets,
    update_exam_target,
)
from studyforge.study.mock_test_grading import (
    InvalidMockTestGradeError,
    MockTestGradingAlreadyFinalizedError,
    MockTestQuestionNotFoundError,
    MockTestReviewExistsError,
    build_mock_test_review_markdown,
    export_mock_test_review,
    finalize_mock_test_grading,
    record_mock_question_result,
    summarize_mock_test_grading,
)
from studyforge.study.mock_tests import (
    InvalidMockTestScopeError,
    InvalidMockTestScoreError,
    MockTestNotFoundError,
    MockTestNotReadyError,
    generate_mock_test,
    list_mock_tests,
    load_mock_test_json,
    record_mock_test_attempt,
    summarize_mock_test_attempts,
)
from studyforge.study.today_dashboard import export_today_dashboard, get_today_dashboard
from studyforge.study.unit_review import get_unit_review_counts
from studyforge.study.weak_points import (
    InvalidConfidenceError,
    InvalidWeakPointStatusError,
    WeakPointNotFoundError,
    add_weak_point,
    export_weak_points_markdown,
    list_weak_points,
    update_weak_point,
)
from studyforge.ui.helpers import read_text_preview, source_pipeline_flags, yes_no
from studyforge.ui.navigation import (
    WHERE_TO_GO_HELP,
    flatten_navigation_pages,
    get_page_by_key,
    get_page_description,
    navigation_keys,
    option_to_page_key,
)

SOURCE_TYPES = ["textbook", "slides", "homework", "notes", "extra_readings"]


def _session_defaults_from_app_settings(settings: dict) -> dict:
    """Map persisted app settings to Streamlit session state keys."""
    lm = settings.get("lm_studio", {})
    chunking = settings.get("chunking", {})
    digest = settings.get("digest", {})
    gui = settings.get("gui", {})
    default_page = str(gui.get("default_page", "today")).strip().lower()
    if default_page not in navigation_keys():
        default_page = "today"
    return {
        "project_root": str(find_project_root()),
        "lm_base_url": lm.get("base_url", DEFAULT_BASE_URL),
        "lm_model": lm.get("default_model", ""),
        "lm_temperature": float(lm.get("temperature", 0.2)),
        "lm_timeout": int(lm.get("timeout", 300)),
        "max_words": int(chunking.get("max_words", 1200)),
        "overlap_words": int(chunking.get("overlap_words", 150)),
        "overwrite": bool(digest.get("overwrite_default", False)),
        "full_digest_default": bool(digest.get("full_digest_default", False)),
        "max_digest_tokens": int(lm.get("max_tokens", DEFAULT_DIGEST_MAX_TOKENS)),
        "google_audit_model": DEFAULT_GEMMA_4_26B_MODEL,
        "limit_chunks": int(digest.get("limit_chunks_default", 1)),
        "only_needs_review": False,
        "selected_course": None,
        "selected_source_id": None,
        "nav_page_key": default_page,
        "show_advanced_options": bool(gui.get("show_advanced_options", True)),
    }


def _apply_app_settings_to_session(settings: dict) -> None:
    """Overwrite pipeline/GUI session keys from saved settings."""
    for key, value in _session_defaults_from_app_settings(settings).items():
        if key in {"project_root", "selected_course", "selected_source_id", "only_needs_review"}:
            continue
        st.session_state[key] = value


def _init_session_state() -> None:
    root = find_project_root()
    settings = load_app_settings(root)
    defaults = _session_defaults_from_app_settings(settings)
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _course_names() -> list[str]:
    return [p.name for p in list_courses()]


def _render_page_intro(page_key: str) -> None:
    """Render page title and role description from navigation metadata."""
    page = get_page_by_key(page_key)
    title = page["label"] if page else page_key.replace("_", " ").title()
    st.header(title)
    description = get_page_description(page_key)
    if description:
        st.caption(description)


def _render_sidebar() -> tuple[str, str | None]:
    st.sidebar.title("StudyForge")
    st.sidebar.caption("Local-first AI study pipeline")

    courses = _course_names()
    if courses:
        index = 0
        if st.session_state.selected_course in courses:
            index = courses.index(st.session_state.selected_course)
        selected = st.sidebar.selectbox("Course", courses, index=index)
        st.session_state.selected_course = selected
    else:
        st.sidebar.info("No courses yet. Create one under Course Tools → Courses.")
        st.session_state.selected_course = None

    options = flatten_navigation_pages()
    keys = navigation_keys()
    current_key = st.session_state.get("nav_page_key", keys[0])
    if current_key not in keys:
        current_key = keys[0]
    selected_index = keys.index(current_key)
    choice = st.sidebar.selectbox("Go to", options, index=selected_index)
    page_key = option_to_page_key(choice) or keys[0]
    st.session_state.nav_page_key = page_key
    return page_key, st.session_state.selected_course


def _require_course() -> str | None:
    if not st.session_state.selected_course:
        st.warning("Create or select a course first (sidebar or **Courses** page).")
        return None
    return st.session_state.selected_course


def _source_options(course_name: str) -> list[dict]:
    try:
        return list_sources(course_name)
    except Exception as exc:
        st.error(str(exc))
        return []


def _select_source(sources: list[dict], key: str = "source_picker") -> str | None:
    if not sources:
        st.info("No sources yet. Add a source PDF from the **Sources** page.")
        return None
    labels = [
        f"{s.get('id', '?')} — {s.get('title', 'Untitled')} ({s.get('status', '?')})"
        for s in sources
    ]
    ids = [s.get("id", "") for s in sources]
    default = 0
    if st.session_state.selected_source_id in ids:
        default = ids.index(st.session_state.selected_source_id)
    choice = st.selectbox("Source", labels, index=default, key=key)
    idx = labels.index(choice)
    sid = ids[idx]
    st.session_state.selected_source_id = sid
    return sid


def _show_exception(exc: Exception) -> None:
    st.error(f"{type(exc).__name__}: {exc}")


def _get_pipeline_status_cached(
    course_name: str, source_id: str, force_refresh: bool = False
) -> dict | None:
    cache_key = f"pipeline_status_{source_id}"
    if force_refresh:
        st.session_state.pop(cache_key, None)
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = get_pipeline_status(course_name, source_id)
        except Exception as exc:
            _show_exception(exc)
            return None
    return st.session_state[cache_key]


def _render_guided_workflow(course_name: str, source_id: str) -> None:
    """One-click next step from Pipeline Doctor (not autonomous)."""
    st.subheader("Guided Workflow")
    st.caption(
        "The **Run next recommended step** button uses Pipeline Doctor to run "
        "exactly one next step. It is not autonomous and does not loop through "
        "the full pipeline."
    )

    try:
        guided = get_guided_next_action(course_name, source_id)
    except Exception as exc:
        _show_exception(exc)
        return

    st.write(f"**Registry status:** `{guided.get('registry_status', 'unknown')}`")
    st.info(
        f"👉 **Next recommended action:** {guided.get('label', '—')}\n\n"
        f"{guided.get('reason', '')}"
    )
    st.write(guided.get("description", ""))
    if guided.get("warning"):
        st.warning(guided["warning"])

    for warning in guided.get("warnings") or []:
        st.warning(f"⚠️ {warning}")

    gw_overwrite = st.checkbox(
        "Overwrite outputs",
        value=st.session_state.overwrite,
        key=f"gw_overwrite_{source_id}",
    )
    st.session_state.overwrite = gw_overwrite

    gw_full_digest = bool(st.session_state.full_digest_default)
    if st.session_state.show_advanced_options:
        st.write("**Advanced options**")
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.lm_base_url = st.text_input(
                "LM Studio base URL",
                value=st.session_state.lm_base_url,
                key=f"gw_lm_url_{source_id}",
            )
        with c2:
            st.session_state.lm_model = st.text_input(
                "Model (empty = first from /models)",
                value=st.session_state.lm_model,
                key=f"gw_lm_model_{source_id}",
            )

        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            st.session_state.max_digest_tokens = st.number_input(
                "Max digest tokens",
                min_value=1000,
                max_value=32000,
                value=int(st.session_state.max_digest_tokens),
                step=500,
                key=f"gw_max_tokens_{source_id}",
            )
        with tc2:
            st.session_state.lm_temperature = st.number_input(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(st.session_state.lm_temperature),
                step=0.1,
                key=f"gw_temperature_{source_id}",
            )
        with tc3:
            st.session_state.lm_timeout = st.number_input(
                "Timeout (seconds)",
                min_value=30,
                max_value=3600,
                value=int(st.session_state.lm_timeout),
                step=30,
                key=f"gw_timeout_{source_id}",
            )

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            st.session_state.max_words = st.number_input(
                "Max words (chunking)",
                min_value=100,
                value=int(st.session_state.max_words),
                key=f"gw_max_words_{source_id}",
            )
        with cc2:
            st.session_state.overlap_words = st.number_input(
                "Overlap words (chunking)",
                min_value=0,
                value=int(st.session_state.overlap_words),
                key=f"gw_overlap_{source_id}",
            )
        with cc3:
            gw_full_digest = st.checkbox(
                "Run full digest (not first chunk only)",
                value=bool(st.session_state.full_digest_default),
                key=f"gw_full_digest_{source_id}",
            )

    can_run = guided.get("can_run", False)
    if st.button(
        "Run next recommended step",
        disabled=not can_run,
        key=f"gw_run_{source_id}",
    ):
        options = default_guided_options()
        options.update(
            {
                "overwrite": gw_overwrite,
                "base_url": st.session_state.lm_base_url,
                "model": st.session_state.lm_model or None,
                "max_tokens": int(st.session_state.max_digest_tokens),
                "temperature": float(st.session_state.lm_temperature),
                "timeout": int(st.session_state.lm_timeout),
                "max_words": int(st.session_state.max_words),
                "overlap_words": int(st.session_state.overlap_words),
                "full_digest": gw_full_digest,
            }
        )
        try:
            with st.spinner(f"Running: {guided.get('label', 'step')}…"):
                result = run_guided_next_step(
                    course_name,
                    source_id,
                    options=options,
                )
            st.session_state.pop(f"pipeline_status_{source_id}", None)
            _show_result_summary(result.get("message", "Step complete"), result.get("summary", {}))
            st.rerun()
        except UnsupportedGuidedActionError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)
    elif not can_run:
        st.caption("This step must be done manually (see hint above).")


def _render_pipeline_doctor(course_name: str, source_id: str) -> dict | None:
    """Show pipeline checklist, warnings, and next recommended action."""
    st.subheader("Pipeline Doctor")
    if st.button("Refresh pipeline status", key=f"refresh_pipeline_{source_id}"):
        status = _get_pipeline_status_cached(course_name, source_id, force_refresh=True)
    else:
        status = _get_pipeline_status_cached(course_name, source_id)

    if status is None:
        return None

    action = status.get("next_action", {})

    st.info(
        f"👉 **Next:** {action.get('label', '—')} — {action.get('reason', '')}"
    )
    if action.get("gui_hint"):
        st.caption(action["gui_hint"])

    st.write(f"**Registry status:** `{status.get('registry_status', 'unknown')}`")

    completed = status.get("completed_steps") or []
    missing = status.get("missing_steps") or []
    if completed:
        st.write(f"✅ **Completed:** {', '.join(completed)}")
    if missing:
        st.write(f"⏳ **Missing:** {', '.join(missing)}")

    for key, label in STEP_ORDER:
        step = status["steps"][key]
        icon = "✅" if step["done"] else "⏳"
        detail = step.get("details") or ""
        line = f"{icon} **{label}**"
        if detail:
            line += f" — {detail}"
        st.write(line)

    warnings = status.get("warnings") or []
    if warnings:
        st.write("**Warnings**")
        for warning in warnings:
            st.warning(f"⚠️ {warning}")

    return status


def _render_extraction_quality(course_name: str, source_id: str) -> None:
    """Show extraction quality status and run manual quality checks."""
    from studyforge.core.extraction_jobs import find_source_by_id

    st.subheader("Extraction Quality")
    st.caption(
        "Deterministic check for empty/low-text pages and suspicious extraction "
        "artifacts. No OCR or AI."
    )

    try:
        entry = find_source_by_id(course_name, source_id)
    except Exception as exc:
        _show_exception(exc)
        return

    quality_status = entry.get("extraction_quality_status")
    report_json = entry.get("extraction_quality_report_path")
    if quality_status:
        if quality_status == "failed":
            st.error(f"Quality status: **{quality_status}**")
        elif quality_status == "needs_review":
            st.warning(f"Quality status: **{quality_status}**")
        else:
            st.success(f"Quality status: **{quality_status}**")

    if st.button("Run extraction quality check", key=f"quality_check_{source_id}"):
        try:
            with st.spinner("Analyzing extraction quality…"):
                report = run_extraction_quality_check(course_name, source_id)
            st.session_state[f"quality_report_{source_id}"] = report
            st.session_state.pop(f"pipeline_status_{source_id}", None)
            st.rerun()
        except Exception as exc:
            _show_exception(exc)
            return

    report = st.session_state.get(f"quality_report_{source_id}")
    if report is None and report_json and Path(report_json).is_file():
        try:
            report = json.loads(Path(report_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = None

    if report:
        st.write(f"**Pages:** {report.get('total_pages', 0)}")
        st.write(f"**Words:** {report.get('total_words', 0)}")
        st.write(f"**Average words/page:** {report.get('average_words_per_page', 0)}")
        empty_pages = report.get("empty_pages") or []
        low_pages = report.get("low_word_pages") or []
        if empty_pages:
            st.write(f"**Empty pages:** {', '.join(str(p) for p in empty_pages)}")
        if low_pages:
            st.write(f"**Low-word pages:** {', '.join(str(p) for p in low_pages)}")
        for warning in report.get("warnings") or []:
            st.warning(warning)

    md_path = None
    if report:
        md_path = report.get("report_markdown_path")
    if not md_path and report_json:
        md_candidate = Path(report_json).with_suffix(".md")
        if md_candidate.is_file():
            md_path = str(md_candidate)

    if md_path and Path(md_path).is_file():
        with st.expander("Preview Markdown report"):
            st.text(Path(md_path).read_text(encoding="utf-8"))


def _render_study_pack_quality(quality: dict | None, extra_warnings: list | None = None) -> None:
    """Show study pack quality banner from manifest or generation result."""
    if not quality:
        return
    status = quality.get("quality_status", "unknown")
    warnings = list(quality.get("warnings") or [])
    if extra_warnings:
        for warning in extra_warnings:
            if warning not in warnings:
                warnings.append(warning)

    if status == "ok":
        st.success(
            "Study pack quality looks good — expected sections were found in the final audit."
        )
    elif status == "needs_review":
        st.warning(
            "Study pack generated, but content may be thin. Review missing sections "
            "before relying on flashcards and quizzes. Try normalizing the final audit "
            "or export a repair packet on Audits, then regenerate the study pack."
        )
    else:
        st.error(
            "Study pack was created, but the final audit had very little usable content. "
            "Try the Final Audit Normalizer on Audits or export a repair packet, then "
            "re-import and regenerate the study pack."
        )

    missing = quality.get("missing_sections") or []
    if missing:
        labels = [f"{k} ({_SECTION_HEADINGS.get(k, k)})" for k in missing]
        st.write("**Missing sections:** " + ", ".join(labels))

    thin = quality.get("placeholder_sections") or []
    if thin:
        labels = [f"{k} ({_SECTION_HEADINGS.get(k, k)})" for k in thin]
        st.write("**Thin sections:** " + ", ".join(labels))

    st.write(f"**Total extracted words:** {quality.get('total_extracted_words', 0)}")

    if warnings:
        st.write("**Quality warnings**")
        for warning in warnings:
            st.write(f"- {warning}")


def _render_flashcards_section(course_name: str, source_id: str, entry: dict) -> None:
    """Flashcard exports, regenerate control, and preview."""
    st.subheader("Flashcards")
    st.caption(
        "Deterministic flashcards from final audit sections. Exports Markdown, CSV, "
        "and Anki TSV (import manually into Anki). No spaced repetition scheduling yet."
    )

    manifest_path = entry.get("study_pack_manifest_path")
    manifest_data: dict | None = None
    if manifest_path and Path(manifest_path).is_file():
        try:
            manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest_data = None

    flashcard_count = None
    if manifest_data is not None:
        flashcard_count = manifest_data.get("flashcard_count")
    if flashcard_count is not None:
        st.write(f"**Card count:** {flashcard_count}")

    path_rows = [
        ("Markdown", entry.get("flashcards_path") or (manifest_data or {}).get("outputs", {}).get("flashcards")),
        ("CSV", entry.get("flashcards_csv_path") or (manifest_data or {}).get("outputs", {}).get("flashcards_csv")),
        (
            "Anki TSV",
            entry.get("flashcards_anki_tsv_path")
            or (manifest_data or {}).get("outputs", {}).get("flashcards_anki_tsv"),
        ),
    ]
    existing_paths = [(label, p) for label, p in path_rows if p and Path(p).is_file()]
    if existing_paths:
        st.write("**Export files**")
        for label, path_str in existing_paths:
            st.write(f"- **{label}:** `{path_str}`")

    fc_overwrite = st.checkbox(
        "Overwrite existing flashcard exports",
        value=False,
        key=f"flashcards_overwrite_{source_id}",
    )
    if st.button("Regenerate flashcards", key=f"regen_flashcards_{source_id}"):
        try:
            course_path = resolve_course_path(course_name)
            final_audit = get_latest_final_audit(course_path, source_id)
            sections = extract_sections(final_audit["text"])
            summary = export_flashcards_from_sections(
                course_name,
                source_id,
                sections,
                overwrite=fc_overwrite,
            )
            st.success(
                f"Regenerated {summary['flashcard_count']} flashcards "
                f"(Markdown, CSV, Anki TSV)."
            )
            for warning in summary.get("warnings", []):
                st.warning(warning)
            st.rerun()
        except FlashcardExportExistsError as exc:
            st.error(str(exc))
        except FinalAuditNotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    csv_path = next((Path(p) for label, p in existing_paths if label == "CSV"), None)
    if csv_path and csv_path.is_file():
        try:
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if rows:
                st.write("**Preview (first 10 cards)**")
                for index, row in enumerate(rows[:10], start=1):
                    st.markdown(f"**Card {index}** — {row.get('section', '')}")
                    st.write(f"Front: {row.get('front', '')}")
                    st.write(f"Back: {row.get('back', '')}")
        except OSError:
            pass


def _render_study_pack(course_name: str, source_id: str, pipeline_status: dict | None) -> None:
    """Generate and preview study pack outputs from the latest final audit."""
    st.subheader("Study Pack")
    st.caption(
        "After importing a final audit, generate a study pack to create the final "
        "guide, flashcards, formula sheet, quiz, active recall file, and weak-points "
        "seed. Deterministic export from the latest final audit (no AI)."
    )

    action_key = (pipeline_status or {}).get("next_action", {}).get("key", "")
    if action_key == "generate_study_pack":
        st.info(
            "Pipeline Doctor: final audit is imported — generate your study pack below."
        )

    pack_overwrite = st.checkbox(
        "Overwrite existing study pack files",
        value=False,
        key=f"study_pack_overwrite_{source_id}",
    )

    col_gen, col_diag = st.columns(2)
    with col_diag:
        if st.button("Diagnose final audit only", key=f"diag_study_pack_{source_id}"):
            try:
                report = diagnose_study_pack(course_name, source_id)
                st.session_state[f"study_pack_diag_{source_id}"] = report
            except FinalAuditNotFoundError as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    diag_report = st.session_state.get(f"study_pack_diag_{source_id}")
    if diag_report:
        st.caption("Diagnostic preview (no files written)")
        _render_study_pack_quality(
            diag_report.get("quality"),
            diag_report.get("warnings"),
        )

    with col_gen:
        run_generate = st.button("Generate study pack", key=f"gen_study_pack_{source_id}")
    if run_generate:
        try:
            with st.spinner("Generating study pack…"):
                summary = generate_study_pack(
                    course_name,
                    source_id,
                    overwrite=pack_overwrite,
                )
            st.session_state.pop(f"pipeline_status_{source_id}", None)
            _render_study_pack_quality(summary.get("quality"), summary.get("warnings"))
            _show_result_summary("Study pack generated", summary)
            st.rerun()
        except StudyPackOutputExistsError as exc:
            st.error(str(exc))
        except FinalAuditNotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    try:
        sources = {s["id"]: s for s in list_sources(course_name)}
        entry = sources.get(source_id)
    except Exception:
        entry = None

    if not entry:
        return

    output_paths = [
        ("Manifest", entry.get("study_pack_manifest_path")),
        ("Final study guide", entry.get("final_study_guide_path")),
        ("Flashcards (Markdown)", entry.get("flashcards_path")),
        ("Flashcards (CSV)", entry.get("flashcards_csv_path")),
        ("Flashcards (Anki TSV)", entry.get("flashcards_anki_tsv_path")),
        ("Formula sheet", entry.get("formula_sheet_path")),
        ("Practice quiz", entry.get("practice_quiz_path")),
        ("Active recall", entry.get("active_recall_path")),
        ("Weak points seed", entry.get("weak_points_seed_path")),
    ]
    existing = [(label, p) for label, p in output_paths if p and Path(p).is_file()]
    if not existing:
        return

    st.write("**Study pack outputs**")
    for label, path_str in existing:
        st.write(f"- **{label}:** `{path_str}`")

    manifest_path = entry.get("study_pack_manifest_path")
    if manifest_path and Path(manifest_path).is_file():
        try:
            manifest_data = json.loads(
                Path(manifest_path).read_text(encoding="utf-8")
            )
            if manifest_data.get("quality"):
                st.write("**Saved pack quality (from manifest)**")
                _render_study_pack_quality(
                    manifest_data["quality"],
                    manifest_data.get("warnings"),
                )
        except (OSError, json.JSONDecodeError):
            pass

    preview_labels = [p[0] for p in existing if p[0] != "Manifest"]
    preview_map = {p[0]: p[1] for p in existing if p[0] != "Manifest"}
    if preview_labels:
        pick = st.selectbox(
            "Preview study pack file",
            preview_labels,
            key=f"study_pack_preview_{source_id}",
        )
        path = Path(preview_map[pick])
        if path.suffix.lower() in {".md", ".txt"}:
            st.text_area(
                pick,
                read_text_preview(path),
                height=300,
                key=f"study_pack_preview_text_{source_id}",
            )

    _render_flashcards_section(course_name, source_id, entry)


def _show_result_summary(title: str, data: dict) -> None:
    st.success(title)
    for key, value in data.items():
        if isinstance(value, list):
            st.write(f"**{key}:**")
            for item in value:
                st.write(f"- {item}")
        else:
            st.write(f"**{key}:** {value}")


def page_today(course_name: str | None) -> None:
    _render_page_intro("today")
    if not _require_course():
        return

    with st.expander("Where should I go?", expanded=False):
        st.markdown(WHERE_TO_GO_HELP)

    try:
        dashboard = get_today_dashboard(course_name)
    except Exception as exc:
        _show_exception(exc)
        return

    summary = dashboard.get("summary", {})
    st.subheader(f"{dashboard.get('course', '')} — {dashboard.get('date', '')}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Due flashcards", summary.get("due_flashcards", 0))
    c2.metric("Active recall", summary.get("active_recall_needs_review", 0))
    c3.metric("Open mistakes", summary.get("open_mistakes", 0))
    c4.metric("Open weak points", summary.get("open_weak_points", 0))
    latest_mock = summary.get("latest_mock_test_score")
    if latest_mock:
        c5.metric(
            "Latest mock test %",
            latest_mock.get("percent", 0),
            help=f"{latest_mock.get('score_correct')}/{latest_mock.get('score_total')}",
        )
    else:
        c5.metric("Latest mock test %", "—")
    st.caption(f"Active study units: {summary.get('active_study_units', 0)}")
    nearest_exam = summary.get("nearest_exam")
    if nearest_exam:
        nearest_line = (
            f"Nearest exam: {nearest_exam.get('title', '')} "
            f"({nearest_exam.get('exam_date', '')}) — "
            f"{nearest_exam.get('days_until_exam', '')} day(s) away"
        )
        if nearest_exam.get("readiness_score") is not None:
            nearest_line += (
                f" · readiness: {nearest_exam.get('readiness_score')}% "
                f"({nearest_exam.get('readiness_status', '')})"
            )
        st.caption(nearest_line)
    elif summary.get("active_exam_targets", 0):
        st.caption(f"Active exam targets: {summary.get('active_exam_targets', 0)}")
    active_units = dashboard.get("active_units") or summary.get("active_units") or []
    if active_units:
        with st.expander("Active study units", expanded=False):
            for unit in active_units:
                markers = ""
                if unit.get("has_synthesis"):
                    markers += " · synthesis"
                if unit.get("has_unit_pack"):
                    markers += " · unit pack"
                extra = ""
                if unit.get("has_unit_pack"):
                    due_fc = unit.get("unit_due_flashcards")
                    recall_gaps = unit.get("unit_recall_gaps")
                    if due_fc is not None or recall_gaps is not None:
                        extra = (
                            f" — unit due flashcards: {due_fc or 0}, "
                            f"unit recall gaps: {recall_gaps or 0}"
                        )
                st.write(
                    f"- `{unit.get('unit_id', '')}` — {unit.get('title', '')}{markers}{extra}"
                )

    actions = dashboard.get("recommended_actions") or []
    if actions:
        primary = actions[0]
        st.info(f"**Recommended:** {primary.get('label', '')} — {primary.get('reason', '')}")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        if st.button("Generate review plan", key="today_gen_plan"):
            try:
                from studyforge.study.review_planner import ReviewPlanExistsError, generate_review_plan

                generate_review_plan(course_name, overwrite=False)
                st.success("Review plan generated.")
                st.rerun()
            except ReviewPlanExistsError:
                st.warning("Today's plan already exists. Use Review Tracker to overwrite.")
            except Exception as exc:
                _show_exception(exc)
    with col_b:
        if st.button("Start study session", key="today_start_session"):
            try:
                result = start_study_session(course_name, limit=10)
                st.success(f"Started `{result['session_id']}` with {result['item_count']} items.")
                st.rerun()
            except Exception as exc:
                _show_exception(exc)
    with col_c:
        session_id = summary.get("latest_session_id")
        if summary.get("latest_session_status") == "in_progress" and session_id:
            if st.button("Continue session", key="today_continue_session"):
                st.session_state[f"study_session_{course_name}"] = get_latest_study_session(
                    course_name
                )
                st.success("Session loaded. Open **Study Session** in the sidebar.")
        else:
            st.button("Continue session", key="today_continue_disabled", disabled=True)
    with col_d:
        if st.button("Export dashboard", key="today_export"):
            try:
                path = export_today_dashboard(course_name)
                st.success(f"Exported: `{path}`")
            except Exception as exc:
                _show_exception(exc)

    if summary.get("latest_session_status") == "in_progress" and session_id:
        st.caption(f"In-progress session: `{session_id}` — use **Study Session** to continue.")

    priority_items = dashboard.get("priority_items") or []
    st.subheader("Priority items")
    if priority_items:
        rows = []
        for item in priority_items:
            rows.append(
                {
                    "Type": item.get("type", ""),
                    "ID": item.get("id", ""),
                    "Source": item.get("source_id", ""),
                    "Title": (item.get("title", "") or "")[:80],
                    "Reason": item.get("priority_reason", ""),
                }
            )
        st.dataframe(rows, use_container_width=True)
    else:
        st.info(
            "Nothing is due right now. You can still review flashcards or start a new source."
        )

    warnings = dashboard.get("warnings") or []
    if warnings:
        st.subheader("Warnings")
        for warning in warnings:
            st.warning(warning)


def page_course_quality(course_name: str | None) -> None:
    _render_page_intro("course_quality")
    if not _require_course():
        return

    col_refresh, col_export = st.columns(2)
    with col_refresh:
        refresh = st.button("Refresh quality report", key="course_quality_refresh")
    with col_export:
        export = st.button("Export report", key="course_quality_export")

    try:
        if export:
            result = export_course_quality_report(course_name)
            st.session_state.course_quality_report = result["report"]
            st.success("Report exported.")
            st.code(result.get("report_markdown_path", ""))
        elif refresh or "course_quality_report" not in st.session_state:
            st.session_state.course_quality_report = get_course_quality_report(
                course_name
            )

        report = st.session_state.get("course_quality_report")
        if not report:
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sources", report.get("source_count", 0))
        c2.metric("Ready", report.get("ready_count", 0))
        c3.metric("Needs review", report.get("needs_review_count", 0))
        c4.metric("Failed", report.get("failed_count", 0))
        st.caption(f"Study units: {report.get('study_units_count', 0)}")
        nearest_exam = report.get("nearest_exam")
        if nearest_exam:
            cq_nearest = (
                f"Nearest exam: {nearest_exam.get('title', '')} "
                f"({nearest_exam.get('exam_date', '')}) — "
                f"{nearest_exam.get('days_until_exam', '')} day(s) away"
            )
            if nearest_exam.get("readiness_score") is not None:
                cq_nearest += (
                    f" · readiness: {nearest_exam.get('readiness_score')}% "
                    f"({nearest_exam.get('readiness_status', '')})"
                )
            st.caption(cq_nearest)
        elif report.get("active_exam_targets_count", 0):
            st.caption(
                f"Active exam targets: {report.get('active_exam_targets_count', 0)}"
            )

        rows = []
        for source in report.get("sources") or []:
            scores = source.get("scores") or {}
            action = source.get("recommended_action") or {}
            rows.append(
                {
                    "source_id": source.get("source_id"),
                    "title": source.get("title"),
                    "status": source.get("quality_status"),
                    "extraction": scores.get("extraction"),
                    "digest": scores.get("local_digest"),
                    "int_audit": scores.get("intermediate_audit"),
                    "final_audit": scores.get("final_audit"),
                    "study_pack": scores.get("study_pack"),
                    "activity": scores.get("study_activity"),
                    "next_action": action.get("label"),
                }
            )
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No sources registered for this course.")

        warnings = report.get("top_warnings") or []
        needs_attention = (
            int(report.get("needs_review_count", 0)) > 0
            or int(report.get("failed_count", 0)) > 0
        )
        if warnings:
            st.subheader("Warnings")
            for warning in warnings:
                st.warning(warning)
        if needs_attention:
            st.info(
                "Use **Evidence Trace** to inspect source chunks, digests, and audits."
            )

        actions = report.get("recommended_next_actions") or []
        if actions:
            st.subheader("Course recommendations")
            for action in actions:
                sources_text = ", ".join(action.get("source_ids") or [])
                st.write(f"- **{action.get('label', '')}** ({sources_text})")

        course_path = resolve_course_path(course_name)
        _, md_path = get_course_quality_report_paths(course_path)
        if md_path.is_file():
            with st.expander("Preview exported Markdown report"):
                st.text(md_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _show_exception(exc)


def page_evidence_trace(course_name: str | None) -> None:
    _render_page_intro("evidence_trace")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="evidence_trace_source")
    if not source_id:
        return

    try:
        summary = get_source_trace_summary(course_name, source_id)
    except Exception as exc:
        _show_exception(exc)
        return

    st.subheader("Source Trace Summary")
    st.write(f"**{summary.get('source_id')}** — {summary.get('title', '')}")
    st.write(f"Registry status: `{summary.get('registry_status', '')}`")

    artifacts = summary.get("available_artifacts") or {}
    cols = st.columns(5)
    artifact_keys = list(artifacts.keys())
    for index, key in enumerate(artifact_keys):
        cols[index % 5].write(f"{'✅' if artifacts[key] else '⏳'} {key.replace('_', ' ')}")

    paths = summary.get("paths") or {}
    with st.expander("Important paths"):
        for key, value in paths.items():
            if value:
                st.write(f"**{key}:** `{value}`")

    for warning in summary.get("warnings") or []:
        st.warning(warning)

    st.subheader("Chunk Viewer")
    chunks = list_source_chunks(course_name, source_id)
    if not chunks:
        st.info("Chunk this source first on **Pipeline** to inspect chunk-level evidence.")
        return

    labels = [
        f"{chunk['chunk_id']} — pages {chunk.get('page_start')}–{chunk.get('page_end')} — "
        f"{chunk.get('word_count', 0)} words"
        for chunk in chunks
    ]
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    selected_index = st.selectbox(
        "Select chunk",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key=f"evidence_chunk_{source_id}",
    )
    selected_chunk_id = chunk_ids[selected_index]

    try:
        trace = get_chunk_trace(course_name, source_id, selected_chunk_id)
    except Exception as exc:
        _show_exception(exc)
        return

    tab_source, tab_digest, tab_review, tab_ia, tab_fa, tab_export = st.tabs(
        [
            "Source Chunk",
            "Local Digest Chunk",
            "Digest Review Mentions",
            "Intermediate Audit Mentions",
            "Final Audit Mentions",
            "Export",
        ]
    )

    source_chunk = trace.get("source_chunk") or {}
    digest_chunk = trace.get("local_digest_chunk") or {}

    with tab_source:
        st.caption(source_chunk.get("path", ""))
        st.text_area(
            "Source chunk",
            read_text_preview(Path(source_chunk.get("path", "")), max_chars=12000)
            if source_chunk.get("exists")
            else "(missing)",
            height=400,
            key=f"evidence_source_{selected_chunk_id}",
        )

    with tab_digest:
        st.caption(digest_chunk.get("path", ""))
        st.text_area(
            "Local digest chunk",
            read_text_preview(Path(digest_chunk.get("path", "")), max_chars=12000)
            if digest_chunk.get("exists")
            else "(missing)",
            height=400,
            key=f"evidence_digest_{selected_chunk_id}",
        )

    def _render_mentions(mentions: list[dict]) -> None:
        if not mentions:
            st.write("No mentions found.")
            return
        for mention in mentions:
            st.write(f"**Line {mention.get('line_number', '?')}:** `{mention.get('match_line', '')}`")
            st.text(mention.get("snippet", ""))

    with tab_review:
        _render_mentions(trace.get("digest_review_mentions") or [])

    with tab_ia:
        _render_mentions(trace.get("intermediate_audit_mentions") or [])

    with tab_fa:
        _render_mentions(trace.get("final_audit_mentions") or [])

    with tab_export:
        if st.button("Export evidence trace", key=f"evidence_export_{selected_chunk_id}"):
            try:
                path = export_chunk_trace(course_name, source_id, selected_chunk_id)
                st.success(f"Exported to `{path}`")
                st.text(path.read_text(encoding="utf-8"))
            except Exception as exc:
                _show_exception(exc)


def page_dashboard(course_name: str | None) -> None:
    _render_page_intro("dashboard")
    if not course_name:
        st.info("Create or select a course first.")
        return

    st.subheader(course_name)
    try:
        course_path = resolve_course_path(course_name)
        sources = list_sources(course_name)
    except Exception as exc:
        _show_exception(exc)
        return

    st.write(f"**Sources:** {len(sources)}")

    if not sources:
        st.info("No sources yet. Add a source PDF from the **Sources** page.")
        return

    rows = []
    for entry in sources:
        flags = source_pipeline_flags(entry)
        rows.append(
            {
                "ID": entry.get("id"),
                "Title": entry.get("title"),
                "Type": entry.get("source_type"),
                "Status": entry.get("status"),
                "Extracted": yes_no(flags["extracted"]),
                "Chunked": yes_no(flags["chunked"]),
                "Local digest": yes_no(flags["local_digest"]),
                "Intermediate audit": yes_no(flags["intermediate_audit"]),
                "Final audit": yes_no(flags["final_audit"]),
            }
        )
    st.dataframe(rows, use_container_width=True)


def page_courses() -> None:
    _render_page_intro("courses")

    st.subheader("Existing courses")
    courses = list_courses()
    if courses:
        for path in courses:
            st.write(f"- `{path.name}` → `{path}`")
    else:
        st.write("No courses yet.")

    st.subheader("Create new course")
    with st.form("create_course_form"):
        code = st.text_input("Course code", placeholder="ECA1010")
        name = st.text_input("Course name", placeholder="Microeconomics")
        submitted = st.form_submit_button("Create course")
    if submitted:
        if not code.strip() or not name.strip():
            st.error("Course code and name are required.")
        else:
            try:
                path = create_course(code.strip(), name.strip())
                folder = path.name
                st.session_state.selected_course = folder
                st.success(f"Course created: {folder}")
                st.code(str(path))
            except Exception as exc:
                _show_exception(exc)

    st.subheader("Course backup")
    st.warning(
        "Backups may contain private course PDFs, extracted text, audits, and study logs. "
        "Store them safely."
    )
    course_name = st.session_state.selected_course
    if not course_name:
        st.info("Select a course in the sidebar to create or list backups.")
    else:
        st.write(f"**Selected course:** `{course_name}`")
        include_sources = st.checkbox(
            "Include source PDFs/materials",
            value=True,
            key="backup_include_sources",
        )
        output_dir_text = st.text_input(
            "Optional output directory (leave empty for course backups folder)",
            value="",
            key="backup_output_dir",
        )
        col_create, col_list = st.columns(2)
        with col_create:
            if st.button("Create backup", key="backup_create_btn"):
                try:
                    output_dir = (
                        Path(output_dir_text.strip())
                        if output_dir_text.strip()
                        else None
                    )
                    summary = create_course_backup(
                        course_name,
                        include_sources=include_sources,
                        output_dir=output_dir,
                    )
                    st.success("Backup created.")
                    st.write(f"**Files:** {summary.get('file_count', 0)}")
                    st.write(
                        f"**Size:** {format_bytes(int(summary.get('total_bytes', 0)))}"
                    )
                    st.code(summary.get("backup_path", ""))
                    for warning in summary.get("warnings") or []:
                        st.warning(warning)
                except BackupExistsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    _show_exception(exc)
        with col_list:
            if st.button("List backups", key="backup_list_btn"):
                st.session_state.show_backup_list = True

        if st.session_state.get("show_backup_list"):
            try:
                output_dir = (
                    Path(output_dir_text.strip()) if output_dir_text.strip() else None
                )
                backups = list_course_backups(
                    course_name,
                    backup_dir=output_dir,
                )
                if backups:
                    st.dataframe(
                        [
                            {
                                "file_name": entry["file_name"],
                                "size": format_bytes(int(entry["size_bytes"])),
                                "modified": entry["modified"],
                                "path": entry["path"],
                            }
                            for entry in backups
                        ],
                        use_container_width=True,
                    )
                else:
                    st.write("No backups found.")
            except Exception as exc:
                _show_exception(exc)

    st.subheader("Backup verification")
    st.warning(
        "Restore never overwrites existing course folders in v1. "
        "Backup zips may contain private course PDFs, extracted text, audits, and study logs."
    )
    verify_upload = st.file_uploader(
        "Upload backup zip to verify or restore",
        type=["zip"],
        key="backup_verify_upload",
    )
    verify_path_text = st.text_input(
        "Or enter backup zip path",
        value="",
        key="backup_verify_path",
    )
    restore_as_name = st.text_input(
        "Restore as course folder (optional new name)",
        value="",
        key="backup_restore_as",
        placeholder="ECA1010_Restored_Test",
    )

    def _resolve_backup_path() -> Path | None:
        if verify_upload is not None:
            temp_path = Path(tempfile.gettempdir()) / f"studyforge_verify_{verify_upload.name}"
            temp_path.write_bytes(verify_upload.getvalue())
            return temp_path
        if verify_path_text.strip():
            return Path(verify_path_text.strip())
        return None

    col_verify, col_preview, col_restore = st.columns(3)
    with col_verify:
        if st.button("Verify backup", key="backup_verify_btn"):
            backup_file = _resolve_backup_path()
            if backup_file is None:
                st.error("Upload a zip or enter a backup path first.")
            elif not backup_file.is_file():
                st.error(f"Backup file not found: {backup_file}")
            else:
                try:
                    report = verify_backup(backup_file)
                    st.session_state.backup_verify_report = report
                except Exception as exc:
                    _show_exception(exc)
    with col_preview:
        if st.button("Preview restore", key="backup_preview_btn"):
            backup_file = _resolve_backup_path()
            if backup_file is None:
                st.error("Upload a zip or enter a backup path first.")
            elif not backup_file.is_file():
                st.error(f"Backup file not found: {backup_file}")
            else:
                try:
                    preview = preview_restore_backup(backup_file)
                    st.session_state.backup_preview_report = preview
                except Exception as exc:
                    _show_exception(exc)
    with col_restore:
        if st.button("Restore to new course folder", key="backup_restore_btn"):
            backup_file = _resolve_backup_path()
            if backup_file is None:
                st.error("Upload a zip or enter a backup path first.")
            elif not backup_file.is_file():
                st.error(f"Backup file not found: {backup_file}")
            else:
                try:
                    target_name = restore_as_name.strip() or None
                    summary = restore_backup_to_new_course(
                        backup_file,
                        target_course_name=target_name,
                    )
                    st.session_state.backup_restore_summary = summary
                    st.session_state.selected_course = summary.get("course_folder")
                except RestoreTargetExistsError as exc:
                    st.error(str(exc))
                except InvalidBackupError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    _show_exception(exc)

    verify_report = st.session_state.get("backup_verify_report")
    if verify_report:
        st.write("**Verification summary**")
        st.write(f"Status: `{verify_report.get('status', 'unknown')}`")
        st.write(f"Course folder: `{verify_report.get('course_folder') or '(none)'}`")
        st.write(f"Files: {verify_report.get('file_count', 0)}")
        st.write(
            f"Size: {format_bytes(int(verify_report.get('total_bytes', 0)))}"
        )
        missing = verify_report.get("missing_expected_paths") or []
        if missing:
            st.write("Missing paths:")
            for item in missing:
                st.write(f"- `{item}`")
        for warning in verify_report.get("warnings") or []:
            st.warning(warning)
        for error in verify_report.get("errors") or []:
            st.error(error)

    preview_report = st.session_state.get("backup_preview_report")
    if preview_report:
        st.write("**Restore preview**")
        st.write(f"Target path: `{preview_report.get('target_path', '')}`")
        st.write(f"Target exists: `{preview_report.get('target_exists')}`")
        st.write(
            f"Would restore files: {preview_report.get('would_restore_files', 0)}"
        )
        st.write(
            f"Safe to restore: `{preview_report.get('safe_to_restore')}`"
        )
        for warning in preview_report.get("warnings") or []:
            st.warning(warning)

    restore_summary = st.session_state.get("backup_restore_summary")
    if restore_summary:
        st.success("Restore complete.")
        st.write(f"Course folder: `{restore_summary.get('course_folder')}`")
        st.write(f"Files restored: {restore_summary.get('files_restored', 0)}")
        st.code(restore_summary.get("target_path", ""))


def page_sources(course_name: str | None) -> None:
    _render_page_intro("sources")
    if not _require_course():
        return

    st.subheader("Registered sources")
    sources = _source_options(course_name)
    if not sources:
        st.info("No sources yet. Upload a PDF below to register your first source.")
    if sources:
        st.dataframe(
            [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "type": s.get("source_type"),
                    "status": s.get("status"),
                    "file": s.get("file_name"),
                }
                for s in sources
            ],
            use_container_width=True,
        )

    st.subheader("Add source (PDF)")
    uploaded = st.file_uploader("PDF file", type=["pdf"])
    source_type = st.selectbox("Source type", SOURCE_TYPES)
    title = st.text_input("Title (optional)", placeholder="Main Textbook")

    if st.button("Add source", disabled=uploaded is None):
        if uploaded is None:
            st.error("Upload a PDF first.")
            return
        suffix = Path(uploaded.name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue())
            temp_path = Path(tmp.name)
        try:
            stored = add_source(
                course_name=course_name,
                source_type=source_type,
                file_path=temp_path,
                title=title or None,
            )
            st.success("Source added.")
            st.write(f"**Stored at:** `{stored}`")
            st.rerun()
        except Exception as exc:
            _show_exception(exc)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def page_pipeline(course_name: str | None) -> None:
    _render_page_intro("pipeline")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="pipeline_source")
    if not source_id:
        return

    _render_guided_workflow(course_name, source_id)
    pipeline_status = _render_pipeline_doctor(course_name, source_id)
    _render_study_pack(course_name, source_id, pipeline_status)
    _render_extraction_quality(course_name, source_id)

    st.subheader("Manual pipeline controls")
    st.caption("Run individual steps yourself (same backend as Guided Workflow).")

    st.subheader("LM Studio")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.lm_base_url = st.text_input(
            "LM Studio base URL",
            value=st.session_state.lm_base_url,
        )
    with col2:
        st.session_state.lm_model = st.text_input(
            "Model (empty = first from /models)",
            value=st.session_state.lm_model,
        )
    tok1, tok2, tok3 = st.columns(3)
    with tok1:
        st.session_state.max_digest_tokens = st.number_input(
            "Max tokens per chunk",
            min_value=1000,
            max_value=32000,
            value=int(st.session_state.max_digest_tokens),
            step=500,
            help="Incomplete digests retry with +2000 tokens. Default 6000.",
        )
    with tok2:
        st.session_state.lm_temperature = st.number_input(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=float(st.session_state.lm_temperature),
            step=0.1,
        )
    with tok3:
        st.session_state.lm_timeout = st.number_input(
            "Timeout (seconds)",
            min_value=30,
            max_value=3600,
            value=int(st.session_state.lm_timeout),
            step=30,
        )

    if st.button("Check LM Studio connection"):
        result = check_lm_studio_connection(st.session_state.lm_base_url)
        if result["ok"]:
            st.success(f"Connected — {len(result['models'])} model(s)")
            for m in result["models"]:
                st.write(f"- `{m}`")
            default = choose_default_model(result)
            if default and not st.session_state.lm_model:
                st.session_state.lm_model = default
                st.info(f"Default model set to: {default}")
        else:
            st.error(result.get("error") or "Connection failed")

    st.subheader("Chunking options")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state.max_words = st.number_input(
            "Max words", min_value=100, value=int(st.session_state.max_words)
        )
    with c2:
        st.session_state.overlap_words = st.number_input(
            "Overlap words", min_value=0, value=int(st.session_state.overlap_words)
        )
    with c3:
        st.session_state.overwrite = st.checkbox(
            "Overwrite outputs", value=st.session_state.overwrite
        )

    if st.button("1. Extract PDF"):
        try:
            with st.spinner("Extracting…"):
                summary = extract_registered_source(
                    course_name,
                    source_id,
                    overwrite=st.session_state.overwrite,
                )
            st.session_state.pop(f"pipeline_status_{source_id}", None)
            _show_result_summary("Extraction complete", summary)
            quality_status = summary.get("extraction_quality_status")
            if quality_status == "failed":
                st.error(
                    "Extraction quality failed — inspect the quality report before chunking."
                )
            elif quality_status == "needs_review":
                st.warning(
                    "Extraction quality needs review — some pages may be empty or low-text."
                )
        except Exception as exc:
            _show_exception(exc)

    if st.button("2. Chunk source"):
        try:
            with st.spinner("Chunking…"):
                summary = chunk_registered_source(
                    course_name,
                    source_id,
                    max_words=int(st.session_state.max_words),
                    overlap_words=int(st.session_state.overlap_words),
                    overwrite=st.session_state.overwrite,
                )
            _show_result_summary("Chunking complete", summary)
        except Exception as exc:
            _show_exception(exc)

    st.caption(
        "After a test run (first chunk only), **Run full local digest** continues "
        "with the remaining chunks. Use **Overwrite** only to redo all chunks."
    )

    if st.button("3. Run local digest (first chunk only)"):
        try:
            with st.spinner("Running local digest (1 chunk)…"):
                summary = run_local_digest_for_source(
                    course_name,
                    source_id,
                    base_url=st.session_state.lm_base_url,
                    model=st.session_state.lm_model or None,
                    max_tokens=int(st.session_state.max_digest_tokens),
                    temperature=float(st.session_state.lm_temperature),
                    timeout=int(st.session_state.lm_timeout),
                    limit_chunks=1,
                    overwrite=st.session_state.overwrite,
                )
            _show_result_summary("Local digest complete", summary)
        except Exception as exc:
            _show_exception(exc)

    if st.button("4. Run full local digest"):
        try:
            with st.spinner("Running full local digest…"):
                summary = run_local_digest_for_source(
                    course_name,
                    source_id,
                    base_url=st.session_state.lm_base_url,
                    model=st.session_state.lm_model or None,
                    max_tokens=int(st.session_state.max_digest_tokens),
                    temperature=float(st.session_state.lm_temperature),
                    timeout=int(st.session_state.lm_timeout),
                    overwrite=st.session_state.overwrite,
                )
            _show_result_summary("Local digest complete", summary)
        except Exception as exc:
            _show_exception(exc)

    if st.button("5. Review local digest"):
        try:
            summary = review_local_digest_for_source(course_name, source_id)
            _show_result_summary("Review complete", summary)
            st.markdown(f"**Report:** `{summary.get('report_path_md', '')}`")
        except Exception as exc:
            _show_exception(exc)

    _render_file_preview(course_name, source_id)


def page_audits(course_name: str | None) -> None:
    _render_page_intro("audits")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="audit_source")
    if not source_id:
        return

    st.session_state.limit_chunks = st.number_input(
        "Limit chunks (0 = all)",
        min_value=0,
        value=int(st.session_state.limit_chunks),
    )
    st.session_state.only_needs_review = st.checkbox(
        "Only chunks needing review",
        value=st.session_state.only_needs_review,
    )
    st.session_state.overwrite = st.checkbox(
        "Overwrite packet files",
        value=st.session_state.overwrite,
        key="audit_overwrite",
    )
    limit = (
        int(st.session_state.limit_chunks)
        if int(st.session_state.limit_chunks) > 0
        else None
    )

    st.subheader("Intermediate audit")

    st.caption(
        "Automated: calls Google AI (Gemma 4) per chunk and saves a versioned audit. "
        "Export packet is optional (manual copy/paste into AI Studio)."
    )
    model_options = [DEFAULT_GEMMA_4_26B_MODEL, DEFAULT_GEMMA_4_31B_MODEL]
    if st.session_state.google_audit_model not in model_options:
        model_options.insert(0, st.session_state.google_audit_model)
    st.session_state.google_audit_model = st.selectbox(
        "Google AI model",
        model_options,
        index=model_options.index(st.session_state.google_audit_model)
        if st.session_state.google_audit_model in model_options
        else 0,
    )

    if st.button("Run intermediate audit (Google AI)"):
        if not get_google_api_key():
            st.error(
                "Google API key not set. Add it on the Settings page or set "
                "GOOGLE_API_KEY in your environment."
            )
        else:
            try:
                with st.spinner("Running intermediate audit (one API call per chunk)…"):
                    summary = run_intermediate_audit_for_source(
                        course_name,
                        source_id,
                        model=st.session_state.google_audit_model,
                        limit_chunks=limit,
                        only_needs_review=st.session_state.only_needs_review,
                    )
                _show_result_summary("Intermediate audit imported", summary)
                st.rerun()
            except Exception as exc:
                _show_exception(exc)

    if st.button("Export intermediate audit packet (manual)"):
        try:
            summary = build_intermediate_audit_packet(
                course_name,
                source_id,
                limit_chunks=limit,
                only_needs_review=st.session_state.only_needs_review,
                overwrite=st.session_state.overwrite,
            )
            _show_result_summary("Packet exported", summary)
        except Exception as exc:
            _show_exception(exc)

    st.write("Import intermediate audit")
    ia_upload = st.file_uploader("Intermediate audit file", type=["md", "txt"], key="ia_file")
    ia_text = st.text_area("Or paste intermediate audit text", height=150, key="ia_text")
    ia_notes = st.text_input("Notes (optional)", key="ia_notes")
    if st.button("Import intermediate audit"):
        if ia_upload and ia_text.strip():
            st.error("Provide either a file or pasted text, not both.")
        elif not ia_upload and not ia_text.strip():
            st.error("Provide a file or pasted text.")
        else:
            try:
                if ia_upload:
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=Path(ia_upload.name).suffix
                    ) as tmp:
                        tmp.write(ia_upload.getvalue())
                        path = Path(tmp.name)
                    summary = import_intermediate_audit(
                        course_name,
                        source_id,
                        audit_file=path,
                        notes=ia_notes or None,
                    )
                    path.unlink(missing_ok=True)
                else:
                    summary = import_intermediate_audit(
                        course_name,
                        source_id,
                        audit_text=ia_text,
                        notes=ia_notes or None,
                    )
                _show_result_summary("Intermediate audit imported", summary)
                st.rerun()
            except Exception as exc:
                _show_exception(exc)

    st.subheader("Final Audit Normalizer")
    st.caption(
        "Map messy final audit headings to the exact StudyForge template (no AI). "
        "Use before generating a study pack if diagnostics report weak quality."
    )
    fa_norm_overwrite = st.checkbox(
        "Overwrite normalizer outputs",
        value=False,
        key=f"fa_norm_overwrite_{source_id}",
    )
    ncol1, ncol2, ncol3 = st.columns(3)
    with ncol1:
        if st.button("Diagnose / normalize", key=f"fa_norm_{source_id}"):
            try:
                summary = normalize_latest_final_audit(
                    course_name,
                    source_id,
                    overwrite=fa_norm_overwrite,
                )
                st.session_state[f"fa_norm_result_{source_id}"] = summary
                st.rerun()
            except (NormalizedAuditExistsError, FinalAuditNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)
    with ncol2:
        if st.button("Normalize & import new version", key=f"fa_norm_import_{source_id}"):
            try:
                summary = normalize_latest_final_audit(
                    course_name,
                    source_id,
                    overwrite=fa_norm_overwrite,
                    import_as_new_version=True,
                )
                st.session_state[f"fa_norm_result_{source_id}"] = summary
                st.session_state.pop(f"pipeline_status_{source_id}", None)
                st.rerun()
            except (NormalizedAuditExistsError, FinalAuditNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)
    with ncol3:
        if st.button("Export repair packet", key=f"fa_repair_{source_id}"):
            try:
                summary = build_final_audit_repair_packet(
                    course_name,
                    source_id,
                    overwrite=fa_norm_overwrite,
                )
                st.success(f"Repair packet: `{summary['repair_packet_path']}`")
            except (RepairPacketExistsError, FinalAuditNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    norm_result = st.session_state.get(f"fa_norm_result_{source_id}")
    if norm_result:
        status = norm_result.get("quality_status", "unknown")
        if status == "ok":
            st.success(f"Normalization quality: {status}")
        elif status == "needs_review":
            st.warning(f"Normalization quality: {status}")
        else:
            st.error(f"Normalization quality: {status}")
        st.write(f"**Mapped:** {norm_result.get('mapped_count', 0)} headings")
        if norm_result.get("missing_headings"):
            st.write(
                "**Missing:** "
                + ", ".join(norm_result["missing_headings"][:8])
            )
        for warning in norm_result.get("warnings") or []:
            st.caption(warning)
        if norm_result.get("normalized_path"):
            path = Path(norm_result["normalized_path"])
            if path.is_file():
                st.text_area(
                    "Normalized preview",
                    read_text_preview(path, max_chars=6000),
                    height=200,
                    key=f"fa_norm_preview_{source_id}",
                )
        if norm_result.get("imported_audit_id"):
            st.info(f"Imported as {norm_result['imported_audit_id']}")

    st.subheader("Final audit")
    if st.button("Export final audit packet"):
        try:
            summary = build_final_audit_packet(
                course_name,
                source_id,
                limit_chunks=limit,
                only_needs_review=st.session_state.only_needs_review,
                overwrite=st.session_state.overwrite,
            )
            _show_result_summary("Packet exported", summary)
        except Exception as exc:
            _show_exception(exc)

    st.write("Import final audit")
    fa_upload = st.file_uploader("Final audit file", type=["md", "txt"], key="fa_file")
    fa_text = st.text_area("Or paste final audit text", height=150, key="fa_text")
    fa_notes = st.text_input("Notes (optional)", key="fa_notes")
    if st.button("Import final audit"):
        if fa_upload and fa_text.strip():
            st.error("Provide either a file or pasted text, not both.")
        elif not fa_upload and not fa_text.strip():
            st.error("Provide a file or pasted text.")
        else:
            try:
                if fa_upload:
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=Path(fa_upload.name).suffix
                    ) as tmp:
                        tmp.write(fa_upload.getvalue())
                        path = Path(tmp.name)
                    summary = import_final_audit(
                        course_name,
                        source_id,
                        audit_file=path,
                        notes=fa_notes or None,
                    )
                    path.unlink(missing_ok=True)
                else:
                    summary = import_final_audit(
                        course_name,
                        source_id,
                        audit_text=fa_text,
                        notes=fa_notes or None,
                    )
                _show_result_summary("Final audit imported", summary)
                st.rerun()
            except Exception as exc:
                _show_exception(exc)

    _render_file_preview(course_name, source_id)


def _render_file_preview(course_name: str, source_id: str) -> None:
    st.subheader("File preview")
    try:
        sources = {s["id"]: s for s in list_sources(course_name)}
        entry = sources.get(source_id)
        if not entry:
            return
        paths = [
            ("Extracted text", entry.get("extracted_text_path")),
            ("Combined digest", entry.get("local_digest_path")),
            ("Digest review", None),
            ("Intermediate packet", None),
            ("Latest intermediate audit", entry.get("latest_intermediate_audit_path")),
            ("Final packet", None),
            ("Latest final audit", entry.get("latest_final_audit_path")),
        ]
        course_path = resolve_course_path(course_name)
        review_path = (
            course_path
            / "03_Local_Digests"
            / source_id
            / f"{source_id}_local_digest_review.md"
        )
        paths[2] = ("Digest review", str(review_path) if review_path.is_file() else None)

        pick_labels = [p[0] for p in paths if p[1]]
        pick_map = {p[0]: p[1] for p in paths if p[1]}
        if not pick_labels:
            st.info("No output files to preview yet.")
            return
        label = st.selectbox("Preview file", pick_labels)
        path = Path(pick_map[label])
        st.code(str(path))
        if path.suffix.lower() in {".md", ".txt", ".json"}:
            st.text_area("Content", read_text_preview(path), height=300)
    except Exception as exc:
        _show_exception(exc)


def page_study_units(course_name: str | None) -> None:
    _render_page_intro("study_units")
    if not _require_course():
        return

    st.caption(
        "Group sources by topic or exam. The unit dashboard aggregates readiness "
        "and review items per unit. No AI synthesis or merged study packs yet."
    )

    try:
        units = list_study_units(course_name)
    except Exception as exc:
        _show_exception(exc)
        return

    st.subheader("Study units")
    if units:
        rows = []
        for unit in units:
            rows.append(
                {
                    "Unit ID": unit.get("unit_id", ""),
                    "Title": unit.get("title", ""),
                    "Sources": ", ".join(unit.get("source_ids", [])),
                    "Status": unit.get("status", "active"),
                    "Tags": ", ".join(unit.get("tags", [])),
                }
            )
        st.dataframe(rows, use_container_width=True)
    else:
        st.info(
            "No study units yet. Create one below to group related sources "
            "(textbook chapter + slides + homework)."
        )

    st.subheader("Create unit")
    sources = _source_options(course_name)
    source_labels = [
        f"{s.get('id', '?')} — {s.get('title', 'Untitled')}" for s in sources
    ]
    source_ids = [s.get("id", "") for s in sources]
    with st.form("create_study_unit_form", clear_on_submit=True):
        new_title = st.text_input("Title", placeholder="Inflation and CPI")
        new_description = st.text_area(
            "Description",
            placeholder="Prepare for Quiz 2",
        )
        selected_sources = st.multiselect(
            "Sources",
            options=source_labels,
            default=[],
        )
        new_tags = st.text_input(
            "Tags (comma-separated)",
            placeholder="quiz2, inflation",
        )
        submitted = st.form_submit_button("Create unit")
    if submitted:
        if not new_title.strip():
            st.error("Enter a title first.")
        else:
            try:
                picked_ids = [
                    source_ids[source_labels.index(label)]
                    for label in selected_sources
                    if label in source_labels
                ]
                tags = [
                    tag.strip()
                    for tag in new_tags.split(",")
                    if tag.strip()
                ]
                unit = create_study_unit(
                    course_name,
                    new_title.strip(),
                    description=new_description.strip() or None,
                    source_ids=picked_ids,
                    tags=tags,
                )
                st.success(f"Created `{unit['unit_id']}` — {unit['title']}")
                st.rerun()
            except InvalidSourceIdError as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    if not units:
        return

    st.subheader("Unit details")
    unit_labels = [
        f"{unit.get('unit_id', '')} — {unit.get('title', '')}" for unit in units
    ]
    unit_map = {label: unit for label, unit in zip(unit_labels, units)}
    picked_label = st.selectbox("Select unit", unit_labels, key="su_pick_unit")
    picked_unit = unit_map[picked_label]
    unit_id = picked_unit.get("unit_id", "")

    try:
        dashboard = get_study_unit_dashboard(course_name, unit_id)
    except Exception as exc:
        _show_exception(exc)
        return

    st.subheader("Unit Dashboard")
    st.write(f"**Description:** {dashboard.get('description') or '—'}")
    review = dashboard.get("review_summary") or {}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Due flashcards", review.get("due_flashcards", 0))
    m2.metric("Active recall", review.get("active_recall_needs_review", 0))
    m3.metric("Open mistakes", review.get("open_mistakes", 0))
    m4.metric("Open weak points", review.get("open_weak_points", 0))
    st.write(
        f"**Ready sources:** {dashboard.get('ready_sources', 0)} · "
        f"**Incomplete:** {dashboard.get('incomplete_sources', 0)}"
    )
    if dashboard.get("has_unit_synthesis"):
        st.write(
            f"**Latest synthesis:** `{dashboard.get('latest_synthesis_id', '')}` "
            f"({dashboard.get('latest_synthesis_quality', 'unknown')})"
        )
        if dashboard.get("latest_synthesis_path"):
            st.caption(f"Synthesis path: `{dashboard['latest_synthesis_path']}`")
    else:
        st.caption("No unit synthesis imported yet.")

    if dashboard.get("has_unit_study_pack"):
        st.write(
            f"**Unit study pack:** quality "
            f"`{dashboard.get('latest_unit_study_pack_quality', 'unknown')}` "
            f"(based on `{dashboard.get('based_on_unit_synthesis_id', '')}`)"
        )
        if dashboard.get("latest_unit_study_pack_manifest_path"):
            st.caption(f"Manifest: `{dashboard['latest_unit_study_pack_manifest_path']}`")
        try:
            review_counts = get_unit_review_counts(course_name, unit_id)
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Unit recall questions", review_counts.get("unit_question_count", 0))
            rc2.metric("Unit flashcards", review_counts.get("unit_flashcard_count", 0))
            rc3.metric("Unit recall gaps", review_counts.get("unit_recall_gaps", 0))
            rc4.metric("Unit flashcards due", review_counts.get("unit_due_flashcards", 0))
        except Exception:
            pass
    else:
        st.caption("No unit study pack generated yet.")

    action = dashboard.get("recommended_action") or {}
    st.info(f"**Recommended:** {action.get('label', '')} — {action.get('reason', '')}")
    if action.get("key") == "process_incomplete_sources":
        st.caption("Process incomplete sources from the **Pipeline** page.")

    source_rows = []
    for source in dashboard.get("sources") or []:
        source_rows.append(
            {
                "Source": source.get("source_id", ""),
                "Title": source.get("title", ""),
                "Status": source.get("status", ""),
                "Study pack": "yes" if source.get("has_study_pack") else "no",
                "Next action": source.get("recommended_action", ""),
                "Study guide": "yes" if source.get("final_study_guide_path") else "no",
                "Flashcards": "yes" if source.get("flashcards_path") else "no",
                "Active recall": "yes" if source.get("active_recall_path") else "no",
            }
        )
    if source_rows:
        st.dataframe(source_rows, use_container_width=True)
    else:
        st.info("No sources in this unit yet.")

    for warning in dashboard.get("warnings") or []:
        st.warning(warning)

    dash_col1, dash_col2 = st.columns(2)
    with dash_col1:
        if st.button("Export unit dashboard", key=f"su_export_dash_{unit_id}"):
            try:
                result = export_unit_dashboard(course_name, unit_id)
                st.success(f"Exported: `{result['markdown_path']}`")
                st.rerun()
            except Exception as exc:
                _show_exception(exc)
    with dash_col2:
        if st.button("Start unit study session", key=f"su_start_session_{unit_id}"):
            try:
                result = start_study_session(course_name, limit=10, unit_id=unit_id)
                st.session_state[f"study_session_{course_name}"] = (
                    get_latest_study_session(course_name)
                )
                st.success(
                    f"Started unit session `{result['session_id']}` with "
                    f"{result['item_count']} items. Open **Study Session** to continue."
                )
                if result.get("warning"):
                    st.warning(result["warning"])
            except Exception as exc:
                _show_exception(exc)
        plan_overwrite = st.checkbox(
            "Overwrite unit review plan",
            value=False,
            key=f"su_plan_overwrite_{unit_id}",
        )
        if st.button("Generate unit review plan", key=f"su_gen_plan_{unit_id}"):
            try:
                result = generate_unit_review_plan(
                    course_name,
                    unit_id,
                    overwrite=plan_overwrite,
                )
                st.success(f"Plan written: `{result['markdown_path']}`")
                st.rerun()
            except UnitReviewPlanExistsError as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    st.subheader("Unit Synthesis Packet")
    st.warning(
        "This packet is meant for manual use with a stronger AI. "
        "StudyForge does not call external AI here."
    )
    synth_include_state = st.checkbox(
        "Include learning state",
        value=True,
        key=f"su_synth_state_{unit_id}",
    )
    synth_overwrite = st.checkbox(
        "Overwrite synthesis packet",
        value=False,
        key=f"su_synth_overwrite_{unit_id}",
    )
    if st.button("Export synthesis packet", key=f"su_synth_export_{unit_id}"):
        try:
            result = build_unit_synthesis_packet(
                course_name,
                unit_id,
                include_learning_state=synth_include_state,
                overwrite=synth_overwrite,
            )
            st.success(f"Packet exported: `{result['packet_path']}`")
            if result.get("warnings"):
                for warning in result["warnings"]:
                    st.warning(warning)
            st.rerun()
        except UnitSynthesisPacketExistsError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    try:
        course_path = resolve_course_path(course_name)
        synth_md, _ = get_unit_synthesis_packet_paths(course_path, unit_id)
        if synth_md.is_file():
            st.caption(f"Synthesis packet: `{synth_md}`")
            with st.expander("Synthesis packet preview", expanded=False):
                st.text_area(
                    "Packet Markdown",
                    read_text_preview(synth_md, max_chars=12000),
                    height=280,
                    key=f"su_synth_preview_{unit_id}",
                )
    except Exception:
        pass

    st.subheader("Import Unit Synthesis")
    st.caption(
        "Paste the unified synthesis from ChatGPT/Gemini after using the export packet. "
        "StudyForge stores a new version each time; older versions are kept."
    )
    synth_upload = st.file_uploader(
        "Upload synthesis (.md or .txt)",
        type=["md", "txt"],
        key=f"su_synth_upload_{unit_id}",
    )
    synth_paste = st.text_area(
        "Or paste synthesis text",
        height=200,
        key=f"su_synth_paste_{unit_id}",
    )
    synth_name = st.text_input(
        "Synthesizer name",
        value="ChatGPT",
        key=f"su_synth_name_{unit_id}",
    )
    synth_notes = st.text_input(
        "Notes (optional)",
        key=f"su_synth_notes_{unit_id}",
    )
    if st.button("Import synthesis", key=f"su_synth_import_{unit_id}"):
        try:
            has_file = synth_upload is not None
            has_paste = bool(synth_paste.strip())
            if has_file and has_paste:
                st.error("Provide either a file upload or pasted text, not both.")
            elif not has_file and not has_paste:
                st.error("Upload a file or paste synthesis text.")
            else:
                if has_file:
                    content = synth_upload.read().decode("utf-8")
                    result = import_unit_synthesis(
                        course_name,
                        unit_id,
                        synthesis_text=content,
                        synthesizer_name=synth_name,
                        notes=synth_notes or None,
                    )
                else:
                    result = import_unit_synthesis(
                        course_name,
                        unit_id,
                        synthesis_text=synth_paste,
                        synthesizer_name=synth_name,
                        notes=synth_notes or None,
                    )
                st.success(
                    f"Imported `{result['synthesis_id']}` "
                    f"(quality: {result.get('quality_status', '')})."
                )
                if result.get("warnings"):
                    for warning in result["warnings"]:
                        st.warning(warning)
                st.rerun()
        except Exception as exc:
            _show_exception(exc)

    latest_path = dashboard.get("latest_synthesis_path", "")
    if latest_path and Path(latest_path).is_file():
        with st.expander("Latest synthesis preview", expanded=False):
            st.text_area(
                "Synthesis Markdown",
                read_text_preview(Path(latest_path), max_chars=12000),
                height=280,
                key=f"su_synth_latest_{unit_id}",
            )

    st.subheader("Unit Study Pack")
    if not dashboard.get("has_unit_synthesis"):
        st.info("Import a unit synthesis before generating a unit study pack.")
    else:
        pack_overwrite = st.checkbox(
            "Overwrite unit study pack",
            value=False,
            key=f"su_pack_overwrite_{unit_id}",
        )
        diag_col, gen_col = st.columns(2)
        with diag_col:
            if st.button("Diagnose unit synthesis for study pack", key=f"su_pack_diag_{unit_id}"):
                try:
                    diag = diagnose_unit_study_pack(course_name, unit_id)
                    st.write(
                        f"Quality: **{diag['quality'].get('quality_status', '')}** "
                        f"({diag['quality'].get('total_extracted_words', 0)} words)"
                    )
                    for warning in diag.get("warnings") or []:
                        st.warning(warning)
                except Exception as exc:
                    _show_exception(exc)
        with gen_col:
            if st.button("Generate unit study pack", key=f"su_pack_gen_{unit_id}"):
                try:
                    result = generate_unit_study_pack(
                        course_name,
                        unit_id,
                        overwrite=pack_overwrite,
                    )
                    st.success(
                        f"Generated unit study pack (quality: "
                        f"{result.get('quality_status', '')}, "
                        f"{result.get('flashcard_count', 0)} flashcards)."
                    )
                    if result.get("warnings"):
                        for warning in result["warnings"]:
                            st.warning(warning)
                    st.rerun()
                except UnitStudyPackOutputExistsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    _show_exception(exc)

        guide_path = dashboard.get("latest_unit_study_guide_path", "")
        if guide_path and Path(guide_path).is_file():
            with st.expander("Unit study guide preview", expanded=False):
                st.text_area(
                    "Unit study guide",
                    read_text_preview(Path(guide_path), max_chars=12000),
                    height=280,
                    key=f"su_pack_guide_{unit_id}",
                )
        paths_lines = []
        for label, key in (
            ("Flashcards", "latest_unit_flashcards_path"),
            ("Active recall", "latest_unit_active_recall_path"),
            ("Manifest", "latest_unit_study_pack_manifest_path"),
        ):
            p = dashboard.get(key, "")
            if p:
                paths_lines.append(f"- **{label}:** `{p}`")
        if paths_lines:
            st.caption("Unit study pack paths:\n" + "\n".join(paths_lines))

    try:
        course_path = resolve_course_path(course_name)
        md_path, _ = get_unit_dashboard_paths(course_path, unit_id)
        if md_path.is_file():
            with st.expander("Exported dashboard preview", expanded=False):
                st.text_area(
                    "Dashboard Markdown",
                    read_text_preview(md_path, max_chars=12000),
                    height=240,
                    key=f"su_dash_preview_{unit_id}",
                )
    except Exception:
        pass

    st.subheader("Edit unit")
    status_options = ["active", "paused", "completed", "archived"]
    current_status = str(picked_unit.get("status", "active")).lower()
    if current_status not in status_options:
        current_status = "active"
    new_status = st.selectbox(
        "Status",
        status_options,
        index=status_options.index(current_status),
        key=f"su_status_{unit_id}",
    )
    if st.button("Update status", key=f"su_update_status_{unit_id}"):
        try:
            update_study_unit(course_name, unit_id, status=new_status)
            st.success(f"Updated `{unit_id}` status to {new_status}.")
            st.rerun()
        except (InvalidStudyUnitStatusError, StudyUnitNotFoundError) as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    available_to_add = [
        label
        for label, sid in zip(source_labels, source_ids)
        if sid not in picked_unit.get("source_ids", [])
    ]
    if available_to_add:
        to_add = st.multiselect(
            "Add sources",
            options=available_to_add,
            key=f"su_add_{unit_id}",
        )
        if st.button("Add selected sources", key=f"su_add_btn_{unit_id}"):
            try:
                add_ids = [
                    source_ids[source_labels.index(label)]
                    for label in to_add
                ]
                add_sources_to_unit(course_name, unit_id, add_ids)
                st.success("Sources added.")
                st.rerun()
            except InvalidSourceIdError as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    in_unit_labels = [
        label
        for label, sid in zip(source_labels, source_ids)
        if sid in picked_unit.get("source_ids", [])
    ]
    if in_unit_labels:
        to_remove = st.multiselect(
            "Remove sources",
            options=in_unit_labels,
            key=f"su_remove_{unit_id}",
        )
        if st.button("Remove selected sources", key=f"su_remove_btn_{unit_id}"):
            try:
                remove_ids = [
                    source_ids[source_labels.index(label)]
                    for label in to_remove
                ]
                remove_sources_from_unit(course_name, unit_id, remove_ids)
                st.success("Sources removed.")
                st.rerun()
            except Exception as exc:
                _show_exception(exc)


def page_active_recall(course_name: str | None) -> None:
    _render_page_intro("active_recall")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="ar_source")
    if not source_id:
        return

    try:
        questions = load_questions_for_source(course_name, source_id)
        summary = summarize_active_recall_log(course_name, source_id)
    except ActiveRecallNotReadyError as exc:
        st.warning(str(exc))
        st.info(
            "Generate a study pack from the **Pipeline** page before using Active Recall."
        )
        return
    except Exception as exc:
        _show_exception(exc)
        return

    if not questions:
        st.warning("No questions found in the active recall file.")
        return

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Attempts", summary["attempt_count"])
    c2.metric("Correct", summary["correct"])
    c3.metric("Partial", summary["partial"])
    c4.metric("Wrong", summary["wrong"])
    c5.metric("Skipped", summary["skipped"])
    c6.metric("Accuracy %", summary["accuracy_percent"])

    labels = [
        f"#{q['question_number']} — {q['question'][:80]}"
        for q in questions
    ]
    id_by_label = {labels[i]: questions[i] for i in range(len(questions))}

    col_sel, col_next = st.columns([3, 1])
    with col_sel:
        chosen_label = st.selectbox("Question", labels, key=f"ar_q_select_{source_id}")
    with col_next:
        st.write("")
        if st.button("Next unanswered", key=f"ar_next_{source_id}"):
            course_path = resolve_course_path(course_name)
            log = load_active_recall_log(
                get_active_recall_log_path(course_path, source_id)
            )
            next_q = get_first_unanswered_question(questions, log)
            if next_q:
                st.session_state[f"ar_q_select_{source_id}"] = (
                    f"#{next_q['question_number']} — {next_q['question'][:80]}"
                )
                st.rerun()
            st.info("Every question has at least one attempt recorded.")

    current = id_by_label[chosen_label]
    st.subheader(f"Question {current['question_number']}")
    st.write(current["question"])
    st.caption(f"ID: `{current['question_id']}`")

    user_answer = st.text_area(
        "Your answer",
        height=120,
        key=f"ar_answer_{source_id}_{current['question_id']}",
    )
    grade = st.selectbox(
        "Grade",
        ["correct", "partial", "wrong", "skipped"],
        key=f"ar_grade_{source_id}_{current['question_id']}",
    )
    notes = st.text_input(
        "Notes (optional)",
        key=f"ar_notes_{source_id}_{current['question_id']}",
    )

    if st.button("Save attempt", key=f"ar_save_{source_id}"):
        try:
            result = record_active_recall_attempt(
                course_name,
                source_id,
                current["question_id"],
                current["question"],
                user_answer,
                grade,
                notes=notes or None,
            )
            st.success(
                f"Saved {result['attempt_id']} — grade: {result['grade']}"
            )
            st.rerun()
        except InvalidGradeError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    if st.button("Export summary", key=f"ar_export_{source_id}"):
        try:
            path = export_active_recall_summary_markdown(course_name, source_id)
            st.success(f"Summary exported: `{path}`")
        except Exception as exc:
            _show_exception(exc)


def page_flashcards(course_name: str | None) -> None:
    _render_page_intro("flashcards")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="fc_source")
    if not source_id:
        return

    try:
        cards = load_flashcards_for_source(course_name, source_id)
        summary = summarize_flashcard_reviews(course_name, source_id)
    except FlashcardsNotReadyError as exc:
        st.warning(str(exc))
        st.info(
            "Generate a study pack from the **Pipeline** page before using Flashcards."
        )
        return
    except Exception as exc:
        _show_exception(exc)
        return

    if not cards:
        st.warning("No flashcards found in the CSV export.")
        return

    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
    c1.metric("Cards", len(cards))
    c2.metric("Reviews", summary["review_count"])
    c3.metric("Due", summary.get("due_count", 0))
    c4.metric("Easy", summary["easy"])
    c5.metric("Good", summary["good"])
    c6.metric("Hard", summary["hard"])
    c7.metric("Forgot", summary["forgot"])
    c8.metric("Needs review", summary["needs_review_count"])

    due_cards = collect_due_flashcards(course_name, source_id=source_id)
    if due_cards:
        st.subheader("Cards due for review")
        for card in due_cards[:10]:
            st.write(
                f"- `{card['card_id']}` · **{card.get('latest_grade', card.get('grade', ''))}** "
                f"· due **{card.get('due_date', '')}** · {card.get('front', '')[:80]}"
            )
        if len(due_cards) > 10:
            st.caption(f"… and {len(due_cards) - 10} more due cards.")

    labels = [f"{card['card_id']} — {card['front'][:70]}" for card in cards]
    id_by_label = {labels[i]: cards[i] for i in range(len(cards))}

    col_sel, col_next = st.columns([3, 1])
    with col_sel:
        chosen_label = st.selectbox("Card", labels, key=f"fc_select_{source_id}")
    with col_next:
        st.write("")
        if st.button("Next unreviewed", key=f"fc_next_{source_id}"):
            course_path = resolve_course_path(course_name)
            log = load_flashcard_review_log(
                get_flashcard_review_log_path(course_path, source_id),
                source_id,
            )
            next_card = get_first_unreviewed_card(cards, log)
            if next_card:
                st.session_state[f"fc_select_{source_id}"] = (
                    f"{next_card['card_id']} — {next_card['front'][:70]}"
                )
                st.session_state[
                    f"fc_revealed_{source_id}_{next_card['card_id']}"
                ] = False
                st.rerun()
            st.info("Every card has at least one review recorded.")

    current = id_by_label[chosen_label]
    card_id = current["card_id"]
    reveal_key = f"fc_revealed_{source_id}_{card_id}"
    if reveal_key not in st.session_state:
        st.session_state[reveal_key] = False

    st.subheader("Front")
    st.write(current["front"])
    st.caption(f"ID: `{card_id}` · Section: {current.get('section', '')}")

    if not st.session_state[reveal_key]:
        if st.button("Reveal answer", key=f"fc_reveal_{source_id}_{card_id}"):
            st.session_state[reveal_key] = True
            st.rerun()
    else:
        st.subheader("Back")
        st.write(current["back"])

    grade = st.selectbox(
        "Grade",
        ["easy", "good", "hard", "forgot", "skipped"],
        key=f"fc_grade_{source_id}_{card_id}",
    )
    notes = st.text_input("Notes", key=f"fc_notes_{source_id}_{card_id}")
    create_weak = st.checkbox(
        "Create weak point if hard/forgot",
        key=f"fc_weak_{source_id}_{card_id}",
    )
    weak_concept = st.text_input(
        "Weak point concept (optional)",
        key=f"fc_wc_{source_id}_{card_id}",
    )

    if st.button("Save review", key=f"fc_save_{source_id}_{card_id}"):
        try:
            result = record_flashcard_review(
                course_name,
                source_id,
                card_id,
                current["front"],
                current["back"],
                grade,
                notes=notes or None,
                create_weak_point=create_weak,
                weak_point_concept=weak_concept or None,
            )
            st.success(f"Saved {result['review_id']} — grade: {result['grade']}")
            st.session_state[reveal_key] = False
            st.rerun()
        except InvalidFlashcardGradeError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    recent = summary.get("recent_reviews") or []
    if recent:
        st.subheader("Recent reviews")
        for review in recent:
            due = review.get("due_date", "")
            due_text = f" · due {due}" if due else ""
            st.write(
                f"- `{review.get('review_id')}` · {review.get('card_id')} · "
                f"**{review.get('grade')}**{due_text} · {review.get('front', '')[:60]}"
            )


def _weak_active_recall_attempts(course_name: str, source_id: str) -> list[dict]:
    """Return wrong, partial, or skipped attempts (most recent first)."""
    course_path = resolve_course_path(course_name)
    log = load_active_recall_log(get_active_recall_log_path(course_path, source_id))
    weak_grades = {"wrong", "partial", "skipped"}
    attempts = [
        attempt
        for attempt in log.get("attempts", [])
        if str(attempt.get("grade", "")).lower() in weak_grades
    ]
    return list(reversed(attempts))


def page_mock_tests(course_name: str | None) -> None:
    _render_page_intro("mock_tests")
    if not _require_course():
        return

    st.subheader("Generate Mock Test")
    gen_scope = st.radio(
        "Scope",
        ["Source", "Study unit"],
        horizontal=True,
        key="mt_gen_scope",
    )
    gen_source_id: str | None = None
    gen_unit_id: str | None = None
    if gen_scope == "Source":
        sources = _source_options(course_name)
        gen_source_id = _select_source(sources, key="mt_gen_source")
        if not gen_source_id:
            return
    else:
        units = [
            unit
            for unit in list_study_units(course_name)
            if str(unit.get("status", "")).lower() != "archived"
        ]
        if not units:
            st.info("No study units yet. Create one on **Study Units**.")
            return
        unit_labels = [
            f"{unit.get('unit_id', '')} — {unit.get('title', '')}"
            for unit in units
        ]
        unit_map = {label: unit for label, unit in zip(unit_labels, units)}
        picked = st.selectbox("Study unit", unit_labels, key="mt_gen_unit")
        gen_unit_id = unit_map[picked].get("unit_id")

    question_count = st.number_input(
        "Question count",
        min_value=1,
        max_value=50,
        value=20,
        step=1,
        key="mt_question_count",
    )
    include_flashcards = st.checkbox(
        "Include flashcards",
        value=True,
        key="mt_include_flashcards",
    )
    if st.button("Generate mock test", key="mt_generate"):
        try:
            if gen_scope == "Source":
                result = generate_mock_test(
                    course_name,
                    "source",
                    source_id=gen_source_id,
                    question_count=int(question_count),
                    include_flashcards=include_flashcards,
                )
            else:
                result = generate_mock_test(
                    course_name,
                    "unit",
                    unit_id=gen_unit_id,
                    question_count=int(question_count),
                    include_flashcards=include_flashcards,
                )
            st.success(
                f"Generated `{result['mock_test_id']}` with "
                f"{result['question_count']} questions."
            )
            st.code(result["markdown_path"])
            st.session_state["mt_last_generated_path"] = result["markdown_path"]
            st.session_state["mt_last_mock_test_id"] = result["mock_test_id"]
            st.rerun()
        except MockTestNotReadyError as exc:
            st.warning(str(exc))
        except Exception as exc:
            _show_exception(exc)

    preview_path = st.session_state.get("mt_last_generated_path", "")
    if preview_path and Path(preview_path).is_file():
        with st.expander("Generated mock test preview", expanded=False):
            st.text_area(
                "Mock test Markdown",
                read_text_preview(Path(preview_path), max_chars=16000),
                height=320,
                key="mt_preview",
            )

    st.subheader("Detailed Grading")
    mock_tests = list_mock_tests(course_name)
    if not mock_tests:
        st.info("Generate a mock test above to start detailed grading.")
    else:
        grade_labels = [
            f"{test.get('mock_test_id', '')} "
            f"({test.get('question_count', 0)} q, {test.get('scope', '')})"
            for test in mock_tests
        ]
        grade_map = {label: test for label, test in zip(grade_labels, mock_tests)}
        picked_grade = st.selectbox(
            "Mock test to grade",
            grade_labels,
            key="mt_grade_pick",
        )
        grade_test = grade_map[picked_grade]
        grade_mock_id = grade_test.get("mock_test_id", "")

        try:
            grade_mock_data = load_mock_test_json(course_name, grade_mock_id)
            grade_summary = summarize_mock_test_grading(course_name, grade_mock_id)
            questions = grade_mock_data.get("questions", [])

            g1, g2, g3, g4 = st.columns(4)
            g1.metric(
                "Graded",
                f"{grade_summary.get('graded_count', 0)}/"
                f"{grade_summary.get('question_count', 0)}",
            )
            g2.metric("Percent", f"{grade_summary.get('percent', 0)}%")
            g3.metric("Correct", grade_summary.get("correct", 0))
            g4.metric("Needs review", grade_summary.get("needs_review_count", 0))

            if grade_summary.get("finalized"):
                st.caption(
                    f"Finalized as `{grade_summary.get('finalized_attempt_id', '')}`"
                )

            if questions:
                q_labels = [
                    f"{q.get('mock_question_id', '')} — "
                    f"{str(q.get('question', ''))[:50]}"
                    for q in questions
                ]
                q_map = {label: q for label, q in zip(q_labels, questions)}
                picked_q = st.selectbox("Question", q_labels, key="mt_grade_question")
                current_q = q_map[picked_q]
                st.write("**Question:**", current_q.get("question", ""))
                expected = current_q.get("expected_answer", "")
                if expected:
                    st.caption(f"Expected answer: {expected}")
                else:
                    st.caption("Expected answer: see answer key in mock test Markdown.")

                user_answer = st.text_area(
                    "Your answer",
                    key=f"mt_g_ans_{grade_mock_id}_{current_q.get('mock_question_id', '')}",
                )
                q_grade = st.selectbox(
                    "Grade",
                    ["correct", "partial", "wrong", "skipped"],
                    key=f"mt_g_grade_{grade_mock_id}_{current_q.get('mock_question_id', '')}",
                )
                q_notes = st.text_input(
                    "Notes",
                    key=f"mt_g_notes_{grade_mock_id}_{current_q.get('mock_question_id', '')}",
                )
                create_mistake = st.checkbox(
                    "Create mistake",
                    key=f"mt_g_mist_{current_q.get('mock_question_id', '')}",
                )
                create_weak = st.checkbox(
                    "Create weak point",
                    key=f"mt_g_weak_{current_q.get('mock_question_id', '')}",
                )
                weak_concept = st.text_input(
                    "Weak point concept (optional)",
                    key=f"mt_g_wc_{current_q.get('mock_question_id', '')}",
                )
                if st.button("Save question grade", key="mt_save_question_grade"):
                    try:
                        result = record_mock_question_result(
                            course_name,
                            grade_mock_id,
                            current_q["mock_question_id"],
                            q_grade,
                            user_answer=user_answer or None,
                            notes=q_notes or None,
                            create_mistake=create_mistake,
                            create_weak_point=create_weak,
                            weak_point_concept=weak_concept or None,
                        )
                        st.success(
                            f"Saved grade `{result['grade']}` for "
                            f"`{result['mock_question_id']}`"
                        )
                        if result.get("applied"):
                            st.caption(f"Applied: {', '.join(result['applied'])}")
                        st.rerun()
                    except (
                        MockTestGradingAlreadyFinalizedError,
                        MockTestQuestionNotFoundError,
                        InvalidMockTestGradeError,
                    ) as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        _show_exception(exc)

            missed = grade_summary.get("missed_questions") or []
            if missed:
                with st.expander("Missed / partial questions", expanded=False):
                    for item in missed:
                        st.markdown(
                            f"- **{item.get('mock_question_id', '')}** "
                            f"({item.get('grade', '')}): "
                            f"{str(item.get('question', ''))[:80]}"
                        )

            finalize_notes = st.text_input(
                "Finalize notes",
                key="mt_finalize_notes",
            )
            col_f, col_e = st.columns(2)
            with col_f:
                if st.button("Finalize grading as mock attempt", key="mt_finalize"):
                    try:
                        result = finalize_mock_test_grading(
                            course_name,
                            grade_mock_id,
                            notes=finalize_notes or None,
                        )
                        st.success(
                            f"Finalized `{result['attempt_id']}`: "
                            f"{result['score_correct']}/{result['score_total']} "
                            f"({result['percent']}%)"
                        )
                        st.rerun()
                    except (MockTestGradingAlreadyFinalizedError, ValueError) as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        _show_exception(exc)
            with col_e:
                review_overwrite = st.checkbox(
                    "Overwrite review",
                    value=False,
                    key="mt_review_overwrite",
                )
                if st.button("Export mock review", key="mt_export_review"):
                    try:
                        result = export_mock_test_review(
                            course_name,
                            grade_mock_id,
                            overwrite=review_overwrite,
                        )
                        st.session_state["mt_last_review_path"] = result["review_path"]
                        st.success(f"Review: `{result['review_path']}`")
                        st.rerun()
                    except MockTestReviewExistsError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        _show_exception(exc)

            review_path = st.session_state.get("mt_last_review_path", "")
            if review_path and Path(review_path).is_file():
                with st.expander("Review preview", expanded=False):
                    st.text_area(
                        "Mock test review",
                        read_text_preview(Path(review_path), max_chars=12000),
                        height=280,
                        key="mt_review_preview",
                    )
            elif grade_summary.get("graded_count", 0) > 0:
                with st.expander("Review preview (live)", expanded=False):
                    st.text_area(
                        "Mock test review",
                        build_mock_test_review_markdown(course_name, grade_mock_id),
                        height=280,
                        key="mt_review_preview_live",
                    )
        except MockTestNotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    st.subheader("Record Attempt")
    mock_test_id = st.text_input(
        "Mock test ID",
        value=st.session_state.get("mt_last_mock_test_id", ""),
        key="mt_record_id",
    )
    record_scope = st.radio(
        "Attempt scope",
        ["source", "unit"],
        horizontal=True,
        key="mt_record_scope",
    )
    record_source_id: str | None = None
    record_unit_id: str | None = None
    if record_scope == "source":
        sources = _source_options(course_name)
        record_source_id = _select_source(sources, key="mt_record_source")
        if not record_source_id:
            return
    else:
        units = [
            unit
            for unit in list_study_units(course_name)
            if str(unit.get("status", "")).lower() != "archived"
        ]
        if not units:
            st.info("No study units available.")
            return
        unit_labels = [
            f"{unit.get('unit_id', '')} — {unit.get('title', '')}"
            for unit in units
        ]
        unit_map = {label: unit for label, unit in zip(unit_labels, units)}
        picked = st.selectbox("Unit for attempt", unit_labels, key="mt_record_unit")
        record_unit_id = unit_map[picked].get("unit_id")

    score_col, total_col = st.columns(2)
    with score_col:
        score_correct = st.number_input(
            "Score correct",
            min_value=0,
            value=0,
            step=1,
            key="mt_score_correct",
        )
    with total_col:
        score_total = st.number_input(
            "Score total",
            min_value=1,
            value=20,
            step=1,
            key="mt_score_total",
        )
    attempt_notes = st.text_input("Notes", key="mt_attempt_notes")
    weak_topics_text = st.text_input(
        "Weak topics (comma-separated)",
        key="mt_weak_topics",
    )
    if st.button("Save attempt", key="mt_save_attempt"):
        try:
            if not mock_test_id.strip():
                st.error("Enter a mock test ID.")
            else:
                topics = [
                    part.strip()
                    for part in weak_topics_text.split(",")
                    if part.strip()
                ]
                result = record_mock_test_attempt(
                    course_name,
                    mock_test_id.strip(),
                    record_scope,
                    record_source_id,
                    record_unit_id,
                    int(score_correct),
                    int(score_total),
                    notes=attempt_notes or None,
                    weak_topics=topics or None,
                )
                st.success(
                    f"Saved {result['attempt_id']}: "
                    f"{result['score_correct']}/{result['score_total']} "
                    f"({result['percent']}%)"
                )
                if result.get("weak_point_ids"):
                    st.caption(
                        "Weak points: " + ", ".join(result["weak_point_ids"])
                    )
                st.rerun()
        except (InvalidMockTestScoreError, InvalidMockTestScopeError) as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    st.subheader("Summary")
    try:
        summary = summarize_mock_test_attempts(course_name)
    except Exception as exc:
        _show_exception(exc)
        return

    s1, s2 = st.columns(2)
    s1.metric("Attempts", summary.get("attempt_count", 0))
    s2.metric("Average score %", summary.get("average_percent", 0.0))
    latest = summary.get("latest_attempt")
    if latest:
        st.caption(
            f"Latest: `{latest.get('mock_test_id')}` — "
            f"{latest.get('score_correct')}/{latest.get('score_total')} "
            f"({latest.get('percent')}%)"
        )
    recent = summary.get("recent_attempts") or []
    if recent:
        rows = []
        for attempt in recent:
            rows.append(
                {
                    "Attempt": attempt.get("attempt_id", ""),
                    "Mock test": attempt.get("mock_test_id", ""),
                    "Score": f"{attempt.get('score_correct')}/{attempt.get('score_total')}",
                    "Percent": attempt.get("percent", ""),
                    "Date": attempt.get("date_recorded", ""),
                }
            )
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No mock test attempts recorded yet.")


def page_exam_prep(course_name: str | None) -> None:
    _render_page_intro("exam_prep")
    if not _require_course():
        return

    st.subheader("Exam Targets")
    targets = list_exam_targets(course_name)
    if targets:
        rows = []
        for target in targets:
            rows.append(
                {
                    "ID": target.get("exam_id", ""),
                    "Title": target.get("title", ""),
                    "Date": target.get("exam_date", ""),
                    "Target %": target.get("target_score", "—"),
                    "Status": target.get("status", ""),
                    "Units": ", ".join(target.get("unit_ids", [])),
                    "Sources": ", ".join(target.get("source_ids", [])),
                }
            )
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No exam targets yet. Create one below.")

    with st.expander("Create exam target", expanded=not targets):
        new_title = st.text_input("Title", key="ep_new_title")
        new_date = st.text_input("Exam date (YYYY-MM-DD)", key="ep_new_date")
        new_desc = st.text_input("Description", key="ep_new_desc")
        new_target = st.number_input(
            "Target score %",
            min_value=0,
            max_value=100,
            value=80,
            step=1,
            key="ep_new_target",
        )
        units = [
            unit
            for unit in list_study_units(course_name)
            if str(unit.get("status", "")).lower() != "archived"
        ]
        unit_labels = [
            f"{unit.get('unit_id', '')} — {unit.get('title', '')}" for unit in units
        ]
        unit_map = {label: unit for label, unit in zip(unit_labels, units)}
        picked_units = st.multiselect(
            "Units",
            unit_labels,
            key="ep_new_units",
        )
        sources = _source_options(course_name)
        source_labels = [
            f"{s.get('id', '')} — {s.get('title', '')}" for s in sources
        ]
        source_map = {label: s for label, s in zip(source_labels, sources)}
        picked_sources = st.multiselect(
            "Additional sources",
            source_labels,
            key="ep_new_sources",
        )
        if st.button("Create exam target", key="ep_create"):
            try:
                if not new_title.strip() or not new_date.strip():
                    st.error("Title and exam date are required.")
                else:
                    unit_ids = [
                        unit_map[label].get("unit_id") for label in picked_units
                    ]
                    source_ids = [
                        source_map[label].get("id") for label in picked_sources
                    ]
                    target = create_exam_target(
                        course_name,
                        new_title.strip(),
                        new_date.strip(),
                        description=new_desc or None,
                        target_score=int(new_target),
                        unit_ids=unit_ids,
                        source_ids=source_ids,
                    )
                    st.success(f"Created `{target['exam_id']}` — {target['title']}")
                    st.rerun()
            except (
                InvalidExamDateError,
                InvalidTargetScoreError,
                InvalidExamUnitIdError,
                InvalidSourceIdError,
            ) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    if targets:
        status_options = ["active", "completed", "archived"]
        target_labels = [
            f"{t.get('exam_id', '')} — {t.get('title', '')}" for t in targets
        ]
        target_map = {label: t for label, t in zip(target_labels, targets)}
        picked_label = st.selectbox(
            "Update exam target",
            target_labels,
            key="ep_update_pick",
        )
        picked_target = target_map[picked_label]
        current_status = str(picked_target.get("status", "active")).lower()
        new_status = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(current_status)
            if current_status in status_options
            else 0,
            key="ep_update_status",
        )
        if st.button("Update status", key="ep_update_btn"):
            try:
                update_exam_target(
                    course_name,
                    picked_target["exam_id"],
                    status=new_status,
                )
                st.success(f"Updated `{picked_target['exam_id']}` to {new_status}.")
                st.rerun()
            except (InvalidExamTargetStatusError, ExamTargetNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)

    st.subheader("Exam Prep Plan")
    active_targets = [
        t for t in targets if str(t.get("status", "")).lower() == "active"
    ]
    if not active_targets:
        st.info("Create an active exam target to generate a prep plan.")
        return

    plan_labels = [
        f"{t.get('exam_id', '')} — {t.get('title', '')} ({t.get('exam_date', '')})"
        for t in active_targets
    ]
    plan_map = {label: t for label, t in zip(plan_labels, active_targets)}
    picked_plan = st.selectbox("Exam target", plan_labels, key="ep_plan_pick")
    exam_target = plan_map[picked_plan]
    exam_id = exam_target.get("exam_id", "")

    try:
        readiness_report = get_exam_readiness_report(course_name, exam_id)
        readiness = readiness_report.get("readiness", {})
        st.caption(
            f"Readiness: {readiness.get('score', 0)}% "
            f"({readiness.get('status', '')})"
        )
    except ExamTargetNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        _show_exception(exc)
        return

    try:
        state = collect_exam_prep_state(course_name, exam_id)
        actions = recommend_exam_prep_actions(state)
    except ExamTargetNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        _show_exception(exc)
        return

    days = state.get("days_until_exam", 0)
    p1, p2, p3 = st.columns(3)
    p1.metric("Days remaining", days)
    p2.metric(
        "Due flashcards",
        len(state.get("review", {}).get("due_flashcards") or [])
        + len(state.get("review", {}).get("due_unit_flashcards") or []),
    )
    p3.metric("Mock attempts", state.get("mock_tests", {}).get("attempt_count", 0))

    st.write("**Scope**")
    st.caption(
        f"Units: {', '.join(state.get('scope', {}).get('unit_ids', [])) or '(none)'}"
    )
    st.caption(
        f"Sources: {', '.join(state.get('scope', {}).get('source_ids', [])) or '(none)'}"
    )

    readiness = state.get("readiness", {})
    review = state.get("review", {})
    st.write("**Readiness**")
    st.caption(
        f"Incomplete sources: {len(readiness.get('incomplete_sources') or [])} · "
        f"Units without synthesis: {len(readiness.get('units_without_synthesis') or [])} · "
        f"Units without pack: {len(readiness.get('units_without_unit_pack') or [])}"
    )
    st.write("**Review summary**")
    st.caption(
        f"Recall gaps: "
        f"{len(review.get('active_recall_needs_review') or []) + len(review.get('unit_recall_needs_review') or [])} · "
        f"Mistakes: {len(review.get('open_mistakes') or [])} · "
        f"Weak points: {len(review.get('open_weak_points') or [])}"
    )
    mock_tests = state.get("mock_tests", {})
    if mock_tests.get("latest_score") is not None:
        st.caption(
            f"Latest mock score: {mock_tests.get('latest_score')}% "
            f"(target: {exam_target.get('target_score', '—')}%)"
        )

    if actions:
        primary = actions[0]
        st.info(f"**Recommended:** {primary.get('label', '')} — {primary.get('reason', '')}")

    st.subheader("Exam Readiness")
    readiness_status = str(readiness.get("status", ""))
    r1, r2 = st.columns(2)
    r1.metric("Readiness score", f"{readiness.get('score', 0)}%")
    r2.metric("Status", readiness_status.replace("_", " "))
    if readiness_status == "ready":
        st.success("You look ready on paper — keep reviewing until exam day.")
    elif readiness_status == "needs_review":
        st.info("Some review work remains before exam day.")
    elif readiness_status == "at_risk":
        st.warning("Readiness is at risk — focus on the blockers below.")
    else:
        st.error("Readiness is low — address blockers before the exam.")

    breakdown = readiness.get("breakdown", {})
    st.write("**Breakdown**")
    st.table(
        {
            "Area": [
                "Material readiness",
                "Review load",
                "Mock tests",
                "Time pressure",
            ],
            "Score": [
                f"{breakdown.get('readiness', 0)}/30",
                f"{breakdown.get('review_load', 0)}/25",
                f"{breakdown.get('mock_tests', 0)}/30",
                f"{breakdown.get('time', 0)}/15",
            ],
        }
    )

    blockers = readiness.get("blockers") or []
    if blockers:
        st.write("**Blockers**")
        for blocker in blockers:
            st.markdown(f"- {blocker}")

    readiness_recs = readiness.get("recommendations") or []
    if readiness_recs:
        st.write("**Recommendations**")
        for recommendation in readiness_recs:
            st.markdown(f"- {recommendation}")

    readiness_overwrite = st.checkbox(
        "Overwrite existing readiness report",
        value=False,
        key="ep_readiness_overwrite",
    )
    if st.button("Export readiness report", key="ep_export_readiness"):
        try:
            result = export_exam_readiness_report(
                course_name,
                exam_id,
                overwrite=readiness_overwrite,
            )
            st.success(f"Readiness report written: `{result['markdown_path']}`")
            st.session_state["ep_last_readiness_path"] = result["markdown_path"]
            st.rerun()
        except ExamReadinessReportExistsError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    readiness_path = st.session_state.get("ep_last_readiness_path", "")
    if readiness_path and Path(readiness_path).is_file():
        with st.expander("Readiness report preview", expanded=False):
            st.text_area(
                "Exam readiness report",
                read_text_preview(Path(readiness_path), max_chars=12000),
                height=280,
                key="ep_readiness_preview",
            )
    else:
        preview_md = build_exam_readiness_markdown(readiness_report)
        with st.expander("Readiness report preview", expanded=False):
            st.text_area(
                "Exam readiness report (preview)",
                preview_md,
                height=280,
                key="ep_readiness_preview_live",
            )

    if st.button("Start exam study session", key="ep_start_session"):
        try:
            summary = start_study_session(
                course_name,
                limit=10,
                exam_id=exam_id,
            )
            session_key = f"study_session_{course_name}"
            st.session_state[session_key] = get_latest_study_session(course_name)
            msg = (
                f"Started exam session `{summary['session_id']}` with "
                f"{summary['item_count']} items. Open **Study Session** to continue."
            )
            if summary.get("warning"):
                st.warning(summary["warning"])
            st.success(msg)
            st.rerun()
        except ExamTargetNotFoundError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    plan_overwrite = st.checkbox("Overwrite existing plan", value=False, key="ep_overwrite")
    if st.button("Generate exam prep plan", key="ep_generate_plan"):
        try:
            result = generate_exam_prep_plan(
                course_name,
                exam_id,
                overwrite=plan_overwrite,
            )
            st.success(f"Plan written: `{result['markdown_path']}`")
            st.session_state["ep_last_plan_path"] = result["markdown_path"]
            st.rerun()
        except ExamPrepPlanExistsError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    plan_path = st.session_state.get("ep_last_plan_path", "")
    if plan_path and Path(plan_path).is_file():
        with st.expander("Plan preview", expanded=False):
            st.text_area(
                "Exam prep plan",
                read_text_preview(Path(plan_path), max_chars=16000),
                height=320,
                key="ep_plan_preview",
            )


def page_review_tracker(course_name: str | None) -> None:
    _render_page_intro("review_tracker")
    if not _require_course():
        return

    st.subheader("Review Session Planner")
    plan_limit = st.number_input(
        "Priority item limit",
        min_value=1,
        max_value=50,
        value=10,
        key="rt_plan_limit",
    )
    plan_overwrite = st.checkbox(
        "Overwrite today's plan if it exists",
        value=False,
        key="rt_plan_overwrite",
    )
    if st.button("Generate today's review plan", key="rt_gen_plan"):
        try:
            summary = generate_review_plan(
                course_name,
                limit=int(plan_limit),
                overwrite=plan_overwrite,
            )
            st.success("Review plan generated.")
            st.write(f"**Mistakes:** {summary['mistake_count']}")
            st.write(f"**Weak points:** {summary['weak_point_count']}")
            st.write(f"**Active recall redo:** {summary['active_recall_review_count']}")
            if summary.get("flashcards_due_count") is not None:
                st.write(f"**Flashcards due:** {summary['flashcards_due_count']}")
            st.write(f"**Top priorities:** {summary['priority_count']}")
            st.code(summary["markdown_path"])
            st.rerun()
        except ReviewPlanExistsError as exc:
            st.error(str(exc))
        except Exception as exc:
            _show_exception(exc)

    try:
        course_path = resolve_course_path(course_name)
        today_plan = get_review_plan_path(course_path)
        if today_plan.is_file():
            st.caption(f"Latest plan: `{today_plan}`")
            st.text_area(
                "Plan preview",
                read_text_preview(today_plan, max_chars=12000),
                height=280,
                key="rt_plan_preview",
            )
    except Exception:
        pass

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="rt_source")
    if not source_id:
        return

    st.subheader("Active Recall Weak Attempts")
    weak_attempts = _weak_active_recall_attempts(course_name, source_id)
    if not weak_attempts:
        st.info("No wrong, partial, or skipped attempts for this source yet.")
    else:
        labels = [
            f"{a.get('attempt_id', '?')} ({a.get('grade')}) — "
            f"{a.get('question', '')[:70]}"
            for a in weak_attempts
        ]
        pick = st.selectbox("Select attempt", labels, key=f"rt_attempt_{source_id}")
        attempt = weak_attempts[labels.index(pick)]
        st.write(f"**Question:** {attempt.get('question', '')}")
        st.write(f"**Your answer:** {attempt.get('user_answer', '')}")
        st.write(f"**Grade:** {attempt.get('grade', '')}")
        if attempt.get("notes"):
            st.write(f"**Notes:** {attempt.get('notes')}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Create mistake from selected attempt", key=f"rt_mistake_{source_id}"):
                try:
                    result = add_mistake(
                        course_name,
                        source_id,
                        attempt.get("question", ""),
                        attempt.get("user_answer", ""),
                        question_id=attempt.get("question_id"),
                        why_wrong=attempt.get("notes") or "",
                    )
                    st.success(f"Created {result['mistake_id']}")
                    st.rerun()
                except Exception as exc:
                    _show_exception(exc)
        with c2:
            if st.button(
                "Create weak point from selected attempt", key=f"rt_weak_{source_id}"
            ):
                try:
                    concept = (attempt.get("question") or "")[:80]
                    result = add_weak_point(
                        course_name,
                        source_id,
                        concept,
                        why_hard=attempt.get("notes") or "",
                        what_to_review=attempt.get("question", ""),
                    )
                    st.success(f"Created {result['weak_point_id']}")
                    st.rerun()
                except Exception as exc:
                    _show_exception(exc)

    st.subheader("Mistakes Log")
    mistakes = list_mistakes(course_name)
    if mistakes:
        st.dataframe(
            [
                {
                    "ID": m.get("mistake_id"),
                    "Source": m.get("source_id"),
                    "Status": m.get("status"),
                    "Question": (m.get("question") or "")[:60],
                }
                for m in mistakes
            ],
            use_container_width=True,
        )
        mistake_ids = [m["mistake_id"] for m in mistakes]
        upd_id = st.selectbox("Update mistake", mistake_ids, key="rt_mistake_upd_id")
        new_status = st.selectbox(
            "New status",
            ["new", "reviewed_once", "still_weak", "mastered"],
            key="rt_mistake_upd_status",
        )
        if st.button("Update mistake status", key="rt_mistake_upd_btn"):
            try:
                update_mistake_status(course_name, upd_id, new_status)
                st.success(f"Updated {upd_id}")
                st.rerun()
            except (InvalidMistakeStatusError, MistakeNotFoundError) as exc:
                st.error(str(exc))
    else:
        st.info("No mistakes logged yet.")

    with st.expander("Add mistake manually"):
        m_q = st.text_input("Question", key="rt_m_q")
        m_a = st.text_input("Your answer", key="rt_m_a")
        m_src = st.text_input("Source ID", value=source_id, key="rt_m_src")
        m_why = st.text_input("Why wrong", key="rt_m_why")
        m_avoid = st.text_input("How to avoid", key="rt_m_avoid")
        if st.button("Add mistake", key="rt_m_add"):
            if not m_q.strip():
                st.error("Question is required.")
            else:
                try:
                    add_mistake(
                        course_name,
                        m_src,
                        m_q,
                        m_a,
                        why_wrong=m_why or None,
                        how_to_avoid=m_avoid or None,
                    )
                    st.success("Mistake added.")
                    st.rerun()
                except Exception as exc:
                    _show_exception(exc)

    if st.button("Export mistakes Markdown", key="rt_m_export"):
        try:
            path = export_mistakes_markdown(course_name)
            st.success(f"Exported to `{path}`")
        except Exception as exc:
            _show_exception(exc)

    st.subheader("Weak Points")
    weak_items = list_weak_points(course_name)
    if weak_items:
        st.dataframe(
            [
                {
                    "ID": w.get("weak_point_id"),
                    "Concept": (w.get("concept") or "")[:50],
                    "Confidence": w.get("confidence_level"),
                    "Status": w.get("status"),
                    "Source": w.get("source_id"),
                }
                for w in weak_items
            ],
            use_container_width=True,
        )
        weak_ids = [w["weak_point_id"] for w in weak_items]
        w_upd_id = st.selectbox("Update weak point", weak_ids, key="rt_weak_upd_id")
        w_conf = st.number_input(
            "Confidence (1–5)", min_value=1, max_value=5, value=2, key="rt_weak_conf"
        )
        w_status = st.selectbox(
            "New status",
            ["new", "reviewing", "still_weak", "improving", "mastered"],
            key="rt_weak_upd_status",
        )
        if st.button("Update weak point", key="rt_weak_upd_btn"):
            try:
                update_weak_point(
                    course_name, w_upd_id, confidence_level=int(w_conf), status=w_status
                )
                st.success(f"Updated {w_upd_id}")
                st.rerun()
            except (
                InvalidConfidenceError,
                InvalidWeakPointStatusError,
                WeakPointNotFoundError,
            ) as exc:
                st.error(str(exc))
    else:
        st.info("No weak points logged yet.")

    with st.expander("Add weak point manually"):
        w_concept = st.text_input("Concept", key="rt_w_concept")
        w_src = st.text_input("Source ID", value=source_id, key="rt_w_src")
        w_conf_add = st.slider("Confidence", 1, 5, 2, key="rt_w_conf_add")
        w_why = st.text_input("Why hard", key="rt_w_why")
        w_review = st.text_input("What to review", key="rt_w_review")
        w_practice = st.text_input("Practice needed", key="rt_w_practice")
        if st.button("Add weak point", key="rt_w_add"):
            if not w_concept.strip():
                st.error("Concept is required.")
            else:
                try:
                    add_weak_point(
                        course_name,
                        w_src,
                        w_concept,
                        confidence_level=int(w_conf_add),
                        why_hard=w_why or None,
                        what_to_review=w_review or None,
                        practice_needed=w_practice or None,
                    )
                    st.success("Weak point added.")
                    st.rerun()
                except Exception as exc:
                    _show_exception(exc)

    if st.button("Export weak points Markdown", key="rt_w_export"):
        try:
            path = export_weak_points_markdown(course_name)
            st.success(f"Exported to `{path}`")
        except Exception as exc:
            _show_exception(exc)


def page_study_session(course_name: str | None) -> None:
    _render_page_intro("study_session")
    if not _require_course():
        return

    session_key = f"study_session_{course_name}"
    limit = st.number_input("Item limit", min_value=1, max_value=30, value=10, step=1)
    scope_choice = st.radio(
        "Session scope",
        ["Whole course", "Study unit", "Exam target"],
        horizontal=True,
        key=f"ss_scope_{course_name}",
    )
    selected_unit_id: str | None = None
    selected_exam_id: str | None = None
    if scope_choice == "Study unit":
        eligible_units = [
            unit
            for unit in list_study_units(course_name)
            if str(unit.get("status", "")).lower() != "archived"
        ]
        if not eligible_units:
            st.info("No active study units. Create one on **Study Units**.")
        else:
            unit_labels = [
                f"{unit.get('unit_id', '')} — {unit.get('title', '')}"
                for unit in eligible_units
            ]
            unit_map = {label: unit for label, unit in zip(unit_labels, eligible_units)}
            picked = st.selectbox(
                "Study unit",
                unit_labels,
                key=f"ss_unit_pick_{course_name}",
            )
            selected_unit_id = unit_map[picked].get("unit_id")
    elif scope_choice == "Exam target":
        active_exams = list_active_exam_targets(course_name)
        if not active_exams:
            st.info("No active exam targets. Create one on **Exam Prep**.")
        else:
            exam_labels = [
                f"{exam.get('exam_id', '')} — {exam.get('title', '')}"
                for exam in active_exams
            ]
            exam_map = {label: exam for label, exam in zip(exam_labels, active_exams)}
            picked_exam = st.selectbox(
                "Exam target",
                exam_labels,
                key=f"ss_exam_pick_{course_name}",
            )
            selected_exam_id = exam_map[picked_exam].get("exam_id")

    if st.button("Start new session", key=f"ss_start_{course_name}"):
        try:
            unit_id = selected_unit_id if scope_choice == "Study unit" else None
            exam_id = selected_exam_id if scope_choice == "Exam target" else None
            if scope_choice == "Study unit" and not unit_id:
                st.warning("Select a study unit to start a unit session.")
            elif scope_choice == "Exam target" and not exam_id:
                st.warning("Select an exam target to start an exam session.")
            else:
                summary = start_study_session(
                    course_name,
                    limit=int(limit),
                    unit_id=unit_id,
                    exam_id=exam_id,
                )
                session = get_latest_study_session(course_name)
                st.session_state[session_key] = session
                msg = (
                    f"Started `{summary['session_id']}` with "
                    f"{summary['item_count']} items."
                )
                if summary.get("warning"):
                    st.warning(summary["warning"])
                st.success(msg)
                st.rerun()
        except Exception as exc:
            _show_exception(exc)

    session = st.session_state.get(session_key)
    if session is None:
        session = get_latest_study_session(course_name)
        if session:
            st.session_state[session_key] = session

    if not session:
        st.info(
            "Nothing is due right now, or no session started yet. Click **Start new session** "
            "when you have review items, or review flashcards on **Flashcards**."
        )
        return

    session_id = session.get("session_id", "")
    items = session.get("items", [])
    completed = session.get("completed_items", [])
    completed_ids = {c.get("session_item_id") for c in completed}

    st.subheader("Current session")
    if session.get("scope") == "unit":
        st.caption(
            f"Unit session: {session.get('unit_id', '')} — "
            f"{session.get('unit_title', '')}"
        )
    elif session.get("scope") == "exam":
        st.caption(
            f"Exam session: {session.get('exam_id', '')} — "
            f"{session.get('exam_title', '')}"
        )
        st.caption(
            f"Date: {session.get('exam_date', '')} · "
            f"Target: {session.get('target_score', '—')}%"
        )
    else:
        st.caption("Course-wide session")
    st.write(f"**ID:** `{session_id}` — **Status:** {session.get('status', '')}")
    st.progress(
        len(completed_ids) / len(items) if items else 0.0,
        text=f"{len(completed_ids)} / {len(items)} items completed",
    )

    if not items:
        st.warning(
            "This session has no items. Add mistakes or weak points, practice active "
            "recall, or generate a study pack with active recall questions."
        )
        col_f, col_e = st.columns(2)
        with col_f:
            if st.button("Finish session", key=f"ss_finish_empty_{course_name}"):
                complete_study_session(course_name, session_id)
                st.session_state[session_key] = get_latest_study_session(course_name)
                st.rerun()
        with col_e:
            if st.button("Export summary", key=f"ss_export_empty_{course_name}"):
                path = export_study_session_summary(course_name, session_id)
                st.success(f"Summary: `{path}`")
        return

    labels = []
    for item in items:
        done = "done" if item["session_item_id"] in completed_ids else "todo"
        labels.append(
            f"[{done}] {item['session_item_id']} ({item['type']}) — {item['title'][:50]}"
        )
    chosen = st.selectbox("Session item", labels, key=f"ss_item_{course_name}_{session_id}")
    chosen_index = labels.index(chosen)
    current = items[chosen_index]
    payload = current.get("payload", {})

    st.markdown(f"**Priority:** {current.get('priority_reason', '')}")
    if current.get("details"):
        st.caption(current["details"])

    item_type = current.get("type", "")
    result_options: list[str]

    if item_type in (
        "active_recall",
        "active_recall_unanswered",
        "unit_active_recall",
        "unit_active_recall_unanswered",
    ):
        if item_type == "unit_active_recall_unanswered":
            st.subheader("Unanswered unit active recall question")
        elif item_type == "unit_active_recall":
            st.subheader("Unit active recall")
        elif item_type == "active_recall_unanswered":
            st.subheader("Unanswered active recall question")
        else:
            st.subheader("Active recall")
        st.write(payload.get("question", current.get("title", "")))
        st.caption(f"Question ID: `{payload.get('question_id', '')}`")
        if payload.get("grade"):
            st.caption(f"Last grade: {payload.get('grade')}")
        user_answer = st.text_area("Your answer", height=100, key=f"ss_ar_ans_{session_id}_{current['session_item_id']}")
        grade = st.selectbox(
            "Grade",
            ["correct", "partial", "wrong", "skipped"],
            key=f"ss_ar_grade_{session_id}_{current['session_item_id']}",
        )
        notes = st.text_input("Notes", key=f"ss_ar_notes_{session_id}_{current['session_item_id']}")
        create_mistake = st.checkbox("Create mistake", key=f"ss_ar_mist_{current['session_item_id']}")
        create_weak = st.checkbox("Create weak point", key=f"ss_ar_weak_{current['session_item_id']}")
        weak_concept = st.text_input(
            "Weak point concept (optional)",
            key=f"ss_ar_wc_{current['session_item_id']}",
        )
        def _save_recall() -> None:
            record_session_item_result(
                course_name,
                session_id,
                current["session_item_id"],
                grade,
                notes=notes or None,
                user_answer=user_answer,
                create_mistake=create_mistake,
                create_weak_point=create_weak,
                weak_point_concept=weak_concept or None,
            )

    elif item_type in (
        "flashcard",
        "flashcard_unreviewed",
        "unit_flashcard",
        "unit_flashcard_unreviewed",
    ):
        if item_type == "unit_flashcard_unreviewed":
            st.subheader("Unreviewed unit flashcard")
        elif item_type == "unit_flashcard":
            st.subheader("Unit flashcard")
        elif item_type == "flashcard_unreviewed":
            st.subheader("Unreviewed flashcard")
        else:
            st.subheader("Flashcard review")
        ss_reveal_key = f"ss_fc_revealed_{session_id}_{current['session_item_id']}"
        if ss_reveal_key not in st.session_state:
            st.session_state[ss_reveal_key] = False
        st.write("**Front:**", payload.get("front", current.get("title", "")))
        st.caption(f"Card ID: `{payload.get('card_id', '')}`")
        if payload.get("due_date"):
            st.caption(f"Due: {payload.get('due_date')}")
        if payload.get("grade"):
            st.caption(f"Last grade: {payload.get('grade')}")
        if not st.session_state[ss_reveal_key]:
            if st.button("Reveal answer", key=f"ss_fc_rev_{current['session_item_id']}"):
                st.session_state[ss_reveal_key] = True
                st.rerun()
        else:
            st.write("**Back:**", payload.get("back", ""))
        grade = st.selectbox(
            "Grade",
            ["easy", "good", "hard", "forgot", "skipped"],
            key=f"ss_fc_grade_{session_id}_{current['session_item_id']}",
        )
        notes = st.text_input(
            "Notes", key=f"ss_fc_notes_{session_id}_{current['session_item_id']}"
        )
        create_weak = st.checkbox(
            "Create weak point if hard/forgot",
            key=f"ss_fc_weak_{current['session_item_id']}",
        )
        weak_concept = st.text_input(
            "Weak point concept (optional)",
            key=f"ss_fc_wc_{current['session_item_id']}",
        )

        def _save_recall() -> None:
            record_session_item_result(
                course_name,
                session_id,
                current["session_item_id"],
                grade,
                notes=notes or None,
                create_weak_point=create_weak,
                weak_point_concept=weak_concept or None,
            )

    elif item_type == "mistake":
        st.subheader("Mistake review")
        st.write("**Question:**", payload.get("question", ""))
        st.write("**Your answer:**", payload.get("user_answer", ""))
        if payload.get("why_wrong"):
            st.write("**Why wrong:**", payload["why_wrong"])
        if payload.get("how_to_avoid"):
            st.write("**How to avoid:**", payload["how_to_avoid"])
        if payload.get("correct_explanation"):
            st.write("**Correct explanation:**", payload["correct_explanation"])
        mist_status_choices = ["reviewed_once", "still_weak", "mastered"]
        current_mist_status = str(payload.get("status", "new")).lower()
        mist_index = (
            mist_status_choices.index(current_mist_status)
            if current_mist_status in mist_status_choices
            else 0
        )
        status = st.selectbox(
            "Update status",
            mist_status_choices,
            index=mist_index,
            key=f"ss_mist_st_{current['session_item_id']}",
        )
        notes = st.text_input("Notes", key=f"ss_mist_notes_{current['session_item_id']}")

        def _save_recall() -> None:
            record_session_item_result(
                course_name,
                session_id,
                current["session_item_id"],
                status,
                notes=notes or None,
            )

    elif item_type == "weak_point":
        st.subheader("Weak point")
        st.write("**Concept:**", payload.get("concept", current.get("title", "")))
        if payload.get("why_hard"):
            st.write("**Why hard:**", payload["why_hard"])
        if payload.get("what_to_review"):
            st.write("**What to review:**", payload["what_to_review"])
        confidence = st.slider(
            "Confidence (1–5)",
            1,
            5,
            int(payload.get("confidence_level", 3)),
            key=f"ss_wp_conf_{current['session_item_id']}",
        )
        wp_status_choices = ["new", "reviewing", "still_weak", "improving", "mastered"]
        current_wp_status = str(payload.get("status", "new")).lower()
        wp_index = (
            wp_status_choices.index(current_wp_status)
            if current_wp_status in wp_status_choices
            else 0
        )
        wp_status = st.selectbox(
            "Status",
            wp_status_choices,
            index=wp_index,
            key=f"ss_wp_st_{current['session_item_id']}",
        )
        notes = st.text_input("Notes", key=f"ss_wp_notes_{current['session_item_id']}")

        def _save_recall() -> None:
            record_session_item_result(
                course_name,
                session_id,
                current["session_item_id"],
                wp_status,
                notes=notes or None,
                confidence_level=confidence,
            )
    else:
        st.warning(f"Unknown item type: {item_type}")

        def _save_recall() -> None:
            record_session_item_result(
                course_name,
                session_id,
                current["session_item_id"],
                "completed",
            )

    ncol1, ncol2, ncol3 = st.columns(3)
    with ncol1:
        if st.button("Save result", key=f"ss_save_{current['session_item_id']}"):
            try:
                _save_recall()
                st.session_state[session_key] = get_latest_study_session(course_name)
                st.success("Saved.")
                st.rerun()
            except (InvalidSessionResultError, StudySessionItemNotFoundError) as exc:
                st.error(str(exc))
            except Exception as exc:
                _show_exception(exc)
    with ncol2:
        if st.button("Finish session", key=f"ss_finish_{course_name}"):
            try:
                complete_study_session(course_name, session_id)
                st.session_state[session_key] = get_latest_study_session(course_name)
                st.success("Session marked complete.")
                st.rerun()
            except Exception as exc:
                _show_exception(exc)
    with ncol3:
        if st.button("Export summary", key=f"ss_export_{course_name}"):
            try:
                path = export_study_session_summary(course_name, session_id)
                st.success(f"Summary: `{path}`")
            except Exception as exc:
                _show_exception(exc)


def page_settings() -> None:
    _render_page_intro("settings")
    root = Path(st.session_state.project_root)
    try:
        config = load_config(root)
        courses_dir = get_courses_dir(root, config)
    except Exception as exc:
        _show_exception(exc)
        return

    settings_path = get_app_settings_path(root)
    st.write(f"**Project root:** `{root}`")
    st.write(f"**Courses directory:** `{courses_dir}`")
    st.write(f"**App settings file:** `{settings_path}`")
    st.warning(
        "Local app settings are gitignored and should **not** contain API keys or secrets. "
        "Use `.env` or **Google AI** below for API keys."
    )

    current = load_app_settings(root)
    lm = current.get("lm_studio", {})
    chunking = current.get("chunking", {})
    digest = current.get("digest", {})
    gui = current.get("gui", {})

    st.subheader("LM Studio")
    set_lm_url = st.text_input(
        "Base URL",
        value=lm.get("base_url", DEFAULT_BASE_URL),
        key="settings_lm_url",
    )
    set_lm_model = st.text_input(
        "Default model (empty = first from /models)",
        value=lm.get("default_model", ""),
        key="settings_lm_model",
    )
    col_lm1, col_lm2, col_lm3 = st.columns(3)
    with col_lm1:
        set_temperature = st.number_input(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=float(lm.get("temperature", 0.2)),
            step=0.1,
            key="settings_lm_temperature",
        )
    with col_lm2:
        set_max_tokens = st.number_input(
            "Max tokens",
            min_value=1000,
            max_value=32000,
            value=int(lm.get("max_tokens", DEFAULT_DIGEST_MAX_TOKENS)),
            step=500,
            key="settings_lm_max_tokens",
        )
    with col_lm3:
        set_timeout = st.number_input(
            "Timeout (seconds)",
            min_value=30,
            max_value=3600,
            value=int(lm.get("timeout", 300)),
            step=30,
            key="settings_lm_timeout",
        )

    st.subheader("Chunking")
    col_ch1, col_ch2 = st.columns(2)
    with col_ch1:
        set_max_words = st.number_input(
            "Max words",
            min_value=100,
            value=int(chunking.get("max_words", 1200)),
            key="settings_max_words",
        )
    with col_ch2:
        set_overlap_words = st.number_input(
            "Overlap words",
            min_value=0,
            value=int(chunking.get("overlap_words", 150)),
            key="settings_overlap_words",
        )

    st.subheader("Digest defaults")
    set_limit_chunks = st.number_input(
        "Default first-chunk limit",
        min_value=1,
        max_value=50,
        value=int(digest.get("limit_chunks_default", 1)),
        key="settings_limit_chunks",
        help="Used as the default chunk limit preference (Pipeline uses 1 for test digest).",
    )
    set_full_digest = st.checkbox(
        "Full digest default (Guided Workflow)",
        value=bool(digest.get("full_digest_default", False)),
        key="settings_full_digest",
    )
    set_overwrite = st.checkbox(
        "Overwrite default",
        value=bool(digest.get("overwrite_default", False)),
        key="settings_overwrite",
    )

    st.subheader("GUI")
    page_options = flatten_navigation_pages()
    page_keys = navigation_keys()
    default_page = str(gui.get("default_page", "today")).strip().lower()
    if default_page not in page_keys:
        default_page = "today"
    set_default_page_label = st.selectbox(
        "Default page on startup",
        page_options,
        index=page_keys.index(default_page),
        key="settings_default_page",
    )
    set_show_advanced = st.checkbox(
        "Show advanced options in Guided Workflow",
        value=bool(gui.get("show_advanced_options", True)),
        key="settings_show_advanced",
    )

    save_col, reset_col = st.columns(2)
    with save_col:
        save_clicked = st.button("Save settings", key="settings_save")
    with reset_col:
        reset_clicked = st.button("Reset to defaults", key="settings_reset")

    if reset_clicked:
        defaults = get_default_app_settings()
        save_app_settings(defaults, root)
        _apply_app_settings_to_session(defaults)
        st.success("Settings reset to defaults.")
        st.rerun()

    if save_clicked:
        new_settings = {
            "lm_studio": {
                "base_url": set_lm_url.strip(),
                "default_model": set_lm_model.strip(),
                "temperature": float(set_temperature),
                "max_tokens": int(set_max_tokens),
                "timeout": int(set_timeout),
            },
            "chunking": {
                "max_words": int(set_max_words),
                "overlap_words": int(set_overlap_words),
            },
            "digest": {
                "limit_chunks_default": int(set_limit_chunks),
                "full_digest_default": bool(set_full_digest),
                "overwrite_default": bool(set_overwrite),
            },
            "gui": {
                "default_page": option_to_page_key(set_default_page_label) or "today",
                "show_advanced_options": bool(set_show_advanced),
            },
        }
        errors = validate_app_settings(new_settings)
        if errors:
            for error in errors:
                st.error(error)
        else:
            path = save_app_settings(new_settings, root)
            _apply_app_settings_to_session(new_settings)
            st.success(f"Saved settings to `{path}`.")
            st.rerun()

    st.subheader("Google AI (intermediate audit)")
    has_key = bool(get_google_api_key(root))
    st.write(
        "API key status:",
        "configured" if has_key else "not set",
    )
    st.caption(
        "Preferred: gitignored `.env` with `GOOGLE_API_KEY=...` (see `.env.example`). "
        "Also: Windows user env var, `config/local_secrets.json`, or Save below. "
        "API keys are **not** stored in app settings."
    )
    new_key = st.text_input(
        "Google AI API key",
        type="password",
        placeholder="Paste key from aistudio.google.com/apikey",
        key="google_api_key_input",
    )
    if st.button("Save Google API key locally"):
        if not new_key.strip():
            st.error("Enter an API key first.")
        else:
            path = set_google_api_key(new_key.strip(), root)
            st.success(f"Saved to `{path}` (gitignored). Restart not required.")
    st.info(
        "Project layout and courses directory: `config/studyforge_config.json`. "
        "Pipeline controls use saved LM Studio and chunking defaults from above."
    )


def run() -> None:
    """Entry point for Streamlit."""
    st.set_page_config(page_title="StudyForge", page_icon="📚", layout="wide")
    _init_session_state()
    page_key, course_name = _render_sidebar()

    if page_key == "today":
        page_today(course_name)
    elif page_key == "dashboard":
        page_dashboard(course_name)
    elif page_key == "course_quality":
        page_course_quality(course_name)
    elif page_key == "evidence_trace":
        page_evidence_trace(course_name)
    elif page_key == "courses":
        page_courses()
    elif page_key == "sources":
        page_sources(course_name)
    elif page_key == "pipeline":
        page_pipeline(course_name)
    elif page_key == "audits":
        page_audits(course_name)
    elif page_key == "study_units":
        page_study_units(course_name)
    elif page_key == "active_recall":
        page_active_recall(course_name)
    elif page_key == "flashcards":
        page_flashcards(course_name)
    elif page_key == "mock_tests":
        page_mock_tests(course_name)
    elif page_key == "exam_prep":
        page_exam_prep(course_name)
    elif page_key == "review_tracker":
        page_review_tracker(course_name)
    elif page_key == "study_session":
        page_study_session(course_name)
    elif page_key == "settings":
        page_settings()


def main() -> None:
    run()


if __name__ == "__main__":
    main()

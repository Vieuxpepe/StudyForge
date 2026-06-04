"""
StudyForge Streamlit GUI — wraps existing CLI backend functions.
"""

from __future__ import annotations

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
from studyforge.core.intermediate_audit_jobs import run_intermediate_audit_for_source
from studyforge.core.guided_workflow import (
    UnsupportedGuidedActionError,
    default_guided_options,
    get_guided_next_action,
    run_guided_next_step,
)
from studyforge.core.pipeline_status import STEP_ORDER, get_pipeline_status
from studyforge.core.paths import find_project_root, get_courses_dir, load_config
from studyforge.core.secrets import get_google_api_key, set_google_api_key
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
from studyforge.study.digest_review import review_local_digest_for_source
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
from studyforge.study.study_pack import (
    FinalAuditNotFoundError,
    StudyPackOutputExistsError,
    _SECTION_HEADINGS,
    diagnose_study_pack,
    generate_study_pack,
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

NAV_PAGES = [
    "Dashboard",
    "Courses",
    "Sources",
    "Pipeline",
    "Audits",
    "Active Recall",
    "Review Tracker",
    "Study Session",
    "Settings",
]

SOURCE_TYPES = ["textbook", "slides", "homework", "notes", "extra_readings"]


def _init_session_state() -> None:
    defaults = {
        "project_root": str(find_project_root()),
        "lm_base_url": DEFAULT_BASE_URL,
        "lm_model": "",
        "max_words": 1200,
        "overlap_words": 150,
        "overwrite": False,
        "max_digest_tokens": DEFAULT_DIGEST_MAX_TOKENS,
        "google_audit_model": DEFAULT_GEMMA_4_26B_MODEL,
        "limit_chunks": 0,
        "only_needs_review": False,
        "selected_course": None,
        "selected_source_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _course_names() -> list[str]:
    return [p.name for p in list_courses()]


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
        st.sidebar.info("No courses yet. Create one on the Courses page.")
        st.session_state.selected_course = None

    page = st.sidebar.radio("Navigation", NAV_PAGES)
    return page, st.session_state.selected_course


def _require_course() -> str | None:
    if not st.session_state.selected_course:
        st.warning("Select or create a course in the sidebar.")
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
        st.info("No sources for this course. Add one on the Sources page.")
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

    st.write("**Advanced options**")
    gw_overwrite = st.checkbox(
        "Overwrite outputs",
        value=st.session_state.overwrite,
        key=f"gw_overwrite_{source_id}",
    )
    st.session_state.overwrite = gw_overwrite

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

    st.session_state.max_digest_tokens = st.number_input(
        "Max digest tokens",
        min_value=1000,
        max_value=32000,
        value=int(st.session_state.max_digest_tokens),
        step=500,
        key=f"gw_max_tokens_{source_id}",
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
            value=False,
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
        ("Flashcards", entry.get("flashcards_path")),
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


def _show_result_summary(title: str, data: dict) -> None:
    st.success(title)
    for key, value in data.items():
        if isinstance(value, list):
            st.write(f"**{key}:**")
            for item in value:
                st.write(f"- {item}")
        else:
            st.write(f"**{key}:** {value}")


def page_dashboard(course_name: str | None) -> None:
    st.header("Dashboard")
    if not course_name:
        st.write("Create a course to get started.")
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
        st.info("No sources registered yet.")
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
    st.header("Courses")

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


def page_sources(course_name: str | None) -> None:
    st.header("Sources")
    if not _require_course():
        return

    st.subheader("Registered sources")
    sources = _source_options(course_name)
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
    st.header("Pipeline")
    if not _require_course():
        return

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="pipeline_source")
    if not source_id:
        return

    _render_guided_workflow(course_name, source_id)
    pipeline_status = _render_pipeline_doctor(course_name, source_id)
    _render_study_pack(course_name, source_id, pipeline_status)

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
    st.session_state.max_digest_tokens = st.number_input(
        "Max tokens per chunk",
        min_value=1000,
        max_value=32000,
        value=int(st.session_state.max_digest_tokens),
        step=500,
        help="Incomplete digests retry with +2000 tokens. Default 6000.",
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
            _show_result_summary("Extraction complete", summary)
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
    st.header("Audits")
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


def page_active_recall(course_name: str | None) -> None:
    st.header("Active Recall")
    if not _require_course():
        return

    st.caption(
        "Practice one question at a time and self-grade (no AI). "
        "Requires a generated study pack with an active recall file."
    )

    sources = _source_options(course_name)
    source_id = _select_source(sources, key="ar_source")
    if not source_id:
        return

    try:
        questions = load_questions_for_source(course_name, source_id)
        summary = summarize_active_recall_log(course_name, source_id)
    except ActiveRecallNotReadyError as exc:
        st.warning(str(exc))
        st.info("Generate a study pack on the **Pipeline** page first.")
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


def page_review_tracker(course_name: str | None) -> None:
    st.header("Review Tracker")
    if not _require_course():
        return

    st.caption(
        "Track mistakes and weak points from active recall (deterministic, no AI)."
    )

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
    st.header("Study Session")
    if not _require_course():
        return

    st.caption(
        "Work through today's review priorities in one place: active recall, "
        "mistakes, and weak points. Self-graded only (no AI)."
    )

    session_key = f"study_session_{course_name}"
    limit = st.number_input("Item limit", min_value=1, max_value=30, value=10, step=1)

    if st.button("Start new session", key=f"ss_start_{course_name}"):
        try:
            summary = start_study_session(course_name, limit=int(limit))
            session = get_latest_study_session(course_name)
            st.session_state[session_key] = session
            st.success(f"Started `{summary['session_id']}` with {summary['item_count']} items.")
            st.rerun()
        except Exception as exc:
            _show_exception(exc)

    session = st.session_state.get(session_key)
    if session is None:
        session = get_latest_study_session(course_name)
        if session:
            st.session_state[session_key] = session

    if not session:
        st.info("No study session yet. Click **Start new session** when you have open mistakes, weak points, or recall gaps.")
        return

    session_id = session.get("session_id", "")
    items = session.get("items", [])
    completed = session.get("completed_items", [])
    completed_ids = {c.get("session_item_id") for c in completed}

    st.subheader("Current session")
    st.write(f"**ID:** `{session_id}` — **Status:** {session.get('status', '')}")
    st.progress(
        len(completed_ids) / len(items) if items else 0.0,
        text=f"{len(completed_ids)} / {len(items)} items completed",
    )

    if not items:
        st.warning("This session has no priority items. Add mistakes, weak points, or practice active recall first.")
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

    if item_type == "active_recall":
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
    st.header("Settings")
    root = Path(st.session_state.project_root)
    try:
        config = load_config(root)
        courses_dir = get_courses_dir(root, config)
    except Exception as exc:
        _show_exception(exc)
        return

    st.write(f"**Project root:** `{root}`")
    st.write(f"**Courses directory:** `{courses_dir}`")
    st.write(f"**Default LM Studio URL:** `{DEFAULT_BASE_URL}`")
    st.subheader("Google AI (intermediate audit)")
    has_key = bool(get_google_api_key(root))
    st.write(
        "API key status:",
        "configured" if has_key else "not set",
    )
    st.caption(
        "Preferred: gitignored `.env` with `GOOGLE_API_KEY=...` (see `.env.example`). "
        "Also: Windows user env var, `config/local_secrets.json`, or Save below."
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
        "LM Studio URL is on the Pipeline page. "
        "General config: `config/studyforge_config.json`."
    )


def run() -> None:
    """Entry point for Streamlit."""
    st.set_page_config(page_title="StudyForge", page_icon="📚", layout="wide")
    _init_session_state()
    page, course_name = _render_sidebar()

    if page == "Dashboard":
        page_dashboard(course_name)
    elif page == "Courses":
        page_courses()
    elif page == "Sources":
        page_sources(course_name)
    elif page == "Pipeline":
        page_pipeline(course_name)
    elif page == "Audits":
        page_audits(course_name)
    elif page == "Active Recall":
        page_active_recall(course_name)
    elif page == "Review Tracker":
        page_review_tracker(course_name)
    elif page == "Study Session":
        page_study_session(course_name)
    elif page == "Settings":
        page_settings()


def main() -> None:
    run()


if __name__ == "__main__":
    main()

"""
StudyForge Streamlit GUI — wraps existing CLI backend functions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

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
    generate_study_pack,
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


def _render_pipeline_doctor(course_name: str, source_id: str) -> dict | None:
    """Show pipeline checklist, warnings, and next recommended action."""
    st.subheader("Pipeline Doctor")
    if st.button("Refresh pipeline status", key=f"refresh_pipeline_{source_id}"):
        st.session_state.pop(f"pipeline_status_{source_id}", None)

    cache_key = f"pipeline_status_{source_id}"
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = get_pipeline_status(course_name, source_id)
        except Exception as exc:
            _show_exception(exc)
            return None

    status = st.session_state[cache_key]
    action = status.get("next_action", {})

    st.info(
        f"**Next:** {action.get('label', '—')} — {action.get('reason', '')}"
    )
    if action.get("gui_hint"):
        st.caption(action["gui_hint"])

    st.write(f"Registry status: `{status.get('registry_status', 'unknown')}`")

    for key, label in STEP_ORDER:
        step = status["steps"][key]
        icon = "✅" if step["done"] else "⬜"
        detail = step.get("details") or ""
        line = f"{icon} **{label}**"
        if detail:
            line += f" — {detail}"
        st.write(line)

    warnings = status.get("warnings") or []
    if warnings:
        st.write("**Warnings**")
        for warning in warnings:
            st.warning(warning)

    return status


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

    if st.button("Generate study pack", key=f"gen_study_pack_{source_id}"):
        try:
            with st.spinner("Generating study pack…"):
                summary = generate_study_pack(
                    course_name,
                    source_id,
                    overwrite=pack_overwrite,
                )
            st.session_state.pop(f"pipeline_status_{source_id}", None)
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

    pipeline_status = _render_pipeline_doctor(course_name, source_id)
    _render_study_pack(course_name, source_id, pipeline_status)

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

    st.subheader("Run steps")

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
    elif page == "Settings":
        page_settings()


def main() -> None:
    run()


if __name__ == "__main__":
    main()

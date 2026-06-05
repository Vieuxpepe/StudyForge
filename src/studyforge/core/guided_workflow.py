"""
Guided Workflow v1 — run one Pipeline Doctor recommended step at a time (not autonomous).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studyforge.audits.final_packet import build_final_audit_packet
from studyforge.audits.intermediate_packet import build_intermediate_audit_packet
from studyforge.core.chunking_jobs import chunk_registered_source
from studyforge.core.digest_jobs import DEFAULT_DIGEST_MAX_TOKENS, run_local_digest_for_source
from studyforge.core.extraction_jobs import extract_registered_source
from studyforge.core.pipeline_status import get_pipeline_status
from studyforge.llm.lm_studio_client import DEFAULT_BASE_URL
from studyforge.study.digest_review import review_local_digest_for_source
from studyforge.study.study_pack import generate_study_pack

# Keys the guided runner can execute (one click = one step).
RUNNABLE_ACTION_KEYS = frozenset(
    {
        "extract_pdf",
        "chunk_source",
        "run_local_digest",
        "review_local_digest",
        "export_or_run_intermediate_audit",
        "export_final_audit_packet",
        "generate_study_pack",
    }
)

_ACTION_DESCRIPTIONS: dict[str, str] = {
    "extract_pdf": "Extract readable text from the registered PDF.",
    "chunk_source": "Split extracted text into chunk files for digest and audits.",
    "run_local_digest": (
        "Run LM Studio digest on chunk(s). Default: first chunk only; "
        "use full digest option for all chunks."
    ),
    "review_local_digest": "Run rule-based quality review on local digests (no AI).",
    "export_or_run_intermediate_audit": (
        "Export intermediate audit packet for manual Gemini / AI Studio review. "
        "Does not call Google AI automatically."
    ),
    "export_final_audit_packet": (
        "Export final audit packet for manual ChatGPT review. "
        "Import the result on the Audits page."
    ),
    "generate_study_pack": (
        "Generate study guide, flashcards, quiz, and active recall from "
        "the latest final audit (no AI)."
    ),
    "study_pack_ready": (
        "Study pack is ready. Practice on the Active Recall page and track "
        "mistakes on Review Tracker."
    ),
    "source_missing": (
        "Source file is missing on disk. Re-upload the PDF on the Sources page."
    ),
}


class UnsupportedGuidedActionError(Exception):
    """Raised when the action cannot be run by guided workflow."""


def default_guided_options() -> dict[str, Any]:
    """Default options for ``run_guided_next_step``."""
    return {
        "overwrite": False,
        "base_url": DEFAULT_BASE_URL,
        "model": None,
        "max_tokens": DEFAULT_DIGEST_MAX_TOKENS,
        "max_words": 1200,
        "overlap_words": 150,
        "limit_chunks": None,
        "only_needs_review": False,
        "full_digest": False,
    }


def _merge_options(options: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_guided_options()
    if options:
        merged.update(options)
    return merged


def _normalize_guided_action(
    pipeline_action: dict[str, str],
    pipeline_status: dict,
) -> dict[str, Any]:
    """Build a guided-action dict from Pipeline Doctor output."""
    key = pipeline_action.get("key", "")
    label = pipeline_action.get("label", key)
    description = _ACTION_DESCRIPTIONS.get(key, pipeline_action.get("reason", ""))

    can_run = key in RUNNABLE_ACTION_KEYS
    requires_user_input = False
    warning: str | None = None

    if key == "study_pack_ready":
        can_run = False
        warning = "Pipeline complete for this source. Use Active Recall to practice."
    elif key == "source_missing":
        can_run = False
        warning = "Fix the missing source file before running pipeline steps."
    elif key == "export_or_run_intermediate_audit":
        warning = (
            "Guided step exports the packet only. Import or run automated audit "
            "manually on the Audits page."
        )
    elif key == "export_final_audit_packet":
        warning = (
            "Guided step exports the packet only. Paste/import the final audit "
            "on the Audits page."
        )
    elif key == "chunk_source":
        quality = pipeline_status.get("extraction_quality_status")
        if quality == "failed":
            warning = (
                "Extraction quality failed. Inspect the extraction report "
                "before chunking."
            )
        elif quality == "needs_review":
            warning = (
                "Extraction quality needs review. Some pages may be empty "
                "or low-text."
            )

    return {
        "key": key,
        "label": label,
        "description": description,
        "reason": pipeline_action.get("reason", ""),
        "gui_hint": pipeline_action.get("gui_hint", ""),
        "can_run": can_run,
        "requires_user_input": requires_user_input,
        "warning": warning,
        "warnings": list(pipeline_status.get("warnings") or []),
        "registry_status": pipeline_status.get("registry_status", ""),
        "completed_steps": pipeline_status.get("completed_steps", []),
        "missing_steps": pipeline_status.get("missing_steps", []),
    }


def get_guided_next_action(
    course_name: str,
    source_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """
    Return normalized next action from Pipeline Doctor for the GUI/CLI.

    One click runs exactly one step when ``can_run`` is True.
    """
    status = get_pipeline_status(course_name, source_id, root)
    return _normalize_guided_action(status.get("next_action", {}), status)


def run_guided_next_step(
    course_name: str,
    source_id: str,
    action_key: str | None = None,
    root: Path | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run exactly one guided pipeline step.

    Raises:
        UnsupportedGuidedActionError: Action cannot be run automatically.
    """
    opts = _merge_options(options)
    guided = get_guided_next_action(course_name, source_id, root)
    key = (action_key or guided["key"]).strip()

    if key not in RUNNABLE_ACTION_KEYS and key != "study_pack_ready":
        raise UnsupportedGuidedActionError(
            f"Action {key!r} cannot be run by guided workflow. "
            f"Reason: {guided.get('reason', '')}"
        )

    if key == "study_pack_ready":
        return {
            "action_key": key,
            "success": True,
            "message": _ACTION_DESCRIPTIONS["study_pack_ready"],
            "summary": {},
        }

    summary: dict[str, Any]
    if key == "extract_pdf":
        summary = extract_registered_source(
            course_name,
            source_id,
            root=root,
            overwrite=bool(opts["overwrite"]),
        )
    elif key == "chunk_source":
        summary = chunk_registered_source(
            course_name,
            source_id,
            max_words=int(opts["max_words"]),
            overlap_words=int(opts["overlap_words"]),
            overwrite=bool(opts["overwrite"]),
            root=root,
        )
    elif key == "run_local_digest":
        limit = None if opts.get("full_digest") else 1
        if opts.get("limit_chunks") is not None:
            limit = opts["limit_chunks"]
        summary = run_local_digest_for_source(
            course_name,
            source_id,
            base_url=str(opts["base_url"]),
            model=opts.get("model"),
            max_tokens=int(opts["max_tokens"]),
            temperature=float(opts.get("temperature", 0.2)),
            timeout=int(opts.get("timeout", 300)),
            limit_chunks=limit,
            overwrite=bool(opts["overwrite"]),
            root=root,
        )
    elif key == "review_local_digest":
        summary = review_local_digest_for_source(course_name, source_id, root=root)
    elif key == "export_or_run_intermediate_audit":
        summary = build_intermediate_audit_packet(
            course_name,
            source_id,
            limit_chunks=opts.get("limit_chunks"),
            only_needs_review=bool(opts["only_needs_review"]),
            overwrite=bool(opts["overwrite"]),
            root=root,
        )
    elif key == "export_final_audit_packet":
        summary = build_final_audit_packet(
            course_name,
            source_id,
            limit_chunks=opts.get("limit_chunks"),
            only_needs_review=bool(opts["only_needs_review"]),
            overwrite=bool(opts["overwrite"]),
            root=root,
        )
    elif key == "generate_study_pack":
        summary = generate_study_pack(
            course_name,
            source_id,
            overwrite=bool(opts["overwrite"]),
            root=root,
        )
    else:
        raise UnsupportedGuidedActionError(f"Unsupported action: {key}")

    return {
        "action_key": key,
        "success": True,
        "message": f"Completed: {guided.get('label', key)}",
        "summary": summary,
    }

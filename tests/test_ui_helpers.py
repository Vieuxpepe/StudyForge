"""Tests for Streamlit UI helpers (no Streamlit required)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.ui.helpers import source_pipeline_flags, yes_no  # noqa: E402


def test_source_pipeline_flags_extracted() -> None:
    entry = {"status": "extracted", "extracted_text_path": "/x.md"}
    flags = source_pipeline_flags(entry)
    assert flags["extracted"] is True
    assert yes_no(flags["chunked"]) == "no"


def test_source_pipeline_flags_final() -> None:
    entry = {
        "status": "final_audit_imported",
        "latest_final_audit_id": "FA-SRC-0001-V001",
    }
    flags = source_pipeline_flags(entry)
    assert flags["final_audit"] is True
    assert flags["intermediate_audit"] is True

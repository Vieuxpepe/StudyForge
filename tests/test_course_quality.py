"""Tests for Course Quality Report v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.course_quality import (  # noqa: E402
    build_course_quality_markdown,
    evaluate_source_quality,
    export_course_quality_report,
    get_course_quality_report,
    get_course_quality_report_paths,
)
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.weak_points import add_weak_point  # noqa: E402


def _setup_course(root: Path, entries: list[dict] | None = None) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {"sources": entries or []},
    )
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "studyforge_config.json").write_text(
        json.dumps(
            {
                "project_root": str(root),
                "courses_dir": str(courses),
                "default_course_template": "_Course_Template",
            }
        ),
        encoding="utf-8",
    )
    return course


def _base_entry(**overrides) -> dict:
    entry = {
        "id": "SRC-0001",
        "title": "Main Textbook",
        "source_type": "textbook",
        "stored_path": "",
        "status": "added",
    }
    entry.update(overrides)
    return entry


class TestEvaluateSourceQuality(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pdf = self.root / "book.pdf"
        self.pdf.write_bytes(b"%PDF")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_not_extracted_incomplete(self) -> None:
        course = _setup_course(
            self.root,
            [_base_entry(stored_path=str(self.pdf.resolve()), status="added")],
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["quality_status"], "incomplete")
        self.assertEqual(result["recommended_action"]["key"], "extract_pdf")
        self.assertEqual(result["scores"]["extraction"], "missing")

    def test_extraction_failed(self) -> None:
        ext = self.root / "extracted.md"
        ext.write_text("## Page 1\n\nx", encoding="utf-8")
        _setup_course(
            self.root,
            [
                _base_entry(
                    stored_path=str(self.pdf.resolve()),
                    status="extracted",
                    extracted_text_path=str(ext.resolve()),
                    extraction_quality_status="failed",
                )
            ],
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["quality_status"], "failed")
        self.assertEqual(result["recommended_action"]["key"], "inspect_extraction")

    def test_digest_review_missing(self) -> None:
        course = _setup_course(self.root, [])
        ext_path = course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md"
        ext_path.parent.mkdir(parents=True)
        ext_path.write_text("## Page 1\n\nhello", encoding="utf-8")
        manifest = course / "02_Extracted_Text" / "chunks" / "SRC-0001" / "chunk_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}))
        digest = course / "03_Local_Digests" / "SRC-0001" / "SRC-0001_combined_local_digest.md"
        digest.parent.mkdir(parents=True)
        digest.write_text("# Combined", encoding="utf-8")

        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="local_digest_complete",
                        extracted_text_path=str(ext_path.resolve()),
                        chunk_manifest_path=str(manifest.resolve()),
                        local_digest_path=str(digest.resolve()),
                        extraction_quality_status="ok",
                    )
                ]
            },
        )

        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "review_local_digest")
        self.assertEqual(result["scores"]["local_digest"], "missing")

    def test_missing_final_audit(self) -> None:
        course = _setup_course(self.root, [])
        ext_path = course / "02_Extracted_Text" / "extracted_sources" / "SRC-0001_extracted_text.md"
        ext_path.parent.mkdir(parents=True)
        ext_path.write_text("## Page 1\n\nhello", encoding="utf-8")
        manifest = course / "02_Extracted_Text" / "chunks" / "SRC-0001" / "chunk_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}))
        digest_dir = course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True)
        combined = digest_dir / "SRC-0001_combined_local_digest.md"
        combined.write_text("# Combined", encoding="utf-8")
        review = digest_dir / "SRC-0001_local_digest_review.json"
        review.write_text(json.dumps({"overall_status": "ok"}))
        ia = course / "04_Intermediate_Audits" / "SRC-0001" / "SRC-0001_intermediate.md"
        ia.parent.mkdir(parents=True)
        ia.write_text("# IA", encoding="utf-8")

        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="intermediate_audit_imported",
                        extracted_text_path=str(ext_path.resolve()),
                        chunk_manifest_path=str(manifest.resolve()),
                        local_digest_path=str(combined.resolve()),
                        latest_intermediate_audit_path=str(ia.resolve()),
                        latest_intermediate_audit_id="IA-SRC-0001-V001",
                        extraction_quality_status="ok",
                    )
                ]
            },
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "export_final_audit_packet")
        self.assertEqual(result["scores"]["final_audit"], "missing")

    def test_study_pack_missing(self) -> None:
        course = _setup_course(self.root, [])
        fa = course / "05_Final_Audits" / "SRC-0001" / "SRC-0001_final.md"
        fa.parent.mkdir(parents=True)
        fa.write_text("# Final", encoding="utf-8")
        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="final_audit_imported",
                        latest_final_audit_path=str(fa.resolve()),
                        latest_final_audit_id="FA-SRC-0001-V001",
                        extracted_text_path=str(fa.resolve()),
                        extraction_quality_status="ok",
                    )
                ]
            },
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "generate_study_pack")
        self.assertEqual(result["scores"]["study_pack"], "missing")

    def test_weak_study_pack_quality(self) -> None:
        course = _setup_course(self.root, [])
        manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps(
                {
                    "quality": {"quality_status": "needs_review"},
                    "flashcard_count": 2,
                }
            ),
            encoding="utf-8",
        )
        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="study_pack_generated",
                        study_pack_manifest_path=str(manifest.resolve()),
                        extracted_text_path=str(manifest.resolve()),
                        extraction_quality_status="ok",
                    )
                ]
            },
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "normalize_final_audit")
        self.assertEqual(result["scores"]["study_pack"], "needs_review")

    def test_no_activity_start_study(self) -> None:
        course = _setup_course(self.root, [])
        manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}, "flashcard_count": 5}),
            encoding="utf-8",
        )
        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="study_pack_generated",
                        study_pack_manifest_path=str(manifest.resolve()),
                        extracted_text_path=str(manifest.resolve()),
                        extraction_quality_status="ok",
                    )
                ]
            },
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "start_study")
        self.assertEqual(result["scores"]["study_activity"], "none")

    def test_open_mistakes_review(self) -> None:
        course = _setup_course(self.root, [])
        manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}, "flashcard_count": 5}),
            encoding="utf-8",
        )
        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        stored_path=str(self.pdf.resolve()),
                        status="study_pack_generated",
                        study_pack_manifest_path=str(manifest.resolve()),
                        extracted_text_path=str(manifest.resolve()),
                        extraction_quality_status="ok",
                    )
                ]
            },
        )
        add_mistake(
            "ECA1010_Test",
            source_id="SRC-0001",
            question="Q?",
            user_answer="bad",
            root=self.root,
        )
        result = evaluate_source_quality("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(result["recommended_action"]["key"], "review_study_items")
        self.assertEqual(result["scores"]["study_activity"], "needs_review")


class TestCourseQualityReport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pdf = self.root / "book.pdf"
        self.pdf.write_bytes(b"%PDF")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_course_summary_counts(self) -> None:
        course = _setup_course(self.root, [])
        manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}}),
            encoding="utf-8",
        )
        save_source_registry(
            course,
            {
                "sources": [
                    _base_entry(
                        id="SRC-0001",
                        title="Ready Book",
                        stored_path=str(self.pdf.resolve()),
                        status="study_pack_generated",
                        study_pack_manifest_path=str(manifest.resolve()),
                        extracted_text_path=str(self.pdf.resolve()),
                        extraction_quality_status="ok",
                    ),
                    _base_entry(
                        id="SRC-0002",
                        title="New Source",
                        stored_path=str(self.pdf.resolve()),
                        status="added",
                    ),
                ]
            },
        )

        report = get_course_quality_report("ECA1010_Test", root=self.root)
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["needs_review_count"], 1)
        self.assertEqual(report["sources"][1]["quality_status"], "incomplete")

    def test_export_writes_files(self) -> None:
        course = _setup_course(
            self.root,
            [_base_entry(stored_path=str(self.pdf.resolve()), status="added")],
        )
        result = export_course_quality_report("ECA1010_Test", root=self.root)
        json_path, md_path = get_course_quality_report_paths(course)
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertIn("# Course Quality Report", md_path.read_text(encoding="utf-8"))
        self.assertEqual(result["report_json_path"], str(json_path.resolve()))

    def test_build_markdown_contains_table(self) -> None:
        report = {
            "course": "ECA1010_Test",
            "date": "2026-06-04",
            "source_count": 1,
            "ready_count": 0,
            "needs_review_count": 1,
            "failed_count": 0,
            "sources": [
                {
                    "source_id": "SRC-0001",
                    "title": "Book",
                    "quality_status": "incomplete",
                    "scores": {
                        "extraction": "missing",
                        "local_digest": "missing",
                        "intermediate_audit": "missing",
                        "final_audit": "missing",
                        "study_pack": "missing",
                        "study_activity": "none",
                    },
                    "warnings": ["not extracted"],
                    "recommended_action": {
                        "key": "extract_pdf",
                        "label": "Extract PDF",
                        "reason": "not extracted",
                    },
                }
            ],
            "top_warnings": ["not extracted"],
            "recommended_next_actions": [],
        }
        text = build_course_quality_markdown(report)
        self.assertIn("Source Health Table", text)
        self.assertIn("SRC-0001", text)


class TestCourseQualityCli(unittest.TestCase):
    @patch("scripts.course_quality.get_course_quality_report")
    def test_cli_smoke(self, mock_report) -> None:
        from scripts import course_quality as cli_module

        mock_report.return_value = {
            "course": "ECA1010_Test",
            "date": "2026-06-04",
            "source_count": 1,
            "ready_count": 0,
            "needs_review_count": 1,
            "failed_count": 0,
            "sources": [
                {
                    "source_id": "SRC-0001",
                    "title": "Book",
                    "quality_status": "incomplete",
                    "recommended_action": {
                        "key": "extract_pdf",
                        "label": "Extract PDF",
                        "reason": "not extracted",
                    },
                    "warnings": ["not extracted"],
                }
            ],
            "top_warnings": [],
            "recommended_next_actions": [],
        }
        buffer = StringIO()
        with patch("sys.stdout", buffer):
            code = cli_module.main(["--course", "ECA1010_Test"])
        self.assertEqual(code, 0)
        self.assertIn("Course Quality Report", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

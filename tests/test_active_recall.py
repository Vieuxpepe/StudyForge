"""Tests for Active Recall Mode v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.pipeline_status import get_pipeline_status  # noqa: E402
from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.active_recall import (  # noqa: E402
    ActiveRecallNotReadyError,
    InvalidGradeError,
    export_active_recall_summary_markdown,
    get_active_recall_file,
    get_active_recall_log_path,
    list_active_recall_questions,
    load_active_recall_log,
    parse_active_recall_questions,
    record_active_recall_attempt,
    summarize_active_recall_log,
)

NUMBERED_TEXT = """# Active Recall

Instructions:
Ask one at a time.

1. What is inflation?
2. How do you calculate CPI?
"""

BULLET_TEXT = """# Active Recall

* What is inflation?
* How do you calculate CPI?
"""

HEADING_TEXT = """# Active Recall

## Question 1

What is inflation?

## Question 2

How do you calculate CPI?
"""


class TestActiveRecall(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        self.course.mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)
        (self.root / "config").mkdir()
        (self.root / "config" / "studyforge_config.json").write_text(
            json.dumps(
                {
                    "project_root": str(self.root),
                    "courses_dir": str(courses),
                    "default_course_template": "_Course_Template",
                }
            ),
            encoding="utf-8",
        )
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Main Textbook",
                        "status": "study_pack_generated",
                    }
                ]
            },
        )
        recall_path = get_active_recall_file(self.course, "SRC-0001")
        recall_path.parent.mkdir(parents=True, exist_ok=True)
        recall_path.write_text(NUMBERED_TEXT, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_numbered_questions(self) -> None:
        items = parse_active_recall_questions(NUMBERED_TEXT, "SRC-0001")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["question_id"], "AR-SRC-0001-Q001")
        self.assertEqual(items[0]["question"], "What is inflation?")

    def test_parse_bullet_questions(self) -> None:
        items = parse_active_recall_questions(BULLET_TEXT, "SRC-0001")
        self.assertEqual(len(items), 2)
        self.assertIn("CPI", items[1]["question"])

    def test_parse_heading_questions(self) -> None:
        items = parse_active_recall_questions(HEADING_TEXT, "SRC-0001")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]["question_number"], 2)

    def test_record_attempt_creates_log(self) -> None:
        result = record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "What is inflation?",
            "Rising prices",
            "partial",
            notes="Unsure",
            root=self.root,
        )
        self.assertEqual(result["attempt_id"], "AR-ATTEMPT-0001")
        log_path = get_active_recall_log_path(self.course, "SRC-0001")
        self.assertTrue(log_path.is_file())
        log = load_active_recall_log(log_path)
        self.assertEqual(len(log["attempts"]), 1)
        self.assertEqual(log["attempts"][0]["grade"], "partial")

    def test_invalid_grade_rejected(self) -> None:
        with self.assertRaises(InvalidGradeError):
            record_active_recall_attempt(
                "ECA1010_Test",
                "SRC-0001",
                "AR-SRC-0001-Q001",
                "Q",
                "A",
                "excellent",
                root=self.root,
            )

    def test_summary_counts_and_accuracy(self) -> None:
        grades = [
            ("correct", "a"),
            ("correct", "b"),
            ("correct", "c"),
            ("correct", "d"),
            ("partial", "e"),
            ("partial", "f"),
            ("partial", "g"),
            ("wrong", "h"),
            ("wrong", "i"),
            ("skipped", "j"),
        ]
        for index, (grade, answer) in enumerate(grades, start=1):
            record_active_recall_attempt(
                "ECA1010_Test",
                "SRC-0001",
                f"AR-SRC-0001-Q{index:03d}",
                f"Question {index}",
                answer,
                grade,
                root=self.root,
            )
        summary = summarize_active_recall_log(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        self.assertEqual(summary["attempt_count"], 10)
        self.assertEqual(summary["correct"], 4)
        self.assertEqual(summary["partial"], 3)
        self.assertEqual(summary["wrong"], 2)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["accuracy_percent"], 61.1)
        self.assertEqual(summary["needs_review_count"], 6)

    def test_skipped_excluded_from_accuracy_denominator(self) -> None:
        record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "Q1",
            "a",
            "correct",
            root=self.root,
        )
        record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q002",
            "Q2",
            "",
            "skipped",
            root=self.root,
        )
        summary = summarize_active_recall_log(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        self.assertEqual(summary["accuracy_percent"], 100.0)

    def test_summary_markdown_created(self) -> None:
        record_active_recall_attempt(
            "ECA1010_Test",
            "SRC-0001",
            "AR-SRC-0001-Q001",
            "What is inflation?",
            "Prices rise",
            "wrong",
            root=self.root,
        )
        path = export_active_recall_summary_markdown(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Active Recall Summary", text)
        self.assertIn("Wrong: 1", text)

    def test_list_questions(self) -> None:
        items = list_active_recall_questions(
            "ECA1010_Test", "SRC-0001", root=self.root
        )
        self.assertEqual(len(items), 2)

    def test_not_ready_without_study_pack(self) -> None:
        save_source_registry(
            self.course,
            {"sources": [{"id": "SRC-0002", "title": "Other", "status": "added"}]},
        )
        with self.assertRaises(ActiveRecallNotReadyError):
            list_active_recall_questions("ECA1010_Test", "SRC-0002", root=self.root)

    def test_pipeline_warning_start_recall(self) -> None:
        self._write_pipeline_ready()
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "study_pack_ready")
        self.assertTrue(
            any(
                "Start active recall" in warning
                for warning in status["warnings"]
            )
        )

    def test_pipeline_warning_weak_areas(self) -> None:
        self._write_pipeline_ready()
        for index in range(4):
            record_active_recall_attempt(
                "ECA1010_Test",
                "SRC-0001",
                f"AR-SRC-0001-Q{index + 1:03d}",
                f"Q{index}",
                "x",
                "wrong",
                root=self.root,
            )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(
            any(
                "weak areas" in warning.lower()
                for warning in status["warnings"]
            )
        )

    def _write_pipeline_ready(self) -> None:
        source_dir = self.course / "01_Source_Material" / "textbook"
        source_dir.mkdir(parents=True, exist_ok=True)
        pdf = source_dir / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        ext = self.course / "02_Extracted_Text" / "extracted_sources"
        ext.mkdir(parents=True, exist_ok=True)
        ext_file = ext / "SRC-0001_extracted_text.md"
        ext_file.write_text("# x", encoding="utf-8")
        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        manifest = chunk_dir / "chunk_manifest.json"
        manifest.write_text(
            json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}),
            encoding="utf-8",
        )
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True, exist_ok=True)
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text("# c", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        ia = self.course / "04_Intermediate_Audits" / "SRC-0001"
        ia.mkdir(parents=True, exist_ok=True)
        ia_file = ia / "SRC-0001_intermediate_audit_v001.md"
        ia_file.write_text("# ia", encoding="utf-8")
        fa = self.course / "05_Final_Audits" / "SRC-0001"
        fa.mkdir(parents=True, exist_ok=True)
        fa_file = fa / "SRC-0001_final_audit_v001.md"
        fa_file.write_text("# fa", encoding="utf-8")
        pack_manifest = (
            self.course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        )
        pack_manifest.parent.mkdir(parents=True, exist_ok=True)
        pack_manifest.write_text("{}", encoding="utf-8")
        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Main Textbook",
                        "status": "study_pack_generated",
                        "stored_path": str(pdf.resolve()),
                        "extracted_text_path": str(ext_file.resolve()),
                        "chunk_manifest_path": str(manifest.resolve()),
                        "local_digest_path": str(
                            (digest_dir / "SRC-0001_combined_local_digest.md").resolve()
                        ),
                        "latest_intermediate_audit_path": str(ia_file.resolve()),
                        "latest_final_audit_path": str(fa_file.resolve()),
                        "study_pack_manifest_path": str(pack_manifest.resolve()),
                        "active_recall_path": str(
                            get_active_recall_file(self.course, "SRC-0001").resolve()
                        ),
                    }
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for Better Flashcards v1."""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_import import import_final_audit  # noqa: E402
from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.flashcards import (  # noqa: E402
    FlashcardExportExistsError,
    build_flashcard_from_bullet,
    build_flashcards_from_sections,
    clean_flashcard_text,
    flashcards_to_anki_tsv,
    flashcards_to_csv,
    save_flashcard_exports,
    split_bullets,
)
from studyforge.study.study_pack import extract_sections, generate_study_pack  # noqa: E402

FULL_AUDIT = """# Final Audit

## Final Verdict

Accuracy is good.

## Must-Memorize List

- CPI formula: cost of current basket / cost of base basket × 100
- P = MC in perfect competition

## Must-Understand List

- Why deadweight loss happens

## Formula / Method Sheet

- Elasticity = (% change Q) / (% change P)

## Exam / Homework Traps

- Mixing up shifts vs movements along a curve

## Active Recall Questions

- What is consumer surplus?

## Practice Questions

1. Define price elasticity.
"""


class TestFlashcards(unittest.TestCase):
    def test_split_bullets_dash(self) -> None:
        text = "- First item\n- Second item"
        items = split_bullets(text)
        self.assertEqual(items, ["First item", "Second item"])

    def test_split_bullets_numbered(self) -> None:
        text = "1. Alpha\n2. Beta"
        items = split_bullets(text)
        self.assertEqual(items, ["Alpha", "Beta"])

    def test_split_bullets_multiline(self) -> None:
        text = "- Line one\n  continues here\n- Line two"
        items = split_bullets(text)
        self.assertEqual(len(items), 2)
        self.assertIn("continues here", items[0])

    def test_clean_flashcard_text(self) -> None:
        raw = "**Bold**   term   with   spaces"
        self.assertEqual(clean_flashcard_text(raw), "Bold term with spaces")

    def test_build_flashcard_from_bullet_with_colon(self) -> None:
        card = build_flashcard_from_bullet(
            "CPI formula: cost of current basket / cost of base basket × 100",
            "SRC-0001",
            "Book",
            "Must-Memorize List",
            tag_key="must_memorize",
        )
        self.assertEqual(card["front"], "What is the CPI formula?")
        self.assertIn("cost of current basket", card["back"])
        self.assertEqual(card["tags"], ["SRC-0001", "must_memorize"])

    def test_build_flashcard_from_bullet_without_colon(self) -> None:
        card = build_flashcard_from_bullet(
            "P = MC in perfect competition",
            "SRC-0001",
            "Book",
            "Must-Memorize List",
            tag_key="must_memorize",
        )
        self.assertEqual(card["front"], "What should I remember about this concept?")
        self.assertEqual(card["back"], "P = MC in perfect competition")

    def test_build_flashcards_skips_placeholders(self) -> None:
        sections = {
            "must_memorize": "Not found in final audit.",
            "must_understand": "Not found in original final audit.",
            "formula_sheet": "",
            "exam_traps": "- Real trap",
            "active_recall": "Not found in final audit.",
        }
        cards = build_flashcards_from_sections("SRC-0001", "Book", sections)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["section"], "Exam / Homework Traps")

    def test_deduplication(self) -> None:
        sections = {
            "must_memorize": "- Same item\n- Same item",
            "must_understand": "",
            "formula_sheet": "",
            "exam_traps": "",
            "active_recall": "",
        }
        cards = build_flashcards_from_sections("SRC-0001", "Book", sections)
        self.assertEqual(len(cards), 1)

    def test_csv_export_headers(self) -> None:
        cards = build_flashcards_from_sections(
            "SRC-0001",
            "Book",
            extract_sections(FULL_AUDIT),
        )
        csv_text = flashcards_to_csv(cards)
        rows = list(csv.reader(io.StringIO(csv_text)))
        self.assertEqual(
            rows[0],
            ["front", "back", "source_id", "source_title", "section", "tags"],
        )
        self.assertGreater(len(rows), 1)

    def test_anki_tsv_format(self) -> None:
        cards = [
            {
                "front": "What is CPI?",
                "back": "Consumer Price Index",
                "tags": ["SRC-0001", "must_memorize"],
            }
        ]
        tsv = flashcards_to_anki_tsv(cards)
        parts = tsv.strip().split("\t")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "What is CPI?")
        self.assertEqual(parts[1], "Consumer Price Index")
        self.assertIn("src-0001", parts[2])

    def test_anki_tsv_escapes_newlines(self) -> None:
        cards = [{"front": "Line one\nLine two", "back": "Answer", "tags": ["SRC-0001"]}]
        tsv = flashcards_to_anki_tsv(cards)
        self.assertIn("Line one<br>Line two", tsv)

    def test_save_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            cards = [{"front": "Q", "back": "A", "source_id": "SRC-0001", "source_title": "Book", "section": "Test", "tags": ["SRC-0001"]}]
            save_flashcard_exports("ECA1010_Test", "SRC-0001", cards, root=root)
            with self.assertRaises(FlashcardExportExistsError):
                save_flashcard_exports("ECA1010_Test", "SRC-0001", cards, root=root)

    def test_save_allows_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_course(root)
            cards = [{"front": "Q", "back": "A", "source_id": "SRC-0001", "source_title": "Book", "section": "Test", "tags": ["SRC-0001"]}]
            save_flashcard_exports("ECA1010_Test", "SRC-0001", cards, root=root)
            result = save_flashcard_exports(
                "ECA1010_Test", "SRC-0001", cards, overwrite=True, root=root
            )
            self.assertEqual(result["flashcard_count"], 1)
            self.assertTrue(Path(result["csv_path"]).is_file())
            self.assertTrue(Path(result["anki_tsv_path"]).is_file())

    def test_generate_study_pack_manifest_includes_flashcard_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = self._setup_course(root)
            import_final_audit(
                "ECA1010_Test",
                "SRC-0001",
                audit_text=FULL_AUDIT,
                root=root,
            )
            summary = generate_study_pack("ECA1010_Test", "SRC-0001", root=root)
            self.assertIn("flashcards_csv", summary["outputs"])
            self.assertIn("flashcards_anki_tsv", summary["outputs"])
            self.assertTrue(Path(summary["outputs"]["flashcards_csv"]).is_file())
            self.assertTrue(Path(summary["outputs"]["flashcards_anki_tsv"]).is_file())
            self.assertGreater(summary["flashcard_count"], 0)

            manifest = json.loads(
                Path(summary["manifest_path"]).read_text(encoding="utf-8")
            )
            self.assertIn("flashcards_csv", manifest["outputs"])
            self.assertIn("flashcards_anki_tsv", manifest["outputs"])
            self.assertGreater(manifest["flashcard_count"], 0)

    @patch("scripts.export_flashcards.export_flashcards_from_sections")
    @patch("scripts.export_flashcards.extract_sections")
    @patch("scripts.export_flashcards.get_latest_final_audit")
    @patch("scripts.export_flashcards.resolve_course_path")
    def test_cli_export(
        self, mock_resolve, mock_audit, mock_extract, mock_export
    ) -> None:
        from scripts import export_flashcards as cli_module

        mock_resolve.return_value = Path("/tmp/course")
        mock_audit.return_value = {"text": "# Audit\n", "entry": {}}
        mock_extract.return_value = {"must_memorize": "- Item"}
        mock_export.return_value = {
            "course": "ECA1010_Test",
            "source_id": "SRC-0001",
            "title": "Book",
            "flashcard_count": 5,
            "markdown_path": "/tmp/a.md",
            "csv_path": "/tmp/a.csv",
            "anki_tsv_path": "/tmp/a.tsv",
            "warnings": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--source-id", "SRC-0001"]
        )
        self.assertEqual(code, 0)
        mock_export.assert_called_once()

    def _setup_course(self, root: Path) -> Path:
        courses = root / "courses"
        course = courses / "ECA1010_Test"
        (course / "07_My_Work").mkdir(parents=True)
        (course / "08_App_Data").mkdir(parents=True)
        save_source_registry(
            course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Book",
                        "status": "intermediate_audit_imported",
                    }
                ]
            },
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


if __name__ == "__main__":
    unittest.main()

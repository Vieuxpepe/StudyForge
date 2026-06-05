"""Tests for Unit Study Pack Generator v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import save_source_registry  # noqa: E402
from studyforge.study.study_unit_dashboard import get_study_unit_dashboard  # noqa: E402
from studyforge.study.study_units import create_study_unit, load_study_units  # noqa: E402
from studyforge.study.unit_study_pack import (  # noqa: E402
    UnitStudyPackOutputExistsError,
    analyze_unit_study_pack_sections,
    diagnose_unit_study_pack,
    extract_unit_synthesis_sections,
    generate_unit_study_pack,
    get_unit_study_pack_output_paths,
)
from studyforge.study.unit_synthesis_import import import_unit_synthesis  # noqa: E402


def _valid_synthesis_text() -> str:
    sections = "\n".join(
        f"## {name}\n"
        f"- Detail about {name} with enough words for quality checks.\n"
        for name in (
            "Unit Overview",
            "Core Concepts",
            "Merged Formula / Method Sheet",
            "Cross-Source Connections",
            "Conflicts or Uncertainties",
            "Must-Memorize List",
            "Must-Understand List",
            "Exam / Homework Traps",
            "Practice Questions",
            "Active Recall Questions",
            "Weak Points to Review",
            "Final Unit Checklist",
        )
    )
    return f"# Unit Synthesis\n\n{sections}\n"


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "00_Master").mkdir(parents=True)
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {"sources": [{"id": "SRC-0001", "title": "Book", "status": "study_pack_generated"}]},
    )
    manifest = course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"quality": {"quality_status": "ok"}}),
        encoding="utf-8",
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


class TestUnitStudyPack(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.unit = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_extract_sections(self) -> None:
        sections = extract_unit_synthesis_sections(_valid_synthesis_text())
        self.assertIn("Core Concepts", sections["core_concepts"])
        self.assertIn("Practice Questions", sections["practice_questions"])
        self.assertNotEqual(sections["core_concepts"], "Not found in unit synthesis.")

    def test_quality_ok(self) -> None:
        sections = extract_unit_synthesis_sections(_valid_synthesis_text())
        quality = analyze_unit_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "ok")
        self.assertGreaterEqual(quality["total_extracted_words"], 100)

    def test_quality_failed_short(self) -> None:
        sections = extract_unit_synthesis_sections("# Unit Synthesis\n\n## Unit Overview\nHi\n")
        quality = analyze_unit_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "failed")

    def test_quality_needs_review_missing_important(self) -> None:
        text = (
            "# Unit Synthesis\n\n## Unit Overview\n"
            + " ".join(["word"] * 120)
            + "\n## Cross-Source Connections\nLinks here.\n"
            "## Conflicts or Uncertainties\nNone noted.\n"
            "## Must-Memorize List\n- Item A\n"
            "## Must-Understand List\n- Item B\n"
            "## Exam / Homework Traps\n- Trap one\n"
            "## Weak Points to Review\n- Weak one\n"
            "## Final Unit Checklist\n- Check done\n"
        )
        sections = extract_unit_synthesis_sections(text)
        quality = analyze_unit_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "needs_review")

    def test_diagnose_only_writes_nothing(self) -> None:
        paths = get_unit_study_pack_output_paths(self.course, self.unit["unit_id"])
        diag = diagnose_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(diag["quality"]["quality_status"], "ok")
        self.assertFalse(paths["manifest"].is_file())

    def test_generate_writes_all_outputs(self) -> None:
        result = generate_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        paths = get_unit_study_pack_output_paths(self.course, self.unit["unit_id"])
        self.assertTrue(paths["unit_study_guide"].is_file())
        self.assertTrue(paths["unit_flashcards"].is_file())
        self.assertTrue(paths["unit_flashcards_csv"].is_file())
        self.assertTrue(paths["unit_flashcards_anki_tsv"].is_file())
        self.assertTrue(paths["unit_practice_quiz"].is_file())
        self.assertTrue(paths["unit_active_recall"].is_file())
        self.assertTrue(paths["unit_formula_sheet"].is_file())
        self.assertTrue(paths["manifest"].is_file())
        guide = paths["unit_study_guide"].read_text(encoding="utf-8")
        self.assertIn("# Unit Study Guide", guide)
        self.assertGreaterEqual(result["flashcard_count"], 1)

    def test_manifest_metadata(self) -> None:
        result = generate_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["unit_id"], self.unit["unit_id"])
        self.assertEqual(manifest["based_on_unit_synthesis_id"], "US-UNIT-0001-V001")
        self.assertIn("quality", manifest)
        self.assertIn("outputs", manifest)
        self.assertGreaterEqual(manifest["flashcard_count"], 1)

    def test_overwrite_refusal_and_allow(self) -> None:
        generate_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        with self.assertRaises(UnitStudyPackOutputExistsError):
            generate_unit_study_pack(
                "ECA1010_Test", self.unit["unit_id"], root=self.root
            )
        generate_unit_study_pack(
            "ECA1010_Test",
            self.unit["unit_id"],
            overwrite=True,
            root=self.root,
        )

    def test_study_units_json_updated(self) -> None:
        generate_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        data = load_study_units("ECA1010_Test", root=self.root)
        unit = data["units"][0]
        self.assertTrue(unit.get("latest_unit_study_pack_manifest_path"))
        self.assertTrue(unit.get("latest_unit_study_guide_path"))
        self.assertTrue(unit.get("date_unit_study_pack_generated"))

    def test_dashboard_shows_unit_pack(self) -> None:
        generate_unit_study_pack(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertTrue(dashboard["has_unit_study_pack"])
        self.assertEqual(dashboard["latest_unit_study_pack_quality"], "ok")

    def test_dashboard_recommends_generate_pack(self) -> None:
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(
            dashboard["recommended_action"]["key"],
            "generate_unit_study_pack",
        )

    @patch("scripts.generate_unit_study_pack.generate_unit_study_pack")
    def test_cli_smoke(self, mock_generate) -> None:
        from scripts import generate_unit_study_pack as cli_module

        mock_generate.return_value = {
            "course": "ECA1010_Test",
            "unit_id": "UNIT-0001",
            "title": "Inflation",
            "based_on_unit_synthesis_id": "US-UNIT-0001-V001",
            "quality_status": "ok",
            "flashcard_count": 5,
            "manifest_path": "/tmp/m.json",
            "warnings": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--unit-id", "UNIT-0001"]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

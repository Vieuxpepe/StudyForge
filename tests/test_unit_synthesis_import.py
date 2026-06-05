"""Tests for Unit Synthesis Import v1."""

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
from studyforge.study.unit_synthesis_import import (  # noqa: E402
    EmptySynthesisError,
    SynthesisInputError,
    analyze_unit_synthesis_quality,
    build_unit_synthesis_file_name,
    get_next_unit_synthesis_version,
    get_unit_synthesis_dir,
    get_unit_synthesis_registry_path,
    import_unit_synthesis,
    load_unit_synthesis_registry,
)


def _valid_synthesis_text() -> str:
    sections = "\n".join(
        f"## {name}\nContent for {name} with enough detail.\n"
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


class TestUnitSynthesisImport(unittest.TestCase):
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

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_import_from_text(self) -> None:
        result = import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        self.assertEqual(result["quality_status"], "ok")
        self.assertTrue(Path(result["file_path"]).is_file())
        self.assertEqual(result["synthesis_id"], "US-UNIT-0001-V001")

    def test_import_from_file(self) -> None:
        path = self.root / "synthesis.md"
        path.write_text(_valid_synthesis_text(), encoding="utf-8")
        result = import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_file=path,
            root=self.root,
        )
        self.assertTrue(result["file_path"].endswith("_synthesis_v001.md"))

    def test_reject_both_file_and_text(self) -> None:
        with self.assertRaises(SynthesisInputError):
            import_unit_synthesis(
                "ECA1010_Test",
                self.unit["unit_id"],
                synthesis_text="x",
                synthesis_file=Path("x.md"),
                root=self.root,
            )

    def test_reject_neither(self) -> None:
        with self.assertRaises(SynthesisInputError):
            import_unit_synthesis(
                "ECA1010_Test", self.unit["unit_id"], root=self.root
            )

    def test_reject_empty(self) -> None:
        with self.assertRaises(EmptySynthesisError):
            import_unit_synthesis(
                "ECA1010_Test",
                self.unit["unit_id"],
                synthesis_text="   ",
                root=self.root,
            )

    def test_version_increments(self) -> None:
        import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        second = import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        self.assertEqual(second["synthesis_id"], "US-UNIT-0001-V002")
        reg_path = get_unit_synthesis_registry_path(self.course, self.unit["unit_id"])
        registry = load_unit_synthesis_registry(reg_path, self.unit["unit_id"])
        self.assertEqual(len(registry["syntheses"]), 2)

    def test_study_units_json_updated(self) -> None:
        import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        data = load_study_units("ECA1010_Test", root=self.root)
        unit = data["units"][0]
        self.assertEqual(unit["latest_synthesis_id"], "US-UNIT-0001-V001")
        self.assertTrue(unit.get("latest_synthesis_path"))
        self.assertTrue(unit.get("date_synthesis_imported"))

    def test_quality_ok_with_headings(self) -> None:
        quality = analyze_unit_synthesis_quality(_valid_synthesis_text())
        self.assertEqual(quality["quality_status"], "ok")
        self.assertGreaterEqual(quality["word_count"], 100)

    def test_quality_failed_short_text(self) -> None:
        quality = analyze_unit_synthesis_quality("too short")
        self.assertEqual(quality["quality_status"], "failed")

    def test_quality_needs_review_missing_important(self) -> None:
        text = (
            "# Unit Synthesis\n\n"
            "## Unit Overview\n"
            + "word " * 120
            + "\n## Cross-Source Connections\n"
            "Links.\n## Conflicts or Uncertainties\n"
            "None.\n"
        )
        quality = analyze_unit_synthesis_quality(text)
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertTrue(
            any(s in quality["missing_sections"] for s in ("Core Concepts",))
        )

    def test_disk_scan_recovery(self) -> None:
        synth_dir = get_unit_synthesis_dir(self.course, self.unit["unit_id"])
        fname = build_unit_synthesis_file_name(self.unit["unit_id"], 2)
        (synth_dir / fname).write_text(_valid_synthesis_text(), encoding="utf-8")
        version = get_next_unit_synthesis_version(
            {"unit_id": self.unit["unit_id"], "syntheses": []},
            synth_dir,
            self.unit["unit_id"],
        )
        self.assertEqual(version, 3)

    def test_dashboard_shows_latest_synthesis(self) -> None:
        import_unit_synthesis(
            "ECA1010_Test",
            self.unit["unit_id"],
            synthesis_text=_valid_synthesis_text(),
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertTrue(dashboard["has_unit_synthesis"])
        self.assertEqual(dashboard["latest_synthesis_id"], "US-UNIT-0001-V001")
        self.assertEqual(dashboard["latest_synthesis_quality"], "ok")

    @patch("scripts.import_unit_synthesis.import_unit_synthesis")
    def test_cli_smoke(self, mock_import) -> None:
        from scripts import import_unit_synthesis as cli_module

        mock_import.return_value = {
            "course": "ECA1010_Test",
            "unit_id": "UNIT-0001",
            "unit_title": "Inflation",
            "synthesis_id": "US-UNIT-0001-V001",
            "quality_status": "ok",
            "file_path": "/tmp/s.md",
            "registry_path": "/tmp/r.json",
            "warnings": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--unit-id", "UNIT-0001", "--text", "x"]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

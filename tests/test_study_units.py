"""Tests for Study Units v1."""

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
from studyforge.study.study_units import (  # noqa: E402
    InvalidSourceIdError,
    StudyUnitNotFoundError,
    add_sources_to_unit,
    count_active_study_units,
    create_study_unit,
    get_study_unit_summary,
    list_study_units,
    load_study_units,
    remove_sources_from_unit,
    update_study_unit,
)
from studyforge.study.today_dashboard import get_today_dashboard  # noqa: E402


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "00_Master").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {
            "sources": [
                {"id": "SRC-0001", "title": "Textbook Chapter", "status": "added"},
                {"id": "SRC-0002", "title": "Teacher Slides", "status": "added"},
                {"id": "SRC-0003", "title": "Homework", "status": "added"},
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


class TestStudyUnits(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_and_list_study_unit(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            description="Quiz 2",
            source_ids=["SRC-0001", "SRC-0002"],
            tags=["quiz2", "inflation"],
            root=self.root,
        )
        self.assertEqual(unit["unit_id"], "UNIT-0001")
        self.assertEqual(unit["title"], "Inflation and CPI")
        self.assertEqual(unit["source_ids"], ["SRC-0001", "SRC-0002"])
        self.assertEqual(unit["status"], "active")

        units = list_study_units("ECA1010_Test", root=self.root)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["unit_id"], "UNIT-0001")

    def test_reject_invalid_source_id(self) -> None:
        with self.assertRaises(InvalidSourceIdError):
            create_study_unit(
                "ECA1010_Test",
                "Bad unit",
                source_ids=["SRC-9999"],
                root=self.root,
            )

    def test_update_unit_status(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        updated = update_study_unit(
            "ECA1010_Test",
            unit["unit_id"],
            status="completed",
            root=self.root,
        )
        self.assertEqual(updated["status"], "completed")

    def test_add_sources_without_duplicates(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        updated = add_sources_to_unit(
            "ECA1010_Test",
            unit["unit_id"],
            ["SRC-0002", "SRC-0001"],
            root=self.root,
        )
        self.assertEqual(updated["source_ids"], ["SRC-0001", "SRC-0002"])

    def test_remove_sources(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        updated = remove_sources_from_unit(
            "ECA1010_Test",
            unit["unit_id"],
            ["SRC-0002"],
            root=self.root,
        )
        self.assertEqual(updated["source_ids"], ["SRC-0001"])

    def test_summary_counts_ready_and_incomplete(self) -> None:
        manifest = (
            self.course
            / "06_Study_Outputs"
            / "SRC-0001_study_pack_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "quality": {"quality_status": "ok"},
                    "based_on_final_audit_id": "FA-SRC-0001-V001",
                }
            ),
            encoding="utf-8",
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        summary = get_study_unit_summary(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["ready_sources"], 1)
        self.assertEqual(summary["incomplete_sources"], 1)

    def test_summary_recommended_action_missing_study_pack(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        summary = get_study_unit_summary(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        action = summary["recommended_action"]
        self.assertEqual(action["key"], "process_incomplete_sources")
        self.assertIn("study pack", action["reason"].lower())

    def test_load_missing_returns_empty(self) -> None:
        data = load_study_units("ECA1010_Test", root=self.root)
        self.assertEqual(data, {"units": []})

    def test_unit_not_found(self) -> None:
        with self.assertRaises(StudyUnitNotFoundError):
            get_study_unit_summary("ECA1010_Test", "UNIT-9999", root=self.root)


class TestStudyUnitsTodayDashboard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_active_unit_count_and_recommended_action(self) -> None:
        create_study_unit(
            "ECA1010_Test",
            "Quiz 2 prep",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        self.assertEqual(count_active_study_units("ECA1010_Test", root=self.root), 1)

        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)

        self.assertEqual(dashboard["summary"]["active_study_units"], 1)
        self.assertEqual(
            dashboard["recommended_actions"][0]["key"],
            "review_active_units",
        )


class TestStudyUnitsCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_create_and_list(self) -> None:
        import importlib.util
        from unittest.mock import patch

        scripts_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "study_units.py"
        )
        spec = importlib.util.spec_from_file_location("study_units_cli", scripts_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with patch("studyforge.core.sources.find_project_root", return_value=self.root):
            rc = module.main(
                [
                    "--course",
                    "ECA1010_Test",
                    "--create",
                    "--title",
                    "Inflation and CPI",
                    "--sources",
                    "SRC-0001",
                ]
            )
            self.assertEqual(rc, 0)
            rc_list = module.main(["--course", "ECA1010_Test", "--list"])
            self.assertEqual(rc_list, 0)
            units = list_study_units("ECA1010_Test", root=self.root)
            self.assertEqual(len(units), 1)


if __name__ == "__main__":
    unittest.main()

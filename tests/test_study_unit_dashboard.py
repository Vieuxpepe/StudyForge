"""Tests for Study Unit Dashboard v1."""

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

from studyforge.core.sources import resolve_course_path, save_source_registry  # noqa: E402
from studyforge.study.flashcard_review import (  # noqa: E402
    get_flashcard_review_log_path,
    save_flashcard_review_log,
)
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.study_unit_dashboard import (  # noqa: E402
    UnitReviewPlanExistsError,
    export_unit_dashboard,
    generate_unit_review_plan,
    get_study_unit_dashboard,
    get_unit_dashboard_paths,
    get_unit_review_plan_path,
    get_unit_source_ids,
)
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.unit_study_pack import generate_unit_study_pack  # noqa: E402
from studyforge.study.unit_synthesis_import import import_unit_synthesis  # noqa: E402
from studyforge.study.today_dashboard import get_today_dashboard  # noqa: E402
from studyforge.study.weak_points import add_weak_point  # noqa: E402


def _setup_course(root: Path) -> Path:
    courses = root / "courses"
    course = courses / "ECA1010_Test"
    (course / "00_Master").mkdir(parents=True)
    (course / "07_My_Work").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {
            "sources": [
                {"id": "SRC-0001", "title": "Textbook", "status": "added"},
                {"id": "SRC-0002", "title": "Slides", "status": "added"},
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


class TestStudyUnitDashboard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_get_unit_source_ids(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Inflation",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        ids = get_unit_source_ids("ECA1010_Test", unit["unit_id"], root=self.root)
        self.assertEqual(ids, ["SRC-0001", "SRC-0002"])

    def test_dashboard_counts_ready_and_incomplete(self) -> None:
        manifest = (
            self.course
            / "06_Study_Outputs"
            / "SRC-0001_study_pack_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}}),
            encoding="utf-8",
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(dashboard["ready_sources"], 1)
        self.assertEqual(dashboard["incomplete_sources"], 1)

    def test_review_summary_filters_due_flashcards(self) -> None:
        log_path = get_flashcard_review_log_path(self.course, "SRC-0001")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        save_flashcard_review_log(
            log_path,
            {
                "source_id": "SRC-0001",
                "reviews": [
                    {
                        "card_id": "FC-SRC-0001-0001",
                        "grade": "hard",
                        "due_date": "2026-06-04",
                        "front": "Q1",
                        "back": "A1",
                    }
                ],
            },
        )
        save_flashcard_review_log(
            get_flashcard_review_log_path(self.course, "SRC-0003"),
            {
                "source_id": "SRC-0003",
                "reviews": [
                    {
                        "card_id": "FC-SRC-0003-0001",
                        "grade": "hard",
                        "due_date": "2026-06-04",
                        "front": "Other",
                        "back": "X",
                    }
                ],
            },
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        with patch(
            "studyforge.study.study_unit_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_study_unit_dashboard(
                "ECA1010_Test", unit["unit_id"], root=self.root
            )
        self.assertEqual(dashboard["review_summary"]["due_flashcards"], 1)

    def test_review_summary_filters_mistakes_and_weak_points(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "Q1",
            "bad",
            root=self.root,
        )
        add_mistake(
            "ECA1010_Test",
            "SRC-0003",
            "Other",
            "bad",
            root=self.root,
        )
        add_weak_point(
            "ECA1010_Test",
            "SRC-0002",
            "Concept",
            root=self.root,
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(dashboard["review_summary"]["open_mistakes"], 1)
        self.assertEqual(dashboard["review_summary"]["open_weak_points"], 1)

    def test_recommended_action_add_sources_for_empty_unit(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Empty",
            source_ids=[],
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(dashboard["recommended_action"]["key"], "add_sources")

    def test_recommended_action_process_incomplete_sources(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(
            dashboard["recommended_action"]["key"],
            "process_incomplete_sources",
        )

    def test_recommended_action_generate_unit_review_plan(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "Q",
            "bad",
            root=self.root,
        )
        manifest = (
            self.course
            / "06_Study_Outputs"
            / "SRC-0001_study_pack_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}}),
            encoding="utf-8",
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        synthesis_body = (
            "# Unit Synthesis\n\n## Unit Overview\n"
            + " ".join(["detail"] * 120)
            + "\n## Core Concepts\nC\n## Merged Formula / Method Sheet\nF\n"
            "## Cross-Source Connections\nX\n## Conflicts or Uncertainties\nY\n"
            "## Must-Memorize List\nM\n## Must-Understand List\nU\n"
            "## Exam / Homework Traps\nT\n## Practice Questions\nP\n"
            "## Active Recall Questions\nA\n## Weak Points to Review\nW\n"
            "## Final Unit Checklist\nDone\n"
        )
        import_unit_synthesis(
            "ECA1010_Test",
            unit["unit_id"],
            synthesis_text=synthesis_body,
            root=self.root,
        )
        generate_unit_study_pack(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(
            dashboard["recommended_action"]["key"],
            "generate_unit_review_plan",
        )

    def test_recommended_action_create_synthesis_when_ready(self) -> None:
        manifest = (
            self.course
            / "06_Study_Outputs"
            / "SRC-0001_study_pack_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}}),
            encoding="utf-8",
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        self.assertEqual(
            dashboard["recommended_action"]["key"],
            "export_or_import_unit_synthesis",
        )

    def test_dashboard_warns_when_unit_pack_is_stale(self) -> None:
        manifest = (
            self.course
            / "06_Study_Outputs"
            / "SRC-0001_study_pack_manifest.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"quality": {"quality_status": "ok"}}),
            encoding="utf-8",
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        synthesis_body = (
            "# Unit Synthesis\n\n## Unit Overview\n"
            + " ".join(["detail"] * 120)
            + "\n## Core Concepts\nC\n## Merged Formula / Method Sheet\nF\n"
            "## Cross-Source Connections\nX\n## Conflicts or Uncertainties\nY\n"
            "## Must-Memorize List\nM\n## Must-Understand List\nU\n"
            "## Exam / Homework Traps\nT\n## Practice Questions\nP\n"
            "## Active Recall Questions\nA\n## Weak Points to Review\nW\n"
            "## Final Unit Checklist\nDone\n"
        )
        import_unit_synthesis(
            "ECA1010_Test",
            unit["unit_id"],
            synthesis_text=synthesis_body,
            root=self.root,
        )
        generate_unit_study_pack(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        import_unit_synthesis(
            "ECA1010_Test",
            unit["unit_id"],
            synthesis_text=synthesis_body + "\nExtra update.\n",
            root=self.root,
        )

        dashboard = get_study_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )

        self.assertTrue(dashboard["stale_unit_study_pack"])
        self.assertEqual(
            dashboard["based_on_unit_study_pack_synthesis_id"],
            "US-UNIT-0001-V001",
        )
        self.assertEqual(dashboard["latest_synthesis_id"], "US-UNIT-0001-V002")
        self.assertEqual(
            dashboard["recommended_action"]["key"],
            "generate_unit_study_pack",
        )
        self.assertTrue(
            any("stale" in warning.lower() for warning in dashboard["warnings"])
        )

    def test_export_dashboard_writes_files(self) -> None:
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        result = export_unit_dashboard(
            "ECA1010_Test", unit["unit_id"], root=self.root
        )
        md_path = Path(result["markdown_path"])
        json_path = Path(result["json_path"])
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertIn("Study Unit Dashboard", md_path.read_text(encoding="utf-8"))

    def test_generate_unit_review_plan_writes_unit_files(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "Q",
            "bad",
            root=self.root,
        )
        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        with patch(
            "studyforge.study.study_unit_dashboard._local_today_str",
            return_value="2026-06-04",
        ):
            result = generate_unit_review_plan(
                "ECA1010_Test",
                unit["unit_id"],
                root=self.root,
            )
        course_path = resolve_course_path("ECA1010_Test", self.root)
        md_path = get_unit_review_plan_path(
            course_path, unit["unit_id"], "2026-06-04"
        )
        self.assertTrue(md_path.is_file())
        self.assertEqual(result["markdown_path"], str(md_path.resolve()))
        self.assertIn("Study Unit Review Plan", md_path.read_text(encoding="utf-8"))

        with patch(
            "studyforge.study.study_unit_dashboard._local_today_str",
            return_value="2026-06-04",
        ):
            with self.assertRaises(UnitReviewPlanExistsError):
                generate_unit_review_plan(
                    "ECA1010_Test",
                    unit["unit_id"],
                    root=self.root,
                )


class TestStudyUnitDashboardToday(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_today_lists_active_unit_titles(self) -> None:
        create_study_unit(
            "ECA1010_Test",
            "Quiz 2 prep",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-04",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(len(dashboard.get("active_units", [])), 1)
        self.assertEqual(dashboard["active_units"][0]["title"], "Quiz 2 prep")


class TestStudyUnitDashboardCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_dashboard_and_export(self) -> None:
        import importlib.util
        from unittest.mock import patch

        unit = create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        scripts_path = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "study_unit_dashboard.py"
        )
        spec = importlib.util.spec_from_file_location(
            "study_unit_dashboard_cli", scripts_path
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with patch("studyforge.core.sources.find_project_root", return_value=self.root):
            self.assertEqual(
                module.main(
                    [
                        "--course",
                        "ECA1010_Test",
                        "--unit-id",
                        unit["unit_id"],
                    ]
                ),
                0,
            )
            self.assertEqual(
                module.main(
                    [
                        "--course",
                        "ECA1010_Test",
                        "--unit-id",
                        unit["unit_id"],
                        "--export",
                    ]
                ),
                0,
            )
            course_path = resolve_course_path("ECA1010_Test", self.root)
            md_path, json_path = get_unit_dashboard_paths(
                course_path, unit["unit_id"]
            )
            self.assertTrue(md_path.is_file())
            self.assertTrue(json_path.is_file())


if __name__ == "__main__":
    unittest.main()

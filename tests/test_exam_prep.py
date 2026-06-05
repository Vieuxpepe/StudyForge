"""Tests for Exam Targets and Exam Prep Planner v1."""

from __future__ import annotations

import importlib.util
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
from studyforge.study.exam_prep import (  # noqa: E402
    ExamPrepPlanExistsError,
    build_exam_prep_plan_markdown,
    collect_exam_prep_state,
    generate_exam_prep_plan,
    get_days_until_exam,
    get_exam_scope_source_ids,
    recommend_exam_prep_actions,
)
from studyforge.study.exam_targets import (  # noqa: E402
    ExamTargetNotFoundError,
    InvalidExamDateError,
    InvalidExamUnitIdError,
    InvalidTargetScoreError,
    create_exam_target,
    get_exam_targets_path,
    list_exam_targets,
    update_exam_target,
)
from studyforge.study.mock_tests import record_mock_test_attempt  # noqa: E402
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.today_dashboard import get_today_dashboard  # noqa: E402


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
                {"id": "SRC-0001", "title": "Textbook", "status": "study_pack_generated"},
                {"id": "SRC-0002", "title": "Slides", "status": "added"},
                {"id": "SRC-0005", "title": "Homework", "status": "added"},
            ]
        },
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


class TestExamTargets(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.unit1 = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        self.unit2 = create_study_unit(
            "ECA1010_Test",
            "GDP Deflator",
            source_ids=["SRC-0002"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_exam_target(self) -> None:
        target = create_exam_target(
            "ECA1010_Test",
            "Quiz 2",
            "2026-06-20",
            description="Inflation, CPI, GDP deflator",
            target_score=80,
            unit_ids=[self.unit1["unit_id"], self.unit2["unit_id"]],
            source_ids=["SRC-0005"],
            root=self.root,
        )
        self.assertEqual(target["exam_id"], "EXAM-0001")
        self.assertEqual(target["target_score"], 80)
        path = get_exam_targets_path(self.course)
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["exam_targets"]), 1)

    def test_invalid_date_rejected(self) -> None:
        with self.assertRaises(InvalidExamDateError):
            create_exam_target(
                "ECA1010_Test",
                "Bad date",
                "20-06-2026",
                root=self.root,
            )

    def test_invalid_score_rejected(self) -> None:
        with self.assertRaises(InvalidTargetScoreError):
            create_exam_target(
                "ECA1010_Test",
                "Quiz",
                "2026-06-20",
                target_score=150,
                root=self.root,
            )

    def test_invalid_unit_rejected(self) -> None:
        with self.assertRaises(InvalidExamUnitIdError):
            create_exam_target(
                "ECA1010_Test",
                "Quiz",
                "2026-06-20",
                unit_ids=["UNIT-9999"],
                root=self.root,
            )

    def test_invalid_source_rejected(self) -> None:
        from studyforge.study.study_units import InvalidSourceIdError

        with self.assertRaises(InvalidSourceIdError):
            create_exam_target(
                "ECA1010_Test",
                "Quiz",
                "2026-06-20",
                source_ids=["SRC-9999"],
                root=self.root,
            )

    def test_update_exam_status(self) -> None:
        target = create_exam_target(
            "ECA1010_Test",
            "Quiz 2",
            "2026-06-20",
            root=self.root,
        )
        updated = update_exam_target(
            "ECA1010_Test",
            target["exam_id"],
            status="completed",
            root=self.root,
        )
        self.assertEqual(updated["status"], "completed")


class TestExamPrep(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        self.unit1 = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        self.unit2 = create_study_unit(
            "ECA1010_Test",
            "GDP Deflator",
            source_ids=["SRC-0002"],
            root=self.root,
        )
        self.exam = create_exam_target(
            "ECA1010_Test",
            "Quiz 2",
            "2026-06-20",
            target_score=80,
            unit_ids=[self.unit1["unit_id"], self.unit2["unit_id"]],
            source_ids=["SRC-0005"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_expand_exam_scope(self) -> None:
        scope = get_exam_scope_source_ids(
            "ECA1010_Test", self.exam["exam_id"], root=self.root
        )
        self.assertEqual(
            set(scope["source_ids"]),
            {"SRC-0001", "SRC-0002", "SRC-0005"},
        )
        self.assertEqual(len(scope["unit_ids"]), 2)

    def test_days_until_exam(self) -> None:
        self.assertEqual(get_days_until_exam("2026-06-20", "2026-06-10"), 10)
        self.assertEqual(get_days_until_exam("2026-06-01", "2026-06-10"), -9)

    def test_collect_prep_state_filters_by_scope(self) -> None:
        add_mistake(
            "ECA1010_Test",
            "SRC-0001",
            "In scope",
            "bad",
            root=self.root,
        )
        add_mistake(
            "ECA1010_Test",
            "SRC-0003",
            "Out of scope",
            "bad",
            root=self.root,
        )
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            state = collect_exam_prep_state(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        self.assertEqual(state["days_until_exam"], 10)
        mistakes = state["review"]["open_mistakes"]
        self.assertEqual(len(mistakes), 1)
        self.assertEqual(mistakes[0]["source_id"], "SRC-0001")
        incomplete = state["readiness"]["incomplete_sources"]
        incomplete_ids = {item["source_id"] for item in incomplete}
        self.assertIn("SRC-0002", incomplete_ids)
        self.assertIn("SRC-0005", incomplete_ids)
        self.assertNotIn("SRC-0001", incomplete_ids)

    def test_recommend_incomplete_source(self) -> None:
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            state = collect_exam_prep_state(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        actions = recommend_exam_prep_actions(state)
        keys = [action["key"] for action in actions]
        self.assertIn("process_incomplete_sources", keys)

    def test_recommend_mock_test_when_exam_soon(self) -> None:
        soon_exam = create_exam_target(
            "ECA1010_Test",
            "Soon quiz",
            "2026-06-12",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            state = collect_exam_prep_state(
                "ECA1010_Test", soon_exam["exam_id"], root=self.root
            )
        actions = recommend_exam_prep_actions(state)
        keys = [action["key"] for action in actions]
        self.assertIn("generate_mock_test", keys)

    def test_plan_markdown_includes_checklist(self) -> None:
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            state = collect_exam_prep_state(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        actions = recommend_exam_prep_actions(state)
        md = build_exam_prep_plan_markdown(
            "ECA1010_Test", self.exam["exam_id"], state, actions
        )
        self.assertIn("## 7-Day Checklist", md)
        self.assertIn("## Final Exam Checklist", md)
        self.assertIn("Quiz 2", md)
        self.assertIn("## Study Session", md)
        self.assertIn("EXAM-0001", md)
        self.assertIn("exam-focused study session", md)

    def test_generate_plan_writes_md_json(self) -> None:
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            result = generate_exam_prep_plan(
                "ECA1010_Test",
                self.exam["exam_id"],
                root=self.root,
            )
        md_path = Path(result["markdown_path"])
        json_path = Path(result["json_path"])
        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertIn("Exam Prep Plan", md_path.read_text(encoding="utf-8"))

        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            with self.assertRaises(ExamPrepPlanExistsError):
                generate_exam_prep_plan(
                    "ECA1010_Test",
                    self.exam["exam_id"],
                    root=self.root,
                )

    def test_mock_attempts_linked_to_scope(self) -> None:
        record_mock_test_attempt(
            "ECA1010_Test",
            "MT-SRC-0001-TEST",
            "source",
            "SRC-0001",
            None,
            14,
            20,
            root=self.root,
        )
        with patch(
            "studyforge.study.exam_prep.today_date_str",
            return_value="2026-06-10",
        ):
            state = collect_exam_prep_state(
                "ECA1010_Test", self.exam["exam_id"], root=self.root
            )
        self.assertEqual(state["mock_tests"]["attempt_count"], 1)
        self.assertEqual(state["mock_tests"]["latest_score"], 70.0)


class TestTodayExamIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)
        create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        create_exam_target(
            "ECA1010_Test",
            "Quiz 2",
            "2026-06-12",
            source_ids=["SRC-0001"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_today_dashboard_nearest_exam(self) -> None:
        with patch(
            "studyforge.study.today_dashboard.today_date_str",
            return_value="2026-06-10",
        ):
            dashboard = get_today_dashboard("ECA1010_Test", root=self.root)
        self.assertEqual(dashboard["summary"]["active_exam_targets"], 1)
        nearest = dashboard["summary"]["nearest_exam"]
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest["title"], "Quiz 2")
        self.assertEqual(nearest["days_until_exam"], 2)


class TestExamTargetsCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _setup_course(self.root)
        create_study_unit(
            "ECA1010_Test",
            "Topic",
            source_ids=["SRC-0001"],
            root=self.root,
        )
        scripts_path = (
            Path(__file__).resolve().parent.parent / "scripts" / "exam_targets.py"
        )
        spec = importlib.util.spec_from_file_location("exam_targets_cli", scripts_path)
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_create_and_list_smoke(self) -> None:
        with patch(
            "studyforge.core.sources.find_project_root", return_value=self.root
        ):
            code = self.module.main(
                [
                    "--course",
                    "ECA1010_Test",
                    "--create",
                    "--title",
                    "Quiz 2",
                    "--date",
                    "2026-06-20",
                    "--units",
                    "UNIT-0001",
                    "--sources",
                    "SRC-0005",
                ]
            )
            self.assertEqual(code, 0)
            targets = list_exam_targets("ECA1010_Test", root=self.root)
            self.assertEqual(len(targets), 1)
            code = self.module.main(["--course", "ECA1010_Test", "--list"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

"""Tests for Unit Synthesis Packet v1."""

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
from studyforge.study.mistakes import add_mistake  # noqa: E402
from studyforge.study.study_units import create_study_unit  # noqa: E402
from studyforge.study.unit_synthesis_packet import (  # noqa: E402
    UnitSynthesisPacketExistsError,
    build_unit_synthesis_instructions,
    build_unit_synthesis_packet,
    collect_unit_learning_state,
    collect_unit_source_outputs,
)
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
                {"id": "SRC-0001", "title": "Textbook", "status": "study_pack_generated"},
                {"id": "SRC-0002", "title": "Slides", "status": "added"},
                {"id": "SRC-0003", "title": "Other", "status": "added"},
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


def _write_study_outputs(course: Path, source_id: str = "SRC-0001") -> None:
    base = course / "06_Study_Outputs"
    (base / "study_guides").mkdir(parents=True, exist_ok=True)
    (base / "formula_sheets").mkdir(parents=True, exist_ok=True)
    (base / "quizzes").mkdir(parents=True, exist_ok=True)
    (base / "active_recall").mkdir(parents=True, exist_ok=True)
    (base / "study_guides" / f"{source_id}_final_study_guide.md").write_text(
        f"# Guide for {source_id}\n", encoding="utf-8"
    )
    (base / "formula_sheets" / f"{source_id}_formula_sheet.md").write_text(
        f"# Formulas for {source_id}\n", encoding="utf-8"
    )
    (base / "quizzes" / f"{source_id}_practice_quiz.md").write_text(
        f"# Quiz for {source_id}\n", encoding="utf-8"
    )
    (base / "active_recall" / f"{source_id}_active_recall.md").write_text(
        f"# Recall for {source_id}\n", encoding="utf-8"
    )
    (base / f"{source_id}_study_pack_manifest.json").write_text(
        json.dumps({"quality": {"quality_status": "ok"}}),
        encoding="utf-8",
    )


class TestUnitSynthesisPacket(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)
        _write_study_outputs(self.course, "SRC-0001")
        self.unit = create_study_unit(
            "ECA1010_Test",
            "Inflation and CPI",
            source_ids=["SRC-0001", "SRC-0002"],
            root=self.root,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_instructions_include_output_format(self) -> None:
        text = build_unit_synthesis_instructions()
        self.assertIn("unit synthesis tutor", text.lower())
        self.assertIn("# Unit Synthesis", text)
        self.assertIn("## Core Concepts", text)

    def test_collect_source_outputs_includes_guides(self) -> None:
        data = collect_unit_source_outputs(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        src1 = next(s for s in data["sources"] if s["source_id"] == "SRC-0001")
        self.assertIn("Guide for SRC-0001", src1["final_study_guide_text"])
        self.assertIn("Formulas for SRC-0001", src1["formula_sheet_text"])
        self.assertIn("Quiz for SRC-0001", src1["practice_quiz_text"])
        self.assertEqual(src1["study_pack_quality"], "ok")

    def test_missing_outputs_add_warnings(self) -> None:
        data = collect_unit_source_outputs(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        src2 = next(s for s in data["sources"] if s["source_id"] == "SRC-0002")
        self.assertTrue(src2["warnings"])
        self.assertIn("Final study guide not found.", src2["warnings"])

    def test_collect_learning_state_filters_by_unit(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "In unit", "bad", root=self.root)
        add_mistake("ECA1010_Test", "SRC-0003", "Outside", "bad", root=self.root)
        add_weak_point(
            "ECA1010_Test", "SRC-0002", "Unit concept", root=self.root
        )
        state = collect_unit_learning_state(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        self.assertEqual(len(state["open_mistakes"]), 1)
        self.assertEqual(state["open_mistakes"][0]["source_id"], "SRC-0001")
        self.assertEqual(len(state["open_weak_points"]), 1)
        self.assertEqual(state["open_weak_points"][0]["source_id"], "SRC-0002")

    def test_build_packet_includes_instructions_and_sources(self) -> None:
        result = build_unit_synthesis_packet(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        text = Path(result["packet_path"]).read_text(encoding="utf-8")
        self.assertIn("# Unit Synthesis Packet", text)
        self.assertIn("## Instructions", text)
        self.assertIn("unit synthesis tutor", text.lower())
        self.assertIn("## Source SRC-0001", text)
        self.assertIn("Guide for SRC-0001", text)

    def test_build_packet_includes_learning_state(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        result = build_unit_synthesis_packet(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        text = Path(result["packet_path"]).read_text(encoding="utf-8")
        self.assertIn("## Unit Learning State", text)
        self.assertIn("### Open Mistakes", text)
        self.assertIn("Q", text)

    def test_no_learning_state_excludes_section(self) -> None:
        add_mistake("ECA1010_Test", "SRC-0001", "Q", "A", root=self.root)
        result = build_unit_synthesis_packet(
            "ECA1010_Test",
            self.unit["unit_id"],
            root=self.root,
            include_learning_state=False,
        )
        text = Path(result["packet_path"]).read_text(encoding="utf-8")
        self.assertNotIn("## Unit Learning State", text)
        meta = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
        self.assertFalse(meta["include_learning_state"])

    def test_overwrite_refusal_and_allow(self) -> None:
        build_unit_synthesis_packet(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        with self.assertRaises(UnitSynthesisPacketExistsError):
            build_unit_synthesis_packet(
                "ECA1010_Test", self.unit["unit_id"], root=self.root
            )
        result = build_unit_synthesis_packet(
            "ECA1010_Test",
            self.unit["unit_id"],
            root=self.root,
            overwrite=True,
        )
        self.assertTrue(Path(result["packet_path"]).is_file())

    def test_metadata_json_written(self) -> None:
        result = build_unit_synthesis_packet(
            "ECA1010_Test", self.unit["unit_id"], root=self.root
        )
        meta = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
        self.assertEqual(meta["unit_id"], self.unit["unit_id"])
        self.assertIn("SRC-0001", meta["included_sources"])
        self.assertEqual(meta["source_count"], 2)

    @patch("scripts.unit_synthesis_packet.build_unit_synthesis_packet")
    def test_cli_smoke(self, mock_build) -> None:
        from scripts import unit_synthesis_packet as cli_module

        mock_build.return_value = {
            "unit_id": "UNIT-0001",
            "unit_title": "Inflation",
            "source_count": 2,
            "packet_path": "/tmp/packet.md",
            "warnings": [],
            "metadata": {"unit_id": "UNIT-0001"},
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--unit-id", "UNIT-0001"]
        )
        self.assertEqual(code, 0)
        mock_build.assert_called_once_with(
            "ECA1010_Test",
            "UNIT-0001",
            include_learning_state=True,
            overwrite=False,
        )


if __name__ == "__main__":
    unittest.main()

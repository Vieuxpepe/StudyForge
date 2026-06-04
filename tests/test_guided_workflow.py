"""Tests for Guided Workflow v1."""

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

from studyforge.core.guided_workflow import (  # noqa: E402
    UnsupportedGuidedActionError,
    get_guided_next_action,
    run_guided_next_step,
)


def _pipeline_status(next_key: str) -> dict:
    return {
        "registry_status": "added",
        "warnings": [],
        "completed_steps": [],
        "missing_steps": ["PDF extracted"],
        "next_action": {
            "key": next_key,
            "label": f"Label for {next_key}",
            "reason": f"Reason for {next_key}",
            "gui_hint": "hint",
        },
        "steps": {},
    }


class TestGetGuidedNextAction(unittest.TestCase):
    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_extract_pdf(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("extract_pdf")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "extract_pdf")
        self.assertTrue(action["can_run"])
        self.assertIn("PDF", action["description"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_chunk_source(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("chunk_source")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "chunk_source")
        self.assertTrue(action["can_run"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_run_local_digest(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("run_local_digest")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "run_local_digest")
        self.assertTrue(action["can_run"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_review_local_digest(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("review_local_digest")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "review_local_digest")
        self.assertTrue(action["can_run"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_export_intermediate(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("export_or_run_intermediate_audit")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "export_or_run_intermediate_audit")
        self.assertTrue(action["can_run"])
        self.assertIn("Does not call Google AI", action["description"])
        self.assertIn("exports the packet only", action["warning"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_export_final(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("export_final_audit_packet")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "export_final_audit_packet")
        self.assertTrue(action["can_run"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_generate_study_pack(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("generate_study_pack")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "generate_study_pack")
        self.assertTrue(action["can_run"])

    @patch("studyforge.core.guided_workflow.get_pipeline_status")
    def test_maps_study_pack_ready_not_runnable(self, mock_status) -> None:
        mock_status.return_value = _pipeline_status("study_pack_ready")
        action = get_guided_next_action("Course", "SRC-0001")
        self.assertEqual(action["key"], "study_pack_ready")
        self.assertFalse(action["can_run"])
        self.assertIn("Active Recall", action["description"])


class TestRunGuidedNextStep(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_rejects_unknown_action(self, mock_guided) -> None:
        mock_guided.return_value = {
            "key": "source_missing",
            "label": "Fix source",
            "can_run": False,
        }
        with self.assertRaises(UnsupportedGuidedActionError):
            run_guided_next_step("Course", "SRC-0001", action_key="source_missing")

    @patch("studyforge.core.guided_workflow.extract_registered_source")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_calls_extract(self, mock_guided, mock_extract) -> None:
        mock_guided.return_value = {"key": "extract_pdf", "label": "Extract PDF"}
        mock_extract.return_value = {"extracted_text_path": "/tmp/out.md"}
        result = run_guided_next_step(
            "Course", "SRC-0001", action_key="extract_pdf", root=self.root
        )
        mock_extract.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["extracted_text_path"], "/tmp/out.md")

    @patch("studyforge.core.guided_workflow.chunk_registered_source")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_calls_chunk(self, mock_guided, mock_chunk) -> None:
        mock_guided.return_value = {"key": "chunk_source", "label": "Chunk"}
        mock_chunk.return_value = {"chunk_count": 5}
        result = run_guided_next_step(
            "Course", "SRC-0001", action_key="chunk_source", root=self.root
        )
        mock_chunk.assert_called_once()
        self.assertEqual(result["summary"]["chunk_count"], 5)

    @patch("studyforge.core.guided_workflow.run_local_digest_for_source")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_digest_default_limit_one(self, mock_guided, mock_digest) -> None:
        mock_guided.return_value = {"key": "run_local_digest", "label": "Digest"}
        mock_digest.return_value = {"chunks_processed": 1}
        run_guided_next_step(
            "Course", "SRC-0001", action_key="run_local_digest", root=self.root
        )
        self.assertEqual(mock_digest.call_args.kwargs["limit_chunks"], 1)

    @patch("studyforge.core.guided_workflow.run_local_digest_for_source")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_digest_full_when_option_set(self, mock_guided, mock_digest) -> None:
        mock_guided.return_value = {"key": "run_local_digest", "label": "Digest"}
        mock_digest.return_value = {"chunks_processed": 10}
        run_guided_next_step(
            "Course",
            "SRC-0001",
            action_key="run_local_digest",
            options={"full_digest": True},
            root=self.root,
        )
        self.assertIsNone(mock_digest.call_args.kwargs["limit_chunks"])

    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_study_pack_ready_message(self, mock_guided) -> None:
        mock_guided.return_value = {
            "key": "study_pack_ready",
            "label": "Study pack ready",
        }
        result = run_guided_next_step(
            "Course", "SRC-0001", action_key="study_pack_ready", root=self.root
        )
        self.assertTrue(result["success"])
        self.assertIn("Active Recall", result["message"])


class TestRunNextStepCli(unittest.TestCase):
    @patch("studyforge.core.guided_workflow.run_guided_next_step")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_cli_parsing(self, mock_guided, mock_run) -> None:
        from scripts import run_next_step

        mock_guided.return_value = {
            "key": "extract_pdf",
            "label": "Extract PDF",
            "reason": "need extract",
            "can_run": True,
            "warning": None,
        }
        mock_run.return_value = {
            "action_key": "extract_pdf",
            "success": True,
            "message": "ok",
            "summary": {},
        }
        code = run_next_step.main(
            [
                "--course",
                "ECA1010_Test",
                "--source-id",
                "SRC-0001",
                "--full-digest",
                "--overwrite",
            ]
        )
        self.assertEqual(code, 0)
        opts = mock_run.call_args.kwargs["options"]
        self.assertTrue(opts["full_digest"])
        self.assertTrue(opts["overwrite"])


if __name__ == "__main__":
    unittest.main()

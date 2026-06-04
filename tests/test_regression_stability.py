"""High-value regression tests for status flow, parsing, CLI, and privacy."""

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

from studyforge.audits.final_audit_normalizer import (  # noqa: E402
    EXPECTED_FINAL_AUDIT_HEADINGS,
    NormalizedAuditExistsError,
    normalize_final_audit_text,
    normalize_latest_final_audit,
)
from studyforge.audits.final_import import import_final_audit  # noqa: E402
from studyforge.core.guided_workflow import RUNNABLE_ACTION_KEYS, run_guided_next_step  # noqa: E402
from studyforge.core.pipeline_status import get_pipeline_status  # noqa: E402
from studyforge.core.sources import load_source_registry, save_source_registry  # noqa: E402
from studyforge.study.study_pack import (  # noqa: E402
    StudyPackOutputExistsError,
    _SECTION_HEADINGS,
    diagnose_study_pack,
    extract_markdown_section,
    generate_study_pack,
    get_latest_final_audit,
)
from studyforge.ui.helpers import source_pipeline_flags  # noqa: E402

NESTED_AUDIT = """# Final Audit

## Corrections That Matter Most

Intro.

### Correction 1

Problem A.

### Correction 2

Problem B.

## Better Explanations

### Real vs. Nominal

Nominal shelf price.

## Must-Memorize List

Fact.

## Must-Understand List

Idea.

## Formula / Method Sheet

F = x.

## Exam / Homework Traps

Trap.

## Practice Questions

Q1.

## Active Recall Questions

R1.

## Final Study Checklist

Done.

## Remaining Uncertainties

Maybe.

## Final Verdict

OK.

## Missing Concepts

Gap.
"""

MINIMAL_PIPELINE_AUDIT = """## Final Verdict
ok
## Corrections That Matter Most
fix
## Missing Concepts
gap
## Better Explanations
tip
## Must-Memorize List
a
## Must-Understand List
b
## Formula / Method Sheet
c
## Exam / Homework Traps
d
## Practice Questions
e
## Active Recall Questions
f
## Final Study Checklist
g
## Remaining Uncertainties
h
"""


def _setup_course(root: Path, course_name: str = "ECA1010_Test") -> Path:
    courses = root / "courses"
    course = courses / course_name
    source_dir = course / "01_Source_Material" / "textbook"
    source_dir.mkdir(parents=True)
    pdf = source_dir / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    (course / "04_Intermediate_Audits" / "SRC-0001").mkdir(parents=True)
    (course / "05_Final_Audits" / "SRC-0001").mkdir(parents=True)
    (course / "08_App_Data").mkdir(parents=True)
    save_source_registry(
        course,
        {
            "sources": [
                {
                    "id": "SRC-0001",
                    "title": "Book",
                    "status": "intermediate_audit_imported",
                    "stored_path": str(pdf.resolve()),
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


class TestStatusAndRegistryFlow(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_final_import_after_study_pack_generated(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        summary = import_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text="## Final Verdict\n\nRevised.\n",
            root=self.root,
        )
        self.assertEqual(summary["audit_id"], "FA-SRC-0001-V002")
        reg = load_source_registry(self.course)
        self.assertEqual(reg["sources"][0]["status"], "final_audit_imported")
        self.assertTrue(
            any("study pack" in w.lower() for w in summary.get("warnings", []))
        )

    def test_normalized_import_after_study_pack_generated(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=NESTED_AUDIT, root=self.root
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        summary = normalize_latest_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            overwrite=True,
            import_as_new_version=True,
            root=self.root,
        )
        self.assertIsNotNone(summary["imported_audit_id"])
        latest = get_latest_final_audit(self.course, "SRC-0001")
        self.assertIn("### Correction 1", latest["text"])

    def test_study_pack_uses_latest_final_audit_version(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text="## Final Verdict\n\nV1 only.\n", root=self.root
        )
        import_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text=MINIMAL_PIPELINE_AUDIT,
            root=self.root,
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        latest = get_latest_final_audit(self.course, "SRC-0001")
        self.assertEqual(latest["entry"]["audit_id"], "FA-SRC-0001-V002")
        sections = latest["text"]
        self.assertIn("Must-Memorize List", sections)

    def _pipeline_ready_entry(self, **extra: object) -> None:
        """Fill registry paths so Pipeline Doctor sees a complete source."""
        ext_dir = self.course / "02_Extracted_Text" / "extracted_sources"
        ext_dir.mkdir(parents=True, exist_ok=True)
        ext_file = ext_dir / "SRC-0001_extracted_text.md"
        ext_file.write_text("# Extracted\n\nBody", encoding="utf-8")
        chunk_dir = self.course / "02_Extracted_Text" / "chunks" / "SRC-0001"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        manifest = chunk_dir / "chunk_manifest.json"
        manifest.write_text(
            json.dumps({"chunks": [{"chunk_id": "SRC-0001-CHUNK-0001"}]}),
            encoding="utf-8",
        )
        digest_dir = self.course / "03_Local_Digests" / "SRC-0001"
        digest_dir.mkdir(parents=True, exist_ok=True)
        (digest_dir / "SRC-0001_combined_local_digest.md").write_text("# d", encoding="utf-8")
        (digest_dir / "SRC-0001_local_digest_review.json").write_text("{}", encoding="utf-8")
        ia_file = self.course / "04_Intermediate_Audits" / "SRC-0001" / "SRC-0001_intermediate_audit_v001.md"
        ia_file.write_text("# IA", encoding="utf-8")
        reg = load_source_registry(self.course)
        entry = reg["sources"][0]
        entry.update(
            {
                "extracted_text_path": str(ext_file.resolve()),
                "chunk_manifest_path": str(manifest.resolve()),
                "latest_intermediate_audit_path": str(ia_file.resolve()),
            }
        )
        entry.update(extra)
        save_source_registry(self.course, reg)

    def test_pipeline_generate_study_pack_after_final_import(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        latest = get_latest_final_audit(self.course, "SRC-0001")
        self._pipeline_ready_entry(
            status="final_audit_imported",
            latest_final_audit_path=latest["file_path"],
            latest_final_audit_id=latest["entry"]["audit_id"],
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "generate_study_pack")

    def test_pipeline_study_pack_ready_when_manifest_exists(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        latest = get_latest_final_audit(self.course, "SRC-0001")
        pack_manifest = self.course / "06_Study_Outputs" / "SRC-0001_study_pack_manifest.json"
        audit_id = latest["entry"]["audit_id"]
        pack_manifest.write_text(
            json.dumps({"based_on_final_audit_id": audit_id}),
            encoding="utf-8",
        )
        self._pipeline_ready_entry(
            status="study_pack_generated",
            latest_final_audit_path=latest["file_path"],
            latest_final_audit_id=audit_id,
            study_pack_manifest_path=str(pack_manifest.resolve()),
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertEqual(status["next_action"]["key"], "study_pack_ready")
        self.assertTrue(status["steps"]["study_pack_generated"]["done"])
        self.assertFalse(any("stale" in w.lower() for w in status["warnings"]))

    def test_stale_study_pack_suggests_regenerate(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        import_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text=MINIMAL_PIPELINE_AUDIT.replace("ok", "updated"),
            root=self.root,
        )
        latest = get_latest_final_audit(self.course, "SRC-0001")
        pack_manifest = Path(
            load_source_registry(self.course)["sources"][0]["study_pack_manifest_path"]
        )
        self._pipeline_ready_entry(
            status="final_audit_imported",
            latest_final_audit_path=latest["file_path"],
            latest_final_audit_id=latest["entry"]["audit_id"],
            study_pack_manifest_path=str(pack_manifest.resolve()),
        )
        status = get_pipeline_status("ECA1010_Test", "SRC-0001", root=self.root)
        self.assertTrue(status["steps"]["study_pack_generated"]["done"])
        self.assertTrue(any("stale" in w.lower() for w in status["warnings"]))
        self.assertEqual(status["next_action"]["key"], "generate_study_pack")
        self.assertIn("Regenerate", status["next_action"]["label"])

    @patch("studyforge.core.guided_workflow.generate_study_pack")
    @patch("studyforge.core.guided_workflow.get_guided_next_action")
    def test_guided_can_regenerate_when_stale(
        self, mock_guided, mock_generate
    ) -> None:
        from studyforge.core.guided_workflow import run_guided_next_step

        mock_guided.return_value = {
            "key": "generate_study_pack",
            "label": "Regenerate study pack",
            "can_run": True,
        }
        mock_generate.return_value = {"quality_status": "ok"}
        result = run_guided_next_step(
            "ECA1010_Test",
            "SRC-0001",
            action_key="generate_study_pack",
            options={"overwrite": True},
            root=self.root,
        )
        self.assertTrue(result["success"])
        mock_generate.assert_called_once()

    def test_gui_flags_include_study_pack_generated(self) -> None:
        flags = source_pipeline_flags(
            {
                "status": "study_pack_generated",
                "latest_final_audit_id": "FA-SRC-0001-V001",
                "latest_intermediate_audit_id": "IA-SRC-0001-V001",
                "extracted_text_path": "/x.md",
                "chunk_manifest_path": "/m.json",
                "local_digest_path": "/d.md",
            }
        )
        self.assertTrue(flags["final_audit"])
        self.assertTrue(flags["intermediate_audit"])
        self.assertTrue(flags["extracted"])


class TestMarkdownParsingRegression(unittest.TestCase):
    def test_nested_corrections_stay_under_parent(self) -> None:
        body = extract_markdown_section(NESTED_AUDIT, "Corrections That Matter Most")
        self.assertIn("### Correction 1", body)
        self.assertIn("### Correction 2", body)
        self.assertNotIn("Better Explanations", body)

    def test_nested_explanations_stay_under_parent(self) -> None:
        body = extract_markdown_section(NESTED_AUDIT, "Better Explanations")
        self.assertIn("### Real vs. Nominal", body)
        self.assertNotIn("Must-Memorize", body)

    def test_normalizer_keeps_nested_out_of_additional_notes(self) -> None:
        normalized, report = normalize_final_audit_text(NESTED_AUDIT)
        self.assertNotIn("Correction 1", report["unmatched_headings"])
        self.assertNotIn("## Additional Notes From Original Audit", normalized)

    def test_normalizer_and_study_pack_headings_match(self) -> None:
        self.assertEqual(
            set(EXPECTED_FINAL_AUDIT_HEADINGS),
            set(_SECTION_HEADINGS.values()),
        )

    def test_missing_heading_triggers_quality_warning(self) -> None:
        thin = "## Final Verdict\n\nOnly.\n"
        _, report = normalize_final_audit_text(thin)
        self.assertIn(report["quality_status"], {"needs_review", "failed"})
        self.assertGreater(len(report["missing_headings"]), 0)


class TestCliAndOverwriteRegression(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.course = _setup_course(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_diagnose_only_does_not_write_outputs(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        before = load_source_registry(self.course)
        report = diagnose_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        after = load_source_registry(self.course)
        self.assertEqual(before, after)
        self.assertIn("quality", report)

    def test_study_pack_overwrite_refusal(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(StudyPackOutputExistsError):
            generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)

    def test_normalizer_overwrite_refusal(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=MINIMAL_PIPELINE_AUDIT, root=self.root
        )
        normalize_latest_final_audit("ECA1010_Test", "SRC-0001", root=self.root)
        with self.assertRaises(NormalizedAuditExistsError):
            normalize_latest_final_audit("ECA1010_Test", "SRC-0001", root=self.root)

    def test_guided_workflow_does_not_run_google_intermediate_audit(self) -> None:
        self.assertNotIn("run_intermediate_audit", RUNNABLE_ACTION_KEYS)
        with patch(
            "studyforge.core.guided_workflow.build_intermediate_audit_packet"
        ) as mock_packet:
            with patch(
                "studyforge.core.guided_workflow.get_guided_next_action"
            ) as mock_guided:
                mock_guided.return_value = {
                    "key": "export_or_run_intermediate_audit",
                    "label": "Export",
                }
                run_guided_next_step(
                    "ECA1010_Test",
                    "SRC-0001",
                    action_key="export_or_run_intermediate_audit",
                    root=self.root,
                )
            mock_packet.assert_called_once()
        with patch(
            "studyforge.core.intermediate_audit_jobs.run_intermediate_audit_for_source"
        ) as mock_auto:
            self.assertFalse(mock_auto.called)


class TestPrivacyRegression(unittest.TestCase):
    def test_gitignore_protects_course_data_and_secrets(self) -> None:
        gitignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn("courses/*", gitignore)
        self.assertIn("!courses/_Course_Template/", gitignore)
        self.assertIn("config/local_secrets.json", gitignore)
        self.assertIn(".env", gitignore)


if __name__ == "__main__":
    unittest.main()

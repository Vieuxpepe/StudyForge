"""Tests for study pack quality analysis and diagnostics."""

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

from studyforge.audits.final_import import import_final_audit  # noqa: E402
from studyforge.core.sources import load_source_registry, save_source_registry  # noqa: E402
from studyforge.study.study_pack import (  # noqa: E402
    _MISSING_SECTION,
    analyze_study_pack_sections,
    diagnose_study_pack,
    extract_sections,
    generate_study_pack,
    get_final_audit_template_warning,
)

FULL_AUDIT = """# Final Audit

## Final Verdict

Accuracy is good and detailed enough for study purposes.

## Corrections That Matter Most

- Fix supply and demand confusion with clear examples

## Missing Concepts

- Opportunity cost edge cases need more practice

## Better Explanations

- Elasticity intuition using real world prices

## Must-Memorize List

- P equals MC in perfect competition long run equilibrium

## Must-Understand List

- Why deadweight loss happens when price is above marginal cost

## Formula / Method Sheet

- Elasticity equals percent change quantity over percent change price

## Exam / Homework Traps

- Mixing up shifts versus movements along a curve on graphs

## Practice Questions

1. Define price elasticity of demand with an example.
2. Explain consumer surplus in one paragraph.

## Active Recall Questions

- What is consumer surplus when price is below willingness to pay?
- How do you calculate CPI from a basket of goods?

## Final Study Checklist

- Review chapter two supply and demand graphs carefully

## Remaining Uncertainties

- Monopsony edge cases in labor markets need clarification
"""


class TestStudyPackQuality(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        (self.course / "04_Intermediate_Audits" / "SRC-0001").mkdir(parents=True)
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
                        "status": "intermediate_audit_imported",
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_all_sections_ok(self) -> None:
        sections = extract_sections(FULL_AUDIT)
        quality = analyze_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "ok")
        self.assertGreaterEqual(quality["total_extracted_words"], 100)
        self.assertGreaterEqual(len(quality["found_sections"]), 10)

    def test_many_missing_failed(self) -> None:
        sections = extract_sections("## Final Verdict\n\nShort.\n")
        quality = analyze_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "failed")
        self.assertGreaterEqual(len(quality["missing_sections"]), 6)

    def test_important_missing_needs_review(self) -> None:
        text = FULL_AUDIT.replace("## Active Recall Questions", "## ARQ Disabled")
        sections = extract_sections(text)
        quality = analyze_study_pack_sections(sections)
        self.assertEqual(quality["quality_status"], "needs_review")
        self.assertIn("active_recall", quality["missing_sections"])

    def test_placeholder_detected(self) -> None:
        sections = extract_sections(FULL_AUDIT)
        sections["must_memorize"] = "only five words here"
        quality = analyze_study_pack_sections(sections)
        self.assertIn("must_memorize", quality["placeholder_sections"])

    def test_manifest_includes_quality(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=FULL_AUDIT, root=self.root
        )
        summary = generate_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        manifest = json.loads(
            Path(summary["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertIn("quality", manifest)
        self.assertEqual(manifest["quality"]["quality_status"], "ok")
        self.assertEqual(summary["quality_status"], "ok")

    def test_diagnose_only_writes_nothing(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=FULL_AUDIT, root=self.root
        )
        before = load_source_registry(self.course)
        report = diagnose_study_pack("ECA1010_Test", "SRC-0001", root=self.root)
        after = load_source_registry(self.course)
        self.assertEqual(before, after)
        self.assertEqual(report["quality"]["quality_status"], "ok")
        outputs_dir = self.course / "06_Study_Outputs"
        self.assertFalse(outputs_dir.exists() or list(outputs_dir.glob("*")))

    def test_final_audit_template_warning(self) -> None:
        warning = get_final_audit_template_warning("## Final Verdict\n\nOnly this.\n")
        self.assertIsNotNone(warning)
        self.assertIn("template", warning.lower())

    def test_import_adds_template_warning(self) -> None:
        summary = import_final_audit(
            "ECA1010_Test",
            "SRC-0001",
            audit_text="## Final Verdict\n\nMinimal content only.\n",
            root=self.root,
        )
        self.assertTrue(
            any("template" in w.lower() for w in summary.get("warnings", []))
        )

    @patch("scripts.generate_study_pack.diagnose_study_pack")
    @patch("scripts.generate_study_pack.generate_study_pack")
    def test_cli_diagnose_only_flag(self, mock_generate, mock_diagnose) -> None:
        from scripts import generate_study_pack as cli_module

        mock_diagnose.return_value = {
            "source_id": "SRC-0001",
            "title": "Book",
            "based_on_final_audit_id": "FA-SRC-0001-V001",
            "final_audit_path": "/tmp/audit.md",
            "quality": {
                "quality_status": "ok",
                "found_sections": ["final_verdict"],
                "missing_sections": [],
                "placeholder_sections": [],
                "section_word_counts": {"final_verdict": 10},
                "total_extracted_words": 10,
                "warnings": [],
            },
            "warnings": [],
        }
        code = cli_module.main(
            ["--course", "ECA1010_Test", "--source-id", "SRC-0001", "--diagnose-only"]
        )
        self.assertEqual(code, 0)
        mock_generate.assert_not_called()
        mock_diagnose.assert_called_once()


if __name__ == "__main__":
    unittest.main()

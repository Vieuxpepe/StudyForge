"""Tests for final audit import."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.final_import import (  # noqa: E402
    AuditInputError,
    EmptyAuditError,
    FinalAuditNotReadyError,
    build_final_audit_file_name,
    get_next_final_audit_version,
    import_final_audit,
    load_final_audit_registry,
)

AUDIT_BODY = "# Final Audit\n\n## Final Verdict\n\nAccuracy: good\n"


class TestFinalImport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        courses = self.root / "courses"
        self.course = courses / "ECA1010_Test"
        (self.course / "04_Intermediate_Audits" / "SRC-0001").mkdir(parents=True)
        (self.course / "08_App_Data").mkdir(parents=True)

        from studyforge.core.sources import save_source_registry

        save_source_registry(
            self.course,
            {
                "sources": [
                    {
                        "id": "SRC-0001",
                        "title": "Test Book",
                        "status": "intermediate_audit_imported",
                    }
                ]
            },
        )

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

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_import_from_text(self) -> None:
        summary = import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        self.assertEqual(summary["audit_id"], "FA-SRC-0001-V001")
        registry = load_final_audit_registry(
            Path(summary["registry_path"]), "SRC-0001"
        )
        self.assertEqual(len(registry["audits"]), 1)

    def test_import_from_file(self) -> None:
        f = self.root / "external.md"
        f.write_text(AUDIT_BODY, encoding="utf-8")
        summary = import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_file=f, root=self.root
        )
        self.assertEqual(Path(summary["saved_path"]).read_text(encoding="utf-8"), AUDIT_BODY)

    def test_reject_both_and_neither(self) -> None:
        with self.assertRaises(AuditInputError):
            import_final_audit(
                "ECA1010_Test",
                "SRC-0001",
                audit_text="x",
                audit_file=Path("y.md"),
                root=self.root,
            )
        with self.assertRaises(AuditInputError):
            import_final_audit("ECA1010_Test", "SRC-0001", root=self.root)

    def test_empty_audit_rejected(self) -> None:
        with self.assertRaises(EmptyAuditError):
            import_final_audit(
                "ECA1010_Test", "SRC-0001", audit_text="  ", root=self.root
            )

    def test_version_increments_and_no_overwrite(self) -> None:
        s1 = import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text="version one", root=self.root
        )
        s2 = import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text="version two", root=self.root
        )
        self.assertEqual(s2["audit_id"], "FA-SRC-0001-V002")
        self.assertEqual(
            Path(s1["saved_path"]).read_text(encoding="utf-8"), "version one"
        )

    def test_source_registry_updated(self) -> None:
        import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        from studyforge.core.sources import load_source_registry

        reg = load_source_registry(self.course)
        self.assertEqual(reg["sources"][0]["status"], "final_audit_imported")
        self.assertEqual(reg["sources"][0]["latest_final_audit_id"], "FA-SRC-0001-V001")

    def test_not_ready_without_intermediate(self) -> None:
        bad = self.root / "courses" / "BAD"
        bad.mkdir(parents=True)
        from studyforge.core.sources import save_source_registry

        save_source_registry(
            bad, {"sources": [{"id": "SRC-0001", "status": "chunked"}]}
        )
        with self.assertRaises(FinalAuditNotReadyError):
            import_final_audit("BAD", "SRC-0001", audit_text=AUDIT_BODY, root=self.root)

    def test_disk_scan_version_recovery(self) -> None:
        audit_dir = self.course / "05_Final_Audits" / "SRC-0001"
        audit_dir.mkdir(parents=True)
        (audit_dir / build_final_audit_file_name("SRC-0001", 1)).write_text(
            "old", encoding="utf-8"
        )
        summary = import_final_audit(
            "ECA1010_Test", "SRC-0001", audit_text=AUDIT_BODY, root=self.root
        )
        self.assertEqual(summary["version"], 2)
        self.assertTrue(summary["warnings"])


if __name__ == "__main__":
    unittest.main()

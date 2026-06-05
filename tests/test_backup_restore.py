"""Tests for backup verification and safe restore v1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.backup import BACKUP_INFO_FILENAME  # noqa: E402
from studyforge.core.backup_restore import (  # noqa: E402
    InvalidBackupError,
    RestoreTargetExistsError,
    UnsafeZipPathError,
    inspect_backup_zip,
    preview_restore_backup,
    restore_backup_to_new_course,
    verify_backup,
)
from studyforge.core.sources import save_source_registry  # noqa: E402


def _write_config(root: Path, courses: Path) -> None:
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


def _create_valid_backup_zip(
    path: Path,
    course_name: str = "ECA1010_Test",
    *,
    include_info: bool = True,
    include_app_data: bool = True,
    full_structure: bool = True,
) -> None:
    dirs = [
        "00_Master",
        "01_Source_Material/textbook",
        "02_Extracted_Text",
        "03_Local_Digests",
        "04_Intermediate_Audits",
        "05_Final_Audits",
        "06_Study_Outputs/study_guides",
        "07_My_Work",
    ]
    if include_app_data:
        dirs.append("08_App_Data")

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if include_info:
            archive.writestr(
                f"{course_name}/{BACKUP_INFO_FILENAME}",
                f"Course: {course_name}\n",
            )
        if full_structure:
            for folder in dirs:
                archive.writestr(f"{course_name}/{folder}/.keep", "x")
        archive.writestr(f"{course_name}/00_Master/notes.txt", "notes")
        if include_app_data:
            archive.writestr(
                f"{course_name}/08_App_Data/source_registry.json",
                '{"sources": []}',
            )
        archive.writestr(
            f"{course_name}/01_Source_Material/textbook/book.pdf",
            b"pdf",
        )
        archive.writestr(
            f"{course_name}/06_Study_Outputs/study_guides/guide.md",
            "# Guide",
        )


class TestInspectBackupZip(unittest.TestCase):
    def test_inspect_valid_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.zip"
            _create_valid_backup_zip(backup)
            report = inspect_backup_zip(backup)

        self.assertTrue(report["valid_zip"])
        self.assertEqual(report["course_folder"], "ECA1010_Test")
        self.assertGreater(report["file_count"], 0)
        self.assertGreater(report["total_bytes"], 0)
        self.assertTrue(report["contains_sources"])
        self.assertTrue(report["contains_study_outputs"])
        self.assertTrue(report["contains_app_data"])
        self.assertTrue(report["has_backup_info"])
        self.assertEqual(report["missing_expected_paths"], [])

    def test_detect_missing_backup_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.zip"
            _create_valid_backup_zip(backup, include_info=False)
            report = verify_backup(backup)

        self.assertFalse(report["has_backup_info"])
        self.assertIn(BACKUP_INFO_FILENAME, report["missing_expected_paths"])
        self.assertEqual(report["status"], "needs_review")

    def test_invalid_zip_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not_a_zip.zip"
            bad.write_text("hello", encoding="utf-8")
            report = verify_backup(bad)

        self.assertFalse(report["valid_zip"])
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["errors"])


class TestPreviewRestore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.courses = self.root / "courses"
        self.courses.mkdir()
        _write_config(self.root, self.courses)
        self.backup = self.root / "backup.zip"
        _create_valid_backup_zip(self.backup)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_preview_safe_when_target_missing(self) -> None:
        preview = preview_restore_backup(
            self.backup,
            courses_dir=self.courses,
            root=self.root,
        )
        self.assertFalse(preview["target_exists"])
        self.assertTrue(preview["safe_to_restore"])
        self.assertIn("ECA1010_Test", preview["target_path"])

    def test_preview_unsafe_when_target_exists(self) -> None:
        (self.courses / "ECA1010_Test").mkdir()
        preview = preview_restore_backup(
            self.backup,
            courses_dir=self.courses,
            root=self.root,
        )
        self.assertTrue(preview["target_exists"])
        self.assertFalse(preview["safe_to_restore"])


class TestRestoreBackup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.courses = self.root / "courses"
        self.courses.mkdir()
        _write_config(self.root, self.courses)
        self.backup = self.root / "backup.zip"
        _create_valid_backup_zip(self.backup)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_restore_refuses_existing_target(self) -> None:
        (self.courses / "ECA1010_Test").mkdir()
        with self.assertRaises(RestoreTargetExistsError):
            restore_backup_to_new_course(self.backup, root=self.root)

    def test_restore_extracts_to_new_folder(self) -> None:
        summary = restore_backup_to_new_course(self.backup, root=self.root)
        target = Path(summary["target_path"])
        self.assertTrue(target.is_dir())
        self.assertTrue((target / "08_App_Data" / "source_registry.json").is_file())
        self.assertTrue((target / "00_Master" / "notes.txt").is_file())
        self.assertGreater(summary["files_restored"], 0)

    def test_restore_as_renames_course_root(self) -> None:
        summary = restore_backup_to_new_course(
            self.backup,
            target_course_name="ECA1010_Restored_Test",
            root=self.root,
        )
        target = Path(summary["target_path"])
        self.assertEqual(summary["course_folder"], "ECA1010_Restored_Test")
        self.assertEqual(summary["source_course_folder"], "ECA1010_Test")
        self.assertTrue((target / "07_My_Work").is_dir())
        self.assertFalse((self.courses / "ECA1010_Test").exists())

    def test_zip_slip_path_traversal_rejected(self) -> None:
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("ECA1010_Test/08_App_Data/registry.json", "{}")
            archive.writestr("ECA1010_Test/../../outside.txt", "bad")

        with self.assertRaises(UnsafeZipPathError):
            restore_backup_to_new_course(
                evil,
                target_course_name="ECA1010_Safe",
                root=self.root,
            )

    def test_restore_fails_without_app_data(self) -> None:
        bad = self.root / "bad.zip"
        _create_valid_backup_zip(bad, include_app_data=False, full_structure=False)
        with self.assertRaises(InvalidBackupError):
            restore_backup_to_new_course(
                bad,
                target_course_name="ECA1010_NoApp",
                root=self.root,
            )


class TestVerifyBackupCli(unittest.TestCase):
    def test_cli_verify_output(self) -> None:
        from scripts import verify_backup as cli_module

        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.zip"
            _create_valid_backup_zip(backup)
            buffer = StringIO()
            with patch("sys.stdout", buffer):
                code = cli_module.main(["--file", str(backup)])
            self.assertEqual(code, 0)
            output = buffer.getvalue()
            self.assertIn("Status: ok", output)
            self.assertIn("ECA1010_Test", output)

    def test_cli_preview_restore(self) -> None:
        from scripts import verify_backup as cli_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            courses = root / "courses"
            courses.mkdir()
            _write_config(root, courses)
            backup = root / "backup.zip"
            _create_valid_backup_zip(backup)

            buffer = StringIO()
            with patch("sys.stdout", buffer):
                with patch(
                    "studyforge.core.backup_restore.find_project_root",
                    return_value=root,
                ):
                    code = cli_module.main(
                        ["--file", str(backup), "--preview-restore"]
                    )
            self.assertEqual(code, 0)
            output = buffer.getvalue()
            self.assertIn("Safe to restore:", output)


if __name__ == "__main__":
    unittest.main()

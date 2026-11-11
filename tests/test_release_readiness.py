import ast
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import app_version
import database
import update_service
import utils


REPO_ROOT = Path(__file__).resolve().parent.parent


class ReleaseReadinessTests(unittest.TestCase):
    def test_app_version_format_and_normalization(self):
        normalized = app_version.normalize_version(app_version.APP_VERSION)
        self.assertEqual(normalized, app_version.APP_VERSION)
        self.assertEqual(app_version.normalize_version("v2.1.0"), "2.1.0")
        with self.assertRaises(ValueError):
            app_version.normalize_version("2.0-beta")

    def test_update_service_configuration(self):
        self.assertEqual(
            update_service.REPOSITORY,
            "krishnashashanth-sks/campus-library",
        )
        self.assertEqual(update_service.PACKAGE_NAME, "Library-Windows.zip")
        self.assertTrue(update_service.is_newer_version("2.1", "2.0"))
        self.assertTrue(update_service.is_newer_version("v2.0.1", "2.0"))
        self.assertFalse(update_service.is_newer_version("2.0", "2.0"))
        self.assertFalse(update_service.is_newer_version("1.9", "2.0"))

    def test_safe_extract_package_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            valid_zip = tmp_path / "valid.zip"
            with zipfile.ZipFile(valid_zip, "w") as archive:
                archive.writestr("Library.exe", b"MZ")
                archive.writestr("_internal/marker.txt", b"ok")

            valid_dest = tmp_path / "valid_out"
            valid_dest.mkdir()
            update_service._safe_extract_package(valid_zip, valid_dest)
            self.assertTrue((valid_dest / "Library.exe").is_file())

            missing_exe_zip = tmp_path / "nested.zip"
            with zipfile.ZipFile(missing_exe_zip, "w") as archive:
                archive.writestr("main/Library.exe", b"MZ")

            missing_dest = tmp_path / "missing_out"
            missing_dest.mkdir()
            with self.assertRaises(RuntimeError):
                update_service._safe_extract_package(missing_exe_zip, missing_dest)

            traversal_zip = tmp_path / "traversal.zip"
            with zipfile.ZipFile(traversal_zip, "w") as archive:
                archive.writestr("../escape.txt", b"bad")

            traversal_dest = tmp_path / "traversal_out"
            traversal_dest.mkdir()
            with self.assertRaises(RuntimeError):
                update_service._safe_extract_package(traversal_zip, traversal_dest)

    def test_core_validators(self):
        self.assertTrue(utils.is_valid_book_id("12345"))
        self.assertFalse(utils.is_valid_book_id("1234"))
        self.assertTrue(utils.is_valid_user_id("24001-CS-097", "Student"))
        self.assertTrue(utils.is_valid_user_id("123456", "Faculty"))
        self.assertEqual(utils.normalize_user_role("student"), "Student")
        self.assertEqual(
            utils.normalize_department_for_role(
                "Sciences and Humanities Department",
                "Faculty",
            ),
            "Sciences & Humanities Department",
        )
        self.assertIsNone(
            utils.normalize_department_for_role(
                "General Administration",
                "Student",
            )
        )

    def test_database_initializes_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_library.db")
            db = database.LocalDatabase(db_path)
            try:
                tables = {
                    row[0]
                    for row in db.conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for expected in ("books", "users", "circulation_logs", "settings"):
                    self.assertIn(expected, tables)
            finally:
                db.close()

    def test_production_login_is_enabled(self):
        source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        bypass_value = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "BYPASS_LOGIN":
                        bypass_value = ast.literal_eval(node.value)
        self.assertIs(
            bypass_value,
            False,
            "BYPASS_LOGIN in main.py must be False before building releases.",
        )

    def test_packaging_files_exist(self):
        required = (
            "assets/library_icon.ico",
            "assets/library_icon.png",
            "main.spec",
            "installer_scipt.iss",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements-services.txt",
            "scripts/build_windows.ps1",
        )
        for rel_path in required:
            self.assertTrue(
                (REPO_ROOT / rel_path).is_file(),
                f"Missing required packaging file: {rel_path}",
            )


if __name__ == "__main__":
    unittest.main()

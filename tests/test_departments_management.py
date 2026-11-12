import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

import database
from dialogs import DepartmentManagerDialog, EditDepartmentDialog, UserDialog
from mainwindow import MainWindow
from pages.settings_view import SettingsView
from theme_manager import ThemeManager


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_departments_management"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=3):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


class DepartmentDatabaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "dept_test.db")
        self.db = database.LocalDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_custom_departments_persist_across_reopen(self):
        ok, _ = self.db.add_department(
            "Artificial Intelligence & ML",
            "STUDENT",
            4,
            branch_code="AI",
        )
        self.assertTrue(ok)

        ok, _ = self.db.delete_department("Automobile Engineering")
        self.assertTrue(ok)

        self.db.close()
        self.db = database.LocalDatabase(self.db_path)

        student_branches = self.db.get_departments("STUDENT")
        self.assertIn("Artificial Intelligence & ML", student_branches)
        self.assertNotIn("Automobile Engineering", student_branches)
        self.assertEqual(self.db.get_course_duration("Artificial Intelligence & ML"), 4)

    def test_add_update_validation_and_code_uniqueness(self):
        ok, msg = self.db.add_department("   ", "STUDENT", 3)
        self.assertFalse(ok)
        self.assertIn("name", msg.lower())

        ok, msg = self.db.add_department("Data Science", "STUDENT", 4, branch_code="CS")
        self.assertFalse(ok)
        self.assertIn("short code", msg.lower())

        ok, msg = self.db.add_department("Data Science", "STUDENT", 4, branch_code="INVALID CODE!")
        self.assertFalse(ok)

        ok, msg = self.db.add_department("Data Science", "STUDENT", 7, branch_code="DS")
        self.assertFalse(ok)

        ok, msg = self.db.add_department("Data Science", "STUDENT", 4, branch_code=" ds ")
        self.assertTrue(ok, msg)

        ok, msg = self.db.add_department("data science", "STUDENT", 3, branch_code="DS2")
        self.assertFalse(ok)
        self.assertIn("already exists", msg.lower())

    def test_rename_cascades_to_users_and_dynamic_normalization(self):
        ok, msg = self.db.add_department("Cloud Computing", "STUDENT", 4, branch_code="CC")
        self.assertTrue(ok, msg)

        self.assertEqual(
            self.db.normalize_department_for_role("CC", "Student"),
            "Cloud Computing",
        )
        self.assertEqual(
            self.db.normalize_department_for_role("cc", "Faculty"),
            "Cloud Computing",
        )

        ok, msg = self.db.insert_user(
            "24001-CC-001",
            "Meera Nair",
            "9876543210",
            "Student",
            "Cloud Computing",
            "meera@example.edu",
        )
        self.assertTrue(ok, msg)

        rows = self.db.get_departments_detailed()
        cloud_row = next(r for r in rows if r["name"] == "Cloud Computing")
        self.assertEqual(cloud_row["user_count"], 1)
        self.assertEqual(cloud_row["student_count"], 1)

        # Restricting to FACULTY must fail while a student is assigned.
        ok, msg = self.db.update_department(
            cloud_row["id"],
            "Cloud Computing",
            "FACULTY",
            3,
            branch_code="CC",
        )
        self.assertFalse(ok)
        self.assertIn("student", msg.lower())

        # Renaming + changing duration updates users atomically.
        ok, msg = self.db.update_department(
            cloud_row["id"],
            "Cloud & DevOps Engineering",
            "STUDENT",
            5,
            branch_code="CDE",
        )
        self.assertTrue(ok, msg)
        self.assertIn("1 member record", msg)

        ok_u, user_row = self.db.get_user_details("24001-CC-001")
        self.assertTrue(ok_u)
        self.assertEqual(user_row[4], "Cloud & DevOps Engineering")
        self.assertEqual(self.db.get_course_duration("Cloud & DevOps Engineering"), 5)

    def test_reassign_delete_guards_and_restore_defaults(self):
        ok, _ = self.db.insert_user(
            "24001-CS-011",
            "Rohan Verma",
            "9123456789",
            "Student",
            "CSE (Computer Science & Engineering)",
        )
        self.assertTrue(ok)

        # Cannot delete without reassign target while members exist.
        ok, msg = self.db.delete_department("CSE (Computer Science & Engineering)")
        self.assertFalse(ok)
        self.assertIn("reassign", msg.lower())

        # Cannot move student into FACULTY-only department.
        ok, msg = self.db.delete_department(
            "CSE (Computer Science & Engineering)",
            reassign_to="General Administration",
        )
        self.assertFalse(ok)
        self.assertIn("student academic branch", msg.lower())

        # Valid reassignment + atomic delete.
        ok, msg = self.db.delete_department(
            "CSE (Computer Science & Engineering)",
            reassign_to="ECE (Electronics & Communication)",
        )
        self.assertTrue(ok, msg)
        _, user_row = self.db.get_user_details("24001-CS-011")
        self.assertEqual(user_row[4], "ECE (Electronics & Communication)")
        self.assertNotIn(
            "CSE (Computer Science & Engineering)",
            self.db.get_departments("STUDENT"),
        )

        # Add a custom branch, then restore defaults non-destructively.
        self.assertTrue(self.db.add_department("Robotics", "STUDENT", 4, branch_code="ROB")[0])
        ok, msg = self.db.restore_default_departments()
        self.assertTrue(ok, msg)
        branches = self.db.get_departments("STUDENT")
        self.assertIn("CSE (Computer Science & Engineering)", branches)
        self.assertIn("Robotics", branches)

        # Guard: cannot delete last remaining student branch.
        for b_name in self.db.get_departments("STUDENT")[1:]:
            if b_name != "ECE (Electronics & Communication)":
                self.db.delete_department(b_name)
        self.db.delete_department(
            "ECE (Electronics & Communication)",
            reassign_to=self.db.get_departments("STUDENT")[0],
        )
        remaining = self.db.get_departments("STUDENT")
        self.assertEqual(len(remaining), 1)
        ok, msg = self.db.delete_department(remaining[0])
        self.assertFalse(ok)
        self.assertIn("at least one student", msg.lower())


class DepartmentUiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = database.LocalDatabase(os.path.join(cls.tmp.name, "dept_ui.db"))
        cls.db.insert_user(
            "24001-CS-002",
            "Ananya Rao",
            "9888877777",
            "Student",
            "CSE (Computer Science & Engineering)",
            "ananya@example.edu",
        )

    @classmethod
    def tearDownClass(cls):
        _pump(2)
        cls.db.close()
        cls.tmp.cleanup()

    def test_settings_inline_and_mainwindow_sync(self):
        win = MainWindow(self.db)
        win.resize(1280, 820)
        win.show()
        _pump(4)
        try:
            win.switch_page(5)
            sv = win.settings_view
            sv.settings_tabs.setCurrentIndex(1)
            _pump(3)

            initial_count = sv.dept_table.rowCount()
            self.assertGreaterEqual(initial_count, 12)
            self.assertFalse(sv.btn_edit_dept.isEnabled())
            self.assertFalse(sv.btn_delete_dept.isEnabled())

            # Inline Add via EditDepartmentDialog
            class FakeAddDlg:
                def __init__(self, *_args, **_kwargs):
                    pass

                def exec(self):
                    return QDialog.DialogCode.Accepted

                def get_full_data(self):
                    return ("Robotics & Automation", "STUDENT", 4, "ROB")

            with (
                mock.patch("pages.settings_view.EditDepartmentDialog", FakeAddDlg),
                mock.patch.object(QMessageBox, "information"),
            ):
                sv.add_department_from_settings()
                _pump(3)

            # Verify SettingsView table + MainWindow -> UserManagementView live sync
            self.assertEqual(sv.dept_table.rowCount(), initial_count + 1)
            dept_names_in_combo = [
                win.usermanagement_view.branch_combo.itemData(i)
                for i in range(win.usermanagement_view.branch_combo.count())
            ]
            self.assertIn("Robotics & Automation", dept_names_in_combo)
            self.assertEqual(
                win.usermanagement_view._get_cached_course_duration("Robotics & Automation"),
                4,
            )

            # UserDialog dropdown immediately reflects the new branch
            udlg = UserDialog(self.db)
            udlg.on_role_changed("Student")
            user_dialog_branches = [
                udlg.combo_department.itemText(i)
                for i in range(udlg.combo_department.count())
            ]
            self.assertIn("Robotics & Automation", user_dialog_branches)
            udlg.deleteLater()

            # CSV batch import accepts new branch by name and short code
            csv_path = os.path.join(self.tmp.name, "import_robots.csv")
            Path(csv_path).write_text(
                "ID,Full Name,Phone,Role,Department,Email\n"
                "25001-RO-001,Vikram Das,9777766666,Student,ROB,vikram@example.edu\n",
                encoding="utf-8",
            )
            with (
                mock.patch("pages.usermanagement_view.QFileDialog.getOpenFileName", return_value=(csv_path, "")),
                mock.patch.object(QMessageBox, "information"),
            ):
                win.usermanagement_view.import_users_from_file()
            _, imported_user = self.db.get_user_details("25001-RO-001")
            self.assertIsNotNone(imported_user)
            self.assertEqual(imported_user[4], "Robotics & Automation")

            # Filter and select the newly added row in SettingsView table
            sv.dept_search_input.setText("Robotics")
            _pump(2)
            self.assertEqual(sv.dept_table.rowCount(), 1)
            sv.dept_table.selectRow(0)
            _pump(2)
            self.assertTrue(sv.btn_edit_dept.isEnabled())
            self.assertTrue(sv.btn_delete_dept.isEnabled())

            # Inline Update via EditDepartmentDialog
            class FakeEditDlg:
                def __init__(self, *_args, **_kwargs):
                    pass

                def exec(self):
                    return QDialog.DialogCode.Accepted

                def get_full_data(self):
                    return ("Autonomous Robotics", "STUDENT", 5, "AROB")

            with (
                mock.patch("pages.settings_view.EditDepartmentDialog", FakeEditDlg),
                mock.patch.object(QMessageBox, "information"),
            ):
                sv.edit_selected_department()
                _pump(3)

            _, updated_user = self.db.get_user_details("25001-RO-001")
            self.assertEqual(updated_user[4], "Autonomous Robotics")
            sv.dept_search_input.clear()
            _pump(2)

            # Select Autonomous Robotics and Delete with Reassignment via ReassignDepartmentDialog
            for r in range(sv.dept_table.rowCount()):
                if sv.dept_table.item(r, 1).text() == "Autonomous Robotics":
                    sv.dept_table.selectRow(r)
                    break
            _pump(2)

            class FakeReassignDlg:
                def __init__(self, *_args, **_kwargs):
                    pass

                def exec(self):
                    return QDialog.DialogCode.Accepted

                def selected_target(self):
                    return "CSE (Computer Science & Engineering)"

            with (
                mock.patch("pages.settings_view.ReassignDepartmentDialog", FakeReassignDlg),
                mock.patch.object(QMessageBox, "information"),
            ):
                sv.delete_selected_department()
                _pump(3)

            _, moved_user = self.db.get_user_details("25001-RO-001")
            self.assertEqual(moved_user[4], "CSE (Computer Science & Engineering)")
            self.assertNotIn("Autonomous Robotics", self.db.get_departments("STUDENT"))

            # DepartmentManagerDialog search + filter smoke check
            mgr = DepartmentManagerDialog(self.db)
            mgr.search_input.setText("AMT")
            _pump(2)
            self.assertEqual(mgr.table.rowCount(), 1)
            self.assertEqual(
                mgr.table.item(0, 1).text(),
                "Advanced Manufacturing Technology (AMT)",
            )
            mgr.search_input.setText("CS")
            _pump(2)
            self.assertIn(
                "CSE (Computer Science & Engineering)",
                [mgr.table.item(i, 1).text() for i in range(mgr.table.rowCount())],
            )
            mgr.deleteLater()
        finally:
            win.close()
            win.deleteLater()
            _pump(3)


if __name__ == "__main__":
    unittest.main()


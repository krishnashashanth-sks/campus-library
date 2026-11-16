import gc
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

import database
from dialogs import IssueBookDialog
from pages.settings_view import SettingsView
from theme_manager import ThemeManager


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_student_loan_limit"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=3):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


class TestStudentLoanLimit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_student_limit.db")
        self.db = database.LocalDatabase(self.db_path)

        # Seed student user and faculty user
        self.student_id = "STU1001"
        self.db.insert_user(
            self.student_id,
            "Alex Smith",
            "9876543210",
            "Student",
            "Computer Science",
            "alex@example.com",
        )

        self.faculty_id = "FAC2001"
        self.db.insert_user(
            self.faculty_id,
            "Dr. Alan Turing",
            "9876543211",
            "Faculty",
            "Computer Science",
            "alan@example.com",
        )

        # Seed 5 books with plenty of copies (total=10, available=10)
        for i in range(1, 6):
            self.db.insert_book(
                f"BK00{i}",
                f"Textbook Volume {i}",
                f"Author {i}",
                "Academic Press",
                10,
                10,
            )

    def tearDown(self):
        try:
            if hasattr(self.db, "conn") and self.db.conn:
                self.db.conn.close()
        except Exception:
            pass
        self.db = None
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_default_student_limit_is_3_books(self):
        """Test default student limit is 3 books across database helpers and loan policy."""
        self.assertEqual(self.db.get_student_max_books(), 3)
        policy = self.db.get_loan_policy("Student")
        self.assertEqual(policy["max_books"], 3)
        self.assertEqual(self.db.get_setting("student_max_books"), "3")

    def test_student_can_take_up_to_3_books_and_4th_is_blocked(self):
        """Verify a student can borrow 3 books, and 4th loan is denied."""
        # 1st book
        ok1, msg1 = self.db.issue_book("BK001", self.student_id)
        self.assertTrue(ok1, f"1st book failed: {msg1}")

        # 2nd book
        ok2, msg2 = self.db.issue_book("BK002", self.student_id)
        self.assertTrue(ok2, f"2nd book failed: {msg2}")

        # 3rd book
        ok3, msg3 = self.db.issue_book("BK003", self.student_id)
        self.assertTrue(ok3, f"3rd book failed: {msg3}")

        # Check borrowing status
        status = self.db.get_user_borrowing_status(self.student_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["active_count"], 3)
        self.assertEqual(status["max_books"], 3)
        self.assertEqual(status["remaining_slots"], 0)
        self.assertFalse(status["can_borrow"])
        self.assertEqual(len(status["active_books"]), 3)

        # Attempt 4th book
        ok4, msg4 = self.db.issue_book("BK004", self.student_id)
        self.assertFalse(ok4)
        self.assertIn("limit of 3", msg4.lower())
        self.assertIn("borrowed", msg4.lower())

    def test_returning_book_frees_student_slot(self):
        """Verify returning a book frees up quota to allow another book to be issued."""
        self.db.issue_book("BK001", self.student_id)
        self.db.issue_book("BK002", self.student_id)
        self.db.issue_book("BK003", self.student_id)

        # 4th is blocked
        ok4, _ = self.db.issue_book("BK004", self.student_id)
        self.assertFalse(ok4)

        # Return 1st book
        ret_ok, ret_fine, ret_msg = self.db.return_book("BK001", self.student_id)
        self.assertTrue(ret_ok, f"Return failed: {ret_msg}")

        # Quota should now allow 1 more book
        status = self.db.get_user_borrowing_status(self.student_id)
        self.assertEqual(status["active_count"], 2)
        self.assertTrue(status["can_borrow"])

        # Issuing 4th book should now succeed
        ok4, msg4 = self.db.issue_book("BK004", self.student_id)
        self.assertTrue(ok4, f"Failed to issue 4th book after return: {msg4}")

    def test_change_student_limit_dynamically(self):
        """Verify increasing student limit in settings allows more books to be borrowed."""
        self.db.issue_book("BK001", self.student_id)
        self.db.issue_book("BK002", self.student_id)
        self.db.issue_book("BK003", self.student_id)

        # 4th is currently blocked under limit 3
        ok, _ = self.db.issue_book("BK004", self.student_id)
        self.assertFalse(ok)

        # Admin changes limit to 5
        set_ok, set_msg = self.db.set_student_max_books(5)
        self.assertTrue(set_ok, f"set_student_max_books failed: {set_msg}")
        self.assertEqual(self.db.get_student_max_books(), 5)
        self.assertEqual(self.db.get_loan_policy("Student")["max_books"], 5)

        # Now 4th and 5th books can be issued
        ok4, msg4 = self.db.issue_book("BK004", self.student_id)
        self.assertTrue(ok4, f"4th book failed under new limit 5: {msg4}")

        ok5, msg5 = self.db.issue_book("BK005", self.student_id)
        self.assertTrue(ok5, f"5th book failed under new limit 5: {msg5}")

        # Status has 5 active loans
        status = self.db.get_user_borrowing_status(self.student_id)
        self.assertEqual(status["active_count"], 5)
        self.assertFalse(status["can_borrow"])

    def test_settings_view_student_books_control_and_sync(self):
        """Test SettingsView student max books spinbox and two-way sync with role policies."""
        _ensure_app()
        settings_view = SettingsView(self.db)
        _pump(3)

        self.assertTrue(hasattr(settings_view, "spin_student_max_books"))
        # Initial value should be 3
        self.assertEqual(settings_view.spin_student_max_books.value(), 3)

        # Check synchronization: changing spin_student_max_books updates student role row
        settings_view.spin_student_max_books.setValue(4)
        student_role_spin = settings_view.role_policy_controls["Student"]["max_books"]
        self.assertEqual(student_role_spin.value(), 4)

        # Changing student role spinbox updates spin_student_max_books
        student_role_spin.setValue(6)
        self.assertEqual(settings_view.spin_student_max_books.value(), 6)

        # Save settings and verify persistence
        with mock.patch("pages.settings_view.QMessageBox.information"):
            settings_view.save_settings()
        self.assertEqual(self.db.get_student_max_books(), 6)
        self.assertEqual(self.db.get_loan_policy("Student")["max_books"], 6)

        # Test reset defaults restores 3
        with mock.patch("pages.settings_view.QMessageBox.question", return_value=mock.MagicMock()) as mock_q:
            mock_q.return_value = 16384  # QMessageBox.StandardButton.Yes
            with mock.patch("pages.settings_view.QMessageBox.information"):
                settings_view.reset_defaults()
        self.assertEqual(settings_view.spin_student_max_books.value(), 3)
        self.assertEqual(student_role_spin.value(), 3)

        settings_view.close()

    def test_issue_book_dialog_live_quota_and_prevalidation(self):
        """Test IssueBookDialog live quota feedback and blocking when student reaches limit."""
        _ensure_app()
        # Student borrows 3 books
        self.db.issue_book("BK001", self.student_id)
        self.db.issue_book("BK002", self.student_id)
        self.db.issue_book("BK003", self.student_id)

        dialog = IssueBookDialog(self.db)
        _pump(2)

        # Set user input to student ID
        dialog.input_user.setText(self.student_id)
        _pump(2)

        # Verify hint text shows limit reached
        hint = dialog.lbl_policy_hint.text()
        self.assertIn("Borrowing Limit Reached", hint)
        self.assertIn("3 of 3", hint)
        # Issue button should be disabled
        self.assertFalse(dialog.btn_issue.isEnabled())

        # Set book input to BK004
        dialog.input_book.setText("BK004")
        _pump(2)

        # Attempt to validate and accept should not accept
        with mock.patch("dialogs.show_warning") as mock_warn:
            dialog.validate_and_accept()
            self.assertTrue(mock_warn.called)
        self.assertEqual(dialog.result(), 0)  # QDialog.Rejected / not Accepted

        dialog.close()


if __name__ == "__main__":
    unittest.main()

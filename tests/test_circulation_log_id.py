import datetime
import os
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

import database
import utils
from dialogs import BookHistoryDialog, PendingFinesDialog, RenewLoanDialog
from mainwindow import MainWindow
from pages.dashboard_view import ActivityHistoryDialog
from theme_manager import ThemeManager


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_circulation_log_id"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=3):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


def _seed_sample_entities(db):
    ok, msg = db.insert_book(
        "10001", "Clean Architecture", "Robert Martin", "Pearson", 4, 4
    )
    assert ok, msg
    ok, msg = db.insert_book(
        "10002", "Designing Data-Intensive Applications", "Martin Kleppmann", "O'Reilly", 3, 3
    )
    assert ok, msg
    ok, msg = db.insert_user(
        "24001-CS-001",
        "Aarav Sharma",
        "9876543210",
        "Student",
        "Computer Science & Engineering",
        "aarav@example.com",
    )
    assert ok, msg
    ok, msg = db.insert_user(
        "100201",
        "Dr. Diya Nair",
        "9876543211",
        "Faculty",
        "Electronics & Communication Engineering",
        "diya@example.com",
    )
    assert ok, msg


class CirculationLogIdUnitTests(unittest.TestCase):
    def test_utils_log_id_helpers(self):
        self.assertTrue(utils.is_structured_log_id("CIR-261112-0001"))
        self.assertTrue(utils.is_structured_log_id("cir-261112-0001"))
        self.assertTrue(utils.is_structured_log_id("  CIR-261112-10005 "))
        self.assertFalse(utils.is_structured_log_id("12"))
        self.assertFalse(utils.is_structured_log_id(""))
        self.assertFalse(utils.is_structured_log_id(12))

        self.assertEqual(utils.format_log_id_display("CIR-261112-0001"), "CIR-261112-0001")
        self.assertEqual(utils.format_log_id_display("#CIR-261112-0001"), "CIR-261112-0001")
        self.assertEqual(utils.format_log_id_display(12), "#12")
        self.assertEqual(utils.format_log_id_display("12"), "#12")
        self.assertEqual(utils.format_log_id_display("#12"), "#12")
        self.assertEqual(utils.format_log_id_display(""), "—")
        self.assertEqual(utils.format_log_id_display(None), "—")

    def test_issue_generates_structured_codes_and_natural_overflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = database.LocalDatabase(os.path.join(tmp, "library.db"))
            try:
                _seed_sample_entities(db)
                today_key = datetime.datetime.now().strftime("%y%m%d")

                ok, msg1 = db.issue_book("10001", "24001-CS-001", 14)
                self.assertTrue(ok, msg1)
                expected_1 = f"CIR-{today_key}-0001"
                self.assertIn(expected_1, msg1)

                ok, msg2 = db.issue_book("10002", "100201", 14)
                self.assertTrue(ok, msg2)
                expected_2 = f"CIR-{today_key}-0002"
                self.assertIn(expected_2, msg2)

                self.assertEqual(db.get_active_loan_id("10001", "24001-CS-001"), expected_1)
                self.assertEqual(db.get_active_loan_id("10002", "100201"), expected_2)

                ok_logs, logs = db.get_logs()
                self.assertTrue(ok_logs)
                self.assertEqual([r[0] for r in logs], [expected_2, expected_1])

                # Return & re-issue should verify return message/email and >9999 growth
                ok_ret, _fine, ret_msg = db.return_book("10001", "24001-CS-001")
                self.assertTrue(ok_ret, ret_msg)
                self.assertIn(expected_1, ret_msg)

                db.conn.execute(
                    "UPDATE circulation_logs SET log_code = ? WHERE log_code = ?",
                    (f"CIR-{today_key}-9999", expected_1),
                )
                db.conn.commit()

                ok, msg3 = db.issue_book("10001", "24001-CS-001", 14)
                self.assertTrue(ok, msg3)
                expected_3 = f"CIR-{today_key}-10000"
                self.assertIn(expected_3, msg3)

                # Queued emails carry structured Transaction IDs
                bodies = [
                    r[0]
                    for r in db.conn.execute("SELECT body FROM email_queue").fetchall()
                ]
                self.assertTrue(any(expected_1 in b for b in bodies))
                self.assertTrue(any(expected_3 in b for b in bodies))

                # Clear logs when all returned resets sequence cleanly
                db.return_book("10001", "24001-CS-001")
                db.return_book("10002", "100201")
                ok_clr, _ = db.clear_all_logs()
                self.assertTrue(ok_clr)
                ok, msg4 = db.issue_book("10001", "24001-CS-001", 14)
                self.assertTrue(ok, msg4)
                self.assertIn(f"CIR-{today_key}-0001", msg4)
            finally:
                db.close()

    def test_legacy_db_migration_backfills_log_codes_preserving_fks(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "legacy.db")
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY COLLATE NOCASE,
                    phone_number TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT,
                    created_at TIMESTAMP
                );
                CREATE TABLE books (
                    id TEXT PRIMARY KEY COLLATE NOCASE,
                    title TEXT NOT NULL,
                    author TEXT,
                    publisher TEXT,
                    total_copies INTEGER NOT NULL DEFAULT 1,
                    available_copies INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP
                );
                CREATE TABLE circulation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    checkout_date TIMESTAMP,
                    due_date TIMESTAMP,
                    return_date TIMESTAMP,
                    fine_amount DECIMAL(10, 2) DEFAULT 0.00,
                    status TEXT DEFAULT 'ISSUED'
                );
                CREATE TABLE renewal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loan_id INTEGER NOT NULL,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    previous_due_date TIMESTAMP,
                    new_due_date TIMESTAMP,
                    extended_days INTEGER NOT NULL,
                    base_mode TEXT NOT NULL DEFAULT 'DUE_DATE',
                    fine_assessed DECIMAL(10, 2) DEFAULT 0.00,
                    fine_action TEXT NOT NULL DEFAULT 'NONE',
                    notes TEXT,
                    renewed_at TIMESTAMP NOT NULL
                );
                CREATE TABLE fine_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loan_id INTEGER NOT NULL,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    amount DECIMAL(10, 2) NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT,
                    settled_at TIMESTAMP NOT NULL
                );
                CREATE TABLE email_notifications (
                    loan_id INTEGER NOT NULL,
                    reminder_type TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (loan_id, reminder_type)
                );
                """
            )
            conn.execute(
                "INSERT INTO users(id, phone_number, full_name, role, department, created_at) "
                "VALUES ('24001-CS-001', '9876543210', 'Aarav', 'Student', 'Computer Science & Engineering', '2026-05-01')"
            )
            conn.execute(
                "INSERT INTO books(id, title, author, publisher, total_copies, available_copies, created_at) "
                "VALUES ('10001', 'Clean Code', 'Martin', 'Pearson', 3, 2, '2026-05-01')"
            )
            conn.execute(
                "INSERT INTO books(id, title, author, publisher, total_copies, available_copies, created_at) "
                "VALUES ('10002', 'Refactoring', 'Fowler', 'Addison', 2, 1, '2026-05-01')"
            )
            conn.execute(
                "INSERT INTO books(id, title, author, publisher, total_copies, available_copies, created_at) "
                "VALUES ('10003', 'Pragmatic Programmer', 'Hunt', 'Addison', 2, 1, '2026-05-01')"
            )
            conn.execute(
                "INSERT INTO circulation_logs(id, book_id, user_id, checkout_date, due_date, fine_amount, status) "
                "VALUES (1, '10001', '24001-CS-001', '2026-05-01 09:00', '2026-05-15 09:00', 10.0, 'ISSUED')"
            )
            conn.execute(
                "INSERT INTO circulation_logs(id, book_id, user_id, checkout_date, due_date, fine_amount, status) "
                "VALUES (2, '10002', '24001-CS-001', '2026-05-01 14:30', '2026-05-15 14:30', 0.0, 'RETURNED')"
            )
            conn.execute(
                "INSERT INTO circulation_logs(id, book_id, user_id, checkout_date, due_date, fine_amount, status) "
                "VALUES (3, '10003', '24001-CS-001', '', '2026-06-01 12:00', 0.0, 'ISSUED')"
            )
            conn.execute(
                "INSERT INTO renewal_logs(loan_id, book_id, user_id, previous_due_date, new_due_date, extended_days, renewed_at) "
                "VALUES (1, '10001', '24001-CS-001', '2026-05-15 09:00', '2026-05-22 09:00', 7, '2026-05-10 10:00')"
            )
            conn.execute(
                "INSERT INTO fine_payments(loan_id, book_id, user_id, amount, action, note, settled_at) "
                "VALUES (2, '10002', '24001-CS-001', 5.0, 'PAID', 'Cash', '2026-05-16 11:00')"
            )
            conn.commit()
            conn.close()

            db = database.LocalDatabase(db_path)
            try:
                rows = db.conn.execute(
                    "SELECT id, log_code FROM circulation_logs ORDER BY id ASC"
                ).fetchall()
                today_key = datetime.datetime.now().strftime("%y%m%d")
                self.assertEqual(rows[0], (1, "CIR-260501-0001"))
                self.assertEqual(rows[1], (2, "CIR-260501-0002"))
                self.assertEqual(rows[2][0], 3)
                self.assertTrue(re.match(rf"^CIR-{today_key}-\d{{4}}$", rows[2][1]))

                # FK integrity preserved
                r_hist = db.get_renewal_history("CIR-260501-0001")
                self.assertEqual(len(r_hist), 1)
                self.assertEqual(r_hist[0]["loan_id"], "CIR-260501-0001")

                f_hist = db.get_fine_payment_history("CIR-260501-0002")
                self.assertEqual(len(f_hist), 1)
                self.assertEqual(f_hist[0]["loan_id"], "CIR-260501-0002")
            finally:
                db.close()

            # Re-opening migrated DB must be completely idempotent
            db2 = database.LocalDatabase(db_path)
            try:
                rows2 = db2.conn.execute(
                    "SELECT id, log_code FROM circulation_logs ORDER BY id ASC"
                ).fetchall()
                self.assertEqual(rows2[0], (1, "CIR-260501-0001"))
                self.assertEqual(rows2[1], (2, "CIR-260501-0002"))
            finally:
                db2.close()

    def test_dual_lookup_compatibility_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = database.LocalDatabase(os.path.join(tmp, "compat.db"))
            try:
                _seed_sample_entities(db)
                db.issue_book("10001", "24001-CS-001", 14)
                loan_code = db.get_active_loan_id("10001", "24001-CS-001")
                self.assertTrue(utils.is_structured_log_id(loan_code))

                # Make loan overdue with unsettled fine
                past_due = (datetime.date.today() - datetime.timedelta(days=4)).strftime("%Y-%m-%d 18:00")
                db.conn.execute(
                    "UPDATE circulation_logs SET due_date = ?, fine_amount = 12.0 WHERE log_code = ?",
                    (past_due, loan_code),
                )
                db.conn.commit()

                # Lookup via structured code, lowercase code, #-prefixed code, and int PK (1)
                for ref in (loan_code, loan_code.lower(), f"#{loan_code}", 1, "1"):
                    preview = db.get_loan_renewal_preview(ref)
                    self.assertTrue(preview["found"], f"Failed lookup for {ref}")
                    self.assertEqual(preview["loan_id"], loan_code)

                    details = db.get_circulation_log_details(ref)
                    self.assertIsNotNone(details)
                    self.assertEqual(details["log_id"], loan_code)

                # Invalid vs Not-Found error discrimination
                bad = db.get_loan_renewal_preview("not-valid")
                self.assertEqual(bad["block_reason"], "Invalid transaction ID.")
                missing_code = db.get_loan_renewal_preview("CIR-261112-9999")
                self.assertEqual(
                    missing_code["block_reason"],
                    "Transaction CIR-261112-9999 was not found.",
                )
                missing_pk = db.get_loan_renewal_preview(999)
                self.assertEqual(missing_pk["block_reason"], "Transaction #999 was not found.")

                # Mixed-key batch meta lookups preserve caller keys
                r_meta = db.get_loan_renewal_meta([loan_code, 1])
                self.assertIn(loan_code, r_meta)
                self.assertIn(1, r_meta)
                f_meta = db.get_loan_fine_settlement_meta([loan_code.lower(), 1])
                self.assertIn(loan_code.lower(), f_meta)
                self.assertIn(1, f_meta)

                # Renew via lowercase structured ID & settle fine via #-prefixed ID
                ok_ren, ren_details, ren_msg = db.renew_loan(
                    loan_code.lower(), extend_days=7, fine_action="CARRY", notes="Test"
                )
                self.assertTrue(ok_ren, ren_msg)
                self.assertEqual(ren_details["loan_id"], loan_code)
                self.assertIn(loan_code, ren_msg)

                ok_settle, settle_msg = db.settle_loan_fine(
                    f"#{loan_code}", action="PAID", note="Desk receipt"
                )
                self.assertTrue(ok_settle, settle_msg)
                self.assertIn(loan_code, settle_msg)
            finally:
                db.close()


class CirculationLogIdUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = database.LocalDatabase(os.path.join(cls.tmp.name, "ui_log_id.db"))
        _seed_sample_entities(cls.db)
        cls.db.issue_book("10001", "24001-CS-001", 14)
        cls.loan_code_1 = cls.db.get_active_loan_id("10001", "24001-CS-001")

        past_due = (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y-%m-%d 18:00")
        cls.db.issue_book("10002", "100201", 14)
        cls.loan_code_2 = cls.db.get_active_loan_id("10002", "100201")
        cls.db.conn.execute(
            "UPDATE circulation_logs SET due_date = ?, fine_amount = 20.0 WHERE log_code = ?",
            (past_due, cls.loan_code_2),
        )
        cls.db.conn.commit()

        cls.window = MainWindow(cls.db)
        cls.window.show()
        _pump(4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.window.email_sync_manager.sync_timer.stop()
            cls.window.email_sync_manager.status_timer.stop()
            cls.window.email_sync_manager.thread_pool.waitForDone(3000)
        except Exception:
            pass
        cls.window.close()
        cls.window.deleteLater()
        _pump(3)
        cls.db.close()
        cls.tmp.cleanup()

    def test_circulation_table_fits_log_id_without_truncation_or_overflow(self):
        self.window.switch_page(3)
        page = self.window.circulation_view
        for size in ((1280, 820), (1366, 768)):
            self.window.resize(*size)
            _pump(4)
            self.assertEqual(page.table.horizontalScrollBar().maximum(), 0)
            col0_item = page.table.item(0, 0)
            self.assertIsNotNone(col0_item)
            self.assertEqual(col0_item.text(), self.loan_code_2)
            col0_w = page.table.columnWidth(0)
            self.assertGreaterEqual(
                col0_w,
                118,
                f"Log ID column ({col0_w}px) narrower than required 118px desktop width at {size}",
            )
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                self.assertGreaterEqual(col0_w, page.table.sizeHintForColumn(0))

        # Selecting row shows structured Transaction ID in inspector & copies cleanly
        page.table.selectRow(0)
        _pump(2)
        overview_texts = [lbl.text() for lbl in page.tab_overview.findChildren(QLabel)]
        self.assertTrue(any(self.loan_code_2 in t for t in overview_texts))
        self.assertFalse(any(f"#{self.loan_code_2}" in t for t in overview_texts))

        copy_btns = [
            b for b in page.tab_actions.findChildren(QPushButton)
            if "Copy Transaction ID" in b.text()
        ]
        self.assertEqual(len(copy_btns), 1)
        copy_btns[0].click()
        self.assertEqual(QApplication.clipboard().text(), self.loan_code_2)

        page.search_input.setText(self.loan_code_1)
        _pump(2)
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 0).text(), self.loan_code_1)

        csv_path = os.path.join(self.tmp.name, "circ_export.csv")
        with mock.patch(
            "pages.circulation_view.QFileDialog.getSaveFileName",
            return_value=(csv_path, "CSV Files (*.csv)"),
        ), mock.patch("pages.circulation_view.QMessageBox.information"):
            page.export_csv()
        self.assertTrue(os.path.isfile(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as handle:
            exported = handle.read()
        self.assertIn(self.loan_code_1, exported)

        page.search_input.clear()
        _pump(2)

    def test_global_search_and_dialogs_render_structured_log_id(self):
        results = self.window.dashboard_view.search_global_records(self.loan_code_1)
        tx_results = [r for r in results if r["type"] == "Transaction"]
        self.assertEqual(len(tx_results), 1)
        self.assertEqual(tx_results[0]["id"], self.loan_code_1)
        self.assertIn(self.loan_code_1, tx_results[0]["description"])
        self.assertNotIn(f"#{self.loan_code_1}", tx_results[0]["description"])

        self.window._open_global_search_result(tx_results[0])
        _pump(3)
        self.assertEqual(self.window.circulation_view.table.item(0, 0).text(), self.loan_code_1)
        self.assertEqual(self.window.circulation_view.search_input.text(), self.loan_code_1)
        self.window.circulation_view.search_input.clear()
        _pump(2)

        # Dialogs format cleanly without '#CIR-...'
        fines_dlg = PendingFinesDialog(self.db)
        fines_dlg.show()
        _pump(2)
        self.assertEqual(fines_dlg.table.item(0, 0).text(), self.loan_code_2)
        fines_dlg.close()
        fines_dlg.deleteLater()

        hist_dlg = ActivityHistoryDialog(self.db)
        hist_dlg.show()
        _pump(2)
        self.assertEqual(hist_dlg.table.item(0, 0).text(), self.loan_code_2)
        hist_dlg.close()
        hist_dlg.deleteLater()

        book_dlg = BookHistoryDialog(self.db, "10001", "Clean Architecture")
        book_dlg.show()
        _pump(2)
        self.assertEqual(book_dlg.table.item(0, 0).text(), self.loan_code_1)
        book_dlg.close()
        book_dlg.deleteLater()

        renew_dlg = RenewLoanDialog(self.db, self.loan_code_1)
        self.assertIn(self.loan_code_1, renew_dlg.windowTitle())
        self.assertNotIn(f"#{self.loan_code_1}", renew_dlg.windowTitle())
        renew_dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()

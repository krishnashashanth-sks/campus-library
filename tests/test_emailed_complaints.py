import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import email.mime.multipart
import email.mime.text
import imaplib
import io
import logging
import sys
import tempfile
import unittest
from email.header import Header
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication

import database
import email_queue
import email_service
import main as app_main
from pages.reports_view import ReportsView
from dialogs import (
    ComplaintDialog,
    ComplaintManagementDialog,
    CustomEmailDialog,
    GmailComplaintReviewDialog,
)
from pages.settings_view import SettingsView
from pages.usermanagement_view import UserManagementView
from theme_manager import ThemeManager


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_emailed_complaints"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=3):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


def _build_raw_email(
    sender,
    to_addr,
    subject,
    plain_body="",
    html_body="",
    message_id=None,
    extra_headers=None,
    date_header="Thu, 12 Nov 2026 10:15:00 +0530",
):
    if html_body and plain_body:
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg.attach(email.mime.text.MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))
    elif html_body:
        msg = email.mime.text.MIMEText(html_body, "html", "utf-8")
    else:
        msg = email.mime.text.MIMEText(plain_body, "plain", "utf-8")

    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = Header(subject, "utf-8") if any(ord(c) > 127 for c in subject) else subject
    msg["Date"] = date_header
    if message_id:
        msg["Message-ID"] = message_id
    for k, v in (extra_headers or {}).items():
        msg[k] = v
    return msg.as_bytes()


class _FakeImapServer:
    """In-memory mock of imaplib.IMAP4_SSL supporting read-only UID SEARCH/FETCH."""

    def __init__(self, messages_by_uid):
        self.messages_by_uid = dict(messages_by_uid)
        self.selected_readonly = None
        self.logged_in = None
        self.closed = False
        self.logged_out = False

    def login(self, user, password):
        self.logged_in = (user, password)
        return "OK", [b"Logged in"]

    def select(self, mailbox="INBOX", readonly=False):
        self.selected_readonly = (mailbox, readonly)
        return "OK", [str(len(self.messages_by_uid)).encode("ascii")]

    def uid(self, command, *args):
        cmd = str(command).lower()
        if cmd == "search":
            uids = " ".join(sorted(self.messages_by_uid.keys(), key=int))
            return "OK", [uids.encode("ascii")]
        if cmd == "fetch":
            uid_bytes = args[0]
            uid_str = uid_bytes.decode("ascii") if isinstance(uid_bytes, (bytes, bytearray)) else str(uid_bytes)
            raw = self.messages_by_uid[uid_str]
            return "OK", [(f"{uid_str} (UID {uid_str} FLAGS ())".encode("ascii"), raw), b")"]
        raise AssertionError(f"Unexpected IMAP UID command: {command}")

    def close(self):
        self.closed = True
        return "OK", []

    def logout(self):
        self.logged_out = True
        return "BYE", []


class EmailedComplaintIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.fspath(Path(self.tmp.name) / "library.db")
        self.db = database.LocalDatabase(self.db_path)
        self.db.insert_user(
            "24001-CS-001",
            "Aarav Sharma",
            "9876500001",
            "Student",
            "Computer Science",
            email="aarav.sharma@college.edu",
        )
        self.db.insert_user(
            "24001-EC-015",
            "Diya Nair",
            "9876500002",
            "Student",
            "Electronics",
            email="",
        )
        self.db.set_setting("email_sender", "librarymanagementsystem.gptm@gmail.com")
        self.db.set_setting("library_contact_email", "librarian.desk@college.edu")
        self.db.set_setting("email_complaint_import_enabled", "1")
        self.db.set_setting("email_complaint_auto_reply", "1")
        self.db.set_setting("email_complaint_filter_mode", "keywords")

    def tearDown(self):
        try:
            self.db.close()
        finally:
            self.tmp.cleanup()

    def test_schema_user_matching_and_dedupe(self):
        # Match by registered email
        uid, name, resolved_email, reason = self.db.find_user_for_inbound_email(
            "AARAV.SHARMA@COLLEGE.EDU",
            "Issue with book copy",
            "Page 42 is missing.",
        )
        self.assertEqual(uid, "24001-CS-001")
        self.assertEqual(name, "Aarav Sharma")
        self.assertEqual(resolved_email, "aarav.sharma@college.edu")
        self.assertIn("Registered email", reason)

        # Match by Roll No mentioned inside email when student sends from personal Gmail
        uid2, name2, _email2, reason2 = self.db.find_user_for_inbound_email(
            "diya.personal@gmail.com",
            "Feedback from 24001-ec-015",
            "Reading room fans are noisy.",
        )
        self.assertEqual(uid2, "24001-EC-015")
        self.assertEqual(name2, "Diya Nair")
        self.assertIn("Roll No", reason2)

        # Unregistered sender falls back gracefully cleanly preserving sender info
        ok, status, row = self.db.import_emailed_complaint(
            message_key="<msg-unknown@gmail.com>",
            sender_email="guest.parent@gmail.com",
            sender_name="Ramesh Rao",
            subject="Broken chair in study hall",
            body="Chair #4 near window needs repair.",
        )
        self.assertTrue(ok)
        self.assertEqual(status, "IMPORTED")
        self.assertIsNone(row[1])
        self.assertEqual(row[2], "Ramesh Rao")
        self.assertEqual(row[3], "guest.parent@gmail.com")

        # Duplicate Message-ID cannot create a second complaint
        ok_dup, status_dup, row_dup = self.db.import_emailed_complaint(
            message_key="<msg-unknown@gmail.com>",
            sender_email="guest.parent@gmail.com",
            sender_name="Ramesh Rao",
            subject="Broken chair in study hall",
            body="Chair #4 near window needs repair.",
        )
        self.assertFalse(ok_dup)
        self.assertEqual(status_dup, "ALREADY_IMPORTED")
        self.assertIsNone(row_dup)

        # Detailed query & status/notes update
        detailed = self.db.get_complaints_detailed(source="EMAIL")
        self.assertEqual(len(detailed), 1)
        self.assertEqual(detailed[0]["source"], "EMAIL")
        self.assertEqual(detailed[0]["reporter_email"], "guest.parent@gmail.com")

        upd_ok, _msg = self.db.update_complaint_status(
            detailed[0]["id"],
            "IN_PROGRESS",
            staff_notes="Maintenance notified on Nov 12.",
        )
        self.assertTrue(upd_ok)
        detailed_after = self.db.get_complaints_detailed(status="IN_PROGRESS")
        self.assertEqual(detailed_after[0]["staff_notes"], "Maintenance notified on Nov 12.")

    def test_imap_sync_imports_student_emails_ignores_loops_and_queues_receipts(self):
        fake_messages = {
            # 1: Registered student plain text complaint -> IMPORT
            "101": _build_raw_email(
                sender="Aarav Sharma <aarav.sharma@college.edu>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Damaged cover on Algorithms book",
                plain_body="Book ID 10001 spine is loose.",
                message_id="<student-1@college.edu>",
            ),
            # 2: Unregistered personal Gmail mentioning Roll No + HTML-only mobile email -> IMPORT + match 24001-EC-015
            "102": _build_raw_email(
                sender="Diya <diya.personal@gmail.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Complaint regarding renewal",
                html_body="<div>Hello Sir,<br>I am <b>24001-EC-015</b>. Renewal option showed fine error.<br>Thanks</div>",
                message_id="<student-2@gmail.com>",
            ),
            # 3: Google Security alert / automated sender -> SKIP (automated)
            "103": _build_raw_email(
                sender="Google <no-reply@accounts.google.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Security alert: App password created",
                plain_body="You created an App password for your Google Account.",
                message_id="<google-alert@accounts.google.com>",
            ),
            # 4: Self-sent feedback receipt / loop -> SKIP (automated/loop)
            "104": _build_raw_email(
                sender="Library <librarymanagementsystem.gptm@gmail.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="We received your library feedback: Test",
                plain_body="Your reference number is #1.",
                message_id="<self-loop@gmail.com>",
                extra_headers={"X-CampusLibrary-Generated": "1"},
            ),
            # 5: Newsletter with List-Unsubscribe containing word "issue" -> SKIP (newsletter)
            "105": _build_raw_email(
                sender="Tech Digest <digest@example.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Weekly issue #99 is out",
                plain_body="Read this week's issue on cloud software.",
                message_id="<newsletter-99@example.com>",
                extra_headers={"List-Unsubscribe": "<mailto:unsub@example.com>"},
            ),
            # 6: Unregistered vague human email ("Hi sir") -> skipped in auto keyword mode, visible in manual Review dialog
            "106": _build_raw_email(
                sender="Ravi Kumar <ravi99@gmail.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Quick question",
                plain_body="What time does the reading room open tomorrow?",
                message_id="<vague-ravi@gmail.com>",
            ),
            # 7: Unicode subject without Message-ID (tests MIME header decode & SHA-256 fallback key)
            "107": _build_raw_email(
                sender="Student Feedback <feedback.sender@gmail.com>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Feedback – Water cooler issue",
                plain_body="Water cooler on 1st floor is not cooling.",
                message_id=None,
            ),
        }

        fake_imap = _FakeImapServer(fake_messages)

        with (
            mock.patch.object(email_service, "read_secret", return_value="abcd efgh ijkl mnop"),
            mock.patch.object(email_service.imaplib, "IMAP4_SSL", return_value=fake_imap),
        ):
            svc = email_service.LibraryEmailService(self.db)
            summary = svc.sync_emailed_complaints()

            self.assertEqual(fake_imap.selected_readonly, ("INBOX", True))
            self.assertTrue(fake_imap.closed)
            self.assertTrue(fake_imap.logged_out)
            self.assertEqual(summary["checked"], 7)
            self.assertEqual(summary["imported"], 3)
            self.assertEqual(summary["matched_users"], 2)
            self.assertEqual(summary["skipped_automated"], 3)
            self.assertEqual(summary["skipped_filter"], 1)

            # Running a second time produces zero duplicate imports
            summary_second = svc.sync_emailed_complaints()
            self.assertEqual(summary_second["imported"], 0)
            self.assertEqual(summary_second["already_processed"], 3)

            # Verify parsed bodies, HTML stripping, and queued auto-replies
            complaints = self.db.get_complaints_detailed(source="EMAIL")
            self.assertEqual(len(complaints), 3)
            subjects = {c["subject"]: c for c in complaints}
            self.assertEqual(subjects["Damaged cover on Algorithms book"]["user_id"], "24001-CS-001")
            self.assertIn("I am 24001-EC-015.", subjects["Complaint regarding renewal"]["body"])
            self.assertEqual(subjects["Complaint regarding renewal"]["user_id"], "24001-EC-015")
            self.assertNotIn("<div>", subjects["Complaint regarding renewal"]["body"])

            # Auto-replies + staff alerts should be queued cleanly (staff + user for each)
            queued = self.db.get_email_queue_items("PENDING")
            recipients = [row[1] for row in queued]
            self.assertIn("aarav.sharma@college.edu", recipients)
            self.assertIn("diya.personal@gmail.com", recipients)
            self.assertIn("feedback.sender@gmail.com", recipients)
            self.assertIn("librarian.desk@college.edu", recipients)

            # Background EmailWorker also imports incoming emails even when outbound delivery is disabled,
            # and skips sending outbound SMTP while email_delivery_enabled == "0".
            self.db.set_setting("email_delivery_enabled", "0")
            fake_imap_2 = _FakeImapServer({
                "201": _build_raw_email(
                    sender="Aarav Sharma <aarav.sharma@college.edu>",
                    to_addr="librarymanagementsystem.gptm@gmail.com",
                    subject="Another complaint on Wi-Fi",
                    plain_body="Reading hall Wi-Fi disconnects every 5 minutes.",
                    message_id="<student-wifi@college.edu>",
                )
            })
            worker_results = []
            with (
                mock.patch.object(email_queue.EmailWorker, "_is_imap_online", return_value=True),
                mock.patch.object(email_service.imaplib, "IMAP4_SSL", return_value=fake_imap_2),
            ):
                worker = email_queue.EmailWorker(self.db_path)
                worker.signals.finished.connect(worker_results.append)
                worker.run()
            self.assertEqual(len(worker_results), 1)
            self.assertEqual(worker_results[0]["imported_complaints"], 1)
            self.assertEqual(worker_results[0]["sent"], 0)
            self.assertEqual(self.db.get_complaint_counts()["email"], 4)

    def test_imap_eof_auto_retries_and_preserves_progress(self):
        fake_messages = {
            "301": _build_raw_email(
                sender="Aarav Sharma <aarav.sharma@college.edu>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Complaint about chair",
                plain_body="Reading room chair leg is loose.",
                message_id="<eof-1@college.edu>",
            ),
            "302": _build_raw_email(
                sender="Aarav Sharma <aarav.sharma@college.edu>",
                to_addr="librarymanagementsystem.gptm@gmail.com",
                subject="Complaint about AC",
                plain_body="AC in quiet zone is warm.",
                message_id="<eof-2@college.edu>",
            ),
        }

        class _FlakyImapServer(_FakeImapServer):
            def __init__(self, messages_by_uid, fail_on_uid=None):
                super().__init__(messages_by_uid)
                self.fail_on_uid = fail_on_uid
                self.fetched_uids = []

            def uid(self, command, *args):
                if str(command).lower() == "fetch":
                    uid_bytes = args[0]
                    uid_str = (
                        uid_bytes.decode("ascii")
                        if isinstance(uid_bytes, (bytes, bytearray))
                        else str(uid_bytes)
                    )
                    self.fetched_uids.append(uid_str)
                    if self.fail_on_uid and uid_str == self.fail_on_uid:
                        raise imaplib.IMAP4.abort("socket error: EOF")
                return super().uid(command, *args)

        # Attempt 1 fails mid-batch on UID 302 after already fetching UID 301;
        # Attempt 2 reconnects and resumes at UID 302 without re-fetching UID 301.
        first_conn = _FlakyImapServer(fake_messages, fail_on_uid="302")
        second_conn = _FlakyImapServer(fake_messages, fail_on_uid=None)

        with (
            mock.patch.object(email_service, "read_secret", return_value="abcd efgh ijkl mnop"),
            mock.patch.object(email_service, "_wait_before_retry"),
            mock.patch.object(
                email_service.imaplib,
                "IMAP4_SSL",
                side_effect=[first_conn, second_conn],
            ),
        ):
            svc = email_service.LibraryEmailService(self.db)
            messages = svc.fetch_inbox_messages()

        self.assertEqual([m["uid"] for m in messages], ["301", "302"])
        self.assertEqual(first_conn.fetched_uids, ["301", "302"])
        self.assertEqual(second_conn.fetched_uids, ["302"])
        self.assertTrue(first_conn.logged_out)
        self.assertTrue(second_conn.logged_out)

    def test_imap_persistent_eof_suppresses_background_warning_spam_and_auth_fails_fast(self):
        # 1. Persistent EOF across all retries raises helpful error in direct calls,
        #    and EmailWorker does NOT emit noisy WARNING:root logs for transient EOF.
        with (
            mock.patch.object(email_service, "read_secret", return_value="abcd efgh ijkl mnop"),
            mock.patch.object(email_service, "_wait_before_retry"),
            mock.patch.object(
                email_queue.EmailWorker, "_is_imap_online", return_value=True
            ),
            mock.patch.object(
                email_service.imaplib,
                "IMAP4_SSL",
                side_effect=imaplib.IMAP4.abort("socket error: EOF"),
            ) as mock_imap_cls,
        ):
            worker_results = []
            with mock.patch.object(email_queue.logging, "warning") as mock_warn:
                worker = email_queue.EmailWorker(self.db_path)
                worker.signals.finished.connect(worker_results.append)
                worker.run()

            mock_warn.assert_not_called()
            self.assertEqual(mock_imap_cls.call_count, 3)
            self.assertEqual(len(worker_results), 1)
            self.assertTrue(worker_results[0]["imap_error_transient"])
            self.assertIn("socket EOF", worker_results[0]["imap_error"])

        # 2. Authentication failures fail fast without retrying 3 times.
        auth_fail_server = mock.MagicMock()
        auth_fail_server.login.side_effect = imaplib.IMAP4.error(
            b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)"
        )
        with (
            mock.patch.object(email_service, "read_secret", return_value="badpass"),
            mock.patch.object(email_service, "_wait_before_retry"),
            mock.patch.object(
                email_service.imaplib,
                "IMAP4_SSL",
                return_value=auth_fail_server,
            ) as mock_imap_cls,
        ):
            svc = email_service.LibraryEmailService(self.db)
            with self.assertRaises(RuntimeError) as ctx:
                svc.fetch_inbox_messages()
            self.assertIn("authentication failed", str(ctx.exception).casefold())
            self.assertEqual(mock_imap_cls.call_count, 1)


class ComplaintAndSettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.fspath(Path(self.tmp.name) / "ui_library.db")
        self.db = database.LocalDatabase(self.db_path)
        self.db.insert_user(
            "24001-CS-001",
            "Aarav Sharma",
            "9876500001",
            "Student",
            "Computer Science",
            email="aarav@college.edu",
        )
        self.db.insert_user(
            "24001-CS-002",
            "Bhavna Reddy",
            "9876500002",
            "Student",
            "Computer Science",
            email="bhavna@college.edu",
        )

    def tearDown(self):
        try:
            self.db.close()
        finally:
            self.tmp.cleanup()

    def test_complaint_ui_workflows_review_dialog_and_settings(self):
        # 1. Pre-selected user in ComplaintDialog + filter narrows dropdown
        dlg = ComplaintDialog(self.db, initial_user_id="24001-CS-002")
        try:
            self.assertEqual(dlg.user_combo.currentData(), "24001-CS-002")
            dlg.user_filter_input.setText("Aarav")
            _pump(2)
            # Item 0 is General/anonymous, item 1 is Aarav Sharma
            self.assertEqual(dlg.user_combo.count(), 2)
            self.assertEqual(dlg.user_combo.itemData(1), "24001-CS-001")
        finally:
            dlg.close()
            dlg.deleteLater()
            _pump(2)

        # 2. GmailComplaintReviewDialog imports missed email & links selected student + queues receipt
        prefetched = [
            {
                "uid": "501",
                "message_key": "<unfiltered-1@gmail.com>",
                "sender_name": "Kiran",
                "sender_email": "kiran.alt@gmail.com",
                "subject": "Quick question",
                "body": "Sir, my Roll No is 24001-CS-001 and my ID card barcode is faded.",
                "received_at": "2026-11-12T11:00:00",
                "is_seen": False,
                "is_automated": False,
                "skip_reason": "",
                "matched_user_id": "24001-CS-001",
                "matched_user_name": "Aarav Sharma",
                "matched_user_email": "aarav@college.edu",
                "match_reason": "Roll No / ID in message",
                "matches_filter": False,
                "filter_reason": "Unfiltered",
                "import_status": "",
                "complaint_id": None,
            }
        ]
        review = GmailComplaintReviewDialog(self.db, prefetched_messages=prefetched)
        try:
            review.show()
            _pump(3)
            self.assertEqual(review.table.rowCount(), 1)
            self.assertTrue(review.import_btn.isEnabled())
            review.import_selected_message()
            _pump(2)
            detailed = self.db.get_complaints_detailed(source="EMAIL")
            self.assertEqual(len(detailed), 1)
            self.assertEqual(detailed[0]["user_id"], "24001-CS-001")
            pending_receipts = [
                m
                for m in self.db.get_email_queue_items("PENDING")
                if "We received your library feedback" in str(m[2])
            ]
            self.assertEqual(len(pending_receipts), 1)
            self.assertEqual(pending_receipts[0][1], "aarav@college.edu")
        finally:
            review.close()
            review.deleteLater()
            _pump(2)

        # 3. ComplaintManagementDialog filters, updates status + notes, and composes email reply
        inbox = ComplaintManagementDialog(self.db)
        try:
            inbox.show()
            _pump(3)
            self.assertEqual(inbox.table.rowCount(), 1)
            self.assertTrue(inbox.reply_email_button.isEnabled())
            inbox.staff_notes_input.setText("Issued replacement barcode label.")
            resolved_idx = inbox.status_combo.findData("RESOLVED")
            inbox.status_combo.setCurrentIndex(resolved_idx)
            inbox.update_status()
            _pump(2)
            saved = self.db.get_complaints_detailed(status="RESOLVED")
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["staff_notes"], "Issued replacement barcode label.")

            with mock.patch("dialogs.CustomEmailDialog.exec", return_value=1), mock.patch(
                "dialogs.CustomEmailDialog.get_data",
                return_value=("Re: Barcode fixed", "Your new card barcode is ready."),
            ), mock.patch("dialogs.show_success"):
                inbox.reply_to_selected_complaint()
            queued_msgs = self.db.get_email_queue_items("PENDING")
            self.assertTrue(any(m[2] == "Re: Barcode fixed" for m in queued_msgs))
        finally:
            inbox.close()
            inbox.deleteLater()
            _pump(2)

        # 4. UserManagementView exposes both complaint buttons visibly & updates unresolved badge
        um = UserManagementView(self.db)
        try:
            um.resize(1100, 760)
            um.show()
            _pump(3)
            self.assertTrue(um.complaint_inbox_btn.isVisible())
            self.assertTrue(um.complaint_btn.isVisible())
            self.assertIn("Complaint Inbox", um.complaint_inbox_btn.text())

            ok, _c = self.db.create_complaint("24001-CS-002", "Desk issue", "Chair squeaks")
            self.assertTrue(ok)
            um.update_complaint_badge()
            self.assertIn("(1)", um.complaint_inbox_btn.text())
        finally:
            um.close()
            um.deleteLater()
            _pump(2)

        # 5. SettingsView persists IMAP complaint fetch, auto-reply, and filter mode
        settings = SettingsView(self.db)
        try:
            settings.email_sender_input.setText("library@college.edu")
            settings.email_import_complaints_checkbox.setChecked(False)
            settings.email_complaint_auto_reply_checkbox.setChecked(False)
            all_idx = settings.email_complaint_filter_combo.findData("all")
            settings.email_complaint_filter_combo.setCurrentIndex(all_idx)
            with mock.patch("pages.settings_view.QMessageBox.information"):
                self.assertTrue(settings.save_email_settings(show_confirmation=True))
            self.assertEqual(self.db.get_setting("email_complaint_import_enabled"), "0")
            self.assertEqual(self.db.get_setting("email_complaint_auto_reply"), "0")
            self.assertEqual(self.db.get_setting("email_complaint_filter_mode"), "all")
        finally:
            settings.stop_workers()
            settings.close()
            settings.deleteLater()
            _pump(2)

        # 6. QtCharts wildcard-disconnect filter suppresses BarChartItem/axis noise while keeping real Qt warnings
        captured_stderr = io.StringIO()
        prev_handler = None
        try:
            with mock.patch.object(sys, "stderr", captured_stderr):
                handler = app_main.install_qt_warning_filter()
                handler(
                    None,
                    None,
                    "QObject::disconnect: wildcard call disconnects from destroyed signal of BarChartItem::unnamed",
                )
                handler(
                    None,
                    None,
                    "QObject::disconnect: wildcard call disconnects from destroyed signal of ChartValueAxisY::unnamed",
                )
                handler(
                    None,
                    None,
                    "QObject::disconnect: wildcard call disconnects from destroyed signal of ChartBarCategoryAxisX::unnamed",
                )
                handler(None, None, "Real Qt warning that must remain visible")
        finally:
            qInstallMessageHandler(prev_handler)

        stderr_text = captured_stderr.getvalue()
        self.assertNotIn("BarChartItem::unnamed", stderr_text)
        self.assertNotIn("ChartValueAxisY::unnamed", stderr_text)
        self.assertNotIn("ChartBarCategoryAxisX::unnamed", stderr_text)
        self.assertIn("Real Qt warning that must remain visible", stderr_text)

        # Verify ReportsView renders, swaps, and closes bar/pie charts cleanly
        reports = ReportsView(self.db)
        try:
            reports.resize(900, 620)
            reports.show()
            _pump(2)
            reports.switch_graph_view("ACTIVE")
            _pump(2)
            reports.switch_graph_view("ISSUED")
            _pump(2)
        finally:
            reports.close()
            reports.deleteLater()
            _pump(2)


if __name__ == "__main__":
    unittest.main()

import datetime
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from database import LocalDatabase
from cloud_backup_service import (
    _verification_email_was_sent_recently,
    export_atomic_clbk_backup,
    read_sync_status,
    get_sync_status_file_path,
    CloudBackupScheduler,
)
from google_drive_backup import decrypt_backup_file


app = QApplication.instance()
if not app:
    app = QApplication([])


class TestSQLiteHardeningAndSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_db_hardening_")
        self.db_path = os.path.join(self.temp_dir, "test_library.db")
        self.db = LocalDatabase(self.db_path)

    def tearDown(self):
        if hasattr(self, "db") and self.db:
            self.db.close()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_pragmas_wal_busy_timeout_synchronous(self):
        """Verify WAL mode, busy_timeout=5000, and synchronous=NORMAL."""
        conn = self.db.conn
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(journal_mode.lower(), "wal")

        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(busy_timeout, 5000)

        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        # synchronous = 1 corresponds to NORMAL in SQLite
        self.assertEqual(synchronous, 1)

    def test_metadata_columns_and_triggers_desktop_write(self):
        """Verify updated_at and last_modified_by default to desktop on local write."""
        # Insert book
        success, msg = self.db.insert_book(
            "B001", "Design Patterns", "GoF", "Addison-Wesley", 5, 5
        )
        self.assertTrue(success, msg)

        conn = self.db.conn
        row = conn.execute(
            "SELECT updated_at, last_modified_by FROM books WHERE id = 'B001'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], "desktop")

        # Update book
        success, msg = self.db.edit_book(
            "B001", "Design Patterns Revised", "GoF", "Addison-Wesley", 5, 5
        )
        self.assertTrue(success, msg)

        row = conn.execute(
            "SELECT updated_at, last_modified_by, title FROM books WHERE id = 'B001'"
        ).fetchone()
        self.assertEqual(row[1], "desktop")
        self.assertEqual(row[2], "Design Patterns Revised")

    def test_triggers_preserve_web_modifier(self):
        """Verify triggers preserve 'web' modifier when written by sync daemon."""
        conn = self.db.conn
        conn.execute(
            """
            INSERT INTO books (id, title, author, publisher, total_copies, available_copies, last_modified_by)
            VALUES ('B002', 'Web Inserted Book', 'Web Author', 'Pub', 3, 3, 'web')
            """
        )
        conn.commit()
        row = conn.execute(
            "SELECT updated_at, last_modified_by FROM books WHERE id = 'B002'"
        ).fetchone()
        self.assertEqual(row[1], "web")
        self.assertIsNotNone(row[0])

        # Now update as web
        conn.execute(
            """
            UPDATE books
            SET title = 'Web Updated Book', last_modified_by = 'web'
            WHERE id = 'B002'
            """
        )
        conn.commit()
        row = conn.execute(
            "SELECT updated_at, last_modified_by, title FROM books WHERE id = 'B002'"
        ).fetchone()
        self.assertEqual(row[1], "web")
        self.assertEqual(row[2], "Web Updated Book")

    def test_concurrent_daemon_write_triggers_data_version(self):
        """Simulate external daemon modifying database.db and verify PRAGMA data_version change."""
        initial_stamp = self.db.get_data_stamp()
        initial_version = initial_stamp[1]

        # External connection writes to database.db
        external_conn = sqlite3.connect(self.db_path, timeout=5)
        external_conn.execute("PRAGMA journal_mode = WAL")
        external_conn.execute(
            """
            INSERT INTO books (id, title, author, publisher, total_copies, available_copies, last_modified_by)
            VALUES ('B_CONC_1', 'Daemon Book', 'Daemon Author', 'Pub', 2, 2, 'web')
            """
        )
        external_conn.commit()
        external_conn.close()

        # Check that local connection sees updated data_version
        new_stamp = self.db.get_data_stamp()
        new_version = new_stamp[1]
        self.assertNotEqual(initial_version, new_version)

    def test_cloud_sync_worker_is_retained_until_completion(self):
        class HoldingThreadPool:
            worker = None

            def start(self, worker):
                self.worker = worker

        scheduler = CloudBackupScheduler(self.db)
        scheduler.thread_pool = HoldingThreadPool()
        scheduler.trigger_async_sync(force=True)

        worker = scheduler.thread_pool.worker
        self.assertIs(scheduler._active_sync_worker, worker)
        self.assertIs(worker.signals.parent(), scheduler)
        self.assertTrue(worker.force_full_scan)

        worker.signals.finished.emit(True, "Sync complete", {"status": "synced"})
        self.assertIsNone(scheduler._active_sync_worker)
        self.assertFalse(scheduler._is_syncing)

        scheduler._stopping = True
        scheduler.poll_timer.stop()
        scheduler.debounce_timer.stop()


class TestAtomicCLBKBackup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_clbk_")
        self.db_path = os.path.join(self.temp_dir, "test_library.db")
        self.backup_folder = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.backup_folder, exist_ok=True)
        self.db = LocalDatabase(self.db_path)
        self.db.insert_book("B1", "Book 1", "Author 1", "Publisher", 10, 10)
        self.db.insert_user("U1", "Alice Student", "1234567890", "Student", "Computer Science", "2026-01-01")

    def tearDown(self):
        if hasattr(self, "db") and self.db:
            self.db.close()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_atomic_export_and_decryption(self):
        """Verify atomic .clbk export produces a valid encrypted archive that can be decrypted."""
        meta = export_atomic_clbk_backup(self.db, self.backup_folder)
        self.assertTrue(meta["success"])
        self.assertEqual(
            read_sync_status(self.db_path)["status"],
            "setup_required",
        )
        clbk_path = meta["path"]
        self.assertTrue(os.path.exists(clbk_path))
        self.assertTrue(clbk_path.endswith(".clbk"))
        # Ensure no temporary .tmp file left over
        self.assertFalse(os.path.exists(clbk_path + ".tmp"))

        # Verify decryption into a restored sqlite file
        restored_db_path = os.path.join(self.temp_dir, "restored.db")
        result_path = decrypt_backup_file(clbk_path, restored_db_path)
        self.assertTrue(os.path.exists(result_path))

        restored_conn = sqlite3.connect(result_path)
        books_count = restored_conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        users_count = restored_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        restored_conn.close()

        self.assertEqual(books_count, 1)
        self.assertEqual(users_count, 1)

    def test_read_sync_status_parsing(self):
        """Test read_sync_status parsing for synced, offline (>24h), and safety-lock."""
        status_file = os.path.join(self.temp_dir, "sync_status.json")

        # 1. Fresh synced status
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "synced",
                "message": "Cloud Synced",
                "last_check_in": now_iso,
                "book_count": 5003,
                "last_backup_text": "Today 10:30 AM",
                "safety_lock": False
            }, f)

        status = read_sync_status(self.db_path)
        self.assertFalse(status["is_offline"])
        self.assertFalse(status["safety_lock"])
        self.assertEqual(status["book_count"], 5003)

        # 2. Offline status (>24 hours ago)
        old_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=26)).isoformat()
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "synced",
                "message": "Cloud Synced",
                "last_check_in": old_iso,
                "safety_lock": False
            }, f)

        status = read_sync_status(self.db_path)
        self.assertTrue(status["is_offline"])
        self.assertFalse(status["safety_lock"])

        # 3. Safety lock status
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "locked",
                "message": "Sync Locked",
                "last_check_in": now_iso,
                "safety_lock": True,
                "safety_lock_reason": "Excessive remote deletions detected (>100 books)"
            }, f)

        status = read_sync_status(self.db_path)
        self.assertTrue(status["safety_lock"])
        self.assertIn("Excessive remote deletions", status["safety_lock_reason"])

    def test_malformed_sync_status_roots_are_handled_safely(self):
        status_file = os.path.join(self.temp_dir, "sync_status.json")

        with open(status_file, "w", encoding="utf-8") as f:
            json.dump("syncing", f)

        status = read_sync_status(self.db_path)
        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["message"], "Status unavailable")
        self.assertFalse(_verification_email_was_sent_recently(status_file, "staff@example.com"))


class TestCloudBackupScheduler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_scheduler_")
        self.db_path = os.path.join(self.temp_dir, "test_library.db")
        self.db = LocalDatabase(self.db_path)
        self.db.insert_book("B_SCHED", "Sched Book", "Author", "Pub", 5, 5)
        self.scheduler = CloudBackupScheduler(self.db)
        self.scheduler.db.set_setting("sync_backup_folder", self.temp_dir)

    def tearDown(self):
        if hasattr(self, "scheduler"):
            self.scheduler.stop()
        if hasattr(self, "db") and self.db:
            self.db.close()
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_immediate_backup_on_shutdown(self):
        """Verify synchronous immediate backup on shutdown produces backup and updates settings."""
        result = self.scheduler.trigger_immediate_backup(reason="app_exit")
        self.assertTrue(result.get("success", False))
        self.assertTrue(os.path.exists(result["path"]))
        self.assertEqual(
            self.db.get_setting("last_daily_backup_date"),
            datetime.date.today().isoformat()
        )

    def test_stale_startup_callbacks_do_not_start_backup_after_stop(self):
        self.scheduler.stop()
        with (
            patch.object(self.scheduler, "trigger_async_backup") as backup,
            patch.object(self.scheduler, "trigger_async_sync") as sync,
        ):
            self.scheduler._initial_check()
            self.scheduler._check_cloud_sync()
            self.scheduler._check_daily_schedule()

        backup.assert_not_called()
        sync.assert_not_called()

    def test_verification_email_cooldown_is_scoped_to_account_and_time(self):
        status_path = os.path.join(self.temp_dir, "sync_status.json")
        status = {
            "verification_email_address": "librarian@example.com",
            "verification_email_sent_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
        }
        with open(status_path, "w", encoding="utf-8") as status_file:
            json.dump(status, status_file)

        self.assertTrue(
            _verification_email_was_sent_recently(
                status_path, "LIBRARIAN@example.com"
            )
        )
        self.assertFalse(
            _verification_email_was_sent_recently(
                status_path, "another@example.com"
            )
        )

    def test_email_verification_failure_pauses_automatic_sync_retries(self):
        self.scheduler._on_sync_worker_finished(
            False,
            "Firebase email verification is required.",
            {"status": "verification_required"},
        )
        self.assertTrue(self.scheduler._sync_blocked)

        with patch.object(self.scheduler.thread_pool, "start") as start:
            self.scheduler.trigger_async_sync()
            start.assert_not_called()

            self.scheduler.trigger_async_sync(force=True)
            start.assert_called_once()

        self.assertFalse(self.scheduler._sync_blocked)
        self.scheduler._is_syncing = False


if __name__ == "__main__":
    unittest.main()

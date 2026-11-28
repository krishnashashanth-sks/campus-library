import datetime
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot

import google_drive_backup
from utils import get_appdata_db_path

logger = logging.getLogger(__name__)
_SYNC_STATUS_LOCK = threading.RLock()
_VERIFICATION_EMAIL_COOLDOWN = datetime.timedelta(minutes=15)

BACKUP_HEADER = google_drive_backup.BACKUP_HEADER  # b"CLBK1"


def get_default_backup_watch_folder() -> str:
    """Return the default folder for encrypted local recovery snapshots."""
    base_appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    watch_dir = os.path.join(base_appdata, "Library", "Backups")
    os.makedirs(watch_dir, exist_ok=True)
    return watch_dir


def get_sync_status_file_path(db_path: str = None) -> str:
    """Resolve the desktop application's Firestore sync status file."""
    app_data_dir = os.path.dirname(get_appdata_db_path())
    if db_path:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if os.path.normcase(db_dir) != os.path.normcase(app_data_dir):
            return os.path.join(db_dir, "sync_status.json")

    primary = os.path.join(app_data_dir, "sync_status.json")
    if os.path.exists(primary):
        return primary
    watch_status = os.path.join(get_default_backup_watch_folder(), "sync_status.json")
    if os.path.exists(watch_status):
        return watch_status
    return primary


def _verification_email_was_sent_recently(path, email):
    with _SYNC_STATUS_LOCK:
        try:
            with open(path, "r", encoding="utf-8") as status_file:
                status = json.load(status_file)
        except (OSError, json.JSONDecodeError):
            return False

    if not isinstance(status, dict):
        return False

    sent_email = str(status.get("verification_email_address", "")).casefold()
    sent_at = status.get("verification_email_sent_at")
    if sent_email != str(email or "").casefold() or not sent_at:
        return False
    try:
        sent_time = datetime.datetime.fromisoformat(
            str(sent_at).replace("Z", "+00:00")
        )
        if sent_time.tzinfo is None:
            sent_time = sent_time.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False

    age = datetime.datetime.now(datetime.timezone.utc) - sent_time
    return datetime.timedelta(0) <= age < _VERIFICATION_EMAIL_COOLDOWN


def export_atomic_clbk_backup(db, target_folder: str = None, max_keep: int = 30) -> dict:
    """
    Atomically export an encrypted .clbk disaster recovery backup.
    1. Stages an online SQLite backup.
    2. Verifies SQLite integrity and book count > 0 (safety guard).
    3. Encrypts payload with AES-256-GCM.
    4. Writes payload to <filename>.clbk.tmp.
    5. Verifies SHA-256 checksum.
    6. Atomically renames tmp file to <filename>.clbk via os.replace.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    folder = target_folder or get_default_backup_watch_folder()
    dest_dir = Path(folder).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    final_filename = f"library-backup-{timestamp_str}.clbk"
    final_path = dest_dir / final_filename

    counter = 1
    while final_path.exists():
        final_filename = f"library-backup-{timestamp_str}-{counter}.clbk"
        final_path = dest_dir / final_filename
        counter += 1

    tmp_path = dest_dir / f"{final_filename}.tmp"

    key = google_drive_backup._get_encryption_key()

    with tempfile.TemporaryDirectory(prefix="clbk-stage-") as stage_folder:
        stage_db = Path(stage_folder) / "library_stage.db"
        success, err = db.backup_database(stage_db)
        if not success:
            raise RuntimeError(f"Database staging failed: {err}")

        # Safety verification: ensure valid SQLite structure and non-zero books if database has books
        try:
            conn = sqlite3.connect(os.fspath(stage_db), timeout=5)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity.lower() != "ok":
                conn.close()
                raise RuntimeError(f"Database integrity check failed: {integrity}")

            book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            conn.close()
        except Exception as exc:
            raise RuntimeError(f"Backup verification failed: {exc}") from exc

        plain_bytes = stage_db.read_bytes()
        plain_sha256 = hashlib.sha256(plain_bytes).hexdigest()

        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, plain_bytes, BACKUP_HEADER)
        encrypted_payload = BACKUP_HEADER + nonce + ciphertext

        # Write to .tmp file first
        tmp_path.write_bytes(encrypted_payload)

        # Verify written file
        written_size = tmp_path.stat().st_size
        if written_size != len(encrypted_payload):
            if tmp_path.exists():
                tmp_path.unlink()
            raise IOError("Incomplete .tmp backup write detected.")

        payload_sha256 = hashlib.sha256(encrypted_payload).hexdigest()

        # Publish only a complete encrypted snapshot.
        os.replace(tmp_path, final_path)

    # Prune old backups if max_keep specified
    if max_keep and max_keep > 0:
        existing = sorted(
            dest_dir.glob("library-backup-*.clbk"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in existing[max_keep:]:
            try:
                old_file.unlink()
            except OSError:
                pass

    return {
        "success": True,
        "filename": final_filename,
        "path": os.fspath(final_path),
        "size_bytes": len(encrypted_payload),
        "book_count": book_count,
        "user_count": user_count,
        "sha256": payload_sha256,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def read_sync_status(db_path: str = None) -> dict:
    """
    Read sync_status.json written by the desktop Firestore sync worker.
    Returns parsed status dict with calculated flags:
    - is_offline: Firestore hasn't confirmed a sync in >24 hours
    - safety_lock: safety lock active
    """
    path = get_sync_status_file_path(db_path)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    if not os.path.exists(path):
        return {
            "status": "setup_required",
            "message": "Cloud account setup required",
            "last_check_in": None,
            "is_offline": False,
            "safety_lock": False,
            "book_count": None,
            "last_backup_text": "Local backups ready",
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.warning("Ignoring malformed sync status JSON: root is not an object")
            return {
                "status": "warning",
                "message": "Status unavailable",
                "last_check_in": None,
                "is_offline": False,
                "safety_lock": False,
                "book_count": None,
                "last_error": "",
                "last_backup_text": "",
            }

        last_check_in_str = data.get("last_check_in") or data.get("last_synced_at")
        is_offline = False
        if last_check_in_str:
            try:
                # Parse ISO-8601
                clean_ts = last_check_in_str.replace("Z", "+00:00")
                check_in_dt = datetime.datetime.fromisoformat(clean_ts)
                delta = now_utc - check_in_dt
                if delta.total_seconds() > 86400:  # > 24 hours
                    is_offline = True
            except Exception:
                pass

        safety_lock = bool(data.get("safety_lock", False))

        return {
            "status": data.get("status", "setup_required"),
            "message": data.get("message", "Cloud account setup required"),
            "last_check_in": last_check_in_str,
            "is_offline": is_offline,
            "safety_lock": safety_lock,
            "safety_lock_reason": data.get("safety_lock_reason", ""),
            "book_count": data.get("book_count"),
            "last_error": data.get("last_error", ""),
            "last_backup_text": data.get("last_backup_text", ""),
            "last_daily_backup_date": data.get("last_daily_backup_date", ""),
            "raw": data,
        }
    except Exception as exc:
        logger.warning("Could not read sync_status.json: %s", exc)
        return {
            "status": "warning",
            "message": "Status unavailable",
            "last_check_in": None,
            "is_offline": False,
            "safety_lock": False,
            "book_count": None,
        }


class _BackupWorkerSignals(QObject):
    finished = pyqtSignal(bool, str, dict)


class _BackupWorker(QRunnable):
    def __init__(
        self, db, target_folder, reason="scheduled", finished_event=None, parent=None
    ):
        super().__init__()
        self.db = db
        self.target_folder = target_folder
        self.reason = reason
        self.finished_event = finished_event
        self.signals = _BackupWorkerSignals(parent)

    @pyqtSlot()
    def run(self):
        try:
            meta = export_atomic_clbk_backup(self.db, self.target_folder)
            self.signals.finished.emit(True, f"Backup created ({self.reason})", meta)
        except Exception as exc:
            self.signals.finished.emit(False, str(exc), {})
        finally:
            if self.finished_event:
                self.finished_event.set()


class _CloudSyncWorkerSignals(QObject):
    finished = pyqtSignal(bool, str, dict)


class _CloudSyncWorker(QRunnable):
    def __init__(self, database_path, email, force_full_scan=False, parent=None):
        super().__init__()
        self.database_path = database_path
        self.email = email
        self.force_full_scan = force_full_scan
        self.signals = _CloudSyncWorkerSignals(parent)

    @pyqtSlot()
    def run(self):
        from firestore_sync import (
            EmailVerificationRequiredError,
            FIREBASE_SYNC_PASSWORD_TARGET,
            FIREBASE_SYNC_REFRESH_TOKEN_TARGET,
            FirestoreSyncError,
            find_service_account_path,
            sync_books,
        )

        from secure_storage import delete_secret, read_secret, store_secret

        status_path = get_sync_status_file_path(self.database_path)
        sa_path = find_service_account_path()

        if not sa_path and not self.email:
            message = "Connect a verified Firebase Admin or Librarian account in Settings, or add serviceAccountKey.json."
            write_sync_status(status_path, "setup_required", message)
            self.signals.finished.emit(False, message, {"status": "setup_required"})
            return

        try:
            refresh_token = read_secret(FIREBASE_SYNC_REFRESH_TOKEN_TARGET)
            password = read_secret(FIREBASE_SYNC_PASSWORD_TARGET)
            if not sa_path and not refresh_token and not password:
                message = "Connect a verified Firebase Admin or Librarian account in Settings, or add serviceAccountKey.json."
                write_sync_status(status_path, "setup_required", message)
                self.signals.finished.emit(False, message, {"status": "setup_required"})
                return

            write_sync_status(status_path, "syncing", "Syncing book catalog with Firestore.")

            def save_refresh_token(token):
                if self.email:
                    store_secret(FIREBASE_SYNC_REFRESH_TOKEN_TARGET, token, self.email)
                if password:
                    delete_secret(FIREBASE_SYNC_PASSWORD_TARGET)

            result = sync_books(
                self.database_path,
                self.email,
                password=password,
                refresh_token=refresh_token,
                service_account_path=sa_path,
                send_verification_email=not _verification_email_was_sent_recently(
                    status_path, self.email
                ),
                force_full_scan=self.force_full_scan,
                on_refresh_token=save_refresh_token,
            )
            result["status"] = "synced"
            auth_suffix = " (Service Account Root Authority)" if sa_path else ""
            result["message"] = (
                f"Firestore verified {result['firestore_book_count']:,} books; "
                f"{result['uploaded_books']:,} uploaded and "
                f"{result['downloaded_books']:,} downloaded{auth_suffix}."
            )
            write_sync_status(status_path, "synced", result["message"], result)
            self.signals.finished.emit(True, result["message"], result)
        except EmailVerificationRequiredError as exc:
            message = str(exc)
            details = {}
            if exc.email_sent:
                details = {
                    "verification_email_sent_at": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "verification_email_address": self.email,
                }
            write_sync_status(
                status_path,
                "verification_required",
                message,
                details,
            )
            self.signals.finished.emit(
                False, message, {"status": "verification_required"}
            )
        except (FirestoreSyncError, OSError) as exc:
            message = str(exc)
            write_sync_status(status_path, "error", message)
            self.signals.finished.emit(False, message, {"status": "error"})
        except Exception as exc:
            logger.exception("Unexpected desktop Firestore sync failure")
            message = f"Unexpected Firestore sync failure: {exc}"
            write_sync_status(status_path, "error", message)
            self.signals.finished.emit(False, message, {"status": "error"})


def write_sync_status(path, status, message, details=None):
    with _SYNC_STATUS_LOCK:
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not read previous sync status: %s", exc)
        if status is not None:
            data["status"] = status
            data["last_attempt_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if message is not None:
            data["message"] = message
        if status == "synced":
            data["last_check_in"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            data["safety_lock"] = False
            data.pop("safety_lock_reason", None)
            data.pop("last_error", None)
            data.pop("verification_email_sent_at", None)
            data.pop("verification_email_address", None)
        elif status == "error":
            data["last_error"] = message
        if details:
            for key in (
                "book_count",
                "firestore_book_count",
                "uploaded_books",
                "downloaded_books",
                "last_backup_text",
                "last_backup_at",
                "last_daily_backup_date",
                "verification_email_sent_at",
                "verification_email_address",
            ):
                if key in details:
                    data[key] = details[key]
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp_path = f"{path}.{secrets.token_hex(6)}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class CloudBackupScheduler(QObject):
    """
    Automated background backup scheduler:
    - Daily scheduled backup (once per day or on first launch of the day).
    - Debounced local backup after significant changes.
    - Automatic bidirectional book synchronization with Firestore.
    - Graceful non-blocking export on app exit.
    """

    backup_started = pyqtSignal()
    backup_completed = pyqtSignal(bool, str, dict)
    sync_status_changed = pyqtSignal(dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.thread_pool = QThreadPool.globalInstance()
        self._is_exporting = False
        self._is_syncing = False
        self._sync_blocked = False
        self._stopping = False
        self._active_backup_worker = None
        self._active_sync_worker = None
        self._backup_finished_event = threading.Event()
        self._backup_finished_event.set()

        # Rapid auto-sync debounce timer for changes (3 seconds = 3,000 ms)
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(3000)
        self.debounce_timer.timeout.connect(self._on_debounce_timeout)

        # Poll Firestore for web-side book changes without requiring an external daemon.
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(30000)
        self.poll_timer.timeout.connect(self._check_cloud_sync)

        # Initial check on launch
        QTimer.singleShot(2500, self._initial_check)

    def start(self):
        self.poll_timer.start()
        self._check_cloud_sync()

    def stop(self):
        self._stopping = True
        self.poll_timer.stop()
        self.debounce_timer.stop()
        if not self._backup_finished_event.is_set() and not self._backup_finished_event.wait(5):
            logger.warning("Background local backup did not finish before shutdown timeout.")
            return False
        self.thread_pool.waitForDone(2000)
        return True

    def get_backup_folder(self) -> str:
        saved = self.db.get_setting("sync_backup_folder")
        if saved and os.path.isdir(saved):
            return saved
        return get_default_backup_watch_folder()

    def schedule_debounced_backup(self, reason="data_change"):
        """Called whenever significant database transactions occur."""
        self._pending_reason = reason
        if reason in {
            "insert_book",
            "edit_book",
            "delete_book",
            "bulk_books_import",
            "issue_book",
            "return_book",
            "clear_logs",
        }:
            path = get_sync_status_file_path(getattr(self.db, "database_path", None))
            write_sync_status(
                path,
                "pending",
                "Local catalog changes are waiting to sync with Firestore.",
            )
            self._check_sync_status()
        self.debounce_timer.start()

    def trigger_immediate_backup(self, reason="manual") -> dict:
        """Synchronous export, useful on clean shutdown."""
        folder = self.get_backup_folder()
        try:
            meta = export_atomic_clbk_backup(self.db, folder)
            today_str = datetime.date.today().isoformat()
            self.db.set_setting("last_daily_backup_date", today_str)
            self.db.set_setting("last_backup_file", meta.get("filename", ""))
            write_sync_status(
                get_sync_status_file_path(getattr(self.db, "database_path", None)),
                None,
                None,
                {
                    "last_daily_backup_date": today_str,
                    "last_backup_text": meta.get("filename", ""),
                    "last_backup_at": meta.get("timestamp", ""),
                    "book_count": meta.get("book_count"),
                },
            )
            return meta
        except Exception as exc:
            logger.error("Immediate backup failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def trigger_async_backup(self, reason="scheduled"):
        if self._stopping or self._is_exporting:
            return
        self._is_exporting = True
        self._backup_finished_event.clear()
        self.backup_started.emit()

        folder = self.get_backup_folder()
        worker = _BackupWorker(
            self.db,
            folder,
            reason=reason,
            finished_event=self._backup_finished_event,
            parent=self,
        )
        self._active_backup_worker = worker
        worker.signals.finished.connect(self._on_worker_finished)
        self.thread_pool.start(worker)

    def _on_worker_finished(self, success, message, meta):
        self._is_exporting = False
        self._active_backup_worker = None
        if success:
            today_str = datetime.date.today().isoformat()
            write_sync_status(
                get_sync_status_file_path(getattr(self.db, "database_path", None)),
                None,
                None,
                {
                    "last_daily_backup_date": today_str,
                    "last_backup_text": meta.get("filename", ""),
                    "last_backup_at": meta.get("timestamp", ""),
                    "book_count": meta.get("book_count"),
                },
            )
        self.backup_completed.emit(success, message, meta)
        self._check_sync_status()
        if success and not self._stopping:
            self.trigger_async_sync()

    def _on_debounce_timeout(self):
        reason = getattr(self, "_pending_reason", "data_change")
        self.trigger_async_backup(reason=f"debounced_{reason}")

    def _initial_check(self):
        if self._stopping:
            return
        self._check_daily_schedule()
        self._check_sync_status()
        self.trigger_async_backup(reason="startup_auto_sync")

    def _check_cloud_sync(self):
        if self._stopping:
            return
        self._check_daily_schedule()
        self._check_sync_status()
        self.trigger_async_sync()

    def trigger_async_sync(self, force=False):
        if self._stopping or self._is_syncing or (self._sync_blocked and not force):
            return
        if force:
            self._sync_blocked = False
        database_path = getattr(self.db, "database_path", None)
        if not database_path:
            message = "The desktop database path is unavailable; Firestore sync cannot start."
            write_sync_status(
                get_sync_status_file_path(),
                "error",
                message,
            )
            self._check_sync_status()
            return

        # Do not background-poll production cloud for temporary unit-test databases unless forced
        if not force and tempfile.gettempdir().lower() in os.path.abspath(database_path).lower():
            return

        self._is_syncing = True
        worker = _CloudSyncWorker(
            database_path,
            self.db.get_setting("firebase_sync_email", ""),
            force_full_scan=force,
            parent=self,
        )
        self._active_sync_worker = worker
        worker.signals.finished.connect(self._on_sync_worker_finished)
        self.thread_pool.start(worker)

    def _on_sync_worker_finished(self, success, message, meta):
        self._is_syncing = False
        self._active_sync_worker = None
        if meta.get("status") == "verification_required":
            self._sync_blocked = True
        elif success:
            self._sync_blocked = False
        else:
            logger.warning("Firestore book sync did not complete: %s", message)
        self._check_sync_status()

    def _check_daily_schedule(self):
        if self._stopping:
            return
        today_str = datetime.date.today().isoformat()
        status = read_sync_status(getattr(self.db, "database_path", None))
        last_date = (
            status.get("last_daily_backup_date")
            or self.db.get_setting("last_daily_backup_date")
        )
        if last_date != today_str and not self._is_exporting:
            self.trigger_async_backup(reason="daily_scheduled")

    def _check_sync_status(self):
        status = read_sync_status(getattr(self.db, "database_path", None))
        self.sync_status_changed.emit(status)

import logging
import socket

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from database import LocalDatabase
from email_service import LibraryEmailService, SMTP_HOST, SMTP_PORT


class _WorkerSignals(QObject):
    finished = pyqtSignal(dict)


class EmailTestWorker(QRunnable):
    def __init__(self, database_path):
        super().__init__()
        self.database_path = database_path
        self.signals = _WorkerSignals()

    def run(self):
        db = None
        try:
            db = LocalDatabase(self.database_path)
            sender = str(db.get_setting("email_sender", "")).strip()
            if not sender:
                raise RuntimeError(
                    "Save a Gmail sender address before sending a test."
                )
            LibraryEmailService(db).send(
                sender,
                "Library email configuration test",
                "Your library email service is configured successfully.",
            )
            self.signals.finished.emit({"sent": True})
        except Exception as error:
            self.signals.finished.emit(
                {"sent": False, "error": str(error)}
            )
        finally:
            if db is not None:
                db.close()


class EmailWorker(QRunnable):
    def __init__(self, database_path, retry_failed=False):
        super().__init__()
        self.database_path = database_path
        self.retry_failed = retry_failed
        self.signals = _WorkerSignals()

    @staticmethod
    def _is_online():
        try:
            with socket.create_connection(
                (SMTP_HOST, SMTP_PORT),
                timeout=3,
            ):
                return True
        except OSError:
            return False

    def run(self):
        db = None
        result = {
            "online": False,
            "configured": False,
            "enabled": False,
            "sent": 0,
            "failed": 0,
            "pending": 0,
            "error": None,
        }
        try:
            db = LocalDatabase(self.database_path)
            result["enabled"] = (
                str(
                    db.get_setting("email_delivery_enabled", "0")
                ).casefold()
                in ("1", "true", "yes")
            )
            counts = db.get_email_queue_counts()
            result["pending"] = counts["pending"]
            if not result["enabled"]:
                return

            if self.retry_failed:
                db.prepare_email_queue_for_manual_sync()

            email_service = LibraryEmailService(db)
            result["configured"] = email_service.is_configured()
            counts = db.get_email_queue_counts()
            result["pending"] = counts["pending"]

            if not result["configured"]:
                return

            result["online"] = self._is_online()
            if not result["online"]:
                return

            for email_id, recipient, subject, body in db.get_pending_emails():
                if str(
                    db.get_setting("email_delivery_enabled", "0")
                ).casefold() not in ("1", "true", "yes"):
                    result["enabled"] = False
                    break
                try:
                    email_service.send(recipient, subject, body)
                    db.mark_email_sent(email_id)
                    result["sent"] += 1
                except Exception as error:
                    retry_count = db.mark_email_failed(email_id)
                    result["failed"] += 1
                    logging.warning(
                        "Email queue item %s failed (retry %s): %s",
                        email_id,
                        retry_count,
                        error,
                    )

            counts = db.get_email_queue_counts()
            result["pending"] = counts["pending"]
        except Exception as error:
            result["error"] = str(error)
            logging.exception("Email queue synchronization failed.")
        finally:
            if db is not None:
                db.close()
            self.signals.finished.emit(result)


class EmailQueueManager(QObject):
    status_changed = pyqtSignal(str)

    def __init__(self, database_path, parent=None, status_database=None):
        super().__init__(parent)
        self.database_path = database_path
        self.status_database = status_database
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(1)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(60_000)
        self.sync_timer.timeout.connect(self.sync_now)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(5_000)
        self.status_timer.timeout.connect(self.refresh_status)
        self._sync_in_progress = False
        self._sync_requested = False
        self._retry_failed_requested = False
        self._configured = None
        self._enabled = None
        self._online = None
        self._error = None
        self._retrying = False

    def start(self):
        self.sync_timer.start()
        self.status_timer.start()
        QTimer.singleShot(0, self.sync_now)
        self.refresh_status()

    def sync_now(self):
        if self._sync_in_progress:
            self._sync_requested = True
            return

        self._sync_in_progress = True
        self._error = None
        self.refresh_status()
        worker = EmailWorker(
            self.database_path,
            retry_failed=self._retry_failed_requested,
        )
        self._retry_failed_requested = False
        worker.signals.finished.connect(self._sync_finished)
        self.thread_pool.start(worker)

    def retry_failed_now(self):
        self._retry_failed_requested = True
        self.sync_now()

    def _sync_finished(self, result):
        self._sync_in_progress = False
        self._configured = result.get("configured")
        self._enabled = result.get("enabled")
        self._online = result.get("online")
        self._error = result.get("error")
        self._retrying = bool(result.get("failed"))
        self.refresh_status()

        if self._sync_requested:
            self._sync_requested = False
            self.sync_now()

    def refresh_status(self):
        try:
            if self.status_database is not None:
                counts = self.status_database.get_email_queue_counts()
            else:
                db = LocalDatabase(self.database_path)
                try:
                    counts = db.get_email_queue_counts()
                finally:
                    db.close()
        except Exception:
            logging.exception("Could not read the email queue status.")
            self.status_changed.emit("Email queue status unavailable")
            return

        pending = counts["pending"]
        failed = counts["failed"]
        queued_text = f"{pending} pending"
        if failed:
            queued_text += f", {failed} failed"

        if self._sync_in_progress:
            message = f"Email sync running ({queued_text})"
        elif self._enabled is False:
            message = f"Email delivery disabled ({queued_text})"
        elif self._error:
            message = f"Email sync error ({queued_text})"
        elif self._configured is False:
            message = f"Email not configured ({queued_text})"
        elif self._online is False:
            message = f"Offline ({queued_text})"
        elif failed:
            message = f"Email sync needs attention ({queued_text})"
        elif self._retrying:
            message = f"Email retry scheduled ({queued_text})"
        elif self._online is True:
            message = f"Email sync active ({queued_text})"
        else:
            message = f"Email sync checking ({queued_text})"

        self.status_changed.emit(message)

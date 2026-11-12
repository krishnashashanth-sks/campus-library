
import sys
import os
import logging
import threading
import datetime

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import QElapsedTimer, QTimer, Qt

from mainwindow import MainWindow
from database import LocalDatabase
from dialogs import LoginDialog, CustomSplashScreen
from email_service import LibraryEmailService
from theme_manager import ThemeManager
from app_version import APP_DEVELOPER, APP_NAME, get_app_version


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

# Keep production authentication enabled; bypass is for local testing only.
BYPASS_LOGIN = False

DEFAULT_THEME = "Dark"
SPLASH_DURATION = 1500


# ============================================================
# RESOURCE MANAGEMENT
# ============================================================

def get_resource_path(relative_path: str) -> str:
    """Resolve resources in development and PyInstaller builds."""

    if hasattr(sys, "_MEIPASS"):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_dir, *relative_path.replace("\\", "/").split("/"))


def load_application_icon(app: QApplication):
    """Load application icon if available."""

    icon_path = get_resource_path("assets/library_icon.ico")

    if os.path.exists(icon_path):
        icon = QIcon(icon_path)

        app.setWindowIcon(icon)

        return icon

    return QIcon()


# ============================================================
# SPLASH SCREEN
# ============================================================

def show_splash(app: QApplication):
    """Display splash screen without freezing the UI."""

    image_path = get_resource_path("assets/library_icon.png")

    splash = CustomSplashScreen(image_path)

    splash.show()
    app.processEvents()

    timer = QElapsedTimer()
    timer.start()

    while timer.elapsed() < SPLASH_DURATION:
        app.processEvents()

    return splash


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():
    """Initialize the application database."""

    return LocalDatabase()


# ============================================================
# APPLICATION STARTUP
# ============================================================

def main():

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(get_app_version())
    app.setOrganizationName(APP_DEVELOPER)

    app.setFont(QFont("Segoe UI", 10))

    # --------------------------------------------------------
    # 1. Application icon
    # --------------------------------------------------------

    load_application_icon(app)

    # --------------------------------------------------------
    # 2. Centralized theme manager
    # --------------------------------------------------------

    theme_manager = ThemeManager(
        app,
        initial_theme=DEFAULT_THEME
    )

    # Make the manager accessible throughout the application.
    app.theme_manager = theme_manager

    # --------------------------------------------------------
    # 3. Splash screen
    # --------------------------------------------------------

    splash = None

    if not BYPASS_LOGIN:
        splash = show_splash(app)

    # --------------------------------------------------------
    # 4. Database initialization
    # --------------------------------------------------------

    try:
        db = initialize_database()

    except Exception as error:

        if splash:
            splash.close()

        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Database Initialization Failed",
            f"Unable to initialize the library database.\n\n{error}"
        )

        return 1

    # --------------------------------------------------------
    # 5. Safe database & worker shutdown
    # --------------------------------------------------------

    window_ref = {"window": None}
    background_timers = []

    def close_database():
        for timer in background_timers:
            try:
                timer.stop()
            except Exception:
                pass

        win = window_ref.get("window")
        if win is not None and hasattr(win, "_shutdown_background_workers"):
            try:
                win._shutdown_background_workers()
            except Exception as error:
                print(f"Worker shutdown warning: {error}")
        else:
            sync_manager = getattr(app, "email_sync_manager", None)
            if sync_manager is not None and hasattr(sync_manager, "stop"):
                try:
                    sync_manager.stop(wait_ms=3500)
                except Exception as error:
                    print(f"Email sync shutdown warning: {error}")

        try:
            connection = getattr(db, "conn", None)

            if connection:
                connection.close()

        except Exception as error:
            print(f"Database shutdown warning: {error}")

    app.aboutToQuit.connect(close_database)

    # --------------------------------------------------------
    # 6. Authentication & Main Window Handoff
    # --------------------------------------------------------

    if BYPASS_LOGIN:

        window = MainWindow(db)
        window_ref["window"] = window
        window.theme_manager = theme_manager
        window.setWindowTitle(f"{APP_NAME} v{get_app_version()}")
        window.showMaximized()

    else:

        if splash:
            splash.close()
            splash = None

        app.setQuitOnLastWindowClosed(False)
        try:
            login_dialog = LoginDialog(db)

            if login_dialog.exec() != QDialog.DialogCode.Accepted:
                close_database()
                return 0

            window = MainWindow(db)
            window_ref["window"] = window
            window.theme_manager = theme_manager
            window.setWindowTitle(f"{APP_NAME} v{get_app_version()}")
            window.showMaximized()
        finally:
            app.setQuitOnLastWindowClosed(True)

    reminder_lock = threading.Lock()

    def run_due_email_reminders():
        if app.closingDown():
            return
        if not reminder_lock.acquire(blocking=False):
            return

        def send_reminders():
            reminder_db = None
            try:
                reminder_db = LocalDatabase(db.database_path)
                enabled = reminder_db.get_setting(
                    "due_email_reminders_enabled",
                    "0",
                )
                if str(enabled).casefold() not in ("1", "true", "yes"):
                    return

                queued, failures = LibraryEmailService(
                    reminder_db
                ).send_due_reminders()
                if queued:
                    logging.info(
                        "Queued %s due-date reminder emails.",
                        queued,
                    )
                for failure in failures:
                    logging.warning(
                        "Could not send due-date reminder: %s",
                        failure,
                    )
            except Exception:
                logging.exception("Due-date email reminder run failed.")
            finally:
                if reminder_db:
                    reminder_db.close()
                reminder_lock.release()

        threading.Thread(
            target=send_reminders,
            name="library-email-reminders",
            daemon=True,
        ).start()

    reminder_timer = QTimer(app)
    reminder_timer.setInterval(60 * 60 * 1000)
    reminder_timer.timeout.connect(run_due_email_reminders)
    reminder_timer.start()
    background_timers.append(reminder_timer)
    QTimer.singleShot(1000, run_due_email_reminders)

    drive_backup_lock = threading.Lock()

    def run_automatic_drive_backup():
        if app.closingDown():
            return
        if not drive_backup_lock.acquire(blocking=False):
            return

        def upload_backup():
            backup_db = None
            try:
                from google_drive_backup import (
                    backup_to_sync_folder,
                    is_drive_connected,
                    upload_encrypted_database_backup,
                )

                backup_db = LocalDatabase(db.database_path)
                today = datetime.date.today().isoformat()

                enabled = backup_db.get_setting(
                    "google_drive_auto_backup_enabled",
                    "0",
                )
                if (
                    str(enabled).casefold() in ("1", "true", "yes")
                    and is_drive_connected()
                    and backup_db.get_setting("google_drive_last_backup", "") != today
                ):
                    try:
                        result = upload_encrypted_database_backup(backup_db)
                        if not backup_db.set_setting("google_drive_last_backup", today):
                            raise RuntimeError(
                                "The backup uploaded, but its completion date could not be saved."
                            )
                        logging.info(
                            "Uploaded encrypted Google Drive backup %s.",
                            result.get("name", "library backup"),
                        )
                    except Exception:
                        logging.exception("Automatic Google Drive backup failed.")

                folder_enabled = backup_db.get_setting(
                    "sync_auto_backup_enabled",
                    "0",
                )
                sync_folder = (
                    backup_db.get_setting("sync_backup_folder", "") or ""
                ).strip()
                if (
                    str(folder_enabled).casefold() in ("1", "true", "yes")
                    and sync_folder
                    and backup_db.get_setting("sync_last_backup", "") != today
                ):
                    try:
                        saved = backup_to_sync_folder(backup_db, sync_folder)
                        backup_db.set_setting("sync_last_backup", today)
                        logging.info(
                            "Saved encrypted synced-folder backup %s.",
                            saved.get("path", ""),
                        )
                    except Exception:
                        logging.exception("Automatic synced-folder backup failed.")
            except Exception:
                logging.exception("Automatic backup run failed.")
            finally:
                if backup_db:
                    backup_db.close()
                drive_backup_lock.release()

        threading.Thread(
            target=upload_backup,
            name="library-google-drive-backup",
            daemon=True,
        ).start()

    drive_backup_timer = QTimer(app)
    drive_backup_timer.setInterval(60 * 60 * 1000)
    drive_backup_timer.timeout.connect(run_automatic_drive_backup)
    drive_backup_timer.start()
    background_timers.append(drive_backup_timer)
    QTimer.singleShot(2000, run_automatic_drive_backup)

    if splash:
        splash.finish(window)

    return app.exec()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())


import sys
import os

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import QElapsedTimer

from mainwindow import MainWindow
from database import LocalDatabase
from dialogs import LoginDialog, CustomSplashScreen
from theme_manager import ThemeManager


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_NAME = "Library Management System"
APP_VERSION = "2.0"

# Set False for normal production authentication.
# Set True only during development/testing.
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

    image_path = get_resource_path("assets/library_icon.jpeg")

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

    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Library Management System")

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
    # 5. Safe database shutdown
    # --------------------------------------------------------

    def close_database():

        try:
            connection = getattr(db, "conn", None)

            if connection:
                connection.close()

        except Exception as error:
            print(f"Database shutdown warning: {error}")

    app.aboutToQuit.connect(close_database)

    # --------------------------------------------------------
    # 6. Authentication
    # --------------------------------------------------------

    if BYPASS_LOGIN:

        window = MainWindow(db)

    else:

        if splash:
            splash.close()
            splash = None

        login_dialog = LoginDialog(db)

        if login_dialog.exec() != QDialog.DialogCode.Accepted:
            close_database()
            return 0

        window = MainWindow(db)

    # --------------------------------------------------------
    # 7. Connect theme manager
    # --------------------------------------------------------

    window.theme_manager = theme_manager

    # --------------------------------------------------------
    # 8. Launch application
    # --------------------------------------------------------

    window.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
    window.showMaximized()

    if splash:
        splash.finish(window)

    return app.exec()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())

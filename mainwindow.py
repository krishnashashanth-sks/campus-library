
import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QStackedWidget,
    QPushButton,
    QLabel,
    QSizePolicy,
    QMessageBox,
    QApplication
)

from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup
)

from pages.bookcatalog_view import CatalogView
from pages.circulation_view import CirculationView
from pages.reports_view import ReportsView
from pages.usermanagement_view import UserManagementView
from pages.settings_view import SettingsView
from pages.dashboard_view import DashboardView


class MainWindow(QMainWindow):

    def __init__(self, db):

        super().__init__()

        self.db = db
        self.sidebar_expanded = True
        self.anim_group = None

        app = QApplication.instance()

        self.theme_manager = getattr(
            app,
            "theme_manager",
            None
        )

        self.setWindowTitle("Library Management System")
        self.setMinimumSize(1024, 640)

        self.load_saved_theme()

        self.initialize_window_icon()
        self.initialize_ui()

        if self.theme_manager:
            self.theme_manager.themeChanged.connect(
                self.apply_shell_theme
            )

        self.apply_shell_theme()

        self.switch_page(0)

    # ========================================================
    # THEME INTEGRATION
    # ========================================================

    def load_saved_theme(self):

        try:

            saved_theme = self.db.get_setting(
                "theme_mode",
                "Dark"
            )

            legacy_themes = {
                "Dark Slate (Default)": "Dark",
                "Classic Dark": "Dark",
                "Light Modern": "Light"
            }

            saved_theme = legacy_themes.get(
                saved_theme,
                saved_theme
            )

            if saved_theme not in ("Dark", "Light", "System"):
                saved_theme = "Dark"

            if self.theme_manager:
                self.theme_manager.set_theme(saved_theme)

        except Exception as error:

            print(f"Theme initialization warning: {error}")

    def apply_shell_theme(self, active_theme=None):
        """Apply theme-specific colors to the main window shell."""

        if not self.theme_manager:
            return

        active_theme = (
            active_theme
            or self.theme_manager.get_active_theme()
        )

        colors = self.theme_manager.COLORS[active_theme]

        self.setStyleSheet(f"""
            QWidget#MainCentralWidget {{
                background-color: {colors["window"]};
            }}

            QFrame#TopBar {{
                background-color: {colors["surface"]};
                border-bottom: 1px solid {colors["border"]};
            }}

            QFrame#SideBar {{
                background-color: {colors["surface"]};
                border-right: 1px solid {colors["border"]};
            }}

            QPushButton#SidebarToggle {{
                background-color: {colors["input"]};
                color: {colors["text"]};
                border: 1px solid {colors["border"]};
                border-radius: 8px;
                font-size: 18px;
            }}

            QPushButton#SidebarToggle:hover {{
                background-color: {colors["surface_alt"]};
                border-color: {colors["primary"]};
            }}

            QPushButton#NavigationButton {{
                background-color: transparent;
                color: {colors["muted"]};
                border: 1px solid transparent;
                text-align: left;
                padding-left: 16px;
                font-size: 14px;
                font-weight: 600;
                min-height: 44px;
                margin: 3px 12px;
                border-radius: 8px;
            }}

            QPushButton#NavigationButton:hover {{
                background-color: {colors["surface_alt"]};
                color: {colors["text"]};
            }}

            QPushButton#NavigationButton:checked {{
                background-color: {colors["primary"]};
                color: #FFFFFF;
                border: 1px solid {colors["primary_hover"]};
            }}

            QPushButton#ExitButton {{
                background-color: rgba(239, 68, 68, 0.10);
                color: #EF4444;
                text-align: left;
                padding-left: 16px;
                min-height: 44px;
                margin: 4px 12px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
                border: 1px solid rgba(239, 68, 68, 0.25);
            }}

            QPushButton#ExitButton:hover {{
                background-color: #DC2626;
                color: #FFFFFF;
                border-color: #DC2626;
            }}

            QLabel#MainTitle {{
                color: {colors["text"]};
                border: none;
                background: transparent;
            }}

            QLabel#SystemStatusBadge {{
                background-color: rgba(16, 185, 129, 0.12);
                color: #10B981;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 14px;
                border: 1px solid rgba(16, 185, 129, 0.3);
            }}
        """)

    # ========================================================
    # RESOURCE MANAGEMENT
    # ========================================================

    @staticmethod
    def get_asset_path(relative_path: str) -> str:

        if hasattr(sys, "_MEIPASS"):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(
                os.path.abspath(__file__)
            )

        return os.path.join(
            base_dir,
            *relative_path.replace("\\", "/").split("/")
        )

    def initialize_window_icon(self):

        icon_path = self.get_asset_path(
            "assets/library_icon.ico"
        )

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ========================================================
    # MAIN USER INTERFACE
    # ========================================================

    def initialize_ui(self):

        main_widget = QWidget()
        main_widget.setObjectName("MainCentralWidget")

        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.create_topbar(main_layout)
        self.create_content_area(main_layout)

    # ========================================================
    # TOPBAR
    # ========================================================

    def create_topbar(self, parent_layout):

        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(68)

        top_layout = QHBoxLayout(topbar)

        top_layout.setContentsMargins(16, 0, 24, 0)
        top_layout.setSpacing(14)

        self.toggle_btn = QPushButton("☰")

        self.toggle_btn.setObjectName("SidebarToggle")
        self.toggle_btn.setFixedSize(42, 42)

        self.toggle_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.toggle_btn.setToolTip(
            "Toggle Navigation Sidebar"
        )

        self.toggle_btn.clicked.connect(
            self.toggle_sidebar
        )

        top_layout.addWidget(self.toggle_btn)

        title_label = QLabel(
            "Library Management System"
        )

        title_label.setObjectName("MainTitle")

        title_label.setFont(
            QFont("Segoe UI", 16, QFont.Weight.Bold)
        )

        top_layout.addWidget(title_label)

        top_layout.addStretch()

        self.status_badge = QLabel(
            "● Hi, Librarian!"
        )

        self.status_badge.setObjectName(
            "SystemStatusBadge"
        )

        # top_layout.addWidget(self.status_badge)

        parent_layout.addWidget(topbar)

    # ========================================================
    # CONTENT AREA
    # ========================================================

    def create_content_area(self, parent_layout):

        content_widget = QWidget()

        content_layout = QHBoxLayout(content_widget)

        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.create_sidebar(content_layout)
        self.create_pages(content_layout)

        parent_layout.addWidget(content_widget)

    # ========================================================
    # SIDEBAR
    # ========================================================

    def create_sidebar(self, parent_layout):

        self.sidebar = QFrame()
        self.sidebar.setObjectName("SideBar")

        self.sidebar.setMinimumWidth(230)
        self.sidebar.setMaximumWidth(230)

        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding
        )

        sidebar_layout = QVBoxLayout(self.sidebar)

        sidebar_layout.setContentsMargins(
            0, 14, 0, 14
        )

        sidebar_layout.setSpacing(4)

        navigation_items = [
            ("📊  Dashboard", 0),
            ("📚  Books Details", 1),
            ("👥  Users Details", 2),
            ("🔄  Circulation", 3),
            ("📈  Reports", 4),
            ("⚙️  Settings", 5)
        ]

        self.nav_buttons = []

        for title, index in navigation_items:

            button = QPushButton(title)

            button.setObjectName("NavigationButton")
            button.setCheckable(True)

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(
                lambda checked=False, idx=index:
                self.switch_page(idx)
            )

            sidebar_layout.addWidget(button)

            self.nav_buttons.append(
                (button, index)
            )

        (
            self.dashboard_btn,
            self.bookcatalog_btn,
            self.usermanagement_btn,
            self.circulation_btn,
            self.reports_btn,
            self.settings_btn
        ) = [
            button for button, _ in self.nav_buttons
        ]

        sidebar_layout.addStretch()

        exit_btn = QPushButton("⏻  Exit System")

        exit_btn.setObjectName("ExitButton")

        exit_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        exit_btn.clicked.connect(
            self.confirm_exit
        )

        sidebar_layout.addWidget(exit_btn)

        parent_layout.addWidget(self.sidebar)

    # ========================================================
    # PAGE INITIALIZATION
    # ========================================================

    def create_pages(self, parent_layout):

        self.pages = QStackedWidget()

        # Dashboard
        self.dashboard_view = DashboardView(self.db)

        if hasattr(
            self.dashboard_view,
            "navigate_requested"
        ):

            self.dashboard_view.navigate_requested.connect(
                self.handle_dashboard_navigation
            )

        # Other pages
        self.catalog_view = CatalogView(self.db)

        self.usermanagement_view = UserManagementView(
            self.db
        )

        self.circulation_view = CirculationView(
            self.db
        )

        self.reports_view = ReportsView(
            self.db
        )

        self.settings_view = SettingsView(
            self.db
        )

        # Register pages in navigation order.
        self.page_views = [
            self.dashboard_view,
            self.catalog_view,
            self.usermanagement_view,
            self.circulation_view,
            self.reports_view,
            self.settings_view
        ]

        for page in self.page_views:
            self.pages.addWidget(page)

        parent_layout.addWidget(self.pages)

    # ========================================================
    # DASHBOARD NAVIGATION
    # ========================================================

    def handle_dashboard_navigation(self, view_name: str):

        route_map = {
            "dashboard": 0,
            "catalog": 1,
            "books": 1,
            "users": 2,
            "circulation": 3,
            "reports": 4,
            "settings": 5
        }

        target_index = route_map.get(
            str(view_name).lower()
        )

        if target_index is not None:
            self.switch_page(target_index)

    # ========================================================
    # PAGE REFRESH
    # ========================================================

    def refresh_page(self, index):

        refresh_methods = {
            0: (
                self.dashboard_view,
                (
                    "refresh_dashboard",
                    "load_dashboard_data",
                    "load_data",
                    "update_stats"
                )
            ),

            1: (
                self.catalog_view,
                ("load_books_to_table",)
            ),

            2: (
                self.usermanagement_view,
                ("load_users_to_table",)
            ),

            3: (
                self.circulation_view,
                ("load_circulation",)
            ),

            4: (
                self.reports_view,
                ("load_data",)
            ),

            5: (
                self.settings_view,
                ("load_settings",)
            )
        }

        if index not in refresh_methods:
            return

        page, methods = refresh_methods[index]

        for method_name in methods:

            method = getattr(
                page,
                method_name,
                None
            )

            if callable(method):

                try:
                    method()

                except Exception as error:

                    print(
                        f"Page refresh error "
                        f"({method_name}): {error}"
                    )

                break

    def switch_page(self, index):

        if not 0 <= index < self.pages.count():
            return

        self.pages.setCurrentIndex(index)

        for button, button_index in self.nav_buttons:

            button.setChecked(
                button_index == index
            )

        self.refresh_page(index)

    # ========================================================
    # SIDEBAR ANIMATION
    # ========================================================

    def toggle_sidebar(self):

        target_width = (
            0 if self.sidebar_expanded else 230
        )

        current_width = self.sidebar.width()

        self.anim_group = QParallelAnimationGroup(self)

        for property_name in (
            b"minimumWidth",
            b"maximumWidth"
        ):

            animation = QPropertyAnimation(
                self.sidebar,
                property_name
            )

            animation.setDuration(240)

            animation.setStartValue(current_width)
            animation.setEndValue(target_width)

            animation.setEasingCurve(
                QEasingCurve.Type.InOutCubic
            )

            self.anim_group.addAnimation(animation)

        self.sidebar_expanded = not self.sidebar_expanded

        self.anim_group.start()

    # ========================================================
    # EXIT CONFIRMATION
    # ========================================================

    def confirm_exit(self):

        reply = QMessageBox.question(
            self,
            "Exit System",
            (
                "Are you sure you want to close "
                "the Library Management System?"
            ),
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:

            app = QApplication.instance()

            if app:
                app.quit()

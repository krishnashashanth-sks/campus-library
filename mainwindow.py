
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
    QApplication,
)

from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
)

from pages.bookcatalog_view import CatalogView
from pages.circulation_view import CirculationView
from pages.reports_view import ReportsView
from pages.usermanagement_view import UserManagementView
from pages.settings_view import SettingsView
from pages.dashboard_view import DashboardView


class MainWindow(QMainWindow):

    SIDEBAR_WIDTH = 230
    SIDEBAR_COLLAPSED_WIDTH = 76

    def __init__(self, db):

        super().__init__()

        self.db = db
        self.sidebar_expanded = True
        self._sidebar_auto_collapsed = False
        self._responsive_sidebar_mode = None
        self.anim_group = None
        self.nav_buttons = []
        self.page_views = []

        app = QApplication.instance()

        self.theme_manager = getattr(
            app,
            "theme_manager",
            None
        )

        self.setWindowTitle(
            "Library Management System"
        )

        screen = app.primaryScreen() if app else None
        available = screen.availableGeometry() if screen else None
        if available and available.isValid():
            self.setMinimumSize(
                min(1024, available.width()),
                min(640, available.height()),
            )
            self.resize(
                min(1440, available.width()),
                min(900, available.height()),
            )
        else:
            self.setMinimumSize(1024, 640)
            self.resize(1440, 900)

        self.load_saved_theme()

        self.initialize_window_icon()
        self.initialize_ui()

        if self.theme_manager:
            try:
                self.theme_manager.themeChanged.connect(
                    self.apply_shell_theme
                )
            except Exception as error:
                print(
                    f"Theme signal connection warning: {error}"
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
                "Light Modern": "Light",
            }

            saved_theme = legacy_themes.get(
                saved_theme,
                saved_theme
            )

            if saved_theme not in (
                "Dark",
                "Light",
                "System"
            ):
                saved_theme = "Dark"

            if self.theme_manager:
                self.theme_manager.set_theme(
                    saved_theme
                )

        except Exception as error:

            print(
                f"Theme initialization warning: {error}"
            )

    def get_theme_colors(self):

        fallback_colors = {
            "window": "#111827",
            "surface": "#1B2433",
            "surface_alt": "#273449",
            "input": "#202C3D",
            "text": "#F3F6FC",
            "muted": "#9AA8BC",
            "border": "#344155",
            "primary": "#5577F5",
            "primary_hover": "#4263DB",
        }

        if not self.theme_manager:
            return fallback_colors

        try:

            active_theme = (
                self.theme_manager.get_active_theme()
            )

            colors = self.theme_manager.COLORS.get(
                active_theme
            )

            if not colors:
                return fallback_colors

            # Fill missing color values safely.
            result = fallback_colors.copy()
            result.update(colors)

            return result

        except Exception as error:

            print(
                f"Theme color warning: {error}"
            )

            return fallback_colors

    def apply_shell_theme(self, active_theme=None):
        """
        Apply theme-specific colors to the main window shell.
        """

        if not self.theme_manager:
            return

        try:

            if active_theme is None:
                active_theme = (
                    self.theme_manager.get_active_theme()
                )

            colors = self.theme_manager.COLORS.get(
                active_theme
            )

            if not colors:
                colors = self.get_theme_colors()

            window = colors.get(
                "window",
                "#111827"
            )

            surface = colors.get(
                "surface",
                "#1B2433"
            )

            surface_alt = colors.get(
                "surface_alt",
                "#273449"
            )

            input_color = colors.get(
                "input",
                surface_alt
            )

            text = colors.get(
                "text",
                "#F3F6FC"
            )

            muted = colors.get(
                "muted",
                "#9AA8BC"
            )

            border = colors.get(
                "border",
                "#344155"
            )

            primary = colors.get(
                "primary",
                "#5577F5"
            )

            primary_hover = colors.get(
                "primary_hover",
                "#4263DB"
            )

            success = colors.get(
                "success",
                "#16A34A"
            )

            self.setStyleSheet(f"""

                /* Main window */

                QMainWindow {{
                    background-color: {window};
                }}

                QWidget#MainCentralWidget {{
                    background-color: {window};
                    color: {text};
                }}

                /* Top bar */

                QFrame#TopBar {{
                    background-color: {surface};
                    border-bottom: 1px solid {border};
                }}

                QLabel#MainTitle {{
                    color: {text};
                    background-color: transparent;
                    border: none;
                    font-size: 17px;
                    font-weight: 700;
                }}

                /* Sidebar toggle */

                QPushButton#SidebarToggle {{
                    background-color: {input_color};
                    color: {text};
                    border: 1px solid {border};
                    border-radius: 9px;
                    font-size: 19px;
                    font-weight: 600;
                }}

                QPushButton#SidebarToggle:hover {{
                    background-color: {surface_alt};
                    border-color: {primary};
                }}

                QPushButton#SidebarToggle:pressed {{
                    background-color: {primary};
                    color: #FFFFFF;
                }}

                /* Librarian greeting */

                QLabel#SystemStatusBadge {{
                    background-color: {surface_alt};
                    color: {success};
                    font-size: 12px;
                    font-weight: 600;
                    padding: 7px 14px;
                    min-height: 20px;
                    border-radius: 15px;
                    border: 1px solid {border};
                }}

                /* Sidebar */

                QFrame#SideBar {{
                    background-color: {surface};
                    border-right: 1px solid {border};
                }}

                QPushButton#NavigationButton {{
                    background-color: transparent;
                    color: {muted};
                    border: 1px solid transparent;
                    text-align: left;
                    padding-left: 16px;
                    padding-right: 10px;
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 44px;
                    margin: 3px 12px;
                    border-radius: 9px;
                }}

                QPushButton#NavigationButton:hover {{
                    background-color: {surface_alt};
                    color: {text};
                }}

                QPushButton#NavigationButton:checked {{
                    background-color: {primary};
                    color: #FFFFFF;
                    border: 1px solid {primary_hover};
                    font-weight: 700;
                }}

                QPushButton#NavigationButton:focus {{
                    outline: none;
                }}

                QPushButton#NavigationButton[compact="true"] {{
                    text-align: center;
                    padding-left: 0;
                    padding-right: 0;
                    margin-left: 8px;
                    margin-right: 8px;
                    font-size: 19px;
                }}

                /* Exit button */

                QPushButton#ExitButton {{
                    background-color: rgba(239, 68, 68, 0.10);
                    color: #EF6464;
                    text-align: left;
                    padding-left: 16px;
                    min-height: 44px;
                    margin: 4px 12px;
                    border-radius: 9px;
                    font-weight: 600;
                    font-size: 13px;
                    border: 1px solid rgba(239, 68, 68, 0.25);
                }}

                QPushButton#ExitButton:hover {{
                    background-color: #DC2626;
                    color: #FFFFFF;
                    border-color: #DC2626;
                }}

                QPushButton#ExitButton[compact="true"] {{
                    text-align: center;
                    padding-left: 0;
                    padding-right: 0;
                    margin-left: 8px;
                    margin-right: 8px;
                    font-size: 18px;
                }}

                /* Pages container */

                QStackedWidget#MainPages {{
                    background-color: {window};
                    border: none;
                }}

            """)

            # Update the shell background palette.
            self.setAutoFillBackground(True)

        except Exception as error:

            print(
                f"Shell theme application error: {error}"
            )

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
            *relative_path.replace(
                "\\",
                "/"
            ).split("/")
        )

    def initialize_window_icon(self):

        icon_path = self.get_asset_path(
            "assets/library_icon.ico"
        )

        if os.path.exists(icon_path):

            self.setWindowIcon(
                QIcon(icon_path)
            )

    # ========================================================
    # MAIN USER INTERFACE
    # ========================================================

    def initialize_ui(self):

        main_widget = QWidget()

        main_widget.setObjectName(
            "MainCentralWidget"
        )

        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(
            main_widget
        )

        main_layout.setContentsMargins(
            0, 0, 0, 0
        )

        main_layout.setSpacing(0)

        self.create_topbar(main_layout)
        self.create_content_area(main_layout)

    # ========================================================
    # TOPBAR
    # ========================================================

    def create_topbar(self, parent_layout):

        topbar = QFrame()

        topbar.setObjectName(
            "TopBar"
        )

        topbar.setFixedHeight(72)

        top_layout = QHBoxLayout(
            topbar
        )

        top_layout.setContentsMargins(
            18, 0, 24, 0
        )

        top_layout.setSpacing(15)

        # Sidebar toggle

        self.toggle_btn = QPushButton("☰")

        self.toggle_btn.setObjectName(
            "SidebarToggle"
        )

        self.toggle_btn.setFixedSize(
            42, 42
        )

        self.toggle_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.toggle_btn.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        self.toggle_btn.setToolTip(
            "Toggle Navigation Sidebar"
        )

        self.toggle_btn.clicked.connect(
            self.toggle_sidebar
        )

        top_layout.addWidget(
            self.toggle_btn
        )

        # Application title

        title_label = QLabel(
            "Library Management System"
        )

        title_label.setObjectName(
            "MainTitle"
        )

        title_label.setFont(
            QFont(
                "Segoe UI",
                16,
                QFont.Weight.Bold
            )
        )

        top_layout.addWidget(
            title_label
        )

        top_layout.addStretch()

        # Librarian greeting

        self.status_badge = QLabel(
            "● Hi, Librarian!"
        )

        self.status_badge.setObjectName(
            "SystemStatusBadge"
        )

        self.status_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        top_layout.addWidget(
            self.status_badge
        )

        parent_layout.addWidget(
            topbar
        )

    # ========================================================
    # CONTENT AREA
    # ========================================================

    def create_content_area(self, parent_layout):

        content_widget = QWidget()

        content_layout = QHBoxLayout(
            content_widget
        )

        content_layout.setContentsMargins(
            0, 0, 0, 0
        )

        content_layout.setSpacing(0)

        self.create_sidebar(
            content_layout
        )

        self.create_pages(
            content_layout
        )

        parent_layout.addWidget(
            content_widget,
            1
        )

    # ========================================================
    # SIDEBAR
    # ========================================================

    def create_sidebar(self, parent_layout):

        self.sidebar = QFrame()

        self.sidebar.setObjectName(
            "SideBar"
        )

        self.sidebar.setMinimumWidth(
            self.SIDEBAR_WIDTH
        )

        self.sidebar.setMaximumWidth(
            self.SIDEBAR_WIDTH
        )

        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding
        )

        self.sidebar_layout = QVBoxLayout(
            self.sidebar
        )

        self.sidebar_layout.setContentsMargins(
            0, 18, 0, 14
        )

        self.sidebar_layout.setSpacing(4)

        # Navigation items

        navigation_items = [
            ("📊  Dashboard", 0),
            ("📚  Books Details", 1),
            ("👥  Users Details", 2),
            ("🔄  Circulation", 3),
            ("📈  Reports", 4),
            ("⚙️  Settings", 5),
        ]

        self.nav_buttons = []
        self.nav_icons = {}

        for title, index in navigation_items:

            button = QPushButton(title)
            icon, _label = title.split("  ", 1)
            self.nav_icons[index] = (icon, title)
            button.setToolTip(title)
            button.setAccessibleName(title)

            button.setObjectName(
                "NavigationButton"
            )

            button.setCheckable(True)

            button.setAutoExclusive(False)

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.setFocusPolicy(
                Qt.FocusPolicy.NoFocus
            )

            button.clicked.connect(
                lambda checked=False, idx=index:
                self.switch_page(idx)
            )

            self.sidebar_layout.addWidget(
                button
            )

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
            button
            for button, _ in self.nav_buttons
        ]

        self.sidebar_layout.addStretch()

        # Exit button

        self.exit_btn = QPushButton(
            "⏻  Exit System"
        )

        self.exit_btn.setObjectName(
            "ExitButton"
        )

        self.exit_btn.setToolTip("Exit System")
        self.exit_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.exit_btn.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )

        self.exit_btn.clicked.connect(
            self.confirm_exit
        )

        self.sidebar_layout.addWidget(
            self.exit_btn
        )

        parent_layout.addWidget(
            self.sidebar
        )

    # ========================================================
    # PAGE INITIALIZATION
    # ========================================================

    def create_pages(self, parent_layout):

        self.pages = QStackedWidget()

        self.pages.setObjectName(
            "MainPages"
        )

        # Dashboard

        self.dashboard_view = DashboardView(
            self.db
        )

        if hasattr(
            self.dashboard_view,
            "navigate_requested"
        ):

            self.dashboard_view.navigate_requested.connect(
                self.handle_dashboard_navigation
            )

        # Other pages

        self.catalog_view = CatalogView(
            self.db
        )

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
            self.settings_view,
        ]

        for page in self.page_views:
            self.pages.addWidget(page)

        parent_layout.addWidget(
            self.pages,
            1
        )

    # ========================================================
    # DASHBOARD NAVIGATION
    # ========================================================

    def handle_dashboard_navigation(
        self,
        view_name: str
    ):

        route_map = {
            "dashboard": 0,
            "catalog": 1,
            "books": 1,
            "users": 2,
            "user management": 2,
            "circulation": 3,
            "reports": 4,
            "settings": 5,
        }

        target_index = route_map.get(
            str(view_name).strip().lower()
        )

        if target_index is not None:
            self.switch_page(
                target_index
            )

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
                    "update_stats",
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
            ),
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

        if not hasattr(self, "pages"):
            return

        if not 0 <= index < self.pages.count():
            return

        self.pages.setCurrentIndex(
            index
        )

        for button, button_index in self.nav_buttons:

            button.setChecked(
                button_index == index
            )

    # ========================================================
    # SIDEBAR ANIMATION
    # ========================================================

    def toggle_sidebar(self):
        self._sidebar_auto_collapsed = False

        if self.anim_group and (
            self.anim_group.state()
            == QParallelAnimationGroup.State.Running
        ):
            self.anim_group.stop()

        target_expanded = not self.sidebar_expanded
        target_width = (
            self.SIDEBAR_WIDTH
            if target_expanded
            else self.SIDEBAR_COLLAPSED_WIDTH
        )
        self._apply_sidebar_compact_mode(not target_expanded)

        current_width = self.sidebar.maximumWidth()

        self.anim_group = QParallelAnimationGroup(
            self
        )

        for property_name in (
            b"minimumWidth",
            b"maximumWidth"
        ):

            animation = QPropertyAnimation(
                self.sidebar,
                property_name,
                self
            )

            animation.setDuration(240)

            animation.setStartValue(
                current_width
            )

            animation.setEndValue(
                target_width
            )

            animation.setEasingCurve(
                QEasingCurve.Type.InOutCubic
            )

            self.anim_group.addAnimation(
                animation
            )

        self.sidebar_expanded = target_expanded

        self.anim_group.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if not hasattr(self, "sidebar"):
            return

        compact = self.width() < 1280
        if compact == self._responsive_sidebar_mode:
            return

        self._responsive_sidebar_mode = compact

        if compact and self.sidebar_expanded:
            self._set_sidebar_expanded(False, automatic=True)
        elif not compact and self._sidebar_auto_collapsed:
            self._set_sidebar_expanded(True, automatic=False)

    def _set_sidebar_expanded(self, expanded, automatic):
        if self.anim_group and (
            self.anim_group.state()
            == QParallelAnimationGroup.State.Running
        ):
            self.anim_group.stop()

        width = (
            self.SIDEBAR_WIDTH
            if expanded
            else self.SIDEBAR_COLLAPSED_WIDTH
        )
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        self.sidebar_expanded = expanded
        self._sidebar_auto_collapsed = automatic and not expanded
        self._apply_sidebar_compact_mode(not expanded)

    def _apply_sidebar_compact_mode(self, compact):
        if not hasattr(self, "nav_buttons"):
            return

        margins = 8 if compact else 0
        self.sidebar_layout.setContentsMargins(
            margins,
            18,
            margins,
            14,
        )

        for button, index in self.nav_buttons:
            icon, title = self.nav_icons[index]
            button.setText(icon if compact else title)
            button.setToolTip(title if compact else "")
            button.setProperty("compact", compact)
            button.style().unpolish(button)
            button.style().polish(button)

        self.exit_btn.setText(
            "⏻" if compact else "⏻  Exit System"
        )
        self.exit_btn.setProperty("compact", compact)
        self.exit_btn.style().unpolish(self.exit_btn)
        self.exit_btn.style().polish(self.exit_btn)

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

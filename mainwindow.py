
import os
import sys

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QStackedWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QMessageBox,
    QApplication,
    QScrollArea,
)

from PyQt6.QtGui import QIcon, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QRect,
    QTimer,
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
from email_queue import EmailQueueManager
from help_dialog import HelpDialog
from app_version import get_app_version
from ui_responsive import active_screen_geometry


class MainWindow(QMainWindow):

    SIDEBAR_WIDTH = 230
    SIDEBAR_COLLAPSED_WIDTH = 76

    def __init__(self, db):

        super().__init__()

        self.db = db
        self.email_sync_manager = EmailQueueManager(
            db.database_path,
            self,
            db,
        )
        application = QApplication.instance()
        if application:
            application.email_sync_manager = self.email_sync_manager
        self.sidebar_expanded = True
        self._sidebar_auto_collapsed = False
        self._responsive_sidebar_mode = None
        self._topbar_tier = None
        self.anim_group = None
        self.nav_buttons = []
        self.page_views = []
        self._page_loaded_stamps = {}
        self._workers_stopped = False
        self._last_email_status_message = "Email sync checking"

        app = QApplication.instance()

        self.theme_manager = getattr(
            app,
            "theme_manager",
            None
        )

        self.setWindowTitle(
            "Library Management System"
        )

        available = active_screen_geometry(self)
        self.setMinimumSize(
            min(760, available.width()),
            min(500, available.height()),
        )
        self.resize(
            min(1440, available.width()),
            min(900, available.height()),
        )

        self.load_saved_theme()

        self.initialize_window_icon()
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(180)
        self._search_debounce_timer.timeout.connect(
            self._update_search_suggestions
        )
        self._search_results = []
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
        self._apply_responsive_topbar()
        self.switch_page(0)
        self.email_sync_manager.status_changed.connect(
            self.update_email_status
        )
        self.email_sync_manager.start()

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

            surface_elevated = colors.get("surface_elevated", surface_alt)
            border_bright = colors.get("border_bright", border)
            success = colors.get("success", "#10B981")
            success_hover = colors.get("success_hover", success)
            indigo = colors.get("indigo", "#6366F1")
            indigo_hover = colors.get("indigo_hover", "#4F46E5")
            cyan = colors.get("cyan", "#06B6D4")
            cyan_hover = colors.get("cyan_hover", "#0891B2")
            teal = colors.get("teal", "#0D9488")
            purple = colors.get("purple", "#8B5CF6")
            warning = colors.get("warning", "#D97706")
            danger = colors.get("danger", "#E11D48")
            danger_hover = colors.get("danger_hover", "#BE123C")
            primary_soft = colors.get("primary_soft", surface_alt)
            indigo_soft = colors.get("indigo_soft", surface_alt)
            success_soft = colors.get("success_soft", surface_alt)
            cyan_soft = colors.get("cyan_soft", surface_alt)
            purple_soft = colors.get("purple_soft", surface_alt)
            warning_soft = colors.get("warning_soft", surface_alt)
            danger_soft = colors.get("danger_soft", surface_alt)

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
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {surface},
                        stop:0.55 {surface_alt},
                        stop:1 {surface}
                    );
                    border-bottom: 2px solid {border_bright};
                }}

                QLabel#MainTitle {{
                    color: {text};
                    background-color: transparent;
                    border: none;
                    font-size: 14px;
                    font-weight: 800;
                }}

                /* Sidebar toggle */

                QPushButton#SidebarToggle {{
                    background-color: {primary_soft};
                    color: {primary};
                    border: 1px solid {border_bright};
                    border-radius: 9px;
                    font-size: 19px;
                    font-weight: 700;
                }}

                QPushButton#SidebarToggle:hover {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 {primary},
                        stop:1 {indigo}
                    );
                    color: #FFFFFF;
                    border-color: {cyan};
                }}

                QPushButton#SidebarToggle:pressed {{
                    background-color: {primary_hover};
                    color: #FFFFFF;
                }}

                QLabel#VersionBadge {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {indigo_soft},
                        stop:1 {cyan_soft}
                    );
                    color: {cyan};
                    font-size: 9px;
                    font-weight: 800;
                    padding: 3px 8px;
                    border-radius: 9px;
                    border: 1px solid {indigo};
                }}

                QLineEdit#HeaderSearch {{
                    background-color: {input_color};
                    color: {text};
                    border: 1.5px solid {border_bright};
                    border-radius: 9px;
                    padding: 7px 12px;
                    min-height: 20px;
                    font-size: 11px;
                }}

                QLineEdit#HeaderSearch:hover {{
                    border-color: {cyan};
                }}

                QLineEdit#HeaderSearch:focus {{
                    border: 1.5px solid {primary};
                    background-color: {surface};
                }}

                QPushButton#HeaderIssue,
                QPushButton#HeaderReturn,
                QPushButton#HeaderTheme,
                QPushButton#HeaderHelp {{
                    color: #FFFFFF;
                    border-radius: 8px;
                    padding: 7px 11px;
                    min-height: 20px;
                    font-size: 10px;
                    font-weight: 700;
                }}

                QPushButton#HeaderIssue[compact="true"],
                QPushButton#HeaderReturn[compact="true"],
                QPushButton#HeaderTheme[compact="true"],
                QPushButton#HeaderHelp[compact="true"] {{
                    padding: 6px 7px;
                    font-size: 10px;
                }}

                QPushButton#HeaderIssue {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {primary},
                        stop:1 {indigo}
                    );
                    border: 1px solid {primary_hover};
                }}

                QPushButton#HeaderIssue:hover {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {primary_hover},
                        stop:1 {indigo_hover}
                    );
                }}

                QPushButton#HeaderReturn {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {success},
                        stop:1 {teal}
                    );
                    border: 1px solid {success_hover};
                }}

                QPushButton#HeaderReturn:hover {{
                    background-color: {success_hover};
                }}

                QPushButton#HeaderTheme {{
                    background-color: {warning_soft};
                    color: {warning};
                    border: 1px solid {warning};
                }}

                QPushButton#HeaderTheme:hover {{
                    background-color: {warning};
                    color: #FFFFFF;
                }}

                QPushButton#HeaderHelp {{
                    background-color: {cyan_soft};
                    color: {cyan};
                    border: 1px solid {cyan};
                }}

                QPushButton#HeaderHelp:hover {{
                    background-color: {cyan_hover};
                    color: #FFFFFF;
                }}

                QLabel#SystemStatusBadge {{
                    background-color: {success_soft};
                    color: {success};
                    font-size: 10px;
                    font-weight: 700;
                    padding: 6px 11px;
                    border-radius: 12px;
                    border: 1px solid {success};
                }}

                /* Sidebar */

                QFrame#SideBar {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:0, y2:1,
                        stop:0 {surface},
                        stop:0.5 {surface_alt},
                        stop:1 {surface}
                    );
                    border-right: 1px solid {border_bright};
                }}

                QPushButton#NavigationButton {{
                    background-color: transparent;
                    color: {muted};
                    border: 1px solid transparent;
                    border-left: 3px solid transparent;
                    text-align: left;
                    padding-left: 14px;
                    padding-right: 10px;
                    font-size: 13px;
                    font-weight: 600;
                    min-height: 44px;
                    margin: 3px 10px;
                    border-radius: 10px;
                }}

                QPushButton#NavigationButton:hover {{
                    background-color: {surface_elevated};
                    color: {text};
                    border-color: {border_bright};
                    border-left: 3px solid {cyan};
                }}

                QPushButton#NavigationButton:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {primary},
                        stop:1 {indigo}
                    );
                    color: #FFFFFF;
                    border: 1px solid {primary_hover};
                    border-left: 4px solid #FFFFFF;
                    font-weight: 800;
                }}

                QPushButton#NavigationButton[navRole="books"]:hover {{
                    border-left: 3px solid {success};
                }}
                QPushButton#NavigationButton[navRole="books"]:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {success},
                        stop:1 {teal}
                    );
                    border-color: {success_hover};
                }}

                QPushButton#NavigationButton[navRole="users"]:hover {{
                    border-left: 3px solid {purple};
                }}
                QPushButton#NavigationButton[navRole="users"]:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {indigo},
                        stop:1 {purple}
                    );
                    border-color: {indigo_hover};
                }}

                QPushButton#NavigationButton[navRole="circulation"]:hover {{
                    border-left: 3px solid {cyan};
                }}
                QPushButton#NavigationButton[navRole="circulation"]:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {cyan_hover},
                        stop:1 {primary}
                    );
                    border-color: {cyan_hover};
                }}

                QPushButton#NavigationButton[navRole="reports"]:hover {{
                    border-left: 3px solid {warning};
                }}
                QPushButton#NavigationButton[navRole="reports"]:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {warning},
                        stop:1 #EA580C
                    );
                    border-color: {warning};
                }}

                QPushButton#NavigationButton[navRole="settings"]:hover {{
                    border-left: 3px solid {indigo};
                }}
                QPushButton#NavigationButton[navRole="settings"]:checked {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {primary_hover},
                        stop:1 #4338CA
                    );
                    border-color: {indigo};
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
                    border-left: 1px solid transparent;
                    font-size: 19px;
                }}

                QPushButton#NavigationButton[compact="true"]:checked {{
                    border-left: 2px solid #FFFFFF;
                }}

                /* Exit button */

                QPushButton#ExitButton {{
                    background-color: {danger_soft};
                    color: {danger};
                    text-align: left;
                    padding-left: 16px;
                    min-height: 44px;
                    margin: 4px 10px;
                    border-radius: 10px;
                    font-weight: 700;
                    font-size: 13px;
                    border: 1px solid {danger};
                }}

                QPushButton#ExitButton:hover {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 {danger},
                        stop:1 {danger_hover}
                    );
                    color: #FFFFFF;
                    border-color: {danger_hover};
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

            if hasattr(self, "theme_button"):
                self._sync_theme_button_text(active_theme)
            if hasattr(self, "status_badge"):
                self._apply_email_status_style(colors)
            if hasattr(self, "quick_actions_fab"):
                self._style_quick_actions_fab(colors)
            if hasattr(self, "quick_actions_popup"):
                self._style_quick_actions_popup(colors)

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
        self._init_quick_actions_fab()
        self._init_quick_actions_popup()
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        search_shortcut.activated.connect(
            self.global_search_input.setFocus
        )
        self._global_search_shortcut = search_shortcut

        quick_actions_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        quick_actions_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        quick_actions_shortcut.activated.connect(
            lambda: self.toggle_quick_actions_popup(
                getattr(self, "quick_actions_fab", None)
            )
        )
        self._quick_actions_shortcut = quick_actions_shortcut

        self._application_shortcuts = []
        shortcut_actions = (
            ("Ctrl+I", self.dashboard_view.open_issue_dialog),
            ("Ctrl+R", self.dashboard_view.open_return_dialog),
            ("Ctrl+B", self.dashboard_view.open_bookform),
            ("Ctrl+U", self.dashboard_view.open_userform),
            ("Ctrl+G", self.dashboard_view.open_bargenerate_form),
            ("Ctrl+Shift+K", self.dashboard_view.open_quick_scan),
            ("Ctrl+H", self.dashboard_view.open_activity_history),
            (
                "F5",
                lambda: self.refresh_page(self.pages.currentIndex(), force=True)
                if hasattr(self, "pages")
                else self.dashboard_view.refresh_dashboard(),
            ),
        )
        for sequence, callback in shortcut_actions:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            shortcut.activated.connect(callback)
            self._application_shortcuts.append(shortcut)

        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        help_shortcut.activated.connect(self.show_help)
        self._help_shortcut = help_shortcut

    # ========================================================
    # TOPBAR
    # ========================================================

    def create_topbar(self, parent_layout):

        topbar = QFrame()

        topbar.setObjectName(
            "TopBar"
        )

        topbar.setFixedHeight(60)
        self.topbar = topbar

        top_layout = QHBoxLayout(
            topbar
        )

        top_layout.setContentsMargins(
            14, 0, 16, 0
        )

        top_layout.setSpacing(9)
        self.top_layout = top_layout

        # Sidebar toggle

        self.toggle_btn = QPushButton("☰")

        self.toggle_btn.setObjectName(
            "SidebarToggle"
        )

        self.toggle_btn.setFixedSize(
            36, 36
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
                13,
                QFont.Weight.Bold
            )
        )
        title_label.setMinimumWidth(0)
        self.title_label = title_label

        top_layout.addWidget(
            title_label
        )

        version_badge = QLabel(f"v{get_app_version()}")
        version_badge.setObjectName("VersionBadge")
        self.version_badge = version_badge
        top_layout.addWidget(version_badge)

        self.global_search_input = QLineEdit()
        self.global_search_input.setObjectName("HeaderSearch")
        self.global_search_input.setPlaceholderText(
            "Search books, Roll No (e.g., 24001-CS-097), author, or ISBN..."
        )
        self.global_search_input.setClearButtonEnabled(True)
        self.global_search_input.setMinimumWidth(110)
        self.global_search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.global_search_input.textChanged.connect(
            self._schedule_search_suggestions
        )
        self.global_search_input.returnPressed.connect(
            self._search_from_header
        )
        top_layout.addWidget(self.global_search_input, 1)

        self.search_suggestions = QFrame(self)
        self.search_suggestions.setObjectName(
            "GlobalSearchSuggestions"
        )
        self.search_suggestions.hide()
        self.search_suggestions.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )
        self.search_suggestions.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            True,
        )
        self.search_suggestions.setMinimumWidth(260)
        self.search_suggestions.setMaximumHeight(360)
        self.search_suggestions_scroll = QScrollArea(
            self.search_suggestions
        )
        self.search_suggestions_scroll.setWidgetResizable(True)
        self.search_suggestions_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )
        self.search_suggestions_scroll.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )
        self.search_suggestions_scroll.setMaximumHeight(348)
        self.search_suggestions_content = QWidget()
        self.search_suggestions_layout = QVBoxLayout(
            self.search_suggestions_content
        )
        self.search_suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.search_suggestions_layout.setSpacing(3)
        self.search_suggestions_scroll.setWidget(
            self.search_suggestions_content
        )
        self.search_suggestions_outer_layout = QVBoxLayout(
            self.search_suggestions
        )
        self.search_suggestions_outer_layout.setContentsMargins(
            6, 6, 6, 6
        )
        self.search_suggestions_outer_layout.addWidget(
            self.search_suggestions_scroll
        )

        self.issue_header_button = QPushButton("+ Issue Book")
        self.issue_header_button.setObjectName("HeaderIssue")
        self.issue_header_button.setToolTip("Issue a book to a member (Ctrl+I)")
        self.issue_header_button.setMinimumWidth(0)
        self.issue_header_button.clicked.connect(
            self._issue_from_header
        )
        top_layout.addWidget(self.issue_header_button)

        self.return_header_button = QPushButton("Return Book")
        self.return_header_button.setObjectName("HeaderReturn")
        self.return_header_button.setToolTip("Return a borrowed book (Ctrl+R)")
        self.return_header_button.setMinimumWidth(0)
        self.return_header_button.clicked.connect(
            self._return_from_header
        )
        top_layout.addWidget(self.return_header_button)

        self.theme_button = QPushButton("☀ Light")
        self.theme_button.setObjectName("HeaderTheme")
        self.theme_button.setToolTip("Toggle Dark / Light theme")
        self.theme_button.setMinimumWidth(0)
        self.theme_button.clicked.connect(
            self._toggle_theme_from_header
        )
        top_layout.addWidget(self.theme_button)

        self.help_button = QPushButton("Help")
        self.help_button.setObjectName("HeaderHelp")
        self.help_button.setToolTip("Open application help (F1)")
        self.help_button.setMinimumWidth(0)
        self.help_button.clicked.connect(self.show_help)
        top_layout.addWidget(self.help_button)

        self.status_badge = QLabel("● Email sync checking")

        self.status_badge.setObjectName(
            "SystemStatusBadge"
        )
        self.status_badge.setMinimumWidth(0)
        self.status_badge.setToolTip("Email sync checking")

        self.status_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        top_layout.addWidget(
            self.status_badge
        )

        parent_layout.addWidget(
            topbar
        )

    def _active_theme_name(self):
        if self.theme_manager:
            try:
                return self.theme_manager.get_active_theme()
            except Exception:
                pass
        return "Dark"

    def _sync_theme_button_text(self, active_theme=None):
        if not hasattr(self, "theme_button"):
            return
        theme = active_theme or self._active_theme_name()
        tier = self._topbar_tier or 0
        if tier >= 1:
            self.theme_button.setText("☀" if theme == "Dark" else "☾")
        else:
            self.theme_button.setText("☀ Light" if theme == "Dark" else "☾ Dark")

    def _compact_email_status_text(self, message: str, ultra_compact: bool = False) -> str:
        msg = (message or "").strip()
        lower = msg.lower()
        if ultra_compact:
            if "active" in lower or "sent" in lower:
                return "● Sync"
            if "running" in lower or "sending" in lower:
                return "● Syncing"
            if "offline" in lower or "error" in lower or "failed" in lower:
                return "● Issue"
            return "● Queue"
        if lower.startswith("email sync active"):
            return "● Sync Active"
        if lower.startswith("email sync running"):
            return "● Syncing..."
        if "offline" in lower:
            return "● Offline"
        if "pending" in lower or "queue" in lower:
            return "● Sync Pending"
        if "check" in lower:
            return "● Sync..."
        return f"● {msg[:18]}..." if len(msg) > 20 else f"● {msg}"

    def _sync_status_badge_text(self):
        if not hasattr(self, "status_badge"):
            return
        message = getattr(self, "_last_email_status_message", "") or "Email sync checking"
        self.status_badge.setToolTip(message)
        tier = self._topbar_tier or 0
        if tier >= 2:
            self.status_badge.setText(self._compact_email_status_text(message, ultra_compact=True))
        elif tier == 1:
            self.status_badge.setText(self._compact_email_status_text(message, ultra_compact=False))
        else:
            self.status_badge.setText(f"● {message}")

    def _apply_responsive_topbar(self):
        if not hasattr(self, "top_layout"):
            return
        width = self.width()
        if width < 960:
            tier = 2
        elif width < 1240:
            tier = 1
        else:
            tier = 0

        if tier == self._topbar_tier:
            return
        self._topbar_tier = tier

        if tier == 2:
            self.top_layout.setContentsMargins(8, 0, 8, 0)
            self.top_layout.setSpacing(4)
            self.title_label.setText("Library")
            self.title_label.setToolTip("Library Management System")
            self.version_badge.setVisible(False)
            self.global_search_input.setMinimumWidth(65)
            self.global_search_input.setPlaceholderText("Search books, Roll No, ISBN...")
            self.issue_header_button.setText("+ Issue")
            self.return_header_button.setText("Return")
            self.help_button.setText("?")
        elif tier == 1:
            self.top_layout.setContentsMargins(10, 0, 12, 0)
            self.top_layout.setSpacing(6)
            self.title_label.setText("Library")
            self.title_label.setToolTip("Library Management System")
            self.version_badge.setVisible(True)
            self.global_search_input.setMinimumWidth(110)
            self.global_search_input.setPlaceholderText("Search books, Roll No, author, ISBN...")
            self.issue_header_button.setText("+ Issue")
            self.return_header_button.setText("Return")
            self.help_button.setText("Help")
        else:
            self.top_layout.setContentsMargins(14, 0, 16, 0)
            self.top_layout.setSpacing(9)
            self.title_label.setText("Library Management System")
            self.title_label.setToolTip("")
            self.version_badge.setVisible(True)
            self.global_search_input.setMinimumWidth(110)
            self.global_search_input.setPlaceholderText(
                "Search books, Roll No (e.g., 24001-CS-097), author, or ISBN..."
            )
            self.issue_header_button.setText("+ Issue Book")
            self.return_header_button.setText("Return Book")
            self.help_button.setText("Help")

        is_compact_btns = tier == 2
        for btn in (
            self.issue_header_button,
            self.return_header_button,
            self.theme_button,
            self.help_button,
        ):
            if btn is not None:
                btn.setProperty("compact", is_compact_btns)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        self._sync_theme_button_text()
        self._sync_status_badge_text()

    def update_email_status(self, message):
        self._last_email_status_message = str(message or "")
        self._sync_status_badge_text()
        self._apply_email_status_style()

    def _apply_email_status_style(self, colors=None):
        colors = colors or self.get_theme_colors()
        message = getattr(self, "_last_email_status_message", "")
        if message.startswith("Email sync active"):
            color = colors.get("success", "#10B981")
            bg = colors.get("success_soft", "rgba(16, 185, 129, 0.14)")
        elif message.startswith("Email sync running"):
            color = colors.get("cyan", "#06B6D4")
            bg = colors.get("cyan_soft", "rgba(6, 182, 212, 0.14)")
        else:
            color = colors.get("warning", "#D97706")
            bg = colors.get("warning_soft", "rgba(217, 119, 6, 0.14)")
        self.status_badge.setStyleSheet(
            f"QLabel#SystemStatusBadge {{"
            f" color: {color};"
            f" background-color: {bg};"
            f" border: 1px solid {color};"
            f" border-radius: 12px;"
            f" padding: 6px 11px;"
            f" font-size: 10px;"
            f" font-weight: 700;"
            f"}}"
        )

    def _search_from_header(self):
        self._search_debounce_timer.stop()
        self._update_search_suggestions()
        if self._search_results:
            self._open_global_search_result(self._search_results[0])

    def _schedule_search_suggestions(self, text):
        if not text.strip():
            self._search_debounce_timer.stop()
            self._search_results = []
            self.search_suggestions.hide()
            return
        self._search_debounce_timer.start()

    def _update_search_suggestions(self):
        query = self.global_search_input.text().strip()
        if not query:
            self.search_suggestions.hide()
            return

        try:
            self._search_results = (
                self.dashboard_view.search_global_records(query)
            )
            message = (
                "No matching books, members, or transactions."
                if not self._search_results else None
            )
        except Exception as error:
            self._search_results = []
            message = f"Search unavailable: {error}"

        self._render_search_suggestions(message)

    def _render_search_suggestions(self, message=None):
        while self.search_suggestions_layout.count():
            item = self.search_suggestions_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        colors = self.get_theme_colors()
        primary = colors.get("primary", "#3B82F6")
        primary_soft = colors.get("primary_soft", colors["surface_alt"])
        border_bright = colors.get("border_bright", colors["border"])
        self.search_suggestions.setStyleSheet(f"""
            QFrame#GlobalSearchSuggestions {{
                background-color: {colors['surface']};
                border: 1.5px solid {border_bright};
                border-radius: 10px;
            }}
            QPushButton#GlobalSearchResult {{
                background-color: transparent;
                color: {colors['text']};
                border: 1px solid transparent;
                border-left: 3px solid {primary};
                border-radius: 7px;
                text-align: left;
                padding: 8px 10px;
                min-height: 42px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#GlobalSearchResult:hover {{
                background-color: {primary_soft};
                border-color: {primary};
            }}
            QLabel#GlobalSearchMessage {{
                color: {colors['muted']};
                padding: 10px;
                font-size: 11px;
            }}
        """)

        if message:
            label = QLabel(message)
            label.setObjectName("GlobalSearchMessage")
            label.setWordWrap(True)
            self.search_suggestions_layout.addWidget(label)
        else:
            for result in self._search_results:
                button = QPushButton(
                    f"{result['title']}\n{result['description']}"
                )
                button.setObjectName("GlobalSearchResult")
                button.setCursor(
                    Qt.CursorShape.PointingHandCursor
                )
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(
                    lambda _checked=False, selected=result:
                    self._open_global_search_result(selected)
                )
                self.search_suggestions_layout.addWidget(button)

        result_count = self.search_suggestions_layout.count()
        anchor = self.mapFromGlobal(
            self.global_search_input.mapToGlobal(
                QPoint(0, self.global_search_input.height())
            )
        )
        avail_height = max(120, self.height() - anchor.y() - 12)
        scroll_height = min(348, max(58, avail_height - 16), max(58, result_count * 58))
        self.search_suggestions_scroll.setFixedHeight(scroll_height)

        popup_width = min(
            max(260, self.global_search_input.width()),
            max(260, self.width() - 24),
        )
        self.search_suggestions.setFixedWidth(popup_width)
        self.search_suggestions.adjustSize()
        anchor.setX(
            max(
                8,
                min(
                    anchor.x(),
                    max(8, self.width() - self.search_suggestions.width() - 8),
                ),
            )
        )
        anchor.setY(
            max(
                8,
                min(
                    anchor.y(),
                    max(8, self.height() - self.search_suggestions.height() - 8),
                ),
            )
        )
        self.search_suggestions.move(anchor)
        self.search_suggestions.raise_()
        self.search_suggestions.show()

    def _open_global_search_result(self, result):
        self.global_search_input.setText(result["id"])
        self._search_debounce_timer.stop()
        self._search_results = []
        self.search_suggestions.hide()

        page_index = result["page"]
        self.switch_page(page_index)

        if page_index == 1:
            page = self.catalog_view
            page.set_catalog_filter("ALL")
            page.search_input.setText(result["id"])
            page.select_book_by_id(result["id"])
        elif page_index == 2:
            page = self.usermanagement_view
            page.set_user_filter("ALL")
            page.branch_combo.setCurrentIndex(0)
            page.search_input.setText(result["id"])
            self._select_table_row_by_id(page, result["id"])
        elif page_index == 3:
            page = self.circulation_view
            page.set_status_filter("ALL")
            page.search_input.setText(result["id"])
            self._select_table_row_by_id(page, result["id"])

    @staticmethod
    def _select_table_row_by_id(page, record_id):
        for row in range(page.table.rowCount()):
            item = page.table.item(row, 0)
            if item and item.text() == str(record_id):
                page.table.selectRow(row)
                page.table.scrollToItem(item)
                return

    def _issue_from_header(self):
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.open_issue_dialog()
            self.refresh_active_page()

    def _return_from_header(self):
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.open_return_dialog()
            self.refresh_active_page()

    def refresh_active_page(self):
        if hasattr(self, "pages"):
            idx = self.pages.currentIndex()
            if idx != 0:
                self.refresh_page(idx, force=True)

    def _toggle_theme_from_header(self):
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.toggle_theme()

    def show_help(self):
        HelpDialog(self).exec()

    # ========================================================
    # FLOATING QUICK ACTIONS TRIGGER & CLASSIC DRAWER
    # ========================================================

    def _init_quick_actions_fab(self):
        self._quick_actions_fab_compact = None
        self.quick_actions_fab = QPushButton("⚡ Quick Actions", self)
        self.quick_actions_fab.setObjectName("FloatingQuickActionsBtn")
        self.quick_actions_fab.setCheckable(True)
        self.quick_actions_fab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.quick_actions_fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_actions_fab.setToolTip("Open Quick Desk Actions (Ctrl+K)")
        self.quick_actions_fab.clicked.connect(
            lambda: self.toggle_quick_actions_popup(self.quick_actions_fab)
        )
        self._style_quick_actions_fab()
        self._position_quick_actions_fab()
        self.quick_actions_fab.raise_()
        self.quick_actions_fab.show()

    def _style_quick_actions_fab(self, colors=None):
        if not hasattr(self, "quick_actions_fab"):
            return
        colors = colors or self.get_theme_colors()
        is_dark = self._active_theme_name() == "Dark"
        surface = colors.get("surface", "#111A2E")
        surface_alt = colors.get("surface_alt", "#182542")
        surface_elevated = colors.get("surface_elevated", surface_alt)
        text = colors.get("text", "#F8FAFC")
        primary = colors.get("primary", "#3B82F6")
        primary_hover = colors.get("primary_hover", "#2563EB")
        indigo = colors.get("indigo", "#818CF8")
        cyan = colors.get("cyan", "#22D3EE")
        primary_soft = colors.get("primary_soft", surface_alt)
        indigo_soft = colors.get("indigo_soft", surface_alt)
        idle_top = surface_alt if is_dark else surface
        idle_bot = surface_elevated if is_dark else surface_alt
        hover_border = cyan if is_dark else primary

        self.quick_actions_fab.setStyleSheet(f"""
            QPushButton#FloatingQuickActionsBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {idle_top},
                    stop:1 {idle_bot}
                );
                color: {text};
                border: 1.5px solid {indigo};
                border-radius: 14px;
                padding: 0px 10px;
                font-size: 10px;
                font-weight: 700;
            }}
            QPushButton#FloatingQuickActionsBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {indigo_soft},
                    stop:1 {primary_soft}
                );
                color: {text if is_dark else primary_hover};
                border: 1.5px solid {hover_border};
            }}
            QPushButton#FloatingQuickActionsBtn:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {primary},
                    stop:1 {indigo}
                );
                color: #FFFFFF;
                border: 1.5px solid {cyan if is_dark else primary_hover};
            }}
            QPushButton#FloatingQuickActionsBtn[compact="true"] {{
                border-radius: 17px;
                padding: 0px;
                font-size: 14px;
            }}
        """)

    def _position_quick_actions_fab(self):
        if not hasattr(self, "quick_actions_fab"):
            return
        is_compact = self.width() < 900
        if is_compact != getattr(self, "_quick_actions_fab_compact", None):
            self._quick_actions_fab_compact = is_compact
            self.quick_actions_fab.setText("⚡" if is_compact else "⚡ Quick Actions")
            self.quick_actions_fab.setProperty("compact", is_compact)
            self.quick_actions_fab.style().unpolish(self.quick_actions_fab)
            self.quick_actions_fab.style().polish(self.quick_actions_fab)

        if is_compact:
            fab_w, fab_h = 34, 34
            margin_right, margin_bottom = 16, 8
        else:
            fab_w, fab_h = 126, 28
            margin_right, margin_bottom = 18, 10

        self.quick_actions_fab.setFixedSize(fab_w, fab_h)
        min_y = (self.topbar.height() + 6) if hasattr(self, "topbar") else 66
        x = max(12, self.width() - fab_w - margin_right)
        y = max(min_y, self.height() - fab_h - margin_bottom)
        self.quick_actions_fab.move(x, y)
        self.quick_actions_fab.raise_()

    def _init_quick_actions_popup(self):
        self._quick_actions_anchor = None
        self._quick_actions_event_filter_installed = False

        self.quick_actions_popup = QFrame(self)
        self.quick_actions_popup.setObjectName("QuickActionsPopup")
        self.quick_actions_popup.hide()
        self.quick_actions_popup.setMinimumWidth(246)
        self.quick_actions_popup.setMaximumWidth(282)

        outer = QVBoxLayout(self.quick_actions_popup)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 0, 2)
        header_row.setSpacing(6)

        self.quick_actions_title = QLabel("Quick Desk Actions")
        self.quick_actions_title.setObjectName("QuickActionsPopupTitle")
        header_row.addWidget(self.quick_actions_title, 1)

        self.quick_actions_page_badge = QLabel("Dashboard")
        self.quick_actions_page_badge.setObjectName("QuickActionsPageBadge")
        header_row.addWidget(self.quick_actions_page_badge)

        self.quick_actions_close_btn = QPushButton("✕")
        self.quick_actions_close_btn.setObjectName("QuickActionsCloseBtn")
        self.quick_actions_close_btn.setToolTip("Close Quick Desk Actions (Esc)")
        self.quick_actions_close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.quick_actions_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_actions_close_btn.setFixedSize(22, 22)
        self.quick_actions_close_btn.clicked.connect(self.hide_quick_actions_popup)
        header_row.addWidget(self.quick_actions_close_btn)
        outer.addLayout(header_row)

        self.quick_actions_scroll = QScrollArea(self.quick_actions_popup)
        self.quick_actions_scroll.setObjectName("QuickActionsScroll")
        self.quick_actions_scroll.setWidgetResizable(True)
        self.quick_actions_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.quick_actions_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.quick_actions_scroll.viewport().setObjectName("QuickActionsViewport")

        self.quick_actions_container = QWidget()
        self.quick_actions_container.setObjectName("QuickActionsBody")
        self.quick_actions_body = QVBoxLayout(self.quick_actions_container)
        self.quick_actions_body.setContentsMargins(0, 0, 2, 0)
        self.quick_actions_body.setSpacing(5)
        self.quick_actions_scroll.setWidget(self.quick_actions_container)
        outer.addWidget(self.quick_actions_scroll, 1)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._quick_actions_event_filter_installed = True

        self._style_quick_actions_popup()

    def _style_quick_actions_popup(self, colors=None):
        if not hasattr(self, "quick_actions_popup"):
            return
        colors = colors or self.get_theme_colors()
        is_dark = self._active_theme_name() == "Dark"
        surface = colors.get("surface", "#111A2E")
        surface_alt = colors.get("surface_alt", "#182542")
        surface_elevated = colors.get("surface_elevated", "#1F2F52")
        text = colors.get("text", "#F8FAFC")
        muted = colors.get("muted", "#9BB0CE")
        border = colors.get("border", "#28385C")
        border_bright = colors.get("border_bright", "#384F82")
        primary = colors.get("primary", "#3B82F6")
        indigo = colors.get("indigo", "#818CF8")
        cyan = colors.get("cyan", "#22D3EE")
        success = colors.get("success", "#10B981")
        warning = colors.get("warning", "#F59E0B")
        purple = colors.get("purple", "#A78BFA")
        danger = colors.get("danger", "#F43F5E")
        primary_soft = colors.get("primary_soft", surface_alt)
        indigo_soft = colors.get("indigo_soft", surface_alt)
        cyan_soft = colors.get("cyan_soft", surface_alt)
        success_soft = colors.get("success_soft", surface_alt)
        warning_soft = colors.get("warning_soft", surface_alt)
        purple_soft = colors.get("purple_soft", surface_alt)
        danger_soft = colors.get("danger_soft", surface_alt)
        drawer_border = indigo if is_dark else border_bright

        self.quick_actions_popup.setStyleSheet(f"""
            QFrame#QuickActionsPopup {{
                background-color: {surface};
                border: 1.5px solid {drawer_border};
                border-top: 3px solid {purple};
                border-radius: 12px;
            }}
            QLabel#QuickActionsPopupTitle {{
                color: {text};
                font-size: 12px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#QuickActionsPageBadge {{
                background: {indigo_soft};
                color: {indigo};
                border: 1px solid {indigo};
                border-radius: 7px;
                padding: 2px 6px;
                font-size: 9px;
                font-weight: 800;
            }}
            QPushButton#QuickActionsCloseBtn {{
                background: {danger_soft};
                color: {danger};
                border: 1px solid {danger};
                border-radius: 7px;
                padding: 0px;
                font-size: 10px;
                font-weight: 800;
            }}
            QPushButton#QuickActionsCloseBtn:hover {{
                background: {danger};
                color: #FFFFFF;
            }}
            QScrollArea#QuickActionsScroll,
            QWidget#QuickActionsViewport,
            QWidget#QuickActionsBody {{
                background: transparent;
                border: none;
            }}
            QLabel#QuickSectionLabel {{
                color: {cyan if is_dark else primary};
                font-size: 9px;
                font-weight: 800;
                padding: 3px 2px 1px 2px;
                background: transparent;
            }}
            QPushButton#QuickActionRow {{
                background: {surface_alt};
                border: 1px solid {border};
                border-radius: 8px;
                text-align: left;
            }}
            QPushButton#QuickActionRow:hover {{
                background: {surface_elevated};
                border-color: {primary};
            }}
            QPushButton#QuickActionRow[actionAccent="book"]:hover {{ border-color: {success}; }}
            QPushButton#QuickActionRow[actionAccent="user"]:hover {{ border-color: {purple}; }}
            QPushButton#QuickActionRow[actionAccent="barcode"]:hover {{ border-color: {cyan}; }}
            QPushButton#QuickActionRow[actionAccent="scan"]:hover {{ border-color: {warning}; }}
            QPushButton#QuickActionRow[actionAccent="history"]:hover {{ border-color: {indigo}; }}
            QPushButton#QuickActionRow[actionAccent="refresh"]:hover {{ border-color: {primary}; }}
            QLabel#QuickActionIcon {{
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#QuickActionIcon[actionAccent="book"] {{
                color: {success};
                background: {success_soft};
                border: 1px solid {success};
            }}
            QLabel#QuickActionIcon[actionAccent="user"] {{
                color: {purple};
                background: {purple_soft};
                border: 1px solid {purple};
            }}
            QLabel#QuickActionIcon[actionAccent="barcode"] {{
                color: {cyan};
                background: {cyan_soft};
                border: 1px solid {cyan};
            }}
            QLabel#QuickActionIcon[actionAccent="scan"] {{
                color: {warning};
                background: {warning_soft};
                border: 1px solid {warning};
            }}
            QLabel#QuickActionIcon[actionAccent="history"] {{
                color: {indigo};
                background: {indigo_soft};
                border: 1px solid {indigo};
            }}
            QLabel#QuickActionIcon[actionAccent="refresh"] {{
                color: {primary};
                background: {primary_soft};
                border: 1px solid {primary};
            }}
            QLabel#QuickActionText {{
                color: {text};
                background: transparent;
                font-size: 10px;
                font-weight: 600;
            }}
            QLabel#QuickActionKeycap {{
                color: {muted};
                background: {surface};
                border: 1px solid {border_bright};
                border-radius: 5px;
                padding: 2px 5px;
                font-size: 8px;
                font-weight: 700;
            }}
        """)

    def _current_page_label(self):
        idx = self.pages.currentIndex() if hasattr(self, "pages") else 0
        names = (
            "Dashboard",
            "Books Details",
            "Users Details",
            "Circulation",
            "Reports",
            "Settings",
        )
        return names[idx] if 0 <= idx < len(names) else "Workspace"

    def _current_page_short_label(self):
        idx = self.pages.currentIndex() if hasattr(self, "pages") else 0
        names = (
            "Dashboard",
            "Books",
            "Users",
            "Circulation",
            "Reports",
            "Settings",
        )
        return names[idx] if 0 <= idx < len(names) else "Page"

    def _build_quick_action_groups(self):
        idx = self.pages.currentIndex() if hasattr(self, "pages") else 0
        page_label = self._current_page_label()
        short_page = self._current_page_short_label()

        if idx == 0:
            return [
                (
                    "",
                    [
                        ("📚", "Add New Book", "Register a new book in catalog", "Ctrl+B", "book", self.dashboard_view.open_bookform),
                        ("👤", "Add New User", "Register a student or faculty member", "Ctrl+U", "user", self.dashboard_view.open_userform),
                        ("▦", "Generate Barcode", "Create printable Code128 book label", "Ctrl+G", "barcode", self.dashboard_view.open_bargenerate_form),
                        ("⌁", "Quick Scan", "USB / camera instant issue, renew, or return", "Ctrl+Shift+K", "scan", self.dashboard_view.open_quick_scan),
                        ("◷", "Activity History", "Browse and filter loan history", "Ctrl+H", "history", self.dashboard_view.open_activity_history),
                        ("+", "Issue Book", "Open book checkout dialog", "Ctrl+I", "refresh", self._issue_from_header),
                        ("↩", "Return Book", "Open book return and fine dialog", "Ctrl+R", "book", self._return_from_header),
                        ("↻", "Refresh Dashboard", "Reload KPIs, charts, and activity", "F5", "refresh", self.dashboard_view.refresh_dashboard),
                    ],
                ),
            ]

        contextual_map = {
            1: [
                ("📚", "Add New Book", "Create a new catalog book record", "Ctrl+B", "book", self.catalog_view.add_book),
                ("📤", "Export Books CSV", "Download visible book catalog", "", "barcode", self.catalog_view.export_books_to_csv),
            ],
            2: [
                ("👤", "Add New User", "Register a student or faculty member", "Ctrl+U", "user", self.usermanagement_view.add_user),
                ("💬", "Complaint Inbox", "Review and resolve member complaints", "", "scan", self.usermanagement_view.open_complaint_inbox),
            ],
            3: [
                ("💳", "Pending Fines Desk", "Collect, waive, or review unpaid fines", "", "scan", self.circulation_view.open_fines_desk),
                ("📤", "Export Log CSV", "Save filtered circulation log", "", "barcode", self.circulation_view.export_csv),
            ],
            4: [
                ("📤", "Export Report CSV", "Save circulation & fines summary", "", "barcode", self.reports_view.export_csv),
                ("📅", "Last 30 Days", "Switch report window to past 30 days", "", "history", lambda: self.reports_view.set_quick_range(30)),
            ],
            5: [
                ("💾", "Save All Settings", "Persist policies, theme & preferences", "", "book", self.settings_view.save_settings),
                ("🏛", "Departments", "Manage college branches & courses", "", "history", self.settings_view.open_department_manager),
            ],
        }

        return [
            (
                f"{page_label} Actions",
                contextual_map.get(idx, []),
            ),
            (
                "Desk Shortcuts",
                [
                    ("+", "Issue Book", "Open checkout dialog from any page", "Ctrl+I", "refresh", self._issue_from_header),
                    ("↩", "Return Book", "Open return dialog from any page", "Ctrl+R", "book", self._return_from_header),
                    ("⌁", "Quick Scan", "USB / camera instant issue, renew, or return", "Ctrl+Shift+K", "scan", self.dashboard_view.open_quick_scan),
                    ("▦", "Generate Barcode", "Generate printable book barcode", "Ctrl+G", "barcode", self.dashboard_view.open_bargenerate_form),
                    ("↻", f"Refresh {short_page}", f"Reload {page_label} data", "F5", "history", lambda: self.refresh_page(self.pages.currentIndex(), force=True)),
                ],
            ),
        ]

    def _rebuild_quick_actions_popup(self):
        if not hasattr(self, "quick_actions_body"):
            return
        while self.quick_actions_body.count():
            item = self.quick_actions_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setObjectName("")
                for child_btn in w.findChildren(QPushButton):
                    child_btn.setObjectName("")
                w.deleteLater()
            elif item.layout() is not None:
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.setObjectName("")
                        for child_btn in sw.findChildren(QPushButton):
                            child_btn.setObjectName("")
                        sw.deleteLater()

        self.quick_actions_page_badge.setText(self._current_page_label())

        for group_title, items in self._build_quick_action_groups():
            if not items:
                continue
            if group_title:
                sec_lbl = QLabel(group_title)
                sec_lbl.setObjectName("QuickSectionLabel")
                self.quick_actions_body.addWidget(sec_lbl)

            for icon, label, desc, shortcut, accent, callback in items:
                button = QPushButton(self.quick_actions_container)
                button.setObjectName("QuickActionRow")
                button.setProperty("actionAccent", accent)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setAccessibleName(label)
                button.setToolTip(desc)
                button.setMinimumWidth(0)
                button.setFixedHeight(33)
                button.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                button.clicked.connect(
                    lambda _checked=False, cb=callback: self._run_quick_action(cb)
                )

                row_layout = QHBoxLayout(button)
                row_layout.setContentsMargins(7, 3, 7, 3)
                row_layout.setSpacing(6)

                icon_label = QLabel(icon, button)
                icon_label.setObjectName("QuickActionIcon")
                icon_label.setProperty("actionAccent", accent)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon_label.setFixedSize(22, 22)
                icon_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                row_layout.addWidget(icon_label)

                text_label = QLabel(label, button)
                text_label.setObjectName("QuickActionText")
                text_label.setMinimumWidth(0)
                text_label.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                row_layout.addWidget(text_label, 1)

                keycap = QLabel(shortcut, button)
                keycap.setObjectName("QuickActionKeycap")
                keycap.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                row_layout.addWidget(keycap)
                keycap.setVisible(bool(shortcut))

                self.quick_actions_body.addWidget(button)

        self.quick_actions_body.activate()
        self.quick_actions_container.adjustSize()
        if hasattr(self, "quick_actions_scroll"):
            self.quick_actions_scroll.verticalScrollBar().setValue(0)

    def _run_quick_action(self, callback):
        self.hide_quick_actions_popup()
        if callable(callback):
            callback()

    def _position_quick_actions_popup(self, anchor_widget=None):
        if not hasattr(self, "quick_actions_popup"):
            return
        self._position_quick_actions_fab()
        popup_w = min(278, max(246, self.width() - 28))
        if hasattr(self, "quick_actions_body"):
            self.quick_actions_body.activate()
        if hasattr(self, "quick_actions_container"):
            self.quick_actions_container.ensurePolished()
            content_h = max(
                self.quick_actions_container.sizeHint().height(),
                self.quick_actions_container.minimumSizeHint().height(),
            )
        else:
            content_h = 300
        desired_h = content_h + 62

        min_y = (self.topbar.height() + 6) if hasattr(self, "topbar") else 66
        anchor = anchor_widget or getattr(self, "quick_actions_fab", None)

        if anchor is not None and anchor.isVisible():
            top_left = self.mapFromGlobal(anchor.mapToGlobal(QPoint(0, 0)))
            max_avail_above = max(160, top_left.y() - min_y - 8)
            popup_h = min(desired_h, max_avail_above)
            x = max(12, min(top_left.x() + anchor.width() - popup_w, self.width() - popup_w - 14))
            y = max(min_y, top_left.y() - popup_h - 8)
        else:
            max_avail = max(160, self.height() - min_y - 54)
            popup_h = min(desired_h, max_avail)
            x = max(12, self.width() - popup_w - 18)
            y = max(min_y, self.height() - popup_h - 46)

        self.quick_actions_popup.resize(popup_w, popup_h)
        self.quick_actions_popup.move(x, y)

    def show_quick_actions_popup(self, anchor_widget=None):
        if not hasattr(self, "quick_actions_popup"):
            return
        if hasattr(self, "search_suggestions"):
            self.search_suggestions.hide()
        self._quick_actions_anchor = anchor_widget or getattr(self, "quick_actions_fab", None)
        self._rebuild_quick_actions_popup()
        self._position_quick_actions_popup(self._quick_actions_anchor)
        self.quick_actions_popup.raise_()
        self.quick_actions_popup.show()
        if hasattr(self, "quick_actions_fab"):
            self.quick_actions_fab.setChecked(True)
            self.quick_actions_fab.raise_()

    def hide_quick_actions_popup(self):
        if hasattr(self, "quick_actions_popup") and self.quick_actions_popup.isVisible():
            self.quick_actions_popup.hide()
        if hasattr(self, "quick_actions_fab"):
            self.quick_actions_fab.setChecked(False)

    def toggle_quick_actions_popup(self, anchor_widget=None):
        if not hasattr(self, "quick_actions_popup"):
            return
        if self.quick_actions_popup.isVisible():
            self.hide_quick_actions_popup()
        else:
            self.show_quick_actions_popup(anchor_widget)

    def _is_quick_action_trigger_widget(self, widget):
        while widget is not None:
            if widget is getattr(self, "quick_actions_fab", None):
                return True
            if widget.objectName() == "FloatingQuickActionsBtn":
                return True
            widget = widget.parentWidget()
        return False

    def eventFilter(self, watched, event):
        if sip.isdeleted(self):
            return False
        if hasattr(self, "quick_actions_popup") and self.quick_actions_popup.isVisible():
            ev_type = event.type()
            if (
                ev_type == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Escape
                and QApplication.activeModalWidget() is None
            ):
                self.hide_quick_actions_popup()
                return True
            if ev_type == QEvent.Type.MouseButtonPress:
                global_pos = event.globalPosition().toPoint()
                popup_rect = QRect(
                    self.quick_actions_popup.mapToGlobal(QPoint(0, 0)),
                    self.quick_actions_popup.size(),
                )
                if not popup_rect.contains(global_pos):
                    target_widget = QApplication.widgetAt(global_pos)
                    if not self._is_quick_action_trigger_widget(target_widget):
                        self.hide_quick_actions_popup()
        return super().eventFilter(watched, event)

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
            ("📊  Dashboard", 0, "dashboard"),
            ("📚  Books Details", 1, "books"),
            ("👥  Users Details", 2, "users"),
            ("🔄  Circulation", 3, "circulation"),
            ("📈  Reports", 4, "reports"),
            ("⚙️  Settings", 5, "settings"),
        ]

        self.nav_buttons = []
        self.nav_icons = {}

        for title, index, nav_role in navigation_items:

            button = QPushButton(title)
            icon, _label = title.split("  ", 1)
            self.nav_icons[index] = (icon, title)
            button.setToolTip(title)
            button.setAccessibleName(title)

            button.setObjectName(
                "NavigationButton"
            )
            button.setProperty("navRole", nav_role)

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

        initial_stamp = self._page_refresh_stamp()
        self._page_loaded_stamps = (
            {idx: initial_stamp for idx in range(len(self.page_views))}
            if initial_stamp is not None
            else {}
        )

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

    def _current_data_stamp(self):
        getter = getattr(self.db, "get_data_stamp", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return None
        return None

    def _active_theme_stamp(self):
        manager = getattr(self, "theme_manager", None)
        if manager is None:
            return None
        try:
            return manager.get_active_theme()
        except Exception:
            return None

    def _page_refresh_stamp(self):
        data_stamp = self._current_data_stamp()
        if data_stamp is None:
            return None
        return (data_stamp, self._active_theme_stamp())

    def refresh_page(self, index, force=True):

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

        current_stamp = self._page_refresh_stamp()
        if not force and current_stamp is not None:
            loaded_stamps = getattr(self, "_page_loaded_stamps", None)
            if loaded_stamps is not None and loaded_stamps.get(index) == current_stamp:
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
                    updated_stamp = self._page_refresh_stamp()
                    if updated_stamp is not None:
                        if not hasattr(self, "_page_loaded_stamps"):
                            self._page_loaded_stamps = {}
                        self._page_loaded_stamps[index] = updated_stamp

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

        self.hide_quick_actions_popup()

        self.pages.setCurrentIndex(
            index
        )

        self.refresh_page(index, force=False)

        for button, button_index in self.nav_buttons:

            button.setChecked(
                button_index == index
            )

        self._position_quick_actions_fab()

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

        self._apply_responsive_topbar()
        self._position_quick_actions_fab()
        if hasattr(self, "quick_actions_popup") and self.quick_actions_popup.isVisible():
            self._position_quick_actions_popup(self._quick_actions_anchor)
            self.quick_actions_popup.raise_()

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

    def showEvent(self, event):
        super().showEvent(event)
        self._position_quick_actions_fab()

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
    # SHUTDOWN & EXIT CONFIRMATION
    # ========================================================

    def _shutdown_background_workers(self):
        if getattr(self, "_workers_stopped", False):
            return
        self._workers_stopped = True

        if getattr(self, "_quick_actions_event_filter_installed", False):
            app = QApplication.instance()
            if app is not None:
                try:
                    app.removeEventFilter(self)
                except (RuntimeError, AttributeError):
                    pass
            self._quick_actions_event_filter_installed = False

        timer = getattr(self, "_search_debounce_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except (RuntimeError, AttributeError):
                pass

        if self.theme_manager:
            signal = getattr(self.theme_manager, "themeChanged", None)
            if signal:
                try:
                    signal.disconnect(self.apply_shell_theme)
                except (TypeError, RuntimeError):
                    pass

        sync_manager = getattr(self, "email_sync_manager", None)
        if sync_manager is not None:
            try:
                sync_manager.stop(wait_ms=3500)
            except (RuntimeError, AttributeError):
                pass

        settings_view = getattr(self, "settings_view", None)
        if settings_view is not None and hasattr(settings_view, "stop_workers"):
            try:
                settings_view.stop_workers(wait_ms=1000)
            except (RuntimeError, AttributeError):
                pass

        for view in getattr(self, "page_views", ()):
            if view is not None:
                try:
                    view.close()
                except (RuntimeError, AttributeError):
                    pass

    def closeEvent(self, event):
        self._shutdown_background_workers()
        super().closeEvent(event)

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
            self._shutdown_background_workers()
            app = QApplication.instance()

            if app:
                app.quit()

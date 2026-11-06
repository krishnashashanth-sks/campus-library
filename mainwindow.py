
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
    QLineEdit,
    QSizePolicy,
    QMessageBox,
    QApplication,
    QScrollArea,
)

from PyQt6.QtGui import QIcon, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import (
    Qt,
    QPoint,
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
                    font-size: 14px;
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

                    QLabel#VersionBadge {{
                        background-color: {surface_alt};
                        color: {primary};
                        font-size: 9px;
                        font-weight: 700;
                        padding: 3px 7px;
                        border-radius: 8px;
                        border: 1px solid {border};
                    }}

                    QLineEdit#HeaderSearch {{
                        background-color: {input_color};
                        color: {text};
                        border: 1px solid {border};
                        border-radius: 8px;
                        padding: 7px 11px;
                        min-height: 20px;
                        font-size: 11px;
                    }}

                    QLineEdit#HeaderSearch:focus {{
                        border-color: {primary};
                    }}

                    QPushButton#HeaderIssue,
                    QPushButton#HeaderReturn,
                    QPushButton#HeaderTheme,
                    QPushButton#HeaderHelp {{
                        color: #FFFFFF;
                        border: none;
                        border-radius: 7px;
                        padding: 7px 10px;
                        min-height: 20px;
                        font-size: 10px;
                        font-weight: 700;
                    }}

                    QPushButton#HeaderIssue {{
                        background-color: {primary};
                    }}

                    QPushButton#HeaderIssue:hover {{
                        background-color: {primary_hover};
                    }}

                    QPushButton#HeaderReturn {{
                        background-color: {success};
                    }}

                    QPushButton#HeaderReturn:hover {{
                        background-color: {colors.get('success_hover', success)};
                    }}

                    QPushButton#HeaderTheme {{
                        background-color: {surface_alt};
                        color: {text};
                        border: 1px solid {border};
                    }}

                    QPushButton#HeaderTheme:hover {{
                        border-color: {primary};
                    }}

                    QPushButton#HeaderHelp {{
                        background-color: {surface_alt};
                        color: {text};
                        border: 1px solid {border};
                    }}

                    QPushButton#HeaderHelp:hover {{
                        border-color: {primary};
                    }}

                    QLabel#SystemStatusBadge {{
                        background-color: {surface_alt};
                        color: {success};
                        font-size: 10px;
                        font-weight: 700;
                        padding: 6px 10px;
                        border-radius: 12px;
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

            if hasattr(self, "theme_button"):
                self.theme_button.setText(
                    "☀ Light" if active_theme == "Dark" else "☾ Dark"
                )

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
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        search_shortcut.activated.connect(
            self.global_search_input.setFocus
        )
        self._global_search_shortcut = search_shortcut

        self._application_shortcuts = []
        shortcut_actions = (
            ("Ctrl+I", self.dashboard_view.open_issue_dialog),
            ("Ctrl+R", self.dashboard_view.open_return_dialog),
            ("Ctrl+B", self.dashboard_view.open_bookform),
            ("Ctrl+U", self.dashboard_view.open_userform),
            ("Ctrl+G", self.dashboard_view.open_bargenerate_form),
            ("Ctrl+Shift+K", self.dashboard_view.open_quick_scan),
            ("Ctrl+H", self.dashboard_view.open_activity_history),
            ("F5", self.dashboard_view.refresh_dashboard),
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

        top_layout = QHBoxLayout(
            topbar
        )

        top_layout.setContentsMargins(
            14, 0, 16, 0
        )

        top_layout.setSpacing(9)

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

        top_layout.addWidget(
            title_label
        )

        version_badge = QLabel(f"v{get_app_version()}")
        version_badge.setObjectName("VersionBadge")
        top_layout.addWidget(version_badge)

        self.global_search_input = QLineEdit()
        self.global_search_input.setObjectName("HeaderSearch")
        self.global_search_input.setPlaceholderText(
            "Search books, Roll No (e.g., 24001-CS-097), author, or ISBN..."
        )
        self.global_search_input.setClearButtonEnabled(True)
        self.global_search_input.setMinimumWidth(200)
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
        self.search_suggestions.setMinimumWidth(340)
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
        self.issue_header_button.clicked.connect(
            self._issue_from_header
        )
        top_layout.addWidget(self.issue_header_button)

        self.return_header_button = QPushButton("Return Book")
        self.return_header_button.setObjectName("HeaderReturn")
        self.return_header_button.clicked.connect(
            self._return_from_header
        )
        top_layout.addWidget(self.return_header_button)

        self.theme_button = QPushButton("☀ Light")
        self.theme_button.setObjectName("HeaderTheme")
        self.theme_button.clicked.connect(
            self._toggle_theme_from_header
        )
        top_layout.addWidget(self.theme_button)

        self.help_button = QPushButton("Help")
        self.help_button.setObjectName("HeaderHelp")
        self.help_button.setToolTip("Open application help (F1)")
        self.help_button.clicked.connect(self.show_help)
        top_layout.addWidget(self.help_button)

        self.status_badge = QLabel("● Email sync checking")

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

    def update_email_status(self, message):
        self.status_badge.setText(f"● {message}")
        if message.startswith("Email sync active"):
            color = "#16A34A"
        elif message.startswith("Email sync running"):
            color = "#2563EB"
        else:
            color = "#D97706"
        self.status_badge.setStyleSheet(
            f"QLabel#SystemStatusBadge {{ color: {color}; }}"
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
        self.search_suggestions.setStyleSheet(f"""
            QFrame#GlobalSearchSuggestions {{
                background-color: {colors['surface']};
                border: 1px solid {colors['border']};
                border-radius: 9px;
            }}
            QPushButton#GlobalSearchResult {{
                background-color: transparent;
                color: {colors['text']};
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 8px 10px;
                min-height: 42px;
                font-size: 11px;
            }}
            QPushButton#GlobalSearchResult:hover {{
                background-color: {colors['surface_alt']};
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
        self.search_suggestions_scroll.setFixedHeight(
            min(348, max(58, result_count * 58))
        )
        popup_width = max(340, self.global_search_input.width())
        screen = self.screen()
        if screen:
            popup_width = min(
                popup_width,
                screen.availableGeometry().width(),
            )
        self.search_suggestions.setFixedWidth(popup_width)
        self.search_suggestions.adjustSize()
        anchor = self.mapFromGlobal(
            self.global_search_input.mapToGlobal(
                QPoint(0, self.global_search_input.height())
            )
        )
        anchor.setX(
            max(
                0,
                min(
                    anchor.x(),
                    self.width() - self.search_suggestions.width(),
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

    def _return_from_header(self):
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.open_return_dialog()

    def _toggle_theme_from_header(self):
        if hasattr(self, "dashboard_view"):
            self.dashboard_view.toggle_theme()

    def show_help(self):
        HelpDialog(self).exec()

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

        self.refresh_page(index)

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

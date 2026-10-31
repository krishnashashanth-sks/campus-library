
import csv
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QSizePolicy,
    QFrame,
    QLabel,
    QMessageBox,
    QFormLayout,
    QMenu,
    QFileDialog,
    QComboBox,
    QAbstractItemView,
    QTabWidget,
)

from dialogs import UserDialog, ViewBooksDialog
from utils import clear_layout


# ============================================================
# INTERACTIVE KPI CARD
# ============================================================

class ClickableMetricCard(QFrame):
    """Clickable KPI card for filtering the user directory."""

    def __init__(
        self,
        filter_key,
        title,
        value="0",
        accent="#3B82F6",
        on_click_callback=None,
        parent=None,
    ):
        super().__init__(parent)

        self.filter_key = filter_key
        self.accent = accent
        self.on_click_callback = on_click_callback
        self.selected = False

        self.setObjectName("MetricCard")
        self.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        self.setMinimumHeight(84)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")
        self.lbl_title.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setObjectName("MetricValue")
        self.lbl_value.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

        self.apply_style()

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.apply_style()

    def apply_style(self):
        if self.selected:
            background = "palette(alternate-base)"
            border = self.accent
        else:
            background = "palette(base)"
            border = "palette(mid)"

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background-color: {background};
                border: 1px solid {border};
                border-left: 4px solid {self.accent};
                border-radius: 9px;
            }}

            QFrame#MetricCard:hover {{
                border: 2px solid {self.accent};
                border-left: 5px solid {self.accent};
            }}

            QLabel#MetricTitle {{
                background: transparent;
                border: none;
                font-size: 10px;
                font-weight: 700;
                color: palette(placeholder-text);
            }}

            QLabel#MetricValue {{
                background: transparent;
                border: none;
                font-size: 23px;
                font-weight: 800;
                color: {self.accent};
            }}
        """)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.on_click_callback
        ):
            self.on_click_callback(self.filter_key)

        super().mousePressEvent(event)


# ============================================================
# USER MANAGEMENT VIEW
# ============================================================

class UserManagementView(QWidget):

    COLORS = {
        "Dark": {
            "window": "#0B1220",
            "surface": "#111C2E",
            "surface_alt": "#17243A",
            "input": "#0F1B2D",
            "border": "#293B55",
            "text": "#E8EEF8",
            "muted": "#94A3B8",
            "primary": "#3B82F6",
            "primary_hover": "#2563EB",
            "success": "#16A34A",
            "warning": "#D97706",
            "danger": "#DC2626",
            "selection": "#1D4ED8",
        },
        "Light": {
            "window": "#F3F6FB",
            "surface": "#FFFFFF",
            "surface_alt": "#EAF0F8",
            "input": "#FFFFFF",
            "border": "#D5DEEA",
            "text": "#172033",
            "muted": "#64748B",
            "primary": "#2563EB",
            "primary_hover": "#1D4ED8",
            "success": "#15803D",
            "warning": "#B45309",
            "danger": "#B91C1C",
            "selection": "#DBEAFE",
        },
    }

    FILTERS = {
        "ALL": "All Users",
        "STUDENT": "Students",
        "FACULTY": "Faculty",
        "GUEST": "Guests",
    }

    HEADERS = [
        "PIN / ID",
        "Full Name",
        "Phone Number",
        "Role",
        "Year of Study",
        "Department",
        "Created At",
    ]

    def __init__(self, db):
        super().__init__()

        self.db = db

        self.all_users: List[Tuple] = []
        self.filtered_users: List[Tuple] = []

        self.current_filter = "ALL"

        self.theme_manager = None
        self.colors = self.COLORS["Dark"]

        self._course_duration_cache: Dict[str, int] = {}
        self._updating_table = False

        self.metric_cards = {}

        self.setObjectName("UserManagementView")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        self.init_ui()
        self.connect_theme_manager()
        self.apply_theme()
        self.load_users_to_table()

    # ========================================================
    # THEME MANAGEMENT
    # ========================================================

    def get_theme_manager(self):

        app = QApplication.instance()

        manager = (
            getattr(app, "theme_manager", None)
            if app
            else None
        )

        if manager:
            return manager

        parent = self.parent()

        while parent:

            manager = getattr(
                parent,
                "theme_manager",
                None,
            )

            if manager:
                return manager

            parent = parent.parent()

        return None

    def connect_theme_manager(self):

        self.theme_manager = self.get_theme_manager()

        if self.theme_manager:

            try:
                self.theme_manager.themeChanged.connect(
                    self.on_theme_changed
                )
            except (AttributeError, TypeError, RuntimeError):
                pass

    def _detect_os_theme(self):

        app = QApplication.instance()

        if app and hasattr(app, "styleHints"):

            try:

                if (
                    app.styleHints().colorScheme()
                    == Qt.ColorScheme.Light
                ):
                    return "Light"

            except Exception:
                pass

        return "Dark"

    def get_active_theme(self):

        manager = (
            self.theme_manager
            or self.get_theme_manager()
        )

        if manager and hasattr(
            manager,
            "get_active_theme",
        ):

            try:

                theme = manager.get_active_theme()

                if theme in self.COLORS:
                    return theme

            except Exception:
                pass

        try:

            saved = str(
                self.db.get_setting(
                    "theme_mode",
                    "Dark",
                )
            )

        except Exception:
            saved = "Dark"

        legacy_map = {
            "Dark Slate (Default)": "Dark",
            "Classic Dark": "Dark",
            "Light Modern": "Light",
        }

        saved = legacy_map.get(saved, saved)

        if saved == "System":
            return self._detect_os_theme()

        return (
            saved
            if saved in self.COLORS
            else "Dark"
        )

    def apply_theme(self, *_):

        theme = self.get_active_theme()

        self.colors = self.COLORS[theme]
        c = self.colors

        self.setStyleSheet(f"""
            QWidget#UserManagementView {{
                background-color: {c["window"]};
                color: {c["text"]};
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QLabel {{
                color: {c["text"]};
                background: transparent;
                border: none;
            }}

            QLabel#PageTitle {{
                font-size: 23px;
                font-weight: 700;
                color: {c["text"]};
            }}

            QLabel#PageSubtitle {{
                color: {c["muted"]};
                font-size: 12px;
            }}

            QLabel#SectionTitle {{
                font-size: 14px;
                font-weight: 700;
                color: {c["text"]};
            }}

            QFrame#MetricCard {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 9px;
            }}

            QLabel#MetricTitle {{
                color: {c["muted"]};
                font-size: 10px;
                font-weight: 700;
            }}

            QFrame#ToolbarCard,
            QFrame#InspectorCard {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
            }}

            QLineEdit,
            QComboBox {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 8px 11px;
                min-height: 20px;
                selection-background-color: {c["selection"]};
            }}

            QLineEdit:focus,
            QComboBox:focus {{
                border: 1px solid {c["primary"]};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                selection-background-color: {c["selection"]};
                selection-color: {c["text"]};
                border-radius: 6px;
                padding: 4px;
            }}

            QPushButton {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 600;
            }}

            QPushButton:hover {{
                border-color: {c["primary"]};
            }}

            QPushButton:disabled {{
                color: {c["muted"]};
                background-color: {c["surface_alt"]};
                border-color: {c["border"]};
            }}

            QPushButton#PrimaryButton {{
                background-color: {c["primary"]};
                color: white;
                border: none;
            }}

            QPushButton#PrimaryButton:hover {{
                background-color: {c["primary_hover"]};
            }}

            QPushButton#DangerButton {{
                background-color: rgba(220, 38, 38, 0.12);
                color: {c["danger"]};
                border: 1px solid {c["danger"]};
            }}

            QPushButton#DangerButton:hover {{
                background-color: {c["danger"]};
                color: white;
            }}

            QPushButton#FilterButton {{
                background: transparent;
                color: {c["muted"]};
                border: 1px solid transparent;
                padding: 7px 11px;
            }}

            QPushButton#FilterButton:hover {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
            }}

            QPushButton#FilterButton:checked {{
                background-color: {c["primary"]};
                color: white;
                border-color: {c["primary"]};
            }}

            QTableWidget {{
                background-color: {c["surface"]};
                alternate-background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
                gridline-color: {c["border"]};
                outline: none;
                selection-background-color: {c["selection"]};
                selection-color: {c["text"]};
            }}

            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {c["border"]};
            }}

            QHeaderView::section {{
                background-color: {c["surface_alt"]};
                color: {c["muted"]};
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid {c["border"]};
                padding: 11px 8px;
            }}

            QTabWidget::pane {{
                border: 1px solid {c["border"]};
                background: {c["surface"]};
                border-radius: 6px;
            }}

            QTabBar::tab {{
                background: {c["surface_alt"]};
                color: {c["muted"]};
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }}

            QTabBar::tab:selected {{
                background: {c["primary"]};
                color: white;
            }}

            QMenu {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 8px;
                padding: 5px;
            }}

            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}

            QMenu::item:selected {{
                background-color: {c["selection"]};
                color: {c["text"]};
            }}
        """)

        for card in self.metric_cards.values():
            card.apply_style()

        if hasattr(self, "table"):
            self.table.viewport().update()

    def on_theme_changed(self, *_):
        self.apply_theme()

    # ========================================================
    # UI CONSTRUCTION
    # ========================================================

    def init_ui(self):

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            18, 16, 18, 16
        )

        main_layout.setSpacing(12)

        # HEADER
        header = QHBoxLayout()

        title_group = QVBoxLayout()
        title_group.setSpacing(2)

        title = QLabel(
            "User Management & Directory"
        )

        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Manage student, faculty, and guest lecturer profiles, "
            "inspect active loans, and perform batch operations."
        )

        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        header.addLayout(title_group)
        header.addStretch()

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setMinimumHeight(35)
        self.refresh_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.refresh_btn.clicked.connect(
            self.load_users_to_table
        )

        header.addWidget(self.refresh_btn)

        main_layout.addLayout(header)

        # KPI STATISTICS
        self.build_statistics(main_layout)

        # SEARCH AND ACTIONS
        self.build_toolbar(main_layout)

        # FILTERS
        self.build_filters(main_layout)

        # MAIN CONTENT
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # USER TABLE
        self.table = QTableWidget()

        self.table.setObjectName("UserTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(
            self.HEADERS
        )

        self.table.setAlternatingRowColors(True)

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.table.setSortingEnabled(False)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)

        table_header = self.table.horizontalHeader()

        table_header.setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.table.customContextMenuRequested.connect(
            self.show_context_menu
        )

        self.table.itemSelectionChanged.connect(
            self.on_users_selection_changed
        )

        self.table.doubleClicked.connect(
            self.on_row_double_clicked
        )

        content_layout.addWidget(
            self.table,
            stretch=3,
        )

        # USER INSPECTOR
        self.detail_container = QFrame()
        self.detail_container.setObjectName(
            "InspectorCard"
        )

        self.detail_container.setMinimumWidth(275)
        self.detail_container.setMaximumWidth(340)

        self.detail_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        detail_layout = QVBoxLayout(
            self.detail_container
        )

        detail_layout.setContentsMargins(
            10, 10, 10, 10
        )

        detail_layout.setSpacing(8)

        self.inspector_title = QLabel(
            "User Control Center"
        )

        self.inspector_title.setObjectName(
            "SectionTitle"
        )

        detail_layout.addWidget(
            self.inspector_title
        )

        self.tab_widget = QTabWidget()

        # PROFILE TAB
        self.tab_overview = QWidget()

        self.overview_layout = QVBoxLayout(
            self.tab_overview
        )

        self.overview_layout.setContentsMargins(
            8, 8, 8, 8
        )

        self.overview_layout.setSpacing(8)

        self.tab_widget.addTab(
            self.tab_overview,
            "Profile",
        )

        # ACTIONS TAB
        self.tab_actions = QWidget()

        self.actions_layout = QVBoxLayout(
            self.tab_actions
        )

        self.actions_layout.setContentsMargins(
            8, 8, 8, 8
        )

        self.actions_layout.setSpacing(6)

        self.tab_widget.addTab(
            self.tab_actions,
            "Actions",
        )

        detail_layout.addWidget(
            self.tab_widget
        )

        content_layout.addWidget(
            self.detail_container,
            stretch=0,
        )

        main_layout.addLayout(
            content_layout,
            1,
        )

        self.show_default_inspector()

    # ========================================================
    # KPI STATISTICS
    # ========================================================

    def build_statistics(self, parent_layout):

        grid = QGridLayout()
        grid.setSpacing(9)

        definitions = [
            (
                "ALL",
                "TOTAL USERS",
                "#3B82F6",
            ),
            (
                "STUDENT",
                "STUDENTS",
                "#10B981",
            ),
            (
                "FACULTY",
                "FACULTY",
                "#38BDF8",
            ),
            (
                "GUEST",
                "GUESTS",
                "#F59E0B",
            ),
        ]

        self.metric_cards = {}

        for index, (key, title, accent) in enumerate(
            definitions
        ):

            card = ClickableMetricCard(
                filter_key=key,
                title=title,
                value="0",
                accent=accent,
                on_click_callback=self.handle_card_click,
                parent=self,
            )

            self.metric_cards[key] = card

            grid.addWidget(
                card,
                0,
                index,
            )

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)

        self.stat_total = self.metric_cards["ALL"]
        self.stat_students = self.metric_cards["STUDENT"]
        self.stat_faculty = self.metric_cards["FACULTY"]
        self.stat_guests = self.metric_cards["GUEST"]

        self.stat_total.set_selected(True)

        parent_layout.addLayout(grid)

    def handle_card_click(self, filter_key):

        self.set_user_filter(filter_key)

    def update_statistics(self):

        total = len(self.all_users)

        students = 0
        faculty = 0
        guests = 0

        for row in self.all_users:

            if len(row) < 4:
                continue

            role = str(row[3] or "").strip().lower()

            if "student" in role:
                students += 1

            elif (
                "faculty" in role
                or "staff" in role
            ):
                faculty += 1

            elif "guest" in role:
                guests += 1

        self.stat_total.set_value(f"{total:,}")
        self.stat_students.set_value(f"{students:,}")
        self.stat_faculty.set_value(f"{faculty:,}")
        self.stat_guests.set_value(f"{guests:,}")

        # Keep card selection synchronized
        for key, card in self.metric_cards.items():

            card.set_selected(
                key == self.current_filter
            )

    # ========================================================
    # TOOLBAR
    # ========================================================

    def build_toolbar(self, parent_layout):

        frame = QFrame()
        frame.setObjectName("ToolbarCard")

        layout = QHBoxLayout(frame)

        layout.setContentsMargins(
            10, 8, 10, 8
        )

        layout.setSpacing(8)

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText(
            "Search by PIN/ID, name, phone, role, or department..."
        )

        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(36)

        self.search_input.textChanged.connect(
            self.apply_filters
        )

        self.import_btn = QPushButton("Import CSV")
        self.import_btn.setObjectName("SecondaryButton")
        self.import_btn.setMinimumHeight(36)

        self.import_btn.clicked.connect(
            self.import_users_from_csv
        )

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.setMinimumHeight(36)

        self.export_btn.clicked.connect(
            self.export_users_to_csv
        )

        self.add_btn = QPushButton("+ Add New User")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setMinimumHeight(36)

        self.add_btn.clicked.connect(
            self.add_user
        )

        for button in (
            self.import_btn,
            self.export_btn,
            self.add_btn,
        ):

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

        layout.addWidget(
            self.search_input,
            1,
        )

        layout.addWidget(self.import_btn)
        layout.addWidget(self.export_btn)
        layout.addWidget(self.add_btn)

        parent_layout.addWidget(frame)

    # ========================================================
    # FILTERS
    # ========================================================

    def build_filters(self, parent_layout):

        layout = QHBoxLayout()
        layout.setSpacing(5)

        self.filter_buttons = {}

        for key, label in self.FILTERS.items():

            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)

            button.setChecked(
                key == "ALL"
            )

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(
                lambda checked=False, selected=key:
                self.set_user_filter(selected)
            )

            self.filter_buttons[key] = button

            layout.addWidget(button)

        self.year_combo = QComboBox()

        self.year_combo.addItem(
            "All Years",
            "ALL",
        )

        for number, label in [
            ("1", "1st Year"),
            ("2", "2nd Year"),
            ("3", "3rd Year"),
            ("4", "4th Year"),
            ("5", "5th Year"),
        ]:

            self.year_combo.addItem(
                label,
                number,
            )

        self.year_combo.setMinimumWidth(110)

        self.year_combo.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.year_combo.currentIndexChanged.connect(
            self.apply_filters
        )

        self.branch_combo = QComboBox()

        self.branch_combo.addItem(
            "All Departments",
            "ALL",
        )

        self.branch_combo.setMinimumWidth(150)

        self.branch_combo.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.branch_combo.currentIndexChanged.connect(
            self.apply_filters
        )

        layout.addWidget(self.year_combo)
        layout.addWidget(self.branch_combo)
        layout.addStretch()

        self.lbl_count = QLabel("0 records")

        layout.addWidget(self.lbl_count)

        parent_layout.addLayout(layout)

    # ========================================================
    # LOAD USERS
    # ========================================================

    def load_users_to_table(self):

        self._course_duration_cache.clear()

        try:

            success, rows = self.db.get_users()

            if not success:
                QMessageBox.warning(
                    self,
                    "Loading Failed",
                    "Unable to load user records.",
                )
                return

            self.all_users = list(rows or [])

            self.update_statistics()
            self.update_branch_dropdown()
            self.apply_filters()

        except Exception as exc:

            QMessageBox.critical(
                self,
                "User Loading Error",
                str(exc),
            )

    def update_branch_dropdown(self):

        current_selection = (
            self.branch_combo.currentData()
        )

        self.branch_combo.blockSignals(True)

        self.branch_combo.clear()

        self.branch_combo.addItem(
            "All Departments",
            "ALL",
        )

        try:

            departments = (
                self.db.get_all_user_departments()
            )

            if departments:

                for department in sorted(
                    set(
                        str(value).strip()
                        for value in departments
                        if value
                    ),
                    key=str.casefold,
                ):

                    self.branch_combo.addItem(
                        department,
                        department,
                    )

        except Exception:
            pass

        index = self.branch_combo.findData(
            current_selection
        )

        self.branch_combo.setCurrentIndex(
            index if index >= 0 else 0
        )

        self.branch_combo.blockSignals(False)

    # ========================================================
    # DYNAMIC ACADEMIC YEAR
    # ========================================================

    def _get_cached_course_duration(
        self,
        department: str,
    ) -> int:

        dept_key = str(
            department or ""
        ).strip()

        if dept_key not in self._course_duration_cache:

            duration = 3

            if hasattr(
                self.db,
                "get_course_duration",
            ):

                try:

                    duration = int(
                        self.db.get_course_duration(
                            dept_key
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                    AttributeError,
                ):
                    duration = 3

            self._course_duration_cache[
                dept_key
            ] = max(1, duration)

        return self._course_duration_cache[
            dept_key
        ]

    def get_dynamic_year_data(
        self,
        user_id,
        role,
        department="",
    ) -> Tuple[int, str]:

        if "student" not in str(role).lower():
            return 0, "N/A (Staff)"

        try:

            today = date.today()

            effective_year = (
                today.year - 1
                if today.month < 6
                else today.year
            )

            prefix = str(user_id).strip()[:2]

            admission_year = int(
                "20" + prefix
            )

            difference = (
                effective_year - admission_year
            )

            duration = (
                self._get_cached_course_duration(
                    department
                )
            )

            year_num = max(
                1,
                min(difference + 1, duration),
            )

            ordinals = {
                1: "1st Year",
                2: "2nd Year",
                3: "3rd Year",
                4: "4th Year",
                5: "5th Year",
            }

            label = ordinals.get(
                year_num,
                f"Year {year_num}",
            )

            if year_num == duration:
                label += " (Final)"

            return year_num, label

        except (
            ValueError,
            TypeError,
            IndexError,
        ):
            return 0, "Student"

    # ========================================================
    # FILTER LOGIC
    # ========================================================

    def set_user_filter(self, key: str):

        if key not in self.FILTERS:
            return

        self.current_filter = key

        # KPI card selection
        for filter_key, card in self.metric_cards.items():

            card.set_selected(
                filter_key == key
            )

        # Filter button selection
        for filter_key, button in self.filter_buttons.items():

            button.setChecked(
                filter_key == key
            )

        # Academic year filter
        self.year_combo.setEnabled(
            key in ("ALL", "STUDENT")
        )

        if key not in ("ALL", "STUDENT"):

            self.year_combo.blockSignals(True)
            self.year_combo.setCurrentIndex(0)
            self.year_combo.blockSignals(False)

        self.apply_filters()

    def apply_filters(self, *_):

        query = (
            self.search_input.text()
            .strip()
            .casefold()
        )

        selected_dept = (
            self.branch_combo.currentData()
        )

        selected_year = (
            self.year_combo.currentData()
        )

        filtered = []

        for row in self.all_users:

            if len(row) < 6:
                continue

            user_id, name, phone, role, department, created = row

            role_lower = str(
                role or ""
            ).lower()

            # ROLE FILTER
            if (
                self.current_filter == "STUDENT"
                and "student" not in role_lower
            ):
                continue

            if (
                self.current_filter == "FACULTY"
                and not (
                    "faculty" in role_lower
                    or "staff" in role_lower
                )
            ):
                continue

            if (
                self.current_filter == "GUEST"
                and "guest" not in role_lower
            ):
                continue

            # YEAR FILTER
            if (
                self.current_filter in ("ALL", "STUDENT")
                and selected_year not in (None, "ALL")
            ):

                year_level, _ = (
                    self.get_dynamic_year_data(
                        user_id,
                        role,
                        department,
                    )
                )

                if str(year_level) != str(selected_year):
                    continue

            # DEPARTMENT FILTER
            if selected_dept not in (None, "ALL"):

                if (
                    str(department or "").strip().casefold()
                    != str(selected_dept).strip().casefold()
                ):
                    continue

            # SEARCH FILTER
            searchable = " ".join(
                str(value or "")
                for value in row
            ).casefold()

            if query and query not in searchable:
                continue

            filtered.append(row)

        self.filtered_users = filtered

        self.populate_table(filtered)

    # ========================================================
    # TABLE POPULATION
    # ========================================================

    def populate_table(self, rows):

        previously_selected = (
            self.get_selected_user_ids()
        )

        self._updating_table = True
        self.table.blockSignals(True)

        try:

            self.table.clearContents()
            self.table.setRowCount(len(rows))

            row_to_reselect = -1
            c = self.colors

            for row_index, row_data in enumerate(rows):

                (
                    user_id,
                    name,
                    phone,
                    role,
                    department,
                    created,
                ) = row_data[:6]

                _, year_label = (
                    self.get_dynamic_year_data(
                        user_id,
                        role,
                        department,
                    )
                )

                if (
                    len(previously_selected) == 1
                    and str(user_id) == previously_selected[0]
                ):
                    row_to_reselect = row_index

                values = [
                    user_id,
                    name,
                    phone or "N/A",
                    role,
                    year_label,
                    department,
                    created,
                ]

                for column, value in enumerate(values):

                    item = QTableWidgetItem(
                        str(
                            value
                            if value is not None
                            else ""
                        )
                    )

                    item.setFlags(
                        item.flags()
                        & ~Qt.ItemFlag.ItemIsEditable
                    )

                    if column == 0:

                        item.setData(
                            Qt.ItemDataRole.UserRole,
                            str(user_id),
                        )

                    elif column == 3:

                        role_text = str(
                            role or ""
                        ).lower()

                        if "guest" in role_text:

                            item.setForeground(
                                QColor(c["warning"])
                            )

                        elif (
                            "faculty" in role_text
                            or "staff" in role_text
                        ):

                            item.setForeground(
                                QColor(c["primary"])
                            )

                        else:

                            item.setForeground(
                                QColor(c["success"])
                            )

                    elif column == 4:

                        item.setForeground(
                            QColor(c["primary"])
                        )

                    self.table.setItem(
                        row_index,
                        column,
                        item,
                    )

        finally:

            self.table.blockSignals(False)
            self._updating_table = False

        self.lbl_count.setText(
            f"{len(rows):,} records"
        )

        if row_to_reselect >= 0:

            self.table.selectRow(
                row_to_reselect
            )

            self.display_user_details(
                previously_selected[0]
            )

        else:

            self.show_default_inspector()

    def get_selected_user_ids(self) -> List[str]:

        if not hasattr(self, "table"):
            return []

        selected = []

        for index in (
            self.table.selectionModel().selectedRows()
        ):

            item = self.table.item(
                index.row(),
                0,
            )

            if not item:
                continue

            user_id = (
                item.data(Qt.ItemDataRole.UserRole)
                or item.text()
            )

            selected.append(str(user_id))

        return list(dict.fromkeys(selected))

    # ========================================================
    # INSPECTOR
    # ========================================================

    def show_default_inspector(self):

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        lbl = QLabel(
            "Select a user from the directory to inspect "
            "profile information, assigned books, and account status."
        )

        lbl.setWordWrap(True)

        lbl.setStyleSheet(
            f"color: {self.colors['muted']}; font-size: 11px;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

    def on_users_selection_changed(self):

        if self._updating_table:
            return

        selected_ids = (
            self.get_selected_user_ids()
        )

        if not selected_ids:

            self.show_default_inspector()

        elif len(selected_ids) == 1:

            self.display_user_details(
                selected_ids[0]
            )

        else:

            self.show_batch_inspector(
                selected_ids
            )

    def show_batch_inspector(
        self,
        user_ids: List[str],
    ):

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        lbl = QLabel(
            f"{len(user_ids)} users selected.\n\n"
            "Active borrowers may be protected from deletion "
            "by the database."
        )

        lbl.setWordWrap(True)

        lbl.setStyleSheet(
            f"color: {self.colors['muted']}; font-size: 11px;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

        delete_button = QPushButton(
            "Delete Selected Users"
        )

        delete_button.setObjectName(
            "DangerButton"
        )

        delete_button.setMinimumHeight(34)

        delete_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        delete_button.clicked.connect(
            lambda: self.handle_batch_delete(user_ids)
        )

        self.actions_layout.addWidget(
            delete_button
        )

        self.actions_layout.addStretch()

    def display_user_details(self, user_id: str):

        try:

            success, user = (
                self.db.get_user_details(user_id)
            )

            if not success or not user:

                self.show_default_inspector()
                return

        except Exception as exc:

            self.show_default_inspector()
            return

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        c = self.colors

        # USER LOANS
        try:

            user_books = (
                self.db.get_user_books_status(
                    user[0]
                )
                or []
            )

        except Exception:
            user_books = []

        active_loans = [
            book
            for book in user_books
            if (
                len(book) > 6
                and str(book[4]).upper() == "ISSUED"
            )
        ]

        today_str = date.today().isoformat()

        overdue_count = sum(
            1
            for book in active_loans
            if (
                book[6]
                and str(book[6])[:10] < today_str
            )
        )

        if overdue_count > 0:

            status_text = "OVERDUE LOANS"
            status_color = c["danger"]

        elif active_loans:

            status_text = "ACTIVE LOANS"
            status_color = c["warning"]

        else:

            status_text = "CLEAR ACCOUNT"
            status_color = c["success"]

        status_lbl = QLabel(
            f"{status_text}\n"
            f"{len(active_loans)} active loans "
            f"({overdue_count} overdue)"
        )

        status_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        status_lbl.setStyleSheet(f"""
            background: {status_color};
            color: white;
            border-radius: 6px;
            padding: 8px;
            font-weight: 700;
            font-size: 10px;
        """)

        self.overview_layout.addWidget(
            status_lbl
        )

        # ACADEMIC YEAR
        _, year_label = (
            self.get_dynamic_year_data(
                user[0],
                user[3],
                user[4],
            )
        )

        # PROFILE FORM
        form = QFormLayout()

        form.setContentsMargins(
            0, 4, 0, 4
        )

        form.setVerticalSpacing(8)

        fields = [
            ("ID / PIN", user[0]),
            ("Full Name", user[1]),
            ("Phone", user[2] or "N/A"),
            ("Role", user[3]),
            ("Year", year_label),
            ("Department", user[4]),
            ("Created", user[5]),
        ]

        for key, value in fields:

            key_label = QLabel(key)

            value_label = QLabel(
                str(
                    value
                    if value is not None
                    else "—"
                )
            )

            key_label.setStyleSheet(
                f"color: {c['muted']}; "
                "font-size: 10px; font-weight: 600;"
            )

            value_label.setStyleSheet(
                f"color: {c['text']}; "
                "font-size: 11px; font-weight: 600;"
            )

            value_label.setWordWrap(True)

            form.addRow(
                key_label,
                value_label,
            )

        self.overview_layout.addLayout(form)
        self.overview_layout.addStretch()

        # ACTIONS
        actions = [
            (
                "View Assigned Books",
                lambda: self.view_books(user[0]),
                "PrimaryButton",
            ),
            (
                "Edit User Profile",
                lambda: self.edit_user(user[0]),
                "SecondaryButton",
            ),
            (
                "Delete User",
                lambda: self.delete_user(user[0]),
                "DangerButton",
            ),
        ]

        for text, callback, object_name in actions:

            button = QPushButton(text)

            button.setObjectName(
                object_name
            )

            button.setMinimumHeight(34)

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(callback)

            self.actions_layout.addWidget(button)

        self.actions_layout.addStretch()

    # ========================================================
    # DOUBLE CLICK
    # ========================================================

    def on_row_double_clicked(self, index):

        if not index.isValid():
            return

        item = self.table.item(
            index.row(),
            0,
        )

        if item:

            user_id = (
                item.data(Qt.ItemDataRole.UserRole)
                or item.text()
            )

            self.view_books(str(user_id))

    # ========================================================
    # USER CRUD
    # ========================================================

    def add_user(self):

        dialog = UserDialog(
            self.db,
            parent=self,
        )

        dialog.data_updated.connect(
            self.load_users_to_table
        )

        dialog.exec()

        self.load_users_to_table()

    def edit_user(self, user_id):

        dialog = UserDialog(
            self.db,
            user_id=user_id,
            parent=self,
        )

        dialog.data_updated.connect(
            self.load_users_to_table
        )

        dialog.exec()

        self.load_users_to_table()

    def delete_user(self, user_id):

        answer = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete user {user_id}?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:

            success, message = (
                self.db.delete_user(user_id)
            )

            if success:

                QMessageBox.information(
                    self,
                    "User Deleted",
                    str(message),
                )

                self.load_users_to_table()

            else:

                QMessageBox.warning(
                    self,
                    "Delete Failed",
                    str(message),
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Delete Error",
                str(exc),
            )

    def handle_batch_delete(self, user_ids):

        if not user_ids:
            return

        answer = QMessageBox.question(
            self,
            "Confirm Batch Delete",
            f"Are you sure you want to delete "
            f"{len(user_ids)} selected users?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        failed = []

        for user_id in user_ids:

            try:

                success, message = (
                    self.db.delete_user(user_id)
                )

                if success:
                    deleted += 1
                else:
                    failed.append(
                        f"{user_id}: {message}"
                    )

            except Exception as exc:

                failed.append(
                    f"{user_id}: {exc}"
                )

        self.load_users_to_table()

        message = (
            f"Successfully deleted: {deleted}\n"
            f"Failed: {len(failed)}"
        )

        if failed:

            message += (
                "\n\nFailed records:\n"
                + "\n".join(failed[:10])
            )

        QMessageBox.information(
            self,
            "Batch Delete Results",
            message,
        )

    def view_books(self, user_id):

        ViewBooksDialog(
            self.db,
            user_id,
            parent=self,
        ).exec()

    # ========================================================
    # CSV IMPORT
    # ========================================================

    def import_users_from_csv(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Users",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )

        if not file_path:
            return

        users_to_insert = []
        errors = []
        seen_ids = set()

        current_date = date.today().isoformat()

        aliases = {
            "id": (
                "user_id",
                "id",
                "pin",
            ),
            "name": (
                "name",
                "full_name",
                "username",
            ),
            "phone": (
                "phone",
                "phone_number",
                "mobile",
            ),
            "role": (
                "role",
                "user_role",
                "category",
            ),
            "department": (
                "department",
                "dept",
                "branch",
            ),
        }

        try:

            with open(
                file_path,
                mode="r",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                reader = csv.DictReader(file)

                if not reader.fieldnames:

                    QMessageBox.warning(
                        self,
                        "Invalid CSV",
                        "The selected CSV file has no header row.",
                    )

                    return

                normalized_headers = {
                    str(header).strip().casefold(): header
                    for header in reader.fieldnames
                    if header
                }

                def find_column(alias_list):

                    for alias in alias_list:

                        if alias in normalized_headers:
                            return normalized_headers[alias]

                    return None

                id_col = find_column(aliases["id"])
                name_col = find_column(aliases["name"])
                phone_col = find_column(aliases["phone"])
                role_col = find_column(aliases["role"])
                dept_col = find_column(aliases["department"])

                if not id_col or not name_col:

                    QMessageBox.warning(
                        self,
                        "Missing CSV Headers",
                        "Required columns:\n"
                        "user_id (or id / pin)\n"
                        "name (or full_name)",
                    )

                    return

                for line_number, row in enumerate(
                    reader,
                    start=2,
                ):

                    if not row or not any(
                        str(value or "").strip()
                        for value in row.values()
                    ):
                        continue

                    user_id = str(
                        row.get(id_col) or ""
                    ).strip().upper()

                    name = str(
                        row.get(name_col) or ""
                    ).strip()

                    phone = (
                        str(row.get(phone_col) or "").strip()
                        if phone_col
                        else ""
                    )

                    role = (
                        str(row.get(role_col) or "Student").strip()
                        if role_col
                        else "Student"
                    )

                    department = (
                        str(row.get(dept_col) or "General").strip()
                        if dept_col
                        else "General"
                    )

                    if not user_id or not name:

                        errors.append(
                            f"Line {line_number}: "
                            "User ID and name are required."
                        )

                        continue

                    if user_id in seen_ids:

                        errors.append(
                            f"Line {line_number}: "
                            f"Duplicate ID '{user_id}' in CSV."
                        )

                        continue

                    seen_ids.add(user_id)

                    if len(user_id) > 100:

                        errors.append(
                            f"Line {line_number}: "
                            "User ID is too long."
                        )

                        continue

                    users_to_insert.append((
                        user_id,
                        name,
                        phone or None,
                        role or "Student",
                        department or "General",
                        current_date,
                    ))

            if not users_to_insert:

                QMessageBox.warning(
                    self,
                    "Nothing to Import",
                    "No valid user records were found.\n\n"
                    + "\n".join(errors[:10]),
                )

                return

            if not hasattr(
                self.db,
                "import_users_batch",
            ):

                QMessageBox.critical(
                    self,
                    "Import Unsupported",
                    "Your database.py does not implement "
                    "import_users_batch().",
                )

                return

            result = self.db.import_users_batch(
                users_to_insert
            )

            # Accept both (success, message/count)
            # and a direct success/count response.
            if (
                isinstance(result, tuple)
                and len(result) >= 2
            ):

                success, imported_result = (
                    result[0],
                    result[1],
                )

                if not success:

                    QMessageBox.critical(
                        self,
                        "Import Failed",
                        str(imported_result),
                    )

                    return

                imported_count = (
                    int(imported_result)
                    if isinstance(imported_result, (int, float))
                    else len(users_to_insert)
                )

            elif result is False:

                QMessageBox.critical(
                    self,
                    "Import Failed",
                    "The database rejected the import.",
                )

                return

            elif isinstance(result, int):

                imported_count = result

            else:

                imported_count = len(users_to_insert)

            message = (
                f"Successfully imported "
                f"{imported_count} user record(s)."
            )

            if errors:

                message += (
                    f"\n\nSkipped {len(errors)} invalid record(s)."
                    "\n\nFirst errors:\n"
                    + "\n".join(errors[:10])
                )

                if len(errors) > 10:

                    message += (
                        f"\n...and {len(errors) - 10} more."
                    )

            QMessageBox.information(
                self,
                "Import Completed",
                message,
            )

            self.load_users_to_table()

        except Exception as exc:

            QMessageBox.critical(
                self,
                "CSV Import Error",
                str(exc),
            )

    # ========================================================
    # CSV EXPORT
    # ========================================================

    def export_users_to_csv(self):

        if not self.filtered_users:

            QMessageBox.information(
                self,
                "Export Users",
                "There are no user records to export.",
            )

            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Users",
            str(Path.home() / "library_users.csv"),
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:

            with open(
                file_path,
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:

                writer = csv.writer(file)

                writer.writerow([
                    "user_id",
                    "name",
                    "phone",
                    "role",
                    "year",
                    "department",
                    "created_at",
                ])

                for row in self.filtered_users:

                    (
                        user_id,
                        name,
                        phone,
                        role,
                        department,
                        created,
                    ) = row[:6]

                    _, year_label = (
                        self.get_dynamic_year_data(
                            user_id,
                            role,
                            department,
                        )
                    )

                    writer.writerow([
                        user_id,
                        name,
                        phone or "",
                        role,
                        year_label,
                        department,
                        created,
                    ])

            QMessageBox.information(
                self,
                "Export Completed",
                f"Successfully exported "
                f"{len(self.filtered_users)} user records.\n\n"
                f"Location:\n{file_path}",
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Export Failed",
                str(exc),
            )

    # ========================================================
    # CONTEXT MENU
    # ========================================================

    def show_context_menu(self, position):

        index = self.table.indexAt(position)

        if not index.isValid():
            return

        row = index.row()

        item = self.table.item(
            row,
            0,
        )

        if not item:
            return

        user_id = str(
            item.data(Qt.ItemDataRole.UserRole)
            or item.text()
        )

        self.table.selectRow(row)

        menu = QMenu(self)

        view_action = menu.addAction(
            "View Assigned Books"
        )

        edit_action = menu.addAction(
            "Edit User Profile"
        )

        menu.addSeparator()

        delete_action = menu.addAction(
            "Delete User"
        )

        action = menu.exec(
            self.table.viewport().mapToGlobal(
                position
            )
        )

        if action == view_action:

            self.view_books(user_id)

        elif action == edit_action:

            self.edit_user(user_id)

        elif action == delete_action:

            self.delete_user(user_id)

    # ========================================================
    # CLEANUP
    # ========================================================

    def closeEvent(self, event):

        if self.theme_manager:

            try:

                self.theme_manager.themeChanged.disconnect(
                    self.on_theme_changed
                )

            except (
                AttributeError,
                TypeError,
                RuntimeError,
            ):
                pass

        super().closeEvent(event)

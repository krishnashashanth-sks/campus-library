
import csv
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import openpyxl
except ImportError:
    openpyxl = None

from PyQt6.QtCore import QEvent, QItemSelectionModel, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont
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
    QButtonGroup,
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
    QScrollArea,
    QSplitter,
    QTabWidget,
)

from dialogs import (
    ComplaintDialog,
    ComplaintManagementDialog,
    UserDialog,
    ViewBooksDialog,
    BatchCirculationDialog,
    CustomEmailDialog,
)
from ui_responsive import (
    FlowLayout,
    configure_inspector_button,
    configure_inspector_form,
    configure_wrapped_label,
    make_scrollable_tab,
    sync_responsive_splitter,
)
from utils import (
    clear_layout,
    is_valid_phone_number,
    is_valid_user_id,
    normalize_department_for_role,
    normalize_user_role,
    rgba_color,
)


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
        colors=None,
    ):
        super().__init__(parent)

        self.filter_key = filter_key
        self.accent = accent
        self.on_click_callback = on_click_callback
        self.selected = False
        self._colors = colors or {}

        self.setObjectName("MetricCard")
        self.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        self.setMinimumHeight(60)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 5, 11, 5)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")
        self.lbl_title.setWordWrap(True)
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

        self.apply_style(self._colors)

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.apply_style(self._colors)

    def set_accent(self, accent, colors=None):
        if accent:
            self.accent = accent
        if colors is not None:
            self._colors = colors
        self.apply_style(self._colors)

    def apply_style(self, colors=None):
        if colors is not None:
            self._colors = colors
        c = self._colors or {}
        is_dark = QColor(c.get("window", "#090E1A")).lightness() < 128
        muted = c.get("muted", "#9BB0CE")
        bg_start = rgba_color(
            self.accent,
            (0.25 if self.selected else 0.14)
            if is_dark
            else (0.42 if self.selected else 0.30),
        )
        bg_end = rgba_color(
            self.accent,
            (0.12 if self.selected else 0.04)
            if is_dark
            else (0.20 if self.selected else 0.14),
        )
        hover_start = rgba_color(self.accent, 0.28 if is_dark else 0.46)
        hover_end = rgba_color(self.accent, 0.12 if is_dark else 0.22)
        border = self.accent if self.selected else rgba_color(
            self.accent,
            0.52 if is_dark else 0.65,
        )

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_start}, stop:1 {bg_end}
                );
                border: {2 if self.selected else 1}px solid {border};
                border-left: 4px solid {self.accent};
                border-radius: 11px;
            }}

            QFrame#MetricCard:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {hover_start},
                    stop:1 {hover_end}
                );
                border: 2px solid {self.accent};
                border-left: 5px solid {self.accent};
            }}

            QLabel#MetricTitle {{
                background: transparent;
                border: none;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.6px;
                color: {muted};
            }}

            QLabel#MetricValue {{
                background: transparent;
                border: none;
                font-size: 20px;
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
            "window": "#090E1A",
            "surface": "#111A2E",
            "surface_alt": "#182542",
            "surface_elevated": "#1F2F52",
            "input": "#0C1426",
            "border": "#28385C",
            "border_bright": "#384F82",
            "text": "#F8FAFC",
            "muted": "#9BB0CE",
            "primary": "#3B82F6",
            "primary_hover": "#2563EB",
            "primary_soft": "rgba(59, 130, 246, 0.16)",
            "selection": "#2563EB",
            "indigo": "#818CF8",
            "indigo_hover": "#6366F1",
            "indigo_soft": "rgba(129, 140, 248, 0.16)",
            "cyan": "#22D3EE",
            "cyan_hover": "#06B6D4",
            "cyan_soft": "rgba(34, 211, 238, 0.16)",
            "teal": "#2DD4BF",
            "purple": "#A78BFA",
            "purple_soft": "rgba(167, 139, 250, 0.16)",
            "success": "#10B981",
            "success_hover": "#059669",
            "success_soft": "rgba(16, 185, 129, 0.16)",
            "warning": "#F59E0B",
            "warning_hover": "#D97706",
            "warning_soft": "rgba(245, 158, 11, 0.16)",
            "danger": "#F43F5E",
            "danger_hover": "#E11D48",
            "danger_soft": "rgba(244, 63, 94, 0.16)",
            "table_row": "#0F182B",
            "table_alt": "#142038",
            "header_bg": "#182745",
        },
        "Light": {
            "window": "#D2DFEF",
            "surface": "#E3ECF9",
            "surface_alt": "#CFDDF3",
            "surface_elevated": "#BED0EC",
            "input": "#DAE6F7",
            "border": "#88A4CE",
            "border_bright": "#5A7CB2",
            "text": "#0A1628",
            "muted": "#283D5E",
            "primary": "#1D4ED8",
            "primary_hover": "#1E40AF",
            "primary_soft": "rgba(29, 78, 216, 0.20)",
            "selection": "#1D4ED8",
            "indigo": "#4338CA",
            "indigo_hover": "#3730A3",
            "indigo_soft": "rgba(67, 56, 202, 0.20)",
            "cyan": "#0369A1",
            "cyan_hover": "#075985",
            "cyan_soft": "rgba(3, 105, 161, 0.20)",
            "teal": "#0F766E",
            "purple": "#6D28D9",
            "purple_soft": "rgba(109, 40, 217, 0.20)",
            "success": "#047857",
            "success_hover": "#065F46",
            "success_soft": "rgba(4, 120, 87, 0.20)",
            "warning": "#B45309",
            "warning_hover": "#92400E",
            "warning_soft": "rgba(180, 83, 9, 0.22)",
            "danger": "#BE123C",
            "danger_hover": "#9F1239",
            "danger_soft": "rgba(190, 18, 60, 0.20)",
            "table_row": "#E4EDF9",
            "table_alt": "#D6E3F6",
            "header_bg": "#C0D3EE",
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
        "Email",
    ]

    def __init__(self, db):
        super().__init__()

        self.db = db

        self.all_users: List[Tuple] = []
        self.filtered_users: List[Tuple] = []

        self.current_filter = "ALL"
        self._page_compact = None
        self._header_compact = None
        self._toolbar_compact = None
        self._splitter_vertical = None
        self._metrics_columns = None
        self._compact_layout = None
        self._table_compact_mode = None
        self._control_center_expanded = True

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

        merged = dict(self.COLORS.get(theme, self.COLORS["Dark"]))
        manager = self.theme_manager or self.get_theme_manager()
        if manager and hasattr(manager, "COLORS"):
            try:
                tm_colors = manager.COLORS.get(theme)
                if tm_colors:
                    merged.update(tm_colors)
            except Exception:
                pass

        self.colors = merged
        c = self.colors

        self.setStyleSheet(f"""
            QWidget#UserManagementView {{
                background-color: {c["window"]};
                color: {c["text"]};
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QWidget#UserPageContent {{
                background-color: transparent;
            }}

            QSplitter#UserSplitter::handle {{
                background: {c["border"]};
                border-radius: 3px;
            }}

            QSplitter#UserSplitter::handle:hover {{
                background: {c["primary"]};
            }}

            QLabel {{
                color: {c["text"]};
                background: transparent;
                border: none;
            }}

            QLabel#PageTitle {{
                font-size: 23px;
                font-weight: 800;
                color: {c["text"]};
            }}

            QLabel#PageSubtitle {{
                color: {c["muted"]};
                font-size: 12px;
            }}

            QLabel#SectionTitle {{
                font-size: 14px;
                font-weight: 700;
                color: {c["primary"]};
            }}

            QLabel#CountLabel {{
                background-color: {c["primary_soft"]};
                color: {c["primary"]};
                border: 1px solid {rgba_color(c["primary"], 0.35)};
                border-radius: 9px;
                padding: 0px 12px;
                min-height: 26px;
                max-height: 26px;
                font-size: 11px;
                font-weight: 700;
            }}

            QFrame#ToolbarCard,
            QFrame#FilterBar,
            QFrame#InspectorCard {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border"]};
                border-radius: 11px;
            }}

            QFrame#InspectorCard {{
                border-top: 3px solid {c["primary"]};
            }}

            QFrame#UserHoverPreview {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border_bright"]};
                border-left: 4px solid {c["primary"]};
                border-radius: 10px;
            }}

            QLabel#UserPreviewTitle {{
                color: {c["text"]};
                font-size: 14px;
                font-weight: 700;
            }}

            QLabel#UserPreviewStatus {{
                color: {c["primary"]};
                font-size: 10px;
                font-weight: 700;
            }}

            QLabel#UserPreviewKey {{
                color: {c["muted"]};
                font-size: 10px;
                font-weight: 600;
            }}

            QLabel#UserPreviewValue {{
                color: {c["text"]};
                font-size: 11px;
                font-weight: 600;
            }}

            QLineEdit,
            QComboBox {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1.5px solid {c["border"]};
                border-radius: 8px;
                padding: 5px 9px;
                min-height: 18px;
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
            }}

            QLineEdit:focus,
            QComboBox:focus {{
                border: 1.5px solid {c["primary"]};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
                border-radius: 6px;
                padding: 4px;
            }}

            QPushButton {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }}

            QPushButton:hover {{
                background-color: {c["surface_elevated"]};
                border-color: {c["primary"]};
            }}

            QPushButton:disabled {{
                color: {c["muted"]};
                background-color: {c["surface_alt"]};
                border-color: {c["border"]};
            }}

            QPushButton#PrimaryButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["primary"]};
                font-weight: 700;
            }}

            QPushButton#PrimaryButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary_hover"]}, stop:1 {c["indigo_hover"]}
                );
            }}

            QPushButton#SuccessButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["success"]}, stop:1 {c["teal"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["success"]};
                font-weight: 700;
            }}

            QPushButton#SuccessButton:hover {{
                background-color: {c["success_hover"]};
            }}

            QPushButton#InfoButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["cyan"]}, stop:1 {c["primary"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["cyan"]};
                font-weight: 700;
            }}

            QPushButton#InfoButton:hover {{
                background-color: {c["cyan_hover"]};
            }}

            QPushButton#WarningButton {{
                background-color: {c["warning"]};
                color: #FFFFFF;
                border: 1px solid {c["warning"]};
                font-weight: 700;
            }}

            QPushButton#WarningButton:hover {{
                background-color: {c["warning_hover"]};
            }}

            QPushButton#SecondaryButton {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
            }}

            QPushButton#SecondaryButton:hover {{
                background-color: {c["surface_elevated"]};
                border-color: {c["primary"]};
                color: {c["primary"]};
            }}

            QPushButton#DangerButton {{
                background-color: {c["danger_soft"]};
                color: {c["danger"]};
                border: 1px solid {rgba_color(c["danger"], 0.65)};
                font-weight: 700;
            }}

            QPushButton#DangerButton:hover {{
                background-color: {c["danger"]};
                color: #FFFFFF;
                border-color: {c["danger"]};
            }}

            QPushButton#PrimaryButton:disabled,
            QPushButton#SuccessButton:disabled,
            QPushButton#InfoButton:disabled,
            QPushButton#WarningButton:disabled,
            QPushButton#SecondaryButton:disabled,
            QPushButton#DangerButton:disabled {{
                background: {c["input"]};
                background-color: {c["input"]};
                color: {c["muted"]};
                border: 1px solid {c["border"]};
            }}

            QPushButton#FilterButton {{
                background: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
                border-radius: 7px;
                padding: 0px 11px;
                min-height: 26px;
                max-height: 26px;
                font-size: 11px;
                font-weight: 600;
            }}

            QFrame#FilterBar QComboBox {{
                padding: 0px 9px;
                min-height: 25px;
                max-height: 25px;
                font-size: 11px;
            }}

            QPushButton#FilterButton:hover {{
                background-color: {c["surface_elevated"]};
                color: {c["text"]};
                border-color: {c["primary"]};
            }}

            QPushButton#FilterButton[filterRole="ALL"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
                border-color: {c["primary"]};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="STUDENT"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["success"]}, stop:1 {c["teal"]}
                );
                color: #FFFFFF;
                border-color: {c["success"]};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="FACULTY"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["cyan"]}, stop:1 {c["primary"]}
                );
                color: #FFFFFF;
                border-color: {c["cyan"]};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="GUEST"]:checked {{
                background-color: {c["warning"]};
                color: #FFFFFF;
                border-color: {c["warning"]};
                font-weight: 700;
            }}

            QTableWidget {{
                background-color: {c["table_row"]};
                alternate-background-color: {c["table_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
                gridline-color: {c["border"]};
                outline: none;
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
            }}

            QTableWidget::item {{
                padding: 6px 6px;
                border-bottom: 1px solid {c["border"]};
            }}

            QHeaderView::section {{
                background-color: {c["header_bg"]};
                color: {c["text"]};
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid {c["border_bright"]};
                padding: 9px 5px;
            }}

            QTabWidget::pane {{
                border: 1px solid {c["border"]};
                background: {c["surface"]};
                border-radius: 8px;
            }}

            QTabBar::tab {{
                background: {c["surface_alt"]};
                color: {c["muted"]};
                padding: 7px 14px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11px;
                font-weight: 700;
            }}

            QTabBar::tab:selected {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
            }}

            QMenu {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
                border-radius: 8px;
                padding: 5px;
            }}

            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}

            QMenu::item:selected {{
                background-color: {c["selection"]};
                color: #FFFFFF;
            }}
        """)

        accent_map = {
            "ALL": c["primary"],
            "STUDENT": c["success"],
            "FACULTY": c["cyan"],
            "GUEST": c["warning"],
        }
        for key, card in self.metric_cards.items():
            card.set_accent(accent_map.get(key, card.accent), c)

        if hasattr(self, "table"):
            if getattr(self, "filtered_users", None) and self.table.rowCount() > 0:
                self.populate_table(self.filtered_users)
            else:
                self._refresh_inspector_theme()
            self.table.viewport().update()

    def _refresh_inspector_theme(self):
        selected_ids = self.get_selected_user_ids()
        if not selected_ids:
            self.show_default_inspector()
        elif len(selected_ids) == 1:
            self.display_user_details(selected_ids[0])
        else:
            self.show_batch_inspector(selected_ids)

    def on_theme_changed(self, *_):
        self.apply_theme()

    # ========================================================
    # UI CONSTRUCTION
    # ========================================================

    def init_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            16, 10, 16, 40
        )

        main_layout.setSpacing(8)
        self.main_layout = main_layout

        # HEADER
        header = QGridLayout()
        header.setHorizontalSpacing(10)
        header.setVerticalSpacing(8)
        self.header_layout = header

        title_group = QVBoxLayout()
        title_group.setContentsMargins(0, 0, 0, 0)
        title_group.setSpacing(2)
        self.title_column_host = QWidget()
        self.title_column_host.setLayout(title_group)
        self.title_column_host.setMinimumWidth(0)

        title = QLabel(
            "User Management & Directory"
        )

        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )

        subtitle = QLabel(
            "Manage student, faculty, and guest lecturer profiles, "
            "view books currently issued, and perform batch operations."
        )

        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )

        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        self.header_actions_host = QWidget()
        header_actions = QHBoxLayout(self.header_actions_host)
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(8)

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.refresh_btn.clicked.connect(
            self.load_users_to_table
        )

        header_actions.addWidget(self.refresh_btn)

        self.control_center_btn = QPushButton("Hide Details")
        self.control_center_btn.setObjectName("SecondaryButton")
        self.control_center_btn.setMinimumHeight(32)
        self.control_center_btn.setToolTip(
            "Show or hide the User Control Center"
        )
        self.control_center_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.control_center_btn.clicked.connect(
            self.toggle_control_center
        )
        header_actions.addWidget(self.control_center_btn)

        self._reflow_header(compact=False)
        main_layout.addLayout(header)

        # KPI STATISTICS
        self.build_statistics(main_layout)

        # SEARCH AND ACTIONS
        self.build_toolbar(main_layout)

        # FILTERS
        self.build_filters(main_layout)

        # MAIN CONTENT
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setObjectName("UserSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)

        # USER TABLE
        self.table = QTableWidget()

        self.table.setObjectName("UserTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(
            self.HEADERS
        )
        self.table.setMinimumHeight(110)
        self.table.setMinimumWidth(0)

        self.table.setAlternatingRowColors(True)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)

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
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)

        table_header = self.table.horizontalHeader()
        table_header.setMinimumSectionSize(44)
        self._apply_table_column_modes(compact=False)

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.table.customContextMenuRequested.connect(
            self.show_context_menu
        )

        self.table.itemSelectionChanged.connect(
            self.on_users_selection_changed
        )
        self.table.cellEntered.connect(
            self.show_user_hover_preview
        )
        self.table.viewport().installEventFilter(self)

        self.table.doubleClicked.connect(
            self.on_row_double_clicked
        )

        self._create_user_hover_preview()

        self.content_splitter.addWidget(self.table)

        # USER INSPECTOR
        self.detail_container = QFrame()
        self.detail_container.setObjectName(
            "InspectorCard"
        )

        self.detail_container.setMinimumWidth(220)
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
        configure_wrapped_label(self.inspector_title)

        detail_layout.addWidget(
            self.inspector_title
        )

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("InspectorTabs")
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setUsesScrollButtons(True)

        # PROFILE TAB
        self.tab_overview, self.overview_layout, _overview_content = make_scrollable_tab(
            self.tab_widget,
            "Profile",
            margins=(8, 8, 8, 8),
            spacing=8,
            object_name="UserOverviewScroll",
        )

        # ACTIONS TAB
        self.tab_actions, self.actions_layout, _actions_content = make_scrollable_tab(
            self.tab_widget,
            "Actions",
            margins=(8, 8, 8, 8),
            spacing=6,
            object_name="UserActionsScroll",
        )

        detail_layout.addWidget(
            self.tab_widget
        )

        self.content_splitter.addWidget(
            self.detail_container
        )

        main_layout.addWidget(
            self.content_splitter,
            1,
        )

        self._sync_responsive_layout()
        self.show_default_inspector()

    def _reflow_header(self, compact: bool):
        if compact == self._header_compact:
            return
        self.header_layout.removeWidget(self.title_column_host)
        self.header_layout.removeWidget(self.header_actions_host)
        self.header_layout.setColumnStretch(0, 1)
        self.header_layout.setColumnStretch(1, 0)
        if compact:
            self.header_layout.addWidget(self.title_column_host, 0, 0)
            self.header_layout.addWidget(
                self.header_actions_host,
                1,
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
        else:
            self.header_layout.addWidget(self.title_column_host, 0, 0)
            self.header_layout.addWidget(
                self.header_actions_host,
                0,
                1,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
        self._header_compact = compact

    def _reflow_toolbar(self, compact: bool):
        if compact == self._toolbar_compact:
            return
        for widget in (self.search_input, self.import_btn, self.export_btn, self.add_btn):
            self.toolbar_layout.removeWidget(widget)
        for col in range(4):
            self.toolbar_layout.setColumnStretch(col, 0)
        if compact:
            self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 3)
            self.toolbar_layout.addWidget(self.import_btn, 1, 0)
            self.toolbar_layout.addWidget(self.export_btn, 1, 1)
            self.toolbar_layout.addWidget(self.add_btn, 1, 2)
            for col in range(3):
                self.toolbar_layout.setColumnStretch(col, 1)
        else:
            self.toolbar_layout.addWidget(self.search_input, 0, 0)
            self.toolbar_layout.addWidget(self.import_btn, 0, 1)
            self.toolbar_layout.addWidget(self.export_btn, 0, 2)
            self.toolbar_layout.addWidget(self.add_btn, 0, 3)
            self.toolbar_layout.setColumnStretch(0, 1)
        self._toolbar_compact = compact

    def _update_splitter_min_height(self):
        if self._splitter_vertical and self._control_center_expanded:
            self.content_splitter.setMinimumHeight(250)
        else:
            self.content_splitter.setMinimumHeight(120)

    def _sync_responsive_layout(self):
        avail_w = self.width() if self.width() > 0 else 1000

        compact_page = avail_w < 860
        if compact_page != self._page_compact:
            self._page_compact = compact_page
            if compact_page:
                self.main_layout.setContentsMargins(12, 6, 12, 40)
                self.main_layout.setSpacing(6)
            else:
                self.main_layout.setContentsMargins(16, 10, 16, 40)
                self.main_layout.setSpacing(8)

        self._reflow_header(avail_w < 640)
        self._reflow_toolbar(avail_w < 880)

        columns = (
            1 if avail_w < 460
            else 2 if avail_w < 680
            else 4
        )
        self._reflow_metric_cards(columns)

        content_w = max(300, avail_w - (24 if compact_page else 32))
        self._splitter_vertical = sync_responsive_splitter(
            self.content_splitter,
            self.detail_container,
            content_w,
            breakpoint=680,
            max_panel_width=340,
            min_panel_width=220,
            min_panel_height=130,
            current_vertical=self._splitter_vertical,
        )
        self._update_splitter_min_height()

        est_table_w = (
            content_w if self._splitter_vertical or not self._control_center_expanded
            else max(280, content_w - 290)
        )
        table_compact = est_table_w < 550
        if table_compact != self._table_compact_mode:
            self._apply_table_column_modes(compact=table_compact)
            self._table_compact_mode = table_compact

    def _reflow_metric_cards(self, columns):
        if self._metrics_columns == columns:
            return

        cards = list(self.metric_cards.values())
        for card in cards:
            self.metrics_grid.removeWidget(card)

        for column in range(len(cards)):
            self.metrics_grid.setColumnStretch(column, 0)

        for index, card in enumerate(cards):
            self.metrics_grid.addWidget(
                card,
                index // columns,
                index % columns,
            )

        for column in range(columns):
            self.metrics_grid.setColumnStretch(column, 1)

        self._metrics_columns = columns

    def toggle_control_center(self):
        self._control_center_expanded = not self._control_center_expanded
        self.detail_container.setVisible(self._control_center_expanded)
        self.control_center_btn.setText(
            "Hide Details"
            if self._control_center_expanded
            else "Show Details"
        )
        self._update_splitter_min_height()

    def _apply_table_column_modes(self, compact=False):
        header = self.table.horizontalHeader()
        if compact:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
            for col, width in (
                (0, 88),
                (1, 145),
                (2, 98),
                (3, 76),
                (4, 86),
                (5, 165),
                (6, 84),
                (7, 175),
            ):
                self.table.setColumnWidth(col, width)
            return

        header.setStretchLastSection(False)
        fixed_widths = {
            0: 108,  # PIN / ID
            2: 94,   # Phone Number
            3: 82,   # Role
            4: 108,  # Year of Study
            6: 94,   # Created At
        }
        for col_idx in range(len(self.HEADERS)):
            if col_idx in fixed_widths:
                header.setSectionResizeMode(
                    col_idx, QHeaderView.ResizeMode.Fixed
                )
                self.table.setColumnWidth(col_idx, fixed_widths[col_idx])
            else:
                header.setSectionResizeMode(
                    col_idx, QHeaderView.ResizeMode.Stretch
                )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()

    # ========================================================
    # KPI STATISTICS
    # ========================================================

    def _create_user_hover_preview(self):

        self.hover_preview = QFrame(
            self,
            Qt.WindowType.ToolTip,
        )
        self.hover_preview.setObjectName("UserHoverPreview")
        self.hover_preview.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating
        )
        self.hover_preview.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.hover_preview.setFixedWidth(330)

        layout = QVBoxLayout(self.hover_preview)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(8)

        self.hover_preview_title = QLabel()
        self.hover_preview_title.setObjectName("UserPreviewTitle")
        self.hover_preview_title.setWordWrap(True)
        layout.addWidget(self.hover_preview_title)

        self.hover_preview_status = QLabel()
        self.hover_preview_status.setObjectName("UserPreviewStatus")
        layout.addWidget(self.hover_preview_status)

        details = QFormLayout()
        details.setContentsMargins(0, 2, 0, 0)
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(6)

        self.hover_preview_values = {}
        for field in (
            "ID / PIN", "Phone", "Role", "Year",
            "Department", "Created", "Email",
        ):
            key_label = QLabel(field)
            key_label.setObjectName("UserPreviewKey")

            value_label = QLabel()
            value_label.setObjectName("UserPreviewValue")
            value_label.setWordWrap(True)

            details.addRow(key_label, value_label)
            self.hover_preview_values[field] = value_label

        layout.addLayout(details)
        self.hover_preview.hide()

    def show_user_hover_preview(self, row, _column):

        id_item = self.table.item(row, 0)
        if not id_item:
            self.hover_preview.hide()
            return

        user_id = str(
            id_item.data(Qt.ItemDataRole.UserRole)
            or id_item.text()
        )
        selected_ids = self.get_selected_user_ids()
        if (
            self.detail_container.isVisible()
            and selected_ids == [user_id]
        ):
            self.hover_preview.hide()
            return

        values = {
            "ID / PIN": user_id,
            "Phone": self._user_table_text(row, 2),
            "Role": self._user_table_text(row, 3),
            "Year": self._user_table_text(row, 4),
            "Department": self._user_table_text(row, 5),
            "Created": self._user_table_text(row, 6),
            "Email": self._user_table_text(row, 7),
        }

        self.hover_preview_title.setText(
            self._user_table_text(row, 1) or "Unnamed user"
        )
        self.hover_preview_status.setText(
            values["Role"].upper() or "USER PROFILE"
        )

        for field, value in values.items():
            self.hover_preview_values[field].setText(
                value or "—"
            )

        self.hover_preview.adjustSize()
        item_rect = self.table.visualItemRect(id_item)
        position = self.table.viewport().mapToGlobal(
            QPoint(item_rect.left(), item_rect.bottom())
        ) + QPoint(12, 8)

        screen = QApplication.screenAt(QCursor.pos())
        if screen:
            bounds = screen.availableGeometry()
            if position.x() + self.hover_preview.width() > bounds.right():
                position.setX(
                    bounds.right() - self.hover_preview.width()
                )
            if position.y() + self.hover_preview.height() > bounds.bottom():
                position.setY(
                    self.table.viewport().mapToGlobal(
                        QPoint(item_rect.left(), item_rect.top())
                    ).y() - self.hover_preview.height() - 8
                )

        self.hover_preview.move(position)
        self.hover_preview.show()
        self.hover_preview.raise_()

    def _user_table_text(self, row, column):
        item = self.table.item(row, column)
        return item.text() if item else ""

    def eventFilter(self, watched, event):
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.Leave
        ):
            self.hover_preview.hide()

        return super().eventFilter(watched, event)

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

        self.metrics_grid = grid
        self._metrics_columns = None
        self._reflow_metric_cards(4)

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

        toolbar_layout = QGridLayout(frame)

        toolbar_layout.setContentsMargins(
            8, 6, 8, 6
        )

        toolbar_layout.setHorizontalSpacing(8)
        toolbar_layout.setVerticalSpacing(6)
        self.toolbar_layout = toolbar_layout

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText(
            "Search by PIN/ID, name, phone, role, or department..."
        )

        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(32)
        self.search_input.setMinimumWidth(0)

        self.search_input.textChanged.connect(
            self.apply_filters
        )

        self.import_btn = QPushButton("Import CSV / XLSX")
        self.import_btn.setObjectName("InfoButton")
        self.import_btn.setMinimumHeight(32)

        self.import_btn.clicked.connect(
            self.import_users_from_file
        )

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SuccessButton")
        self.export_btn.setMinimumHeight(32)

        self.export_btn.clicked.connect(
            self.export_users_to_csv
        )

        self.complaint_btn = QPushButton("New Complaint", self)
        self.complaint_btn.setObjectName("WarningButton")
        self.complaint_btn.setMinimumHeight(32)
        self.complaint_btn.clicked.connect(
            self.open_complaint_dialog
        )
        self.complaint_btn.hide()

        self.complaint_inbox_btn = QPushButton("Complaint Inbox", self)
        self.complaint_inbox_btn.setObjectName("InfoButton")
        self.complaint_inbox_btn.setMinimumHeight(32)
        self.complaint_inbox_btn.clicked.connect(
            self.open_complaint_inbox
        )
        self.complaint_inbox_btn.hide()

        self.add_btn = QPushButton("+ Add New User")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setMinimumHeight(32)

        self.add_btn.clicked.connect(
            self.add_user
        )

        for button in (
            self.import_btn,
            self.export_btn,
            self.complaint_btn,
            self.complaint_inbox_btn,
            self.add_btn,
        ):

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.setMinimumWidth(0)

        self._reflow_toolbar(compact=False)

        parent_layout.addWidget(frame)

    # ========================================================
    # FILTERS
    # ========================================================

    def build_filters(self, parent_layout):

        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")

        outer_layout = QHBoxLayout(filter_frame)
        outer_layout.setContentsMargins(6, 5, 8, 5)
        outer_layout.setSpacing(8)

        filters_host = QWidget()
        filters_host.setObjectName("FilterButtonsHost")
        filters_host.setMinimumWidth(0)
        filters_host.setStyleSheet("QWidget#FilterButtonsHost { background: transparent; border: none; }")
        filters_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout = FlowLayout(filters_host, margin=0, h_spacing=6, v_spacing=5)

        self.filter_buttons = {}
        self.filter_button_group = QButtonGroup(self)
        self.filter_button_group.setExclusive(True)

        for key, label in self.FILTERS.items():

            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setProperty("filterRole", key)
            button.setCheckable(True)
            button.setFixedHeight(28)
            button.setMinimumWidth(0)
            button.setAccessibleName(label)

            button.setChecked(
                key == "ALL"
            )
            self.filter_button_group.addButton(button)

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

        self.year_combo.setFixedHeight(28)
        self.year_combo.setMinimumWidth(85)
        self.year_combo.setMaximumWidth(150)
        self.year_combo.setEnabled(False)

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

        self.branch_combo.setFixedHeight(28)
        self.branch_combo.setMinimumWidth(100)
        self.branch_combo.setMaximumWidth(240)

        self.branch_combo.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.branch_combo.currentIndexChanged.connect(
            self.apply_filters
        )

        layout.addWidget(self.year_combo)
        layout.addWidget(self.branch_combo)

        outer_layout.addWidget(filters_host, 1)

        self.lbl_count = QLabel("0 records")
        self.lbl_count.setObjectName("CountLabel")
        self.lbl_count.setFixedHeight(28)
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_count.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        outer_layout.addWidget(
            self.lbl_count,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        parent_layout.addWidget(filter_frame)

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

            if self.current_filter == "STUDENT":
                departments = self.db.get_departments("STUDENT")
            else:
                departments = self.db.get_all_user_departments()

            if departments:

                for department in dict.fromkeys(
                    str(value).strip()
                    for value in departments
                    if value and str(value).strip()
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
            key == "STUDENT"
        )

        if key != "STUDENT":

            self.year_combo.blockSignals(True)
            self.year_combo.setCurrentIndex(0)
            self.year_combo.blockSignals(False)

        self.update_branch_dropdown()
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

            user_id, name, phone, role, department, created = row[:6]

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
                self.current_filter == "STUDENT"
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

        self.hover_preview.hide()
        previously_selected = (
            self.get_selected_user_ids()
        )

        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:

            self.table.clearContents()
            self.table.setRowCount(len(rows))

            rows_to_reselect = []
            c = self.colors
            primary_color = QColor(c["primary"])
            warning_color = QColor(c["warning"])
            cyan_color = QColor(c["cyan"])
            success_color = QColor(c["success"])
            muted_color = QColor(c["muted"])
            purple_color = QColor(c["purple"])
            indigo_color = QColor(c["indigo"])
            bold_font = QFont(self.table.font())
            bold_font.setBold(True)

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

                if str(user_id) in previously_selected:
                    rows_to_reselect.append(row_index)

                values = [
                    user_id,
                    name,
                    phone or "N/A",
                    role,
                    year_label,
                    department,
                    created,
                    row_data[6] if len(row_data) > 6 else "",
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
                        item.setFont(bold_font)
                        item.setForeground(primary_color)

                    elif column == 3:

                        role_text = str(
                            role or ""
                        ).lower()
                        item.setFont(bold_font)

                        if "guest" in role_text:

                            item.setForeground(
                                warning_color
                            )

                        elif (
                            "faculty" in role_text
                            or "staff" in role_text
                        ):

                            item.setForeground(
                                cyan_color
                            )

                        else:

                            item.setForeground(
                                success_color
                            )

                    elif column == 4:

                        year_str = str(value or "").strip()
                        if year_str.startswith("N/A"):
                            item.setForeground(muted_color)
                        elif "(Final)" in year_str:
                            item.setFont(bold_font)
                            item.setForeground(cyan_color)
                        elif "(Graduated)" in year_str:
                            item.setForeground(purple_color)
                        else:
                            item.setForeground(indigo_color)

                    self.table.setItem(
                        row_index,
                        column,
                        item,
                    )

        finally:

            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self._updating_table = False

        self.lbl_count.setText(
            f"{len(rows):,} records"
        )

        if rows_to_reselect:
            selection_model = self.table.selectionModel()
            selection_model.blockSignals(True)
            for row in rows_to_reselect:
                selection_model.select(
                    self.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
            selection_model.blockSignals(False)
            self.on_users_selection_changed()
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

        configure_wrapped_label(lbl)

        lbl.setStyleSheet(
            f"color: {self.colors['muted']}; font-size: 11px;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

    def on_users_selection_changed(self):

        if self._updating_table:
            return

        self.hover_preview.hide()

        selected_ids = (
            self.get_selected_user_ids()
        )

        if not selected_ids:

            self.tab_widget.setCurrentWidget(self.tab_overview)
            self.show_default_inspector()

        elif len(selected_ids) == 1:
            self.tab_widget.setCurrentWidget(self.tab_overview)

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
        self.tab_widget.setCurrentWidget(self.tab_actions)

        lbl = QLabel(
            f"{len(user_ids)} users selected.\n\n"
            "Active borrowers may be protected from deletion "
            "by the database."
        )

        configure_wrapped_label(lbl)

        lbl.setStyleSheet(
            f"background-color: {self.colors['primary_soft']}; "
            f"color: {self.colors['text']}; "
            f"border: 1px solid {rgba_color(self.colors['primary'], 0.35)}; "
            "border-radius: 8px; padding: 10px; font-size: 11px; font-weight: 600;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

        for mode, text, object_name in (
            ("ISSUE", "Issue a Book to Selected Users", "PrimaryButton"),
            ("RETURN", "Return a Book from Selected Users", "SuccessButton"),
        ):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setMinimumHeight(34)
            configure_inspector_button(button)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, selected_mode=mode:
                self.handle_batch_user_circulation(
                    selected_mode,
                    user_ids,
                )
            )
            self.actions_layout.addWidget(button)

        delete_button = QPushButton(
            "Delete Selected Users"
        )

        delete_button.setObjectName(
            "DangerButton"
        )

        delete_button.setMinimumHeight(34)
        configure_inspector_button(delete_button)

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

    def handle_batch_user_circulation(self, mode, user_ids=None):
        selected_ids = user_ids or self.get_selected_user_ids()
        if not selected_ids:
            QMessageBox.information(
                self,
                "No Users Selected",
                "Select at least one user before choosing a batch action.",
            )
            return

        dialog = BatchCirculationDialog(
            self.db,
            mode,
            selected_ids,
            "users",
            self,
        )
        if not dialog.exec():
            return

        book_id, days = dialog.get_data()
        operation = "issue" if mode == "ISSUE" else "return"
        answer = QMessageBox.question(
            self,
            f"Confirm Batch {operation.title()}",
            f"{operation.title()} Book ID '{book_id}' "
            f"for {len(selected_ids)} selected users?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        succeeded = []
        failed = []
        for user_id in selected_ids:
            try:
                if mode == "ISSUE":
                    result = self.db.issue_book(
                        book_id,
                        user_id,
                        days,
                    )
                    if not isinstance(result, tuple) or len(result) < 2:
                        raise ValueError("Unexpected issue_book() response.")
                    success, detail = result[0], result[1]
                else:
                    result = self.db.return_book(book_id, user_id)
                    if not isinstance(result, tuple) or len(result) < 2:
                        raise ValueError("Unexpected return_book() response.")
                    success, detail = result[0], result[1]
                    if success:
                        detail = f"Fine: ₹{float(detail or 0):.2f}"

                if success:
                    succeeded.append(user_id)
                else:
                    failed.append(f"{user_id}: {detail}")
            except Exception as error:
                failed.append(f"{user_id}: {error}")

        self.load_users_to_table()
        summary = (
            f"Completed: {len(succeeded)}\n"
            f"Failed: {len(failed)}"
        )
        if failed:
            summary += "\n\nNot completed:\n" + "\n".join(failed[:10])
        QMessageBox.information(
            self,
            f"Batch {operation.title()} Results",
            summary,
        )

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

            status_text = "OVERDUE BOOKS"
            status_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['danger']}, stop:1 {c['danger_hover']})"
            )
            status_border = c["danger"]

        elif active_loans:

            status_text = "ISSUED BOOKS"
            status_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['warning']}, stop:1 {c['warning_hover']})"
            )
            status_border = c["warning"]

        else:

            status_text = "CLEAR ACCOUNT"
            status_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['success']}, stop:1 {c['teal']})"
            )
            status_border = c["success"]

        status_lbl = QLabel(
            f"{status_text}\n"
            f"{len(active_loans)} issued books "
            f"({overdue_count} overdue)"
        )

        configure_wrapped_label(status_lbl)

        status_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        status_lbl.setStyleSheet(f"""
            background: {status_bg};
            color: #FFFFFF;
            border: 1px solid {status_border};
            border-radius: 8px;
            padding: 9px;
            font-weight: 800;
            font-size: 11px;
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
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=7)

        form.setContentsMargins(
            0, 4, 0, 4
        )

        try:
            policy = self.db.get_loan_policy(user[3])
            policy_label = (
                f"Max {policy.get('max_books', 3)} books · "
                f"{policy.get('default_days', 14)} days · "
                f"₹{float(policy.get('fine_rate', 2.0)):.2f}/day"
            )
        except Exception:
            policy_label = "Standard policy"

        try:
            unpaid_fines = float(
                self.db.get_user_pending_fines_total(user[0]) or 0.0
            )
        except Exception:
            unpaid_fines = 0.0

        fields = [
            ("ID / PIN", user[0]),
            ("Full Name", user[1]),
            ("Phone", user[2] or "N/A"),
            ("Role", user[3]),
            ("Loan Policy", policy_label),
            ("Year", year_label),
            ("Department", user[4]),
            ("Unpaid Fines", f"₹{unpaid_fines:.2f}"),
            ("Created", user[5]),
            ("Email", user[6] if len(user) > 6 else ""),
        ]

        for key, value in fields:

            key_label = QLabel(key)
            configure_wrapped_label(key_label, expanding_width=False)

            value_label = QLabel(
                str(
                    value
                    if value is not None
                    else "—"
                )
            )
            configure_wrapped_label(value_label, expanding_width=True)

            key_label.setStyleSheet(
                f"color: {c['muted']}; "
                "font-size: 10px; font-weight: 600;"
            )

            value_color = (
                c["warning"]
                if key == "Unpaid Fines" and unpaid_fines > 0
                else c["text"]
            )
            value_label.setStyleSheet(
                f"color: {value_color}; "
                "font-size: 11px; font-weight: 600;"
            )

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
                "Send Custom Email",
                lambda: self.send_custom_email(user[0]),
                "InfoButton",
            ),
        ]
        if unpaid_fines > 0:
            actions.append((
                f"💳 Settle Pending Fines (₹{unpaid_fines:.2f})",
                lambda: self.settle_user_fines(user[0]),
                "WarningButton",
            ))
        actions.append((
            "Delete User",
            lambda: self.delete_user(user[0]),
            "DangerButton",
        ))

        for text, callback, object_name in actions:

            button = QPushButton(text)

            button.setObjectName(
                object_name
            )

            button.setMinimumHeight(34)
            configure_inspector_button(button)

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(callback)

            self.actions_layout.addWidget(button)

        self.actions_layout.addStretch()

    def send_custom_email(self, user_id):
        try:
            success, user = self.db.get_user_details(user_id)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Email Lookup Failed",
                str(error),
            )
            return

        if not success or not user:
            QMessageBox.warning(
                self,
                "User Not Found",
                f"Could not load user '{user_id}'.",
            )
            return

        recipient = str(user[6] or "").strip() if len(user) > 6 else ""
        if not recipient:
            QMessageBox.warning(
                self,
                "Email Address Missing",
                "Add an email address to this user's profile before "
                "sending a message.",
            )
            return

        dialog = CustomEmailDialog(user[1], self)
        if not dialog.exec():
            return
        subject, body = dialog.get_data()

        try:
            queue_id = self.db.enqueue_email(
                recipient,
                subject,
                body,
                "SYSTEM_ALERT",
            )
            if not queue_id:
                raise RuntimeError("The message was not added to the queue.")
        except Exception as error:
            QMessageBox.critical(
                self,
                "Email Queue Failed",
                str(error),
            )
            return

        app = QApplication.instance()
        sync_manager = (
            getattr(app, "email_sync_manager", None)
            if app
            else None
        )
        if sync_manager:
            sync_manager.sync_now()

        QMessageBox.information(
            self,
            "Email Queued",
            f"The message for {user[1]} was saved to the email queue. "
            "It will be delivered when email sync is available.",
        )

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

    def settle_user_fines(self, user_id):
        try:
            total = float(self.db.get_user_pending_fines_total(user_id) or 0.0)
        except Exception:
            total = 0.0
        if total <= 0:
            QMessageBox.information(
                self,
                "No Pending Fines",
                f"User '{user_id}' has no unsettled fines.",
            )
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Settle Pending Fines")
        msg.setText(
            f"User '{user_id}' currently has ₹{total:.2f} in unpaid fines.\n\n"
            "How would you like to settle these fines?"
        )
        pay_btn = msg.addButton("Mark All Paid", QMessageBox.ButtonRole.AcceptRole)
        waive_btn = msg.addButton("Waive All", QMessageBox.ButtonRole.DestructiveRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == pay_btn:
            action = "PAID"
        elif clicked == waive_btn:
            action = "WAIVED"
        else:
            return

        try:
            success, message = self.db.settle_all_user_fines(
                user_id, action, "Settled from User Management"
            )
            if success:
                QMessageBox.information(self, "Fines Settled", str(message))
                self.load_users_to_table()
            else:
                QMessageBox.warning(self, "Settlement Failed", str(message))
        except Exception as error:
            QMessageBox.critical(self, "Settlement Error", str(error))

    def view_books(self, user_id):

        dialog = ViewBooksDialog(
            self.db,
            user_id,
            parent=self,
        )
        dialog.data_updated.connect(self.load_users_to_table)
        dialog.exec()
        self.load_users_to_table()

    def open_complaint_dialog(self):
        try:
            dialog = ComplaintDialog(self.db, self)
            dialog.exec()
        except Exception as error:
            QMessageBox.critical(
                self,
                "Complaint Form Error",
                str(error),
            )

    def open_complaint_inbox(self):
        dialog = ComplaintManagementDialog(self.db, self)
        dialog.exec()

    # ========================================================
    # CSV / XLSX IMPORT
    # ========================================================

    def import_users_from_file(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Users",
            "",
            "Data Files (*.csv *.xlsx);;CSV Files (*.csv);;"
            "Excel Files (*.xlsx);;All Files (*)",
        )

        if not file_path:
            return

        file_extension = Path(file_path).suffix.casefold()
        if file_extension == ".xlsx" and openpyxl is None:
            QMessageBox.critical(
                self,
                "Missing Dependency",
                "Please install 'openpyxl' to import Excel files:\n"
                "pip install openpyxl",
            )
            return

        users_to_insert = []
        errors = []
        seen_ids = set()
        seen_phones = {}

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
            "email": (
                "email",
                "email_address",
                "e_mail",
            ),
            "role": (
                "role",
                "user_role",
                "category",
            ),
            "department": (
                "department",
                "department_name",
                "dept",
                "branch",
                "branch_name",
                "student_branch",
                "student_department",
                "teaching_department",
                "faculty_department",
                "program",
                "course",
                "major",
            ),
        }

        try:
            existing_success, existing_users = self.db.get_users()
            if not existing_success:
                raise RuntimeError(
                    "Could not check existing user IDs and phone numbers."
                )
            existing_phones = {
                str(user[2]).strip().casefold(): str(user[0]).strip().upper()
                for user in existing_users
                if len(user) > 2 and str(user[2] or "").strip()
            }

            fieldnames = []
            rows = []

            if file_extension == ".xlsx":
                workbook = openpyxl.load_workbook(
                    file_path,
                    data_only=True,
                    read_only=True,
                )
                try:
                    worksheet = workbook.active
                    excel_rows = worksheet.iter_rows(
                        values_only=True
                    )
                    header_row = next(excel_rows, None)

                    if header_row:
                        fieldnames = [
                            str(value).strip()
                            if value is not None
                            else ""
                            for value in header_row
                        ]

                        for excel_row in excel_rows:
                            row = {}
                            for index, value in enumerate(excel_row):
                                if (
                                    index >= len(fieldnames)
                                    or not fieldnames[index]
                                ):
                                    continue

                                if value is None:
                                    text = ""
                                elif (
                                    isinstance(value, float)
                                    and value.is_integer()
                                ):
                                    text = str(int(value))
                                else:
                                    text = str(value).strip()

                                row[fieldnames[index]] = text

                            rows.append(row)
                finally:
                    workbook.close()

            elif file_extension == ".csv":
                with open(
                    file_path,
                    mode="r",
                    encoding="utf-8-sig",
                    newline="",
                ) as file:
                    reader = csv.DictReader(file)
                    fieldnames = reader.fieldnames or []
                    rows = list(reader)

            else:
                QMessageBox.warning(
                    self,
                    "Unsupported File",
                    "Select a CSV or XLSX file.",
                )
                return

            if not fieldnames:
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    "The selected file has no header row.",
                )
                return

            def normalize_header(header):
                return re.sub(
                    r"[^a-z0-9]+",
                    "_",
                    str(header).strip().casefold(),
                ).strip("_")

            normalized_headers = {
                normalize_header(header): header
                for header in fieldnames
                if header
            }

            def find_column(alias_list):

                for alias in alias_list:
                    normalized_alias = normalize_header(alias)
                    if normalized_alias in normalized_headers:
                        return normalized_headers[normalized_alias]

                return None

            id_col = find_column(aliases["id"])
            name_col = find_column(aliases["name"])
            phone_col = find_column(aliases["phone"])
            email_col = find_column(aliases["email"])
            role_col = find_column(aliases["role"])
            dept_col = find_column(aliases["department"])

            if not id_col or not name_col:
                QMessageBox.warning(
                    self,
                    "Missing Headers",
                    "Required columns:\n"
                    "user_id (or id / pin)\n"
                    "name (or full_name)",
                )
                return

            for line_number, row in enumerate(rows, start=2):

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
                email = (
                    str(row.get(email_col) or "").strip().casefold()
                    if email_col
                    else ""
                )

                role_value = (
                    str(row.get(role_col) or "Student").strip()
                    if role_col
                    else "Student"
                )
                role = normalize_user_role(role_value)

                department = (
                    str(row.get(dept_col) or "").strip()
                    if dept_col
                    else ""
                )

                if not role:
                    errors.append(
                        f"Line {line_number}: Unsupported user role "
                        f"'{role_value}'."
                    )
                    continue

                if not user_id or not name:
                    errors.append(
                        f"Line {line_number}: "
                        "User ID and name are required."
                    )
                    continue

                if not is_valid_user_id(user_id, role):
                    if role == "Student":
                        expected_format = "24001-CS-097"
                    else:
                        expected_format = "123456"
                    errors.append(
                        f"Line {line_number}: Invalid ID '{user_id}' for "
                        f"{role}; expected a format like {expected_format}."
                    )
                    continue

                if user_id in seen_ids:
                    errors.append(
                        f"Line {line_number}: "
                        f"Duplicate ID '{user_id}' in file."
                    )
                    continue

                if len(user_id) > 100:
                    errors.append(
                        f"Line {line_number}: "
                        "User ID is too long."
                    )
                    continue

                if phone and not is_valid_phone_number(phone):
                    errors.append(
                        f"Line {line_number}: Phone number must contain "
                        "exactly 10 digits."
                    )
                    continue

                canonical_department = normalize_department_for_role(
                    department,
                    role,
                )
                if role == "Student" and not canonical_department:
                    errors.append(
                        f"Line {line_number}: Students must be assigned an "
                        "official college branch (not Sciences & Humanities "
                        "or General Administration)."
                    )
                    continue
                if role in ("Faculty", "Guest Lecturer") and not canonical_department:
                    errors.append(
                        f"Line {line_number}: {role} must be assigned a "
                        "college branch, Sciences & Humanities Department, "
                        "or General Administration."
                    )
                    continue
                department = canonical_department or "General Administration"

                if email and (
                    "@" not in email
                    or email.startswith("@")
                    or email.endswith("@")
                    or "." not in email.rsplit("@", 1)[-1]
                ):
                    errors.append(
                        f"Line {line_number}: Invalid email address."
                    )
                    continue

                phone_key = phone.casefold()
                if phone_key:
                    existing_owner = existing_phones.get(phone_key)
                    if existing_owner and existing_owner != user_id:
                        errors.append(
                            f"Line {line_number}: Phone number is already "
                            f"assigned to user '{existing_owner}'."
                        )
                        continue
                    batch_owner = seen_phones.get(phone_key)
                    if batch_owner and batch_owner != user_id:
                        errors.append(
                            f"Line {line_number}: Phone number is duplicated "
                            f"for user '{batch_owner}' in the file."
                        )
                        continue
                    seen_phones[phone_key] = user_id

                seen_ids.add(user_id)
                users_to_insert.append((
                    user_id,
                    name,
                    phone or None,
                    role or "Student",
                    department,
                    current_date,
                    email or None,
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
                "User Import Error",
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
                    "email",
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
                    email = row[6] if len(row) > 6 else ""

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
                        email or "",
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

        selected_rows = {
            selected.row()
            for selected in self.table.selectionModel().selectedRows()
        }
        if row not in selected_rows:
            self.table.selectRow(row)

        menu = QMenu(self)

        selected_user_ids = self.get_selected_user_ids()
        if len(selected_user_ids) > 1:
            issue_action = menu.addAction(
                "Issue a Book to Selected Users"
            )
            return_action = menu.addAction(
                "Return a Book from Selected Users"
            )
            menu.addSeparator()
            delete_action = menu.addAction("Delete Selected Users")
            view_action = edit_action = email_action = None
        else:
            issue_action = return_action = None
            view_action = menu.addAction(
                "View Assigned Books"
            )

            edit_action = menu.addAction(
                "Edit User Profile"
            )
            email_action = menu.addAction(
                "Send Custom Email"
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

        if action is None:
            return

        if action == view_action:

            self.view_books(user_id)

        elif action == edit_action:

            self.edit_user(user_id)

        elif action == email_action:

            self.send_custom_email(user_id)

        elif action == issue_action:

            self.handle_batch_user_circulation(
                "ISSUE",
                selected_user_ids,
            )

        elif action == return_action:

            self.handle_batch_user_circulation(
                "RETURN",
                selected_user_ids,
            )

        elif action == delete_action:

            if len(selected_user_ids) > 1:
                self.handle_batch_delete(selected_user_ids)
            else:
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

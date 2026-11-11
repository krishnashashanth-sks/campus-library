
"""
Centralized Theme Manager
Library Management System - PyQt6

Supported themes:
    - Dark
    - Light
    - System

Usage:
    from theme_manager import ThemeManager

    theme_manager = ThemeManager(app)
    theme_manager.set_theme("Dark")
"""

import os
import sys

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette, QFont
from PyQt6.QtWidgets import QApplication

# Qt color scheme enum (available in modern PyQt6 versions).
try:
    from PyQt6.QtCore import Qt
    QtColorScheme = Qt.ColorScheme
except AttributeError:
    class QtColorScheme:
        Dark = None
        Light = None


class ThemeManager(QObject):

    themeChanged = pyqtSignal(str)

    THEMES = ("Dark", "Light", "System")

    THEME = {
        "dark": {
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
            "tooltip": "#182542",
            "table_row": "#0F182B",
            "table_alt": "#142038",
            "header_bg": "#182745",
            "overdue_tint": "#2A1420",
            "amber_tint": "#2B2112",
            "chart_issued": "#38BDF8",
            "chart_returned": "#34D399",
            "inventory_issued": "#60A5FA",
            "inventory_due": "#FBBF24",
            "inventory_overdue": "#FB7185",
        },
        "light": {
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
            "tooltip": "#DCE7F7",
            "table_row": "#E4EDF9",
            "table_alt": "#D6E3F6",
            "header_bg": "#C0D3EE",
            "overdue_tint": "#F8CFD7",
            "amber_tint": "#FCE0A2",
            "chart_issued": "#0369A1",
            "chart_returned": "#047857",
            "inventory_issued": "#1D4ED8",
            "inventory_due": "#B45309",
            "inventory_overdue": "#BE123C",
        },
    }
    COLORS = {
        "Dark": THEME["dark"],
        "Light": THEME["light"],
    }

    def __init__(self, app: QApplication, initial_theme="Dark"):
        super().__init__()

        self.app = app
        self.app.setProperty("theme_manager", self)
        self.current_theme = initial_theme
        self.active_theme = "Dark"

        self.app.setStyle("Fusion")
        self.app.setFont(QFont("Segoe UI", 10))

        # Automatically detect Windows appearance changes.
        self.style_hints = self.app.styleHints()

        try:
            self.style_hints.colorSchemeChanged.connect(
                self._on_system_theme_changed
            )
        except (AttributeError, TypeError):
            pass

        self.apply_theme(initial_theme)

    def set_theme(self, theme: str):
        """Change the selected application theme."""

        if theme not in self.THEMES:
            raise ValueError(
                f"Invalid theme: {theme}. "
                f"Choose from {', '.join(self.THEMES)}."
            )

        self.current_theme = theme
        self.apply_theme(theme)

    def get_theme(self):
        """Return the selected theme setting."""

        return self.current_theme

    def get_active_theme(self):
        """Return the currently applied visual theme."""

        return self.active_theme

    def _get_system_theme(self):
        """Detect the operating system's preferred color scheme."""

        try:
            scheme = self.style_hints.colorScheme()

            if scheme == QtColorScheme.Dark:
                return "Dark"

            if scheme == QtColorScheme.Light:
                return "Light"

        except (AttributeError, RuntimeError):
            pass

        return "Light"

    def _on_system_theme_changed(self, scheme):
        """Reapply the theme when the OS appearance changes."""

        if self.current_theme == "System":
            self.apply_theme("System")

    def apply_theme(self, theme=None):
        """Apply the selected theme to the entire application."""

        if theme is not None:
            self.current_theme = theme

        if self.current_theme == "System":
            active = self._get_system_theme()
        else:
            active = self.current_theme

        if active not in self.COLORS:
            active = "Dark"

        self.active_theme = active

        colors = self.COLORS[active]

        self.app.setPalette(self._create_palette(colors))
        self.app.setStyleSheet(self._create_stylesheet(colors))

        self.themeChanged.emit(active)

    @staticmethod
    def _create_palette(c):
        """Create a consistent Qt application palette."""

        palette = QPalette()

        palette.setColor(
            QPalette.ColorRole.Window,
            QColor(c["window"])
        )
        palette.setColor(
            QPalette.ColorRole.WindowText,
            QColor(c["text"])
        )
        palette.setColor(
            QPalette.ColorRole.Base,
            QColor(c["input"])
        )
        palette.setColor(
            QPalette.ColorRole.AlternateBase,
            QColor(c["surface_alt"])
        )
        palette.setColor(
            QPalette.ColorRole.ToolTipBase,
            QColor(c["tooltip"])
        )
        palette.setColor(
            QPalette.ColorRole.ToolTipText,
            QColor(c["text"])
        )
        palette.setColor(
            QPalette.ColorRole.Text,
            QColor(c["text"])
        )
        palette.setColor(
            QPalette.ColorRole.Button,
            QColor(c["surface"])
        )
        palette.setColor(
            QPalette.ColorRole.ButtonText,
            QColor(c["text"])
        )
        palette.setColor(
            QPalette.ColorRole.Highlight,
            QColor(c["selection"])
        )
        palette.setColor(
            QPalette.ColorRole.HighlightedText,
            QColor("#FFFFFF")
        )
        palette.setColor(
            QPalette.ColorRole.PlaceholderText,
            QColor(c["muted"])
        )

        return palette

    @staticmethod
    def _create_stylesheet(c):
        """Central application stylesheet."""

        resource_root = getattr(
            sys,
            "_MEIPASS",
            os.path.dirname(os.path.abspath(__file__)),
        )
        checkbox_check = os.path.join(
            resource_root,
            "assets",
            "checkbox-check.svg",
        ).replace("\\", "/")
        is_dark = QColor(c["window"]).lightness() < 128
        arrow_scheme = "light" if is_dark else "dark"
        spin_up_arrow = os.path.join(
            resource_root,
            "assets",
            f"spin-up-{arrow_scheme}.svg",
        ).replace("\\", "/")
        spin_down_arrow = os.path.join(
            resource_root,
            "assets",
            f"spin-down-{arrow_scheme}.svg",
        ).replace("\\", "/")

        return f"""
        /* ---------- GLOBAL ---------- */

        QWidget {{
            color: {c["text"]};
            font-family: "Segoe UI";
            font-size: 10pt;
        }}

        QMainWindow,
        QDialog,
        QWidget#centralWidget {{
            background-color: {c["window"]};
        }}

        QToolTip {{
            background-color: {c["tooltip"]};
            color: {c["text"]};
            border: 1px solid {c["primary"]};
            padding: 7px 10px;
            border-radius: 7px;
            font-weight: 500;
        }}

        /* ---------- BUTTONS ---------- */

        QPushButton {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 8px 14px;
            min-height: 22px;
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: {c["surface_elevated"]};
            border-color: {c["primary"]};
        }}

        QPushButton:pressed {{
            background-color: {c["selection"]};
            color: #FFFFFF;
        }}

        QPushButton:disabled {{
            color: {c["muted"]};
            background-color: {c["surface"]};
            border-color: {c["border"]};
        }}

        QPushButton:default {{
            border: 1px solid {c["primary"]};
        }}

        /* Semantic Action Button Variants */

        QPushButton#PrimaryButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["primary"]},
                stop:1 {c["indigo"]}
            );
            color: #FFFFFF;
            font-weight: 700;
            border: 1px solid {c["primary_hover"]};
        }}

        QPushButton#PrimaryButton:hover {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["primary_hover"]},
                stop:1 {c["indigo_hover"]}
            );
            border-color: {c["cyan"]};
        }}

        QPushButton#PrimaryButton:disabled {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1px solid {c["border"]};
        }}

        QPushButton#SuccessButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["success"]},
                stop:1 {c["teal"]}
            );
            color: #FFFFFF;
            font-weight: 700;
            border: 1px solid {c["success_hover"]};
        }}

        QPushButton#SuccessButton:hover {{
            background: {c["success_hover"]};
        }}

        QPushButton#SuccessButton:disabled {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1px solid {c["border"]};
        }}

        QPushButton#WarningButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["warning"]},
                stop:1 #EA580C
            );
            color: #FFFFFF;
            font-weight: 700;
            border: 1px solid {c["warning_hover"]};
        }}

        QPushButton#WarningButton:hover {{
            background: {c["warning_hover"]};
        }}

        QPushButton#WarningButton:disabled {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1px solid {c["border"]};
        }}

        QPushButton#InfoButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["cyan_hover"]},
                stop:1 {c["primary"]}
            );
            color: #FFFFFF;
            font-weight: 700;
            border: 1px solid {c["cyan_hover"]};
        }}

        QPushButton#InfoButton:hover {{
            background: {c["cyan_hover"]};
        }}

        QPushButton#InfoButton:disabled {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1px solid {c["border"]};
        }}

        QPushButton#SecondaryButton {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border_bright"]};
            font-weight: 600;
        }}

        QPushButton#SecondaryButton:hover {{
            background-color: {c["primary_soft"]};
            color: {c["text"]};
            border-color: {c["primary"]};
        }}

        QPushButton#DangerButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["danger"]},
                stop:1 {c["danger_hover"]}
            );
            color: #FFFFFF;
            font-weight: 700;
            border: 1px solid {c["danger_hover"]};
        }}

        QPushButton#DangerButton:hover {{
            background-color: {c["danger_hover"]};
        }}

        QPushButton#DangerButton:disabled {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1px solid {c["border"]};
        }}

        /* ---------- INPUTS ---------- */

        QLineEdit,
        QTextEdit,
        QPlainTextEdit,
        QSpinBox,
        QDoubleSpinBox,
        QDateEdit,
        QDateTimeEdit,
        QTimeEdit,
        QComboBox {{
            background-color: {c["input"]};
            color: {c["text"]};
            border: 1.5px solid {c["border"]};
            border-radius: 8px;
            padding: 7px 9px;
            selection-background-color: {c["selection"]};
        }}

        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QDateEdit,
        QDateTimeEdit,
        QTimeEdit,
        QComboBox {{
            min-height: 20px;
        }}

        QLineEdit:focus,
        QTextEdit:focus,
        QPlainTextEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QDateEdit:focus,
        QDateTimeEdit:focus,
        QComboBox:focus {{
            border: 1.5px solid {c["primary"]};
            background-color: {c["surface"]};
        }}

        QSpinBox,
        QDoubleSpinBox {{
            padding-right: 26px;
        }}

        QSpinBox::up-button,
        QDoubleSpinBox::up-button,
        QSpinBox::down-button,
        QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 18px;
            background-color: {c["surface_alt"]};
            border-left: 1px solid {c["border"]};
        }}

        QSpinBox::up-button,
        QDoubleSpinBox::up-button {{
            border-top-right-radius: 5px;
        }}

        QSpinBox::down-button,
        QDoubleSpinBox::down-button {{
            subcontrol-position: bottom right;
            border-top: 1px solid {c["border"]};
            border-bottom-right-radius: 5px;
        }}

        QSpinBox::up-button:hover,
        QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover,
        QDoubleSpinBox::down-button:hover {{
            background-color: {c["primary_soft"]};
        }}

        QSpinBox::up-arrow,
        QDoubleSpinBox::up-arrow {{
            image: url("{spin_up_arrow}");
            width: 8px;
            height: 6px;
        }}

        QSpinBox::down-arrow,
        QDoubleSpinBox::down-arrow {{
            image: url("{spin_down_arrow}");
            width: 8px;
            height: 6px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["primary"]};
            selection-background-color: {c["selection"]};
            selection-color: #FFFFFF;
            outline: none;
            padding: 3px;
        }}

        /* ---------- TABLES ---------- */

        QTableWidget,
        QTableView,
        QTreeWidget,
        QTreeView {{
            background-color: {c["table_row"]};
            alternate-background-color: {c["table_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            gridline-color: {c["border"]};
            selection-background-color: {c["selection"]};
            selection-color: #FFFFFF;
            outline: none;
        }}

        QTableWidget::item,
        QTableView::item,
        QTreeWidget::item,
        QTreeView::item {{
            padding: 7px 9px;
            border: none;
        }}

        QTableWidget::item:selected,
        QTableView::item:selected,
        QTreeWidget::item:selected,
        QTreeView::item:selected {{
            background-color: {c["selection"]};
            color: #FFFFFF;
            border: none;
            border-radius: 0px;
        }}

        QHeaderView::section {{
            background-color: {c["header_bg"]};
            color: {c["text"]};
            border: none;
            border-bottom: 2px solid {c["border_bright"]};
            padding: 10px 10px;
            font-weight: 700;
        }}

        QLabel#PageTitle {{
            color: {c["text"]};
            font-size: 23px;
            font-weight: 800;
        }}

        QLabel#PageSubtitle {{
            color: {c["muted"]};
            font-size: 12px;
        }}

        QLabel#SectionTitle {{
            color: {c["text"]};
            font-size: 14px;
            font-weight: 700;
        }}

        /* Dialog semantic classes & status badges */

        QLabel[class="dialog-heading"] {{
            color: {c["text"]};
            font-size: 17px;
            font-weight: 800;
            background: {c["primary_soft"]};
            border-left: 4px solid {c["primary"]};
            border-radius: 7px;
            padding: 7px 12px;
        }}

        QLabel[class="barcode-preview"],
        QLabel[class="camera-preview"] {{
            background: {c["surface_alt"]};
            color: {c["muted"]};
            border: 1.5px dashed {c["border_bright"]};
            border-radius: 10px;
            padding: 12px;
        }}

        QFrame#ProjectionCard {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {c["cyan_soft"]},
                stop:1 {c["indigo_soft"]}
            );
            border: 1px solid {c["cyan"]};
            border-left: 4px solid {c["cyan"]};
            border-radius: 10px;
        }}

        QLabel[status="issued"] {{
            background: {c["primary_soft"]};
            color: {c["primary"]};
            border: 1px solid {c["primary"]};
            border-radius: 10px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 11px;
        }}

        QLabel[status="overdue"] {{
            background: {c["danger_soft"]};
            color: {c["danger"]};
            border: 1px solid {c["danger"]};
            border-radius: 10px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 11px;
        }}

        QLabel[status="returned"] {{
            background: {c["success_soft"]};
            color: {c["success"]};
            border: 1px solid {c["success"]};
            border-radius: 10px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 11px;
        }}

        QLabel[status="renewed"] {{
            background: {c["cyan_soft"]};
            color: {c["cyan"]};
            border: 1px solid {c["cyan"]};
            border-radius: 10px;
            padding: 3px 10px;
            font-weight: 700;
            font-size: 11px;
        }}

        /* ---------- CHECKBOXES / RADIO ---------- */

        QCheckBox,
        QRadioButton {{
            spacing: 8px;
            color: {c["text"]};
        }}

        QCheckBox::indicator,
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            background-color: {c["input"]};
            border: 1.5px solid {c["muted"]};
        }}

        QCheckBox::indicator {{
            border-radius: 4px;
        }}

        QCheckBox::indicator:checked,
        QRadioButton::indicator:checked {{
            background-color: {c["primary"]};
            border: 1.5px solid {c["primary"]};
        }}

        QCheckBox::indicator:checked {{
            image: url("{checkbox_check}");
        }}

        QCheckBox::indicator:hover,
        QRadioButton::indicator:hover {{
            border-color: {c["primary"]};
        }}

        QCheckBox::indicator:disabled,
        QRadioButton::indicator:disabled {{
            background-color: {c["surface"]};
            border-color: {c["border"]};
        }}

        QRadioButton::indicator {{
            border-radius: 9px;
        }}

        QCheckBox:disabled,
        QRadioButton:disabled {{
            color: {c["muted"]};
        }}

        /* ---------- GROUP BOX ---------- */

        QGroupBox {{
            background-color: {c["surface"]};
            border: 1.5px solid {c["border_bright"]};
            border-radius: 10px;
            margin-top: 15px;
            padding: 18px 12px 12px 12px;
            font-weight: 700;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            top: 4px;
            left: 12px;
            padding: 2px 10px;
            color: {c["primary"]};
            background-color: {c["surface_elevated"]};
            border: 1.5px solid {c["border_bright"]};
            border-radius: 6px;
        }}

        /* ---------- SCROLLBARS ---------- */

        QAbstractScrollArea::corner {{
            background: transparent;
            border: none;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 3px 1px 3px 1px;
        }}

        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 1px 3px 1px 3px;
        }}

        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {{
            background: {c["border_bright"]};
            border-radius: 3px;
            min-height: 28px;
            min-width: 28px;
        }}

        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:horizontal:hover {{
            background: {c["primary"]};
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
        }}

        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {{
            background: transparent;
            border: none;
        }}

        /* ---------- TABS ---------- */

        QTabWidget::pane {{
            background-color: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            top: -1px;
        }}

        QTabBar::tab {{
            background-color: {c["surface_alt"]};
            color: {c["muted"]};
            padding: 9px 16px;
            border: 1px solid {c["border"]};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            margin-right: 4px;
            font-weight: 600;
        }}

        QTabBar::tab:hover {{
            background-color: {c["primary_soft"]};
            color: {c["text"]};
        }}

        QTabBar::tab:selected {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["primary"]},
                stop:1 {c["indigo"]}
            );
            color: #FFFFFF;
            border-color: {c["primary"]};
            font-weight: 700;
        }}

        /* ---------- MENUS ---------- */

        QMenu {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border_bright"]};
            border-radius: 8px;
            padding: 5px;
        }}

        QMenu::item {{
            padding: 7px 25px;
            border-radius: 5px;
        }}

        QMenu::item:selected {{
            background-color: {c["selection"]};
            color: #FFFFFF;
        }}

        QMenu::separator {{
            height: 1px;
            background-color: {c["border"]};
            margin: 5px;
        }}

        /* ---------- PROGRESS BAR ---------- */

        QProgressBar {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 6px;
            text-align: center;
        }}

        QProgressBar::chunk {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {c["success"]},
                stop:1 {c["cyan"]}
            );
            border-radius: 5px;
        }}

        /* ---------- CALENDAR ---------- */

        QCalendarWidget QWidget {{
            background-color: {c["surface"]};
            color: {c["text"]};
        }}

        QCalendarWidget QToolButton {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border-radius: 5px;
            padding: 5px;
        }}

        QCalendarWidget QAbstractItemView {{
            background-color: {c["surface"]};
            color: {c["text"]};
            selection-background-color: {c["selection"]};
            selection-color: #FFFFFF;
        }}

        QCalendarWidget QAbstractItemView:disabled {{
            color: {c["muted"]};
        }}

        /* ---------- SPLITTER ---------- */

        QSplitter::handle {{
            background-color: {c["border"]};
        }}

        QSplitter::handle:hover {{
            background-color: {c["primary"]};
        }}

        /* ---------- FRAMES ---------- */

        QFrame {{
            border-color: {c["border"]};
        }}

        QFrame#SettingsCard {{
            background-color: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 12px;
        }}

        QFrame#DangerFrame {{
            background-color: {c["danger_soft"]};
            border: 1px solid {c["danger"]};
            border-left: 4px solid {c["danger"]};
            border-radius: 10px;
        }}
        """

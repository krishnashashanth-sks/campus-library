
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
            "window": "#0B1120",
            "surface": "#151F32",
            "surface_alt": "#1B2940",
            "input": "#111B2D",
            "border": "#28354A",
            "text": "#F8FAFC",
            "muted": "#94A3B8",
            "primary": "#2563EB",
            "primary_hover": "#2563EB",
            "selection": "#1D4ED8",
            "success": "#10B981",
            "success_hover": "#059669",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "tooltip": "#151F32",
            "table_row": "#131C2E",
            "table_alt": "#182338",
            "overdue_tint": "#1E1B18",
            "amber_tint": "#2B2415",
            "chart_issued": "#38BDF8",
            "chart_returned": "#34D399",
            "inventory_issued": "#3B82F6",
            "inventory_due": "#F59E0B",
            "inventory_overdue": "#EF4444",
        },
        "light": {
            "window": "#F1F5F9",
            "surface": "#FFFFFF",
            "surface_alt": "#E8EEF5",
            "input": "#FFFFFF",
            "border": "#CBD5E1",
            "text": "#0F172A",
            "muted": "#64748B",
            "primary": "#2563EB",
            "primary_hover": "#1D4ED8",
            "selection": "#BFDBFE",
            "success": "#10B981",
            "success_hover": "#059669",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "tooltip": "#FFFFFF",
            "table_row": "#FFFFFF",
            "table_alt": "#F1F5F9",
            "overdue_tint": "#FEE2E2",
            "amber_tint": "#FEF3C7",
            "chart_issued": "#38BDF8",
            "chart_returned": "#34D399",
            "inventory_issued": "#3B82F6",
            "inventory_due": "#F59E0B",
            "inventory_overdue": "#EF4444",
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
        arrow_scheme = (
            "light" if c["text"].lower() == "#e8eef8" else "dark"
        )
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
            border: 1px solid {c["border"]};
            padding: 6px 9px;
            border-radius: 5px;
        }}

        /* ---------- BUTTONS ---------- */

        QPushButton {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 8px 14px;
            min-height: 22px;
        }}

        QPushButton:hover {{
            background-color: {c["surface"]};
            border-color: {c["primary"]};
        }}

        QPushButton:pressed {{
            background-color: {c["selection"]};
        }}

        QPushButton:disabled {{
            color: {c["muted"]};
            background-color: {c["surface"]};
            border-color: {c["border"]};
        }}

        QPushButton:default {{
            border: 1px solid {c["primary"]};
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
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 7px 9px;
            selection-background-color: {c["selection"]};
        }}

        QLineEdit:focus,
        QTextEdit:focus,
        QPlainTextEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QDateEdit:focus,
        QDateTimeEdit:focus,
        QComboBox:focus {{
            border: 1px solid {c["primary"]};
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
            background-color: {c["selection"]};
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
            border: 1px solid {c["border"]};
            selection-background-color: {c["selection"]};
            selection-color: #FFFFFF;
            outline: none;
        }}

        /* ---------- TABLES ---------- */

        QTableWidget,
        QTableView,
        QTreeWidget,
        QTreeView {{
            background-color: {c["surface"]};
            alternate-background-color: {c["surface_alt"]};
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
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: none;
            border-bottom: 1px solid {c["border"]};
            padding: 10px 10px;
            font-weight: 600;
        }}

        QLabel#PageTitle {{
            color: {c["text"]};
            font-size: 23px;
            font-weight: 700;
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
            border: 1px solid {c["muted"]};
        }}

        QCheckBox::indicator {{
            border-radius: 4px;
        }}

        QCheckBox::indicator:checked,
        QRadioButton::indicator:checked {{
            background-color: {c["primary"]};
            border: 1px solid {c["primary"]};
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
            border: 1px solid {c["border"]};
            border-radius: 8px;
            margin-top: 12px;
            padding: 12px;
            font-weight: 600;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 5px;
        }}

        /* ---------- SCROLLBARS ---------- */

        QScrollBar:vertical {{
            background: {c["window"]};
            width: 10px;
            margin: 0;
        }}

        QScrollBar:horizontal {{
            background: {c["window"]};
            height: 10px;
            margin: 0;
        }}

        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {{
            background: {c["border"]};
            border-radius: 5px;
            min-height: 25px;
            min-width: 25px;
        }}

        QScrollBar::handle:hover {{
            background: {c["muted"]};
        }}

        QScrollBar::add-line,
        QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
        }}

        /* ---------- TABS ---------- */

        QTabWidget::pane {{
            border: 1px solid {c["border"]};
            border-radius: 8px;
        }}

        QTabBar::tab {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            padding: 9px 16px;
            border: none;
            margin-right: 2px;
        }}

        QTabBar::tab:selected {{
            background-color: {c["primary"]};
            color: #FFFFFF;
        }}

        /* ---------- MENUS ---------- */

        QMenu {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            padding: 5px;
        }}

        QMenu::item {{
            padding: 7px 25px;
            border-radius: 4px;
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
            border-radius: 5px;
            text-align: center;
        }}

        QProgressBar::chunk {{
            background-color: {c["primary"]};
            border-radius: 4px;
        }}

        /* ---------- CALENDAR ---------- */

        QCalendarWidget QWidget {{
            background-color: {c["surface"]};
            color: {c["text"]};
        }}

        QCalendarWidget QToolButton {{
            background-color: {c["surface_alt"]};
            color: {c["text"]};
            border: none;
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
            background-color: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.30);
            border-radius: 8px;
        }}

        QPushButton#PrimaryButton {{
            background-color: {c["primary"]};
            color: white;
            font-weight: 600;
            border: none;
        }}

        QPushButton#DangerButton {{
            background-color: #DC2626;
            color: white;
            font-weight: 600;
            border: none;
        }}
        """


import csv
import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QCursor
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from dialogs import (
    BarcodeGeneratorDialog,
    BookDialog,
    QuickScanDialog,
    UserDialog,
)


PRIMARY = "#2563eb"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#6366f1"


# ============================================================
# THEME HELPERS
# ============================================================

def get_theme_colors():
    app = QApplication.instance()
    palette = app.palette() if app else QApplication.palette()

    return {
        "window": palette.color(palette.ColorRole.Window).name(),
        "surface": palette.color(palette.ColorRole.Base).name(),
        "surface_alt": palette.color(palette.ColorRole.AlternateBase).name(),
        "text": palette.color(palette.ColorRole.Text).name(),
        "muted": palette.color(palette.ColorRole.PlaceholderText).name(),
        "border": palette.color(palette.ColorRole.Mid).name(),
        "primary": palette.color(palette.ColorRole.Highlight).name(),
        "selection_text": palette.color(
            palette.ColorRole.HighlightedText
        ).name(),
        "button": palette.color(palette.ColorRole.Button).name(),
        "button_text": palette.color(
            palette.ColorRole.ButtonText
        ).name(),
    }


def safe_text(value):
    return "" if value is None else str(value)


def activity_color(action_type):
    action = safe_text(action_type).lower()

    if "return" in action:
        return SUCCESS
    if "overdue" in action:
        return DANGER
    if "fine" in action:
        return WARNING
    if "issue" in action or "checkout" in action:
        return PRIMARY

    return INFO


def activity_icon(action_type):
    action = safe_text(action_type).lower()

    if "return" in action:
        return "↩"
    if "overdue" in action:
        return "⚠"
    if "fine" in action:
        return "₹"
    if "issue" in action or "checkout" in action:
        return "↗"

    return "●"


def connect_theme(widget):
    app = QApplication.instance()
    manager = getattr(app, "theme_manager", None) if app else None

    if manager:
        try:
            manager.themeChanged.connect(widget.apply_theme)
        except (TypeError, RuntimeError):
            pass

    return manager


def disconnect_theme(widget):
    manager = getattr(widget, "theme_manager", None)

    if manager:
        try:
            manager.themeChanged.disconnect(widget.apply_theme)
        except (TypeError, RuntimeError):
            pass


# ============================================================
# METRIC CARD
# ============================================================

class MetricCard(QFrame):
    clicked = pyqtSignal()

    def __init__(
        self,
        title,
        value,
        subtitle,
        icon,
        accent_color,
        inventory=False,
        parent=None,
    ):
        super().__init__(parent)

        self.inventory = inventory
        self.accent_color = accent_color

        self.setObjectName("MetricCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(125)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(7)

        top = QHBoxLayout()

        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        top.addWidget(self.title_label)
        top.addStretch()

        self.icon_label = QLabel(icon)
        self.icon_label.setObjectName("MetricIcon")
        top.addWidget(self.icon_label)

        layout.addLayout(top)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        layout.addWidget(self.value_label)

        self.progress_bar = None

        if inventory:
            self.progress_bar = QProgressBar()
            self.progress_bar.setObjectName("InventoryProgress")
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(7)
            layout.addWidget(self.progress_bar)
        else:
            spacer = QWidget()
            spacer.setFixedHeight(7)
            layout.addWidget(spacer)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricSubtitle")
        layout.addWidget(self.subtitle_label)

        layout.addStretch()
        self.apply_style()

    def apply_style(self, *_):
        c = get_theme_colors()

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-left: 4px solid {self.accent_color};
                border-radius: 12px;
            }}
            QFrame#MetricCard:hover {{
                background: {c['surface_alt']};
                border: 1px solid {self.accent_color};
            }}
            QLabel#MetricTitle {{
                color: {c['muted']};
                font-size: 12px;
                font-weight: 600;
                border: none;
                background: transparent;
            }}
            QLabel#MetricIcon {{
                color: {self.accent_color};
                font-size: 19px;
                border: none;
                background: transparent;
            }}
            QLabel#MetricValue {{
                color: {c['text']};
                font-size: 25px;
                font-weight: 750;
                border: none;
                background: transparent;
            }}
            QLabel#MetricSubtitle {{
                color: {c['muted']};
                font-size: 10px;
                border: none;
                background: transparent;
            }}
            QProgressBar#InventoryProgress {{
                background: {c['surface_alt']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#InventoryProgress::chunk {{
                background: {self.accent_color};
                border-radius: 3px;
            }}
        """)

    def set_metric(self, value, subtitle=None):
        self.value_label.setText(str(value))

        if subtitle is not None:
            self.subtitle_label.setText(str(subtitle))

    def set_inventory(self, available_copies, total_copies):
        if not self.progress_bar:
            return

        total = max(int(total_copies or 0), 0)
        available = max(min(int(available_copies or 0), total), 0)

        percentage = int(available / total * 100) if total else 0

        if available == 0:
            self.accent_color = DANGER
            status = "Empty inventory"
        elif percentage <= 25:
            self.accent_color = WARNING
            status = f"Low stock · {percentage}% available"
        else:
            self.accent_color = SUCCESS
            status = f"Healthy stock · {percentage}% available"

        self.value_label.setText(f"{available:,} / {total:,}")
        self.subtitle_label.setText(status)
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(available)

        self.apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ============================================================
# SHARED DIALOG THEME
# ============================================================

def dialog_stylesheet(c):
    return f"""
        QDialog {{
            background: {c['window']};
            color: {c['text']};
        }}

        QLabel {{
            color: {c['text']};
        }}

        QLineEdit, QComboBox {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 7px;
            padding: 9px 11px;
            min-height: 20px;
        }}

        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {c['primary']};
        }}

        QTableWidget {{
            background: {c['surface']};
            alternate-background-color: {c['surface_alt']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 9px;
            gridline-color: transparent;
            selection-background-color: {c['primary']};
            selection-color: white;
            outline: none;
        }}

        QTableWidget::item {{
            padding: 9px 10px;
            border: none;
            border-bottom: 1px solid {c['border']};
            border-radius: 0px;
        }}

        QTableWidget::item:selected {{
            background: {c['primary']};
            color: white;
            border-radius: 0px;
        }}

        QHeaderView::section {{
            background: {c['surface_alt']};
            color: {c['text']};
            font-size: 11px;
            font-weight: 700;
            border: none;
            border-bottom: 1px solid {c['border']};
            padding: 12px 9px;
        }}

        QPushButton {{
            background: {c['primary']};
            color: white;
            border: none;
            border-radius: 7px;
            padding: 9px 18px;
            font-weight: 600;
            min-height: 19px;
        }}

        QPushButton:hover {{
            background: {c['button']};
            color: {c['button_text']};
        }}

        QPushButton:disabled {{
            background: {c['surface_alt']};
            color: {c['muted']};
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 9px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical {{
            background: {c['border']};
            border-radius: 4px;
            min-height: 25px;
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """


# ============================================================
# METRIC DETAIL DIALOG
# ============================================================


class MetricDetailDialog(QDialog):
    """Responsive dashboard record viewer with balanced table columns."""

    COLUMN_WEIGHTS = {
        "User ID": 1.15,
        "Book ID": 1.10,
        "Name": 1.25,
        "Title": 1.80,
        "Phone": 1.15,
        "Role": 0.90,
        "Department": 1.35,
        "Publisher": 1.45,
        "Author": 1.35,
        "Total Copies": 1.10,
        "Available": 1.00,
        "Created On": 1.20,
        "Added On": 1.20,
        "Issue Date": 1.30,
        "Due Date": 1.20,
        "Return Date": 1.25,
        "Fine Amount": 1.15,
    }

    def __init__(
        self,
        title: str,
        headers: List[str],
        rows: List[Tuple[object, ...]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.headers = headers
        self.rows = rows or []

        self.setWindowTitle(title)
        self.resize(1050, 620)
        self.setMinimumSize(760, 450)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(24, 22, 24, 22)
        self.layout_main.setSpacing(16)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        self.layout_main.addWidget(self.title_label)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("RecordSearch")
        self.search_input.setPlaceholderText(
            "Search by ID, title, author or any field..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(36)
        self.search_input.textChanged.connect(self.apply_search)
        self.layout_main.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(43)

        # Important: fixed sections allow us to calculate
        # proportional widths ourselves.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(65)
        header.setHighlightSections(False)

        self.layout_main.addWidget(self.table, 1)
        self.visible_rows = list(self.rows)

        footer = QHBoxLayout()

        self.count_label = QLabel()
        self.count_label.setObjectName("RecordCount")
        self.populate_table()

        footer.addWidget(self.count_label)
        footer.addStretch()

        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.setMinimumHeight(38)
        close_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        close_button.clicked.connect(self.accept)

        footer.addWidget(close_button)
        self.layout_main.addLayout(footer)

        app = QApplication.instance()
        self.theme_manager = (
            getattr(app, "theme_manager", None)
            if app else None
        )

        self.apply_theme()

        if self.theme_manager:
            try:
                self.theme_manager.themeChanged.connect(
                    self.apply_theme
                )
            except (TypeError, RuntimeError):
                pass

    def apply_search(self, text):
        query = text.strip().casefold()

        if query:
            self.visible_rows = [
                row for row in self.rows
                if any(
                    query in safe_text(value).casefold()
                    for value in row
                )
            ]
        else:
            self.visible_rows = list(self.rows)

        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.visible_rows))

        for row_index, row_data in enumerate(self.visible_rows):
            for column_index in range(len(self.headers)):
                value = (
                    row_data[column_index]
                    if column_index < len(row_data)
                    else ""
                )

                item = QTableWidgetItem(safe_text(value))

                if column_index == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignVCenter
                        | Qt.AlignmentFlag.AlignLeft
                    )

                self.table.setItem(row_index, column_index, item)

        query = self.search_input.text().strip()
        if query:
            self.count_label.setText(
                f"{len(self.visible_rows)} of {len(self.rows)} record(s)"
            )
        else:
            self.count_label.setText(f"{len(self.rows)} record(s)")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_columns()

    def showEvent(self, event):
        super().showEvent(event)
        self._resize_columns()

    def _resize_columns(self):
        """Distribute available table width proportionally."""

        column_count = len(self.headers)

        if column_count == 0:
            return

        available_width = self.table.viewport().width()

        if available_width <= 0:
            return

        weights = [
            self.COLUMN_WEIGHTS.get(header, 1.15)
            for header in self.headers
        ]

        total_weight = sum(weights)

        if total_weight <= 0:
            return

        widths = [
            int(available_width * weight / total_weight)
            for weight in weights
        ]

        # Assign rounding remainder to the final column
        # so the complete table width is used.
        widths[-1] += available_width - sum(widths)

        for index, width in enumerate(widths):
            self.table.setColumnWidth(
                index,
                max(65, width),
            )

    def apply_theme(self, *_):
        c = get_theme_colors()

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c['window']};
                color: {c['text']};
            }}

            QLabel#DialogTitle {{
                color: {c['text']};
                font-size: 20px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#RecordCount {{
                color: {c['muted']};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}

            QLineEdit#RecordSearch {{
                background-color: {c['surface']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 7px;
                padding: 7px 10px;
                font-size: 12px;
            }}

            QLineEdit#RecordSearch:focus {{
                border: 1px solid {c['primary']};
            }}

            QTableWidget {{
                background-color: {c['surface']};
                alternate-background-color: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: {c['primary']};
                selection-color: {c['selection_text']};
                outline: none;
                font-size: 12px;
            }}

            QTableWidget::item {{
                padding: 9px 10px;
                border: none;
                border-bottom: 1px solid {c['border']};
                border-radius: 0px;
            }}

            QTableWidget::item:selected {{
                background-color: {c['primary']};
                color: {c['selection_text']};
                border-radius: 0px;
            }}

            QHeaderView {{
                background-color: {c['surface_alt']};
                border: none;
            }}

            QHeaderView::section {{
                background-color: {c['surface_alt']};
                color: {c['text']};
                font-size: 11px;
                font-weight: 700;
                border: none;
                border-bottom: 1px solid {c['border']};
                padding: 12px 8px;
            }}

            QScrollBar:vertical {{
                background-color: {c['surface']};
                width: 9px;
                margin: 2px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {c['border']};
                min-height: 25px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {c['muted']};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QPushButton {{
                background-color: {c['primary']};
                color: white;
                border: none;
                border-radius: 7px;
                padding: 9px 20px;
                font-size: 12px;
                font-weight: 600;
            }}

            QPushButton:hover {{
                background-color: {c['primary']};
            }}

            QPushButton:pressed {{
                background-color: {c['surface_alt']};
            }}
        """)

        self._resize_columns()

    def closeEvent(self, event):
        if self.theme_manager:
            try:
                self.theme_manager.themeChanged.disconnect(
                    self.apply_theme
                )
            except (TypeError, RuntimeError):
                pass

        super().closeEvent(event)


# ============================================================
# ACTIVITY CARD
# ============================================================

class ActivityCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(
        self,
        action_type,
        book_title,
        username,
        timestamp,
        parent=None,
    ):
        super().__init__(parent)

        self.action_type = safe_text(action_type)
        self.book_title = safe_text(book_title)
        self.username = safe_text(username)
        self.timestamp = safe_text(timestamp)

        self.setObjectName("ActivityCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(95)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)

        header = QHBoxLayout()

        self.icon_label = QLabel(activity_icon(self.action_type))
        self.icon_label.setObjectName("ActivityIcon")

        self.type_label = QLabel(self.action_type)
        self.type_label.setObjectName("ActivityType")

        self.timestamp_label = QLabel(self.timestamp)
        self.timestamp_label.setObjectName("ActivityTimestamp")
        self.timestamp_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        header.addWidget(self.icon_label)
        header.addWidget(self.type_label, 1)
        header.addWidget(self.timestamp_label)

        layout.addLayout(header)

        self.book_label = QLabel(
            f"📖  {self.book_title or 'Book information unavailable'}"
        )
        self.book_label.setObjectName("ActivityBook")
        self.book_label.setWordWrap(True)
        layout.addWidget(self.book_label)

        self.user_label = QLabel(
            f"👤  {self.username or 'Unknown user'}"
        )
        self.user_label.setObjectName("ActivityDetails")
        layout.addWidget(self.user_label)

        hint = QLabel("Click to inspect transaction")
        hint.setObjectName("ActivityHint")
        layout.addWidget(hint)

        for child in self.findChildren(QLabel):
            child.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )

        self.apply_style()

    def apply_style(self, *_):
        c = get_theme_colors()
        accent = activity_color(self.action_type)

        self.setStyleSheet(f"""
            QFrame#ActivityCard {{
                background: {c['surface_alt']};
                border: 1px solid {c['border']};
                border-left: 4px solid {accent};
                border-radius: 9px;
            }}
            QFrame#ActivityCard:hover {{
                background: {c['surface']};
                border: 1px solid {c['primary']};
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {c['text']};
            }}
            QLabel#ActivityIcon {{
                color: {accent};
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#ActivityType {{
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#ActivityBook {{
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#ActivityTimestamp,
            QLabel#ActivityDetails {{
                color: {c['muted']};
                font-size: 10px;
            }}
            QLabel#ActivityHint {{
                color: {c['primary']};
                font-size: 10px;
                font-weight: 600;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)


# ============================================================
# ACTIVITY DETAIL DIALOG
# ============================================================

class ActivityDetailDialog(QDialog):
    def __init__(
        self,
        action_type,
        book_title,
        username,
        timestamp,
        parent=None,
    ):
        super().__init__(parent)

        self.action_type = safe_text(action_type)
        self.book_title = safe_text(book_title)
        self.username = safe_text(username)
        self.timestamp = safe_text(timestamp)

        self.setWindowTitle("Activity Details")
        self.resize(590, 480)
        self.setMinimumSize(480, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(13)

        title = QLabel(
            f"{activity_icon(self.action_type)}  {self.action_type}"
        )
        title.setStyleSheet(
            "font-size: 20px; font-weight: 750;"
        )
        layout.addWidget(title)

        self.add_detail(layout, "BOOK / ITEM", self.book_title)
        self.add_detail(layout, "USER", self.username)
        self.add_detail(layout, "ACTIVITY TYPE", self.action_type)
        self.add_detail(layout, "TIMESTAMP", self.timestamp)

        note = QLabel(
            "The recent activity database method currently supplies "
            "these four fields. Additional transaction details are "
            "not available from that result."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px;")
        layout.addWidget(note)

        footer = QHBoxLayout()

        copy_button = QPushButton("Copy Details")
        copy_button.clicked.connect(self.copy_details)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        footer.addWidget(copy_button)
        footer.addStretch()
        footer.addWidget(close_button)

        layout.addLayout(footer)

        self.theme_manager = connect_theme(self)
        self.apply_theme()

    def add_detail(self, parent_layout, heading, value):
        frame = QFrame()
        frame.setObjectName("DetailFrame")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(4)

        label = QLabel(heading)
        label.setStyleSheet("font-size: 10px; font-weight: 700;")

        value_label = QLabel(value or "Not available")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        value_label.setStyleSheet("font-size: 13px; font-weight: 600;")

        layout.addWidget(label)
        layout.addWidget(value_label)
        parent_layout.addWidget(frame)

    def copy_details(self):
        text = (
            f"Activity: {self.action_type}\n"
            f"Book: {self.book_title}\n"
            f"User: {self.username}\n"
            f"Timestamp: {self.timestamp}"
        )

        QApplication.clipboard().setText(text)

        QMessageBox.information(
            self,
            "Copied",
            "Activity details copied to clipboard.",
        )

    def apply_theme(self, *_):
        c = get_theme_colors()

        self.setStyleSheet(dialog_stylesheet(c) + f"""
            QFrame#DetailFrame {{
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 8px;
            }}
        """)

    def closeEvent(self, event):
        disconnect_theme(self)
        super().closeEvent(event)


# ============================================================
# ACTIVITY HISTORY DIALOG
# ============================================================

class ActivityHistoryDialog(QDialog):
    HEADERS = ["Activity", "Book / Item", "User", "Timestamp"]

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self.all_logs = []
        self.filtered_logs = []

        self.setWindowTitle("Complete Activity History")
        self.resize(1050, 650)
        self.setMinimumSize(750, 470)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(22, 22, 22, 22)
        self.main_layout.setSpacing(13)

        self.build_ui()

        self.theme_manager = connect_theme(self)
        self.apply_theme()
        self.load_history()

    def build_ui(self):
        header = QHBoxLayout()

        heading_col = QVBoxLayout()

        title = QLabel("Activity History")
        title.setStyleSheet("font-size: 21px; font-weight: 750;")

        description = QLabel(
            "Search, inspect and export circulation activity."
        )
        description.setStyleSheet("font-size: 11px;")

        heading_col.addWidget(title)
        heading_col.addWidget(description)

        header.addLayout(heading_col)
        header.addStretch()

        refresh = QPushButton("↻  Refresh")
        refresh.clicked.connect(self.load_history)
        header.addWidget(refresh)

        self.main_layout.addLayout(header)

        filter_frame = QFrame()
        filter_frame.setObjectName("FilterPanel")

        filters = QHBoxLayout(filter_frame)
        filters.setContentsMargins(12, 12, 12, 12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search activity, book, user or timestamp..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.apply_filters)

        self.type_filter = QComboBox()
        self.type_filter.addItems([
            "All Activities", "Issue", "Return",
            "Overdue", "Fine", "Other",
        ])
        self.type_filter.currentTextChanged.connect(
            self.apply_filters
        )

        filters.addWidget(self.search_input, 3)
        filters.addWidget(self.type_filter, 1)

        self.main_layout.addWidget(filter_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(43)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )

        self.table.cellDoubleClicked.connect(
            self.open_selected_activity
        )

        self.main_layout.addWidget(self.table, 1)

        footer = QHBoxLayout()

        self.count_label = QLabel("0 activities")
        footer.addWidget(self.count_label)
        footer.addStretch()

        self.hint_label = QLabel(
            "Double-click a record to inspect details."
        )
        footer.addWidget(self.hint_label)

        self.main_layout.addLayout(footer)

        buttons = QHBoxLayout()

        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self.export_csv)

        self.details_button = QPushButton("View Details")
        self.details_button.clicked.connect(
            self.open_selected_activity
        )

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons.addWidget(self.export_button)
        buttons.addWidget(self.details_button)
        buttons.addStretch()
        buttons.addWidget(close_button)

        self.main_layout.addLayout(buttons)

    def load_history(self):
        try:
            success, logs = self.db.get_recent_activity_logs(
                limit=10000
            )

            self.all_logs = list(logs or []) if success else []

            if not success:
                QMessageBox.warning(
                    self,
                    "Activity History",
                    "Could not retrieve activity records.",
                )

        except Exception as error:
            self.all_logs = []
            QMessageBox.critical(
                self,
                "Activity History Error",
                str(error),
            )

        self.apply_filters()

    def normalize_log(self, log):
        try:
            return (
                safe_text(log[0]) if len(log) > 0 else "",
                safe_text(log[1]) if len(log) > 1 else "",
                safe_text(log[2]) if len(log) > 2 else "",
                safe_text(log[3]) if len(log) > 3 else "",
            )
        except (TypeError, IndexError):
            return ("", "", "", "")

    def matches_type(self, action, selected):
        action = action.lower()

        if selected == "All Activities":
            return True
        if selected == "Issue":
            return "issue" in action or "checkout" in action
        if selected == "Return":
            return "return" in action
        if selected == "Overdue":
            return "overdue" in action
        if selected == "Fine":
            return "fine" in action
        if selected == "Other":
            known = ("issue", "checkout", "return", "overdue", "fine")
            return not any(word in action for word in known)

        return True

    def apply_filters(self, *_):
        query = self.search_input.text().strip().lower()
        selected = self.type_filter.currentText()

        self.filtered_logs = []

        for raw in self.all_logs:
            record = self.normalize_log(raw)

            if not self.matches_type(record[0], selected):
                continue

            if query and query not in " ".join(record).lower():
                continue

            self.filtered_logs.append(record)

        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.filtered_logs))

        for row, record in enumerate(self.filtered_logs):
            for col, value in enumerate(record):
                item = QTableWidgetItem(value)

                if col == 0:
                    item.setForeground(
                        QBrush(QColor(activity_color(value)))
                    )

                self.table.setItem(row, col, item)

        self.count_label.setText(
            f"{len(self.filtered_logs)} of "
            f"{len(self.all_logs)} activities"
        )

        enabled = bool(self.filtered_logs)
        self.details_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def open_selected_activity(self, *_):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.filtered_logs):
            QMessageBox.information(
                self,
                "Select Activity",
                "Please select an activity record first.",
            )
            return

        record = self.filtered_logs[row]

        dialog = ActivityDetailDialog(
            record[0], record[1], record[2], record[3], self
        )
        dialog.exec()

    def export_csv(self):
        if not self.filtered_logs:
            QMessageBox.information(
                self,
                "Export Activity",
                "There are no records to export.",
            )
            return

        filename = (
            "activity_history_"
            + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".csv"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Activity History",
            filename,
            "CSV Files (*.csv)",
        )

        if not path:
            return

        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            with open(
                path, "w", newline="", encoding="utf-8-sig"
            ) as file:
                writer = csv.writer(file)
                writer.writerow(self.HEADERS)
                writer.writerows(self.filtered_logs)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Activity history exported:\n{path}",
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Export Failed",
                str(error),
            )

    def apply_theme(self, *_):
        c = get_theme_colors()
        self.setStyleSheet(dialog_stylesheet(c) + f"""
            QFrame#FilterPanel {{
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 9px;
            }}
        """)

    def closeEvent(self, event):
        disconnect_theme(self)
        super().closeEvent(event)


# ============================================================
# MAIN DASHBOARD
# ============================================================

class DashboardView(QWidget):
    navigate_requested = pyqtSignal(str)

    def __init__(self, db):
        super().__init__()

        self.db = db
        self.metric_widgets: Dict[str, MetricCard] = {}

        self.setObjectName("DashboardView")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 22, 24, 22)
        self.main_layout.setSpacing(16)

        self.tiles_grid = QGridLayout()
        self.tiles_grid.setHorizontalSpacing(14)
        self.tiles_grid.setVerticalSpacing(14)

        for column in range(4):
            self.tiles_grid.setColumnStretch(column, 1)

        self.main_layout.addLayout(self.tiles_grid)
        self._create_metric_cards()

        lower_layout = QHBoxLayout()
        lower_layout.setSpacing(16)

        feed_container = QFrame()
        feed_container.setObjectName("DashboardPanel")

        feed_layout = QVBoxLayout(feed_container)
        feed_layout.setContentsMargins(19, 17, 19, 17)
        feed_layout.setSpacing(11)

        feed_header = QHBoxLayout()

        feed_title = QLabel("🕒  Recent Activity")
        feed_title.setObjectName("PanelTitle")
        feed_header.addWidget(feed_title)
        feed_header.addStretch()

        self.view_all_button = QPushButton("View All  →")
        self.view_all_button.setObjectName("ViewAllButton")
        self.view_all_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.view_all_button.clicked.connect(
            self.open_activity_history
        )
        feed_header.addWidget(self.view_all_button)

        feed_layout.addLayout(feed_header)

        self.activity_summary_label = QLabel(
            "Latest circulation transactions"
        )
        self.activity_summary_label.setObjectName("ActivitySummary")
        feed_layout.addWidget(self.activity_summary_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.feed_content_widget = QWidget()
        self.feed_inner_layout = QVBoxLayout(
            self.feed_content_widget
        )
        self.feed_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_inner_layout.setSpacing(10)

        self.scroll_area.setWidget(self.feed_content_widget)
        feed_layout.addWidget(self.scroll_area, 1)

        lower_layout.addWidget(feed_container, 3)
        lower_layout.addWidget(self.create_quick_actions(), 1)

        self.main_layout.addLayout(lower_layout, 1)

        self.theme_manager = connect_theme(self)
        self.apply_theme()
        self.refresh_dashboard()

    # --------------------------------------------------------
    # THEME
    # --------------------------------------------------------

    def apply_theme(self, *_):
        c = get_theme_colors()

        self.setStyleSheet(f"""
            QWidget#DashboardView {{
                background: {c['window']};
                color: {c['text']};
            }}

            QFrame#DashboardPanel {{
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 12px;
            }}

            QLabel#PanelTitle {{
                color: {c['text']};
                font-size: 15px;
                font-weight: 750;
                background: transparent;
                border: none;
            }}

            QLabel#ActivitySummary {{
                color: {c['muted']};
                font-size: 10px;
                background: transparent;
                border: none;
            }}

            QPushButton#QuickActionButton {{
                background: {c['surface_alt']};
                color: {c['text']};
                font-size: 11px;
                font-weight: 600;
                text-align: left;
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 11px 12px;
            }}

            QPushButton#QuickActionButton:hover {{
                border-color: {c['primary']};
                background: {c['button']};
            }}

            QPushButton#ViewAllButton {{
                background: transparent;
                color: {c['primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 7px 12px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#ViewAllButton:hover {{
                background: {c['surface_alt']};
                border-color: {c['primary']};
            }}
        """)

        for card in self.metric_widgets.values():
            card.apply_style()

        for index in range(self.feed_inner_layout.count()):
            item = self.feed_inner_layout.itemAt(index)
            widget = item.widget() if item else None

            if isinstance(widget, ActivityCard):
                widget.apply_style()

    # --------------------------------------------------------
    # METRIC CARDS
    # --------------------------------------------------------

    def _create_metric_cards(self):
        metrics = [
            (
                "total_users", "Total Users", "0",
                "Registered library users", "👥",
                PRIMARY, 0, 0, self.show_users_drilldown, False,
            ),
            (
                "unique_titles", "Unique Titles", "0",
                "Books in catalog", "📚",
                INFO, 0, 1, self.show_titles_drilldown, False,
            ),
            (
                "inventory", "Inventory", "0 / 0",
                "Available / Total Copies", "📦",
                SUCCESS, 0, 2, self.show_total_copies_drilldown, True,
            ),
            (
                "unpaid_fines", "Unpaid Fines", "₹0.00",
                "Pending collection", "💳",
                WARNING, 0, 3, self.show_fines_drilldown, False,
            ),
            (
                "active_loans", "Issued Books", "0",
                "Currently issued", "🔄",
                INFO, 1, 0, self.show_active_loans_drilldown, False,
            ),
            (
                "issued_today", "Issued Today", "0",
                "Books issued today", "📈",
                SUCCESS, 1, 1, self.show_issued_today_drilldown, False,
            ),
            (
                "overdue_books", "Overdue Books", "0",
                "Action required", "⚠️",
                DANGER, 1, 2, self.show_overdue_drilldown, False,
            ),
            (
                "today_due", "Due Today", "0",
                "Books due today", "📅",
                PRIMARY, 1, 3, self.show_due_today_drilldown, False,
            ),
        ]

        for (
            key, title, value, subtitle, icon, accent,
            row, column, callback, inventory
        ) in metrics:
            self.create_metric_card(
                key, title, value, subtitle, icon,
                accent, row, column, callback, inventory,
            )

    def create_metric_card(
        self,
        key,
        title,
        value,
        subtitle,
        icon,
        accent_color,
        row,
        column,
        callback,
        inventory=False,
    ):
        card = MetricCard(
            title,
            value,
            subtitle,
            icon,
            accent_color,
            inventory,
            self,
        )

        card.clicked.connect(callback)
        self.metric_widgets[key] = card
        self.tiles_grid.addWidget(card, row, column)

        return card

    # --------------------------------------------------------
    # QUICK ACTIONS
    # --------------------------------------------------------

    def create_quick_actions(self):
        card = QFrame()
        card.setObjectName("DashboardPanel")
        card.setMinimumWidth(215)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 17, 17, 17)
        layout.setSpacing(11)

        title = QLabel("⚡  Quick Actions")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        actions = [
            ("👤   Add New User", self.open_userform),
            ("📚   Add New Book", self.open_bookform),
            ("▦   Generate Barcode", self.open_bargenerate_form),
            ("▣   Quick Scan", self.open_quick_scan),
            ("📋   Activity History", self.open_activity_history),
            ("⟳   Refresh Dashboard", self.refresh_dashboard),
        ]

        for label, callback in actions:
            button = QPushButton(label)
            button.setObjectName("QuickActionButton")
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.setMinimumHeight(42)
            button.clicked.connect(callback)
            layout.addWidget(button)

        layout.addStretch()
        return card

    # --------------------------------------------------------
    # ACTIVITY STREAM
    # --------------------------------------------------------

    def create_activity_card(
        self,
        action_type,
        book_title,
        username,
        timestamp,
    ):
        card = ActivityCard(
            action_type,
            book_title,
            username,
            timestamp,
            self.feed_content_widget,
        )
        card.clicked.connect(self.open_activity_details)
        return card

    def open_activity_details(self, card):
        if not isinstance(card, ActivityCard):
            return

        dialog = ActivityDetailDialog(
            card.action_type,
            card.book_title,
            card.username,
            card.timestamp,
            self,
        )
        dialog.exec()

    def open_activity_history(self):
        dialog = ActivityHistoryDialog(self.db, self)
        dialog.exec()
        self.load_activity_log()

    def load_activity_log(self):
        while self.feed_inner_layout.count():
            item = self.feed_inner_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        try:
            success, logs = self.db.get_recent_activity_logs(
                limit=8
            )
        except Exception as error:
            success, logs = False, []
            print(f"Activity log error: {error}")

        if success and logs:
            for log in logs:
                try:
                    card = self.create_activity_card(
                        safe_text(log[0]),
                        safe_text(log[1]),
                        safe_text(log[2]),
                        safe_text(log[3]),
                    )
                    self.feed_inner_layout.addWidget(card)

                except (IndexError, TypeError) as error:
                    print(f"Invalid activity record: {error}")

            self.activity_summary_label.setText(
                f"Showing the latest {len(logs)} activity record(s)."
            )

        else:
            empty = QLabel(
                "No recent circulation activity yet."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setMinimumHeight(110)
            empty.setStyleSheet(
                "padding: 20px; border: 1px dashed "
                f"{get_theme_colors()['border']}; border-radius: 8px;"
            )

            self.feed_inner_layout.addWidget(empty)
            self.activity_summary_label.setText(
                "No recent transactions are available."
            )

        self.feed_inner_layout.addStretch(1)

    # --------------------------------------------------------
    # DASHBOARD METRICS
    # --------------------------------------------------------

    def update_dashboard_metrics(self):
        try:
            details = self.db.get_dashboard_details()

            if not details or len(details) < 9:
                raise ValueError(
                    "Invalid dashboard database result."
                )

            (
                total_users,
                unique_titles,
                total_copies,
                available_copies,
                active_loans,
                today_issued,
                overdue_books,
                due_today,
                unpaid_fines,
            ) = details

            self.metric_widgets["total_users"].set_metric(
                str(total_users)
            )

            self.metric_widgets["unique_titles"].set_metric(
                str(unique_titles)
            )

            self.metric_widgets["inventory"].set_inventory(
                available_copies,
                total_copies,
            )

            self.metric_widgets["active_loans"].set_metric(
                str(active_loans)
            )

            self.metric_widgets["issued_today"].set_metric(
                str(today_issued)
            )

            self.metric_widgets["overdue_books"].set_metric(
                str(overdue_books)
            )

            self.metric_widgets["today_due"].set_metric(
                str(due_today)
            )

            self.metric_widgets["unpaid_fines"].set_metric(
                f"₹{float(unpaid_fines or 0):,.2f}"
            )

        except Exception as error:
            print(f"Dashboard metrics error: {error}")

    # --------------------------------------------------------
    # DETAIL DIALOG HELPER
    # --------------------------------------------------------

    def _open_report_dialog(self, title, headers, rows):
        dialog = MetricDetailDialog(
            title,
            headers,
            rows or [],
            self,
        )
        dialog.exec()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    def show_users_drilldown(self):
        try:
            success, rows = self.db.get_users()

            if not success:
                QMessageBox.warning(
                    self, "Database Error",
                    "Could not fetch user records.",
                )
                return

            self._open_report_dialog(
                "Registered User Records",
                [
                    "User ID", "Name", "Phone",
                    "Role", "Department", "Created On",
                ],
                rows,
            )

        except Exception as error:
            QMessageBox.critical(
                self, "User Records Error", str(error)
            )

    # --------------------------------------------------------
    # BOOKS
    # --------------------------------------------------------

    def show_titles_drilldown(self):
        self._show_books_dialog("Complete Book Catalog")

    def show_total_copies_drilldown(self):
        self._show_books_dialog("Complete Inventory Status")

    def _show_books_dialog(self, title):
        try:
            success, rows = self.db.get_books()

            if not success:
                QMessageBox.warning(
                    self, "Database Error",
                    "Could not fetch book records.",
                )
                return

            self._open_report_dialog(
                title,
                [
                    "Book ID", "Title", "Author", "Publisher",
                    "Total Copies", "Available", "Added On",
                ],
                rows,
            )

        except Exception as error:
            QMessageBox.critical(
                self, "Catalog Error", str(error)
            )

    # --------------------------------------------------------
    # ISSUED BOOKS
    # --------------------------------------------------------

    def show_active_loans_drilldown(self):
        self._show_date_report(
            "Issued Books",
            self.db.get_active_loans_report,
        )

    def show_issued_today_drilldown(self):
        today = datetime.date.today().strftime("%Y-%m-%d")

        self._show_date_report(
            "Books Issued Today",
            self.db.get_issued_today_report,
            today,
        )

    def show_overdue_drilldown(self):
        today = datetime.date.today().strftime("%Y-%m-%d")

        self._show_date_report(
            "Overdue Books / Action Required",
            self.db.get_overdue_books_report,
            today,
        )

    def show_due_today_drilldown(self):
        today = datetime.date.today().strftime("%Y-%m-%d")

        self._show_date_report(
            "Books Due Today",
            self.db.get_due_today_report,
            today,
        )

    def _show_date_report(self, title, method, *args):
        try:
            success, rows = method(*args)

            if success:
                self._open_report_dialog(
                    title,
                    [
                        "Book ID", "User ID",
                        "Issue Date", "Due Date",
                    ],
                    rows,
                )
            else:
                QMessageBox.warning(
                    self, "Report Error",
                    f"Could not fetch {title.lower()}.",
                )

        except Exception as error:
            QMessageBox.critical(
                self, "Report Error", str(error)
            )

    # --------------------------------------------------------
    # FINES
    # --------------------------------------------------------

    def show_fines_drilldown(self):
        try:
            success, rows = self.db.get_pending_fines_report()

            if success:
                self._open_report_dialog(
                    "Pending Fine Records",
                    [
                        "User ID", "Book ID",
                        "Fine Amount", "Return Date",
                    ],
                    rows,
                )
            else:
                QMessageBox.warning(
                    self, "Report Error",
                    "Could not fetch pending fines.",
                )

        except Exception as error:
            QMessageBox.critical(
                self, "Fine Report Error", str(error)
            )

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    def refresh_dashboard(self):
        self.update_dashboard_metrics()
        self.load_activity_log()

    # --------------------------------------------------------
    # QUICK ACTIONS
    # --------------------------------------------------------

    def open_userform(self):
        dialog = UserDialog(self.db, parent=self)
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        self.refresh_dashboard()

    def open_bookform(self):
        dialog = BookDialog(self.db, parent=self)
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        self.refresh_dashboard()

    def open_bargenerate_form(self):
        dialog = BarcodeGeneratorDialog(self.db, parent=self)
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        self.refresh_dashboard()

    def open_quick_scan(self):
        dialog = QuickScanDialog(self.db, parent=self)
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        self.refresh_dashboard()

    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------

    def closeEvent(self, event):
        disconnect_theme(self)
        super().closeEvent(event)

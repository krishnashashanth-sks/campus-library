
import csv
import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QBrush, QCursor, QFont, QKeyEvent, QPainter, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout,
    QHeaderView,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QScrollArea, QTableWidget, QTableWidgetItem,
    QToolTip, QVBoxLayout, QWidget,
)

from dialogs import (
    BarcodeGeneratorDialog,
    BookDialog,
    IssueBookDialog,
    QuickScanDialog,
    ReturnBookDialog,
    UserDialog,
)
from utils import rgba_color


PRIMARY = "#2563eb"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#6366f1"
STATUS_BADGE_COLORS = {
    "ISSUED": ("#1D4ED8", "#93C5FD"),
    "DUE TODAY": ("#B45309", "#FDE68A"),
    "OVERDUE": ("#991B1B", "#FCA5A5"),
    "RETURNED": ("#065F46", "#A7F3D0"),
}


# ============================================================
# THEME HELPERS
# ============================================================

def get_theme_colors():
    app = QApplication.instance()
    palette = app.palette() if app else QApplication.palette()
    manager = getattr(app, "theme_manager", None) if app else None
    active_theme = (
        manager.get_active_theme().lower()
        if manager
        else "dark"
    )
    theme = (
        manager.THEME.get(active_theme, {})
        if manager
        else {}
    )

    return {
        "window": theme.get(
            "window", palette.color(palette.ColorRole.Window).name()
        ),
        "surface": theme.get(
            "surface", palette.color(palette.ColorRole.Base).name()
        ),
        "surface_alt": theme.get(
            "surface_alt", palette.color(palette.ColorRole.AlternateBase).name()
        ),
        "text": theme.get(
            "text", palette.color(palette.ColorRole.Text).name()
        ),
        "muted": theme.get(
            "muted", palette.color(palette.ColorRole.PlaceholderText).name()
        ),
        "border": theme.get(
            "border", palette.color(palette.ColorRole.Mid).name()
        ),
        "primary": theme.get(
            "primary", palette.color(palette.ColorRole.Highlight).name()
        ),
        "primary_hover": theme.get("primary_hover", PRIMARY),
        "success": theme.get("success", SUCCESS),
        "warning": theme.get("warning", WARNING),
        "danger": theme.get("danger", DANGER),
        "table_row": theme.get("table_row", "#FFFFFF"),
        "table_alt": theme.get("table_alt", "#F1F5F9"),
        "overdue_tint": theme.get("overdue_tint", "#FEE2E2"),
        "amber_tint": theme.get("amber_tint", "#FEF3C7"),
        "chart_issued": theme.get("chart_issued", "#38BDF8"),
        "chart_returned": theme.get("chart_returned", "#34D399"),
        "inventory_issued": theme.get("inventory_issued", "#3B82F6"),
        "inventory_due": theme.get("inventory_due", "#F59E0B"),
        "inventory_overdue": theme.get("inventory_overdue", "#EF4444"),
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


class ExpressBookInput(QLineEdit):
    issueRequested = pyqtSignal()
    returnRequested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.returnRequested.emit()
            else:
                self.issueRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
        self.metric_key = ""
        self.overdue_active = False
        self.unpaid_fines_active = False
        self.overdue_glow = None
        self.overdue_glow_animation = None

        self.setObjectName("MetricCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(115)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 8)
        layout.setSpacing(3)

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
            self.progress_bar.setFixedHeight(6)
            layout.addWidget(self.progress_bar)

        self.secondary_container = QWidget()
        secondary_layout = QHBoxLayout(self.secondary_container)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        secondary_layout.setSpacing(5)
        self.issued_badge = QLabel()
        self.issued_badge.setObjectName("IssuedBadge")
        self.due_badge = QLabel()
        self.due_badge.setObjectName("DueBadge")
        secondary_layout.addWidget(self.issued_badge)
        secondary_layout.addWidget(self.due_badge)
        secondary_layout.addStretch()
        self.secondary_container.hide()
        layout.addWidget(self.secondary_container)

        footer = QHBoxLayout()
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricSubtitle")
        self.subtitle_label.setWordWrap(True)
        footer.addWidget(self.subtitle_label, 1)

        self.action_button = QPushButton()
        self.action_button.setObjectName("MetricAction")
        self.action_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.action_button.setFixedHeight(20)
        self.action_button.hide()
        footer.addWidget(self.action_button)
        layout.addLayout(footer)

        self.apply_style()

    def apply_style(self, *_):
        c = get_theme_colors()
        accent = {
            "inventory": c["success"],
            "active_loans": c["primary"],
            "overdue_books": c["danger"],
            "unpaid_fines": c["warning"],
        }.get(self.metric_key, self.accent_color)
        card_border = rgba_color(accent, 0.48)
        card_background = rgba_color(accent, 0.10)
        if self.metric_key == "overdue_books":
            accent = c["danger"]
            if self.overdue_active:
                card_border = c["danger"]
                card_background = rgba_color(c["danger"], 0.20)
        elif self.metric_key == "unpaid_fines" and self.unpaid_fines_active:
            accent = c["warning"]
            card_border = c["warning"]
            card_background = rgba_color(c["warning"], 0.20)

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: {card_background};
                border: 1px solid {card_border};
                border-left: 4px solid {accent};
                border-radius: 10px;
            }}
            QFrame#MetricCard:hover {{
                background: {c['surface_alt']};
                border: 1px solid {accent};
            }}
            QLabel#MetricTitle {{
                color: {c['muted']};
                font-size: 10px;
                font-weight: 700;
                border: none;
                background: transparent;
            }}
            QLabel#MetricIcon {{
                color: {accent};
                font-size: 16px;
                border: none;
                background: transparent;
            }}
            QLabel#MetricValue {{
                color: {c['text']};
                font-size: 23px;
                font-weight: 800;
                border: none;
                background: transparent;
            }}
            QLabel#MetricSubtitle {{
                color: {c['muted']};
                font-size: 10px;
                border: none;
                background: transparent;
            }}
            QLabel#MetricSecondary {{
                color: {c['text']};
                font-size: 10px;
                font-weight: 600;
                background: {c['surface_alt']};
                border: none;
                border-radius: 5px;
                padding: 2px 6px;
            }}
            QLabel#IssuedBadge {{
                color: {c['primary']};
                font-size: 10px;
                font-weight: 700;
                background: {c['surface_alt']};
                border: 1px solid {c['border']};
                border-radius: 7px;
                padding: 2px 6px;
            }}
            QLabel#DueBadge {{
                color: {c['warning']};
                font-size: 10px;
                font-weight: 700;
                background: {c['surface_alt']};
                border: 1px solid {c['border']};
                border-radius: 7px;
                padding: 2px 6px;
            }}
            QPushButton#MetricAction {{
                background: transparent;
                color: {c['primary']};
                border: none;
                padding: 1px 2px;
                font-size: 10px;
                font-weight: 700;
            }}
            QPushButton#MetricAction:hover {{
                color: {c['primary_hover']};
                text-decoration: underline;
            }}
            QProgressBar#InventoryProgress {{
                background: {c['surface_alt']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#InventoryProgress::chunk {{
                background: {c['success']};
                border-radius: 3px;
            }}
        """)
        if self.overdue_glow:
            self.overdue_glow.setColor(QColor(c["danger"]))

    def set_metric(self, value, subtitle=None):
        self.value_label.setText(str(value))

        if subtitle is not None:
            self.subtitle_label.setText(str(subtitle))

    def set_overdue(self, count):
        self.overdue_active = int(count or 0) > 0
        self.value_label.setText(str(count))
        self.apply_style()
        if self.overdue_active:
            self._start_overdue_glow()
        else:
            self._stop_overdue_glow()

    def set_fines(self, amount):
        value = float(amount or 0)
        self.unpaid_fines_active = value > 0
        self.value_label.setText(f"₹{value:,.2f}")
        self.apply_style()

    def _start_overdue_glow(self):
        if self.overdue_glow is None:
            self.overdue_glow = QGraphicsDropShadowEffect(self)
            self.overdue_glow.setOffset(0, 0)
            self.overdue_glow.setColor(
                QColor(get_theme_colors()["danger"])
            )
            self.setGraphicsEffect(self.overdue_glow)

        if self.overdue_glow_animation is None:
            animation = QPropertyAnimation(
                self.overdue_glow, b"blurRadius", self
            )
            animation.setStartValue(3.0)
            animation.setEndValue(12.0)
            animation.setDuration(1100)
            animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            animation.setLoopCount(-1)
            animation.setKeyValueAt(0.5, 6.0)
            self.overdue_glow_animation = animation

        if (
            self.overdue_glow_animation.state()
            != QPropertyAnimation.State.Running
        ):
            self.overdue_glow_animation.start()

    def _stop_overdue_glow(self):
        if self.overdue_glow_animation:
            self.overdue_glow_animation.stop()
        if self.overdue_glow:
            self.overdue_glow.setBlurRadius(0)

    def set_secondary(self, issued, due=None):
        if due is None:
            self.issued_badge.setText(str(issued))
            self.due_badge.hide()
        else:
            self.issued_badge.setText(f"Issued Today: {issued}")
            self.due_badge.setText(f"Due Today: {due}")
            self.due_badge.show()
        self.secondary_container.show()

    def set_inventory(
        self,
        available_copies,
        total_copies,
        unique_titles=None,
    ):
        if not self.progress_bar:
            return

        total = max(int(total_copies or 0), 0)
        available = max(min(int(available_copies or 0), total), 0)

        percentage = int(available / total * 100) if total else 0

        if available == 0:
            self.accent_color = get_theme_colors()["danger"]
            status = "Empty inventory"
        elif percentage <= 25:
            self.accent_color = get_theme_colors()["warning"]
            status = f"Low stock · {percentage}% available"
        else:
            self.accent_color = get_theme_colors()["success"]
            status = f"Healthy stock · {percentage}% available"

        self.value_label.setText(f"{available:,} / {total:,}")
        self.subtitle_label.setText(
            f"{int(unique_titles):,} Unique Titles ({percentage}% in stock)"
            if unique_titles is not None
            else status
        )
        self.setToolTip(status)
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(available)

        self.apply_style()

    def set_action(self, text, callback):
        self.action_button.setText(text)
        self.action_button.clicked.connect(callback)
        self.action_button.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ============================================================
# CIRCULATION ANALYTICS PANEL
# ============================================================

class CirculationAnalyticsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.setMouseTracking(True)
        self.days = []
        self.inventory = []

    def set_data(self, days, inventory):
        self.days = list(days)
        self.inventory = list(inventory)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        colors = get_theme_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Segoe UI", 9))

        width = self.width()
        height = self.height()
        split_x = int(width * 0.61)
        muted = QColor(colors["muted"])
        text = QColor(colors["text"])
        border = QColor(colors["border"])

        painter.setPen(text)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(14, 23, "7-Day Circulation")
        painter.drawText(split_x + 14, 23, "Inventory Status")

        painter.setPen(QPen(border, 1))
        painter.drawLine(split_x, 12, split_x, height - 12)

        chart_left = 28
        chart_right = split_x - 14
        chart_top = 54
        chart_bottom = height - 34
        chart_height = max(chart_bottom - chart_top, 1)
        values = [
            max(int(day.get("issued", 0)), int(day.get("returned", 0)))
            for day in self.days
        ]
        max_value = max(values, default=0) or 1

        painter.setPen(QPen(border, 1))
        painter.drawLine(chart_left, chart_bottom, chart_right, chart_bottom)
        group_width = (chart_right - chart_left) / max(len(self.days), 1)
        bar_width = max(min(int(group_width * 0.24), 13), 4)
        issued_color = QColor(colors["chart_issued"])
        returned_color = QColor(colors["chart_returned"])

        for index, day in enumerate(self.days):
            center = chart_left + group_width * (index + 0.5)
            for offset, key, color in (
                (-bar_width * 0.65, "issued", issued_color),
                (bar_width * 0.65, "returned", returned_color),
            ):
                value = int(day.get(key, 0))
                bar_height = chart_height * value / max_value
                x = int(center + offset - bar_width / 2)
                y = int(chart_bottom - bar_height)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(
                    x, y, bar_width, max(int(bar_height), 2), 3, 3
                )
                if value:
                    painter.setPen(muted)
                    painter.drawText(
                        x - 2, max(y - 3, chart_top - 4), str(value)
                    )

            painter.setPen(muted)
            painter.drawText(
                int(center - 14), height - 12, str(day.get("label", ""))
            )

        legend_y = 40
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(issued_color)
        painter.drawRoundedRect(108, legend_y - 8, 8, 8, 2, 2)
        painter.setPen(muted)
        painter.drawText(120, legend_y, "Issued")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(returned_color)
        painter.drawRoundedRect(165, legend_y - 8, 8, 8, 2, 2)
        painter.setPen(muted)
        painter.drawText(177, legend_y, "Returned")

        status_colors = {
            "Available on Shelf": QColor(colors["success"]),
            "Currently Issued": QColor(colors["inventory_issued"]),
            "Due Today / Reserved": QColor(colors["inventory_due"]),
            "Overdue / Missing": QColor(colors["inventory_overdue"]),
        }
        status_x = split_x + 14
        status_width = max(width - status_x - 14, 1)
        bar_x = status_x
        bar_y = 55
        bar_width_total = status_width
        total = sum(max(int(item.get("count", 0)), 0) for item in self.inventory)
        if total <= 0:
            painter.setPen(muted)
            painter.drawText(status_x, bar_y + 15, "No inventory records")
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            for item in self.inventory:
                count = max(int(item.get("count", 0)), 0)
                segment_width = int(bar_width_total * count / total)
                painter.setBrush(status_colors[item["label"]])
                painter.drawRect(bar_x, bar_y, segment_width, 10)
                bar_x += segment_width

            row_top = bar_y + 22
            for item in self.inventory:
                count = max(int(item.get("count", 0)), 0)
                percent = count / total * 100
                color = status_colors[item["label"]]
                label_y = row_top + 9
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(status_x, label_y - 7, 7, 7, 2, 2)
                painter.setPen(text)
                painter.drawText(
                    status_x + 13, label_y,
                    f"{item['label']}  {count:,}",
                )
                percentage_text = f"{percent:.0f}%"
                percentage_width = painter.fontMetrics().horizontalAdvance(
                    percentage_text
                )
                painter.drawText(
                    width - 14 - percentage_width,
                    label_y,
                    percentage_text,
                )

                track_y = row_top + 13
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(border)
                painter.drawRoundedRect(
                    status_x, track_y, status_width, 5, 2, 2
                )
                progress_width = int(status_width * count / total)
                if progress_width:
                    painter.setBrush(color)
                    painter.drawRoundedRect(
                        status_x, track_y, progress_width, 5, 2, 2
                    )
                row_top += 32

        painter.end()

    def mouseMoveEvent(self, event):
        if self.days:
            split_x = int(self.width() * 0.61)
            chart_left = 28
            chart_right = split_x - 14
            if chart_left <= event.position().x() <= chart_right:
                group_width = (chart_right - chart_left) / len(self.days)
                index = int((event.position().x() - chart_left) / group_width)
                if 0 <= index < len(self.days):
                    day = self.days[index]
                    QToolTip.showText(
                        QCursor.pos(),
                        (
                            f"{day['label']}: "
                            f"{day['issued']} issued · "
                            f"{day['returned']} returned"
                        ),
                        self,
                    )
        super().mouseMoveEvent(event)


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
            padding: 7px 9px;
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
            padding: 10px 10px;
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
        searchable: bool = True,
    ):
        super().__init__(parent)

        self.headers = headers
        self.rows = rows or []

        self.setWindowTitle(title)
        self.resize(1050, 620)
        self.setMinimumSize(760, 450)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(20, 18, 20, 18)
        self.layout_main.setSpacing(16)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        self.layout_main.addWidget(self.title_label)

        self.search_input = None
        if searchable:
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
        self.table.verticalHeader().setDefaultSectionSize(44)

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

        query = (
            self.search_input.text().strip()
            if self.search_input else ""
        )
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
                padding: 7px 9px;
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
                padding: 10px 10px;
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
        details=None,
        dialog_title="Activity Details",
    ):
        super().__init__(parent)

        self.action_type = safe_text(action_type)
        self.book_title = safe_text(book_title)
        self.username = safe_text(username)
        self.timestamp = safe_text(timestamp)

        self.detail_items = details or [
            ("BOOK / ITEM", self.book_title),
            ("USER", self.username),
            ("ACTIVITY TYPE", self.action_type),
            ("TIMESTAMP", self.timestamp),
        ]
        self.setWindowTitle(dialog_title)
        self.resize(590, 480)
        self.setMinimumSize(480, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(13)

        heading = (
            dialog_title
            if details is not None
            else f"{activity_icon(self.action_type)}  {self.action_type}"
        )
        title = QLabel(heading)
        title.setStyleSheet(
            "font-size: 20px; font-weight: 750;"
        )
        layout.addWidget(title)

        if details is not None:
            detail_form = QFormLayout()
            detail_form.setContentsMargins(2, 4, 2, 4)
            detail_form.setVerticalSpacing(7)
            for label, value in self.detail_items:
                key_label = QLabel(label)
                key_label.setStyleSheet(
                    "font-size: 10px; font-weight: 700;"
                )
                value_label = QLabel(safe_text(value) or "Not available")
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                value_label.setStyleSheet(
                    "font-size: 12px; font-weight: 600;"
                )
                detail_form.addRow(key_label, value_label)
            layout.addLayout(detail_form, 1)
        else:
            for label, value in self.detail_items:
                self.add_detail(layout, label, safe_text(value))

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
        text = "\n".join(
            f"{label}: {safe_text(value)}"
            for label, value in self.detail_items
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
        self.main_layout.setContentsMargins(20, 18, 20, 18)
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
        self.table.verticalHeader().setDefaultSectionSize(44)

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
        self._activity_records = []
        self._activity_filter = "All Recent"
        self.activity_filter_buttons = {}
        self._users_by_id = {}
        self._books_by_id = {}
        self._current_books_by_user = {}

        self.setObjectName("DashboardView")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setObjectName("DashboardScroll")
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.dashboard_content = QWidget()
        self.dashboard_content.setObjectName("DashboardContent")
        self.dashboard_scroll.setWidget(self.dashboard_content)
        outer_layout.addWidget(self.dashboard_scroll)

        self.main_layout = QVBoxLayout(self.dashboard_content)
        self.main_layout.setContentsMargins(20, 16, 20, 16)
        self.main_layout.setSpacing(12)

        page_header = QVBoxLayout()
        page_header.setSpacing(3)

        page_title = QLabel("Dashboard")
        page_title.setObjectName("PageTitle")
        page_header.addWidget(page_title)

        page_subtitle = QLabel(
            "At a glance: inventory, circulation, and recent activity."
        )
        page_subtitle.setObjectName("PageSubtitle")
        page_subtitle.setWordWrap(True)
        page_header.addWidget(page_subtitle)
        self.main_layout.addLayout(page_header)

        self.tiles_grid = QGridLayout()
        self.tiles_grid.setHorizontalSpacing(12)
        self.tiles_grid.setVerticalSpacing(12)

        for column in range(4):
            self.tiles_grid.setColumnStretch(column, 1)
        self.tiles_grid.setRowMinimumHeight(0, 115)
        self.tiles_grid.setRowStretch(0, 0)

        self.main_layout.addLayout(self.tiles_grid)
        self._create_metric_cards()

        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(12)
        middle_layout.addWidget(self._create_analytics_panel(), 13)
        middle_layout.addWidget(
            self._create_express_circulation_panel(), 7
        )
        self.main_layout.addLayout(middle_layout)

        lower_layout = QHBoxLayout()
        lower_layout.setSpacing(12)
        lower_layout.addWidget(self._create_activity_table_panel(), 4)
        lower_layout.addWidget(self.create_quick_actions(), 1)

        self.main_layout.addLayout(lower_layout, 1)
        self.main_layout.setStretch(0, 0)
        self.main_layout.setStretch(1, 0)
        self.main_layout.setStretch(2, 0)
        self.main_layout.setStretch(3, 1)

        self.theme_manager = connect_theme(self)
        self.apply_theme()
        self.refresh_dashboard()

    def _create_analytics_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setFixedHeight(230)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 9, 12, 8)
        layout.setSpacing(3)

        self.analytics_widget = CirculationAnalyticsWidget()
        layout.addWidget(self.analytics_widget, 1)
        return panel

    def _create_express_circulation_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setFixedHeight(230)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(13, 11, 13, 10)
        layout.setSpacing(6)

        title = QLabel("Express Circulation")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.express_user_input = QLineEdit()
        self.express_user_input.setObjectName("ExpressInput")
        self.express_user_input.setPlaceholderText(
            "Student / Member ID or Roll No"
        )
        self.express_user_input.setClearButtonEnabled(True)
        self.express_user_input.textChanged.connect(
            self._update_express_previews
        )
        layout.addWidget(self.express_user_input)

        self.express_user_preview = QLabel(
            "Enter a registered member ID to preview eligibility."
        )
        self.express_user_preview.setObjectName("ExpressPreview")
        self.express_user_preview.setWordWrap(True)
        layout.addWidget(self.express_user_preview)

        self.express_book_input = ExpressBookInput()
        self.express_book_input.setObjectName("ExpressInput")
        self.express_book_input.setPlaceholderText("Book ID / Barcode")
        self.express_book_input.setClearButtonEnabled(True)
        self.express_book_input.textChanged.connect(
            self._update_express_previews
        )
        self.express_book_input.issueRequested.connect(
            self.instant_issue_book
        )
        self.express_book_input.returnRequested.connect(
            self.instant_return_book
        )
        layout.addWidget(self.express_book_input)

        self.express_book_preview = QLabel(
            "Enter a book ID to check title and availability."
        )
        self.express_book_preview.setObjectName("ExpressPreview")
        self.express_book_preview.setWordWrap(True)
        layout.addWidget(self.express_book_preview)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.instant_issue_button = QPushButton("⚡ Instant Issue (Enter)")
        self.instant_issue_button.setObjectName("InstantIssue")
        self.instant_issue_button.clicked.connect(self.instant_issue_book)
        actions.addWidget(self.instant_issue_button)

        self.instant_return_button = QPushButton(
            "↩ Instant Return (Shift+Enter)"
        )
        self.instant_return_button.setObjectName("InstantReturn")
        self.instant_return_button.clicked.connect(self.instant_return_book)
        actions.addWidget(self.instant_return_button)
        layout.addLayout(actions)

        self.express_status_label = QLabel("")
        self.express_status_label.setObjectName("ExpressStatus")
        self.express_status_label.setWordWrap(True)
        layout.addWidget(self.express_status_label)
        return panel

    def _create_activity_table_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        header = QHBoxLayout()
        title = QLabel("Recent Circulation & Alerts")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch()

        self.view_all_button = QPushButton("View All")
        self.view_all_button.setObjectName("ViewAllButton")
        self.view_all_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.view_all_button.clicked.connect(self.open_activity_history)
        header.addWidget(self.view_all_button)
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(4)
        filter_group = QButtonGroup(self)
        filter_group.setExclusive(True)
        for label in (
            "All Recent", "Issued Today", "Due Today", "Overdue Alerts"
        ):
            button = QPushButton(label)
            button.setObjectName("ActivityFilter")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(label == self._activity_filter)
            button.clicked.connect(
                lambda _checked=False, value=label:
                self.set_activity_filter(value)
            )
            filter_group.addButton(button)
            self.activity_filter_buttons[label] = button
            filters.addWidget(button)
        filters.addStretch()

        self.activity_summary_label = QLabel("Latest transactions")
        self.activity_summary_label.setObjectName("ActivitySummary")
        filters.addWidget(self.activity_summary_label)
        layout.addLayout(filters)

        self.activity_table = QTableWidget()
        self.activity_table.setObjectName("ActivityTable")
        self.activity_table.setColumnCount(7)
        self.activity_table.setHorizontalHeaderLabels([
            "Time / Date", "Book ID", "Book Title", "Member / User",
            "Status", "Due Date", "Quick Action",
        ])
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.setShowGrid(False)
        self.activity_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.activity_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.activity_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.verticalHeader().setDefaultSectionSize(44)
        self.activity_table.setMouseTracking(True)

        table_header = self.activity_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for column, width in (
            (0, 130), (1, 80), (3, 160), (4, 90), (5, 130), (6, 200)
        ):
            self.activity_table.setColumnWidth(column, width)

        self.activity_table.setFixedHeight(208)
        layout.addWidget(self.activity_table)
        self.activity_empty_hint = QLabel(
            "Showing all recent records — Press Ctrl+I to issue a book "
            "or scan a barcode at the Express Desk."
        )
        self.activity_empty_hint.setObjectName("ActivityEmptyHint")
        self.activity_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.activity_empty_hint.setWordWrap(True)
        layout.addWidget(self.activity_empty_hint)
        return panel

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

            QScrollArea#DashboardScroll,
            QWidget#DashboardContent {{
                background: {c['window']};
                border: none;
            }}

            QLineEdit#ExpressInput {{
                background: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 7px;
                padding: 6px 9px;
                font-size: 11px;
            }}

            QLineEdit#ExpressInput:focus {{
                border-color: {c['primary']};
            }}

            QLabel#ExpressPreview, QLabel#ExpressStatus {{
                color: {c['muted']};
                font-size: 10px;
                background: transparent;
            }}

            QLabel#ExpressStatus[success="true"] {{
                color: {c['success']};
            }}

            QLabel#ExpressStatus[success="false"] {{
                color: {c['danger']};
            }}

            QPushButton#InstantIssue,
            QPushButton#InstantReturn {{
                color: white;
                border: none;
                border-radius: 7px;
                padding: 7px 8px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#InstantIssue {{
                background: {c['primary']};
            }}

            QPushButton#InstantIssue:hover {{
                background: {c.get('primary_hover', c['primary'])};
            }}

            QPushButton#InstantReturn {{
                background: {c.get('success', SUCCESS)};
            }}

            QPushButton#InstantReturn:hover {{
                background: #059669;
            }}

            QFrame#DashboardPanel {{
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}

            QLabel#PanelTitle {{
                color: {c['text']};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#ActivitySummary {{
                color: {c['muted']};
                font-size: 10px;
                background: transparent;
                border: none;
            }}

            QPushButton#ActivityFilter {{
                background: transparent;
                color: {c['muted']};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 10px;
                font-weight: 600;
            }}

            QPushButton#ActivityFilter:hover {{
                background: {c['surface_alt']};
                color: {c['text']};
            }}

            QPushButton#ActivityFilter:checked {{
                background: {c['primary']};
                color: white;
                border-color: {c['primary']};
            }}

            QTableWidget#ActivityTable {{
                background: {c['table_row']};
                alternate-background-color: {c['table_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 10px;
                selection-background-color: {c['primary']};
                selection-color: {c['selection_text']};
                outline: none;
                font-size: 11px;
            }}

            QTableWidget#ActivityTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid {c['border']};
            }}

            QTableWidget#ActivityTable::item:hover {{
                background: {c['surface_alt']};
            }}

            QLabel#StatusBadge {{
                border-radius: 8px;
                padding: 3px 7px;
                font-size: 10px;
                font-weight: 700;
            }}

            QHeaderView::section {{
                background: {c['surface_alt']};
                color: {c['muted']};
                border: none;
                border-bottom: 1px solid {c['border']};
                padding: 10px 10px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#QuickActionRow {{
                background: {c['surface_alt']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                text-align: left;
            }}

            QPushButton#QuickActionRow:hover {{
                border-color: {c['primary']};
                background: {c['surface']};
            }}

            QLabel#QuickActionIcon {{
                color: {c['primary']};
                background: transparent;
                font-size: 13px;
            }}

            QLabel#QuickActionText {{
                color: {c['text']};
                background: transparent;
                font-size: 10px;
                font-weight: 600;
            }}

            QLabel#QuickActionKeycap {{
                color: {c['muted']};
                background: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 5px;
                padding: 3px 5px;
                font-size: 8px;
                font-weight: 700;
            }}

            QLabel#ActivityEmptyHint {{
                color: {c['muted']};
                font-size: 10px;
                padding: 3px;
                background: transparent;
            }}

            QPushButton#RowAction {{
                background: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 5px;
                padding: 4px 6px;
                font-size: 9px;
                font-weight: 600;
            }}

            QPushButton#RowAction:hover {{
                border-color: {c['primary']};
                background: {c['surface']};
            }}

            QPushButton#RowAction:disabled {{
                color: {c['muted']};
                background: {c['surface_alt']};
                border-color: {c['border']};
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
        self.analytics_widget.update()

    # --------------------------------------------------------
    # METRIC CARDS
    # --------------------------------------------------------

    def _create_metric_cards(self):
        metrics = [
            (
                "inventory", "Total Inventory", "0 / 0",
                "Available copies", "📚",
                SUCCESS, 0, 0, self.show_total_copies_drilldown, True,
            ),
            (
                "active_loans", "Active Circulation", "0",
                "Currently issued", "↗",
                INFO, 0, 1, self.show_active_loans_drilldown, False,
            ),
            (
                "overdue_books", "Overdue Books", "0",
                "Action required", "⚠",
                DANGER, 0, 2, self.show_overdue_drilldown, False,
            ),
            (
                "unpaid_fines", "Unpaid Fines", "₹0.00",
                "Pending collection", "₹",
                WARNING, 0, 3, self.show_fines_drilldown, False,
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

        self.metric_widgets["inventory"].set_action(
            "Catalog →", lambda: self.navigate_requested.emit("catalog")
        )
        self.metric_widgets["active_loans"].set_action(
            "Circulation →",
            lambda: self.navigate_requested.emit("circulation"),
        )
        self.metric_widgets["overdue_books"].set_action(
            "Overdue List →",
            lambda: self.navigate_requested.emit("circulation"),
        )
        self.metric_widgets["unpaid_fines"].set_action(
            "View Fines →", self.show_fines_drilldown
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

        card.metric_key = key
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
        card.setMinimumWidth(220)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("Quick Desk Actions")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        actions = [
            ("📚", "Add New Book", "Ctrl+B", self.open_bookform),
            ("👤", "Add New User", "Ctrl+U", self.open_userform),
            ("▦", "Generate Barcode", "Ctrl+G", self.open_bargenerate_form),
            ("⌁", "Quick Scan", "Ctrl+Shift+K", self.open_quick_scan),
            ("◷", "Activity History", "Ctrl+H", self.open_activity_history),
            ("↻", "Refresh Dashboard", "F5", self.refresh_dashboard),
        ]

        for icon, label, shortcut, callback in actions:
            button = QPushButton()
            button.setObjectName("QuickActionRow")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(label)
            button.clicked.connect(callback)
            row_layout = QHBoxLayout(button)
            row_layout.setContentsMargins(9, 5, 8, 5)
            row_layout.setSpacing(7)
            icon_label = QLabel(icon)
            icon_label.setObjectName("QuickActionIcon")
            icon_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            row_layout.addWidget(icon_label)
            text_label = QLabel(label)
            text_label.setObjectName("QuickActionText")
            text_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            row_layout.addWidget(text_label, 1)
            keycap = QLabel(shortcut)
            keycap.setObjectName("QuickActionKeycap")
            keycap.setVisible(bool(shortcut))
            keycap.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            row_layout.addWidget(keycap)
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
            self,
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
        try:
            success, logs = self.db.get_logs()
            if not success:
                raise RuntimeError("Could not retrieve circulation records.")

            books_success, books = self.db.get_books()
            users_success, users = self.db.get_users()
            if not books_success or not users_success:
                raise RuntimeError(
                    "Could not load book and user details for activity."
                )

            book_titles = {
                str(book[0]): safe_text(book[1])
                for book in books
                if len(book) > 1
            }
            user_names = {
                str(user[0]): safe_text(user[1])
                for user in users
                if len(user) > 1
            }
            self._books_by_id = {
                str(book[0]).strip().casefold(): book
                for book in books if len(book) > 1
            }
            self._users_by_id = {
                str(user[0]).strip().casefold(): user
                for user in users if len(user) > 1
            }
            self._current_books_by_user = {}
            for record in logs or []:
                if (
                    len(record) >= 8
                    and safe_text(record[7]).upper() == "ISSUED"
                ):
                    user_key = safe_text(record[2]).strip().casefold()
                    self._current_books_by_user[user_key] = (
                        self._current_books_by_user.get(user_key, 0) + 1
                    )

            self._activity_records = []
            today = datetime.date.today().isoformat()
            for record in list(logs or [])[:300]:
                if len(record) < 8:
                    continue
                log_id, book_id, user_id, issue_date, due_date, returned, fine, raw_status = record
                status = safe_text(raw_status).upper()
                due_text = safe_text(due_date)
                if (
                    status == "ISSUED"
                    and due_text
                    and due_text[:10] < today
                ):
                    status = "OVERDUE"
                elif (
                    status == "ISSUED"
                    and due_text
                    and due_text[:10] == today
                ):
                    status = "DUE TODAY"

                self._activity_records.append({
                    "record": record,
                    "log_id": log_id,
                    "book_id": safe_text(book_id),
                    "book_title": book_titles.get(
                        str(book_id), "Unknown book"
                    ),
                    "user_id": safe_text(user_id),
                    "user_name": user_names.get(
                        str(user_id), "Unknown user"
                    ),
                    "display_date": safe_text(returned or issue_date),
                    "issue_date": safe_text(issue_date),
                    "due_date": due_text,
                    "status": status,
                    "fine": fine,
                })

            self._update_analytics(logs, books)
            self._update_express_previews()
            self._render_activity_table()
        except Exception as error:
            self._activity_records = []
            self.activity_table.setRowCount(0)
            self.activity_summary_label.setText(
                f"Could not load activity: {error}"
            )

    def set_activity_filter(self, filter_name):
        self._activity_filter = filter_name
        self._render_activity_table()

    def _render_activity_table(self):
        today = datetime.date.today().isoformat()
        if self._activity_filter == "Issued Today":
            records = [
                item for item in self._activity_records
                if item["issue_date"][:10] == today
            ]
        elif self._activity_filter == "Due Today":
            records = [
                item for item in self._activity_records
                if item["status"] in ("ISSUED", "DUE TODAY", "OVERDUE")
                and item["due_date"][:10] == today
            ]
        elif self._activity_filter == "Overdue Alerts":
            records = [
                item for item in self._activity_records
                if item["status"] == "OVERDUE"
            ]
        else:
            records = self._activity_records

        self.activity_table.setRowCount(len(records))
        self.activity_empty_hint.setVisible(len(records) < 4)
        for row_index, item in enumerate(records):
            values = (
                item["display_date"],
                item["book_id"],
                item["book_title"],
                f"{item['user_name']} ({item['user_id']})",
                item["due_date"] or "—",
            )
            for column, value in enumerate(values):
                actual_column = column if column < 4 else column + 1
                table_item = QTableWidgetItem(safe_text(value) or "—")
                table_item.setToolTip(safe_text(value) or "—")
                if actual_column == 0:
                    table_item.setData(
                        Qt.ItemDataRole.UserRole,
                        item["record"],
                    )
                self.activity_table.setItem(
                    row_index, actual_column, table_item
                )

            badge_background, status_color = STATUS_BADGE_COLORS.get(
                item["status"],
                STATUS_BADGE_COLORS["ISSUED"],
            )
            badge = QLabel(item["status"].title())
            badge.setObjectName("StatusBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"color: {status_color}; background: {badge_background};"
            )
            self.activity_table.setCellWidget(row_index, 4, badge)

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            return_button = QPushButton("Return")
            return_button.setObjectName("RowAction")
            return_button.setEnabled(
                item["status"] in ("ISSUED", "DUE TODAY", "OVERDUE")
            )
            return_button.clicked.connect(
                lambda _checked=False, selected=item:
                self.return_activity_record(selected)
            )
            actions_layout.addWidget(return_button)

            renew_button = QPushButton("Renew")
            renew_button.setObjectName("RowAction")
            renew_button.setEnabled(False)
            renew_button.setToolTip(
                "Renewals are not supported by the current circulation service."
            )
            actions_layout.addWidget(renew_button)

            inspect_button = QPushButton("Inspect")
            inspect_button.setObjectName("RowAction")
            inspect_button.clicked.connect(
                lambda _checked=False, selected=item:
                self.inspect_activity_record(selected)
            )
            actions_layout.addWidget(inspect_button)
            self.activity_table.setCellWidget(
                row_index, 6, actions
            )

        self.activity_summary_label.setText(
            f"{len(records)} transaction(s)"
        )

    def _update_analytics(self, logs, books):
        today = datetime.date.today()
        days = []
        issue_counts = {}
        return_counts = {}
        for offset in range(6, -1, -1):
            date = today - datetime.timedelta(days=offset)
            key = date.isoformat()
            issue_counts[key] = 0
            return_counts[key] = 0

        active = []
        for record in logs or []:
            if len(record) < 8:
                continue
            _, _, _, checkout_date, due_date, returned_date, _, status = record
            checkout_day = safe_text(checkout_date)[:10]
            returned_day = safe_text(returned_date)[:10]
            if checkout_day in issue_counts:
                issue_counts[checkout_day] += 1
            if returned_day in return_counts:
                return_counts[returned_day] += 1
            if safe_text(status).upper() == "ISSUED":
                active.append((safe_text(due_date)[:10], due_date))

        for key in issue_counts:
            date = datetime.date.fromisoformat(key)
            days.append({
                "label": date.strftime("%a"),
                "issued": issue_counts[key],
                "returned": return_counts[key],
            })

        total_copies = sum(
            max(int(book[4] or 0), 0) for book in books if len(book) > 5
        )
        available_copies = sum(
            max(int(book[5] or 0), 0) for book in books if len(book) > 5
        )
        due_count = sum(1 for due_day, _ in active if due_day == today.isoformat())
        overdue_count = sum(1 for due_day, _ in active if due_day and due_day < today.isoformat())
        issued_regular = max(
            len(active) - due_count - overdue_count, 0
        )
        self.analytics_widget.set_data(
            days,
            [
                {"label": "Available on Shelf", "count": available_copies},
                {"label": "Currently Issued", "count": issued_regular},
                {"label": "Due Today / Reserved", "count": due_count},
                {"label": "Overdue / Missing", "count": overdue_count},
            ],
        )

    def _update_express_previews(self, *_):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user_key = user_id.casefold()
        book_key = book_id.casefold()
        user = self._users_by_id.get(user_key)
        book = self._books_by_id.get(book_key)

        if user:
            held = self._current_books_by_user.get(user_key, 0)
            self.express_user_preview.setText(
                f"{safe_text(user[1])} · {held} book(s) currently held"
            )
        elif user_id:
            self.express_user_preview.setText(
                "Member ID not found in the library records."
            )
        else:
            self.express_user_preview.setText(
                "Enter a registered member ID to preview eligibility."
            )

        if book:
            available = int(book[5] or 0)
            self.express_book_preview.setText(
                f"{safe_text(book[1])} · "
                f"{'Available' if available > 0 else 'No copies available'}"
            )
        elif book_id:
            self.express_book_preview.setText(
                "Book ID not found in the catalog."
            )
        else:
            self.express_book_preview.setText(
                "Enter a book ID to check title and availability."
            )

        can_transact = bool(user and book)
        self.instant_issue_button.setEnabled(
            can_transact and int(book[5] or 0) > 0
        )
        self.instant_return_button.setEnabled(can_transact)

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
                _total_users,
                unique_titles,
                total_copies,
                available_copies,
                active_loans,
                today_issued,
                overdue_books,
                due_today,
                unpaid_fines,
            ) = details

            self.metric_widgets["inventory"].set_inventory(
                available_copies,
                total_copies,
                unique_titles,
            )

            self.metric_widgets["active_loans"].set_metric(
                str(active_loans),
                "Currently issued",
            )
            self.metric_widgets["active_loans"].set_secondary(
                today_issued,
                due_today,
            )

            overdue_card = self.metric_widgets["overdue_books"]
            overdue_card.set_overdue(overdue_books)

            self.metric_widgets["unpaid_fines"].set_fines(
                unpaid_fines
            )

        except Exception as error:
            self.activity_summary_label.setText(
                f"Could not load dashboard metrics: {error}"
            )

    # --------------------------------------------------------
    # DETAIL DIALOG HELPER
    # --------------------------------------------------------

    def _open_report_dialog(
        self, title, headers, rows, searchable=True
    ):
        dialog = MetricDetailDialog(
            title,
            headers,
            rows or [],
            self,
            searchable=searchable,
        )
        dialog.exec()

    def open_issue_dialog(self):
        dialog = IssueBookDialog(self.db, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            book_id, user_id, days = dialog.get_data()
            success, message = self.db.issue_book(
                book_id,
                user_id,
                days,
            )
            if success:
                QMessageBox.information(
                    self, "Book Issued", str(message)
                )
                self.refresh_dashboard()
            else:
                QMessageBox.warning(
                    self, "Issue Failed", str(message)
                )
        except Exception as error:
            QMessageBox.critical(
                self, "Issue Error", str(error)
            )

    def open_return_dialog(self):
        dialog = ReturnBookDialog(self.db, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            book_id, user_id = dialog.get_data()
            success, fine, message = self.db.return_book(
                book_id,
                user_id,
            )
            if success:
                QMessageBox.information(
                    self,
                    "Book Returned",
                    f"{message}\nFine: ₹{float(fine or 0):.2f}",
                )
                self.refresh_dashboard()
            else:
                QMessageBox.warning(
                    self, "Return Failed", str(message)
                )
        except Exception as error:
            QMessageBox.critical(
                self, "Return Error", str(error)
            )

    def quick_scan_barcode(self, input_field=None):
        input_field = input_field or self.express_book_input
        book_id = input_field.text().strip()
        if not book_id:
            return

        dialog = QuickScanDialog(self.db, self)
        dialog.set_camera_scanned_book_id(
            book_id,
            "barcode / Book ID entry",
        )
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        input_field.clear()
        self.refresh_dashboard()

    def instant_issue_book(self):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user = self._users_by_id.get(user_id.casefold())
        book = self._books_by_id.get(book_id.casefold())
        if not user_id or not book_id or not user or not book:
            self.express_status_label.setText(
                "Enter a registered member ID and a registered book ID."
            )
            return

        try:
            success, message = self.db.issue_book(
                safe_text(book[0]),
                safe_text(user[0]),
            )
            self.express_status_label.setText(str(message))
            self.express_status_label.setProperty(
                "success", bool(success)
            )
            self.express_status_label.style().unpolish(
                self.express_status_label
            )
            self.express_status_label.style().polish(
                self.express_status_label
            )
            self.refresh_dashboard()
            if success:
                self.express_book_input.clear()
        except Exception as error:
            self.express_status_label.setText(
                f"Issue failed: {error}"
            )

    def instant_return_book(self):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user = self._users_by_id.get(user_id.casefold())
        book = self._books_by_id.get(book_id.casefold())
        if not user_id or not book_id or not user or not book:
            self.express_status_label.setText(
                "Enter a registered member ID and a registered book ID."
            )
            return

        try:
            success, fine, message = self.db.return_book(
                safe_text(book[0]),
                safe_text(user[0]),
            )
            result = str(message)
            if success:
                result += f" · Fine: ₹{float(fine or 0):.2f}"
            self.express_status_label.setText(result)
            self.express_status_label.setProperty(
                "success", bool(success)
            )
            self.express_status_label.style().unpolish(
                self.express_status_label
            )
            self.express_status_label.style().polish(
                self.express_status_label
            )
            self.refresh_dashboard()
            if success:
                self.express_book_input.clear()
        except Exception as error:
            self.express_status_label.setText(
                f"Return failed: {error}"
            )

    def search_global_records(self, query=None):
        query = safe_text(query).strip().casefold()
        if not query:
            return []

        books_success, books = self.db.get_books()
        users_success, users = self.db.get_users()
        logs_success, logs = self.db.get_logs()
        if not (books_success and users_success and logs_success):
            raise RuntimeError("The search data could not be loaded.")

        book_map = {
            str(row[0]): row for row in books if len(row) >= 2
        }
        user_map = {
            str(row[0]): row for row in users if len(row) >= 2
        }
        results = []
        category_counts = {
            "Book": 0,
            "Member": 0,
            "Transaction": 0,
        }
        per_category_limit = 4

        def append_result(kind, record_id, title, description, page):
            if category_counts[kind] >= per_category_limit:
                return
            results.append({
                "type": kind,
                "id": safe_text(record_id),
                "title": safe_text(title) or f"{kind} record",
                "description": safe_text(description),
                "page": page,
            })
            category_counts[kind] += 1

        for book in books:
            values = [safe_text(value) for value in book]
            if len(values) >= 2 and query in " ".join(values).casefold():
                author = values[2] if len(values) > 2 else ""
                append_result(
                    "Book",
                    values[0],
                    values[1],
                    f"Book · ID {values[0]}"
                    + (f" · {author}" if author else ""),
                    1,
                )

        for user in users:
            values = [safe_text(value) for value in user]
            if len(values) >= 2 and query in " ".join(values).casefold():
                role = values[3] if len(values) > 3 else "Member"
                append_result(
                    "Member",
                    values[0],
                    values[1],
                    f"Member · ID {values[0]} · {role}",
                    2,
                )

        for log in logs:
            if len(log) < 8:
                continue
            log_id, book_id, user_id, issue_date, due_date, returned, _fine, status = log
            book = book_map.get(str(book_id), ())
            user = user_map.get(str(user_id), ())
            values = [
                safe_text(value) for value in log
            ] + [
                safe_text(value) for value in book
            ] + [
                safe_text(value) for value in user
            ]
            if query in " ".join(values).casefold():
                book_title = (
                    safe_text(book[1])
                    if len(book) > 1 else safe_text(book_id)
                )
                member_name = (
                    safe_text(user[1])
                    if len(user) > 1 else safe_text(user_id)
                )
                append_result(
                    "Transaction",
                    log_id,
                    book_title,
                    f"Transaction · #{log_id} · {member_name} · "
                    f"{safe_text(status).title()}",
                    3,
                )

        return results

    def toggle_theme(self):
        if not self.theme_manager:
            QMessageBox.warning(
                self,
                "Theme Unavailable",
                "The application theme manager is not available.",
            )
            return

        active = self.theme_manager.get_active_theme()
        target = "Light" if active == "Dark" else "Dark"
        try:
            if not self.db.set_setting("theme_mode", target):
                raise RuntimeError("Unable to save the selected theme.")
            self.theme_manager.set_theme(target)
        except Exception as error:
            QMessageBox.critical(
                self, "Theme Change Failed", str(error)
            )

    def inspect_activity_record(self, item):
        record = item["record"]
        details = [
            ("Transaction ID", item["log_id"]),
            ("Book ID", item["book_id"]),
            ("Book Title", item["book_title"]),
            (
                "Member",
                f"{item['user_name']} ({item['user_id']})",
            ),
            ("Issue Date", item["issue_date"]),
            ("Due Date", item["due_date"]),
            ("Return Date", safe_text(record[5]) or "—"),
            ("Status", item["status"].title()),
            ("Fine", f"₹{float(item['fine'] or 0):.2f}"),
        ]
        dialog = ActivityDetailDialog(
            "Transaction",
            item["book_title"],
            f"{item['user_name']} ({item['user_id']})",
            item["display_date"],
            self,
            details=details,
            dialog_title=f"Transaction #{item['log_id']}",
        )
        dialog.exec()

    def return_activity_record(self, item):
        try:
            success, fine, message = self.db.return_book(
                item["book_id"],
                item["user_id"],
            )
            if success:
                QMessageBox.information(
                    self,
                    "Book Returned",
                    f"{message}\nFine: ₹{float(fine or 0):.2f}",
                )
                self.refresh_dashboard()
            else:
                QMessageBox.warning(
                    self, "Return Failed", str(message)
                )
        except Exception as error:
            QMessageBox.critical(
                self, "Return Error", str(error)
            )

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

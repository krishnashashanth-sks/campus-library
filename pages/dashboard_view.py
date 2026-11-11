
import csv
import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QBrush, QCursor, QFont, QKeyEvent, QLinearGradient,
    QPainter, QPainterPath, QPen,
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
    PendingFinesDialog,
    QuickScanDialog,
    RenewLoanDialog,
    ReturnBookDialog,
    UserDialog,
)
from ui_responsive import (
    FlowLayout,
    clamp_widget_to_screen,
    configure_inspector_form,
    configure_wrapped_label,
    wrap_in_scroll_area,
)
from utils import rgba_color


PRIMARY = "#2563eb"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"
INFO = "#6366f1"
STATUS_BADGE_COLORS = {
    "ISSUED": ("rgba(59, 130, 246, 0.22)", "#93C5FD", "#3B82F6"),
    "DUE TODAY": ("rgba(245, 158, 11, 0.22)", "#FCD34D", "#F59E0B"),
    "OVERDUE": ("rgba(244, 63, 94, 0.24)", "#FDA4AF", "#F43F5E"),
    "RETURNED": ("rgba(16, 185, 129, 0.22)", "#6EE7B7", "#10B981"),
    "RENEWED": ("rgba(34, 211, 238, 0.22)", "#67E8F9", "#06B6D4"),
}
STATUS_BADGE_COLORS_LIGHT = {
    "ISSUED": ("rgba(29, 78, 216, 0.20)", "#1E3A8A", "#1D4ED8"),
    "DUE TODAY": ("rgba(180, 83, 9, 0.22)", "#92400E", "#B45309"),
    "OVERDUE": ("rgba(190, 18, 60, 0.20)", "#9F1239", "#BE123C"),
    "RETURNED": ("rgba(4, 120, 87, 0.20)", "#065F46", "#047857"),
    "RENEWED": ("rgba(3, 105, 161, 0.20)", "#075985", "#0369A1"),
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
    window_color = theme.get(
        "window", palette.color(palette.ColorRole.Window).name()
    )
    is_dark = QColor(window_color).lightness() < 128

    return {
        "is_dark": is_dark,
        "window": window_color,
        "surface": theme.get(
            "surface", palette.color(palette.ColorRole.Base).name()
        ),
        "surface_alt": theme.get(
            "surface_alt", palette.color(palette.ColorRole.AlternateBase).name()
        ),
        "surface_elevated": theme.get("surface_elevated", "#1F2F52" if is_dark else "#BED0EC"),
        "text": theme.get(
            "text", palette.color(palette.ColorRole.Text).name()
        ),
        "muted": theme.get(
            "muted", palette.color(palette.ColorRole.PlaceholderText).name()
        ),
        "border": theme.get(
            "border", palette.color(palette.ColorRole.Mid).name()
        ),
        "border_bright": theme.get("border_bright", "#384F82" if is_dark else "#5A7CB2"),
        "header_bg": theme.get("header_bg", "#182745" if is_dark else "#C0D3EE"),
        "primary": theme.get(
            "primary", palette.color(palette.ColorRole.Highlight).name()
        ),
        "primary_hover": theme.get("primary_hover", PRIMARY),
        "primary_soft": theme.get("primary_soft", "rgba(59, 130, 246, 0.15)"),
        "indigo": theme.get("indigo", "#818CF8" if is_dark else "#4338CA"),
        "indigo_hover": theme.get("indigo_hover", "#6366F1" if is_dark else "#3730A3"),
        "indigo_soft": theme.get("indigo_soft", "rgba(129, 140, 248, 0.15)"),
        "cyan": theme.get("cyan", "#22D3EE" if is_dark else "#0369A1"),
        "cyan_hover": theme.get("cyan_hover", "#06B6D4" if is_dark else "#075985"),
        "cyan_soft": theme.get("cyan_soft", "rgba(34, 211, 238, 0.15)"),
        "teal": theme.get("teal", "#2DD4BF" if is_dark else "#0F766E"),
        "purple": theme.get("purple", "#A78BFA" if is_dark else "#6D28D9"),
        "purple_soft": theme.get("purple_soft", "rgba(167, 139, 250, 0.15)"),
        "success": theme.get("success", SUCCESS),
        "success_hover": theme.get("success_hover", "#059669"),
        "success_soft": theme.get("success_soft", "rgba(16, 185, 129, 0.15)"),
        "warning": theme.get("warning", WARNING),
        "warning_hover": theme.get("warning_hover", "#D97706"),
        "warning_soft": theme.get("warning_soft", "rgba(245, 158, 11, 0.15)"),
        "danger": theme.get("danger", DANGER),
        "danger_hover": theme.get("danger_hover", "#E11D48"),
        "danger_soft": theme.get("danger_soft", "rgba(244, 63, 94, 0.15)"),
        "table_row": theme.get("table_row", "#0F182B" if is_dark else "#E4EDF9"),
        "table_alt": theme.get("table_alt", "#142038" if is_dark else "#D6E3F6"),
        "overdue_tint": theme.get("overdue_tint", "#2A1420" if is_dark else "#F8CFD7"),
        "amber_tint": theme.get("amber_tint", "#2B2112" if is_dark else "#FCE0A2"),
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


class _ActivityTableWidget(QTableWidget):
    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), 160)


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
        self.setMinimumWidth(0)
        self.setMinimumHeight(74)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 5, 11, 5)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        configure_wrapped_label(self.title_label)
        top.addWidget(self.title_label, 1)

        self.icon_label = QLabel(icon)
        self.icon_label.setObjectName("MetricIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(24, 24)
        top.addWidget(self.icon_label)

        layout.addLayout(top)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setMinimumWidth(0)
        self.value_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.value_label)

        self.progress_bar = None

        if inventory:
            self.progress_bar = QProgressBar()
            self.progress_bar.setObjectName("InventoryProgress")
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(5)
            layout.addWidget(self.progress_bar)

        self.secondary_container = QWidget(self)
        self.secondary_container.setMinimumWidth(0)
        self.secondary_container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        secondary_layout = FlowLayout(
            self.secondary_container,
            margin=0,
            h_spacing=4,
            v_spacing=2,
        )
        self.issued_badge = QLabel()
        self.issued_badge.setObjectName("IssuedBadge")
        self.due_badge = QLabel()
        self.due_badge.setObjectName("DueBadge")
        secondary_layout.addWidget(self.issued_badge)
        secondary_layout.addWidget(self.due_badge)
        self.secondary_container.hide()
        layout.addWidget(self.secondary_container)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricSubtitle")
        configure_wrapped_label(self.subtitle_label)
        footer.addWidget(self.subtitle_label, 1)

        self.action_button = QPushButton(self)
        self.action_button.setObjectName("MetricAction")
        self.action_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.action_button.setFixedHeight(19)
        self.action_button.hide()
        footer.addWidget(self.action_button)
        layout.addLayout(footer)

        self.apply_style()

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())

    def apply_style(self, *_):
        c = get_theme_colors()
        is_dark = c.get("is_dark", True)
        accent = {
            "inventory": c["success"],
            "active_loans": c["primary"],
            "overdue_books": c["danger"],
            "unpaid_fines": c["warning"],
        }.get(self.metric_key, self.accent_color)
        secondary_accent = {
            "inventory": c.get("teal", "#2DD4BF"),
            "active_loans": c.get("indigo", "#818CF8"),
            "overdue_books": "#FB7185",
            "unpaid_fines": "#FBBF24" if is_dark else "#EA580C",
        }.get(self.metric_key, c.get("cyan", accent))

        top_tint = rgba_color(accent, 0.24 if is_dark else 0.28)
        bot_tint = rgba_color(secondary_accent, 0.09 if is_dark else 0.14)
        hover_top = rgba_color(accent, 0.32 if is_dark else 0.38)
        hover_bot = rgba_color(secondary_accent, 0.14 if is_dark else 0.20)
        card_border = rgba_color(accent, 0.55 if is_dark else 0.65)

        if self.metric_key == "overdue_books":
            accent = c["danger"]
            if self.overdue_active:
                card_border = c["danger"]
                top_tint = rgba_color(c["danger"], 0.30 if is_dark else 0.25)
                bot_tint = rgba_color(c["danger"], 0.14 if is_dark else 0.13)
        elif self.metric_key == "unpaid_fines" and self.unpaid_fines_active:
            accent = c["warning"]
            card_border = c["warning"]
            top_tint = rgba_color(c["warning"], 0.30 if is_dark else 0.32)
            bot_tint = rgba_color(c["warning"], 0.14 if is_dark else 0.16)

        icon_bg = rgba_color(accent, 0.24 if is_dark else 0.22)
        icon_border = rgba_color(accent, 0.52 if is_dark else 0.55)

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {top_tint},
                    stop:1 {bot_tint}
                );
                border: 1px solid {card_border};
                border-left: 4px solid {accent};
                border-radius: 12px;
            }}
            QFrame#MetricCard:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {hover_top},
                    stop:1 {hover_bot}
                );
                border: 1.5px solid {accent};
                border-left: 4px solid {secondary_accent};
            }}
            QLabel#MetricTitle {{
                color: {c['muted']};
                font-size: 11px;
                font-weight: 700;
                border: none;
                background: transparent;
            }}
            QLabel#MetricIcon {{
                color: {accent};
                font-size: 14px;
                font-weight: 800;
                background: {icon_bg};
                border: 1px solid {icon_border};
                border-radius: 8px;
            }}
            QLabel#MetricValue {{
                color: {c['text']};
                font-size: 19px;
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
                color: {c['cyan']};
                font-size: 9.5px;
                font-weight: 700;
                background: {c.get('cyan_soft', c['surface_alt'])};
                border: 1px solid {rgba_color(c['cyan'], 0.45)};
                border-radius: 6px;
                padding: 1px 6px;
            }}
            QLabel#DueBadge {{
                color: {c['warning']};
                font-size: 9.5px;
                font-weight: 700;
                background: {c.get('warning_soft', c['surface_alt'])};
                border: 1px solid {rgba_color(c['warning'], 0.45)};
                border-radius: 6px;
                padding: 1px 6px;
            }}
            QPushButton#MetricAction {{
                background: {rgba_color(accent, 0.14 if is_dark else 0.11)};
                color: {accent if is_dark else c['text']};
                border: 1px solid {rgba_color(accent, 0.40)};
                border-radius: 6px;
                padding: 1px 8px;
                font-size: 10px;
                font-weight: 700;
            }}
            QPushButton#MetricAction:hover {{
                background: {accent};
                color: #FFFFFF;
                border-color: {accent};
            }}
            QProgressBar#InventoryProgress {{
                background: {rgba_color(c['border'], 0.65)};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#InventoryProgress::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['success']},
                    stop:1 {c.get('cyan', c['success'])}
                );
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
        self.setMinimumHeight(150)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMouseTracking(True)
        self.days = []
        self.inventory = []
        self._is_stacked = False

    def set_data(self, days, inventory):
        self.days = list(days)
        self.inventory = list(inventory)
        self.update()

    def _chart_bounds(self):
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        stacked = width < 470
        if stacked:
            split_y = max(145, int(height * 0.48))
            chart_left = 30
            chart_right = width - 16
            chart_bottom = split_y - 24
            return stacked, width, height, 0, split_y, chart_left, chart_right, chart_bottom
        split_x = int(width * 0.59)
        chart_left = 34
        chart_right = split_x - 16
        chart_bottom = height - (22 if height < 186 else 30)
        return stacked, width, height, split_x, 0, chart_left, chart_right, chart_bottom

    def sizeHint(self):
        return QSize(560, 154)

    def minimumSizeHint(self):
        return QSize(240, 148)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return 300 if width < 470 else 152

    def resizeEvent(self, event):
        super().resizeEvent(event)
        stacked = self.width() < 470
        if stacked != self._is_stacked:
            self._is_stacked = stacked
            self.updateGeometry()

    def paintEvent(self, event):
        super().paintEvent(event)
        colors = get_theme_colors()
        is_dark = colors.get("is_dark", True)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Segoe UI", 9))

        stacked, width, height, split_x, split_y, chart_left, chart_right, chart_bottom = self._chart_bounds()
        compact_h = (not stacked) and height < 186
        muted = QColor(colors["muted"])
        text = QColor(colors["text"])
        border = QColor(colors["border"])

        title_text = "7-Day Circulation"
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setPen(text)
        painter.setFont(title_font)
        title_y = 19 if compact_h else 23
        painter.drawText(14, title_y, title_text)
        title_right = 14 + painter.fontMetrics().horizontalAdvance(title_text)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        ret_label = "Returned"
        iss_label = "Issued"
        ret_w = fm.horizontalAdvance(ret_label)
        iss_w = fm.horizontalAdvance(iss_label)
        legend_right = chart_right
        ret_text_x = legend_right - ret_w
        ret_box_x = ret_text_x - 13
        iss_text_x = ret_box_x - 14 - iss_w
        iss_box_x = iss_text_x - 13

        legend_collides = (title_right + 12) > iss_box_x
        if legend_collides:
            legend_base_y = 33 if compact_h else 39
            chart_top = 48 if compact_h else 56
            iss_box_x = 14
            iss_text_x = iss_box_x + 13
            ret_box_x = iss_text_x + iss_w + 14
            ret_text_x = ret_box_x + 13
        else:
            legend_base_y = 18 if compact_h else 22
            chart_top = 34 if compact_h else 48

        issued_color = QColor(colors["chart_issued"])
        returned_color = QColor(colors["chart_returned"])
        issued_end = QColor(colors["primary"])
        returned_end = QColor(colors.get("teal", "#0D9488"))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(issued_color)
        painter.drawRoundedRect(iss_box_x, legend_base_y - 8, 9, 9, 2, 2)
        painter.setPen(muted)
        painter.drawText(iss_text_x, legend_base_y, iss_label)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(returned_color)
        painter.drawRoundedRect(ret_box_x, legend_base_y - 8, 9, 9, 2, 2)
        painter.setPen(muted)
        painter.drawText(ret_text_x, legend_base_y, ret_label)

        chart_height = max(chart_bottom - chart_top, 16)
        values = [
            max(int(day.get("issued", 0)), int(day.get("returned", 0)))
            for day in self.days
        ]
        max_value = max(values, default=0) or 1

        painter.setFont(QFont("Segoe UI", 8))
        grid_pen = QPen(
            QColor(border.red(), border.green(), border.blue(), 110 if is_dark else 140),
            1,
            Qt.PenStyle.DashLine,
        )
        for frac, tick_val in ((1.0, max_value), (0.5, max(max_value // 2, 0))):
            gy = int(chart_bottom - chart_height * frac)
            painter.setPen(grid_pen)
            painter.drawLine(chart_left, gy, chart_right, gy)
            if tick_val > 0 or frac == 1.0:
                tick_str = str(tick_val)
                tw = painter.fontMetrics().horizontalAdvance(tick_str)
                painter.setPen(muted)
                painter.drawText(max(2, chart_left - tw - 6), gy + 3, tick_str)

        painter.setPen(QPen(border, 1))
        painter.drawLine(chart_left, chart_bottom, chart_right, chart_bottom)

        day_count = max(len(self.days), 1)
        group_width = max(chart_right - chart_left, 1) / day_count
        bar_width = max(min(int(group_width * 0.25), 14), 4)
        day_label_y = (split_y - 8) if stacked else (height - (7 if compact_h else 10))

        for index, day in enumerate(self.days):
            center = chart_left + group_width * (index + 0.5)
            if index == len(self.days) - 1:
                band_color = QColor(colors["primary"])
                band_color.setAlpha(20 if is_dark else 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(band_color)
                painter.drawRoundedRect(
                    int(chart_left + group_width * index + 3),
                    chart_top - 10,
                    max(int(group_width - 6), 8),
                    chart_height + 12,
                    6,
                    6,
                )

            for offset, key, top_col, bot_col in (
                (-bar_width * 0.65, "issued", issued_color, issued_end),
                (bar_width * 0.65, "returned", returned_color, returned_end),
            ):
                value = int(day.get(key, 0))
                bar_height = chart_height * value / max_value
                x = int(center + offset - bar_width / 2)
                draw_h = max(int(bar_height), 3 if value > 0 else 2)
                y = int(chart_bottom - draw_h)
                painter.setPen(Qt.PenStyle.NoPen)
                if value > 0:
                    grad = QLinearGradient(x, y, x, chart_bottom)
                    grad.setColorAt(0.0, top_col)
                    grad.setColorAt(1.0, bot_col)
                    painter.setBrush(grad)
                else:
                    flat = QColor(top_col)
                    flat.setAlpha(95 if is_dark else 110)
                    painter.setBrush(flat)
                painter.drawRoundedRect(x, y, bar_width, draw_h, 3, 3)

                if value:
                    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    val_str = str(value)
                    vw = painter.fontMetrics().horizontalAdvance(val_str)
                    painter.setPen(text)
                    painter.drawText(
                        int(x + bar_width / 2 - vw / 2),
                        max(y - 4, chart_top - 2),
                        val_str,
                    )

            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold if index == len(self.days) - 1 else QFont.Weight.Normal))
            painter.setPen(text if index == len(self.days) - 1 else muted)
            day_label = str(day.get("label", ""))
            lw = painter.fontMetrics().horizontalAdvance(day_label)
            painter.drawText(
                int(center - lw / 2), day_label_y, day_label
            )

        painter.setPen(QPen(border, 1))
        if stacked:
            painter.drawLine(14, split_y + 2, width - 14, split_y + 2)
            inv_title_y = split_y + 22
            status_x = 14
            status_width = max(width - 28, 1)
            bar_y = split_y + 34
        else:
            painter.drawLine(split_x, 12, split_x, height - 12)
            inv_title_y = 19 if compact_h else 23
            status_x = split_x + 14
            status_width = max(width - status_x - 14, 1)
            bar_y = 28 if compact_h else 46

        painter.setPen(text)
        painter.setFont(title_font)
        painter.drawText(status_x, inv_title_y, "Inventory Status")

        status_colors = {
            "Available on Shelf": (QColor(colors["success"]), QColor(colors.get("teal", "#0D9488"))),
            "Currently Issued": (QColor(colors["inventory_issued"]), QColor(colors.get("indigo", "#6366F1"))),
            "Due Today / Reserved": (QColor(colors["inventory_due"]), QColor("#EA580C")),
            "Overdue / Missing": (QColor(colors["inventory_overdue"]), QColor(colors["danger_hover"])),
        }
        bar_x = status_x
        bar_width_total = status_width
        total = sum(max(int(item.get("count", 0)), 0) for item in self.inventory)
        if total <= 0:
            painter.setPen(muted)
            painter.drawText(status_x, bar_y + 15, "No inventory records")
        else:
            painter.save()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(status_x, bar_y, bar_width_total, 10), 5, 5)
            painter.setClipPath(clip_path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(border.red(), border.green(), border.blue(), 120))
            painter.drawRect(status_x, bar_y, bar_width_total, 10)
            remaining_w = bar_width_total
            non_zero_items = [
                (item, max(int(item.get("count", 0)), 0))
                for item in self.inventory
                if max(int(item.get("count", 0)), 0) > 0
            ]
            for idx_item, (item, count) in enumerate(non_zero_items):
                seg_w = (
                    remaining_w
                    if idx_item == len(non_zero_items) - 1
                    else max(int(bar_width_total * count / total), 3)
                )
                seg_w = min(seg_w, remaining_w)
                c_start, c_end = status_colors[item["label"]]
                seg_grad = QLinearGradient(bar_x, bar_y, bar_x + max(seg_w, 1), bar_y)
                seg_grad.setColorAt(0.0, c_start)
                seg_grad.setColorAt(1.0, c_end)
                painter.setBrush(seg_grad)
                painter.drawRect(bar_x, bar_y, seg_w, 10)
                bar_x += seg_w
                remaining_w -= seg_w
            painter.restore()

            row_step = 26 if compact_h else (29 if stacked else 34)
            row_top = bar_y + (15 if compact_h else (16 if stacked else 22))
            track_bg = QColor(border.red(), border.green(), border.blue(), 95 if is_dark else 130)
            for item in self.inventory:
                count = max(int(item.get("count", 0)), 0)
                percent = count / total * 100
                c_start, c_end = status_colors[item["label"]]
                label_y = row_top + 9
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c_start)
                painter.drawRoundedRect(status_x, label_y - 7, 8, 8, 4, 4)

                percentage_text = f"{percent:.0f}%"
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                percentage_width = painter.fontMetrics().horizontalAdvance(percentage_text)
                painter.setPen(c_start if count > 0 else muted)
                painter.drawText(
                    width - 14 - percentage_width,
                    label_y,
                    percentage_text,
                )

                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.setPen(text)
                max_label_w = max(24, (width - 14 - percentage_width - 8) - (status_x + 14))
                row_label = painter.fontMetrics().elidedText(
                    f"{item['label']}  {count:,}",
                    Qt.TextElideMode.ElideRight,
                    max_label_w,
                )
                painter.drawText(status_x + 14, label_y, row_label)

                track_y = row_top + 14
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(track_bg)
                painter.drawRoundedRect(
                    status_x, track_y, status_width, 5, 2, 2
                )
                progress_width = int(status_width * count / total)
                if progress_width:
                    prog_grad = QLinearGradient(status_x, track_y, status_x + progress_width, track_y)
                    prog_grad.setColorAt(0.0, c_start)
                    prog_grad.setColorAt(1.0, c_end)
                    painter.setBrush(prog_grad)
                    painter.drawRoundedRect(
                        status_x, track_y, max(progress_width, 4), 5, 2, 2
                    )
                row_top += row_step

        painter.end()

    def mouseMoveEvent(self, event):
        if self.days:
            stacked, _w, _h, _sx, split_y, chart_left, chart_right, _cb = self._chart_bounds()
            in_y = (event.position().y() <= split_y) if stacked else True
            if in_y and chart_left <= event.position().x() <= chart_right and chart_right > chart_left:
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
        clamp_widget_to_screen(self, 1050, 620, min_width=480, min_height=340)

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(20, 18, 20, 18)
        self.layout_main.setSpacing(14)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        configure_wrapped_label(self.title_label)
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

        header = self.table.horizontalHeader()
        if column_count > 4 and available_width < column_count * 95:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            self.table.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            for index, header_text in enumerate(self.headers):
                weight = self.COLUMN_WEIGHTS.get(header_text, 1.15)
                self.table.setColumnWidth(index, max(90, int(92 * weight)))
            return

        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        weights = [
            self.COLUMN_WEIGHTS.get(header_text, 1.15)
            for header_text in self.headers
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
        action_label=None,
        action_callback=None,
    ):
        super().__init__(parent)

        self.action_type = safe_text(action_type)
        self.book_title = safe_text(book_title)
        self.username = safe_text(username)
        self.timestamp = safe_text(timestamp)
        self._action_callback = action_callback

        self.detail_items = details or [
            ("BOOK / ITEM", self.book_title),
            ("USER", self.username),
            ("ACTIVITY TYPE", self.action_type),
            ("TIMESTAMP", self.timestamp),
        ]
        self.setWindowTitle(dialog_title)
        clamp_widget_to_screen(self, 620, 520, min_width=380, min_height=320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = (
            dialog_title
            if details is not None
            else f"{activity_icon(self.action_type)}  {self.action_type}"
        )
        title = QLabel(heading)
        configure_wrapped_label(title)
        title.setStyleSheet(
            "font-size: 20px; font-weight: 750;"
        )
        layout.addWidget(title)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(10)

        if details is not None:
            detail_form = QFormLayout()
            detail_form.setContentsMargins(2, 4, 2, 4)
            configure_inspector_form(detail_form, horizontal_spacing=12, vertical_spacing=8)
            for label, value in self.detail_items:
                key_label = QLabel(label)
                configure_wrapped_label(key_label, expanding_width=False)
                key_label.setStyleSheet(
                    "font-size: 10px; font-weight: 700;"
                )
                value_label = QLabel(safe_text(value) or "Not available")
                configure_wrapped_label(value_label)
                value_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                value_label.setStyleSheet(
                    "font-size: 12px; font-weight: 600;"
                )
                detail_form.addRow(key_label, value_label)
            body_layout.addLayout(detail_form)
            body_layout.addStretch()
        else:
            for label, value in self.detail_items:
                self.add_detail(body_layout, label, safe_text(value))

            note = QLabel(
                "The recent activity database method currently supplies "
                "these four fields. Additional transaction details are "
                "not available from that result."
            )
            configure_wrapped_label(note)
            note.setStyleSheet("font-size: 10px;")
            body_layout.addWidget(note)
            body_layout.addStretch()

        scroll = wrap_in_scroll_area(body, object_name="ActivityDetailScroll")
        layout.addWidget(scroll, 1)

        footer_widget = QWidget()
        footer = FlowLayout(footer_widget, margin=0, h_spacing=8, v_spacing=8)

        copy_button = QPushButton("Copy Details")
        copy_button.clicked.connect(self.copy_details)

        footer.addWidget(copy_button)

        if action_label and callable(action_callback):
            action_button = QPushButton(action_label)
            action_button.clicked.connect(self._trigger_custom_action)
            footer.addWidget(action_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)

        layout.addWidget(footer_widget)

        self.theme_manager = connect_theme(self)
        self.apply_theme()

    def _trigger_custom_action(self):
        self.accept()
        if callable(self._action_callback):
            self._action_callback()

    def add_detail(self, parent_layout, heading, value):
        frame = QFrame()
        frame.setObjectName("DetailFrame")
        frame.setMinimumWidth(0)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(4)

        label = QLabel(heading)
        configure_wrapped_label(label)
        label.setStyleSheet("font-size: 10px; font-weight: 700;")

        value_label = QLabel(value or "Not available")
        configure_wrapped_label(value_label)
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
    HEADERS = ["Log ID", "Activity", "Book / Item", "User", "Renewals", "Timestamp"]
    data_updated = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self.all_logs = []
        self.filtered_logs = []

        self.setWindowTitle("Complete Activity History")
        clamp_widget_to_screen(self, 1120, 670, min_width=480, min_height=360)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 16, 18, 16)
        self.main_layout.setSpacing(12)

        self.build_ui()

        self.theme_manager = connect_theme(self)
        self.apply_theme()
        self.load_history()

    def build_ui(self):
        header = QHBoxLayout()
        header.setSpacing(10)

        heading_col = QVBoxLayout()
        heading_col.setSpacing(2)

        title = QLabel("Activity History")
        configure_wrapped_label(title)
        title.setStyleSheet("font-size: 21px; font-weight: 750;")

        description = QLabel(
            "Search, inspect, renew, return, and export complete circulation history."
        )
        configure_wrapped_label(description)
        description.setStyleSheet("font-size: 11px;")

        heading_col.addWidget(title)
        heading_col.addWidget(description)

        header.addLayout(heading_col, 1)

        refresh = QPushButton("↻  Refresh")
        refresh.clicked.connect(self.load_history)
        header.addWidget(refresh)

        self.main_layout.addLayout(header)

        filter_frame = QFrame()
        filter_frame.setObjectName("FilterPanel")

        filters = QGridLayout(filter_frame)
        filters.setContentsMargins(12, 10, 12, 10)
        filters.setHorizontalSpacing(10)
        filters.setVerticalSpacing(8)
        self._filters_grid = filters
        self._filters_stacked = None

        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(140)
        self.search_input.setPlaceholderText(
            "Search log ID, activity, book, user or timestamp..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.apply_filters)

        self.type_filter = QComboBox()
        self.type_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.type_filter.setMinimumWidth(135)
        self.type_filter.addItems([
            "All Activities", "Issue", "Renewed", "Return",
            "Overdue", "Fine", "Other",
        ])
        self.type_filter.currentTextChanged.connect(
            self.apply_filters
        )

        filters.addWidget(self.search_input, 0, 0)
        filters.addWidget(self.type_filter, 0, 1)
        filters.setColumnStretch(0, 3)
        filters.setColumnStretch(1, 1)

        self.main_layout.addWidget(filter_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
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
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self._history_table_compact = None
        self._apply_history_table_columns()

        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self.table.cellDoubleClicked.connect(
            self.open_selected_activity
        )

        self.main_layout.addWidget(self.table, 1)

        footer = QGridLayout()
        footer.setHorizontalSpacing(10)
        footer.setVerticalSpacing(4)

        self.count_label = QLabel("0 activities")
        footer.addWidget(self.count_label, 0, 0)

        self.hint_label = QLabel(
            "Double-click any record to view full details & renewal timeline."
        )
        configure_wrapped_label(self.hint_label)
        self.hint_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        footer.addWidget(self.hint_label, 0, 1)
        footer.setColumnStretch(1, 1)

        self.main_layout.addLayout(footer)

        buttons_bar = QWidget()
        buttons = FlowLayout(buttons_bar, margin=0, h_spacing=8, v_spacing=8)

        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self.export_csv)

        self.renew_button = QPushButton("🔄 Renew Loan")
        self.renew_button.clicked.connect(self.renew_selected_activity)

        self.return_button = QPushButton("↩ Return Book")
        self.return_button.clicked.connect(self.return_selected_activity)

        self.details_button = QPushButton("View Details")
        self.details_button.clicked.connect(
            self.open_selected_activity
        )

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        buttons.addWidget(self.export_button)
        buttons.addWidget(self.renew_button)
        buttons.addWidget(self.return_button)
        buttons.addWidget(self.details_button)
        buttons.addWidget(close_button)

        self.main_layout.addWidget(buttons_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_history_responsive()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_history_responsive()

    def _apply_history_responsive(self):
        stacked = self.width() < 580
        if stacked != self._filters_stacked:
            self._filters_stacked = stacked
            if stacked:
                self._filters_grid.addWidget(self.search_input, 0, 0)
                self._filters_grid.addWidget(self.type_filter, 1, 0)
                self._filters_grid.setColumnStretch(0, 1)
                self._filters_grid.setColumnStretch(1, 0)
            else:
                self._filters_grid.addWidget(self.search_input, 0, 0)
                self._filters_grid.addWidget(self.type_filter, 0, 1)
                self._filters_grid.setColumnStretch(0, 3)
                self._filters_grid.setColumnStretch(1, 1)
        self._apply_history_table_columns()

    def _apply_history_table_columns(self):
        compact = max(self.table.viewport().width(), self.width() - 40) < 700
        if compact == self._history_table_compact:
            return
        self._history_table_compact = compact
        header = self.table.horizontalHeader()
        if compact:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            for col, width in enumerate((68, 95, 190, 145, 78, 130)):
                self.table.setColumnWidth(col, width)
        else:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

    def load_history(self):
        try:
            success, entries = self.db.get_activity_history_entries(
                limit=5000
            )
            self.all_logs = list(entries or []) if success else []

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

    def matches_type(self, entry, selected):
        status = safe_text(entry.get("status")).casefold()
        ren_count = int(entry.get("renewal_count", 0) or 0)
        fine_amt = float(entry.get("fine_amount", 0) or 0.0)

        if selected == "All Activities":
            return True
        if selected == "Issue":
            return entry.get("raw_status") == "ISSUED"
        if selected == "Renewed":
            return ren_count > 0
        if selected == "Return":
            return "return" in status
        if selected == "Overdue":
            return "overdue" in status
        if selected == "Fine":
            return fine_amt > 0
        if selected == "Other":
            known = ("issue", "checkout", "return", "overdue", "due today", "fine")
            return not any(word in status for word in known) and ren_count == 0

        return True

    def apply_filters(self, *_):
        query = self.search_input.text().strip().casefold()
        selected = self.type_filter.currentText()

        self.filtered_logs = []

        for entry in self.all_logs:
            if not self.matches_type(entry, selected):
                continue

            if query:
                searchable = " ".join([
                    str(entry.get("log_id", "")),
                    entry.get("status", ""),
                    entry.get("book_label", ""),
                    entry.get("user_label", ""),
                    entry.get("timestamp", ""),
                    str(entry.get("renewal_count", 0)),
                ]).casefold()
                if query not in searchable:
                    continue

            self.filtered_logs.append(entry)

        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.filtered_logs))

        for row, entry in enumerate(self.filtered_logs):
            ren_count = int(entry.get("renewal_count", 0) or 0)
            values = [
                f"#{entry['log_id']}",
                entry["status"],
                entry["book_label"],
                entry["user_label"],
                f"↻ {ren_count}" if ren_count > 0 else "0",
                entry["timestamp"],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)

                if col == 1:
                    item.setForeground(
                        QBrush(QColor(activity_color(value)))
                    )

                self.table.setItem(row, col, item)

        self.count_label.setText(
            f"{len(self.filtered_logs)} of "
            f"{len(self.all_logs)} activities"
        )

        self.export_button.setEnabled(bool(self.filtered_logs))
        if self.filtered_logs:
            self.table.selectRow(0)
        self._update_action_buttons()

    def _current_entry(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.filtered_logs):
            return self.filtered_logs[row]
        return None

    def _update_action_buttons(self):
        entry = self._current_entry()
        has_entry = entry is not None
        is_active = bool(has_entry and entry.get("raw_status") == "ISSUED")
        self.details_button.setEnabled(has_entry)
        self.renew_button.setEnabled(is_active)
        self.return_button.setEnabled(is_active)

    def renew_selected_activity(self, *_):
        entry = self._current_entry()
        if not entry or entry.get("raw_status") != "ISSUED":
            return
        dialog = RenewLoanDialog(self.db, entry["log_id"], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.data_updated.emit()
            QMessageBox.information(
                self,
                "Loan Renewed",
                dialog.result_message or "Loan renewed successfully.",
            )
            self.load_history()

    def return_selected_activity(self, *_):
        entry = self._current_entry()
        if not entry or entry.get("raw_status") != "ISSUED":
            return
        answer = QMessageBox.question(
            self,
            "Confirm Return",
            f"Return {entry['book_label']} for {entry['user_label']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            success, fine, message = self.db.return_book(
                entry["book_id"],
                entry["user_id"],
            )
            if success:
                self.data_updated.emit()
                QMessageBox.information(
                    self,
                    "Book Returned",
                    f"{message}\nFine: ₹{float(fine or 0):.2f}",
                )
                self.load_history()
            else:
                QMessageBox.warning(self, "Return Failed", str(message))
        except Exception as error:
            QMessageBox.critical(self, "Return Error", str(error))

    def open_selected_activity(self, *_):
        entry = self._current_entry()

        if not entry:
            QMessageBox.information(
                self,
                "Select Activity",
                "Please select an activity record first.",
            )
            return

        full = self.db.get_circulation_log_details(entry["log_id"])
        if not full:
            dialog = ActivityDetailDialog(
                entry["status"],
                entry["book_label"],
                entry["user_label"],
                entry["timestamp"],
                self,
            )
            dialog.exec()
            return

        fine_val = float(full.get("fine_amount") or 0.0)
        if fine_val <= 0:
            fine_text = "₹0.00"
        elif full.get("fine_settled"):
            badge = "Waived" if full.get("fine_settlement_action") == "WAIVED" else "Paid"
            fine_text = f"₹{fine_val:.2f} ({badge})"
        else:
            fine_text = f"₹{fine_val:.2f} (Unpaid)"

        max_r = int(full.get("max_renewals") or 0)
        r_count = int(full.get("renewal_count") or 0)
        ren_text = f"{r_count} / {max_r}" if max_r > 0 else f"{r_count} (Unlimited)"
        details = [
            ("TRANSACTION ID", f"#{full['log_id']}"),
            ("STATUS", full["status"]),
            ("BOOK", f"{full['book_title']} ({full['book_id']})"),
            ("MEMBER", f"{full['user_name']} ({full['user_id']} · {full['user_role']})"),
            ("ISSUED ON", full["checkout_date"] or "—"),
            ("DUE DATE", full["due_date"] or "—"),
            ("RENEWALS", ren_text),
            ("LAST RENEWED", full["last_renewed_at"] or "—"),
            ("RETURNED ON", full["return_date"] or "Not yet returned"),
            ("FINE", fine_text),
        ]
        history = full.get("renewal_history") or []
        if history:
            timeline = "\n".join(
                f"• {h['renewed_at']} | +{h['extended_days']}d -> {h['new_due_date']}"
                + (f" | {h['notes']}" if h.get("notes") else "")
                for h in history[:5]
            )
            details.append(("RECENT RENEWALS", timeline))

        is_active = full.get("raw_status") == "ISSUED"
        dialog = ActivityDetailDialog(
            full["status"],
            full["book_title"],
            full["user_name"],
            entry["timestamp"],
            self,
            details=details,
            dialog_title=f"Transaction #{full['log_id']}",
            action_label="Renew Loan" if is_active else None,
            action_callback=(
                self.renew_selected_activity
                if is_active
                else None
            ),
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
                for entry in self.filtered_logs:
                    writer.writerow([
                        entry["log_id"],
                        entry["status"],
                        entry["book_label"],
                        entry["user_label"],
                        entry["renewal_count"],
                        entry["timestamp"],
                    ])

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
        self._metrics_columns = None
        self._middle_stacked = None
        self._header_stacked = None
        self._activity_header_inline = None
        self._activity_table_compact = None
        self._metric_order = [
            "inventory",
            "active_loans",
            "overdue_books",
            "unpaid_fines",
        ]

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
        self.dashboard_content.setMinimumWidth(0)
        self.dashboard_scroll.setWidget(self.dashboard_content)
        outer_layout.addWidget(self.dashboard_scroll)

        self.main_layout = QVBoxLayout(self.dashboard_content)
        self.main_layout.setContentsMargins(16, 6, 16, 40)
        self.main_layout.setSpacing(6)

        self.dashboard_header_layout = QGridLayout()
        self.dashboard_header_layout.setHorizontalSpacing(10)
        self.dashboard_header_layout.setVerticalSpacing(6)

        self.header_title_box = QWidget()
        self.header_title_box.setMinimumWidth(0)
        title_box = QVBoxLayout(self.header_title_box)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        page_title = QLabel("Dashboard")
        page_title.setObjectName("PageTitle")
        title_box.addWidget(page_title)

        page_subtitle = QLabel(
            "At a glance: inventory, circulation, and recent activity."
        )
        page_subtitle.setObjectName("PageSubtitle")
        configure_wrapped_label(page_subtitle)
        title_box.addWidget(page_subtitle)
        self.dashboard_header_layout.addWidget(self.header_title_box, 0, 0)

        self.header_actions_host = QWidget()
        self.header_actions_host.setMinimumWidth(0)
        header_actions = QHBoxLayout(self.header_actions_host)
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(8)

        self.header_refresh_btn = QPushButton("↻ Refresh")
        self.header_refresh_btn.setObjectName("ViewAllButton")
        self.header_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_refresh_btn.setToolTip("Refresh Dashboard (F5)")
        self.header_refresh_btn.clicked.connect(self.refresh_dashboard)
        header_actions.addWidget(self.header_refresh_btn)

        self.dashboard_header_layout.addWidget(
            self.header_actions_host,
            0,
            1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.dashboard_header_layout.setColumnStretch(0, 1)
        self.main_layout.addLayout(self.dashboard_header_layout)

        self.tiles_grid = QGridLayout()
        self.tiles_grid.setHorizontalSpacing(10)
        self.tiles_grid.setVerticalSpacing(8)

        for column in range(4):
            self.tiles_grid.setColumnStretch(column, 1)
        self.tiles_grid.setRowMinimumHeight(0, 74)
        self.tiles_grid.setRowStretch(0, 0)

        self.main_layout.addLayout(self.tiles_grid)
        self._create_metric_cards()

        self.middle_layout = QGridLayout()
        self.middle_layout.setHorizontalSpacing(10)
        self.middle_layout.setVerticalSpacing(6)
        self.analytics_panel = self._create_analytics_panel()
        self.express_panel = self._create_express_circulation_panel()
        self.middle_layout.addWidget(self.analytics_panel, 0, 0)
        self.middle_layout.addWidget(self.express_panel, 0, 1)
        self.middle_layout.setColumnStretch(0, 13)
        self.middle_layout.setColumnStretch(1, 7)
        self.main_layout.addLayout(self.middle_layout)

        self.lower_layout = QGridLayout()
        self.lower_layout.setHorizontalSpacing(10)
        self.lower_layout.setVerticalSpacing(8)
        self.activity_panel = self._create_activity_table_panel()
        self.quick_actions_card = None
        self.lower_layout.addWidget(self.activity_panel, 0, 0)
        self.lower_layout.setColumnStretch(0, 1)

        self.main_layout.addLayout(self.lower_layout, 1)
        self.main_layout.setStretch(0, 0)
        self.main_layout.setStretch(1, 0)
        self.main_layout.setStretch(2, 0)
        self.main_layout.setStretch(3, 1)

        self.theme_manager = connect_theme(self)
        self.apply_theme()
        self._reflow_layout()
        self.refresh_dashboard()

    def _create_analytics_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setProperty("panelRole", "analytics")
        panel.setMinimumWidth(0)
        panel.setMinimumHeight(156)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 6, 10, 5)
        layout.setSpacing(2)

        self.analytics_widget = CirculationAnalyticsWidget()
        layout.addWidget(self.analytics_widget, 1)
        return panel

    def _create_express_circulation_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setProperty("panelRole", "express")
        panel.setMinimumWidth(0)
        panel.setMinimumHeight(156)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 6, 11, 6)
        layout.setSpacing(2)

        title = QLabel("⚡ Express Circulation")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.express_user_input = QLineEdit()
        self.express_user_input.setObjectName("ExpressInput")
        self.express_user_input.setMinimumWidth(0)
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
        configure_wrapped_label(self.express_user_preview)
        layout.addWidget(self.express_user_preview)

        self.express_book_input = ExpressBookInput()
        self.express_book_input.setObjectName("ExpressInput")
        self.express_book_input.setMinimumWidth(0)
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
        configure_wrapped_label(self.express_book_preview)
        layout.addWidget(self.express_book_preview)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.instant_issue_button = QPushButton("⚡ Issue")
        self.instant_issue_button.setToolTip("Issue Book (Enter)")
        self.instant_issue_button.setObjectName("InstantIssue")
        self.instant_issue_button.setMinimumWidth(0)
        self.instant_issue_button.clicked.connect(self.instant_issue_book)
        actions.addWidget(self.instant_issue_button)

        self.instant_renew_button = QPushButton("↻ Renew")
        self.instant_renew_button.setToolTip("Renew Active Loan")
        self.instant_renew_button.setObjectName("InstantRenew")
        self.instant_renew_button.setMinimumWidth(0)
        self.instant_renew_button.setEnabled(False)
        self.instant_renew_button.clicked.connect(self.instant_renew_book)
        actions.addWidget(self.instant_renew_button)

        self.instant_return_button = QPushButton("↩ Return")
        self.instant_return_button.setToolTip("Return Book (Shift+Enter)")
        self.instant_return_button.setObjectName("InstantReturn")
        self.instant_return_button.setMinimumWidth(0)
        self.instant_return_button.clicked.connect(self.instant_return_book)
        actions.addWidget(self.instant_return_button)
        layout.addLayout(actions)

        self.express_status_label = QLabel("")
        self.express_status_label.setObjectName("ExpressStatus")
        configure_wrapped_label(self.express_status_label)
        self.express_status_label.hide()
        layout.addWidget(self.express_status_label)
        return panel

    def _create_activity_table_panel(self):
        panel = QFrame()
        panel.setObjectName("DashboardPanel")
        panel.setProperty("panelRole", "activity")
        panel.setMinimumWidth(0)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(5)

        header = QGridLayout()
        header.setHorizontalSpacing(8)
        header.setVerticalSpacing(4)
        self.activity_header_layout = header

        self.activity_title_label = QLabel("Recent Circulation & Alerts")
        self.activity_title_label.setObjectName("PanelTitle")
        configure_wrapped_label(self.activity_title_label, expanding_width=False)

        self.filters_host = QWidget()
        self.filters_host.setMinimumWidth(0)
        self.filters_host.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        filters = FlowLayout(self.filters_host, margin=0, h_spacing=4, v_spacing=4)
        filter_group = QButtonGroup(self)
        filter_group.setExclusive(True)
        for label, role_key in (
            ("All Recent", "all"),
            ("Issued Today", "issued"),
            ("Due Today", "due"),
            ("Overdue Alerts", "overdue"),
            ("Renewed", "renewed"),
        ):
            button = QPushButton(label)
            button.setObjectName("ActivityFilter")
            button.setProperty("filterRole", role_key)
            button.setCheckable(True)
            button.setFixedHeight(25)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(label == self._activity_filter)
            button.clicked.connect(
                lambda _checked=False, value=label:
                self.set_activity_filter(value)
            )
            filter_group.addButton(button)
            self.activity_filter_buttons[label] = button
            filters.addWidget(button)

        self.activity_summary_label = QLabel("Latest transactions")
        self.activity_summary_label.setObjectName("ActivitySummary")
        self.activity_summary_label.setFixedHeight(25)
        self.activity_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.view_all_button = QPushButton("View All")
        self.view_all_button.setObjectName("ViewAllButton")
        self.view_all_button.setFixedHeight(25)
        self.view_all_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.view_all_button.clicked.connect(self.open_activity_history)

        self._reflow_activity_header(inline=True)
        layout.addLayout(header)

        self.activity_table = _ActivityTableWidget()
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
        self.activity_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.verticalHeader().setDefaultSectionSize(40)
        self.activity_table.setMouseTracking(True)

        table_header = self.activity_table.horizontalHeader()
        table_header.setMinimumSectionSize(44)
        self._apply_activity_table_columns(compact=False)

        self.activity_table.setMinimumWidth(0)
        self.activity_table.setMinimumHeight(106)
        self.activity_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.activity_table, 1)
        self.activity_empty_hint = QLabel(
            "Showing all recent records — Press Ctrl+I to issue a book "
            "or scan a barcode at the Express Desk."
        )
        self.activity_empty_hint.setObjectName("ActivityEmptyHint")
        self.activity_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        configure_wrapped_label(self.activity_empty_hint)
        self.activity_empty_hint.hide()
        layout.addWidget(self.activity_empty_hint)
        return panel

    def _reflow_activity_header(self, inline: bool):
        if inline == self._activity_header_inline or not hasattr(self, "activity_header_layout"):
            return
        self._activity_header_inline = inline
        header = self.activity_header_layout
        for widget in (
            self.activity_title_label,
            self.filters_host,
            self.activity_summary_label,
            self.view_all_button,
        ):
            header.removeWidget(widget)
        for col in range(4):
            header.setColumnStretch(col, 0)

        if inline:
            header.addWidget(self.activity_title_label, 0, 0, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.filters_host, 0, 1, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.activity_summary_label, 0, 2, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.view_all_button, 0, 3, Qt.AlignmentFlag.AlignVCenter)
            header.setColumnStretch(1, 1)
        else:
            header.addWidget(self.activity_title_label, 0, 0, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.activity_summary_label, 0, 1, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.view_all_button, 0, 2, Qt.AlignmentFlag.AlignVCenter)
            header.addWidget(self.filters_host, 1, 0, 1, 3)
            header.setColumnStretch(0, 1)

    # --------------------------------------------------------
    # THEME
    # --------------------------------------------------------

    def apply_theme(self, *_):
        c = get_theme_colors()
        is_dark = c.get("is_dark", True)
        indigo = c.get("indigo", "#6366F1")
        indigo_hover = c.get("indigo_hover", "#4F46E5")
        cyan = c.get("cyan", "#06B6D4")
        cyan_hover = c.get("cyan_hover", "#0891B2")
        teal = c.get("teal", "#0D9488")
        purple = c.get("purple", "#8B5CF6")
        primary = c["primary"]
        primary_hover = c.get("primary_hover", primary)
        success = c.get("success", SUCCESS)
        success_hover = c.get("success_hover", "#059669")
        warning = c.get("warning", WARNING)
        warning_hover = c.get("warning_hover", "#D97706")
        danger = c.get("danger", DANGER)
        danger_hover = c.get("danger_hover", "#E11D48")
        border_bright = c.get("border_bright", c["border"])
        row_return_bg = "#13342E" if is_dark else "#DCFCE7"
        row_return_fg = "#34D399" if is_dark else "#065F46"
        row_renew_bg = "#123044" if is_dark else "#E0F2FE"
        row_renew_fg = "#38BDF8" if is_dark else "#075985"
        row_inspect_bg = "#202752" if is_dark else "#E0E7FF"
        row_inspect_fg = "#A5B4FC" if is_dark else "#3730A3"
        row_disabled_bg = "#182542" if is_dark else "#E2EAF6"
        row_disabled_fg = "#7D93B2" if is_dark else "#64748B"
        row_disabled_border = "#28385C" if is_dark else "#9DB3D6"

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
                background: {c.get('input', c['surface_alt'])};
                color: {c['text']};
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
            }}

            QLineEdit#ExpressInput:hover {{
                border-color: {border_bright};
            }}

            QLineEdit#ExpressInput:focus {{
                border: 1.5px solid {cyan};
                background: {c['surface']};
            }}

            QLabel#ExpressPreview, QLabel#ExpressStatus {{
                color: {c['muted']};
                font-size: 9.5px;
                background: transparent;
                border-radius: 5px;
                padding: 1px 4px;
            }}

            QLabel#ExpressPreview[matchState="ok"] {{
                color: {success};
                background: {c['success_soft']};
                font-weight: 600;
            }}

            QLabel#ExpressPreview[matchState="warn"] {{
                color: {danger};
                background: {c['danger_soft']};
                font-weight: 600;
            }}

            QLabel#ExpressStatus[success="true"] {{
                color: {success};
                font-weight: 700;
            }}

            QLabel#ExpressStatus[success="false"] {{
                color: {danger};
                font-weight: 700;
            }}

            QPushButton#InstantIssue,
            QPushButton#InstantRenew,
            QPushButton#InstantReturn {{
                color: white;
                border: none;
                border-radius: 8px;
                padding: 5px 8px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#InstantIssue {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {primary},
                    stop:1 {indigo}
                );
            }}

            QPushButton#InstantIssue:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {primary_hover},
                    stop:1 {indigo_hover}
                );
            }}

            QPushButton#InstantIssue:disabled {{
                background: {c['primary_soft']};
                color: {rgba_color(primary, 0.70 if is_dark else 0.75)};
                border: 1px solid {rgba_color(primary, 0.35)};
            }}

            QPushButton#InstantRenew {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {cyan_hover},
                    stop:1 {primary}
                );
            }}

            QPushButton#InstantRenew:hover {{
                background: {cyan_hover};
            }}

            QPushButton#InstantRenew:disabled {{
                background: {c['cyan_soft']};
                color: {rgba_color(cyan, 0.70 if is_dark else 0.75)};
                border: 1px solid {rgba_color(cyan, 0.35)};
            }}

            QPushButton#InstantReturn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {success},
                    stop:1 {teal}
                );
            }}

            QPushButton#InstantReturn:hover {{
                background: {success_hover};
            }}

            QPushButton#InstantReturn:disabled {{
                background: {c['success_soft']};
                color: {rgba_color(success, 0.70 if is_dark else 0.75)};
                border: 1px solid {rgba_color(success, 0.35)};
            }}

            QFrame#DashboardPanel {{
                background: {c['surface']};
                border: 1.5px solid {c['border']};
                border-radius: 12px;
            }}

            QFrame#DashboardPanel[panelRole="analytics"] {{
                border-top: 3px solid {cyan};
            }}

            QFrame#DashboardPanel[panelRole="express"] {{
                border-top: 3px solid {indigo};
            }}

            QFrame#DashboardPanel[panelRole="activity"] {{
                border-top: 3px solid {primary};
            }}

            QFrame#DashboardPanel[panelRole="actions"] {{
                border-top: 3px solid {purple};
            }}

            QLabel#PanelTitle {{
                color: {c['text']};
                font-size: 13px;
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#ActivitySummary {{
                color: {cyan};
                background: {c['cyan_soft']};
                border: 1px solid {rgba_color(cyan, 0.55)};
                border-radius: 8px;
                padding: 0px 9px;
                min-height: 23px;
                max-height: 23px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#ActivityFilter {{
                background: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {border_bright};
                border-radius: 7px;
                padding: 0px 8px;
                min-height: 23px;
                max-height: 23px;
                font-size: 10px;
                font-weight: 600;
            }}

            QPushButton#ActivityFilter:hover {{
                background: {c['surface_elevated']};
                color: {c['text']};
                border-color: {primary};
            }}

            QPushButton#ActivityFilter[filterRole="all"]:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {primary}, stop:1 {indigo});
                color: white;
                border-color: {primary};
                font-weight: 700;
            }}

            QPushButton#ActivityFilter[filterRole="issued"]:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {indigo}, stop:1 {purple});
                color: white;
                border-color: {indigo};
                font-weight: 700;
            }}

            QPushButton#ActivityFilter[filterRole="due"]:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {warning}, stop:1 #EA580C);
                color: white;
                border-color: {warning};
                font-weight: 700;
            }}

            QPushButton#ActivityFilter[filterRole="overdue"]:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {danger}, stop:1 {danger_hover});
                color: white;
                border-color: {danger};
                font-weight: 700;
            }}

            QPushButton#ActivityFilter[filterRole="renewed"]:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {cyan_hover}, stop:1 {teal});
                color: white;
                border-color: {cyan_hover};
                font-weight: 700;
            }}

            QTableWidget#ActivityTable {{
                background: {c['table_row']};
                alternate-background-color: {c['table_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 10px;
                selection-background-color: {primary};
                selection-color: {c['selection_text']};
                outline: none;
                font-size: 11px;
            }}

            QTableWidget#ActivityTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid {c['border']};
            }}

            QTableWidget#ActivityTable::item:hover {{
                background: {c['primary_soft']};
            }}

            QLabel#StatusBadge {{
                border-radius: 9px;
                padding: 2px 8px;
                margin: 4px 2px;
                font-size: 10px;
                font-weight: 800;
            }}

            QHeaderView::section {{
                background: {c['header_bg']};
                color: {c['text']};
                border: none;
                border-bottom: 2px solid {border_bright};
                padding: 7px 8px;
                font-size: 10px;
                font-weight: 700;
            }}

            QLabel#ActivityEmptyHint {{
                color: {c['muted']};
                font-size: 10px;
                padding: 3px;
                background: transparent;
            }}

            QPushButton#RowAction {{
                background: {c['surface']};
                color: {c['text']};
                border: 1px solid {border_bright};
                border-radius: 6px;
                padding: 0px 4px;
                margin: 0px;
                min-height: 22px;
                max-height: 22px;
                font-size: 9.5px;
                font-weight: 700;
            }}

            QPushButton#RowAction[actionRole="return"] {{
                background: {row_return_bg};
                color: {row_return_fg};
                border-color: {success};
            }}
            QPushButton#RowAction[actionRole="return"]:hover {{
                background: {success};
                color: #FFFFFF;
                border-color: {success};
            }}

            QPushButton#RowAction[actionRole="renew"] {{
                background: {row_renew_bg};
                color: {row_renew_fg};
                border-color: {cyan};
            }}
            QPushButton#RowAction[actionRole="renew"]:hover {{
                background: {cyan_hover};
                color: #FFFFFF;
                border-color: {cyan_hover};
            }}

            QPushButton#RowAction[actionRole="inspect"] {{
                background: {row_inspect_bg};
                color: {row_inspect_fg};
                border-color: {indigo};
            }}
            QPushButton#RowAction[actionRole="inspect"]:hover {{
                background: {indigo};
                color: #FFFFFF;
                border-color: {indigo};
            }}

            QPushButton#RowAction:disabled {{
                color: {row_disabled_fg};
                background: {row_disabled_bg};
                border-color: {row_disabled_border};
            }}

            QPushButton#ViewAllButton {{
                background: {c['primary_soft']};
                color: {primary};
                border: 1px solid {rgba_color(primary, 0.45)};
                border-radius: 7px;
                padding: 0px 10px;
                min-height: 23px;
                max-height: 23px;
                font-size: 10px;
                font-weight: 700;
            }}

            QPushButton#ViewAllButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {primary},
                    stop:1 {indigo}
                );
                color: #FFFFFF;
                border-color: {primary};
            }}
        """)

        for card in self.metric_widgets.values():
            card.apply_style()
        self.analytics_widget.update()
        if hasattr(self, "_activity_records") and self._activity_records:
            self._render_activity_table()

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

    def _apply_activity_table_columns(self, compact: bool):
        if compact == self._activity_table_compact:
            return
        self._activity_table_compact = compact
        table_header = self.activity_table.horizontalHeader()
        if compact:
            table_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            for column, width in (
                (0, 114), (1, 60), (2, 165), (3, 155), (4, 88), (5, 118), (6, 200)
            ):
                self.activity_table.setColumnWidth(column, width)
        else:
            table_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            table_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            for column, width in (
                (0, 114), (1, 60), (4, 86), (5, 118), (6, 206)
            ):
                self.activity_table.setColumnWidth(column, width)

    def _reflow_layout(self):
        if not hasattr(self, "tiles_grid"):
            return
        sb_w = (
            self.dashboard_scroll.verticalScrollBar().width()
            if self.dashboard_scroll.verticalScrollBar().isVisible()
            else 0
        )
        avail_w = max(320, self.width() - sb_w) if self.width() > 0 else 1080
        margin = 12 if avail_w < 840 else 16
        self.main_layout.setContentsMargins(margin, 6, margin, 40)

        header_stacked = avail_w < 740
        if header_stacked != self._header_stacked and hasattr(self, "dashboard_header_layout"):
            self._header_stacked = header_stacked
            self.dashboard_header_layout.removeWidget(self.header_actions_host)
            if header_stacked:
                self.dashboard_header_layout.addWidget(
                    self.header_actions_host, 1, 0, Qt.AlignmentFlag.AlignLeft
                )
            else:
                self.dashboard_header_layout.addWidget(
                    self.header_actions_host,
                    0,
                    1,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                )

        metric_cols = 4 if avail_w >= 920 else (2 if avail_w >= 540 else 1)
        if metric_cols != self._metrics_columns:
            self._metrics_columns = metric_cols
            for col in range(4):
                self.tiles_grid.setColumnStretch(col, 1 if col < metric_cols else 0)
            for row in range(4):
                self.tiles_grid.setRowMinimumHeight(
                    row, 74 if row * metric_cols < len(self._metric_order) else 0
                )
            for idx, key in enumerate(self._metric_order):
                card = self.metric_widgets.get(key)
                if card is not None:
                    self.tiles_grid.addWidget(card, idx // metric_cols, idx % metric_cols)

        middle_stacked = avail_w < 920
        if middle_stacked != self._middle_stacked:
            self._middle_stacked = middle_stacked
            if middle_stacked:
                self.middle_layout.addWidget(self.analytics_panel, 0, 0)
                self.middle_layout.addWidget(self.express_panel, 1, 0)
                self.middle_layout.setColumnStretch(0, 1)
                self.middle_layout.setColumnStretch(1, 0)
            else:
                self.middle_layout.addWidget(self.analytics_panel, 0, 0)
                self.middle_layout.addWidget(self.express_panel, 0, 1)
                self.middle_layout.setColumnStretch(0, 13)
                self.middle_layout.setColumnStretch(1, 7)

        est_analytics_w = (
            avail_w - (margin * 2) - 24
            if middle_stacked
            else int((avail_w - (margin * 2) - 36) * 0.65)
        )
        stacked_chart = est_analytics_w < 470
        self.analytics_widget.setMinimumHeight(300 if stacked_chart else 150)
        self.analytics_panel.setMinimumHeight(320 if stacked_chart else 156)
        self.express_panel.setMinimumHeight(156)

        self._reflow_activity_header(inline=(avail_w >= 860))

        est_table_w = avail_w - (margin * 2) - 20
        self._apply_activity_table_columns(compact=(est_table_w < 620))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow_layout()

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
        dialog.data_updated.connect(self.refresh_dashboard)
        dialog.exec()
        self.refresh_dashboard()

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

            recent_logs = list(logs or [])[:300]
            log_ids = [
                record[0] for record in recent_logs
                if record and len(record) >= 8
            ]
            renewal_meta = self.db.get_loan_renewal_meta(log_ids)
            max_renewals = self.db.get_max_renewals()

            self._activity_records = []
            today = datetime.date.today().isoformat()
            for record in recent_logs:
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

                renewal_count, last_renewed_at = renewal_meta.get(
                    int(log_id), (0, "")
                )

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
                    "renewal_count": int(renewal_count),
                    "last_renewed_at": safe_text(last_renewed_at),
                    "max_renewals": int(max_renewals),
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
        elif self._activity_filter == "Renewed":
            records = [
                item for item in self._activity_records
                if int(item.get("renewal_count", 0)) > 0
            ]
        else:
            records = self._activity_records

        self.activity_table.setRowCount(len(records))
        self.activity_empty_hint.setVisible(len(records) == 0)
        for row_index, item in enumerate(records):
            renewal_count = int(item.get("renewal_count", 0))
            max_renewals = int(item.get("max_renewals", 0))
            due_display = item["due_date"] or "—"
            if renewal_count > 0 and item["due_date"]:
                due_display = f"{item['due_date']}  (↻{renewal_count})"

            values = (
                item["display_date"],
                item["book_id"],
                item["book_title"],
                f"{item['user_name']} ({item['user_id']})",
                due_display,
            )
            for column, value in enumerate(values):
                actual_column = column if column < 4 else column + 1
                table_item = QTableWidgetItem(safe_text(value) or "—")
                if actual_column == 5 and renewal_count > 0:
                    last_r = item.get("last_renewed_at") or "Recorded"
                    table_item.setToolTip(
                        f"Due Date: {item['due_date'] or '—'}\n"
                        f"Renewals Used: {renewal_count}"
                        + (f" / {max_renewals}" if max_renewals > 0 else " (Unlimited)")
                        + f"\nLast Renewed: {last_r}"
                    )
                else:
                    table_item.setToolTip(safe_text(value) or "—")
                if actual_column == 0:
                    table_item.setData(
                        Qt.ItemDataRole.UserRole,
                        item["record"],
                    )
                self.activity_table.setItem(
                    row_index, actual_column, table_item
                )

            colors = get_theme_colors()
            badge_palette = (
                STATUS_BADGE_COLORS
                if colors.get("is_dark", True)
                else STATUS_BADGE_COLORS_LIGHT
            )
            badge_background, status_color, badge_border = badge_palette.get(
                item["status"],
                badge_palette["ISSUED"],
            )
            badge = QLabel(item["status"].title())
            badge.setObjectName("StatusBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"color: {status_color}; background: {badge_background};"
                f" border: 1px solid {badge_border}; border-radius: 9px;"
                f" padding: 1px 6px; margin: 6px 2px;"
                f" font-size: 10px; font-weight: 800;"
            )
            self.activity_table.setCellWidget(row_index, 4, badge)

            actions = QWidget()
            actions.setStyleSheet("background: transparent;")
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(3, 0, 3, 0)
            actions_layout.setSpacing(4)

            is_active = item["status"] in ("ISSUED", "DUE TODAY", "OVERDUE")

            return_button = QPushButton("Return")
            return_button.setObjectName("RowAction")
            return_button.setProperty("actionRole", "return")
            return_button.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            return_button.setFixedHeight(24)
            return_button.setCursor(Qt.CursorShape.PointingHandCursor)
            return_button.setEnabled(is_active)
            return_button.clicked.connect(
                lambda _checked=False, selected=item:
                self.return_activity_record(selected)
            )
            actions_layout.addWidget(return_button, 10, Qt.AlignmentFlag.AlignVCenter)

            renew_label = "Renew"
            if renewal_count > 0:
                renew_label = (
                    f"Renew ({renewal_count}/{max_renewals})"
                    if max_renewals > 0
                    else f"Renew ({renewal_count})"
                )
            renew_button = QPushButton(renew_label)
            renew_button.setObjectName("RowAction")
            renew_button.setProperty("actionRole", "renew")
            renew_button.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            renew_button.setFixedHeight(24)
            renew_button.setCursor(Qt.CursorShape.PointingHandCursor)
            renew_button.setEnabled(is_active)
            if not is_active:
                renew_button.setToolTip(
                    "Returned loans cannot be renewed."
                )
            elif max_renewals > 0 and renewal_count >= max_renewals:
                renew_button.setToolTip(
                    f"Renewal quota reached ({renewal_count}/{max_renewals}). "
                    "Click to inspect details or apply Librarian Override."
                )
            else:
                remaining = (
                    f"{max_renewals - renewal_count} remaining"
                    if max_renewals > 0
                    else "Unlimited"
                )
                renew_button.setToolTip(
                    f"Renew loan #{item['log_id']} ({remaining})"
                )
            renew_button.clicked.connect(
                lambda _checked=False, selected=item:
                self.renew_activity_record(selected)
            )
            renew_stretch = 14 if renewal_count > 0 else 10
            actions_layout.addWidget(renew_button, renew_stretch, Qt.AlignmentFlag.AlignVCenter)

            inspect_button = QPushButton("Inspect")
            inspect_button.setObjectName("RowAction")
            inspect_button.setProperty("actionRole", "inspect")
            inspect_button.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            inspect_button.setFixedHeight(24)
            inspect_button.setCursor(Qt.CursorShape.PointingHandCursor)
            inspect_button.clicked.connect(
                lambda _checked=False, selected=item:
                self.inspect_activity_record(selected)
            )
            actions_layout.addWidget(inspect_button, 11, Qt.AlignmentFlag.AlignVCenter)
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
            role_name = safe_text(user[3] if len(user) > 3 else "Student") or "Student"
            try:
                policy = self.db.get_loan_policy(role_name)
                max_books = int(policy.get("max_books", 3))
                default_days = int(policy.get("default_days", 14))
                quota_text = (
                    f"{held}/{max_books} held"
                    if max_books > 0
                    else f"{held} held"
                )
                policy_text = f" · {quota_text} · {default_days}d term"
            except Exception:
                policy_text = f" · {held} book(s) currently held"
            self.express_user_preview.setText(
                f"{safe_text(user[1])} ({role_name}){policy_text}"
            )
            user_match_state = "ok"
        elif user_id:
            self.express_user_preview.setText(
                "Member ID not found in the library records."
            )
            user_match_state = "warn"
        else:
            self.express_user_preview.setText(
                "Enter a registered member ID to preview eligibility."
            )
            user_match_state = "idle"
        self.express_user_preview.setProperty("matchState", user_match_state)
        self.express_user_preview.style().unpolish(self.express_user_preview)
        self.express_user_preview.style().polish(self.express_user_preview)

        active_loan_id = None
        if user and book:
            try:
                active_loan_id = self.db.get_active_loan_id(
                    safe_text(book[0]), safe_text(user[0])
                )
            except Exception:
                active_loan_id = None

        if book:
            available = int(book[5] or 0)
            availability_text = (
                f"{available} copy(s) available"
                if available > 0
                else "No copies available"
            )
            if active_loan_id is not None:
                availability_text += f" · Active loan #{active_loan_id} ready to renew/return"
            self.express_book_preview.setText(
                f"{safe_text(book[1])} · {availability_text}"
            )
            book_match_state = "ok" if (available > 0 or active_loan_id is not None) else "warn"
        elif book_id:
            self.express_book_preview.setText(
                "Book ID not found in the catalog."
            )
            book_match_state = "warn"
        else:
            self.express_book_preview.setText(
                "Enter a book ID to check title and availability."
            )
            book_match_state = "idle"
        self.express_book_preview.setProperty("matchState", book_match_state)
        self.express_book_preview.style().unpolish(self.express_book_preview)
        self.express_book_preview.style().polish(self.express_book_preview)

        can_transact = bool(user and book)
        self.instant_issue_button.setEnabled(
            can_transact and int(book[5] or 0) > 0
        )
        self.instant_renew_button.setEnabled(active_loan_id is not None)
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

    def _set_express_status(self, message, success=None):
        text = safe_text(message).strip()
        self.express_status_label.setText(text)
        if success is not None:
            self.express_status_label.setProperty("success", bool(success))
            self.express_status_label.style().unpolish(self.express_status_label)
            self.express_status_label.style().polish(self.express_status_label)
        self.express_status_label.setVisible(bool(text))

    def instant_issue_book(self):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user = self._users_by_id.get(user_id.casefold())
        book = self._books_by_id.get(book_id.casefold())
        if not user_id or not book_id or not user or not book:
            self._set_express_status(
                "Enter a registered member ID and a registered book ID.",
                success=False,
            )
            return

        try:
            success, message = self.db.issue_book(
                safe_text(book[0]),
                safe_text(user[0]),
            )
            self._set_express_status(str(message), success=bool(success))
            self.refresh_dashboard()
            if success:
                self.express_book_input.clear()
        except Exception as error:
            self._set_express_status(f"Issue failed: {error}", success=False)

    def instant_renew_book(self):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user = self._users_by_id.get(user_id.casefold())
        book = self._books_by_id.get(book_id.casefold())
        if not user_id or not book_id or not user or not book:
            self._set_express_status(
                "Enter a registered member ID and a registered book ID.",
                success=False,
            )
            return

        loan_id = self.db.get_active_loan_id(
            safe_text(book[0]), safe_text(user[0])
        )
        if loan_id is None:
            self._set_express_status(
                f"No active loan found for Book ID '{safe_text(book[0])}' "
                f"and Member ID '{safe_text(user[0])}'.",
                success=False,
            )
            return

        dialog = RenewLoanDialog(self.db, loan_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_express_status(
                dialog.result_message or f"Loan #{loan_id} renewed.",
                success=True,
            )
            self.refresh_dashboard()
            self.express_book_input.clear()

    def instant_return_book(self):
        user_id = self.express_user_input.text().strip()
        book_id = self.express_book_input.text().strip()
        user = self._users_by_id.get(user_id.casefold())
        book = self._books_by_id.get(book_id.casefold())
        if not user_id or not book_id or not user or not book:
            self._set_express_status(
                "Enter a registered member ID and a registered book ID.",
                success=False,
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
            self._set_express_status(result, success=bool(success))
            self.refresh_dashboard()
            if success:
                self.express_book_input.clear()
        except Exception as error:
            self._set_express_status(f"Return failed: {error}", success=False)

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
        renewal_count = int(item.get("renewal_count", 0))
        max_renewals = int(item.get("max_renewals", 0))
        quota_str = (
            f"{renewal_count} / {max_renewals}"
            if max_renewals > 0
            else f"{renewal_count} (Unlimited)"
        )
        history = self.db.get_renewal_history(item["log_id"])
        if history:
            history_lines = "\n".join(
                f"• {h['renewed_at']}: {h['previous_due_date']} → "
                f"{h['new_due_date']} (+{h['extended_days']}d"
                + (
                    f", Fine ₹{h['fine_assessed']:.2f} {h['fine_action'].title()}"
                    if float(h.get("fine_assessed") or 0) > 0
                    else ""
                )
                + (f", {h['notes']}" if h.get("notes") else "")
                + ")"
                for h in history[:5]
            )
        else:
            history_lines = "None"

        fine_val = float(item["fine"] or 0)
        settled, fine_action, settled_at, _fine_note = (
            self.db.get_loan_fine_settlement_meta([item["log_id"]]).get(
                int(item["log_id"]), (False, "", "", "")
            )
        )
        if fine_val <= 0:
            fine_text = "₹0.00"
        elif settled:
            tag = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
            fine_text = f"₹{fine_val:.2f} ({tag}" + (f" · {settled_at}" if settled_at else "") + ")"
        else:
            fine_text = f"₹{fine_val:.2f} (Pending)"

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
            ("Renewals Used", quota_str),
            ("Last Renewed", item.get("last_renewed_at") or "—"),
            ("Fine Balance", fine_text),
            ("Renewal History", history_lines),
        ]
        is_active = item["status"] in ("ISSUED", "DUE TODAY", "OVERDUE")
        dialog = ActivityDetailDialog(
            "Transaction",
            item["book_title"],
            f"{item['user_name']} ({item['user_id']})",
            item["display_date"],
            self,
            details=details,
            dialog_title=f"Transaction #{item['log_id']}",
            action_label="🔄 Renew Loan" if is_active else None,
            action_callback=(
                (lambda selected=item: self.renew_activity_record(selected))
                if is_active
                else None
            ),
        )
        dialog.exec()

    def renew_activity_record(self, item):
        try:
            dialog = RenewLoanDialog(self.db, item["log_id"], parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                details = dialog.result_details or {}
                new_due = details.get("new_due_date", "")
                r_count = details.get("renewal_count", 1)
                max_r = details.get("max_renewals", 0)
                quota = f"{r_count}/{max_r}" if max_r else str(r_count)
                fine_info = ""
                if float(details.get("accrued_fine") or 0) > 0:
                    fine_info = (
                        f"\nOverdue Fine: ₹{float(details['accrued_fine']):.2f} "
                        f"({str(details.get('fine_action', 'CARRY')).title()})"
                    )
                QMessageBox.information(
                    self,
                    "Loan Renewed",
                    f"{item['book_title']} ({item['book_id']}) renewed.\n"
                    f"New Due Date: {new_due}\n"
                    f"Renewals Used: {quota}{fine_info}",
                )
                self.refresh_dashboard()
        except Exception as error:
            QMessageBox.critical(
                self, "Renewal Error", str(error)
            )

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
            dialog = PendingFinesDialog(self.db, self)
            dialog.data_updated.connect(self.refresh_dashboard)
            dialog.exec()
            self.refresh_dashboard()
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

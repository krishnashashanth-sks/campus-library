
import csv
from datetime import datetime
from collections import defaultdict

from PyQt6.QtCore import Qt, QDate, pyqtSignal, QMargins, QSize
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QPushButton,
    QDateEdit,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QPieSeries,
    QBarSet,
    QBarSeries,
    QBarCategoryAxis,
    QValueAxis,
)
from ui_responsive import FlowLayout, configure_wrapped_label
from utils import rgba_color


# ============================================================
# INTERACTIVE KPI CARD
# ============================================================

class InteractiveStatCard(QFrame):

    card_activated = pyqtSignal(str)

    def __init__(
        self,
        metric_key,
        title,
        value,
        subtitle,
        accent,
        parent=None,
    ):
        super().__init__(parent)

        self.metric_key = metric_key
        self.accent = accent
        self.selected = False

        self.colors = {
            "surface": "#111C2E",
            "surface_alt": "#17243A",
            "border": "#293B55",
            "text": "#E8EEF8",
            "muted": "#94A3B8",
        }

        self.setObjectName("StatCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(0)
        self.setMinimumHeight(72)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 6, 11, 6)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.title_label.setMinimumWidth(0)
        self.title_label.setWordWrap(True)

        top.addWidget(self.title_label, 1)

        self.indicator = QLabel("VIEW")
        self.indicator.setObjectName("CardIndicator")
        self.indicator.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignVCenter
        )

        top.addWidget(self.indicator)
        layout.addLayout(top)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("CardValue")
        self.value_label.setMinimumWidth(0)
        self.value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("CardSubtitle")
        self.subtitle_label.setMinimumWidth(0)
        self.subtitle_label.setWordWrap(True)

        layout.addWidget(self.subtitle_label)
        layout.addStretch()

        self.set_theme_style()

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())

    def set_theme_style(self):
        is_dark = QColor(self.colors.get("window", "#090E1A")).lightness() < 128
        border = (
            self.accent
            if self.selected
            else rgba_color(self.accent, 0.52 if is_dark else 0.65)
        )
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
        badge_bg = self.accent if self.selected else rgba_color(
            self.accent, 0.18 if is_dark else 0.24
        )
        badge_fg = "#FFFFFF" if self.selected else self.accent
        badge_border = self.accent if self.selected else rgba_color(
            self.accent, 0.40 if is_dark else 0.60
        )

        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_start}, stop:1 {bg_end}
                );
                border: {2 if self.selected else 1}px solid {border};
                border-left: 5px solid {self.accent};
                border-radius: 11px;
            }}

            QFrame#StatCard:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {hover_start}, stop:1 {hover_end}
                );
                border: 2px solid {self.accent};
                border-left: 5px solid {self.accent};
            }}

            QLabel#CardTitle {{
                color: {self.colors["muted"]};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.6px;
                border: none;
                background: transparent;
            }}

            QLabel#CardValue {{
                color: {self.accent};
                font-size: 20px;
                font-weight: 800;
                border: none;
                background: transparent;
            }}

            QLabel#CardSubtitle {{
                color: {self.colors["muted"]};
                font-size: 10px;
                font-weight: 600;
                border: none;
                background: transparent;
            }}

            QLabel#CardIndicator {{
                color: {badge_fg};
                background-color: {badge_bg};
                border: 1px solid {badge_border};
                border-radius: 9px;
                padding: 2px 6px;
                font-size: 9px;
                font-weight: 800;
            }}
        """)

        self.indicator.setText(
            "● ACTIVE" if self.selected else "VIEW"
        )

    def set_accent(self, accent):
        if accent:
            self.accent = accent
            self.set_theme_style()

    def set_colors(self, colors):
        self.colors = {
            **self.colors,
            **colors,
        }
        self.set_theme_style()

    def update_style(self, active=False):
        self.selected = active
        self.set_theme_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_activated.emit(self.metric_key)

        super().mousePressEvent(event)


class _ResponsiveChartView(QChartView):
    """QChartView with balanced sizeHint so charts fit cleanly inside standard windows."""

    def minimumSizeHint(self):
        return QSize(200, 130)

    def sizeHint(self):
        return QSize(320, 170)


# ============================================================
# REPORTS AND ANALYTICS
# ============================================================

class ReportsView(QWidget):

    DEFAULT_COLORS = {
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
        "cyan": "#22D3EE",
        "cyan_hover": "#06B6D4",
        "teal": "#2DD4BF",
        "purple": "#A78BFA",
        "success": "#10B981",
        "success_hover": "#059669",
        "success_soft": "rgba(16, 185, 129, 0.16)",
        "warning": "#F59E0B",
        "warning_hover": "#D97706",
        "danger": "#F43F5E",
        "tooltip": "#182542",
    }

    ACCENTS = {
        "ISSUED": "#3B82F6",
        "RETURNED": "#10B981",
        "RENEWED": "#22D3EE",
        "ACTIVE": "#A78BFA",
        "FINES": "#F59E0B",
    }

    def __init__(self, db):
        super().__init__()

        self.db = db

        self.setObjectName("ReportsView")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        self.filtered_rows = []
        self.all_rows = []
        self.current_metric = "ISSUED"
        self._cards_columns = None
        self._graph_header_stacked = None
        self._card_order = ["ISSUED", "RETURNED", "RENEWED", "ACTIVE", "FINES"]

        self.stats_summary = {
            "issued": 0,
            "returned": 0,
            "renewed": 0,
            "renewed_days": 0,
            "unique_renewed": 0,
            "active": 0,
            "overdue": 0,
            "fines": 0.0,
            "fines_collected": 0.0,
            "fines_pending": 0.0,
            "fines_waived": 0.0,
        }

        self.daily_stats = defaultdict(
            lambda: {
                "issued": 0,
                "returned": 0,
                "renewed": 0,
                "fines": 0.0,
            }
        )

        self.colors = self.DEFAULT_COLORS.copy()
        self.theme_manager = self._find_theme_manager()

        self._build_ui()
        self._connect_theme()
        self.apply_theme()
        self.load_analytics()

    # --------------------------------------------------------
    # THEME MANAGER
    # --------------------------------------------------------

    def _find_theme_manager(self):
        app = QApplication.instance()

        manager = getattr(app, "theme_manager", None)

        if manager is not None:
            return manager

        parent = self.parent()

        while parent is not None:
            manager = getattr(parent, "theme_manager", None)

            if manager is not None:
                return manager

            parent = parent.parent()

        return None

    def _connect_theme(self):
        if self.theme_manager is not None:
            try:
                self.theme_manager.themeChanged.connect(
                    self._on_theme_changed
                )
            except (AttributeError, TypeError):
                pass

    def _on_theme_changed(self, theme=None):
        self.apply_theme()

    def apply_theme(self):
        manager = self.theme_manager

        if manager is not None:
            try:
                active = manager.get_active_theme()
                theme_colors = manager.COLORS.get(active, {})

                self.colors = {
                    **self.DEFAULT_COLORS,
                    **theme_colors,
                }

            except (AttributeError, TypeError):
                self.colors = self.DEFAULT_COLORS.copy()

        else:
            self.colors = self.DEFAULT_COLORS.copy()

        c = self.colors
        self.accents = {
            "ISSUED": c["primary"],
            "RETURNED": c["success"],
            "RENEWED": c["cyan"],
            "ACTIVE": c["purple"],
            "FINES": c["warning"],
        }

        self.setStyleSheet(f"""
            QWidget#ReportsView {{
                background: {c["window"]};
                color: {c["text"]};
            }}

            QWidget#ReportsScrollContent {{
                background: transparent;
            }}

            QFrame#ReportHeader {{
                background: transparent;
                border: none;
            }}

            QFrame#ControlPanel {{
                background: {c["surface"]};
                border: 1.5px solid {c["border"]};
                border-left: 4px solid {c["indigo"]};
                border-radius: 12px;
            }}

            QFrame#GraphField {{
                background: {c["surface"]};
                border: 1.5px solid {c["border"]};
                border-top: 3px solid {c["primary"]};
                border-radius: 14px;
            }}

            QFrame#PanelSeparator {{
                background: {c["border_bright"]};
                max-height: 1px;
                border: none;
            }}

            QLabel#PageTitle {{
                color: {c["text"]};
                font-size: 23px;
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#PageSubtitle {{
                color: {c["muted"]};
                font-size: 12px;
                background: transparent;
                border: none;
            }}

            QLabel#SectionTitle {{
                color: {c["primary"]};
                font-size: 15px;
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#SectionSubtitle {{
                color: {c["muted"]};
                font-size: 11px;
                background: transparent;
                border: none;
            }}

            QLabel#ControlLabel {{
                color: {c["muted"]};
                font-size: 11px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#Readout {{
                color: {c["primary"]};
                background: {c["primary_soft"]};
                border: 1px solid {rgba_color(c["primary"], 0.38)};
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
            }}

            QDateEdit {{
                background: {c["input"]};
                color: {c["text"]};
                border: 1.5px solid {c["border"]};
                border-radius: 8px;
                padding: 5px 7px;
                min-width: 86px;
                font-size: 12px;
            }}

            QDateEdit:focus {{
                border: 1.5px solid {c["primary"]};
            }}

            QDateEdit::drop-down {{
                border: none;
                width: 24px;
            }}

            QPushButton {{
                border-radius: 8px;
                padding: 6px 11px;
                font-size: 11px;
                font-weight: 700;
            }}

            QPushButton#PresetBtn {{
                background: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
            }}

            QPushButton#PresetBtn:hover {{
                background: {c["surface_elevated"]};
                color: {c["text"]};
                border: 1px solid {c["primary"]};
            }}

            QPushButton#PresetBtn:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["cyan"]}, stop:1 {c["primary"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["cyan"]};
            }}

            QPushButton#PrimaryBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["primary"]};
            }}

            QPushButton#PrimaryBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary_hover"]}, stop:1 {c["indigo_hover"]}
                );
            }}

            QPushButton#ExportBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["success"]}, stop:1 {c["teal"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["success"]};
            }}

            QPushButton#ExportBtn:hover {{
                background: {c["success_hover"]};
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}
        """)

        for key, card in getattr(self, "cards", {}).items():
            card.accent = self.accents.get(key, card.accent)
            card.set_colors(self.colors)

        if hasattr(self, "chart_view"):
            self._render_current_chart()

    # --------------------------------------------------------
    # USER INTERFACE
    # --------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 40)
        main_layout.setSpacing(8)
        self.main_layout = main_layout

        header = QFrame()
        header.setObjectName("ReportHeader")

        title_box = QVBoxLayout(header)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)

        title = QLabel("Library Analytics")
        title.setObjectName("PageTitle")
        configure_wrapped_label(title)

        subtitle = QLabel(
            "Circulation performance, lending trends and financial reports"
        )
        subtitle.setObjectName("PageSubtitle")
        configure_wrapped_label(subtitle)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        main_layout.addWidget(header)

        self._build_filter_panel(main_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.content = QWidget()
        self.content.setObjectName("ReportsScrollContent")
        self.content.setMinimumWidth(0)

        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(6)

        self._build_stat_cards()
        self._build_graph_panel()

        self.scroll_area.setWidget(self.content)
        main_layout.addWidget(self.scroll_area, 1)
        self._reflow_layout()

    def _build_filter_panel(self, parent_layout):
        panel = QFrame()
        panel.setObjectName("ControlPanel")
        panel.setMinimumWidth(0)

        layout = FlowLayout(panel, margin=8, h_spacing=7, v_spacing=6)

        from_pair = QWidget()
        from_layout = QHBoxLayout(from_pair)
        from_layout.setContentsMargins(0, 0, 0, 0)
        from_layout.setSpacing(6)
        from_label = QLabel("FROM")
        from_label.setObjectName("ControlLabel")
        from_layout.addWidget(from_label)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd MMM yyyy")
        self.start_date.setDate(
            QDate.currentDate().addDays(-29)
        )
        self.start_date.dateChanged.connect(
            self._on_date_changed
        )
        from_layout.addWidget(self.start_date)
        layout.addWidget(from_pair)

        to_pair = QWidget()
        to_layout = QHBoxLayout(to_pair)
        to_layout.setContentsMargins(0, 0, 0, 0)
        to_layout.setSpacing(6)
        to_label = QLabel("TO")
        to_label.setObjectName("ControlLabel")
        to_layout.addWidget(to_label)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd MMM yyyy")
        self.end_date.setDate(QDate.currentDate())
        self.end_date.dateChanged.connect(
            self._on_date_changed
        )
        to_layout.addWidget(self.end_date)
        layout.addWidget(to_pair)

        self.preset_buttons = {}
        for label, days in (
            ("7 DAYS", 7),
            ("30 DAYS", 30),
            ("90 DAYS", 90),
        ):
            button = QPushButton(label)
            button.setObjectName("PresetBtn")
            button.setCheckable(True)
            button.setChecked(days == 30)
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.clicked.connect(
                lambda checked=False, d=days: self.set_quick_range(d)
            )
            self.preset_buttons[days] = button
            layout.addWidget(button)

        all_button = QPushButton("ALL TIME")
        all_button.setObjectName("PresetBtn")
        all_button.setCheckable(True)
        all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        all_button.clicked.connect(self.set_all_time)
        self.preset_buttons[36500] = all_button
        layout.addWidget(all_button)

        refresh = QPushButton("↻  Refresh")
        refresh.setObjectName("PrimaryBtn")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.load_analytics)
        layout.addWidget(refresh)

        export = QPushButton("↓  Export CSV")
        export.setObjectName("ExportBtn")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.clicked.connect(self.export_csv)
        layout.addWidget(export)

        parent_layout.addWidget(panel)

    def _build_stat_cards(self):
        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(10)

        self.card_issued = InteractiveStatCard(
            "ISSUED",
            "BOOKS ISSUED",
            "0",
            "Books issued during selected period",
            self.ACCENTS["ISSUED"],
        )

        self.card_returned = InteractiveStatCard(
            "RETURNED",
            "BOOKS RETURNED",
            "0",
            "Returns completed in selected period",
            self.ACCENTS["RETURNED"],
        )

        self.card_renewed = InteractiveStatCard(
            "RENEWED",
            "LOAN RENEWALS",
            "0",
            "Extensions completed in period",
            self.ACCENTS["RENEWED"],
        )

        self.card_active = InteractiveStatCard(
            "ACTIVE",
            "ISSUED BOOKS",
            "0",
            "Books currently issued",
            self.ACCENTS["ACTIVE"],
        )

        self.card_fines = InteractiveStatCard(
            "FINES",
            "FINES RECORDED",
            "₹0.00",
            "Collected, waived & pending balance",
            self.ACCENTS["FINES"],
        )

        self.cards = {
            "ISSUED": self.card_issued,
            "RETURNED": self.card_returned,
            "RENEWED": self.card_renewed,
            "ACTIVE": self.card_active,
            "FINES": self.card_fines,
        }

        for index, card in enumerate(self.cards.values()):
            self.cards_grid.addWidget(card, 0, index)
            self.cards_grid.setColumnStretch(index, 1)
            card.card_activated.connect(
                self.switch_graph_view
            )
            card.set_colors(self.colors)

        self.content_layout.addLayout(self.cards_grid)

    def _build_graph_panel(self):
        self.graph_frame = QFrame()
        self.graph_frame.setObjectName("GraphField")
        self.graph_frame.setMinimumWidth(0)
        self.graph_frame.setMinimumHeight(182)

        self.graph_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self.graph_frame)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(5)

        self.graph_header_grid = QGridLayout()
        self.graph_header_grid.setHorizontalSpacing(10)
        self.graph_header_grid.setVerticalSpacing(6)

        self.graph_title_box = QWidget()
        self.graph_title_box.setMinimumWidth(0)
        title_box = QVBoxLayout(self.graph_title_box)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)

        self.graph_title = QLabel("Daily Books Issued")
        self.graph_title.setObjectName("SectionTitle")
        configure_wrapped_label(self.graph_title)

        self.graph_subtitle = QLabel(
            "Daily circulation activity across the selected date range"
        )
        self.graph_subtitle.setObjectName("SectionSubtitle")
        configure_wrapped_label(self.graph_subtitle)

        title_box.addWidget(self.graph_title)
        title_box.addWidget(self.graph_subtitle)

        self.hover_readout = QLabel(
            "Hover over a chart element to inspect its value"
        )
        self.hover_readout.setObjectName("Readout")
        configure_wrapped_label(self.hover_readout, expanding_width=False)
        self.hover_readout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.graph_header_grid.addWidget(self.graph_title_box, 0, 0)
        self.graph_header_grid.addWidget(self.hover_readout, 0, 1)
        self.graph_header_grid.setColumnStretch(0, 1)
        self.graph_header_grid.setColumnStretch(1, 0)
        layout.addLayout(self.graph_header_grid)

        separator = QFrame()
        separator.setObjectName("PanelSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

        self.chart_view = _ResponsiveChartView()
        self.chart_view.setMinimumWidth(0)
        self.chart_view.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        self.chart_view.setMinimumHeight(130)

        self.chart_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.chart_view.setStyleSheet(
            "background: transparent; border: none;"
        )

        layout.addWidget(self.chart_view, 1)
        self.content_layout.addWidget(self.graph_frame, 1)

    def _reflow_layout(self):
        if not hasattr(self, "cards_grid"):
            return
        avail_w = max(320, self.width()) if self.width() > 0 else 1080
        margin = 12 if avail_w < 840 else 16
        self.main_layout.setContentsMargins(margin, 6, margin, 40)

        cols = (
            5 if avail_w >= 960
            else (3 if avail_w >= 620 else (2 if avail_w >= 420 else 1))
        )
        if cols != self._cards_columns:
            self._cards_columns = cols
            for key in self._card_order:
                card = self.cards.get(key)
                if card is not None:
                    self.cards_grid.removeWidget(card)
            for col in range(5):
                self.cards_grid.setColumnStretch(col, 1 if col < cols else 0)
            for idx, key in enumerate(self._card_order):
                card = self.cards.get(key)
                if card is not None:
                    self.cards_grid.addWidget(card, idx // cols, idx % cols)

        stacked_header = avail_w < 700
        if stacked_header != self._graph_header_stacked:
            self._graph_header_stacked = stacked_header
            self.graph_header_grid.removeWidget(self.graph_title_box)
            self.graph_header_grid.removeWidget(self.hover_readout)
            if stacked_header:
                self.hover_readout.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                self.graph_header_grid.addWidget(self.graph_title_box, 0, 0)
                self.graph_header_grid.addWidget(self.hover_readout, 1, 0)
                self.graph_header_grid.setColumnStretch(0, 1)
                self.graph_header_grid.setColumnStretch(1, 0)
            else:
                self.hover_readout.setSizePolicy(
                    QSizePolicy.Policy.Preferred,
                    QSizePolicy.Policy.Preferred,
                )
                self.graph_header_grid.addWidget(self.graph_title_box, 0, 0)
                self.graph_header_grid.addWidget(self.hover_readout, 0, 1)
                self.graph_header_grid.setColumnStretch(0, 1)
                self.graph_header_grid.setColumnStretch(1, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow_layout()

    # --------------------------------------------------------
    # DATE FILTERS
    # --------------------------------------------------------

    def _on_date_changed(self):
        if self.start_date.date() > self.end_date.date():
            self.start_date.blockSignals(True)
            self.start_date.setDate(self.end_date.date())
            self.start_date.blockSignals(False)

        for button in getattr(self, "preset_buttons", {}).values():
            button.setChecked(False)

        self.load_analytics()

    def set_quick_range(self, days):
        today = QDate.currentDate()

        self.start_date.blockSignals(True)
        self.end_date.blockSignals(True)

        self.end_date.setDate(today)
        self.start_date.setDate(today.addDays(-days + 1))

        self.start_date.blockSignals(False)
        self.end_date.blockSignals(False)

        for preset_days, button in getattr(self, "preset_buttons", {}).items():
            button.setChecked(preset_days == days)

        self.load_analytics()

    def set_all_time(self):
        self.set_quick_range(36500)

    def load_data(self):
        """Compatibility method for the main window."""
        self.load_analytics()

    # --------------------------------------------------------
    # DATA PROCESSING
    # --------------------------------------------------------

    @staticmethod
    def _normalise_date(value):
        if value is None:
            return ""

        value = str(value).strip()

        if not value:
            return ""

        value = value[:10]

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def load_analytics(self):
        try:
            result = self.db.get_logs()

            if not result or not result[0]:
                self.all_rows = []
                self.filtered_rows = []
                self._reset_statistics()
                return

            rows = result[1] or []

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Report Loading Error",
                f"Unable to load circulation records:\n{exc}",
            )
            return

        start_str = self.start_date.date().toString("yyyy-MM-dd")
        end_str = self.end_date.date().toString("yyyy-MM-dd")
        today_str = datetime.now().strftime("%Y-%m-%d")

        self.all_rows = list(rows)
        self.filtered_rows = []
        self.daily_stats.clear()

        issued = 0
        returned = 0
        active = 0
        overdue = 0
        fines = 0.0

        for row in rows:
            if not row or len(row) < 8:
                continue

            checkout = self._normalise_date(row[3])
            due = self._normalise_date(row[4])
            return_date = self._normalise_date(row[5])

            try:
                fine = max(float(row[6] or 0), 0.0)
            except (TypeError, ValueError):
                fine = 0.0

            status = str(row[7] or "").strip().upper()

            checkout_in_range = (
                bool(checkout)
                and start_str <= checkout <= end_str
            )

            return_in_range = (
                status == "RETURNED"
                and bool(return_date)
                and start_str <= return_date <= end_str
            )

            if checkout_in_range:
                issued += 1
                self.daily_stats[checkout]["issued"] += 1

            if return_in_range:
                returned += 1
                fines += fine

                self.daily_stats[return_date]["returned"] += 1
                self.daily_stats[return_date]["fines"] += fine

            # Outstanding loans as of today, limited to loans
            # that existed by the selected end date.
            if (
                status == "ISSUED"
                and checkout
                and checkout <= end_str
            ):
                active += 1

                if due and due < today_str:
                    overdue += 1

            if checkout_in_range or return_in_range:
                self.filtered_rows.append(row)

        renewal_analytics = self.db.get_renewal_analytics(start_str, end_str)
        for day, count in (renewal_analytics.get("daily_renewals") or {}).items():
            self.daily_stats[day]["renewed"] += int(count or 0)

        fine_summary = self.db.get_fines_financial_summary(start_str, end_str)

        self.stats_summary = {
            "issued": issued,
            "returned": returned,
            "renewed": int(renewal_analytics.get("total_renewals", 0)),
            "renewed_days": int(renewal_analytics.get("total_extended_days", 0)),
            "unique_renewed": int(renewal_analytics.get("unique_loans_renewed", 0)),
            "active": active,
            "overdue": overdue,
            "fines": fines,
            "fines_collected": float(fine_summary.get("total_collected", 0.0)),
            "fines_pending": float(fine_summary.get("pending_fines", 0.0)),
            "fines_waived": float(fine_summary.get("waived_total", 0.0)),
        }

        self._update_cards()
        self._render_current_chart()

    def _reset_statistics(self):
        self.daily_stats.clear()
        self.filtered_rows = []

        self.stats_summary = {
            "issued": 0,
            "returned": 0,
            "renewed": 0,
            "renewed_days": 0,
            "unique_renewed": 0,
            "active": 0,
            "overdue": 0,
            "fines": 0.0,
            "fines_collected": 0.0,
            "fines_pending": 0.0,
            "fines_waived": 0.0,
        }

        self._update_cards()
        self._render_current_chart()

    def _update_cards(self):
        stats = self.stats_summary

        self.card_issued.value_label.setText(
            f"{stats['issued']:,}"
        )

        self.card_returned.value_label.setText(
            f"{stats['returned']:,}"
        )

        self.card_renewed.value_label.setText(
            f"{stats['renewed']:,}"
        )
        self.card_renewed.subtitle_label.setText(
            f"+{stats['renewed_days']:,} days across {stats['unique_renewed']:,} loan(s)"
        )

        self.card_active.value_label.setText(
            f"{stats['active']:,}"
        )

        self.card_active.subtitle_label.setText(
            f"{stats['overdue']:,} overdue · "
            f"{max(stats['active'] - stats['overdue'], 0):,} on time"
        )

        self.card_fines.value_label.setText(
            f"₹{stats['fines']:,.2f}"
        )
        self.card_fines.subtitle_label.setText(
            f"Collected ₹{stats['fines_collected']:,.2f} · "
            f"Pending ₹{stats['fines_pending']:,.2f}"
        )

    # --------------------------------------------------------
    # GRAPH SWITCHING
    # --------------------------------------------------------

    def switch_graph_view(self, metric_key):
        if metric_key not in self.cards:
            return

        self.current_metric = metric_key

        for key, card in self.cards.items():
            card.update_style(key == metric_key)

        self._render_current_chart()

    def _render_current_chart(self):
        if not hasattr(self, "chart_view"):
            return

        accents = getattr(self, "accents", self.ACCENTS)
        metric = self.current_metric

        if metric == "ISSUED":
            self.graph_title.setText("Daily Books Issued")
            self.graph_subtitle.setText(
                "Books issued on each date"
            )

            self.render_bar_chart(
                "issued",
                "Books Issued",
                accents.get("ISSUED", self.ACCENTS["ISSUED"]),
            )

        elif metric == "RETURNED":
            self.graph_title.setText("Daily Books Returned")
            self.graph_subtitle.setText(
                "Number of successfully completed returns"
            )

            self.render_bar_chart(
                "returned",
                "Books Returned",
                accents.get("RETURNED", self.ACCENTS["RETURNED"]),
            )

        elif metric == "RENEWED":
            stats = self.stats_summary
            self.graph_title.setText("Daily Loan Renewals")
            self.graph_subtitle.setText(
                f"{stats['renewed']:,} renewals totaling +{stats['renewed_days']:,} extension days"
            )

            self.render_bar_chart(
                "renewed",
                "Loan Renewals",
                accents.get("RENEWED", self.ACCENTS["RENEWED"]),
                unit_label="renewals",
            )

        elif metric == "ACTIVE":
            self.graph_title.setText(
                "Current Circulation Breakdown"
            )
            self.graph_subtitle.setText(
                "Issued and overdue books"
            )

            self.render_status_pie_chart()

        elif metric == "FINES":
            stats = self.stats_summary
            self.graph_title.setText("Daily Fine Recording & Settlements")
            self.graph_subtitle.setText(
                f"Recorded ₹{stats['fines']:,.2f} · "
                f"Collected ₹{stats['fines_collected']:,.2f} · "
                f"Waived ₹{stats['fines_waived']:,.2f} · "
                f"Pending ₹{stats['fines_pending']:,.2f}"
            )

            self.render_bar_chart(
                "fines",
                "Fines Recorded (₹)",
                accents.get("FINES", self.ACCENTS["FINES"]),
                is_currency=True,
            )

        for key, card in self.cards.items():
            card.update_style(key == metric)

    # --------------------------------------------------------
    # CHART ENGINE
    # --------------------------------------------------------

    def _create_base_chart(self):
        c = self.colors

        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(True)

        chart.setPlotAreaBackgroundBrush(
            QColor(c["input"])
        )

        chart.setMargins(QMargins(10, 6, 10, 6))

        chart.setAnimationOptions(
            QChart.AnimationOption.NoAnimation
        )

        chart.legend().setVisible(True)
        chart.legend().setLabelColor(
            QColor(c["text"])
        )

        chart.legend().setAlignment(
            Qt.AlignmentFlag.AlignBottom
        )

        font = QFont()
        font.setPointSize(10)
        chart.legend().setFont(font)

        return chart

    def render_bar_chart(
        self,
        stat_field,
        series_label,
        hex_color,
        is_currency=False,
        unit_label="books",
    ):
        chart = self._create_base_chart()

        active_days = sorted(
            day
            for day, values in self.daily_stats.items()
            if values[stat_field] > 0
        )

        # Show the most recent 14 active dates.
        display_days = active_days[-14:]

        if not display_days:
            empty_text = chart.setTitle(
                "No circulation activity found for this period"
            )
            chart.setTitleBrush(QColor(self.colors["muted"]))
            chart.setTitleFont(QFont("Segoe UI", 11))
            self.hover_readout.setText("No chart data available")
            self.chart_view.setChart(chart)
            return

        bar_set = QBarSet(series_label)
        base_color = QColor(hex_color)
        grad = QLinearGradient(0, 0, 0, 1)
        grad.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
        grad.setColorAt(0.0, base_color.lighter(118))
        grad.setColorAt(1.0, base_color.darker(115))
        bar_set.setBrush(QBrush(grad))
        bar_set.setBorderColor(base_color)

        categories = []
        maximum = 0.0

        for day in display_days:
            value = self.daily_stats[day][stat_field]

            bar_set.append(value)

            try:
                label = datetime.strptime(
                    day,
                    "%Y-%m-%d",
                ).strftime("%d %b")
            except ValueError:
                label = day

            categories.append(label)
            maximum = max(maximum, float(value))

        series = QBarSeries()
        series.append(bar_set)
        series.setBarWidth(0.62)

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(
            QColor(self.colors["text"])
        )
        axis_x.setGridLineVisible(False)
        axis_x.setLabelsAngle(-25)

        chart.addAxis(
            axis_x,
            Qt.AlignmentFlag.AlignBottom,
        )
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(
            0,
            max(
                maximum * 1.25,
                5 if not is_currency else 1,
            ),
        )

        if is_currency:
            axis_y.setLabelFormat("₹%.0f")
        else:
            axis_y.setLabelFormat("%.0f")
            axis_y.setTickType(
                QValueAxis.TickType.TicksDynamic
            )
            axis_y.setTickInterval(1)

        axis_y.setLabelsColor(
            QColor(self.colors["text"])
        )

        axis_y.setGridLinePen(
            QPen(
                QColor(self.colors["border"]),
                1,
                Qt.PenStyle.DashLine,
            )
        )

        chart.addAxis(
            axis_y,
            Qt.AlignmentFlag.AlignLeft,
        )
        series.attachAxis(axis_y)

        def on_hovered(status, index):
            if status and 0 <= index < len(display_days):
                day = display_days[index]
                value = self.daily_stats[day][stat_field]

                if is_currency:
                    formatted = f"₹{value:,.2f}"
                else:
                    formatted = f"{int(value):,} {unit_label}"

                self.hover_readout.setText(
                    f"{day}  |  {series_label}: {formatted}"
                )

            else:
                self.hover_readout.setText(
                    "Hover over a bar to inspect its value"
                )

        bar_set.hovered.connect(on_hovered)

        self.hover_readout.setText(
            "Hover over a bar to inspect its value"
        )

        self.chart_view.setChart(chart)

    def render_status_pie_chart(self):
        chart = self._create_base_chart()

        series = QPieSeries()
        series.setHoleSize(0.46)
        series.setPieSize(0.72)

        active = self.stats_summary["active"]
        overdue = self.stats_summary["overdue"]
        on_time = max(active - overdue, 0)

        accents = getattr(self, "accents", self.ACCENTS)
        values = [
            (
                "On-Time Books",
                on_time,
                accents.get("ISSUED", self.ACCENTS["ISSUED"]),
            ),
            (
                "Overdue Books",
                overdue,
                self.colors["danger"],
            ),
        ]

        total = sum(value for _, value, _ in values)

        if total == 0:
            empty = series.append("No Issued Books", 1)
            empty.setBrush(
                QColor(self.colors["border"])
            )
            empty.setLabelVisible(True)
            empty.setLabelColor(
                QColor(self.colors["muted"])
            )

        else:
            for label, value, color in values:
                if value <= 0:
                    continue

                pie_slice = series.append(
                    f"{label} ({value:,})",
                    value,
                )

                pie_slice.setBrush(QColor(color))
                pie_slice.setBorderColor(QColor(self.colors["surface"]))
                pie_slice.setBorderWidth(2)
                pie_slice.setLabelVisible(True)
                pie_slice.setLabelColor(
                    QColor(self.colors["text"])
                )

        def on_slice_hovered(pie_slice, state):
            if state:
                pie_slice.setExploded(True)

                self.hover_readout.setText(
                    f"{pie_slice.label()} · "
                    f"{pie_slice.percentage() * 100:.1f}%"
                )

            else:
                pie_slice.setExploded(False)

                self.hover_readout.setText(
                    "Hover over a segment to inspect its proportion"
                )

        series.hovered.connect(on_slice_hovered)

        chart.addSeries(series)
        chart.legend().setVisible(True)

        self.hover_readout.setText(
            "Hover over a segment to inspect its proportion"
        )

        self.chart_view.setChart(chart)

    # --------------------------------------------------------
    # CSV EXPORT
    # --------------------------------------------------------

    def export_csv(self):
        if not self.filtered_rows:
            QMessageBox.information(
                self,
                "No Records",
                "There are no circulation records in the selected date range.",
            )
            return

        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")

        default_name = (
            f"Library_Analytics_{start}_to_{end}.csv"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Library Analytics",
            default_name,
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
                newline="",
                encoding="utf-8-sig",
            ) as file:
                writer = csv.writer(file)

                writer.writerow([
                    "LIBRARY MANAGEMENT SYSTEM",
                    "CIRCULATION ANALYTICS REPORT",
                ])

                writer.writerow([
                    "Report Period",
                    start,
                    "to",
                    end,
                ])

                writer.writerow([
                    "Generated On",
                    datetime.now().strftime(
                        "%d-%m-%Y %H:%M:%S"
                    ),
                ])

                writer.writerow([])

                writer.writerow([
                    "Log ID",
                    "Book ID",
                    "User ID",
                    "Issue Date",
                    "Due Date",
                    "Return Date",
                    "Fine Amount (INR)",
                    "Status",
                    "Renewals",
                    "Fine Status",
                ])

                log_ids = [r[0] for r in self.filtered_rows if r]
                renewal_meta = self.db.get_loan_renewal_meta(log_ids)
                fine_meta = self.db.get_loan_fine_settlement_meta(log_ids)

                for row in self.filtered_rows:
                    lid = row[0]
                    r_count = (
                        renewal_meta.get(lid)
                        if lid in renewal_meta
                        else renewal_meta.get(str(lid), (0, ""))
                    )[0]
                    settled, f_act, _, _ = (
                        fine_meta.get(lid)
                        if lid in fine_meta
                        else fine_meta.get(str(lid), (False, "", "", ""))
                    )
                    f_val = float(row[6] or 0)
                    if f_val <= 0:
                        f_status = "No Fine"
                    elif settled:
                        f_status = "Waived" if str(f_act).upper() == "WAIVED" else "Paid"
                    else:
                        f_status = "Pending"
                    writer.writerow(list(row) + [r_count, f_status])

                writer.writerow([])
                writer.writerow(["REPORT SUMMARY"])

                writer.writerow([
                    "Books Issued",
                    self.stats_summary["issued"],
                ])

                writer.writerow([
                    "Books Returned",
                    self.stats_summary["returned"],
                ])

                writer.writerow([
                    "Loan Renewals",
                    self.stats_summary["renewed"],
                ])

                writer.writerow([
                    "Total Extended Days",
                    self.stats_summary["renewed_days"],
                ])

                writer.writerow([
                    "Issued Books",
                    self.stats_summary["active"],
                ])

                writer.writerow([
                    "Overdue Books",
                    self.stats_summary["overdue"],
                ])

                writer.writerow([
                    "Fines Recorded",
                    f"{self.stats_summary['fines']:.2f}",
                ])

                writer.writerow([
                    "Fines Collected (Payments)",
                    f"{self.stats_summary['fines_collected']:.2f}",
                ])

                writer.writerow([
                    "Fines Waived",
                    f"{self.stats_summary['fines_waived']:.2f}",
                ])

                writer.writerow([
                    "Pending Unpaid Fines",
                    f"{self.stats_summary['fines_pending']:.2f}",
                ])

            QMessageBox.information(
                self,
                "Export Successful",
                f"Report exported successfully.\n\n"
                f"Records: {len(self.filtered_rows)}\n"
                f"Location:\n{file_path}",
            )

        except (OSError, csv.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not export the report:\n{exc}",
            )

    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------

    def closeEvent(self, event):
        if self.theme_manager is not None:
            try:
                self.theme_manager.themeChanged.disconnect(
                    self._on_theme_changed
                )
            except (TypeError, RuntimeError):
                pass

        super().closeEvent(event)

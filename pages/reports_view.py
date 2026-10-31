
import csv
from datetime import datetime
from collections import defaultdict

from PyQt6.QtCore import Qt, QDate, pyqtSignal, QMargins
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
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
        self.setMinimumHeight(145)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 17, 19, 17)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.title_label.setWordWrap(True)

        top.addWidget(self.title_label, 1)

        self.indicator = QLabel("VIEW ANALYTICS")
        self.indicator.setObjectName("CardIndicator")
        self.indicator.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignVCenter
        )

        top.addWidget(self.indicator)
        layout.addLayout(top)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("CardValue")
        self.value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("CardSubtitle")
        self.subtitle_label.setWordWrap(True)

        layout.addWidget(self.subtitle_label)
        layout.addStretch()

        self.set_theme_style()

    def set_theme_style(self):
        border = (
            self.accent
            if self.selected
            else self.colors["border"]
        )

        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background: {self.colors["surface"]};
                border: 1px solid {border};
                border-left: 5px solid {self.accent};
                border-radius: 12px;
            }}

            QFrame#StatCard:hover {{
                background: {self.colors["surface_alt"]};
                border: 1px solid {self.accent};
                border-left: 5px solid {self.accent};
            }}

            QLabel#CardTitle {{
                color: {self.colors["muted"]};
                font-size: 12px;
                font-weight: 700;
                border: none;
                background: transparent;
            }}

            QLabel#CardValue {{
                color: {self.colors["text"]};
                font-size: 29px;
                font-weight: 800;
                border: none;
                background: transparent;
            }}

            QLabel#CardSubtitle {{
                color: {self.colors["muted"]};
                font-size: 11px;
                border: none;
                background: transparent;
            }}

            QLabel#CardIndicator {{
                color: {self.accent};
                font-size: 9px;
                font-weight: 800;
                border: none;
                background: transparent;
            }}
        """)

        self.indicator.setText(
            "● SELECTED" if self.selected else "VIEW ANALYTICS"
        )

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


# ============================================================
# REPORTS AND ANALYTICS
# ============================================================

class ReportsView(QWidget):

    DEFAULT_COLORS = {
        "window": "#0B1220",
        "surface": "#111C2E",
        "surface_alt": "#17243A",
        "input": "#0F1B2D",
        "border": "#293B55",
        "text": "#E8EEF8",
        "muted": "#94A3B8",
        "primary": "#3B82F6",
        "primary_hover": "#2563EB",
        "selection": "#1D4ED8",
        "success": "#16A34A",
        "warning": "#D97706",
        "danger": "#DC2626",
        "tooltip": "#17243A",
    }

    ACCENTS = {
        "ISSUED": "#3B82F6",
        "RETURNED": "#10B981",
        "ACTIVE": "#8B5CF6",
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

        self.stats_summary = {
            "issued": 0,
            "returned": 0,
            "active": 0,
            "overdue": 0,
            "fines": 0.0,
        }

        self.daily_stats = defaultdict(
            lambda: {
                "issued": 0,
                "returned": 0,
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
                border: 1px solid {c["border"]};
                border-radius: 12px;
            }}

            QFrame#GraphField {{
                background: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 14px;
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
                color: {c["text"]};
                font-size: 17px;
                font-weight: 700;
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
                background: {c["input"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: 600;
            }}

            QDateEdit {{
                background: {c["input"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 8px 10px;
                min-width: 115px;
                font-size: 12px;
            }}

            QDateEdit:focus {{
                border: 1px solid {c["primary"]};
            }}

            QDateEdit::drop-down {{
                border: none;
                width: 24px;
            }}

            QPushButton {{
                border-radius: 7px;
                padding: 9px 14px;
                font-size: 11px;
                font-weight: 700;
            }}

            QPushButton#PresetBtn {{
                background: {c["input"]};
                color: {c["muted"]};
                border: 1px solid {c["border"]};
            }}

            QPushButton#PresetBtn:hover {{
                background: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["primary"]};
            }}

            QPushButton#PrimaryBtn {{
                background: {c["primary"]};
                color: white;
                border: none;
            }}

            QPushButton#PrimaryBtn:hover {{
                background: {c["primary_hover"]};
            }}

            QPushButton#ExportBtn {{
                background: {c["success"]};
                color: white;
                border: none;
            }}

            QPushButton#ExportBtn:hover {{
                background: #15803D;
            }}

            QScrollArea {{
                background: transparent;
                border: none;
            }}

            QScrollBar:vertical {{
                background: {c["window"]};
                width: 9px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical {{
                background: {c["border"]};
                border-radius: 4px;
                min-height: 35px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {c["muted"]};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        for card in getattr(self, "cards", {}).values():
            card.set_colors(self.colors)

        if hasattr(self, "chart_view"):
            self._render_current_chart()

    # --------------------------------------------------------
    # USER INTERFACE
    # --------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("ReportHeader")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)

        title = QLabel("Library Analytics")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Circulation performance, lending trends and financial reports"
        )
        subtitle.setObjectName("PageSubtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header_layout.addLayout(title_box)
        header_layout.addStretch()

        main_layout.addWidget(header)

        self._build_filter_panel(main_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.content = QWidget()
        self.content.setObjectName("ReportsScrollContent")

        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 2, 8, 12)
        self.content_layout.setSpacing(18)

        self._build_stat_cards()
        self._build_graph_panel()

        self.scroll_area.setWidget(self.content)
        main_layout.addWidget(self.scroll_area, 1)

    def _build_filter_panel(self, parent_layout):
        panel = QFrame()
        panel.setObjectName("ControlPanel")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(9)

        from_label = QLabel("FROM")
        from_label.setObjectName("ControlLabel")
        layout.addWidget(from_label)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd MMM yyyy")
        self.start_date.setDate(
            QDate.currentDate().addDays(-29)
        )
        self.start_date.dateChanged.connect(
            self._on_date_changed
        )
        layout.addWidget(self.start_date)

        to_label = QLabel("TO")
        to_label.setObjectName("ControlLabel")
        layout.addWidget(to_label)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd MMM yyyy")
        self.end_date.setDate(QDate.currentDate())
        self.end_date.dateChanged.connect(
            self._on_date_changed
        )
        layout.addWidget(self.end_date)

        layout.addSpacing(7)

        for label, days in (
            ("7 DAYS", 7),
            ("30 DAYS", 30),
            ("90 DAYS", 90),
        ):
            button = QPushButton(label)
            button.setObjectName("PresetBtn")
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.clicked.connect(
                lambda checked=False, d=days: self.set_quick_range(d)
            )
            layout.addWidget(button)

        all_button = QPushButton("ALL TIME")
        all_button.setObjectName("PresetBtn")
        all_button.clicked.connect(self.set_all_time)
        layout.addWidget(all_button)

        layout.addStretch()

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
        grid = QGridLayout()
        grid.setSpacing(14)

        self.card_issued = InteractiveStatCard(
            "ISSUED",
            "BOOKS ISSUED",
            "0",
            "Loans started in selected period",
            self.ACCENTS["ISSUED"],
        )

        self.card_returned = InteractiveStatCard(
            "RETURNED",
            "BOOKS RETURNED",
            "0",
            "Returns completed in selected period",
            self.ACCENTS["RETURNED"],
        )

        self.card_active = InteractiveStatCard(
            "ACTIVE",
            "ACTIVE LOANS",
            "0",
            "Current outstanding loans",
            self.ACCENTS["ACTIVE"],
        )

        self.card_fines = InteractiveStatCard(
            "FINES",
            "FINES COLLECTED",
            "₹0.00",
            "Fines recorded for returned loans",
            self.ACCENTS["FINES"],
        )

        self.cards = {
            "ISSUED": self.card_issued,
            "RETURNED": self.card_returned,
            "ACTIVE": self.card_active,
            "FINES": self.card_fines,
        }

        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, index)
            card.card_activated.connect(
                self.switch_graph_view
            )
            card.set_colors(self.colors)

        self.content_layout.addLayout(grid)

    def _build_graph_panel(self):
        self.graph_frame = QFrame()
        self.graph_frame.setObjectName("GraphField")
        self.graph_frame.setMinimumHeight(590)

        self.graph_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self.graph_frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        self.graph_title = QLabel("Daily Books Issued")
        self.graph_title.setObjectName("SectionTitle")

        self.graph_subtitle = QLabel(
            "Daily circulation activity across the selected date range"
        )
        self.graph_subtitle.setObjectName("SectionSubtitle")

        title_box.addWidget(self.graph_title)
        title_box.addWidget(self.graph_subtitle)

        header.addLayout(title_box)
        header.addStretch()

        self.hover_readout = QLabel(
            "Hover over a chart element to inspect its value"
        )
        self.hover_readout.setObjectName("Readout")
        self.hover_readout.setMinimumWidth(260)
        self.hover_readout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        header.addWidget(self.hover_readout)
        layout.addLayout(header)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(
            f"background: {self.colors['border']}; max-height: 1px;"
        )
        layout.addWidget(separator)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        self.chart_view.setMinimumHeight(490)

        self.chart_view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.chart_view.setStyleSheet(
            "background: transparent; border: none;"
        )

        layout.addWidget(self.chart_view, 1)
        self.content_layout.addWidget(self.graph_frame, 1)

    # --------------------------------------------------------
    # DATE FILTERS
    # --------------------------------------------------------

    def _on_date_changed(self):
        if self.start_date.date() > self.end_date.date():
            self.start_date.blockSignals(True)
            self.start_date.setDate(self.end_date.date())
            self.start_date.blockSignals(False)

        self.load_analytics()

    def set_quick_range(self, days):
        today = QDate.currentDate()

        self.start_date.blockSignals(True)
        self.end_date.blockSignals(True)

        self.end_date.setDate(today)
        self.start_date.setDate(today.addDays(-days + 1))

        self.start_date.blockSignals(False)
        self.end_date.blockSignals(False)

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

        self.stats_summary = {
            "issued": issued,
            "returned": returned,
            "active": active,
            "overdue": overdue,
            "fines": fines,
        }

        self._update_cards()
        self._render_current_chart()

    def _reset_statistics(self):
        self.daily_stats.clear()
        self.filtered_rows = []

        self.stats_summary = {
            "issued": 0,
            "returned": 0,
            "active": 0,
            "overdue": 0,
            "fines": 0.0,
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

        metric = self.current_metric

        if metric == "ISSUED":
            self.graph_title.setText("Daily Books Issued")
            self.graph_subtitle.setText(
                "Number of loans started on each date"
            )

            self.render_bar_chart(
                "issued",
                "Books Issued",
                self.ACCENTS["ISSUED"],
            )

        elif metric == "RETURNED":
            self.graph_title.setText("Daily Books Returned")
            self.graph_subtitle.setText(
                "Number of successfully completed returns"
            )

            self.render_bar_chart(
                "returned",
                "Books Returned",
                self.ACCENTS["RETURNED"],
            )

        elif metric == "ACTIVE":
            self.graph_title.setText(
                "Current Circulation Breakdown"
            )
            self.graph_subtitle.setText(
                "Outstanding loans and overdue distribution"
            )

            self.render_status_pie_chart()

        elif metric == "FINES":
            self.graph_title.setText("Daily Fine Collection")
            self.graph_subtitle.setText(
                "Fine amounts recorded against returned loans"
            )

            self.render_bar_chart(
                "fines",
                "Fines Collected (₹)",
                self.ACCENTS["FINES"],
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

        chart.setMargins(QMargins(14, 12, 14, 12))

        chart.setAnimationOptions(
            QChart.AnimationOption.SeriesAnimations
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
        bar_set.setColor(QColor(hex_color))
        bar_set.setBorderColor(QColor(hex_color))

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
            QColor(self.colors["muted"])
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
            QColor(self.colors["muted"])
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
                    formatted = f"{int(value):,} books"

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
        series.setHoleSize(0.48)
        series.setPieSize(0.78)

        active = self.stats_summary["active"]
        overdue = self.stats_summary["overdue"]
        on_time = max(active - overdue, 0)

        values = [
            (
                "On-Time Loans",
                on_time,
                self.ACCENTS["ISSUED"],
            ),
            (
                "Overdue Loans",
                overdue,
                self.colors["danger"],
            ),
        ]

        total = sum(value for _, value, _ in values)

        if total == 0:
            empty = series.append("No Active Loans", 1)
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
                    "Checkout Date",
                    "Due Date",
                    "Return Date",
                    "Fine Amount (INR)",
                    "Status",
                ])

                for row in self.filtered_rows:
                    writer.writerow(row)

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
                    "Currently Active Loans",
                    self.stats_summary["active"],
                ])

                writer.writerow([
                    "Overdue Loans",
                    self.stats_summary["overdue"],
                ])

                writer.writerow([
                    "Fines Recorded",
                    f"{self.stats_summary['fines']:.2f}",
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

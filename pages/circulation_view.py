import csv
from datetime import datetime, date

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QSizePolicy, QFrame, QLabel,
    QMessageBox, QFormLayout, QMenu, QAbstractItemView,
    QFileDialog, QTabWidget, QSpacerItem, QInputDialog, QSplitter
)

from ui_responsive import (
    FlowLayout,
    configure_inspector_button,
    configure_inspector_form,
    configure_wrapped_label,
    make_scrollable_tab,
    sync_responsive_splitter,
)
from utils import clear_layout, rgba_color
from dialogs import IssueBookDialog, PendingFinesDialog, RenewLoanDialog, ReturnBookDialog


class ClickableMetricCard(QFrame):
    """Interactive KPI card."""

    def __init__(
        self, filter_key, title, value="0", subtitle="",
        accent="#3B82F6", on_click_callback=None, parent=None
    ):
        super().__init__(parent)

        self.filter_key = filter_key
        self.accent = accent
        self.on_click_callback = on_click_callback
        self.selected = False
        self.colors = {}

        self.setObjectName("MetricCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(60)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred
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

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setObjectName("MetricSubtitle")
        self.lbl_subtitle.setWordWrap(True)
        self.lbl_subtitle.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtitle)

        self.apply_card_style()

    def minimumSizeHint(self):
        return QSize(0, self.minimumHeight())

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.apply_card_style()

    def set_accent(self, accent, colors=None):
        if accent:
            self.accent = accent
        if colors is not None:
            self.colors = colors
        self.apply_card_style()

    def apply_card_style(self):
        c = self.colors
        is_dark = QColor(c.get("window", "#090E1A")).lightness() < 128

        muted = c.get("muted", "#94A3B8")
        text = c.get("text", "#F8FAFC")

        border_color = self.accent if self.selected else rgba_color(
            self.accent,
            0.52 if is_dark else 0.65,
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

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_start}, stop:1 {bg_end}
                );
                border: {2 if self.selected else 1}px solid {border_color};
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
                color: {muted};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.6px;
                background: transparent;
                border: none;
            }}
            QLabel#MetricValue {{
                color: {self.accent};
                font-size: 20px;
                font-weight: 800;
                background: transparent;
                border: none;
            }}
            QLabel#MetricSubtitle {{
                color: {text};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.on_click_callback
        ):
            self.on_click_callback(self.filter_key)

        super().mousePressEvent(event)


class CirculationView(QWidget):

    HEADERS = [
        "Log ID", "Book ID", "User ID", "Status",
        "Issue Date", "Due Date", "Return Date", "Fine"
    ]

    FILTERS = [
        ("ALL", "All Transactions"),
        ("ISSUED", "Issued Books"),
        ("DUE_TODAY", "Due Today"),
        ("OVERDUE", "Overdue"),
        ("RENEWED", "Renewed"),
        ("RETURNED_TODAY", "Returned Today"),
        ("RETURNED_HISTORY", "Return History"),
    ]

    def __init__(self, db):
        super().__init__()

        self.db = db
        self.setObjectName("CirculationView")

        self.all_logs = []
        self.filtered_logs = []
        self.renewal_meta = {}
        self.fine_meta = {}
        self.current_filter = "ALL"
        self.colors = {}
        self._metrics_columns = None
        self._header_compact = None
        self._toolbar_tier = None
        self._splitter_vertical = None
        self._table_compact = None
        self._page_compact = None
        self._filter_compact_mode = None
        self._control_center_expanded = True

        self._updating_table = False

        app = QApplication.instance()
        self.theme_manager = (
            getattr(app, "theme_manager", None) if app else None
        )

        self._build_ui()
        self._connect_theme_manager()
        self.apply_theme()
        self.load_circulation()

    # ---------------------------------------------------------
    # THEME
    # ---------------------------------------------------------

    def _connect_theme_manager(self):
        if self.theme_manager:
            try:
                self.theme_manager.themeChanged.connect(
                    self.apply_theme
                )
            except (AttributeError, TypeError, RuntimeError):
                pass

    def _get_colors(self):
        defaults = {
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
            "cyan_soft": "rgba(34, 211, 238, 0.16)",
            "teal": "#2DD4BF",
            "purple": "#A78BFA",
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
        }

        try:
            if self.theme_manager:
                active_theme = (
                    self.theme_manager.get_active_theme()
                )

                theme_colors = getattr(
                    self.theme_manager, "COLORS", {}
                ).get(active_theme, {})

                defaults.update(theme_colors)

        except Exception:
            pass

        return defaults

    def apply_theme(self, *_):
        self.colors = self._get_colors()
        c = self.colors

        self.setStyleSheet(f"""
            QWidget#CirculationView {{
                background-color: {c['window']};
                color: {c['text']};
                font-family: 'Segoe UI';
                font-size: 12px;
            }}

            QLabel#PageTitle {{
                color: {c['text']};
                font-size: 23px;
                font-weight: 800;
                background: transparent;
            }}

            QLabel#PageSubtitle {{
                color: {c['muted']};
                font-size: 12px;
                background: transparent;
            }}

            QFrame#CirculationToolbar,
            QFrame#CirculationFilterBar,
            QFrame#CirculationInspector {{
                background-color: {c['surface']};
                border: 1.5px solid {c['border']};
                border-radius: 11px;
            }}

            QFrame#CirculationInspector {{
                border-top: 3px solid {c['primary']};
            }}

            QFrame#CirculationHoverPreview {{
                background-color: {c['surface']};
                border: 1.5px solid {c['border_bright']};
                border-left: 4px solid {c['primary']};
                border-radius: 10px;
            }}

            QLabel#CirculationPreviewTitle {{
                color: {c['text']};
                font-size: 14px;
                font-weight: 700;
            }}

            QLabel#CirculationPreviewStatus {{
                font-size: 10px;
                font-weight: 700;
            }}

            QLabel#CirculationPreviewKey {{
                color: {c['muted']};
                font-size: 10px;
                font-weight: 600;
            }}

            QLabel#CirculationPreviewValue {{
                color: {c['text']};
                font-size: 11px;
                font-weight: 600;
            }}

            QLineEdit#CirculationSearch {{
                background-color: {c['input']};
                color: {c['text']};
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }}

            QLineEdit#CirculationSearch:focus {{
                border: 1.5px solid {c['primary']};
            }}

            QPushButton {{
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 5px 12px;
            }}

            QPushButton#PrimaryButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary']}, stop:1 {c['indigo']}
                );
                color: #FFFFFF;
                border: 1px solid {c['primary']};
                font-weight: 700;
            }}

            QPushButton#PrimaryButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary_hover']}, stop:1 {c['indigo_hover']}
                );
            }}

            QPushButton#SuccessButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['success']}, stop:1 {c['teal']}
                );
                color: #FFFFFF;
                border: 1px solid {c['success']};
                font-weight: 700;
            }}

            QPushButton#SuccessButton:hover {{
                background-color: {c['success_hover']};
            }}

            QPushButton#InfoButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['cyan']}, stop:1 {c['primary']}
                );
                color: #FFFFFF;
                border: 1px solid {c['cyan']};
                font-weight: 700;
            }}

            QPushButton#InfoButton:hover {{
                background-color: {c['cyan_hover']};
            }}

            QPushButton#WarningButton {{
                background-color: {c['warning']};
                color: #FFFFFF;
                border: 1px solid {c['warning']};
                font-weight: 700;
            }}

            QPushButton#WarningButton:hover {{
                background-color: {c['warning_hover']};
            }}

            QPushButton#DangerButton {{
                background-color: {c['danger_soft']};
                color: {c['danger']};
                border: 1px solid {rgba_color(c['danger'], 0.65)};
                font-weight: 700;
            }}

            QPushButton#DangerButton:hover {{
                background-color: {c['danger']};
                color: #FFFFFF;
                border-color: {c['danger']};
            }}

            QPushButton#SecondaryButton {{
                background-color: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border_bright']};
            }}

            QPushButton#SecondaryButton:hover {{
                background-color: {c['surface_elevated']};
                border-color: {c['primary']};
                color: {c['primary']};
            }}

            QPushButton#FilterButton {{
                background-color: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border_bright']};
                border-radius: 7px;
                padding: 0px 10px;
                min-height: 26px;
                max-height: 26px;
                font-size: 11px;
                font-weight: 600;
            }}

            QPushButton#FilterButton:hover {{
                background-color: {c['surface_elevated']};
                color: {c['text']};
                border-color: {c['primary']};
            }}

            QPushButton#FilterButton[filterRole="ALL"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary']}, stop:1 {c['indigo']}
                );
                color: #FFFFFF;
                border-color: {c['primary']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="ISSUED"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['success']}, stop:1 {c['teal']}
                );
                color: #FFFFFF;
                border-color: {c['success']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="DUE_TODAY"]:checked {{
                background-color: {c['warning']};
                color: #FFFFFF;
                border-color: {c['warning']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="OVERDUE"]:checked {{
                background-color: {c['danger']};
                color: #FFFFFF;
                border-color: {c['danger']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="RENEWED"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['cyan']}, stop:1 {c['primary']}
                );
                color: #FFFFFF;
                border-color: {c['cyan']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="RETURNED_TODAY"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['teal']}, stop:1 {c['success']}
                );
                color: #FFFFFF;
                border-color: {c['teal']};
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="RETURNED_HISTORY"]:checked {{
                background-color: {c['purple']};
                color: #FFFFFF;
                border-color: {c['purple']};
                font-weight: 700;
            }}

            QLabel#CountLabel {{
                background-color: {c['primary_soft']};
                color: {c['primary']};
                border: 1px solid {rgba_color(c['primary'], 0.35)};
                border-radius: 9px;
                padding: 0px 12px;
                min-height: 26px;
                max-height: 26px;
                font-size: 11px;
                font-weight: 700;
            }}

            QLabel#SectionTitle {{
                color: {c['primary']};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }}

            QTableWidget#CirculationTable {{
                background-color: {c['table_row']};
                alternate-background-color: {c['table_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 10px;
                selection-background-color: {c['selection']};
                selection-color: #FFFFFF;
                outline: none;
            }}

            QTableWidget#CirculationTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid {c['border']};
            }}

            QHeaderView::section {{
                background-color: {c['header_bg']};
                color: {c['text']};
                border: none;
                border-bottom: 2px solid {c['border_bright']};
                padding: 10px 10px;
                font-size: 11px;
                font-weight: 700;
            }}

            QTabWidget::pane {{
                border: 1px solid {c['border']};
                background: {c['surface']};
                border-radius: 8px;
            }}

            QTabBar::tab {{
                background: {c['surface_alt']};
                color: {c['muted']};
                padding: 8px 13px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11px;
                font-weight: 700;
            }}

            QTabBar::tab:selected {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary']}, stop:1 {c['indigo']}
                );
                color: #FFFFFF;
            }}

            QMenu {{
                background-color: {c['surface']};
                color: {c['text']};
                border: 1px solid {c['border_bright']};
                border-radius: 8px;
                padding: 5px;
            }}

            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}

            QMenu::item:selected {{
                background-color: {c['selection']};
                color: #FFFFFF;
            }}
        """)

        accent_map = {
            "ALL": c["primary"],
            "ISSUED": c["success"],
            "OVERDUE": c["danger"],
            "RETURNED_HISTORY": c["purple"],
        }
        for key, card in getattr(self, "metric_cards", {}).items():
            card.set_accent(accent_map.get(key, card.accent), c)

        if hasattr(self, "table") and self.table.rowCount() > 0 and self.filtered_logs:
            selected_ids = self._get_selected_log_ids()
            self.populate_table(self.filtered_logs)
            if selected_ids:
                self._restore_selection(selected_ids)
                return

        self._refresh_inspector_theme()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def _build_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 40)
        main_layout.setSpacing(8)
        self.main_layout = main_layout

        # HEADER
        header_layout = QGridLayout()
        header_layout.setHorizontalSpacing(10)
        header_layout.setVerticalSpacing(8)
        self.header_layout = header_layout

        title_column = QVBoxLayout()
        title_column.setSpacing(3)
        self.title_column_host = QWidget()
        self.title_column_host.setLayout(title_column)
        self.title_column_host.setMinimumWidth(0)

        self.lbl_title = QLabel("Circulation Management")
        self.lbl_title.setObjectName("PageTitle")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setMinimumWidth(0)
        self.lbl_title.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )

        self.lbl_subtitle = QLabel(
            "Issue books, manage returns, and track overdue books."
        )
        self.lbl_subtitle.setObjectName("PageSubtitle")
        self.lbl_subtitle.setWordWrap(True)
        self.lbl_subtitle.setMinimumWidth(0)
        self.lbl_subtitle.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )

        title_column.addWidget(self.lbl_title)
        title_column.addWidget(self.lbl_subtitle)

        self.header_actions_host = QWidget()
        header_actions = QHBoxLayout(self.header_actions_host)
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(8)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_refresh.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_refresh.setMinimumHeight(32)
        self.btn_refresh.clicked.connect(self.load_circulation)

        header_actions.addWidget(self.btn_refresh)

        self.control_center_btn = QPushButton("Hide Details")
        self.control_center_btn.setObjectName("SecondaryButton")
        self.control_center_btn.setMinimumHeight(32)
        self.control_center_btn.setToolTip(
            "Show or hide the Transaction Control Center"
        )
        self.control_center_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.control_center_btn.clicked.connect(
            self.toggle_control_center
        )
        header_actions.addWidget(self.control_center_btn)

        self._reflow_header(compact=False)
        main_layout.addLayout(header_layout)

        # KPI CARDS
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)

        self.metric_total = ClickableMetricCard(
            "ALL", "TOTAL TRANSACTIONS", "0",
            "All circulation activities", "#3B82F6",
            self.handle_card_click
        )

        self.metric_active = ClickableMetricCard(
            "ISSUED", "ISSUED BOOKS", "0",
            "Books currently issued", "#16A34A",
            self.handle_card_click
        )

        self.metric_overdue = ClickableMetricCard(
            "OVERDUE", "OVERDUE BOOKS", "0",
            "Past their due date", "#DC2626",
            self.handle_card_click
        )

        self.metric_returned = ClickableMetricCard(
            "RETURNED_HISTORY", "RETURNED BOOKS", "0",
            "Completed transactions", "#8B5CF6",
            self.handle_card_click
        )

        self.metric_cards = {
            "ALL": self.metric_total,
            "ISSUED": self.metric_active,
            "OVERDUE": self.metric_overdue,
            "RETURNED_HISTORY": self.metric_returned,
        }

        for column, card in enumerate(self.metric_cards.values()):
            metrics_layout.addWidget(card, 0, column)

        self.metrics_grid = metrics_layout
        self._metrics_columns = None
        self._reflow_metric_cards(4)
        main_layout.addLayout(metrics_layout)

        # TOOLBAR
        toolbar = QFrame()
        toolbar.setObjectName("CirculationToolbar")

        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setHorizontalSpacing(8)
        toolbar_layout.setVerticalSpacing(6)
        self.toolbar_layout = toolbar_layout

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CirculationSearch")
        self.search_input.setPlaceholderText(
            "Search Log ID, Book ID, User ID or status..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(32)
        self.search_input.setMinimumWidth(0)
        self.search_input.textChanged.connect(self.apply_filters)

        self.btn_fines = QPushButton("Pending Fines")
        self.btn_fines.setObjectName("WarningButton")
        self.btn_fines.setMinimumHeight(32)
        self.btn_fines.setMinimumWidth(0)
        self.btn_fines.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fines.clicked.connect(self.open_fines_desk)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setObjectName("InfoButton")
        self.btn_export.setMinimumHeight(32)
        self.btn_export.setMinimumWidth(0)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_csv)

        self.btn_issue = QPushButton("+ Issue Books")
        self.btn_issue.setObjectName("PrimaryButton")
        self.btn_issue.setMinimumHeight(32)
        self.btn_issue.setMinimumWidth(0)
        self.btn_issue.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_issue.clicked.connect(self.open_issue_wizard)

        self.btn_return = QPushButton("Return Books")
        self.btn_return.setObjectName("SuccessButton")
        self.btn_return.setMinimumHeight(32)
        self.btn_return.setMinimumWidth(0)
        self.btn_return.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_return.clicked.connect(self.open_return_wizard)

        self._reflow_toolbar(tier=0)

        main_layout.addWidget(toolbar)

        # FILTER BAR
        filter_frame = QFrame()
        filter_frame.setObjectName("CirculationFilterBar")

        filter_outer = QHBoxLayout(filter_frame)
        filter_outer.setContentsMargins(6, 5, 8, 5)
        filter_outer.setSpacing(8)

        filters_host = QWidget()
        filters_host.setObjectName("FilterButtonsHost")
        filters_host.setMinimumWidth(0)
        filters_host.setStyleSheet("background: transparent; border: none;")
        filters_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        filter_layout = FlowLayout(filters_host, margin=0, h_spacing=6, v_spacing=5)

        self.filter_buttons = {}

        for key, label in self.FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setProperty("filterRole", key)
            button.setCheckable(True)
            button.setFixedHeight(28)
            button.setMinimumWidth(0)
            button.setChecked(key == "ALL")
            button.setCursor(Qt.CursorShape.PointingHandCursor)

            button.clicked.connect(
                lambda checked=False, selected=key:
                self.set_status_filter(selected)
            )

            self.filter_buttons[key] = button
            filter_layout.addWidget(button)

        filter_outer.addWidget(filters_host, 1)

        self.lbl_count = QLabel("Showing 0 of 0 transactions")
        self.lbl_count.setObjectName("CountLabel")
        self.lbl_count.setFixedHeight(28)
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_count.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        filter_outer.addWidget(
            self.lbl_count,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        main_layout.addWidget(filter_frame)

        # MAIN CONTENT
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setObjectName("CirculationSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)

        # TABLE
        self.table = QTableWidget()
        self.table.setObjectName("CirculationTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setMinimumHeight(110)
        self.table.setMinimumWidth(0)

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)

        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(44)
        header.setHighlightSections(False)
        self._apply_table_column_modes(compact=False)

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self.show_context_menu
        )
        self.table.itemSelectionChanged.connect(
            self.on_circulation_selection_changed
        )
        self.table.cellEntered.connect(
            self.show_transaction_hover_preview
        )
        self.table.viewport().installEventFilter(self)
        self._create_transaction_hover_preview()

        self.content_splitter.addWidget(self.table)

        # INSPECTOR
        self.detail_container = QFrame()
        self.detail_container.setObjectName("CirculationInspector")
        self.detail_container.setMinimumWidth(220)
        self.detail_container.setMaximumWidth(340)
        self.detail_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding
        )

        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(11, 11, 11, 11)
        detail_layout.setSpacing(9)

        self.inspector_title = QLabel(
            "Transaction Control Center"
        )
        self.inspector_title.setObjectName("SectionTitle")
        self.inspector_title.setWordWrap(True)
        self.inspector_title.setMinimumWidth(0)

        detail_layout.addWidget(self.inspector_title)

        self.tab_widget = QTabWidget()
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setUsesScrollButtons(True)

        self.tab_overview, self.overview_layout, _overview_content = make_scrollable_tab(
            self.tab_widget,
            "Details",
            margins=(8, 8, 8, 8),
            spacing=8,
            object_name="CirculationOverviewScroll",
        )

        self.tab_actions, self.actions_layout, _actions_content = make_scrollable_tab(
            self.tab_widget,
            "Actions",
            margins=(8, 8, 8, 8),
            spacing=7,
            object_name="CirculationActionsScroll",
        )

        detail_layout.addWidget(self.tab_widget)

        self.content_splitter.addWidget(self.detail_container)
        main_layout.addWidget(self.content_splitter, 1)

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

    def _reflow_toolbar(self, tier: int):
        if tier == self._toolbar_tier:
            return
        widgets = (
            self.search_input,
            self.btn_fines,
            self.btn_export,
            self.btn_issue,
            self.btn_return,
        )
        for widget in widgets:
            self.toolbar_layout.removeWidget(widget)
        for col in range(5):
            self.toolbar_layout.setColumnStretch(col, 0)

        if tier == 2:
            self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 2)
            self.toolbar_layout.addWidget(self.btn_fines, 1, 0)
            self.toolbar_layout.addWidget(self.btn_export, 1, 1)
            self.toolbar_layout.addWidget(self.btn_issue, 2, 0)
            self.toolbar_layout.addWidget(self.btn_return, 2, 1)
            self.toolbar_layout.setColumnStretch(0, 1)
            self.toolbar_layout.setColumnStretch(1, 1)
        elif tier == 1:
            self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 4)
            self.toolbar_layout.addWidget(self.btn_fines, 1, 0)
            self.toolbar_layout.addWidget(self.btn_export, 1, 1)
            self.toolbar_layout.addWidget(self.btn_issue, 1, 2)
            self.toolbar_layout.addWidget(self.btn_return, 1, 3)
            for col in range(4):
                self.toolbar_layout.setColumnStretch(col, 1)
        else:
            self.toolbar_layout.addWidget(self.search_input, 0, 0)
            self.toolbar_layout.addWidget(self.btn_fines, 0, 1)
            self.toolbar_layout.addWidget(self.btn_export, 0, 2)
            self.toolbar_layout.addWidget(self.btn_issue, 0, 3)
            self.toolbar_layout.addWidget(self.btn_return, 0, 4)
            self.toolbar_layout.setColumnStretch(0, 1)
        self._toolbar_tier = tier

    def _apply_table_column_modes(self, compact: bool):
        if compact == self._table_compact:
            return
        header = self.table.horizontalHeader()
        if compact:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(False)
            compact_widths = {
                0: 74,   # Log ID
                1: 82,   # Book ID
                2: 122,  # User ID
                3: 92,   # Status
                4: 96,   # Issue Date
                5: 120,  # Due Date
                6: 96,   # Return Date
                7: 108,  # Fine
            }
            for col, width in compact_widths.items():
                self.table.setColumnWidth(col, width)
        else:
            header.setStretchLastSection(False)
            fixed_widths = {
                0: 56,   # Log ID
                1: 68,   # Book ID
                3: 94,   # Status
                4: 118,  # Issue Date
                6: 118,  # Return Date
                7: 78,   # Fine
            }
            for col in range(len(self.HEADERS)):
                if col in fixed_widths:
                    header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                    self.table.setColumnWidth(col, fixed_widths[col])
                else:
                    header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._table_compact = compact

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
        toolbar_tier = 2 if avail_w < 820 else 1 if avail_w < 1040 else 0
        self._reflow_toolbar(toolbar_tier)

        compact = avail_w < 1100
        if compact != self._filter_compact_mode:
            compact_labels = {
                "ALL": "All",
                "ISSUED": "Issued",
                "DUE_TODAY": "Due Today",
                "OVERDUE": "Overdue",
                "RENEWED": "Renewed",
                "RETURNED_TODAY": "Ret. Today",
                "RETURNED_HISTORY": "History",
            }
            labels = (
                compact_labels
                if compact
                else dict(self.FILTERS)
            )
            for key, button in self.filter_buttons.items():
                button.setText(labels[key])
            self._filter_compact_mode = compact

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
        self._apply_table_column_modes(est_table_w < 580)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_responsive_layout()

    def _create_transaction_hover_preview(self):
        self.hover_preview = QFrame(
            self,
            Qt.WindowType.ToolTip,
        )
        self.hover_preview.setObjectName("CirculationHoverPreview")
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
        self.hover_preview_title.setObjectName(
            "CirculationPreviewTitle"
        )
        self.hover_preview_title.setWordWrap(True)
        layout.addWidget(self.hover_preview_title)

        self.hover_preview_status = QLabel()
        self.hover_preview_status.setObjectName(
            "CirculationPreviewStatus"
        )
        layout.addWidget(self.hover_preview_status)

        details = QFormLayout()
        details.setContentsMargins(0, 2, 0, 0)
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(6)

        self.hover_preview_values = {}
        for field in (
            "Book ID", "User ID", "Issue Date", "Due Date",
            "Renewals", "Last Renewed", "Return Date", "Fine",
        ):
            key_label = QLabel(field)
            key_label.setObjectName("CirculationPreviewKey")

            value_label = QLabel()
            value_label.setObjectName("CirculationPreviewValue")
            value_label.setWordWrap(True)

            details.addRow(key_label, value_label)
            self.hover_preview_values[field] = value_label

        layout.addLayout(details)
        self.hover_preview.hide()

    def show_transaction_hover_preview(self, row, _column):
        id_item = self.table.item(row, 0)
        if not id_item:
            self.hover_preview.hide()
            return

        record = id_item.data(Qt.ItemDataRole.UserRole)
        if not record or len(record) < 8:
            self.hover_preview.hide()
            return

        log_id = record[0]
        if (
            self.detail_container.isVisible()
            and self._get_selected_log_ids() == [str(log_id)]
        ):
            self.hover_preview.hide()
            return

        (
            _log_id, book_id, user_id, issue_date,
            due_date, return_date, fine, _status,
        ) = record
        display_status = self._display_status(record)
        try:
            fine_value = float(fine or 0)
        except (TypeError, ValueError):
            fine_value = 0.0

        renewal_count, last_renewed = self.renewal_meta.get(int(log_id), (0, ""))
        settled, fine_action, _, _ = self.fine_meta.get(
            int(log_id), (False, "", "", "")
        )
        fine_text = f"₹{fine_value:.2f}"
        if fine_value > 0 and settled:
            badge = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
            fine_text = f"{fine_text} ({badge})"

        values = {
            "Book ID": book_id,
            "User ID": user_id,
            "Issue Date": issue_date,
            "Due Date": due_date,
            "Renewals": str(renewal_count),
            "Last Renewed": last_renewed or "—",
            "Return Date": return_date or "—",
            "Fine": fine_text,
        }

        self.hover_preview_title.setText(
            f"Transaction #{log_id}"
        )
        self.hover_preview_status.setText(display_status)
        status_color = (
            self.colors["danger"] if display_status == "OVERDUE"
            else self.colors["warning"] if display_status == "DUE TODAY"
            else self.colors["success"] if display_status == "ISSUED"
            else self.colors["muted"]
        )
        self.hover_preview_status.setStyleSheet(
            f"color: {status_color};"
        )

        for field, value in values.items():
            self.hover_preview_values[field].setText(
                self._date_text(value) or "—"
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
                    max(bounds.left(), bounds.right() - self.hover_preview.width())
                )
            if position.x() < bounds.left():
                position.setX(bounds.left())
            if position.y() + self.hover_preview.height() > bounds.bottom():
                position.setY(
                    self.table.viewport().mapToGlobal(
                        QPoint(item_rect.left(), item_rect.top())
                    ).y() - self.hover_preview.height() - 8
                )
            if position.y() < bounds.top():
                position.setY(bounds.top())

        self.hover_preview.move(position)
        self.hover_preview.show()
        self.hover_preview.raise_()

    def eventFilter(self, watched, event):
        if (
            watched is self.table.viewport()
            and event.type() == QEvent.Type.Leave
        ):
            self.hover_preview.hide()

        return super().eventFilter(watched, event)

    # ---------------------------------------------------------
    # DATE AND STATUS HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _date_text(value):
        return "" if value is None else str(value).strip()

    @staticmethod
    def _parse_date(value):
        if not value:
            return None

        text = str(value).strip()

        formats = (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d-%m-%Y",
            "%d/%m/%Y",
        )

        for fmt in formats:
            try:
                return datetime.strptime(text[:19], fmt).date()
            except ValueError:
                continue

        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _is_overdue(self, row):
        try:
            if str(row[7]).strip().upper() != "ISSUED":
                return False

            due_date = self._parse_date(row[4])
            return bool(due_date and due_date < date.today())

        except (IndexError, TypeError):
            return False

    def _is_due_today(self, row):
        try:
            if str(row[7]).strip().upper() != "ISSUED":
                return False

            due_date = self._parse_date(row[4])
            return due_date == date.today()

        except (IndexError, TypeError):
            return False

    def _is_returned_today(self, row):
        try:
            if str(row[7]).strip().upper() != "RETURNED":
                return False

            returned_date = self._parse_date(row[5])
            return returned_date == date.today()

        except (IndexError, TypeError):
            return False

    def _get_renewal_count(self, log_id):
        try:
            return int(self.renewal_meta.get(int(log_id), (0, ""))[0] or 0)
        except (TypeError, ValueError):
            return 0

    def _display_status(self, row):
        status = str(row[7]).strip().upper()

        if status == "ISSUED" and self._is_overdue(row):
            return "OVERDUE"
        if status == "ISSUED" and self._is_due_today(row):
            return "DUE TODAY"

        return status

    # ---------------------------------------------------------
    # DATA LOADING
    # ---------------------------------------------------------

    def load_logs(self):
        """Compatibility alias for load_circulation()."""
        self.load_circulation()

    def load_circulation(self):
        selected_ids = self._get_selected_log_ids()

        try:
            result = self.db.get_logs()

            if not isinstance(result, tuple) or len(result) != 2:
                raise ValueError("Unexpected database response.")

            success, rows = result

            if not success:
                QMessageBox.warning(
                    self,
                    "Database Error",
                    "Unable to load circulation records."
                )
                return

            self.all_logs = [
                tuple(row)
                for row in (rows or [])
                if row is not None and len(row) == 8
            ]
            log_ids = [row[0] for row in self.all_logs]
            self.renewal_meta = (
                self.db.get_loan_renewal_meta(log_ids) if log_ids else {}
            )
            self.fine_meta = (
                self.db.get_loan_fine_settlement_meta(log_ids)
                if log_ids
                else {}
            )

            self.update_metrics()
            self.apply_filters(preserve_selection=False)

            if selected_ids:
                self._restore_selection(selected_ids)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Circulation Error",
                f"Unable to load transactions:\n{exc}"
            )

    def update_metrics(self):
        total = len(self.all_logs)

        active = sum(
            1 for row in self.all_logs
            if str(row[7]).upper() == "ISSUED"
            and not self._is_overdue(row)
        )

        overdue = sum(
            1 for row in self.all_logs
            if self._is_overdue(row)
        )

        returned = sum(
            1 for row in self.all_logs
            if str(row[7]).upper() == "RETURNED"
        )

        self.metric_total.set_value(total)
        self.metric_active.set_value(active)
        self.metric_overdue.set_value(overdue)
        self.metric_returned.set_value(returned)

    # ---------------------------------------------------------
    # FILTERS
    # ---------------------------------------------------------

    def handle_card_click(self, filter_key):
        self.set_status_filter(filter_key)

    def set_status_filter(self, key):
        valid_keys = {item[0] for item in self.FILTERS}

        if key not in valid_keys:
            return

        self.current_filter = key

        for filter_key, button in self.filter_buttons.items():
            button.setChecked(filter_key == key)

        for card_key, card in self.metric_cards.items():
            card.set_selected(card_key == key)

        self.apply_filters()

    def apply_filters(self, *_args, preserve_selection=True):
        selected_ids = (
            self._get_selected_log_ids()
            if preserve_selection else []
        )

        query = self.search_input.text().strip().casefold()
        filtered = []

        for row in self.all_logs:
            status = str(row[7]).strip().upper()

            if self.current_filter == "ISSUED":
                if status != "ISSUED" or self._is_overdue(row):
                    continue

            elif self.current_filter == "DUE_TODAY":
                if not self._is_due_today(row):
                    continue

            elif self.current_filter == "OVERDUE":
                if not self._is_overdue(row):
                    continue

            elif self.current_filter == "RENEWED":
                if self._get_renewal_count(row[0]) <= 0:
                    continue

            elif self.current_filter == "RETURNED_TODAY":
                if not self._is_returned_today(row):
                    continue

            elif self.current_filter == "RETURNED_HISTORY":
                if status != "RETURNED":
                    continue

            renewal_count = self._get_renewal_count(row[0])
            settled, fine_action, _, _ = self.fine_meta.get(
                int(row[0]), (False, "", "", "")
            )
            fine_tag = (
                "waived" if settled and str(fine_action).upper() == "WAIVED"
                else "paid" if settled
                else "unpaid pending" if float(row[6] or 0) > 0
                else ""
            )
            searchable = (
                " ".join(str(value or "") for value in row)
                + " " + self._display_status(row)
                + (f" renewed {renewal_count}" if renewal_count > 0 else "")
                + f" {fine_tag}"
            ).casefold()

            if query and query not in searchable:
                continue

            filtered.append(row)

        self.filtered_logs = filtered
        self.populate_table(filtered)

        if selected_ids:
            self._restore_selection(selected_ids)

    # ---------------------------------------------------------
    # TABLE
    # ---------------------------------------------------------

    def populate_table(self, rows):
        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:
            self.table.clearContents()
            self.table.setRowCount(len(rows))

            c = self.colors or self._get_colors()

            for row_index, row in enumerate(rows):
                (
                    log_id, book_id, user_id,
                    checkout, due, returned, fine, status
                ) = row

                display_status = self._display_status(row)
                renewal_count, last_renewed = self.renewal_meta.get(
                    int(log_id), (0, "")
                )
                settled, fine_action, settled_at, _ = self.fine_meta.get(
                    int(log_id), (False, "", "", "")
                )

                try:
                    fine_value = float(fine or 0)
                except (TypeError, ValueError):
                    fine_value = 0.0

                due_display = self._date_text(due)
                if renewal_count > 0 and due_display:
                    due_display = f"{due_display} (↻{renewal_count})"

                fine_display = f"₹{fine_value:.2f}"
                if fine_value > 0 and settled:
                    tag = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
                    fine_display = f"{fine_display} ({tag})"

                values = [
                    str(log_id),
                    str(book_id),
                    str(user_id),
                    display_status,
                    self._date_text(checkout),
                    due_display,
                    self._date_text(returned) or "—",
                    fine_display,
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if column in (0, 7):
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter
                        )

                    if column == 0:
                        item.setData(
                            Qt.ItemDataRole.UserRole,
                            tuple(row)
                        )
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        item.setForeground(QColor(c["primary"]))

                    if column == 3:
                        item.setFont(
                            QFont("Segoe UI", 9, QFont.Weight.Bold)
                        )

                        if display_status == "OVERDUE":
                            item.setForeground(
                                QColor(c["danger"])
                            )
                        elif display_status == "DUE TODAY":
                            item.setForeground(
                                QColor(c["warning"])
                            )
                        elif display_status == "ISSUED":
                            item.setForeground(
                                QColor(c["success"])
                            )
                        elif display_status == "RETURNED":
                            item.setForeground(
                                QColor(c["muted"])
                            )

                    if column == 5 and renewal_count > 0:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        item.setForeground(QColor(c["cyan"]))
                        item.setToolTip(
                            f"Due Date: {self._date_text(due) or '—'}\n"
                            f"Renewals: {renewal_count}\n"
                            f"Last Renewed: {last_renewed or 'Recorded'}"
                        )

                    if column == 7 and fine_value > 0:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        if settled:
                            item.setForeground(QColor(c["success"]))
                            item.setToolTip(
                                f"Fine ₹{fine_value:.2f} marked {fine_action or 'PAID'}"
                                + (f" on {settled_at}" if settled_at else "")
                            )
                        else:
                            item.setForeground(QColor(c["warning"]))

                    self.table.setItem(
                        row_index, column, item
                    )

        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self._updating_table = False

        self.lbl_count.setText(
            f"Showing {len(rows)} of {len(self.all_logs)} transactions"
        )

        if not rows:
            self.show_default_inspector()

    def _get_row_data(self, row_index):
        if row_index < 0 or row_index >= self.table.rowCount():
            return None

        item = self.table.item(row_index, 0)

        return (
            item.data(Qt.ItemDataRole.UserRole)
            if item else None
        )

    def _get_selected_log_ids(self):
        if not hasattr(self, "table"):
            return []

        selected = []

        for index in self.table.selectionModel().selectedRows():
            row = self._get_row_data(index.row())

            if row:
                selected.append(str(row[0]))

        return selected

    def _restore_selection(self, log_ids):
        wanted = {str(value) for value in log_ids}

        self.table.blockSignals(True)

        try:
            self.table.clearSelection()

            for row_index in range(self.table.rowCount()):
                row_data = self._get_row_data(row_index)

                if row_data and str(row_data[0]) in wanted:
                    self.table.selectRow(row_index)

        finally:
            self.table.blockSignals(False)

        self.on_circulation_selection_changed()

    # ---------------------------------------------------------
    # INSPECTOR
    # ---------------------------------------------------------

    def show_default_inspector(self):
        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        lbl = QLabel(
            "Select a transaction from the table to inspect "
            "its details and available actions."
        )

        configure_wrapped_label(lbl)
        lbl.setStyleSheet(
            f"color: {self.colors.get('muted', '#94A3B8')};"
            "font-size: 11px;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

        empty = QLabel("No transaction selected.")
        configure_wrapped_label(empty)
        empty.setStyleSheet(
            f"color: {self.colors.get('muted', '#94A3B8')};"
            "font-size: 11px;"
        )

        self.actions_layout.addWidget(empty)
        self.actions_layout.addStretch()

    def _refresh_inspector_theme(self):
        if not hasattr(self, "detail_container"):
            return

        selected = self.table.selectionModel().selectedRows()

        if not selected:
            self.show_default_inspector()

        elif len(selected) == 1:
            self.display_log_details(selected[0].row())

        else:
            self.on_circulation_selection_changed()

    def display_log_details(self, row_index):
        row = self._get_row_data(row_index)

        if not row:
            return

        (
            log_id, book_id, user_id,
            checkout, due, returned, fine, original_status
        ) = row

        status = self._display_status(row)

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        c = self.colors

        if status == "OVERDUE":
            banner_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['danger']}, stop:1 {c['danger_hover']})"
            )
            banner_border = c["danger"]
        elif status == "DUE TODAY":
            banner_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['warning']}, stop:1 {c['warning_hover']})"
            )
            banner_border = c["warning"]
        elif status == "ISSUED":
            banner_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['success']}, stop:1 {c['teal']})"
            )
            banner_border = c["success"]
        else:
            banner_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['indigo']}, stop:1 {c['purple']})"
            )
            banner_border = c["indigo"]

        status_lbl = QLabel(
            f"{status}\nTransaction #{log_id}"
        )

        status_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        configure_wrapped_label(status_lbl)

        status_lbl.setStyleSheet(f"""
            background: {banner_bg};
            color: #FFFFFF;
            border: 1px solid {banner_border};
            border-radius: 8px;
            padding: 10px;
            font-weight: 800;
            font-size: 11px;
        """)

        self.overview_layout.addWidget(status_lbl)

        try:
            fine_value = float(fine or 0)
        except (TypeError, ValueError):
            fine_value = 0.0

        renewal_meta = self.db.get_loan_renewal_meta([log_id]).get(
            int(log_id), (0, "")
        )
        renewal_count, last_renewed = renewal_meta
        max_renewals = self.db.get_max_renewals()
        renewal_text = (
            f"{renewal_count} / {max_renewals}"
            if max_renewals > 0
            else f"{renewal_count} (Unlimited)"
        )
        settled, fine_action, settled_at, fine_note = (
            self.db.get_loan_fine_settlement_meta([log_id]).get(
                int(log_id), (False, "", "", "")
            )
        )
        if fine_value <= 0:
            fine_status_text = "No fine"
        elif settled:
            tag = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
            fine_status_text = tag + (f" ({settled_at})" if settled_at else "")
            if fine_note:
                fine_status_text += f" — {fine_note}"
        else:
            fine_status_text = "Pending collection"

        renewal_history = (
            self.db.get_renewal_history(log_id)
            if renewal_count > 0
            else []
        )
        history_summary = (
            "\n".join(
                f"• {h['renewed_at']}: +{h['extended_days']}d → {h['new_due_date']}"
                for h in renewal_history[:3]
            )
            if renewal_history
            else "None"
        )

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=7)
        form.setContentsMargins(2, 5, 2, 5)

        details = [
            ("Log ID", log_id),
            ("Book ID", book_id),
            ("User ID", user_id),
            ("Issue Date", checkout),
            ("Due Date", due),
            ("Renewals", renewal_text),
            ("Last Renewed", last_renewed or "—"),
            ("Returned", returned or "—"),
            ("Fine", f"₹{fine_value:.2f}"),
            ("Fine Status", fine_status_text),
        ]
        if renewal_history:
            details.append(("History", history_summary))

        for key, value in details:
            lbl_key = QLabel(str(key))
            configure_wrapped_label(lbl_key, expanding_width=False)
            lbl_value = QLabel(str(value or "—"))
            configure_wrapped_label(lbl_value, expanding_width=True)

            lbl_key.setStyleSheet(
                f"color: {c['muted']};"
                "font-size: 10px;"
                "font-weight: 600;"
            )

            lbl_value.setStyleSheet(
                f"color: {c['text']};"
                "font-size: 11px;"
                "font-weight: 600;"
            )

            form.addRow(lbl_key, lbl_value)

        self.overview_layout.addLayout(form)
        self.overview_layout.addStretch()

        if status in ("ISSUED", "DUE TODAY", "OVERDUE"):
            renew_btn = QPushButton("Renew Loan")
            renew_btn.setObjectName("InfoButton")
            renew_btn.setMinimumHeight(35)
            configure_inspector_button(renew_btn)
            renew_btn.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            renew_btn.clicked.connect(
                lambda: self.renew_single_loan(log_id)
            )
            self.actions_layout.addWidget(renew_btn)

            ret_btn = QPushButton("Process Return")
            ret_btn.setObjectName("SuccessButton")
            ret_btn.setMinimumHeight(35)
            configure_inspector_button(ret_btn)
            ret_btn.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            ret_btn.clicked.connect(
                lambda: self.process_single_return(
                    str(book_id), str(user_id)
                )
            )

            self.actions_layout.addWidget(ret_btn)

        if fine_value > 0 and not settled:
            pay_btn = QPushButton("💳 Mark Fine Paid")
            pay_btn.setObjectName("SuccessButton")
            pay_btn.setMinimumHeight(35)
            configure_inspector_button(pay_btn)
            pay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            pay_btn.clicked.connect(
                lambda: self.settle_single_fine(log_id, "PAID")
            )
            self.actions_layout.addWidget(pay_btn)

            waive_btn = QPushButton("Waive Fine")
            waive_btn.setObjectName("WarningButton")
            waive_btn.setMinimumHeight(35)
            configure_inspector_button(waive_btn)
            waive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            waive_btn.clicked.connect(
                lambda: self.settle_single_fine(log_id, "WAIVED")
            )
            self.actions_layout.addWidget(waive_btn)

        copy_btn = QPushButton("Copy Transaction ID")
        copy_btn.setObjectName("SecondaryButton")
        copy_btn.setMinimumHeight(35)
        configure_inspector_button(copy_btn)
        copy_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(
                str(log_id)
            )
        )

        self.actions_layout.addWidget(copy_btn)
        self.actions_layout.addStretch()

    def on_circulation_selection_changed(self):
        if self._updating_table:
            return

        rows = sorted({
            index.row()
            for index in self.table.selectionModel().selectedRows()
        })

        if not rows:
            self.show_default_inspector()

        elif len(rows) == 1:
            self.display_log_details(rows[0])

        else:
            clear_layout(self.overview_layout)
            clear_layout(self.actions_layout)

            selected_records = [
                self._get_row_data(r) for r in rows
            ]
            selected_records = [r for r in selected_records if r]
            active_rows = [
                r for r in selected_records
                if str(r[7]).strip().upper() == "ISSUED"
            ]
            unpaid_fine_rows = [
                r for r in selected_records
                if float(r[6] or 0) > 0
                and not self.fine_meta.get(int(r[0]), (False, "", "", ""))[0]
            ]
            unpaid_total = sum(float(r[6] or 0) for r in unpaid_fine_rows)

            c = self.colors or self._get_colors()
            lbl = QLabel(
                f"{len(selected_records)} transactions selected.\n\n"
                f"• Active Loans: {len(active_rows)}\n"
                f"• Unsettled Fines: {len(unpaid_fine_rows)} (₹{unpaid_total:.2f})"
            )
            configure_wrapped_label(lbl)
            lbl.setStyleSheet(
                f"background-color: {c.get('primary_soft', 'rgba(59, 130, 246, 0.16)')}; "
                f"color: {c.get('text', '#F8FAFC')}; "
                f"border: 1px solid {rgba_color(c.get('primary', '#3B82F6'), 0.35)}; "
                "border-radius: 8px; padding: 10px; font-size: 11px; font-weight: 600;"
            )
            self.overview_layout.addWidget(lbl)
            self.overview_layout.addStretch()

            if active_rows:
                batch_renew_btn = QPushButton(
                    f"Renew Selected Active ({len(active_rows)})"
                )
                batch_renew_btn.setObjectName("InfoButton")
                batch_renew_btn.setMinimumHeight(35)
                configure_inspector_button(batch_renew_btn)
                batch_renew_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                batch_renew_btn.clicked.connect(
                    lambda: self.handle_batch_renew(active_rows)
                )
                self.actions_layout.addWidget(batch_renew_btn)

                batch_return_btn = QPushButton(
                    f"Return Selected Active ({len(active_rows)})"
                )
                batch_return_btn.setObjectName("SuccessButton")
                batch_return_btn.setMinimumHeight(35)
                configure_inspector_button(batch_return_btn)
                batch_return_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                batch_return_btn.clicked.connect(
                    lambda: self.handle_batch_return(active_rows)
                )
                self.actions_layout.addWidget(batch_return_btn)

            if unpaid_fine_rows:
                batch_fine_btn = QPushButton(
                    f"Mark Selected Fines Paid (₹{unpaid_total:.2f})"
                )
                batch_fine_btn.setObjectName("WarningButton")
                batch_fine_btn.setMinimumHeight(35)
                configure_inspector_button(batch_fine_btn)
                batch_fine_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                batch_fine_btn.clicked.connect(
                    lambda: self.handle_batch_settle_fines(unpaid_fine_rows)
                )
                self.actions_layout.addWidget(batch_fine_btn)

            if not active_rows and not unpaid_fine_rows:
                hint = QLabel("No batch actions available for these rows.")
                configure_wrapped_label(hint)
                hint.setStyleSheet(
                    f"color: {c.get('muted', '#94A3B8')}; font-size: 11px;"
                )
                self.actions_layout.addWidget(hint)

            self.actions_layout.addStretch()

    # ---------------------------------------------------------
    # ISSUE BOOK
    # ---------------------------------------------------------

    def open_issue_wizard(self):
        dialog = IssueBookDialog(self.db, self)

        if not dialog.exec():
            return

        try:
            book_id, user_id, days = dialog.get_data()

            if not book_id or not user_id:
                return

            try:
                success, msg = self.db.issue_book(
                    book_id, user_id, days
                )
            except TypeError:
                success, msg = self.db.issue_book(
                    book_id, user_id
                )

            if success:
                QMessageBox.information(
                    self,
                    "Book Issued",
                    "Book successfully issued."
                )
                self.load_circulation()

            else:
                QMessageBox.warning(
                    self, "Issue Failed", str(msg)
                )

        except Exception as exc:
            QMessageBox.critical(
                self, "Issue Error", str(exc)
            )

    # ---------------------------------------------------------
    # RETURN BOOK
    # ---------------------------------------------------------

    def open_return_wizard(self):
        dialog = ReturnBookDialog(self.db, self)

        if not dialog.exec():
            return

        try:
            book_id, user_id = dialog.get_data()

            self.process_single_return(
                book_id, user_id
            )

        except Exception as exc:
            QMessageBox.critical(
                self, "Return Error", str(exc)
            )

    def process_single_return(self, book_id, user_id):
        if not book_id or not user_id:
            return

        try:
            result = self.db.return_book(
                book_id, user_id
            )

            if not isinstance(result, (tuple, list)) or len(result) < 2:
                raise ValueError(
                    "Unexpected return operation response."
                )

            success, fine = result[0], result[1]

            if success:
                try:
                    fine_value = float(fine or 0)
                except (TypeError, ValueError):
                    fine_value = 0.0

                QMessageBox.information(
                    self,
                    "Book Returned",
                    "Book returned successfully.\n"
                    f"Fine: ₹{fine_value:.2f}"
                )

                self.load_circulation()

            else:
                QMessageBox.warning(
                    self,
                    "Return Failed",
                    "Return unsuccessful. Check the book and user IDs."
                )

        except Exception as exc:
            QMessageBox.critical(
                self, "Return Error", str(exc)
            )

    def renew_single_loan(self, log_id):
        try:
            dialog = RenewLoanDialog(self.db, log_id, self)
            if dialog.exec() == dialog.DialogCode.Accepted:
                self.load_circulation()
                QMessageBox.information(
                    self,
                    "Loan Renewed",
                    dialog.result_message or "Loan renewed successfully.",
                )
        except Exception as exc:
            QMessageBox.critical(
                self, "Renewal Error", str(exc)
            )

    def settle_single_fine(self, log_id, action="PAID"):
        action_key = "WAIVED" if str(action).upper() == "WAIVED" else "PAID"
        label = "Waive Fine" if action_key == "WAIVED" else "Mark Fine Paid"
        note, ok = QInputDialog.getText(
            self,
            label,
            f"Optional reference / note for transaction #{log_id}:",
        )
        if not ok:
            return

        try:
            success, message = self.db.settle_loan_fine(
                log_id, action_key, note
            )
            if success:
                QMessageBox.information(self, label, message)
                self.load_circulation()
            else:
                QMessageBox.warning(self, label, message)
        except Exception as exc:
            QMessageBox.critical(self, "Fine Settlement Error", str(exc))

    def open_fines_desk(self):
        try:
            dialog = PendingFinesDialog(self.db, self)
            dialog.data_updated.connect(self.load_circulation)
            dialog.exec()
            self.load_circulation()
        except Exception as exc:
            QMessageBox.critical(self, "Pending Fines Error", str(exc))

    def handle_batch_renew(self, active_rows):
        if not active_rows:
            return
        days, ok = QInputDialog.getInt(
            self,
            "Batch Loan Renewal",
            f"Extend {len(active_rows)} active loan(s) by how many days?\n"
            "(Carried overdue fines will follow policy defaults.)",
            14, 1, 180, 1,
        )
        if not ok:
            return

        succeeded = 0
        failed = []
        for row in active_rows:
            ok_ren, _, msg = self.db.renew_loan(
                row[0], extend_days=days, notes="Batch renewal"
            )
            if ok_ren:
                succeeded += 1
            else:
                failed.append(f"#{row[0]} ({row[1]}): {msg}")

        self.load_circulation()
        summary = f"Renewed: {succeeded}\nFailed: {len(failed)}"
        if failed:
            summary += "\n\nNot renewed:\n" + "\n".join(failed[:10])
        QMessageBox.information(self, "Batch Renewal Results", summary)

    def handle_batch_return(self, active_rows):
        if not active_rows:
            return
        answer = QMessageBox.question(
            self,
            "Confirm Batch Return",
            f"Process return for {len(active_rows)} selected active loan(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        succeeded = 0
        total_fines = 0.0
        failed = []
        for row in active_rows:
            ok_ret, fine, msg = self.db.return_book(str(row[1]), str(row[2]))
            if ok_ret:
                succeeded += 1
                total_fines += float(fine or 0)
            else:
                failed.append(f"#{row[0]} ({row[1]}): {msg}")

        self.load_circulation()
        summary = (
            f"Returned: {succeeded}\n"
            f"Total Fines Recorded: ₹{total_fines:.2f}\n"
            f"Failed: {len(failed)}"
        )
        if failed:
            summary += "\n\nNot returned:\n" + "\n".join(failed[:10])
        QMessageBox.information(self, "Batch Return Results", summary)

    def handle_batch_settle_fines(self, unpaid_fine_rows):
        if not unpaid_fine_rows:
            return
        total = sum(float(r[6] or 0) for r in unpaid_fine_rows)
        answer = QMessageBox.question(
            self,
            "Confirm Batch Fine Collection",
            f"Mark {len(unpaid_fine_rows)} fine(s) totaling ₹{total:.2f} as Paid?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        succeeded = 0
        failed = []
        for row in unpaid_fine_rows:
            ok_settle, msg = self.db.settle_loan_fine(
                row[0], "PAID", "Batch fine settlement"
            )
            if ok_settle:
                succeeded += 1
            else:
                failed.append(f"#{row[0]}: {msg}")

        self.load_circulation()
        summary = f"Settled: {succeeded}\nFailed: {len(failed)}"
        if failed:
            summary += "\n\nNot settled:\n" + "\n".join(failed[:10])
        QMessageBox.information(self, "Batch Fine Settlement", summary)

    # ---------------------------------------------------------
    # CONTEXT MENU
    # ---------------------------------------------------------

    def show_context_menu(self, position):
        index = self.table.indexAt(position)

        if not index.isValid():
            return

        row = index.row()
        row_data = self._get_row_data(row)

        if not row_data:
            return

        self.table.selectRow(row)

        menu = QMenu(self)

        renew_action = None
        ret_action = None
        pay_action = None
        waive_action = None

        if self._display_status(row_data) in (
            "ISSUED", "DUE TODAY", "OVERDUE"
        ):
            renew_action = menu.addAction(
                "Renew Loan"
            )
            ret_action = menu.addAction(
                "Process Return"
            )

        fine_val = float(row_data[6] or 0)
        settled = self.fine_meta.get(int(row_data[0]), (False, "", "", ""))[0]
        if fine_val > 0 and not settled:
            pay_action = menu.addAction("💳 Mark Fine Paid")
            waive_action = menu.addAction("Waive Fine")

        menu.addSeparator()

        copy_action = menu.addAction(
            "Copy Transaction ID"
        )

        selected_action = menu.exec(
            self.table.viewport().mapToGlobal(position)
        )

        if renew_action is not None and selected_action == renew_action:
            self.renew_single_loan(row_data[0])

        elif ret_action is not None and selected_action == ret_action:
            self.process_single_return(
                str(row_data[1]),
                str(row_data[2])
            )

        elif pay_action is not None and selected_action == pay_action:
            self.settle_single_fine(row_data[0], "PAID")

        elif waive_action is not None and selected_action == waive_action:
            self.settle_single_fine(row_data[0], "WAIVED")

        elif selected_action == copy_action:
            QApplication.clipboard().setText(
                str(row_data[0])
            )

    # ---------------------------------------------------------
    # EXPORT CSV
    # ---------------------------------------------------------

    def export_csv(self):
        if not self.filtered_logs:
            QMessageBox.information(
                self,
                "Export CSV",
                "There are no transactions to export."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Circulation Report",
            "circulation_report.csv",
            "CSV Files (*.csv)"
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
                encoding="utf-8-sig"
            ) as file:

                writer = csv.writer(file)

                writer.writerow(
                    list(self.HEADERS) + ["Renewals", "Last Renewed", "Fine Status"]
                )

                for row in self.filtered_logs:
                    lid = int(row[0])
                    r_count, last_r = self.renewal_meta.get(lid, (0, ""))
                    settled, f_action, _, _ = self.fine_meta.get(
                        lid, (False, "", "", "")
                    )
                    fine_val = float(row[6] or 0)
                    if fine_val <= 0:
                        f_status = "No Fine"
                    elif settled:
                        f_status = "Waived" if str(f_action).upper() == "WAIVED" else "Paid"
                    else:
                        f_status = "Pending"
                    writer.writerow([
                        row[0],
                        row[1],
                        row[2],
                        self._display_status(row),
                        row[3] or "",
                        row[4] or "",
                        row[5] or "",
                        row[6] or "0.00",
                        r_count,
                        last_r,
                        f_status,
                    ])

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported "
                f"{len(self.filtered_logs)} transactions.\n\n"
                f"Location:\n{file_path}"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Unable to export CSV:\n{exc}"
            )
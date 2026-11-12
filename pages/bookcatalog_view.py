import csv
import math
import re
from datetime import date
import openpyxl
from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QPoint,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QFont
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
    QAbstractItemView,
    QMessageBox,
    QFileDialog,
    QMenu,
    QTabWidget,
    QFormLayout,
    QSplitter,
)

from dialogs import (
    BookDialog,
    BarcodeGeneratorDialog,
    BookHistoryDialog,
    IssueBookDialog,
    ReturnBookDialog,
    BatchCirculationDialog,
)
from ui_responsive import (
    FlowLayout,
    configure_inspector_button,
    configure_inspector_form,
    configure_wrapped_label,
    make_scrollable_tab,
    sync_responsive_splitter,
)

from utils import clear_layout, is_valid_book_id, rgba_color


# ============================================================
# COLORS
# ============================================================

ACCENT_BLUE = "#3B82F6"
ACCENT_PURPLE = "#8B5CF6"
ACCENT_GREEN = "#16A34A"
ACCENT_ORANGE = "#D97706"
ACCENT_RED = "#DC2626"


# ============================================================
# INTERACTIVE KPI CARD
# ============================================================

class MetricCard(QFrame):
    """
    Interactive dashboard KPI card.

    Clicking a card emits its filter key to CatalogView.
    """

    clicked = pyqtSignal(str)

    def __init__(
        self,
        title,
        value="0",
        accent=ACCENT_BLUE,
        filter_key="ALL",
        parent=None,
        colors=None,
    ):
        super().__init__(parent)

        self.accent = accent
        self.filter_key = filter_key
        self.selected = False
        self._colors = colors or {}

        self.setObjectName("MetricCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setMinimumWidth(0)
        self.setMinimumHeight(60)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 5, 11, 5)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setMinimumWidth(0)

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setObjectName("MetricValue")
        self.lbl_value.setMinimumWidth(0)

        self.lbl_title.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

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
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.filter_key)

        super().mousePressEvent(event)


# ============================================================
# CATALOG VIEW
# ============================================================

class CatalogView(QWidget):

    HEADERS = [
        "Book ID",
        "Title",
        "Author",
        "Publisher",
        "Total Copies",
        "Available",
        "Added On",
    ]

    FILTERS = {
        "ALL": "All Titles",
        "AVAILABLE": "Available",
        "ISSUED": "Issued",
        "LOW_STOCK": "Low Stock",
    }

    def __init__(self, db):
        super().__init__()

        self.db = db

        self.setObjectName("CatalogView")

        self.all_books = []
        self.current_filter = "ALL"
        self.current_book_id = None
        self._updating_table = False

        self.metric_cards = {}
        self._metrics_columns = None
        self._header_compact = None
        self._toolbar_compact = None
        self._splitter_vertical = None
        self._table_compact = None
        self._page_compact = None
        self._control_center_expanded = True

        app = QApplication.instance()
        self.theme_manager = (
            getattr(app, "theme_manager", None)
            if app else None
        )

        self._build_ui()
        self._connect_theme_manager()
        self.apply_theme()
        self.load_books_to_table()

    # ========================================================
    # UI CONSTRUCTION
    # ========================================================

    def _build_ui(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 40)
        main_layout.setSpacing(8)
        self.main_layout = main_layout

        # HEADER
        header = QGridLayout()
        header.setHorizontalSpacing(10)
        header.setVerticalSpacing(8)
        self.header_layout = header

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        self.title_column_host = QWidget()
        self.title_column_host.setLayout(title_column)
        self.title_column_host.setMinimumWidth(0)

        self.lbl_title = QLabel("Book Catalog")
        self.lbl_title.setObjectName("PageTitle")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setMinimumWidth(0)
        self.lbl_title.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )

        self.lbl_subtitle = QLabel(
            "Manage physical inventory, import and export CSV data, "
            "and monitor book availability."
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

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setMinimumHeight(32)
        self.refresh_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.refresh_btn.clicked.connect(
            self.load_books_to_table
        )

        header_actions.addWidget(self.refresh_btn)

        self.control_center_btn = QPushButton("Hide Details")
        self.control_center_btn.setObjectName("SecondaryButton")
        self.control_center_btn.setMinimumHeight(32)
        self.control_center_btn.setToolTip(
            "Show or hide the Book Control Center"
        )
        self.control_center_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.control_center_btn.clicked.connect(
            self.toggle_control_center
        )
        header_actions.addWidget(self.control_center_btn)
        self.header_actions_stretch = header_actions

        self._reflow_header(compact=False)
        main_layout.addLayout(header)

        # ====================================================
        # INTERACTIVE KPI CARDS
        # ====================================================

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)

        card_definitions = [
            (
                "TOTAL TITLES",
                "0",
                ACCENT_BLUE,
                "ALL",
            ),
            (
                "TOTAL COPIES",
                "0",
                ACCENT_PURPLE,
                "ALL",
            ),
            (
                "AVAILABLE",
                "0",
                ACCENT_GREEN,
                "AVAILABLE",
            ),
            (
                "ISSUED",
                "0",
                ACCENT_ORANGE,
                "ISSUED",
            ),
            (
                "LOW STOCK",
                "0",
                ACCENT_RED,
                "LOW_STOCK",
            ),
        ]

        for index, definition in enumerate(card_definitions):

            title, value, accent, filter_key = definition

            card = MetricCard(
                title=title,
                value=value,
                accent=accent,
                filter_key=filter_key,
                parent=self,
            )

            card.clicked.connect(
                self.set_catalog_filter
            )

            self.metric_cards[title] = card

            metrics_grid.addWidget(
                card,
                0,
                index,
            )

        self.metrics_grid = metrics_grid
        self._reflow_metric_cards(5)

        main_layout.addLayout(metrics_grid)

        # Default selected card
        self.metric_cards["TOTAL TITLES"].set_selected(True)

        # ====================================================
        # TOOLBAR
        # ====================================================

        toolbar = QFrame()
        toolbar.setObjectName("CatalogToolbar")

        toolbar_layout = QGridLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setHorizontalSpacing(8)
        toolbar_layout.setVerticalSpacing(6)
        self.toolbar_layout = toolbar_layout

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CatalogSearch")

        self.search_input.setPlaceholderText(
            "Search by ID, title, author or publisher..."
        )

        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(32)
        self.search_input.setMinimumWidth(0)

        self.search_input.textChanged.connect(
            self.apply_filters
        )

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SuccessButton")
        self.export_btn.setMinimumHeight(32)
        self.export_btn.clicked.connect(
            self.export_books_to_csv
        )

        self.import_btn = QPushButton("Import CSV / XLSX")
        self.import_btn.setObjectName("InfoButton")
        self.import_btn.setMinimumHeight(32)
        self.import_btn.clicked.connect(
            self.import_books_from_file
        )

        self.addbook_btn = QPushButton("+ Add New Book")
        self.addbook_btn.setObjectName("PrimaryButton")
        self.addbook_btn.setMinimumHeight(32)
        self.addbook_btn.clicked.connect(self.add_book)

        for button in (
            self.export_btn,
            self.import_btn,
            self.addbook_btn,
        ):
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.setMinimumWidth(0)

        self._reflow_toolbar(compact=False)

        main_layout.addWidget(toolbar)

        # ====================================================
        # FILTER BAR
        # ====================================================

        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")

        filter_outer = QHBoxLayout(filter_frame)
        filter_outer.setContentsMargins(6, 5, 8, 5)
        filter_outer.setSpacing(8)

        filters_host = QWidget()
        filters_host.setObjectName("FilterButtonsHost")
        filters_host.setMinimumWidth(0)
        filters_host.setStyleSheet("QWidget#FilterButtonsHost { background: transparent; border: none; }")
        filters_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        filter_layout = FlowLayout(filters_host, margin=0, h_spacing=6, v_spacing=5)

        self.filter_buttons = {}

        for key, label in self.FILTERS.items():

            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setProperty("filterRole", key)
            button.setCheckable(True)
            button.setFixedHeight(28)
            button.setMinimumWidth(0)
            button.setChecked(key == "ALL")

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(
                lambda checked=False, selected=key:
                self.set_catalog_filter(selected)
            )

            self.filter_buttons[key] = button

            filter_layout.addWidget(button)

        filter_outer.addWidget(filters_host, 1)

        self.lbl_count = QLabel("0 titles")
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

        # ====================================================
        # CONTENT AREA
        # ====================================================

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setObjectName("CatalogSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)

        # BOOK TABLE
        self.table = QTableWidget()

        self.table.setObjectName("CatalogTable")

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setMinimumHeight(110)
        self.table.setMinimumWidth(0)

        # Configure Header Resizing
        header_view = self.table.horizontalHeader()

        # Fixed data columns avoid rescanning thousands of rows for width hints.
        for column in (0, 4, 5, 6):
            header_view.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )

        for column, width in ((0, 72), (4, 82), (5, 72), (6, 86)):
            self.table.setColumnWidth(column, width)
        self._apply_table_column_modes(compact=False)

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

        header_view.setMinimumSectionSize(44)
        header_view.setHighlightSections(False)

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        self.table.customContextMenuRequested.connect(
            self.show_context_menu
        )

        self.table.itemSelectionChanged.connect(
            self.on_books_selection_changed
        )
        self.table.cellEntered.connect(
            self.show_book_hover_preview
        )
        self.table.viewport().installEventFilter(self)

        self._create_book_hover_preview()

        self.content_splitter.addWidget(self.table)

        # ====================================================
        # BOOK INSPECTOR
        # ====================================================

        self.detail_container = QFrame()
        self.detail_container.setObjectName("BookInspector")

        self.detail_container.setMinimumWidth(220)
        self.detail_container.setMaximumWidth(340)

        self.detail_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        inspector_layout = QVBoxLayout(
            self.detail_container
        )

        inspector_layout.setContentsMargins(10, 10, 10, 10)
        inspector_layout.setSpacing(8)

        self.inspector_title = QLabel(
            "Book Control Center"
        )
        self.inspector_title.setObjectName("SectionTitle")
        self.inspector_title.setWordWrap(True)
        self.inspector_title.setMinimumWidth(0)

        inspector_layout.addWidget(
            self.inspector_title
        )

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("InspectorTabs")
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.tabBar().setUsesScrollButtons(True)

        # DETAILS TAB (scrollable so content is never clipped on small displays)
        self.tab_overview, self.overview_layout, _overview_content = make_scrollable_tab(
            self.tab_widget,
            "Details",
            margins=(8, 8, 8, 8),
            spacing=8,
            object_name="BookOverviewScroll",
        )

        # ACTIONS TAB (scrollable)
        self.tab_actions, self.actions_layout, _actions_content = make_scrollable_tab(
            self.tab_widget,
            "Actions",
            margins=(8, 8, 8, 8),
            spacing=6,
            object_name="BookActionsScroll",
        )

        inspector_layout.addWidget(
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
        for widget in (self.search_input, self.export_btn, self.import_btn, self.addbook_btn):
            self.toolbar_layout.removeWidget(widget)
        for col in range(4):
            self.toolbar_layout.setColumnStretch(col, 0)
        if compact:
            self.toolbar_layout.addWidget(self.search_input, 0, 0, 1, 3)
            self.toolbar_layout.addWidget(self.export_btn, 1, 0)
            self.toolbar_layout.addWidget(self.import_btn, 1, 1)
            self.toolbar_layout.addWidget(self.addbook_btn, 1, 2)
            for col in range(3):
                self.toolbar_layout.setColumnStretch(col, 1)
        else:
            self.toolbar_layout.addWidget(self.search_input, 0, 0)
            self.toolbar_layout.addWidget(self.export_btn, 0, 1)
            self.toolbar_layout.addWidget(self.import_btn, 0, 2)
            self.toolbar_layout.addWidget(self.addbook_btn, 0, 3)
            self.toolbar_layout.setColumnStretch(0, 1)
        self._toolbar_compact = compact

    def _apply_table_column_modes(self, compact: bool):
        if compact == self._table_compact:
            return
        header_view = self.table.horizontalHeader()
        if compact:
            for col, width in ((0, 74), (1, 185), (2, 140), (3, 130), (4, 82), (5, 72), (6, 86)):
                header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                self.table.setColumnWidth(col, width)
        else:
            for col, width in ((0, 70), (4, 90), (5, 80), (6, 96)):
                header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, width)
            for col in (1, 2, 3):
                header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
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
        self._reflow_toolbar(avail_w < 880)

        columns = (
            1 if avail_w < 460
            else 2 if avail_w < 680
            else 5
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
        self._apply_table_column_modes(est_table_w < 500)

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

    # ========================================================
    # THEME MANAGEMENT
    # ========================================================

    def _connect_theme_manager(self):

        if self.theme_manager is None:
            return

        signal = getattr(
            self.theme_manager,
            "themeChanged",
            None,
        )

        if signal is not None:
            try:
                signal.connect(self.apply_theme)
            except (TypeError, RuntimeError):
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

        if self.theme_manager is not None:
            try:
                active_theme = (
                    self.theme_manager.get_active_theme()
                )
                colors = (
                    self.theme_manager.COLORS.get(
                        active_theme
                    )
                )
                if colors:
                    merged = dict(defaults)
                    merged.update(colors)
                    return merged
            except Exception:
                pass

        return defaults

    def apply_theme(self, *_):

        c = self._get_colors()

        self.setStyleSheet(f"""
            QWidget#CatalogView {{
                background-color: {c["window"]};
                color: {c["text"]};
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QLabel {{
                background: transparent;
            }}

            QLabel#PageTitle {{
                font-size: 23px;
                font-weight: 800;
                color: {c["text"]};
            }}

            QLabel#PageSubtitle {{
                font-size: 12px;
                color: {c["muted"]};
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

            QFrame#CatalogToolbar,
            QFrame#FilterBar,
            QFrame#BookInspector {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border"]};
                border-radius: 11px;
            }}

            QFrame#BookInspector {{
                border-top: 3px solid {c["primary"]};
            }}

            QFrame#BookHoverPreview {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border_bright"]};
                border-left: 4px solid {c["primary"]};
                border-radius: 10px;
            }}

            QLabel#BookPreviewTitle {{
                color: {c["text"]};
                font-size: 14px;
                font-weight: 700;
            }}

            QLabel#BookPreviewStatus {{
                color: {c["success"]};
                font-size: 10px;
                font-weight: 700;
            }}

            QLabel#BookPreviewKey {{
                color: {c["muted"]};
                font-size: 10px;
                font-weight: 600;
            }}

            QLabel#BookPreviewValue {{
                color: {c["text"]};
                font-size: 11px;
                font-weight: 600;
            }}

            QLineEdit#CatalogSearch {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1.5px solid {c["border"]};
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }}

            QLineEdit#CatalogSearch:focus {{
                border: 1.5px solid {c["primary"]};
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

            QPushButton#FilterButton:hover {{
                background: {c["surface_elevated"]};
                color: {c["text"]};
                border-color: {c["primary"]};
            }}

            QPushButton#FilterButton[filterRole="ALL"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="AVAILABLE"]:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["success"]}, stop:1 {c["teal"]}
                );
                color: #FFFFFF;
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="ISSUED"]:checked {{
                background-color: {c["warning"]};
                color: #FFFFFF;
                font-weight: 700;
            }}

            QPushButton#FilterButton[filterRole="LOW_STOCK"]:checked {{
                background-color: {c["danger"]};
                color: #FFFFFF;
                font-weight: 700;
            }}

            QTableWidget#CatalogTable {{
                background-color: {c["table_row"]};
                alternate-background-color: {c["table_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
                outline: none;
            }}

            QTableWidget#CatalogTable::item {{
                padding: 6px 6px;
                border-bottom: 1px solid {c["border"]};
            }}

            QHeaderView::section {{
                background-color: {c["header_bg"]};
                color: {c["text"]};
                border: none;
                border-bottom: 2px solid {c["border_bright"]};
                padding: 9px 6px;
                font-size: 11px;
                font-weight: 700;
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
        """)

        accent_map = {
            "TOTAL TITLES": c["primary"],
            "TOTAL COPIES": c["purple"],
            "AVAILABLE": c["success"],
            "ISSUED": c["warning"],
            "LOW STOCK": c["danger"],
        }
        for title_key, card in self.metric_cards.items():
            card.set_accent(accent_map.get(title_key, card.accent), c)

        if (
            hasattr(self, "table")
            and self.table.rowCount() > 0
            and getattr(self, "filtered_books", None)
        ):
            selected_ids = [b[0] for b in self.get_selected_books()]
            self.populate_table(self.filtered_books)
            if selected_ids:
                self.select_books_by_ids(selected_ids)
        else:
            self._refresh_inspector_theme()

    def _refresh_inspector_theme(self):

        if self.current_book_id:
            self.display_book_details_by_id(
                self.current_book_id
            )
        elif hasattr(self, "table") and len(self.get_selected_books()) > 1:
            self.show_batch_book_inspector()
        else:
            self.show_default_inspector()

    # ========================================================
    # INVENTORY HELPERS
    # ========================================================

    def _create_book_hover_preview(self):

        self.hover_preview = QFrame(
            self,
            Qt.WindowType.ToolTip,
        )
        self.hover_preview.setObjectName("BookHoverPreview")
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
        self.hover_preview_title.setObjectName("BookPreviewTitle")
        self.hover_preview_title.setWordWrap(True)
        layout.addWidget(self.hover_preview_title)

        self.hover_preview_status = QLabel()
        self.hover_preview_status.setObjectName("BookPreviewStatus")
        layout.addWidget(self.hover_preview_status)

        details = QFormLayout()
        details.setContentsMargins(0, 2, 0, 0)
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(6)

        self.hover_preview_values = {}
        for field in (
            "Book ID", "Author", "Publisher",
            "Total Copies", "Available", "Added On",
        ):
            key_label = QLabel(field)
            key_label.setObjectName("BookPreviewKey")

            value_label = QLabel()
            value_label.setObjectName("BookPreviewValue")
            value_label.setWordWrap(True)

            details.addRow(key_label, value_label)
            self.hover_preview_values[field] = value_label

        layout.addLayout(details)
        self.hover_preview.hide()

    def show_book_hover_preview(self, row, _column):

        id_item = self.table.item(row, 0)
        if not id_item:
            self.hover_preview.hide()
            return

        book_id = id_item.text()
        if (
            self.detail_container.isVisible()
            and self.current_book_id == book_id
        ):
            self.hover_preview.hide()
            return

        book = [
            self.table.item(row, column).text()
            if self.table.item(row, column)
            else ""
            for column in range(len(self.HEADERS))
        ]
        total, available = self._book_counts(book)

        self.hover_preview_title.setText(book[1] or "Untitled book")
        self.hover_preview_status.setText(
            "AVAILABLE" if available > 0 else "OUT OF STOCK"
        )

        values = {
            "Book ID": book[0],
            "Author": book[2] or "—",
            "Publisher": book[3] or "—",
            "Total Copies": str(total),
            "Available": str(available),
            "Added On": book[6] or "—",
        }
        for field, value in values.items():
            self.hover_preview_values[field].setText(value)

        c = self._get_colors()
        status_color = c["success"] if available > 0 else c["danger"]
        self.hover_preview_status.setStyleSheet(
            f"color: {status_color}; font-size: 10px; font-weight: 700;"
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

    @staticmethod
    def _book_counts(book):

        try:
            total = max(
                0,
                int(book[4] or 0),
            )
        except (ValueError, TypeError, IndexError):
            total = 0

        try:
            available = max(
                0,
                int(book[5] or 0),
            )
        except (ValueError, TypeError, IndexError):
            available = 0

        return total, min(available, total)

    def update_metrics(self):

        total_titles = len(self.all_books)

        total_copies = 0
        available_copies = 0
        low_stock = 0

        for book in self.all_books:

            if len(book) < 6:
                continue

            total, available = self._book_counts(book)

            total_copies += total
            available_copies += available

            if available <= 2:
                low_stock += 1

        issued_copies = max(
            0,
            total_copies - available_copies,
        )

        self.metric_cards["TOTAL TITLES"].set_value(
            f"{total_titles:,}"
        )

        self.metric_cards["TOTAL COPIES"].set_value(
            f"{total_copies:,}"
        )

        self.metric_cards["AVAILABLE"].set_value(
            f"{available_copies:,}"
        )

        self.metric_cards["ISSUED"].set_value(
            f"{issued_copies:,}"
        )

        self.metric_cards["LOW STOCK"].set_value(
            f"{low_stock:,}"
        )

    # ========================================================
    # LOAD AND FILTER BOOKS
    # ========================================================

    def load_books_to_table(self):

        selected_id = self.current_book_id

        try:

            result = self.db.get_books()

            if (
                not isinstance(result, tuple)
                or len(result) != 2
            ):
                return

            success, rows = result

            if not success:
                return

            self.all_books = list(rows or [])

            self.update_metrics()

            self.apply_filters(
                preserve_selection=False
            )

            if selected_id:
                self.select_book_by_id(selected_id)

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Catalog Loading Error",
                str(exc),
            )

    def set_catalog_filter(self, key):

        if key not in self.FILTERS:
            return

        self.current_filter = key

        # Synchronize KPI card highlights
        for card in self.metric_cards.values():

            card.set_selected(
                card.filter_key == key
            )

        # Synchronize regular filter buttons
        for filter_key, button in self.filter_buttons.items():

            button.setChecked(
                filter_key == key
            )

        self.apply_filters()

    def reset_catalog_filter(self):

        self.set_catalog_filter("ALL")

    def apply_filters(
        self,
        *_args,
        preserve_selection=True,
    ):

        selected_id = (
            self.current_book_id
            if preserve_selection
            else None
        )

        query = (
            self.search_input.text()
            .strip()
            .casefold()
        )

        filtered = []

        for book in self.all_books:

            if len(book) < 7:
                continue

            total, available = self._book_counts(book)

            # AVAILABLE
            if self.current_filter == "AVAILABLE":

                if available <= 0:
                    continue

            # ISSUED
            elif self.current_filter == "ISSUED":

                if available >= total:
                    continue

            # LOW STOCK
            elif self.current_filter == "LOW_STOCK":

                if available > 2:
                    continue

            # SEARCH
            searchable = " ".join(
                str(value or "")
                for value in book[:4]
            ).casefold()

            if query and query not in searchable:
                continue

            filtered.append(book)

        self.populate_table(filtered)

        if selected_id:
            self.select_book_by_id(selected_id)

    # ========================================================
    # TABLE POPULATION
    # ========================================================

    def populate_table(self, rows):

        self.filtered_books = list(rows or [])
        self.hover_preview.hide()
        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:

            self.table.clearContents()
            self.table.setRowCount(len(rows))

            c = self._get_colors()
            primary_color = QColor(c["primary"])
            danger_color = QColor(c["danger"])
            warning_color = QColor(c["warning"])
            success_color = QColor(c["success"])
            bold_font = QFont(self.table.font())
            bold_font.setBold(True)

            for row_index, book in enumerate(rows):

                _, available = self._book_counts(book)

                for col_idx, value in enumerate(book[:7]):

                    item = QTableWidgetItem(
                        str(
                            value
                            if value is not None
                            else ""
                        )
                    )

                    if col_idx in (0, 4, 5):

                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter
                        )

                    if col_idx == 0:
                        item.setFont(bold_font)
                        item.setForeground(primary_color)

                    if col_idx == 5:

                        if available <= 0:
                            fg_color = danger_color

                        elif available <= 2:
                            fg_color = warning_color

                        else:
                            fg_color = success_color

                        item.setFont(bold_font)
                        item.setForeground(fg_color)

                    self.table.setItem(
                        row_index,
                        col_idx,
                        item,
                    )

        finally:

            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self._updating_table = False

        self.lbl_count.setText(
            f"{len(rows):,} titles"
        )

        if not rows:

            self.current_book_id = None
            self.show_default_inspector()

    def select_book_by_id(self, book_id):

        target = str(book_id)

        for row in range(self.table.rowCount()):

            item = self.table.item(row, 0)

            if item and item.text() == target:

                self.table.selectRow(row)
                self.current_book_id = target

                return True

        return False

    # ========================================================
    # BOOK INSPECTOR
    # ========================================================

    def show_default_inspector(self):

        self.current_book_id = None

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        c = self._get_colors()

        label = QLabel(
            "Select a book from the catalog to view its "
            "information, availability and management actions."
        )

        configure_wrapped_label(label)

        label.setStyleSheet(
            f"color: {c['muted']}; font-size: 12px;"
        )

        self.overview_layout.addWidget(label)
        self.overview_layout.addStretch()

    def display_book_details_by_id(self, book_id):

        try:

            success, book = self.db.get_book_details(
                str(book_id)
            )

            if not success or not book:
                return

        except Exception:
            return

        self.current_book_id = str(book[0])

        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        c = self._get_colors()

        total, available = self._book_counts(book)

        issued = max(
            0,
            total - available,
        )

        # STATUS
        status = (
            "AVAILABLE"
            if available > 0
            else "OUT OF STOCK"
        )

        status_label = QLabel(
            f"{status}\n"
            f"{available} of {total} copies available"
        )

        status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        configure_wrapped_label(status_label)

        if available > 0:
            status_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['success']}, stop:1 {c['teal']})"
            )
            status_border = c["success"]
        else:
            status_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {c['danger']}, stop:1 {c['danger_hover']})"
            )
            status_border = c["danger"]

        status_label.setStyleSheet(f"""
            background: {status_bg};
            color: #FFFFFF;
            border: 1px solid {status_border};
            border-radius: 8px;
            padding: 9px;
            font-weight: 800;
            font-size: 11px;
        """)

        self.overview_layout.addWidget(
            status_label
        )

        # BOOK INFORMATION
        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=7)
        form.setContentsMargins(0, 4, 0, 4)

        fields = [
            ("Book ID", book[0]),
            ("Title", book[1]),
            ("Author", book[2]),
            ("Publisher", book[3]),
            ("Total Copies", total),
            ("Available", available),
            ("Issued", issued),
            ("Added On", book[6]),
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

            value_label.setStyleSheet(
                f"color: {c['text']}; "
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
                "Issue Books",
                lambda: self.handle_issue_book(
                    book[0],
                    book[1],
                ),
                "PrimaryButton",
            ),
            (
                "Return Books",
                lambda: self.handle_return_book(
                    book[0],
                    book[1],
                ),
                "SuccessButton",
            ),
            (
                "Print Barcode",
                lambda: self.open_barcode_dialog_for_selected(
                    book[0]
                ),
                "InfoButton",
            ),
            (
                "Audit History",
                lambda: self.open_book_history(
                    book[0],
                    book[1],
                ),
                "WarningButton",
            ),
            (
                "Edit Record",
                lambda: self.edit_book(book[0]),
                "SecondaryButton",
            ),
            (
                "Delete Book",
                lambda: self.delete_book(book[0]),
                "DangerButton",
            ),
        ]

        for text, callback, object_name in actions:

            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setMinimumHeight(32)
            configure_inspector_button(button)

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(callback)

            self.actions_layout.addWidget(button)

        self.actions_layout.addStretch()

    def on_books_selection_changed(self):

        if self._updating_table:
            return

        self.hover_preview.hide()

        rows = sorted({
            index.row()
            for index in self.table.selectionModel().selectedRows()
        })

        if not rows:

            self.tab_widget.setCurrentWidget(self.tab_overview)
            self.show_default_inspector()

        elif len(rows) == 1:
            self.tab_widget.setCurrentWidget(self.tab_overview)

            item = self.table.item(rows[0], 0)

            if item:
                self.display_book_details_by_id(
                    item.text()
                )

        else:

            self.show_batch_book_inspector()

    def get_selected_books(self):
        selected = []
        for index in self.table.selectionModel().selectedRows():
            row = index.row()
            id_item = self.table.item(row, 0)
            if not id_item:
                continue
            title_item = self.table.item(row, 1)
            selected.append((
                id_item.text().strip(),
                title_item.text().strip() if title_item else "",
            ))
        return list(dict.fromkeys(selected))

    def select_books_by_ids(self, book_ids):
        wanted = {str(book_id) for book_id in book_ids}
        selection_model = self.table.selectionModel()
        selection_model.clearSelection()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() in wanted:
                selection_model.select(
                    self.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self.on_books_selection_changed()

    def show_batch_book_inspector(self):
        books = self.get_selected_books()
        if not books:
            self.show_default_inspector()
            return

        self.current_book_id = None
        self.tab_widget.setCurrentWidget(self.tab_actions)
        clear_layout(self.overview_layout)
        clear_layout(self.actions_layout)

        c = self._get_colors()
        label = QLabel(
            f"{len(books)} books selected.\n\n"
            "Choose a batch action to issue or return all selected titles "
            "for the same user."
        )
        configure_wrapped_label(label)
        label.setStyleSheet(
            f"background-color: {c['primary_soft']}; "
            f"color: {c['text']}; "
            f"border: 1px solid {rgba_color(c['primary'], 0.35)}; "
            "border-radius: 8px; padding: 10px; font-weight: 600;"
        )
        self.overview_layout.addWidget(label)

        for mode, text, object_name in (
            ("ISSUE", "Issue Selected Books", "PrimaryButton"),
            ("RETURN", "Return Selected Books", "SuccessButton"),
        ):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setMinimumHeight(34)
            configure_inspector_button(button)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, selected_mode=mode:
                self.handle_batch_book_circulation(selected_mode)
            )
            self.actions_layout.addWidget(button)
        self.actions_layout.addStretch()

    # ========================================================
    # BOOK OPERATIONS
    # ========================================================

    def add_book(self):

        dialog = BookDialog(
            self.db,
            parent=self,
        )

        dialog.data_updated.connect(
            self.load_books_to_table
        )

        dialog.exec()

        self.load_books_to_table()

    def handle_issue_book(self, book_id, book_title):

        dialog = IssueBookDialog(
            self.db,
            self,
        )

        dialog.input_book.setText(
            str(book_id)
        )

        if not dialog.exec():
            return

        bid, uid, days = dialog.get_data()

        try:

            try:
                success, message = self.db.issue_book(
                    bid,
                    uid,
                    days,
                )

            except TypeError:
                success, message = self.db.issue_book(
                    bid,
                    uid,
                )

            if success:

                QMessageBox.information(
                    self,
                    "Book Issued",
                    f"'{book_title}' successfully issued.",
                )

                self.load_books_to_table()
                self.select_book_by_id(book_id)

            else:

                QMessageBox.warning(
                    self,
                    "Issue Failed",
                    str(message),
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Issue Error",
                str(exc),
            )

    def handle_return_book(self, book_id, book_title):

        dialog = ReturnBookDialog(
            self.db,
            self,
        )

        dialog.input_book.setText(
            str(book_id)
        )

        if not dialog.exec():
            return

        bid, uid = dialog.get_data()

        try:

            result = self.db.return_book(
                bid,
                uid,
            )

            if not isinstance(result, tuple) or len(result) < 2:
                raise ValueError(
                    "Unexpected return_book() response."
                )

            success, fine = result[0], result[1]

            if success:

                QMessageBox.information(
                    self,
                    "Book Returned",
                    "Book returned successfully.\n"
                    f"Fine: ₹{float(fine or 0):.2f}",
                )

                self.load_books_to_table()
                self.select_book_by_id(book_id)

            else:

                QMessageBox.warning(
                    self,
                    "Return Failed",
                    str(fine),
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "Return Error",
                str(exc),
            )

    def handle_batch_book_circulation(self, mode, books=None):
        selected_books = books or self.get_selected_books()
        if not selected_books:
            QMessageBox.information(
                self,
                "No Books Selected",
                "Select at least one book before choosing a batch action.",
            )
            return

        dialog = BatchCirculationDialog(
            self.db,
            mode,
            [book_id for book_id, _title in selected_books],
            "books",
            self,
        )
        if not dialog.exec():
            return

        user_id, days = dialog.get_data()
        operation = "issue" if mode == "ISSUE" else "return"
        answer = QMessageBox.question(
            self,
            f"Confirm Batch {operation.title()}",
            f"{operation.title()} {len(selected_books)} selected books "
            f"for user '{user_id}'?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        succeeded = []
        failed = []
        for book_id, title in selected_books:
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
                    succeeded.append(f"{book_id} — {title}")
                else:
                    failed.append(f"{book_id}: {detail}")
            except Exception as error:
                failed.append(f"{book_id}: {error}")

        self.load_books_to_table()
        self.select_books_by_ids(
            [book_id for book_id, _title in selected_books]
        )
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

    def edit_book(self, book_id):

        dialog = BookDialog(
            self.db,
            book_id=book_id,
            parent=self,
        )

        dialog.data_updated.connect(
            self.load_books_to_table
        )

        dialog.exec()

        self.load_books_to_table()
        self.select_book_by_id(book_id)

    def delete_book(self, book_id):

        answer = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete book {book_id}?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:

            success, message = self.db.delete_book(
                book_id
            )

            if success:

                QMessageBox.information(
                    self,
                    "Deleted",
                    str(message),
                )

                self.load_books_to_table()

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

    # ========================================================
    # CONTEXT MENU
    # ========================================================

    def show_context_menu(self, position):

        index = self.table.indexAt(position)

        if not index.isValid():
            return

        row = index.row()

        item = self.table.item(row, 0)

        if not item:
            return

        book_id = item.text()

        title_item = self.table.item(row, 1)

        book_title = (
            title_item.text()
            if title_item
            else ""
        )

        selected_rows = {
            selected.row()
            for selected in self.table.selectionModel().selectedRows()
        }
        if row not in selected_rows:
            self.table.selectRow(row)

        selected_books = self.get_selected_books()

        menu = QMenu(self)

        if len(selected_books) > 1:
            issue = menu.addAction("Issue Selected Books")
            ret = menu.addAction("Return Selected Books")
        else:
            issue = menu.addAction("Issue Books")
            ret = menu.addAction("Return Books")

        menu.addSeparator()

        barcode = menu.addAction("Print Barcode")
        history = menu.addAction("View Audit History")
        edit = menu.addAction("Edit Book")
        delete = menu.addAction("Delete Book")

        action = menu.exec(
            self.table.viewport().mapToGlobal(position)
        )

        if action == issue:
            if len(selected_books) > 1:
                self.handle_batch_book_circulation("ISSUE", selected_books)
            else:
                self.handle_issue_book(book_id, book_title)

        elif action == ret:
            if len(selected_books) > 1:
                self.handle_batch_book_circulation("RETURN", selected_books)
            else:
                self.handle_return_book(book_id, book_title)

        elif action == barcode:
            self.open_barcode_dialog_for_selected(
                book_id
            )

        elif action == history:
            self.open_book_history(
                book_id,
                book_title,
            )

        elif action == edit:
            self.edit_book(book_id)

        elif action == delete:
            self.delete_book(book_id)

    # ========================================================
    # BARCODE AND HISTORY
    # ========================================================

    def open_barcode_dialog_for_selected(self, book_id=""):

        if book_id:

            try:

                success, book = self.db.get_book_details(
                    str(book_id)
                )

                if not success or not book:
                    return

                dialog = BarcodeGeneratorDialog(
                    self.db,
                    book_id=str(book[0]),
                    title=str(book[1]),
                    author=str(book[2]),
                    publisher=str(book[3]),
                    parent=self,
                )

            except Exception as exc:

                QMessageBox.critical(
                    self,
                    "Barcode Error",
                    str(exc),
                )

                return

        else:

            dialog = BarcodeGeneratorDialog(
                self.db,
                parent=self,
            )

        dialog.data_updated.connect(
            self.load_books_to_table
        )

        dialog.exec()

    def open_book_history(self, book_id, book_title):

        dialog = BookHistoryDialog(
            self.db,
            book_id,
            book_title,
            parent=self,
        )
        dialog.data_updated.connect(self.load_books_to_table)
        dialog.exec()
        self.load_books_to_table()

    # ========================================================
    # CSV / XLSX IMPORT
    # ========================================================

    def import_books_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Book Catalog",
            "",
            "Data Files (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx);;All Files (*)",
        )

        if not file_path:
            return

        file_extension = Path(file_path).suffix.casefold()
        if file_extension not in (".csv", ".xlsx"):
            QMessageBox.warning(
                self,
                "Unsupported File",
                "Select a CSV or XLSX file.",
            )
            return

        required_aliases = {
            "id": ("book_id", "id"),
            "title": ("title",),
            "author": ("author",),
            "publisher": ("publisher",),
            "isbn": ("isbn", "isbn_13", "isbn_10"),
            "copies": (
                "total_copies",
                "copies",
                "total",
            ),
        }

        books_to_insert = []
        errors = []
        current_date = date.today().isoformat()

        try:
            # 1. PARSE DATA BASED ON FILE TYPE
            rows = []
            fieldnames = []

            if file_extension == ".xlsx":
                if openpyxl is None:
                    QMessageBox.critical(
                        self,
                        "Missing Dependency",
                        "Please install 'openpyxl' to import Excel files:\npip install openpyxl"
                    )
                    return

                workbook = openpyxl.load_workbook(
                    file_path,
                    data_only=True,
                    read_only=True,
                )
                try:
                    excel_rows = workbook.active.iter_rows(
                        values_only=True
                    )
                    header_row = next(excel_rows, None)
                    if header_row:
                        fieldnames = [
                            str(cell).strip() if cell is not None else ""
                            for cell in header_row
                        ]
                        for row_data in excel_rows:
                            row_dict = {}
                            for index, cell in enumerate(row_data):
                                if index >= len(fieldnames) or not fieldnames[index]:
                                    continue
                                if (
                                    isinstance(cell, float)
                                    and math.isfinite(cell)
                                    and cell.is_integer()
                                ):
                                    value = str(int(cell))
                                else:
                                    value = str(cell).strip() if cell is not None else ""
                                row_dict[fieldnames[index]] = value
                            rows.append(row_dict)
                finally:
                    workbook.close()
            else:
                # Handle CSV
                with open(file_path, "r", newline="", encoding="utf-8-sig") as csv_file:
                    reader = csv.DictReader(csv_file)
                    fieldnames = reader.fieldnames or []
                    rows = list(reader)

            # 2. VALIDATE HEADERS
            if not fieldnames:
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    "The selected file has no header row or is empty.",
                )
                return

            normalized_headers = {
                re.sub(
                    r"[^a-z0-9]+",
                    "_",
                    str(name).strip().casefold(),
                ).strip("_"): name
                for name in fieldnames
                if name
            }

            def find_column(aliases):
                for alias in aliases:
                    normalized_alias = re.sub(
                        r"[^a-z0-9]+",
                        "_",
                        alias.strip().casefold(),
                    ).strip("_")
                    if normalized_alias in normalized_headers:
                        return normalized_headers[normalized_alias]
                return None

            id_col = find_column(required_aliases["id"])
            title_col = find_column(required_aliases["title"])
            author_col = find_column(required_aliases["author"])
            publisher_col = find_column(required_aliases["publisher"])
            isbn_col = find_column(required_aliases["isbn"])
            copies_col = find_column(required_aliases["copies"])

            if not id_col or not title_col or not publisher_col:
                QMessageBox.warning(
                    self,
                    "Missing Headers",
                    "Required columns: book_id (or id), title, publisher",
                )
                return

            # 3. PROCESS ROWS
            seen_ids = set()
            seen_isbns = set()

            for line_number, row in enumerate(rows, start=2):
                book_id = str(row.get(id_col, "") or "").strip()
                title = str(row.get(title_col, "") or "").strip()

                author = str(row.get(author_col, "") or "").strip() if author_col else ""
                publisher = str(row.get(publisher_col, "") or "").strip() if publisher_col else ""
                isbn = str(row.get(isbn_col, "") or "").strip() if isbn_col else ""
                copies_text = str(row.get(copies_col, "") or "").strip() if copies_col else "1"

                if not is_valid_book_id(book_id):
                    errors.append(
                        f"Line {line_number}: Book ID must contain exactly 5 digits."
                    )
                    continue

                if not title or len(title) > 200:
                    errors.append(
                        f"Line {line_number}: Title is required and must be "
                        "no longer than 200 characters."
                    )
                    continue

                if not publisher or len(publisher) > 100:
                    errors.append(
                        f"Line {line_number}: Publisher is required and must be "
                        "no longer than 100 characters."
                    )
                    continue

                if book_id.casefold() in seen_ids:
                    errors.append(f"Line {line_number}: Duplicate ID '{book_id}' in file.")
                    continue

                try:
                    copies_value = float(copies_text or "1")
                    if (
                        not math.isfinite(copies_value)
                        or not copies_value.is_integer()
                        or copies_value < 1
                    ):
                        raise ValueError
                    copies = int(copies_value)
                except ValueError:
                    errors.append(f"Line {line_number}: Invalid total copies value.")
                    continue
                isbn_key = isbn.casefold()
                if isbn_key and isbn_key in seen_isbns:
                    errors.append(
                        f"Line {line_number}: Duplicate ISBN '{isbn}' in file."
                    )
                    continue
                seen_ids.add(book_id.casefold())
                if isbn_key:
                    seen_isbns.add(isbn_key)

                books_to_insert.append((
                    book_id,
                    title,
                    author or "Unknown",
                    publisher or "Unknown",
                    copies,
                    copies,
                    current_date,
                    isbn or None,
                ))

            # 4. DATABASE INSERTION
            if not books_to_insert:
                QMessageBox.warning(
                    self,
                    "Nothing to Import",
                    "No valid book records were found.",
                )
                return

            success, result = self.db.import_books_batch(books_to_insert)

            if not success:
                QMessageBox.critical(self, "Import Failed", str(result))
                return

            message = f"Successfully imported {int(result or 0)} book records."

            if errors:
                message += f"\n\nSkipped {len(errors)} invalid record(s).\n\nFirst errors:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    message += f"\n...and {len(errors) - 10} more."

            QMessageBox.information(self, "Import Completed", message)
            self.load_books_to_table()

        except Exception as exc:
            QMessageBox.critical(self, "Import Error", f"Unable to import file:\n\n{exc}")

    # ========================================================
    # CSV EXPORT
    # ========================================================

    def export_books_to_csv(self):

        if not self.all_books:
            QMessageBox.information(
                self,
                "Export Catalog",
                "There are no book records to export.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Book Catalog",
            str(Path.home() / "book_catalog.csv"),
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
                writer.writerow(self.HEADERS)
                writer.writerows(self.all_books)

            QMessageBox.information(
                self,
                "Export Completed",
                f"Successfully exported records to:\n{file_path}",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export Failed",
                str(exc),
            )

    # ========================================================
    # CLEANUP
    # ========================================================

    def closeEvent(self, event):

        if self.theme_manager:

            try:

                self.theme_manager.themeChanged.disconnect(
                    self.apply_theme
                )

            except (TypeError, RuntimeError):
                pass

        super().closeEvent(event)
import csv
from datetime import date
import openpyxl
from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor
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
)

from dialogs import (
    BookDialog,
    BarcodeGeneratorDialog,
    BookHistoryDialog,
    IssueBookDialog,
    ReturnBookDialog,
)

from utils import clear_layout


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
    ):
        super().__init__(parent)

        self.accent = accent
        self.filter_key = filter_key
        self.selected = False

        self.setObjectName("MetricCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setMinimumHeight(88)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(5)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setObjectName("MetricValue")

        self.lbl_title.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        self.lbl_value.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

        self.apply_style()

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.apply_style()

    def apply_style(self):
        background = (
            "palette(alternate-base)"
            if self.selected
            else "palette(base)"
        )

        border = (
            self.accent
            if self.selected
            else "palette(mid)"
        )

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background-color: {background};
                border: 1px solid {border};
                border-left: 4px solid {self.accent};
                border-radius: 9px;
            }}

            QFrame#MetricCard:hover {{
                border: 2px solid {self.accent};
                border-left: 5px solid {self.accent};
            }}

            QLabel#MetricTitle {{
                color: palette(placeholder-text);
                font-size: 10px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#MetricValue {{
                color: {self.accent};
                font-size: 23px;
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
        self._compact_layout = None
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

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # HEADER
        header = QHBoxLayout()

        title_column = QVBoxLayout()
        title_column.setSpacing(2)

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

        header.addLayout(title_column, 1)

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.setMinimumHeight(35)
        self.refresh_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.refresh_btn.clicked.connect(
            self.load_books_to_table
        )

        header.addWidget(self.refresh_btn)

        self.control_center_btn = QPushButton("Hide Details")
        self.control_center_btn.setObjectName("SecondaryButton")
        self.control_center_btn.setMinimumHeight(35)
        self.control_center_btn.setToolTip(
            "Show or hide the Book Control Center"
        )
        self.control_center_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.control_center_btn.clicked.connect(
            self.toggle_control_center
        )
        header.addWidget(self.control_center_btn)

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

        toolbar_layout = QHBoxLayout(toolbar)

        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CatalogSearch")

        self.search_input.setPlaceholderText(
            "Search by ID, title, author or publisher..."
        )

        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(36)

        self.search_input.textChanged.connect(
            self.apply_filters
        )

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.setMinimumHeight(36)
        self.export_btn.clicked.connect(
            self.export_books_to_csv
        )

        self.import_btn = QPushButton("Import CSV / XLSX")
        self.import_btn.setObjectName("SecondaryButton")
        self.import_btn.setMinimumHeight(36)
        self.import_btn.clicked.connect(
            self.import_books_from_file
        )

        self.addbook_btn = QPushButton("+ Add New Book")
        self.addbook_btn.setObjectName("PrimaryButton")
        self.addbook_btn.setMinimumHeight(36)
        self.addbook_btn.clicked.connect(self.add_book)

        for button in (
            self.export_btn,
            self.import_btn,
            self.addbook_btn,
        ):
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

        toolbar_layout.addWidget(self.search_input, 1)
        toolbar_layout.addWidget(self.export_btn)
        toolbar_layout.addWidget(self.import_btn)
        toolbar_layout.addWidget(self.addbook_btn)

        main_layout.addWidget(toolbar)

        # ====================================================
        # FILTER BAR
        # ====================================================

        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")

        filter_layout = QHBoxLayout(filter_frame)

        filter_layout.setContentsMargins(6, 4, 6, 4)
        filter_layout.setSpacing(4)

        self.filter_buttons = {}

        for key, label in self.FILTERS.items():

            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)
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

        filter_layout.addStretch()

        self.lbl_count = QLabel("0 titles")
        self.lbl_count.setObjectName("CountLabel")

        filter_layout.addWidget(self.lbl_count)

        main_layout.addWidget(filter_frame)

        # ====================================================
        # CONTENT AREA
        # ====================================================

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # BOOK TABLE
        self.table = QTableWidget()

        self.table.setObjectName("CatalogTable")

        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)

        # Configure Header Resizing
        header_view = self.table.horizontalHeader()

        # Fixed data columns avoid rescanning thousands of rows for width hints.
        for column in (0, 4, 5, 6):
            header_view.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )

        # Stretch the text columns to fill the remaining empty space
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)          # Title
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # Author
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)          # Publisher
        for column, width in ((0, 105), (4, 95), (5, 90), (6, 115)):
            self.table.setColumnWidth(column, width)

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
        self.table.verticalHeader().setDefaultSectionSize(43)

        header_view.setMinimumSectionSize(65)
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

        content_layout.addWidget(self.table, 1)

        # ====================================================
        # BOOK INSPECTOR
        # ====================================================

        self.detail_container = QFrame()
        self.detail_container.setObjectName("BookInspector")

        self.detail_container.setMinimumWidth(265)
        self.detail_container.setMaximumWidth(360)

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

        inspector_layout.addWidget(
            self.inspector_title
        )

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("InspectorTabs")

        # DETAILS TAB
        self.tab_overview = QWidget()

        self.overview_layout = QVBoxLayout(
            self.tab_overview
        )

        self.overview_layout.setContentsMargins(
            8, 8, 8, 8
        )

        self.overview_layout.setSpacing(8)

        self.tab_widget.addTab(
            self.tab_overview,
            "Details",
        )

        # ACTIONS TAB
        self.tab_actions = QWidget()

        self.actions_layout = QVBoxLayout(
            self.tab_actions
        )

        self.actions_layout.setContentsMargins(
            8, 8, 8, 8
        )

        self.actions_layout.setSpacing(6)

        self.tab_widget.addTab(
            self.tab_actions,
            "Actions",
        )

        inspector_layout.addWidget(
            self.tab_widget
        )

        content_layout.addWidget(
            self.detail_container
        )

        main_layout.addLayout(
            content_layout,
            1,
        )

        self.show_default_inspector()

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

    def resizeEvent(self, event):
        super().resizeEvent(event)

        compact = self.width() < 1080
        if compact != self._compact_layout:
            self._compact_layout = compact
            self._control_center_expanded = not compact
            self.detail_container.setVisible(
                self._control_center_expanded
            )
            self.control_center_btn.setText(
                "Hide Details"
                if self._control_center_expanded
                else "Show Details"
            )

        columns = (
            2 if self.width() < 850
            else 3 if self.width() < 1050
            else 5
        )
        self._reflow_metric_cards(columns)

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
                    return colors

            except Exception:
                pass

        return {
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
        }

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
                font-weight: 700;
                color: {c["text"]};
            }}

            QLabel#PageSubtitle {{
                font-size: 12px;
                color: {c["muted"]};
            }}

            QLabel#SectionTitle {{
                font-size: 14px;
                font-weight: 700;
                color: {c["text"]};
            }}

            QFrame#MetricCard {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 9px;
            }}

            QLabel#MetricTitle {{
                font-size: 10px;
                font-weight: 700;
                color: {c["muted"]};
            }}

            QFrame#CatalogToolbar,
            QFrame#FilterBar,
            QFrame#BookInspector {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
            }}

            QFrame#BookHoverPreview {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
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
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 9px 12px;
                font-size: 12px;
            }}

            QLineEdit#CatalogSearch:focus {{
                border: 1px solid {c["primary"]};
            }}

            QPushButton {{
                font-size: 12px;
                font-weight: 600;
                border-radius: 7px;
                padding: 8px 13px;
            }}

            QPushButton#PrimaryButton {{
                background-color: {c["primary"]};
                color: white;
                border: none;
            }}

            QPushButton#PrimaryButton:hover {{
                background-color: {c["primary_hover"]};
            }}

            QPushButton#SecondaryButton {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}

            QPushButton#SecondaryButton:hover {{
                border-color: {c["primary"]};
            }}

            QPushButton#DangerButton {{
                background-color: rgba(220, 38, 38, 0.15);
                color: {c["danger"]};
                border: 1px solid {c["danger"]};
            }}

            QPushButton#FilterButton {{
                background: transparent;
                color: {c["muted"]};
                border: none;
                padding: 7px 12px;
            }}

            QPushButton#FilterButton:checked {{
                background-color: {c["primary"]};
                color: white;
                border-radius: 4px;
            }}

            QTableWidget#CatalogTable {{
                background-color: {c["surface"]};
                alternate-background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 9px;
                selection-background-color: {c["selection"]};
                selection-color: white;
                outline: none;
            }}

            QTableWidget#CatalogTable::item {{
                padding: 8px;
                border-bottom: 1px solid {c["border"]};
            }}

            QHeaderView::section {{
                background-color: {c["surface_alt"]};
                color: {c["muted"]};
                border: none;
                border-bottom: 1px solid {c["border"]};
                padding: 11px 8px;
                font-size: 11px;
                font-weight: 700;
            }}

            QTabWidget::pane {{
                border: 1px solid {c["border"]};
                background: {c["surface"]};
                border-radius: 6px;
            }}

            QTabBar::tab {{
                background: {c["surface_alt"]};
                color: {c["muted"]};
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }}

            QTabBar::tab:selected {{
                background: {c["primary"]};
                color: white;
            }}
        """)

        for card in self.metric_cards.values():
            card.apply_style()

        self._refresh_inspector_theme()

    def _refresh_inspector_theme(self):

        if self.current_book_id:
            self.display_book_details_by_id(
                self.current_book_id
            )
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

        self.hover_preview.hide()
        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        try:

            self.table.clearContents()
            self.table.setRowCount(len(rows))

            c = self._get_colors()

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

                    if col_idx == 5:

                        if available <= 0:
                            color = c["danger"]

                        elif available <= 2:
                            color = c["warning"]

                        else:
                            color = c["success"]

                        item.setForeground(
                            QColor(color)
                        )

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

        label.setWordWrap(True)

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

        status_label.setStyleSheet(f"""
            background: {
                c['success'] if available > 0
                else c['danger']
            };
            color: white;
            border-radius: 6px;
            padding: 8px;
            font-weight: 700;
            font-size: 10px;
        """)

        self.overview_layout.addWidget(
            status_label
        )

        # BOOK INFORMATION
        form = QFormLayout()

        form.setContentsMargins(0, 4, 0, 4)
        form.setVerticalSpacing(8)

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

            value_label = QLabel(
                str(
                    value
                    if value is not None
                    else "—"
                )
            )

            key_label.setStyleSheet(
                f"color: {c['muted']}; "
                "font-size: 10px; font-weight: 600;"
            )

            value_label.setStyleSheet(
                f"color: {c['text']}; "
                "font-size: 11px; font-weight: 600;"
            )

            value_label.setWordWrap(True)

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
                "SecondaryButton",
            ),
            (
                "Print Barcode",
                lambda: self.open_barcode_dialog_for_selected(
                    book[0]
                ),
                "SecondaryButton",
            ),
            (
                "Audit History",
                lambda: self.open_book_history(
                    book[0],
                    book[1],
                ),
                "SecondaryButton",
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

            self.show_default_inspector()

        elif len(rows) == 1:

            item = self.table.item(rows[0], 0)

            if item:
                self.display_book_details_by_id(
                    item.text()
                )

        else:

            self.current_book_id = None

            clear_layout(self.overview_layout)
            clear_layout(self.actions_layout)

            label = QLabel(
                f"{len(rows)} books selected. "
                "Select one book to inspect its details."
            )

            label.setWordWrap(True)

            self.overview_layout.addWidget(label)

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

        self.table.selectRow(row)

        menu = QMenu(self)

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
            self.handle_issue_book(
                book_id,
                book_title,
            )

        elif action == ret:
            self.handle_return_book(
                book_id,
                book_title,
            )

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

        BookHistoryDialog(
            self.db,
            book_id,
            book_title,
            parent=self,
        ).exec()

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

        required_aliases = {
            "id": ("book_id", "id"),
            "title": ("title",),
            "author": ("author",),
            "publisher": ("publisher",),
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

            if file_path.lower().endswith(".xlsx"):
                if openpyxl is None:
                    QMessageBox.critical(
                        self,
                        "Missing Dependency",
                        "Please install 'openpyxl' to import Excel files:\npip install openpyxl"
                    )
                    return

                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheet = wb.active
                excel_rows = list(sheet.iter_rows(values_only=True))

                if excel_rows:
                    # Convert headers to strings, handling potential empty cells
                    fieldnames = [str(cell).strip() if cell else "" for cell in excel_rows[0]]

                    # Create dictionary for each row to mimic csv.DictReader
                    for row_data in excel_rows[1:]:
                        row_dict = {
                            fieldnames[i]: (str(cell).strip() if cell is not None else "")
                            for i, cell in enumerate(row_data) if i < len(fieldnames)
                        }
                        rows.append(row_dict)
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
                str(name).strip().casefold(): name
                for name in fieldnames
                if name
            }

            def find_column(aliases):
                for alias in aliases:
                    if alias in normalized_headers:
                        return normalized_headers[alias]
                return None

            id_col = find_column(required_aliases["id"])
            title_col = find_column(required_aliases["title"])
            author_col = find_column(required_aliases["author"])
            publisher_col = find_column(required_aliases["publisher"])
            copies_col = find_column(required_aliases["copies"])

            if not id_col or not title_col:
                QMessageBox.warning(
                    self,
                    "Missing Headers",
                    "Required columns: book_id (or id), title",
                )
                return

            # 3. PROCESS ROWS
            seen_ids = set()

            for line_number, row in enumerate(rows, start=2):
                book_id = str(row.get(id_col, "") or "").strip()
                title = str(row.get(title_col, "") or "").strip()

                author = str(row.get(author_col, "") or "").strip() if author_col else ""
                publisher = str(row.get(publisher_col, "") or "").strip() if publisher_col else ""
                copies_text = str(row.get(copies_col, "") or "").strip() if copies_col else "1"

                if not book_id or not title:
                    errors.append(f"Line {line_number}: Book ID and title are required.")
                    continue

                if book_id in seen_ids:
                    errors.append(f"Line {line_number}: Duplicate ID '{book_id}' in file.")
                    continue

                seen_ids.add(book_id)

                try:
                    copies = int(copies_text or "1")
                    if copies < 1:
                        raise ValueError
                except ValueError:
                    errors.append(f"Line {line_number}: Invalid total copies value.")
                    continue

                books_to_insert.append((
                    book_id,
                    title,
                    author or "Unknown",
                    publisher or "Unknown",
                    copies,
                    copies,
                    current_date,
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
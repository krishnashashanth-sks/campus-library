import csv
from datetime import datetime, date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QSizePolicy, QFrame, QLabel,
    QMessageBox, QFormLayout, QMenu, QAbstractItemView,
    QFileDialog, QTabWidget, QSpacerItem
)

from utils import clear_layout
from dialogs import IssueBookDialog, ReturnBookDialog


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
        self.setMinimumHeight(94)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MetricTitle")
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
        self.lbl_subtitle.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtitle)

        self.apply_card_style()

    def set_value(self, value):
        self.lbl_value.setText(str(value))

    def set_selected(self, selected):
        self.selected = bool(selected)
        self.apply_card_style()

    def apply_card_style(self):
        c = self.colors

        surface = c.get("surface", "#111C2E")
        border = c.get("border", "#293B55")
        text = c.get("text", "#E8EEF8")
        muted = c.get("muted", "#94A3B8")

        border_color = self.accent if self.selected else border
        background = (
            c.get("surface_alt", "#17243A")
            if self.selected else surface
        )

        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background-color: {background};
                border: 1px solid {border_color};
                border-left: 4px solid {self.accent};
                border-radius: 9px;
            }}
            QFrame#MetricCard:hover {{
                border: 1px solid {self.accent};
                border-left: 4px solid {self.accent};
            }}
            QLabel#MetricTitle {{
                color: {muted};
                font-size: 10px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#MetricValue {{
                color: {self.accent};
                font-size: 24px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#MetricSubtitle {{
                color: {text};
                font-size: 10px;
                background: transparent;
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
        "Checkout Date", "Due Date", "Return Date", "Fine"
    ]

    FILTERS = [
        ("ALL", "All Transactions"),
        ("ISSUED", "Active Loans"),
        ("OVERDUE", "Overdue"),
        ("RETURNED_TODAY", "Returned Today"),
        ("RETURNED_HISTORY", "Return History"),
    ]

    def __init__(self, db):
        super().__init__()

        self.db = db
        self.setObjectName("CirculationView")

        self.all_logs = []
        self.filtered_logs = []
        self.current_filter = "ALL"
        self.colors = {}

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
                font-weight: 750;
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
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}

            QLineEdit#CirculationSearch {{
                background-color: {c['input']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 7px;
                padding: 9px 12px;
                font-size: 12px;
            }}

            QLineEdit#CirculationSearch:focus {{
                border: 1px solid {c['primary']};
            }}

            QPushButton {{
                font-size: 12px;
                font-weight: 600;
                border-radius: 7px;
                padding: 8px 13px;
            }}

            QPushButton#PrimaryButton {{
                background-color: {c['primary']};
                color: white;
                border: none;
            }}

            QPushButton#PrimaryButton:hover {{
                background-color: {c['primary_hover']};
            }}

            QPushButton#SuccessButton {{
                background-color: {c['success']};
                color: white;
                border: none;
            }}

            QPushButton#SuccessButton:hover {{
                background-color: #15803D;
            }}

            QPushButton#SecondaryButton {{
                background-color: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
            }}

            QPushButton#SecondaryButton:hover {{
                border-color: {c['primary']};
            }}

            QPushButton#FilterButton {{
                background-color: transparent;
                color: {c['muted']};
                border: 1px solid transparent;
                padding: 8px 11px;
            }}

            QPushButton#FilterButton:hover {{
                background-color: {c['surface_alt']};
                color: {c['text']};
            }}

            QPushButton#FilterButton:checked {{
                background-color: {c['primary']};
                color: white;
                border-color: {c['primary']};
            }}

            QLabel#CountLabel {{
                color: {c['muted']};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }}

            QLabel#SectionTitle {{
                color: {c['text']};
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }}

            QTableWidget#CirculationTable {{
                background-color: {c['surface']};
                alternate-background-color: {c['surface_alt']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 9px;
                selection-background-color: {c['selection']};
                selection-color: white;
                outline: none;
            }}

            QTableWidget#CirculationTable::item {{
                padding: 8px;
                border-bottom: 1px solid {c['border']};
            }}

            QHeaderView::section {{
                background-color: {c['surface_alt']};
                color: {c['muted']};
                border: none;
                border-bottom: 1px solid {c['border']};
                padding: 11px 8px;
                font-size: 11px;
                font-weight: 700;
            }}

            QTabWidget::pane {{
                border: 1px solid {c['border']};
                background: {c['surface']};
                border-radius: 6px;
            }}

            QTabBar::tab {{
                background: {c['surface_alt']};
                color: {c['muted']};
                padding: 8px 13px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 11px;
                font-weight: 600;
            }}

            QTabBar::tab:selected {{
                background: {c['primary']};
                color: white;
            }}

            QMenu {{
                background-color: {c['surface']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 5px;
            }}

            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
            }}

            QMenu::item:selected {{
                background-color: {c['selection']};
                color: white;
            }}
        """)

        for card in getattr(self, "metric_cards", {}).values():
            card.colors = c
            card.apply_card_style()

        self._refresh_inspector_theme()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # HEADER
        header_layout = QHBoxLayout()

        title_column = QVBoxLayout()
        title_column.setSpacing(3)

        self.lbl_title = QLabel("Circulation Management")
        self.lbl_title.setObjectName("PageTitle")

        self.lbl_subtitle = QLabel(
            "Monitor book loans, manage returns and track overdue transactions."
        )
        self.lbl_subtitle.setObjectName("PageSubtitle")

        title_column.addWidget(self.lbl_title)
        title_column.addWidget(self.lbl_subtitle)

        header_layout.addLayout(title_column)
        header_layout.addStretch()

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_refresh.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.btn_refresh.setMinimumHeight(36)
        self.btn_refresh.clicked.connect(self.load_circulation)

        header_layout.addWidget(self.btn_refresh)
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
            "ISSUED", "ACTIVE LOANS", "0",
            "Currently issued", "#16A34A",
            self.handle_card_click
        )

        self.metric_overdue = ClickableMetricCard(
            "OVERDUE", "OVERDUE LOANS", "0",
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

        main_layout.addLayout(metrics_layout)

        # TOOLBAR
        toolbar = QFrame()
        toolbar.setObjectName("CirculationToolbar")

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 9, 10, 9)
        toolbar_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CirculationSearch")
        self.search_input.setPlaceholderText(
            "Search Log ID, Book ID, User ID or status..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(38)
        self.search_input.textChanged.connect(self.apply_filters)

        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setObjectName("SecondaryButton")
        self.btn_export.setMinimumHeight(38)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_csv)

        self.btn_issue = QPushButton("+ Issue Book")
        self.btn_issue.setObjectName("PrimaryButton")
        self.btn_issue.setMinimumHeight(38)
        self.btn_issue.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_issue.clicked.connect(self.open_issue_wizard)

        self.btn_return = QPushButton("Process Return")
        self.btn_return.setObjectName("SuccessButton")
        self.btn_return.setMinimumHeight(38)
        self.btn_return.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_return.clicked.connect(self.open_return_wizard)

        toolbar_layout.addWidget(self.search_input, 1)
        toolbar_layout.addWidget(self.btn_export)
        toolbar_layout.addWidget(self.btn_issue)
        toolbar_layout.addWidget(self.btn_return)

        main_layout.addWidget(toolbar)

        # FILTER BAR
        filter_frame = QFrame()
        filter_frame.setObjectName("CirculationFilterBar")

        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(7, 5, 7, 5)
        filter_layout.setSpacing(3)

        self.filter_buttons = {}

        for key, label in self.FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)
            button.setChecked(key == "ALL")
            button.setCursor(Qt.CursorShape.PointingHandCursor)

            button.clicked.connect(
                lambda checked=False, selected=key:
                self.set_status_filter(selected)
            )

            self.filter_buttons[key] = button
            filter_layout.addWidget(button)

        filter_layout.addStretch()

        self.lbl_count = QLabel("Showing 0 records")
        self.lbl_count.setObjectName("CountLabel")
        filter_layout.addWidget(self.lbl_count)

        main_layout.addWidget(filter_frame)

        # MAIN CONTENT
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # TABLE
        self.table = QTableWidget()
        self.table.setObjectName("CirculationTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)

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
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        header.setHighlightSections(False)

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self.show_context_menu
        )
        self.table.itemSelectionChanged.connect(
            self.on_circulation_selection_changed
        )

        content_layout.addWidget(self.table, 1)

        # INSPECTOR
        self.detail_container = QFrame()
        self.detail_container.setObjectName("CirculationInspector")
        self.detail_container.setMinimumWidth(275)
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

        detail_layout.addWidget(self.inspector_title)

        self.tab_widget = QTabWidget()

        self.tab_overview = QWidget()
        self.overview_layout = QVBoxLayout(self.tab_overview)
        self.overview_layout.setContentsMargins(8, 8, 8, 8)
        self.overview_layout.setSpacing(8)

        self.tab_widget.addTab(self.tab_overview, "Details")

        self.tab_actions = QWidget()
        self.actions_layout = QVBoxLayout(self.tab_actions)
        self.actions_layout.setContentsMargins(8, 8, 8, 8)
        self.actions_layout.setSpacing(7)

        self.tab_widget.addTab(self.tab_actions, "Actions")

        detail_layout.addWidget(self.tab_widget)

        content_layout.addWidget(self.detail_container)
        main_layout.addLayout(content_layout, 1)

        self.show_default_inspector()

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

    def _is_returned_today(self, row):
        try:
            if str(row[7]).strip().upper() != "RETURNED":
                return False

            returned_date = self._parse_date(row[5])
            return returned_date == date.today()

        except (IndexError, TypeError):
            return False

    def _display_status(self, row):
        status = str(row[7]).strip().upper()

        if status == "ISSUED" and self._is_overdue(row):
            return "OVERDUE"

        return status

    # ---------------------------------------------------------
    # DATA LOADING
    # ---------------------------------------------------------

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

            elif self.current_filter == "OVERDUE":
                if not self._is_overdue(row):
                    continue

            elif self.current_filter == "RETURNED_TODAY":
                if not self._is_returned_today(row):
                    continue

            elif self.current_filter == "RETURNED_HISTORY":
                if status != "RETURNED":
                    continue

            searchable = (
                " ".join(str(value or "") for value in row)
                + " " + self._display_status(row)
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

                try:
                    fine_value = float(fine or 0)
                except (TypeError, ValueError):
                    fine_value = 0.0

                values = [
                    str(log_id),
                    str(book_id),
                    str(user_id),
                    display_status,
                    self._date_text(checkout),
                    self._date_text(due),
                    self._date_text(returned) or "—",
                    f"₹{fine_value:.2f}",
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

                    if column == 3:
                        item.setFont(
                            QFont("Segoe UI", 9, QFont.Weight.Bold)
                        )

                        if display_status == "OVERDUE":
                            item.setForeground(
                                QColor(c["danger"])
                            )
                        elif display_status == "ISSUED":
                            item.setForeground(
                                QColor(c["success"])
                            )
                        elif display_status == "RETURNED":
                            item.setForeground(
                                QColor(c["muted"])
                            )

                    if column == 7 and fine_value > 0:
                        item.setForeground(
                            QColor(c["warning"])
                        )

                    self.table.setItem(
                        row_index, column, item
                    )

        finally:
            self.table.blockSignals(False)
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

        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {self.colors.get('muted', '#94A3B8')};"
            "font-size: 11px;"
        )

        self.overview_layout.addWidget(lbl)
        self.overview_layout.addStretch()

        empty = QLabel("No transaction selected.")
        empty.setWordWrap(True)
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

        banner_color = (
            c["danger"] if status == "OVERDUE"
            else c["success"] if status == "ISSUED"
            else c["muted"]
        )

        status_lbl = QLabel(
            f"{status}\nTransaction #{log_id}"
        )

        status_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        status_lbl.setStyleSheet(f"""
            background-color: {banner_color};
            color: white;
            border-radius: 7px;
            padding: 10px;
            font-weight: 700;
            font-size: 11px;
        """)

        self.overview_layout.addWidget(status_lbl)

        try:
            fine_value = float(fine or 0)
        except (TypeError, ValueError):
            fine_value = 0.0

        form = QFormLayout()
        form.setContentsMargins(2, 5, 2, 5)
        form.setVerticalSpacing(10)

        details = [
            ("Log ID", log_id),
            ("Book ID", book_id),
            ("User ID", user_id),
            ("Checkout", checkout),
            ("Due Date", due),
            ("Returned", returned or "—"),
            ("Fine", f"₹{fine_value:.2f}"),
        ]

        for key, value in details:
            lbl_key = QLabel(str(key))
            lbl_value = QLabel(str(value or "—"))

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

            lbl_value.setWordWrap(True)

            form.addRow(lbl_key, lbl_value)

        self.overview_layout.addLayout(form)
        self.overview_layout.addStretch()

        if status in ("ISSUED", "OVERDUE"):
            ret_btn = QPushButton("Process Return")
            ret_btn.setObjectName("SuccessButton")
            ret_btn.setMinimumHeight(35)
            ret_btn.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            ret_btn.clicked.connect(
                lambda: self.process_single_return(
                    str(book_id), str(user_id)
                )
            )

            self.actions_layout.addWidget(ret_btn)

        copy_btn = QPushButton("Copy Transaction ID")
        copy_btn.setObjectName("SecondaryButton")
        copy_btn.setMinimumHeight(35)
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

            lbl = QLabel(
                f"{len(rows)} transactions selected."
            )
            lbl.setWordWrap(True)
            self.overview_layout.addWidget(lbl)
            self.overview_layout.addStretch()

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

        ret_action = None

        if self._display_status(row_data) in (
            "ISSUED", "OVERDUE"
        ):
            ret_action = menu.addAction(
                "Process Return"
            )

        menu.addSeparator()

        copy_action = menu.addAction(
            "Copy Transaction ID"
        )

        selected_action = menu.exec(
            self.table.viewport().mapToGlobal(position)
        )

        if selected_action == ret_action:
            self.process_single_return(
                str(row_data[1]),
                str(row_data[2])
            )

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

                writer.writerow(self.HEADERS)

                for row in self.filtered_logs:
                    writer.writerow([
                        row[0],
                        row[1],
                        row[2],
                        self._display_status(row),
                        row[3] or "",
                        row[4] or "",
                        row[5] or "",
                        row[6] or "0.00",
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
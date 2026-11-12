import csv
import datetime
import html
import io
import os
import re
import secrets
import threading
import cv2
import barcode

from barcode.writer import ImageWriter
from PIL import Image

from PyQt6 import sip
from PyQt6.QtWidgets import (
    QApplication, QDialog, QPushButton, QLineEdit, QMessageBox, QVBoxLayout,
    QComboBox, QLabel, QSpinBox, QFileDialog, QHBoxLayout,
    QCheckBox, QFrame, QTableWidget, QWidget, QSizePolicy,
    QHeaderView, QFormLayout, QTableWidgetItem, QAbstractItemView,
    QDialogButtonBox, QGridLayout, QGroupBox, QPlainTextEdit, QScrollArea,
    QSplitter, QTextBrowser,
)

from PyQt6.QtCore import (
    pyqtSignal, Qt, QTimer, QRegularExpression, QThreadPool, QUrl
)

from PyQt6.QtGui import (
    QPixmap, QImage, QFont, QRegularExpressionValidator,
    QIntValidator, QColor, QDesktopServices, QTextDocument
)

from app_version import APP_DEVELOPER_CREDIT, APP_NAME
from update_service import RELEASES_PAGE_URL, is_newer_version
from utils import (
    clear_layout,
    format_log_id_display,
    is_valid_book_id,
    is_valid_phone_number,
    is_valid_user_id,
    normalize_department_for_role,
    normalize_user_role,
)
from ui_responsive import (
    FlowLayout,
    clamp_widget_to_screen,
    configure_inspector_button,
    configure_inspector_form,
    configure_wrapped_label,
    sync_responsive_splitter,
    wrap_in_scroll_area,
)


# ============================================================
# SHARED HELPERS
# ============================================================

def configure_dialog(
    dialog,
    title,
    width=None,
    height=None,
    min_width=None,
    min_height=None,
):
    """Apply common dialog configuration without overriding ThemeManager."""
    dialog.setWindowTitle(title)
    clamp_widget_to_screen(
        dialog,
        target_width=width,
        target_height=height,
        min_width=min_width,
        min_height=min_height,
    )
    dialog.setModal(True)


def configure_table(table, alternating=True):
    """Apply consistent table behavior while inheriting global theme colors."""
    table.setAlternatingRowColors(alternating)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
    )
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setHighlightSections(False)
    table.setSortingEnabled(False)


def create_heading(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("DialogHeading")
    label.setProperty("class", "dialog-heading")
    c = get_dialog_colors(label)
    label.setStyleSheet(
        f"QLabel#DialogHeading {{"
        f" color: {c['text']};"
        f" font-size: 17px;"
        f" font-weight: 800;"
        f" background: {c['primary_soft']};"
        f" border-left: 4px solid {c['primary']};"
        f" border-radius: 7px;"
        f" padding: 7px 12px;"
        f"}}"
    )
    return label


def create_button(text, callback=None, enabled=True, variant=None):
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setEnabled(enabled)
    if variant:
        button.setObjectName(variant)

    if callback:
        button.clicked.connect(callback)

    return button


def get_dialog_colors(widget=None):
    """Return active ThemeManager tokens, falling back by palette lightness."""
    app = QApplication.instance()
    tm = (
        app.property("theme_manager") or getattr(app, "theme_manager", None)
        if app is not None
        else None
    )
    if tm is not None and hasattr(tm, "COLORS"):
        try:
            active = (
                tm.get_active_theme()
                if hasattr(tm, "get_active_theme")
                else "Dark"
            )
            if active in tm.COLORS:
                return tm.COLORS[active]
        except Exception:
            pass
    is_dark = True
    try:
        pal = (
            widget.palette()
            if widget is not None
            else (app.palette() if app is not None else None)
        )
        if pal is not None:
            is_dark = pal.window().color().lightness() < 128
    except Exception:
        pass
    if is_dark:
        return {
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
            "primary_soft": "rgba(59, 130, 246, 0.16)",
            "indigo": "#818CF8",
            "indigo_soft": "rgba(129, 140, 248, 0.16)",
            "cyan": "#22D3EE",
            "cyan_soft": "rgba(34, 211, 238, 0.16)",
            "purple": "#A78BFA",
            "purple_soft": "rgba(167, 139, 250, 0.16)",
            "success": "#10B981",
            "success_soft": "rgba(16, 185, 129, 0.16)",
            "warning": "#F59E0B",
            "warning_soft": "rgba(245, 158, 11, 0.16)",
            "danger": "#F43F5E",
            "danger_soft": "rgba(244, 63, 94, 0.16)",
            "amber_tint": "#2B2112",
        }
    return {
        "window": "#D2DFEF",
        "surface": "#E3ECF9",
        "surface_alt": "#CFDDF3",
        "surface_elevated": "#BED0EC",
        "input": "#DAE6F7",
        "border": "#88A4CE",
        "border_bright": "#5A7CB2",
        "text": "#0A1628",
        "muted": "#283D5E",
        "primary": "#1D4ED8",
        "primary_soft": "rgba(29, 78, 216, 0.20)",
        "indigo": "#4338CA",
        "indigo_soft": "rgba(67, 56, 202, 0.20)",
        "cyan": "#0369A1",
        "cyan_soft": "rgba(3, 105, 161, 0.20)",
        "purple": "#6D28D9",
        "purple_soft": "rgba(109, 40, 217, 0.20)",
        "success": "#047857",
        "success_soft": "rgba(4, 120, 87, 0.20)",
        "warning": "#B45309",
        "warning_soft": "rgba(180, 83, 9, 0.22)",
        "danger": "#BE123C",
        "danger_soft": "rgba(190, 18, 60, 0.20)",
        "amber_tint": "#FCE0A2",
    }


def show_error(parent, title, message):
    QMessageBox.critical(parent, title, str(message))


def show_warning(parent, title, message):
    QMessageBox.warning(parent, title, str(message))


def show_success(parent, title, message):
    QMessageBox.information(parent, title, str(message))


def money(value):
    try:
        return f"₹{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def safe_text(value, fallback="N/A"):
    if value is None or str(value).strip() == "":
        return fallback
    return str(value)


def set_status_property(label, status):
    """Set a theme-compatible property for status-specific styling."""
    label.setProperty("status", str(status).lower())
    label.style().unpolish(label)
    label.style().polish(label)


def markdown_to_plain_text(markdown_text):
    """Convert Markdown release notes to readable plain text for simple prompts."""
    raw = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    # Strip optional fence language tags (e.g. ```text) so plain text output never merges them cleanly.
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]+\s*$", "```", raw, flags=re.MULTILINE)
    doc = QTextDocument()
    doc.setMarkdown(cleaned, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    return re.sub(r"\n{3,}", "\n\n", doc.toPlainText()).strip()


def markdown_to_themed_html(markdown_text, colors=None, title="", subtitle=""):
    """Render GitHub-style Markdown (headings, lists, code, links) into themed HTML."""
    c = colors or get_dialog_colors()
    is_dark = QColor(c["window"]).lightness() < 128
    link_color = c["cyan"] if is_dark else c["primary"]
    code_bg = c["surface_alt"]
    pre_bg = c["window"] if is_dark else c["surface"]

    raw = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    body_html = ""
    if raw:
        doc = QTextDocument()
        doc.setMarkdown(raw, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        qt_html = doc.toHtml()
        body_match = re.search(
            r"<body[^>]*>(.*)</body>",
            qt_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        body_html = body_match.group(1) if body_match else html.escape(raw)
        body_html = re.sub(
            r'(<a\b[^>]*>\s*<span\s+style="[^"]*?)color\s*:\s*#[0-9a-fA-F]{3,8}\s*;?',
            rf'\1color:{link_color}; text-decoration:underline;',
            body_html,
            flags=re.IGNORECASE,
        )
        body_html = re.sub(
            r'<a\b(?![^>]*style=)([^>]*)>',
            rf'<a\1 style="color:{link_color}; text-decoration:underline;">',
            body_html,
            flags=re.IGNORECASE,
        )
        body_html = re.sub(
            r'<span\s+style="([^"]*monospace[^"]*)"',
            lambda m: (
                f'<span style="{m.group(1)}; background-color:{code_bg}; '
                f'color:{c["text"]}; padding:1px 4px;"'
            ),
            body_html,
        )
        body_html = re.sub(
            r"<pre\b[^>]*>",
            (
                f'<pre style="background-color:{pre_bg}; color:{c["text"]}; '
                f'border:1px solid {c["border"]}; padding:8px 10px; '
                f'margin:6px 0px; white-space: pre-wrap; '
                f'font-family:\'Consolas\',\'Courier New\',monospace; '
                f'font-size:11px;">'
            ),
            body_html,
            flags=re.IGNORECASE,
        )
        body_html = re.sub(
            r"<h([1-4])\b[^>]*>",
            lambda m: (
                f'<h{m.group(1)} style="color:{c["primary"]}; '
                f'margin:10px 0px 4px 0px; font-weight:700;">'
            ),
            body_html,
            flags=re.IGNORECASE,
        )
        body_html = re.sub(
            r"<table\b[^>]*>",
            (
                f'<table border="1" cellspacing="0" cellpadding="5" '
                f'style="border-collapse:collapse; border:1px solid {c["border"]}; '
                f'margin:6px 0px;">'
            ),
            body_html,
            flags=re.IGNORECASE,
        )
        body_html = re.sub(
            r"<hr\b[^>]*>",
            f'<hr style="border:none; border-top:1px solid {c["border"]}; margin:8px 0px;">',
            body_html,
            flags=re.IGNORECASE,
        )

    header_parts = []
    if title:
        badge_html = ""
        if subtitle:
            badge_html = (
                f' <span style="background-color:{c["primary_soft"]}; '
                f'color:{link_color}; padding:2px 8px; font-size:11px; '
                f'font-weight:700;">{html.escape(subtitle)}</span>'
            )
        header_parts.append(
            f'<div style="margin-bottom:8px; padding-bottom:6px; '
            f'border-bottom:1px solid {c["border"]};">'
            f'<span style="font-size:14px; font-weight:800; color:{c["text"]};">'
            f'{html.escape(title)}</span>{badge_html}</div>'
        )

    return (
        f"<html><body style=\"color:{c['text']}; font-family:'Segoe UI',sans-serif; "
        f"font-size:12px; line-height:1.45;\">"
        + "".join(header_parts)
        + body_html
        + "</body></html>"
    )


# ============================================================
# BOOK DIALOG
# ============================================================

class BookDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, book_id=None, parent=None):
        super().__init__(parent)

        self.db = db
        self.book_id = book_id

        configure_dialog(
            self,
            "New Book" if book_id is None else "Edit Book",
            460,
            470,
            min_width=360,
            min_height=340,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        heading = create_heading(
            "📚 Add New Book" if book_id is None
            else f"✏️ Edit Book — {book_id}"
        )
        layout.addWidget(heading)

        form_host = QWidget()
        form_layout = QVBoxLayout(form_host)
        form_layout.setContentsMargins(0, 0, 4, 0)
        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=11)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("5-digit book ID")
        self.input_id.setMaxLength(5)

        id_regex = QRegularExpression(
            r"^[0-9]{5}$"
        )
        self.input_id.setValidator(
            QRegularExpressionValidator(id_regex, self.input_id)
        )

        if book_id is not None:
            self.input_id.setText(str(book_id))
            self.input_id.setReadOnly(True)

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Enter book title")
        self.input_title.setMaxLength(200)

        self.input_author = QLineEdit()
        self.input_author.setPlaceholderText("Enter author name")
        self.input_author.setMaxLength(100)

        self.input_publisher = QLineEdit()
        self.input_publisher.setPlaceholderText("Enter publisher")
        self.input_publisher.setMaxLength(100)

        self.input_total = QLineEdit()
        self.input_total.setValidator(
            QIntValidator(1, 99999, self.input_total)
        )
        self.input_total.setPlaceholderText("Total copies")

        self.input_available = QLineEdit()
        self.input_available.setValidator(
            QIntValidator(0, 99999, self.input_available)
        )
        self.input_available.setPlaceholderText("Available copies")

        if book_id is None:
            self.input_total.setText("1")
            self.input_available.setText("1")
        else:
            self.load_book_data()

        form.addRow("Book ID:", self.input_id)
        form.addRow("Title:", self.input_title)
        form.addRow("Author:", self.input_author)
        form.addRow("Publisher:", self.input_publisher)
        form.addRow("Total Copies:", self.input_total)
        form.addRow("Available Copies:", self.input_available)

        form_layout.addLayout(form)
        form_layout.addStretch()
        layout.addWidget(wrap_in_scroll_area(form_host, object_name="BookDialogScroll"), 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = create_button("Cancel", self.reject, variant="SecondaryButton")
        save = create_button(
            "💾 Save Book" if book_id is None else "💾 Update Book",
            self.save_book,
            variant="PrimaryButton",
        )

        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def load_book_data(self):
        try:
            success, row = self.db.get_book_details(self.book_id)

            if not success or not row:
                show_error(
                    self,
                    "Book Not Found",
                    "The selected book could not be loaded."
                )
                QTimer.singleShot(0, self.reject)
                return

            self.input_title.setText(str(row[1] or ""))
            self.input_author.setText(str(row[2] or ""))
            self.input_publisher.setText(str(row[3] or ""))
            self.input_total.setText(str(row[4] or 1))
            self.input_available.setText(str(row[5] or 0))

        except Exception as error:
            show_error(self, "Database Error", error)
            QTimer.singleShot(0, self.reject)

    def validate_counts(self):
        try:
            total = int(self.input_total.text())
            available = int(self.input_available.text())
        except ValueError:
            show_warning(
                self,
                "Invalid Copies",
                "Enter valid numeric copy counts."
            )
            return None

        if total < 1:
            show_warning(
                self,
                "Invalid Copies",
                "Total copies must be at least 1."
            )
            return None

        if available < 0 or available > total:
            show_warning(
                self,
                "Invalid Copies",
                "Available copies cannot exceed total copies."
            )
            return None

        return total, available

    def save_book(self):
        book_id = self.input_id.text().strip()
        title = self.input_title.text().strip()
        author = self.input_author.text().strip()
        publisher = self.input_publisher.text().strip()

        if not all([book_id, title, author, publisher]):
            show_warning(
                self,
                "Required Fields",
                "Please complete all book information."
            )
            return

        if self.book_id is None and not is_valid_book_id(book_id):
            show_warning(
                self,
                "Invalid Book ID",
                "Book ID must contain exactly 5 digits.",
            )
            return

        counts = self.validate_counts()

        if counts is None:
            return

        total, available = counts

        try:
            if self.book_id is None:
                success, message = self.db.insert_book(
                    book_id,
                    title,
                    author,
                    publisher,
                    total,
                    available
                )
            else:
                success, message = self.db.edit_book(
                    self.book_id,
                    title,
                    author,
                    publisher,
                    total,
                    available
                )

            if success:
                self.data_updated.emit()
                show_success(self, "Success", message)
                self.accept()
            else:
                show_warning(self, "Unable to Save", message)

        except Exception as error:
            show_error(self, "Database Error", error)


# ============================================================
# USER DIALOG
# ============================================================

class ComplaintDialog(QDialog):

    def __init__(
        self,
        db,
        parent=None,
        initial_user_id=None,
        initial_subject="",
        initial_body="",
    ):
        super().__init__(parent)
        self.db = db
        self._initial_user_id = str(initial_user_id or "").strip()

        configure_dialog(
            self,
            "Record Library Complaint",
            590,
            520,
            min_width=410,
            min_height=350,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(create_heading("New library complaint"))

        hint = QLabel(
            "Record a walk-in or desk complaint, or log one on a member's behalf. "
            "Students can also email complaints directly to the library Gmail."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        success, users = self.db.get_users()
        if not success:
            raise RuntimeError("Unable to load users for the complaint form.")
        self._all_users = [
            (str(u[0] or ""), str(u[1] or ""), str(u[6] or "") if len(u) > 6 else "")
            for u in users
        ]

        form_host = QWidget()
        form_host_layout = QVBoxLayout(form_host)
        form_host_layout.setContentsMargins(0, 0, 4, 0)
        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=10)

        self.user_filter_input = QLineEdit()
        self.user_filter_input.setClearButtonEnabled(True)
        self.user_filter_input.setPlaceholderText(
            "Filter member by Roll No, name, or email..."
        )
        self.user_filter_input.textChanged.connect(self._populate_user_combo)

        self.user_combo = QComboBox()
        self.user_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.user_combo.setMinimumContentsLength(16)
        self._populate_user_combo("")

        self.subject_input = QLineEdit()
        self.subject_input.setMaxLength(160)
        self.subject_input.setPlaceholderText("Short summary")
        if initial_subject:
            self.subject_input.setText(str(initial_subject))

        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText(
            "Describe the issue, suggestion, or complaint..."
        )
        self.body_input.setMinimumHeight(120)
        if initial_body:
            self.body_input.setPlainText(str(initial_body))

        form.addRow("Find Member:", self.user_filter_input)
        form.addRow("User:", self.user_combo)
        form.addRow("Subject:", self.subject_input)
        form.addRow("Details:", self.body_input)
        form_host_layout.addLayout(form)
        layout.addWidget(wrap_in_scroll_area(form_host, object_name="ComplaintDialogScroll"), 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(create_button("Cancel", self.reject, variant="SecondaryButton"))
        buttons.addWidget(
            create_button("Submit Complaint", self.submit_complaint, variant="PrimaryButton")
        )
        layout.addLayout(buttons)

    def _populate_user_combo(self, query=""):
        current_selected = self.user_combo.currentData()
        target_uid = (
            str(current_selected).strip()
            if current_selected
            else self._initial_user_id
        )
        q = str(query or "").strip().casefold()
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItem("General / anonymous", "")
        matched_index = 0
        for uid, name, email in self._all_users:
            if q and q not in uid.casefold() and q not in name.casefold() and q not in email.casefold():
                continue
            label = f"{name} ({uid})" if name else uid
            self.user_combo.addItem(label, uid)
            if target_uid and uid.casefold() == target_uid.casefold():
                matched_index = self.user_combo.count() - 1
        self.user_combo.setCurrentIndex(matched_index)
        self.user_combo.blockSignals(False)

    def submit_complaint(self):
        user_id = self.user_combo.currentData()
        subject = self.subject_input.text().strip()
        body = self.body_input.toPlainText().strip()

        if not subject or not body:
            show_warning(
                self,
                "Incomplete Complaint",
                "Enter both a subject and complaint details.",
            )
            return

        success, complaint = self.db.create_complaint(
            user_id,
            subject,
            body,
            source="DESK",
        )
        if not success:
            show_error(self, "Complaint Not Saved", complaint)
            return

        try:
            from email_service import LibraryEmailService

            LibraryEmailService(self.db).send_complaint_receipt(
                complaint
            )
        except Exception as error:
            show_warning(
                self,
                "Complaint Saved; Email Not Queued",
                f"Complaint #{complaint[0]} was saved locally, but the "
                f"email notification could not be added to the queue:\n\n{error}",
            )
            self.accept()
            return

        app = QApplication.instance()
        sync_manager = (
            getattr(app, "email_sync_manager", None) if app else None
        )
        if sync_manager:
            sync_manager.sync_now()

        show_success(
            self,
            "Complaint Submitted",
            f"Complaint #{complaint[0]} was saved and its notifications were "
            "added to the email queue.",
        )
        self.accept()


class GmailComplaintReviewDialog(QDialog):
    complaint_imported = pyqtSignal(int)

    def __init__(self, db, parent=None, prefetched_messages=None):
        super().__init__(parent)
        self.db = db
        self.messages = list(prefetched_messages or [])
        self._visible_messages = []
        self._closing = False
        self._stop_event = threading.Event()
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._active_worker = None
        self._users = []
        try:
            ok, users = self.db.get_users()
            if ok and users:
                self._users = [
                    (str(u[0] or ""), str(u[1] or ""), str(u[6] or "") if len(u) > 6 else "")
                    for u in users
                ]
        except Exception:
            self._users = []

        configure_dialog(
            self,
            "Review Gmail Inbox Complaints",
            960,
            640,
            min_width=460,
            min_height=360,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(create_heading("Review Gmail inbox for student complaints"))

        self.status_banner = QLabel(
            "Inspect recent inbox emails and import missed student complaints or ignore unrelated emails."
        )
        self.status_banner.setWordWrap(True)
        self.status_banner.setStyleSheet(
            f"background: {c['cyan_soft']}; color: {c['text']}; "
            f"border: 1px solid {c['cyan']}; border-left: 4px solid {c['cyan']}; "
            "border-radius: 7px; padding: 7px 10px; font-weight: 600;"
        )
        layout.addWidget(self.status_banner)

        filter_host = QWidget()
        filter_flow = FlowLayout(filter_host, margin=0, h_spacing=8, v_spacing=6)
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(250)
        self.search_input.setPlaceholderText("Search sender, subject, or body...")
        self.search_input.textChanged.connect(self._render_messages)
        self.hide_processed_checkbox = QCheckBox("Hide already imported / ignored")
        self.hide_processed_checkbox.setChecked(True)
        self.hide_processed_checkbox.toggled.connect(self._render_messages)
        self.hide_automated_checkbox = QCheckBox("Hide automated / alerts")
        self.hide_automated_checkbox.setChecked(True)
        self.hide_automated_checkbox.toggled.connect(self._render_messages)
        filter_flow.addWidget(self.search_input)
        filter_flow.addWidget(self.hide_processed_checkbox)
        filter_flow.addWidget(self.hide_automated_checkbox)
        layout.addWidget(filter_host)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "From", "Subject", "Rule / Match", "State", "Received",
        ])
        configure_table(self.table)
        self.table.setMinimumHeight(140)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(2, 200)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setMaximumHeight(130)
        self.preview_box.setPlaceholderText("Select an email to inspect its sender and message content.")
        layout.addWidget(self.preview_box)

        assign_host = QWidget()
        assign_flow = FlowLayout(assign_host, margin=0, h_spacing=8, v_spacing=6)
        assign_lbl = QLabel("Link to member:")
        assign_lbl.setStyleSheet("font-weight: 600;")
        self.assign_user_combo = QComboBox()
        self.assign_user_combo.setMinimumWidth(240)
        self.assign_user_combo.addItem("General / External Email Sender", "")
        for uid, name, _email in self._users:
            self.assign_user_combo.addItem(f"{name} ({uid})" if name else uid, uid)
        assign_flow.addWidget(assign_lbl)
        assign_flow.addWidget(self.assign_user_combo)
        layout.addWidget(assign_host)

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)
        self.refresh_btn = create_button(
            "↻ Refresh Gmail",
            self.refresh_from_gmail,
            variant="InfoButton",
        )
        self.import_btn = create_button(
            "Import as Complaint",
            self.import_selected_message,
            variant="PrimaryButton",
        )
        self.ignore_btn = create_button(
            "Ignore Email",
            self.ignore_selected_message,
            variant="WarningButton",
        )
        close_btn = create_button("Close", self.accept, variant="SecondaryButton")
        actions.addWidget(self.refresh_btn)
        actions.addWidget(self.import_btn)
        actions.addWidget(self.ignore_btn)
        actions.addWidget(close_btn)
        layout.addWidget(actions_host)

        self.import_btn.setEnabled(False)
        self.ignore_btn.setEnabled(False)

        if prefetched_messages is not None:
            self._render_messages()
        else:
            QTimer.singleShot(0, self.refresh_from_gmail)

    def _stop_workers(self):
        self._closing = True
        self._stop_event.set()
        self._thread_pool.waitForDone(1500)

    def done(self, result):
        self._stop_workers()
        super().done(result)

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)

    def refresh_from_gmail(self):
        if self._closing or self._active_worker is not None:
            return
        from email_queue import ComplaintImapInboxWorker
        from email_service import LibraryEmailService

        if not LibraryEmailService(self.db).is_configured():
            self.status_banner.setText(
                "Configure Gmail sender and App Password in Settings -> Email & Updates first."
            )
            return

        self.refresh_btn.setEnabled(False)
        self.status_banner.setText("Checking Gmail INBOX for recent emails...")
        worker = ComplaintImapInboxWorker(
            self.db.database_path,
            limit=40,
            lookback_days=14,
            stop_event=self._stop_event,
        )
        worker.signals.finished.connect(self._on_gmail_fetched)
        self._active_worker = worker
        self._thread_pool.start(worker)

    def _on_gmail_fetched(self, payload):
        self._active_worker = None
        if self._closing or sip.isdeleted(self):
            return
        self.refresh_btn.setEnabled(True)
        if not payload.get("ok"):
            err = payload.get("error") or "Unable to connect to Gmail IMAP."
            self.status_banner.setText(f"Gmail check failed: {err}")
            return
        self.messages = list(payload.get("messages") or [])
        self.status_banner.setText(
            f"Loaded {len(self.messages)} recent Gmail inbox email(s) from the last 14 days."
        )
        self._render_messages()

    def _render_messages(self):
        c = get_dialog_colors(self)
        query = self.search_input.text().strip().casefold()
        hide_processed = self.hide_processed_checkbox.isChecked()
        hide_auto = self.hide_automated_checkbox.isChecked()

        visible = []
        for msg in reversed(self.messages):
            imp_status = str(msg.get("import_status") or "").upper()
            if hide_processed and imp_status in ("IMPORTED", "IGNORED"):
                continue
            if hide_auto and msg.get("is_automated"):
                continue
            if query:
                hay = " ".join(
                    str(msg.get(k) or "")
                    for k in ("sender_name", "sender_email", "subject", "body", "matched_user_id")
                ).casefold()
                if query not in hay:
                    continue
            visible.append(msg)

        self._visible_messages = visible
        self.table.setRowCount(len(visible))
        for row_idx, msg in enumerate(visible):
            imp_status = str(msg.get("import_status") or "").upper()
            if imp_status == "IMPORTED":
                cid = msg.get("complaint_id")
                state_text = f"Imported (#{cid})" if cid else "Imported"
                state_key = "success"
            elif imp_status == "IGNORED":
                state_text = "Ignored"
                state_key = "muted"
            elif msg.get("is_automated"):
                state_text = "Automated"
                state_key = "muted"
            elif msg.get("matches_filter"):
                state_text = "Ready"
                state_key = "cyan"
            else:
                state_text = "Unfiltered"
                state_key = "warning"

            sender_lbl = msg.get("sender_name") or msg.get("sender_email") or "Unknown"
            if msg.get("matched_user_id"):
                sender_lbl = f"{sender_lbl} [{msg['matched_user_id']}]"

            row_vals = (
                sender_lbl,
                msg.get("subject") or "(No Subject)",
                msg.get("filter_reason") or msg.get("match_reason") or "",
                state_text,
                msg.get("received_at") or "",
            )
            for col_idx, val in enumerate(row_vals):
                item = QTableWidgetItem(str(val or ""))
                item.setData(Qt.ItemDataRole.UserRole, row_idx)
                if col_idx == 3:
                    item.setForeground(QColor(c[state_key]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table.setItem(row_idx, col_idx, item)

        if visible:
            self.table.selectRow(0)
        else:
            self.preview_box.setPlainText(
                "No matching inbox emails to review."
                if self.messages
                else "No recent Gmail inbox emails loaded yet. Click 'Refresh Gmail' to fetch."
            )
            self.import_btn.setEnabled(False)
            self.ignore_btn.setEnabled(False)

    def _current_message(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row_idx = rows[0].row()
        if 0 <= row_idx < len(self._visible_messages):
            return self._visible_messages[row_idx]
        return None

    def _on_selection_changed(self):
        msg = self._current_message()
        if not msg:
            self.import_btn.setEnabled(False)
            self.ignore_btn.setEnabled(False)
            return

        imp_status = str(msg.get("import_status") or "").upper()
        matched_uid = str(msg.get("matched_user_id") or "")
        combo_idx = self.assign_user_combo.findData(matched_uid)
        self.assign_user_combo.setCurrentIndex(combo_idx if combo_idx >= 0 else 0)

        self.preview_box.setPlainText(
            f"From: {msg.get('sender_name') or ''} <{msg.get('sender_email') or 'unknown'}>\n"
            f"Match: {msg.get('match_reason') or 'External'} | "
            f"Filter: {msg.get('filter_reason') or ''}\n\n"
            f"{msg.get('body') or '(Empty message)'}"
        )
        self.import_btn.setEnabled(imp_status != "IMPORTED")
        self.ignore_btn.setEnabled(imp_status != "IMPORTED")

    def import_selected_message(self):
        msg = self._current_message()
        if not msg:
            return
        selected_uid = str(self.assign_user_combo.currentData() or "").strip() or None
        ok, status_code, complaint_row = self.db.import_emailed_complaint(
            message_key=msg["message_key"],
            sender_email=msg.get("sender_email") or "",
            sender_name=msg.get("sender_name") or "",
            subject=msg.get("subject") or "(No Subject)",
            body=msg.get("body") or "(Empty message)",
            user_id=selected_uid,
            received_at=msg.get("received_at"),
            allow_if_ignored=True,
        )
        if not ok:
            if status_code == "ALREADY_IMPORTED":
                msg["import_status"] = "IMPORTED"
                self._render_messages()
                return
            show_error(self, "Import Failed", status_code)
            return

        msg["import_status"] = "IMPORTED"
        msg["complaint_id"] = complaint_row[0]
        msg["matched_user_id"] = selected_uid or ""

        auto_reply = str(
            self.db.get_setting("email_complaint_auto_reply", "1")
        ).casefold() in ("1", "true", "yes")
        if auto_reply:
            try:
                from email_service import LibraryEmailService

                LibraryEmailService(self.db).send_complaint_receipt(
                    complaint_row,
                    require_staff_email=False,
                    notify_staff=True,
                )
            except Exception as error:
                show_warning(
                    self,
                    "Imported; Receipt Not Queued",
                    f"Complaint #{complaint_row[0]} was imported, but the confirmation email could not be queued:\n\n{error}",
                )

        app = QApplication.instance()
        sync_manager = getattr(app, "email_sync_manager", None) if app else None
        if sync_manager:
            sync_manager.sync_now()

        self.complaint_imported.emit(int(complaint_row[0]))
        self.status_banner.setText(
            f"Imported email as Complaint #{complaint_row[0]}."
        )
        self._render_messages()

    def ignore_selected_message(self):
        msg = self._current_message()
        if not msg:
            return
        if self.db.mark_email_complaint_ignored(
            msg["message_key"],
            msg.get("sender_email") or "",
            msg.get("subject") or "",
        ):
            msg["import_status"] = "IGNORED"
            self.status_banner.setText("Marked selected email as ignored.")
            self._render_messages()


class ComplaintManagementDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.complaints = []
        self._closing = False
        self._stop_event = threading.Event()
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._imap_sync_worker = None
        configure_dialog(
            self,
            "Library Complaints",
            980,
            660,
            min_width=520,
            min_height=380,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(create_heading("Complaint inbox"))

        summary_host = QWidget()
        summary_flow = FlowLayout(summary_host, margin=0, h_spacing=8, v_spacing=6)
        self.summary_badge = QLabel()
        self.summary_badge.setStyleSheet(
            f"background: {c['primary_soft']}; color: {c['primary']}; "
            f"border: 1px solid {c['primary']}; border-radius: 10px; "
            "padding: 4px 10px; font-weight: 700; font-size: 11px;"
        )
        self.new_complaint_button = create_button(
            "+ New Complaint",
            self.open_new_complaint,
            variant="SuccessButton",
        )
        self.fetch_gmail_button = create_button(
            "↻ Fetch Gmail",
            self.fetch_emailed_complaints,
            variant="InfoButton",
        )
        self.review_gmail_button = create_button(
            "Review Gmail Inbox...",
            self.open_gmail_review_dialog,
            variant="SecondaryButton",
        )
        summary_flow.addWidget(self.summary_badge)
        summary_flow.addWidget(self.new_complaint_button)
        summary_flow.addWidget(self.fetch_gmail_button)
        summary_flow.addWidget(self.review_gmail_button)
        layout.addWidget(summary_host)

        self.imap_status_banner = QLabel()
        self.imap_status_banner.setWordWrap(True)
        self.imap_status_banner.setStyleSheet(
            f"color: {c['muted']}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(self.imap_status_banner)

        filters_host = QWidget()
        filters = FlowLayout(filters_host, margin=0, h_spacing=8, v_spacing=6)
        filters.addWidget(QLabel("Status:"))
        self.filter_status_combo = QComboBox()
        self.filter_status_combo.addItem("All", "ALL")
        self.filter_status_combo.addItem("Open", "OPEN")
        self.filter_status_combo.addItem("In Progress", "IN_PROGRESS")
        self.filter_status_combo.addItem("Resolved", "RESOLVED")
        self.filter_status_combo.currentIndexChanged.connect(self.load_complaints)
        filters.addWidget(self.filter_status_combo)

        filters.addWidget(QLabel("Source:"))
        self.filter_source_combo = QComboBox()
        self.filter_source_combo.addItem("All Sources", "ALL")
        self.filter_source_combo.addItem("From Email", "EMAIL")
        self.filter_source_combo.addItem("At Desk", "DESK")
        self.filter_source_combo.currentIndexChanged.connect(self.load_complaints)
        filters.addWidget(self.filter_source_combo)

        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(260)
        self.search_input.setPlaceholderText(
            "Search #ID, student, email, or subject..."
        )
        self.search_input.textChanged.connect(self.load_complaints)
        filters.addWidget(self.search_input)
        layout.addWidget(filters_host)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Source", "Member / Sender", "Subject", "Status", "Received",
        ])
        configure_table(self.table)
        self.table.setMinimumHeight(140)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        c_header = self.table.horizontalHeader()
        c_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        c_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        c_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        c_header.setStretchLastSection(False)
        self.table.setColumnWidth(2, 215)
        self.table.itemSelectionChanged.connect(
            self.show_selected_complaint
        )
        layout.addWidget(self.table, 1)

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setMaximumHeight(115)
        layout.addWidget(self.body_view)

        notes_host = QWidget()
        notes_layout = QHBoxLayout(notes_host)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(8)
        notes_lbl = QLabel("Staff Notes:")
        notes_lbl.setStyleSheet("font-weight: 600;")
        self.staff_notes_input = QLineEdit()
        self.staff_notes_input.setPlaceholderText(
            "Optional action taken, fine adjustment note, or follow-up details..."
        )
        notes_layout.addWidget(notes_lbl)
        notes_layout.addWidget(self.staff_notes_input, 1)
        layout.addWidget(notes_host)

        actions_host = QWidget()
        actions = QHBoxLayout(actions_host)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.status_combo = QComboBox()
        self.status_combo.addItem("Open", "OPEN")
        self.status_combo.addItem("In Progress", "IN_PROGRESS")
        self.status_combo.addItem("Resolved", "RESOLVED")
        self.update_status_button = create_button(
            "Update Status",
            self.update_status,
            variant="PrimaryButton",
        )
        self.reply_email_button = create_button(
            "Reply by Email",
            self.reply_to_selected_complaint,
            variant="InfoButton",
        )
        close_button = create_button("Close", self.accept, variant="SecondaryButton")
        actions.addWidget(self.status_combo)
        actions.addWidget(self.update_status_button)
        actions.addWidget(self.reply_email_button)
        actions.addStretch(1)
        actions.addWidget(close_button)
        layout.addWidget(actions_host)

        self._refresh_imap_banner()
        self.load_complaints()

    def _stop_workers(self):
        self._closing = True
        self._stop_event.set()
        self._thread_pool.waitForDone(1500)

    def done(self, result):
        self._stop_workers()
        super().done(result)

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)

    def _refresh_imap_banner(self, override_text=None):
        if override_text:
            self.imap_status_banner.setText(override_text)
            return
        from email_service import LibraryEmailService

        svc = LibraryEmailService(self.db)
        sender = str(self.db.get_setting("email_sender", "")).strip()
        if svc.is_configured():
            auto_on = str(
                self.db.get_setting("email_complaint_import_enabled", "1")
            ).casefold() in ("1", "true", "yes")
            mode = str(
                self.db.get_setting("email_complaint_filter_mode", "keywords")
            ).strip()
            mode_lbl = "Smart Filter" if mode != "all" else "All Inbox Emails"
            self.imap_status_banner.setText(
                f"Gmail intake ({sender}): {'Auto-sync ON' if auto_on else 'Manual sync'} · {mode_lbl}"
            )
            self.fetch_gmail_button.setEnabled(True)
            self.review_gmail_button.setEnabled(True)
        else:
            self.imap_status_banner.setText(
                "Configure Gmail sender & App Password in Settings -> Email & Updates to fetch student complaint emails."
            )
            self.fetch_gmail_button.setEnabled(False)
            self.review_gmail_button.setEnabled(False)

    def load_complaints(self):
        selected_id = self._selected_complaint_id()
        try:
            self.complaints = self.db.get_complaints_detailed(
                status=self.filter_status_combo.currentData(),
                source=self.filter_source_combo.currentData(),
                search=self.search_input.text().strip(),
            )
            counts = self.db.get_complaint_counts()
        except Exception as error:
            show_error(self, "Complaint Loading Error", error)
            return

        self.summary_badge.setText(
            f"{counts['open']} Open · {counts['in_progress']} In Progress · "
            f"{counts['resolved']} Resolved · {counts['email']} From Email"
        )

        c = get_dialog_colors(self)
        self.table.setRowCount(len(self.complaints))
        target_row = 0
        for row_index, complaint in enumerate(self.complaints):
            cid = int(complaint["id"])
            if selected_id is not None and cid == selected_id:
                target_row = row_index
            uid = complaint["user_id"]
            name = complaint["full_name"]
            email_addr = complaint["email"]
            if uid and name:
                user_label = f"{name} ({uid})"
            elif uid:
                user_label = uid
            elif name and email_addr and name.casefold() != email_addr.casefold():
                user_label = f"{name} <{email_addr}>"
            elif email_addr or name:
                user_label = email_addr or name
            else:
                user_label = "General / anonymous"

            raw_status = complaint["status"]
            source_text = "Email" if complaint["source"] == "EMAIL" else "Desk"
            values = (
                f"#{cid}",
                source_text,
                user_label,
                complaint["subject"],
                raw_status.replace("_", " ").title(),
                complaint["created_at"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.ItemDataRole.UserRole, cid)
                if column == 0:
                    item.setForeground(QColor(c["primary"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif column == 1:
                    item.setForeground(
                        QColor(c["cyan"] if source_text == "Email" else c["muted"])
                    )
                    f = item.font()
                    f.setBold(source_text == "Email")
                    item.setFont(f)
                elif column == 4:
                    color_key = (
                        "success"
                        if raw_status == "RESOLVED"
                        else "cyan"
                        if raw_status == "IN_PROGRESS"
                        else "warning"
                    )
                    item.setForeground(QColor(c[color_key]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table.setItem(row_index, column, item)

        if self.complaints:
            self.table.selectRow(target_row)
            self.show_selected_complaint()
        else:
            self.body_view.setPlainText("No complaints match the current filter.")
            self.staff_notes_input.clear()
            self.staff_notes_input.setEnabled(False)
            self.update_status_button.setEnabled(False)
            self.reply_email_button.setEnabled(False)

    def _selected_complaint_id(self):
        if not hasattr(self, "table"):
            return None
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_complaint(self):
        complaint_id = self._selected_complaint_id()
        if complaint_id is None:
            return None
        return next(
            (item for item in self.complaints if int(item["id"]) == int(complaint_id)),
            None,
        )

    def show_selected_complaint(self):
        complaint = self._selected_complaint()
        if not complaint:
            return

        source_label = "Emailed to Library Gmail" if complaint["source"] == "EMAIL" else "Recorded at Desk"
        member_tag = complaint["user_id"] or "Unmatched / Anonymous"
        sender_display = complaint["full_name"] or complaint["reporter_name"] or "Not specified"
        self.body_view.setPlainText(
            f"From: {sender_display} ({member_tag}) · Source: {source_label}\n"
            f"Email: {complaint['email'] or 'Not provided'} · Updated: {complaint['updated_at']}\n\n"
            f"{complaint['body']}"
        )
        index = self.status_combo.findData(complaint["status"])
        if index >= 0:
            self.status_combo.setCurrentIndex(index)
        self.staff_notes_input.setEnabled(True)
        self.staff_notes_input.setText(complaint.get("staff_notes") or "")
        self.update_status_button.setEnabled(True)
        self.reply_email_button.setEnabled(bool(str(complaint.get("email") or "").strip()))

    def update_status(self):
        complaint = self._selected_complaint()
        if not complaint:
            show_warning(
                self,
                "Select a Complaint",
                "Select a complaint to update its status.",
            )
            return

        success, message = self.db.update_complaint_status(
            complaint["id"],
            self.status_combo.currentData(),
            staff_notes=self.staff_notes_input.text().strip(),
        )
        if not success:
            show_error(self, "Status Update Failed", message)
            return

        self.load_complaints()

    def reply_to_selected_complaint(self):
        complaint = self._selected_complaint()
        if not complaint:
            return
        recipient = str(complaint.get("email") or "").strip()
        if not recipient:
            show_warning(
                self,
                "No Reply Email Address",
                "This complaint has no saved student or sender email address.",
            )
            return

        recipient_name = (
            complaint.get("full_name")
            or complaint.get("reporter_name")
            or recipient
        )
        initial_subject = f"Re: [Complaint #{complaint['id']}] {complaint['subject']}"
        note_text = self.staff_notes_input.text().strip()
        initial_body = (
            f"Hello {recipient_name},\n\n"
            f"Regarding your library complaint #{complaint['id']} "
            f"({complaint['subject']}):\n\n"
            f"{note_text + chr(10) + chr(10) if note_text else ''}"
            "Regards,\nLibrary Management System"
        )
        dialog = CustomEmailDialog(
            f"{recipient_name} <{recipient}>",
            self,
            initial_subject=initial_subject,
            initial_body=initial_body,
        )
        if not dialog.exec():
            return
        subject, body = dialog.get_data()
        try:
            self.db.enqueue_email(
                recipient,
                subject,
                body,
                "SYSTEM_ALERT",
            )
        except Exception as error:
            show_error(self, "Email Queue Failed", error)
            return

        app = QApplication.instance()
        sync_manager = getattr(app, "email_sync_manager", None) if app else None
        if sync_manager:
            sync_manager.sync_now()

        show_success(
            self,
            "Reply Queued",
            f"Reply to {recipient} was added to the email queue.",
        )

    def open_new_complaint(self):
        try:
            dialog = ComplaintDialog(self.db, self)
            if dialog.exec():
                self.load_complaints()
        except Exception as error:
            show_error(self, "Complaint Form Error", error)

    def fetch_emailed_complaints(self):
        if self._closing or self._imap_sync_worker is not None:
            return
        from email_queue import ComplaintImapSyncWorker

        self.fetch_gmail_button.setEnabled(False)
        self._refresh_imap_banner("Checking Gmail inbox for new student complaints...")
        worker = ComplaintImapSyncWorker(
            self.db.database_path,
            limit=40,
            lookback_days=14,
            stop_event=self._stop_event,
        )
        worker.signals.finished.connect(self._on_fetch_emailed_finished)
        self._imap_sync_worker = worker
        self._thread_pool.start(worker)

    def _on_fetch_emailed_finished(self, payload):
        self._imap_sync_worker = None
        if self._closing or sip.isdeleted(self):
            return
        self.fetch_gmail_button.setEnabled(True)
        if not payload.get("ok"):
            err = payload.get("error") or "Unknown Gmail IMAP error."
            self._refresh_imap_banner(f"Gmail sync failed: {err}")
            show_warning(self, "Gmail Fetch Failed", err)
            return

        summary = payload.get("summary") or {}
        imported = int(summary.get("imported", 0))
        checked = int(summary.get("checked", 0))
        matched = int(summary.get("matched_users", 0))
        if imported > 0:
            app = QApplication.instance()
            sync_manager = getattr(app, "email_sync_manager", None) if app else None
            if sync_manager:
                sync_manager.sync_now()
            self._refresh_imap_banner(
                f"Imported {imported} new emailed complaint(s) "
                f"({matched} matched to registered members)."
            )
            self.load_complaints()
        else:
            self._refresh_imap_banner(
                f"Checked {checked} recent Gmail message(s): no new unmatched complaints found."
            )

    def open_gmail_review_dialog(self):
        dialog = GmailComplaintReviewDialog(self.db, self)
        dialog.complaint_imported.connect(lambda _cid: self.load_complaints())
        dialog.exec()
        self.load_complaints()
        self._refresh_imap_banner()


class EmailQueueManagementDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.email_items = []
        configure_dialog(
            self,
            "Email Queue Manager",
            1100,
            680,
            min_width=500,
            min_height=380,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(create_heading("Email queue"))
        intro_label = QLabel(
            "Review messages without sending them. Delete selected messages, "
            "including sent history, or clear all pending and failed messages."
        )
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        filters_host = QWidget()
        filters = FlowLayout(filters_host, margin=0, h_spacing=8, v_spacing=6)
        filters.addWidget(QLabel("Show:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All", None)
        self.status_filter.addItem("Pending", "PENDING")
        self.status_filter.addItem("Failed", "FAILED")
        self.status_filter.addItem("Sent", "SENT")
        self.status_filter.currentIndexChanged.connect(self.load_items)
        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.count_label)
        layout.addWidget(filters_host)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Filter by recipient, subject, or message content"
        )
        self.search_input.textChanged.connect(self.filter_items)
        layout.addWidget(self.search_input)

        self.delivery_warning = QLabel()
        self.delivery_warning.setWordWrap(True)
        layout.addWidget(self.delivery_warning)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Recipient", "Subject", "Type", "Status",
            "Attempts", "Created",
        ])
        configure_table(self.table)
        self.table.setMinimumHeight(140)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.itemSelectionChanged.connect(self.show_selected_body)
        layout.addWidget(self.table, 1)

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setPlaceholderText(
            "Select a message to preview its body."
        )
        self.body_view.setMaximumHeight(110)
        layout.addWidget(self.body_view)

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)
        refresh_button = create_button("↻ Refresh", self.load_items, variant="InfoButton")
        self.delete_selected_button = create_button(
            "Delete Selected",
            self.delete_selected,
            variant="DangerButton",
        )
        self.delete_all_button = create_button(
            "Delete All Pending / Failed",
            self.delete_all_unsent,
            variant="DangerButton",
        )
        close_button = create_button("Close", self.accept, variant="SecondaryButton")
        actions.addWidget(refresh_button)
        actions.addWidget(self.delete_selected_button)
        actions.addWidget(self.delete_all_button)
        actions.addWidget(close_button)
        layout.addWidget(actions_host)
        self.load_items()

    def load_items(self):
        try:
            counts = self.db.get_email_queue_counts()
            selected_status = self.status_filter.currentData()
            self.email_items = self.db.get_email_queue_items(
                selected_status
            )
            delivery_enabled = str(
                self.db.get_setting("email_delivery_enabled", "0")
            ).casefold() in ("1", "true", "yes")
        except Exception as error:
            show_error(self, "Email Queue Error", error)
            return

        c = get_dialog_colors(self)
        self.count_label.setText(
            f"{counts['pending']} pending · {counts['failed']} failed · "
            f"{counts['sent']} sent"
        )
        self.count_label.setStyleSheet(
            f"background: {c['primary_soft']}; color: {c['primary']}; "
            f"border: 1px solid {c['primary']}; border-radius: 10px; "
            "padding: 4px 10px; font-weight: 700; font-size: 11px;"
        )
        self.delivery_warning.setText(
            "Queued delivery is enabled. Disable it in Settings before "
            "managing queued messages."
            if delivery_enabled
            else "Queued delivery is disabled. Messages will stay queued "
            "until you explicitly enable delivery in Settings."
        )
        warn_key = "warning" if delivery_enabled else "cyan"
        self.delivery_warning.setStyleSheet(
            f"background: {c[warn_key + '_soft']}; color: {c['text']}; "
            f"border: 1px solid {c[warn_key]}; border-left: 4px solid {c[warn_key]}; "
            "border-radius: 7px; padding: 7px 10px; font-weight: 600;"
        )

        self.filter_items()
        self._update_delete_buttons(delivery_enabled, counts)

    def filter_items(self):
        query = self.search_input.text().strip().casefold()
        visible_items = [
            email for email in self.email_items
            if not query
            or any(
                query in str(value or "").casefold()
                for value in (email[1], email[2], email[8])
            )
        ]
        c = get_dialog_colors(self)
        self.table.setRowCount(len(visible_items))
        for row_index, email in enumerate(visible_items):
            (
                email_id, recipient, subject, trigger, status,
                retry_count, created_at, _sent_at, _body,
            ) = email
            raw_status = str(status or "").upper()
            values = (
                email_id,
                recipient,
                subject,
                str(trigger).replace("_", " ").title(),
                status.title(),
                retry_count,
                created_at,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.ItemDataRole.UserRole, int(email_id))
                if column == 0:
                    item.setForeground(QColor(c["primary"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif column == 4:
                    color_key = (
                        "success"
                        if raw_status == "SENT"
                        else "danger"
                        if raw_status == "FAILED"
                        else "warning"
                    )
                    item.setForeground(QColor(c[color_key]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table.setItem(row_index, column, item)

        self.body_view.clear()

    def _update_delete_buttons(self, delivery_enabled, counts):
        self.delete_selected_button.setEnabled(
            bool(self.email_items) and not delivery_enabled
        )
        self.delete_all_button.setEnabled(
            counts["pending"] + counts["failed"] > 0
            and not delivery_enabled
        )

    def show_selected_body(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.body_view.clear()
            return
        selected_ids = {
            self.table.item(row.row(), 0).data(Qt.ItemDataRole.UserRole)
            for row in rows
        }
        selected = next(
            (
                email for email in self.email_items
                if int(email[0]) in selected_ids
            ),
            None,
        )
        if selected:
            self.body_view.setPlainText(str(selected[8] or ""))

    def _delivery_is_enabled(self):
        return str(
            self.db.get_setting("email_delivery_enabled", "0")
        ).casefold() in ("1", "true", "yes")

    def delete_selected(self):
        try:
            if self._delivery_is_enabled():
                show_warning(
                    self,
                    "Disable Email Delivery",
                    "Disable queued email delivery in Settings before "
                    "deleting queued messages.",
                )
                self.load_items()
                return

            rows = self.table.selectionModel().selectedRows()
            selected_ids = {
                int(self.table.item(row.row(), 0).data(
                    Qt.ItemDataRole.UserRole
                ))
                for row in rows
            }
            deletable_ids = [
                int(email[0])
                for email in self.email_items
                if int(email[0]) in selected_ids
            ]
            if not deletable_ids:
                show_warning(
                    self,
                    "Select Messages",
                    "Select one or more messages to delete.",
                )
                return
            selected_counts = {
                status: sum(
                    1 for email in self.email_items
                    if int(email[0]) in selected_ids and email[4] == status
                )
                for status in ("PENDING", "FAILED", "SENT")
            }
            summary = ", ".join(
                f"{count} {status.lower()}"
                for status, count in selected_counts.items()
                if count
            )
            answer = QMessageBox.question(
                self,
                "Delete Selected Messages",
                f"Permanently delete {len(deletable_ids)} selected message(s) "
                f"({summary})? Sent messages are part of the email history. "
                "This cannot be undone.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.db.delete_email_queue_items(deletable_ids)
        except Exception as error:
            show_error(self, "Email Queue Delete Error", error)
            return
        self.load_items()

    def delete_all_unsent(self):
        try:
            if self._delivery_is_enabled():
                show_warning(
                    self,
                    "Disable Email Delivery",
                    "Disable queued email delivery in Settings before "
                    "deleting queued messages.",
                )
                self.load_items()
                return
            counts = self.db.get_email_queue_counts()
            queued = counts["pending"] + counts["failed"]
            if queued == 0:
                return
            answer = QMessageBox.question(
                self,
                "Delete All Queued Messages",
                f"Permanently delete all {queued} pending or failed queued "
                "message(s)? Sent email history will be kept. This cannot "
                "be undone.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.db.delete_unsent_email_queue_items()
        except Exception as error:
            show_error(self, "Email Queue Delete Error", error)
            return
        self.load_items()


class VersionManagerDialog(QDialog):

    def __init__(
        self,
        releases,
        current_version,
        can_install,
        parent=None,
        install_reason="",
    ):
        super().__init__(parent)
        self.releases = list(releases)
        self.current_version = current_version
        self.can_install = can_install
        self.install_reason = str(install_reason or "").strip()
        self.selected_release = None
        configure_dialog(
            self,
            "Application Version Manager",
            980,
            640,
            min_width=460,
            min_height=380,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(create_heading("Published application versions"))
        version_intro = QLabel(
            f"Installed version: v{str(current_version).lstrip('vV')}. "
            "Select a published release below to read its release notes, "
            "install or roll back, or open it on GitHub."
        )
        version_intro.setWordWrap(True)
        layout.addWidget(version_intro)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Version", "Published", "Package", "Availability",
        ])
        configure_table(self.table)
        self.table.setMinimumHeight(110)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.itemSelectionChanged.connect(self.show_release_details)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        self.details = QTextBrowser()
        self.details.setObjectName("ReleaseNotesBrowser")
        self.details.setReadOnly(True)
        self.details.setOpenExternalLinks(True)
        self.details.setMinimumHeight(140)
        self.details.setStyleSheet(
            f"QTextBrowser#ReleaseNotesBrowser {{"
            f" background-color: {c['input']};"
            f" color: {c['text']};"
            f" border: 1.5px solid {c['border']};"
            f" border-radius: 8px;"
            f" padding: 8px 10px;"
            f"}}"
        )

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([200, 260])
        layout.addWidget(splitter, 1)

        self.install_status_label = QLabel(
            "Only stable releases with a verified Library-Windows.zip can "
            "be installed."
        )
        configure_wrapped_label(self.install_status_label)
        self.install_status_label.setStyleSheet(
            f"color: {c['muted']}; font-size: 12px;"
        )
        layout.addWidget(self.install_status_label)

        self.install_button = create_button(
            "Install / Roll Back to Selected",
            self.install_selected,
            enabled=False,
            variant="PrimaryButton" if can_install else "SecondaryButton",
        )
        self.open_release_button = create_button(
            "Download Installer on GitHub",
            self.open_selected_release,
            enabled=True,
            variant="PrimaryButton" if not can_install else "InfoButton",
        )
        close_button = create_button("Close", self.reject, variant="SecondaryButton")

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)
        actions.addWidget(self.install_button)
        actions.addWidget(self.open_release_button)
        actions.addWidget(close_button)
        layout.addWidget(actions_host)
        self._populate()

    def _selected_release_record(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or index < 0 or index >= len(self.releases):
            return None
        return self.releases[index]

    def _sync_action_button_cursor(self, enabled):
        self.install_button.setEnabled(enabled)
        self.install_button.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )

    def _populate(self):
        c = get_dialog_colors(self)
        self.table.setRowCount(len(self.releases))
        for row, release in enumerate(self.releases):
            installable = bool(release.get("installable"))
            is_current = bool(release.get("current"))
            package_text = (
                "Verified"
                if installable
                else "Unavailable"
            )
            availability = (
                "Installed version"
                if is_current
                else (
                    "Ready to install"
                    if installable
                    else release.get("reason", "Package unavailable")
                )
            )
            values = (
                release["tag_name"],
                release.get("published_at", ""),
                package_text,
                availability,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    item.setForeground(QColor(c["primary"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif column == 2:
                    item.setForeground(QColor(c["success"] if installable else c["muted"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif column == 3:
                    color_key = (
                        "cyan"
                        if is_current
                        else "primary"
                        if installable
                        else "warning"
                    )
                    item.setForeground(QColor(c[color_key]))
                self.table.setItem(row, column, item)
        if self.releases:
            self.table.selectRow(0)
        else:
            self.details.setHtml(
                markdown_to_themed_html(
                    "No stable numeric releases were found on GitHub.",
                    colors=c,
                    title="No Published Releases",
                )
            )
            self._sync_action_button_cursor(False)
            self.install_button.setText("Install Unavailable")
            self.install_status_label.setText(
                self.install_reason
                or "No published stable releases were found. You can still open GitHub Releases."
            )

    def show_release_details(self):
        c = get_dialog_colors(self)
        release = self._selected_release_record()
        if not release:
            self.details.clear()
            self._sync_action_button_cursor(False)
            self.install_button.setText("Install / Roll Back to Selected")
            self.install_status_label.setText(
                self.install_reason
                or "Select a published release from the table above."
            )
            return

        is_current = bool(release.get("current"))
        installable = bool(release.get("installable"))
        tag = release["tag_name"]
        notes = release.get("release_notes", "").strip()
        subtitle = "Currently Installed" if is_current else "Published Release"
        self.details.setHtml(
            markdown_to_themed_html(
                notes or release.get("reason") or "No release notes provided.",
                colors=c,
                title=tag,
                subtitle=subtitle,
            )
        )

        can_apply_now = self.can_install and installable and not is_current
        self._sync_action_button_cursor(can_apply_now)
        self.install_button.setObjectName(
            "PrimaryButton" if can_apply_now else "SecondaryButton"
        )
        self.install_button.style().unpolish(self.install_button)
        self.install_button.style().polish(self.install_button)

        if is_current:
            self.install_button.setText(f"Installed ({tag})")
            self.install_button.setToolTip(
                f"{tag} is currently installed. Select a different version to upgrade or roll back."
            )
            self.install_status_label.setStyleSheet(
                f"color: {c['muted']}; font-size: 12px;"
            )
            self.install_status_label.setText(
                f"{tag} is currently installed. Select another release to install or roll back, "
                "or click 'Download Installer on GitHub' to view/download the installer."
            )
        elif not self.can_install:
            self.install_button.setText("In-App Install (EXE Only)")
            self.install_button.setToolTip(
                self.install_reason
                or "In-app installation works only in the packaged Windows app (Library.exe)."
            )
            self.install_status_label.setStyleSheet(
                f"color: {c['warning']}; font-size: 12px; font-weight: 600;"
            )
            self.install_status_label.setText(
                self.install_reason
                or "Running from Python source or a read-only folder — in-app replacement requires "
                "the installed Windows app (Library.exe). Click 'Download Installer on GitHub' to install this version."
            )
        elif not installable:
            self.install_button.setText("Package Unavailable")
            self.install_button.setToolTip(
                release.get("reason")
                or f"Release {tag} cannot be installed automatically."
            )
            self.install_status_label.setStyleSheet(
                f"color: {c['warning']}; font-size: 12px; font-weight: 600;"
            )
            self.install_status_label.setText(
                release.get("reason")
                or f"Release {tag} cannot be installed automatically."
            )
        else:
            try:
                newer = is_newer_version(tag, self.current_version)
            except ValueError:
                newer = True
            self.install_button.setText(
                f"Install Update ({tag})" if newer else f"Roll Back to {tag}"
            )
            self.install_button.setToolTip(
                f"Download and install {tag} and restart the application."
            )
            size_mb = float(release.get("size", 0) or 0) / (1024 * 1024)
            self.install_status_label.setStyleSheet(
                f"color: {c['success']}; font-size: 12px; font-weight: 600;"
            )
            self.install_status_label.setText(
                f"Ready to {'upgrade' if newer else 'roll back'} to {tag} "
                f"({size_mb:.1f} MB verified package). Click '{self.install_button.text()}' to begin."
            )

    def _on_row_double_clicked(self, _row, _column):
        release = self._selected_release_record()
        if not release:
            return
        if (
            self.can_install
            and release.get("installable")
            and not release.get("current")
        ):
            self.install_selected()
            return
        tag = release.get("tag_name", "this version")
        if release.get("current"):
            show_success(
                self,
                "Already Installed",
                f"{tag} is currently installed.\n\n"
                "Select a different published version to upgrade or roll back, or "
                "click 'Download Installer on GitHub' to view release files.",
            )
            return
        if not self.can_install:
            msg = QMessageBox(self)
            msg.setWindowTitle("Packaged Windows App Required")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                self.install_reason
                or "Automatic in-app replacement works only when running the installed Windows application (Library.exe)."
            )
            open_btn = msg.addButton(
                "Download Installer on GitHub",
                QMessageBox.ButtonRole.AcceptRole,
            )
            msg.addButton(QMessageBox.StandardButton.Close)
            msg.exec()
            if msg.clickedButton() is open_btn:
                self.open_selected_release()
            return
        show_warning(
            self,
            "Release Unavailable",
            release.get("reason")
            or f"Release {tag} cannot be installed automatically.",
        )

    def open_selected_release(self):
        release = self._selected_release_record()
        target_url = (
            (release or {}).get("release_url")
            or RELEASES_PAGE_URL
        )
        opened = QDesktopServices.openUrl(QUrl(target_url))
        c = get_dialog_colors(self)
        if opened:
            self.install_status_label.setStyleSheet(
                f"color: {c['cyan']}; font-size: 12px; font-weight: 600;"
            )
            self.install_status_label.setText(
                f"Opened GitHub release page in your browser ({target_url})."
            )
        else:
            QApplication.clipboard().setText(target_url)
            show_warning(
                self,
                "Could Not Open Browser",
                f"Could not launch browser automatically. URL copied to clipboard:\n{target_url}",
            )

    def install_selected(self):
        release = self._selected_release_record()
        if not release:
            return
        if (
            not self.can_install
            or not release.get("installable")
            or release.get("current")
        ):
            return
        self.selected_release = {
            "available": True,
            "current_version": self.current_version,
            "latest_version": release["tag_name"],
            "version_selection": True,
            "release_notes": release.get("release_notes", ""),
            "release_url": release.get("release_url", ""),
            "download_url": release["download_url"],
            "digest": release["digest"],
            "size": release["size"],
        }
        self.accept()


class UpdateConfirmationDialog(QDialog):
    """Themed update prompt that renders GitHub release notes Markdown cleanly as HTML."""

    def __init__(
        self,
        latest_version,
        current_version,
        release_notes="",
        version_selection=False,
        is_upgrade=True,
        release_url="",
        parent=None,
    ):
        super().__init__(parent)
        self.release_url = str(release_url or "").strip()
        ver_tag = f"v{str(latest_version or '').lstrip('vV')}"
        cur_tag = f"v{str(current_version or '').lstrip('vV')}"

        configure_dialog(
            self,
            "Application Update Available",
            720,
            520,
            min_width=420,
            min_height=300,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)

        if version_selection:
            action_word = "upgrade to" if is_upgrade else "roll back to"
            heading_text = f"Confirm Release Install — {ver_tag}"
            intro_text = (
                f"Version {ver_tag} is selected (installed: {cur_tag}). "
                f"Do you want to {action_word} this release? "
                "The application will close and restart."
            )
            install_label = f"Install {ver_tag}" if is_upgrade else f"Roll Back to {ver_tag}"
        else:
            heading_text = f"Update Available — {ver_tag}"
            intro_text = (
                f"Version {ver_tag} is available (currently {cur_tag}). "
                "Install it now? The application will close and restart."
            )
            install_label = f"Install {ver_tag}"

        layout.addWidget(create_heading(heading_text))
        intro_label = QLabel(intro_text)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        notes = str(release_notes or "").strip()
        self.notes_browser = QTextBrowser()
        self.notes_browser.setObjectName("UpdateReleaseNotesBrowser")
        self.notes_browser.setReadOnly(True)
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setMinimumHeight(180)
        self.notes_browser.setStyleSheet(
            f"QTextBrowser#UpdateReleaseNotesBrowser {{"
            f" background-color: {c['input']};"
            f" color: {c['text']};"
            f" border: 1.5px solid {c['border']};"
            f" border-radius: 8px;"
            f" padding: 8px 10px;"
            f"}}"
        )
        self.notes_browser.setHtml(
            markdown_to_themed_html(
                notes or "No release notes were provided for this version.",
                colors=c,
                title=f"Release {ver_tag}",
                subtitle="Upgrade" if is_upgrade else "Selected Version",
            )
        )
        layout.addWidget(self.notes_browser, 1)

        self.install_button = create_button(
            install_label,
            self.accept,
            variant="PrimaryButton",
        )
        self.github_button = None
        if self.release_url:
            self.github_button = create_button(
                "View on GitHub",
                lambda: QDesktopServices.openUrl(QUrl(self.release_url)),
                variant="InfoButton",
            )
        self.later_button = create_button(
            "Later",
            self.reject,
            variant="SecondaryButton",
        )
        self.later_button.setDefault(True)

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)
        actions.addWidget(self.install_button)
        if self.github_button is not None:
            actions.addWidget(self.github_button)
        actions.addWidget(self.later_button)
        layout.addWidget(actions_host)


class UserDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, user_id=None, parent=None):
        super().__init__(parent)

        self.db = db
        self.user_id = user_id

        configure_dialog(
            self,
            "Register User" if user_id is None else "Edit User",
            460,
            520,
            min_width=360,
            min_height=340,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        layout.addWidget(
            create_heading(
                "👤 Register New User" if user_id is None
                else f"✏️ Edit User — {user_id}"
            )
        )

        form_host = QWidget()
        form_host_layout = QVBoxLayout(form_host)
        form_host_layout.setContentsMargins(0, 0, 4, 0)
        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=11)

        self.combo_role = QComboBox()
        self.combo_role.addItems([
            "Select Role",
            "Student",
            "Faculty",
            "Guest Lecturer",
            "Librarian",
            "Admin"
        ])

        self.lbl_department = QLabel("Department:")
        self.combo_department = QComboBox()
        self.combo_department.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo_department.setMinimumContentsLength(14)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("Select a role first")
        self.input_id.setEnabled(False)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Full name")
        self.input_name.setMaxLength(100)

        self.input_phoneno = QLineEdit()
        self.input_phoneno.setPlaceholderText("10-digit mobile number")
        self.input_phoneno.setMaxLength(10)

        phone_regex = QRegularExpression(r"^[0-9]{10}$")
        self.input_phoneno.setValidator(
            QRegularExpressionValidator(
                phone_regex,
                self.input_phoneno
            )
        )

        self.input_email = QLineEdit()
        self.input_email.setPlaceholderText(
            "Email for due-date reminders"
        )
        self.input_email.setMaxLength(254)

        form.addRow("Role:", self.combo_role)
        form.addRow(self.lbl_department, self.combo_department)
        form.addRow("User ID / PIN:", self.input_id)
        form.addRow("Full Name:", self.input_name)
        form.addRow("Phone:", self.input_phoneno)
        form.addRow("Email:", self.input_email)

        form_host_layout.addLayout(form)
        form_host_layout.addStretch()
        layout.addWidget(wrap_in_scroll_area(form_host, object_name="UserDialogScroll"), 1)

        self.combo_role.currentTextChanged.connect(
            self.on_role_changed
        )

        if user_id is not None:
            self.load_user_data()

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(create_button("Cancel", self.reject, variant="SecondaryButton"))
        buttons.addWidget(
            create_button(
                "💾 Save User",
                self.save_user,
                variant="PrimaryButton",
            )
        )

        layout.addLayout(buttons)

    def load_user_data(self):
        try:
            success, row = self.db.get_user_details(self.user_id)

            if not success or not row:
                show_error(
                    self,
                    "User Not Found",
                    "The selected user could not be loaded."
                )
                QTimer.singleShot(0, self.reject)
                return

            self.input_id.setText(str(self.user_id))
            self.input_id.setReadOnly(True)

            self.input_name.setText(str(row[1] or ""))
            self.input_phoneno.setText(str(row[2] or ""))
            self.input_email.setText(
                str(row[6] or "") if len(row) > 6 else ""
            )

            role = normalize_user_role(row[3]) or str(row[3] or "")
            department = str(row[4] or "")

            self.combo_role.setCurrentText(role)
            self.on_role_changed(role)

            if hasattr(self.db, "normalize_department_for_role"):
                canonical_department = (
                    self.db.normalize_department_for_role(department, role)
                    or department
                )
            else:
                canonical_department = (
                    normalize_department_for_role(department, role)
                    or department
                )
            index = self.combo_department.findText(
                canonical_department,
                Qt.MatchFlag.MatchFixedString,
            )

            if index >= 0:
                self.combo_department.setCurrentIndex(index)
            elif canonical_department and role in (
                "Student",
                "Faculty",
                "Guest Lecturer",
            ):
                self.combo_department.addItem(canonical_department)
                self.combo_department.setCurrentIndex(
                    self.combo_department.count() - 1
                )

        except Exception as error:
            show_error(self, "Database Error", error)
            QTimer.singleShot(0, self.reject)

    def on_role_changed(self, role):
        self.combo_department.clear()
        self.combo_department.addItem("Select Option")

        self.set_id_validator(role)

        if role == "Student":
            self.lbl_department.show()
            self.combo_department.show()
            self.lbl_department.setText("Student Branch:")

            for branch in self.db.get_departments("STUDENT") or []:
                self.combo_department.addItem(str(branch))

        elif role in ("Faculty", "Guest Lecturer"):
            self.lbl_department.show()
            self.combo_department.show()
            self.lbl_department.setText("Branch / Department:")

            for department in self.db.get_departments("FACULTY") or []:
                self.combo_department.addItem(str(department))

        else:
            self.lbl_department.hide()
            self.combo_department.hide()

    def set_id_validator(self, role):
        if role == "Student":
            regex = QRegularExpression(
                r"^[0-9]{5}-[A-Za-z]{2}-[0-9]{3}$"
            )
            placeholder = "Example: 24001-CS-097"

        elif role in (
            "Faculty",
            "Guest Lecturer",
            "Admin",
            "Librarian"
        ):
            regex = QRegularExpression(r"^[0-9]{6}$")
            placeholder = "6-digit ID (e.g. 123456)"

        else:
            regex = QRegularExpression(r"^$")
            placeholder = "Select a role first"

        self.input_id.setValidator(
            QRegularExpressionValidator(regex, self.input_id)
        )

        if not self.input_id.isReadOnly():
            self.input_id.setEnabled(role != "Select Role")
            self.input_id.setPlaceholderText(placeholder)

            if role == "Select Role":
                self.input_id.clear()

    def save_user(self):
        user_id = self.input_id.text().strip()
        name = self.input_name.text().strip()
        phone = self.input_phoneno.text().strip()
        email = self.input_email.text().strip()
        role = self.combo_role.currentText()

        if role == "Select Role":
            show_warning(self, "Validation Error", "Select a user role.")
            return

        if not user_id or not name:
            show_warning(
                self,
                "Validation Error",
                "User ID and full name are required."
            )
            return

        if not all(char.isalpha() or char in " .'-" for char in name):
            show_warning(
                self,
                "Invalid Name",
                "Name contains invalid characters."
            )
            return

        if phone and not is_valid_phone_number(phone):
            show_warning(
                self,
                "Invalid Phone",
                "Enter exactly 10 digits for the phone number."
            )
            return

        if email and (
            "@" not in email
            or email.startswith("@")
            or email.endswith("@")
            or "." not in email.rsplit("@", 1)[-1]
        ):
            show_warning(
                self,
                "Invalid Email",
                "Enter a valid email address for reminders and replies."
            )
            return

        if self.user_id is None and not is_valid_user_id(user_id, role):
            show_warning(
                self,
                "Invalid User ID",
                "Students must use 5 digits, a 2-letter branch, and 3 digits "
                "(for example, 24001-CS-097). Other user roles must use "
                "exactly 6 digits (for example, 123456).",
            )
            return

        user_id = user_id.upper()

        if role in ("Student", "Faculty", "Guest Lecturer"):
            department = self.combo_department.currentText()

            if department == "Select Option":
                show_warning(
                    self,
                    "Department Required",
                    "Select a valid branch or department."
                )
                return
        else:
            department = "General Administration"

        try:
            if self.user_id is None:
                success, message = self.db.insert_user(
                    user_id,
                    name,
                    phone,
                    role,
                    department,
                    email,
                )
            else:
                success, message = self.db.edit_user(
                    self.user_id,
                    name,
                    phone,
                    role,
                    department,
                    email,
                )

            if success:
                self.data_updated.emit()
                show_success(self, "Success", message)
                self.accept()
            else:
                show_warning(self, "Unable to Save", message)

        except Exception as error:
            show_error(self, "Database Error", error)


# ============================================================
# USER CIRCULATION HISTORY
# ============================================================

class ViewBooksDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, user_id, parent=None):
        super().__init__(parent)

        self.db = db
        self.user_id = user_id
        self.books_data = []
        self._splitter_vertical = None
        self._compact_table_mode = None

        configure_dialog(
            self,
            f"Circulation History — {user_id}",
            1050,
            620,
            min_width=480,
            min_height=360,
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        main_layout.addWidget(
            create_heading(f"📋 Circulation History — User {user_id}")
        )

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(6)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Book ID",
            "Title",
            "Author",
            "Status",
            "Issue Date",
            "Due Date",
            "Renewals",
            "Fine"
        ])

        configure_table(self.table)
        self.table.setMinimumHeight(160)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._apply_table_column_modes()

        self.detail_container = QFrame()
        self.detail_container.setObjectName("DialogInspector")
        c_panel = get_dialog_colors(self)
        self.detail_container.setStyleSheet(
            f"#DialogInspector {{ background-color: {c_panel['surface']}; "
            f"border: 1px solid {c_panel['border']}; border-radius: 12px; }}"
        )

        detail_outer = QVBoxLayout(self.detail_container)
        detail_outer.setContentsMargins(10, 10, 10, 10)
        detail_outer.setSpacing(0)

        self.detail_content = QWidget()
        self.detail_content.setObjectName("LoanInspectorContent")
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(4, 4, 6, 4)
        self.detail_layout.setSpacing(10)

        self.detail_scroll = wrap_in_scroll_area(
            self.detail_content,
            object_name="LoanInspectorScroll",
        )
        detail_outer.addWidget(self.detail_scroll)

        self.table.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        self.content_splitter.addWidget(self.table)
        self.content_splitter.addWidget(self.detail_container)
        self._sync_responsive_layout()

        main_layout.addWidget(self.content_splitter, 1)

        self.show_default_inspector()
        self.load_user_books()

    def _apply_table_column_modes(self):
        compact = self.width() < 860
        if compact == self._compact_table_mode:
            return
        self._compact_table_mode = compact
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(55)
        for col in (0, 3, 4, 5, 6, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        if compact:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(1, 180)
            self.table.setColumnWidth(2, 130)
        else:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _sync_responsive_layout(self):
        self._splitter_vertical = sync_responsive_splitter(
            self.content_splitter,
            self.detail_container,
            self.width() - 36,
            breakpoint=820,
            max_panel_width=340,
            min_panel_width=240,
            min_panel_height=190,
            current_vertical=self._splitter_vertical,
        )
        self._apply_table_column_modes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "content_splitter"):
            self._sync_responsive_layout()

    def show_default_inspector(self):
        clear_layout(self.detail_layout)

        self.detail_layout.addWidget(
            create_heading("🔍 Record Inspector")
        )

        hint = QLabel(
            "Select a circulation record to view its complete details."
        )
        hint.setWordWrap(True)

        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_user_books(self):
        try:
            self.books_data = self.db.get_user_books_status(
                self.user_id
            ) or []
            self._loan_extras = self.db.conn.execute("""
                SELECT COALESCE(NULLIF(c.log_code, ''), CAST(c.id AS TEXT)),
                       COALESCE(c.renewal_count, 0),
                       COALESCE(c.last_renewed_at, ''),
                       COALESCE(c.fine_settled, 0),
                       COALESCE(c.fine_settlement_action, '')
                FROM circulation_logs c
                JOIN books b ON c.book_id = b.id
                WHERE c.user_id = ?
                ORDER BY c.id DESC
            """, (str(self.user_id).strip(),)).fetchall()
            self._max_renewals = self.db.get_max_renewals()
            today_str = datetime.date.today().isoformat()

            self.table.blockSignals(True)
            self.table.setRowCount(0)

            self.table.setRowCount(len(self.books_data))

            for row_index, book in enumerate(self.books_data):
                (
                    book_id,
                    title,
                    author,
                    publisher,
                    status,
                    checkout,
                    due,
                    returned,
                    fine
                ) = book

                extras = (
                    self._loan_extras[row_index]
                    if row_index < len(self._loan_extras)
                    else (None, 0, "", 0, "")
                )
                ren_count = int(extras[1] or 0)
                fine_settled = int(extras[3] or 0) == 1 or str(status).upper() == "PAID"
                fine_action = str(extras[4] or "").upper()
                try:
                    fine_val = float(fine or 0.0)
                except (TypeError, ValueError):
                    fine_val = 0.0

                raw_status = str(status).upper()
                due_text = safe_text(due)
                if raw_status == "ISSUED" and due_text and due_text[:10] < today_str:
                    status_text = "OVERDUE"
                elif raw_status == "ISSUED" and due_text and due_text[:10] == today_str:
                    status_text = "DUE TODAY"
                else:
                    status_text = raw_status

                ren_text = (
                    f"{ren_count}/{self._max_renewals}"
                    if self._max_renewals > 0
                    else str(ren_count)
                ) if ren_count > 0 else "0"
                fine_text = money(fine_val)
                if fine_val > 0 and fine_settled:
                    badge = "Waived" if fine_action == "WAIVED" else "Paid"
                    fine_text = f"{fine_text} ({badge})"

                values = [
                    safe_text(book_id),
                    safe_text(title),
                    safe_text(author),
                    status_text,
                    safe_text(checkout),
                    due_text,
                    ren_text,
                    fine_text,
                ]

                c = get_dialog_colors(self)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if column == 0:
                        item.setForeground(QColor(c["primary"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 3:
                        if status_text == "OVERDUE":
                            item.setForeground(QColor(c["danger"]))
                        elif status_text == "DUE TODAY":
                            item.setForeground(QColor(c["warning"]))
                        elif status_text == "ISSUED":
                            item.setForeground(QColor(c["primary"]))
                        else:
                            item.setForeground(QColor(c["success"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 6 and ren_count > 0:
                        item.setForeground(QColor(c["cyan"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 7 and fine_val > 0 and not fine_settled:
                        item.setForeground(QColor(c["danger"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)

                    self.table.setItem(row_index, column, item)

            self.table.blockSignals(False)

            if self.books_data:
                self.table.selectRow(0)
                self.display_record_details(0)
            else:
                self.show_default_inspector()

        except Exception as error:
            self.table.blockSignals(False)
            show_error(self, "History Error", error)

    def on_selection_changed(self, *args):
        selected = self.table.selectionModel().selectedRows()

        if not selected:
            self.show_default_inspector()
            return

        row = selected[0].row()

        if 0 <= row < len(self.books_data):
            self.display_record_details(row)

    def display_record_details(self, row_or_book):
        if isinstance(row_or_book, int):
            row_index = row_or_book
            book = self.books_data[row_index]
        else:
            book = row_or_book
            try:
                row_index = self.books_data.index(book)
            except ValueError:
                row_index = -1

        (
            book_id,
            title,
            author,
            publisher,
            status,
            checkout,
            due,
            returned,
            fine
        ) = book

        extras = (
            self._loan_extras[row_index]
            if 0 <= row_index < len(getattr(self, "_loan_extras", []))
            else (None, 0, "", 0, "")
        )
        loan_id, ren_count, last_renewed, fine_settled_flag, fine_action = extras
        try:
            fine_val = float(fine or 0.0)
        except (TypeError, ValueError):
            fine_val = 0.0
        fine_settled = bool(int(fine_settled_flag or 0) == 1 or str(status).upper() == "PAID")

        clear_layout(self.detail_layout)

        raw_status = str(status).upper()
        is_issued = raw_status == "ISSUED"
        today_str = datetime.date.today().isoformat()
        is_overdue = bool(is_issued and safe_text(due) and safe_text(due)[:10] < today_str)

        self.detail_layout.addWidget(
            create_heading("Loan Control Center")
        )

        banner = QLabel(
            "🔴 Overdue Book"
            if is_overdue else
            "🟠 Issued Book"
            if is_issued else
            "🟢 Returned Record"
        )
        banner.setWordWrap(True)
        set_status_property(
            banner,
            "overdue" if is_overdue else "issued" if is_issued else "returned"
        )

        self.detail_layout.addWidget(banner)

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=7)

        max_r = getattr(self, "_max_renewals", 0)
        ren_display = f"{ren_count} / {max_r}" if max_r > 0 else f"{ren_count} (Unlimited)"
        if fine_val <= 0:
            fine_status = "No Fine"
        elif fine_settled:
            fine_status = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
        else:
            fine_status = "Unpaid Balance"

        details = [
            ("Book ID:", book_id),
            ("Title:", title),
            ("Author:", author),
            ("Publisher:", publisher),
            ("Issue Date:", checkout),
            ("Due Date:", due),
            ("Renewals:", ren_display),
            ("Last Renewed:", last_renewed or "—"),
            ("Returned:", returned or "Not yet returned"),
            ("Fine:", f"{money(fine_val)} ({fine_status})"),
        ]

        for label, value in details:
            key_label = QLabel(label)
            key_label.setMinimumWidth(0)
            key_label.setWordWrap(True)
            value_label = QLabel(safe_text(value))
            configure_wrapped_label(value_label)
            form.addRow(key_label, value_label)

        self.detail_layout.addLayout(form)

        if is_issued:
            renew_btn = configure_inspector_button(
                create_button(
                    "🔄 Renew Loan",
                    lambda: self.handle_renew_action(book_id, loan_id),
                    variant="InfoButton",
                )
            )
            self.detail_layout.addWidget(renew_btn)

            button = configure_inspector_button(
                create_button(
                    "↩ Return Book",
                    lambda: self.handle_return_action(book_id),
                    variant="SuccessButton",
                )
            )
            self.detail_layout.addWidget(button)

        if fine_val > 0 and not fine_settled and loan_id is not None:
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "💳 Mark Fine Paid",
                        lambda: self.handle_settle_fine(loan_id, "PAID"),
                        variant="SuccessButton",
                    )
                )
            )
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "Waive Fine",
                        lambda: self.handle_settle_fine(loan_id, "WAIVED"),
                        variant="WarningButton",
                    )
                )
            )

        self.detail_layout.addStretch()

    def handle_renew_action(self, book_id, loan_id=None):
        if loan_id is None:
            loan_id = self.db.get_active_loan_id(book_id, self.user_id)
        if loan_id is None:
            show_warning(
                self,
                "Active Loan Not Found",
                f"No active loan found for Book {book_id} and User {self.user_id}."
            )
            return

        dialog = RenewLoanDialog(self.db, loan_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.data_updated.emit()
            show_success(
                self,
                "Loan Renewed",
                dialog.result_message or "Loan renewed successfully."
            )
            self.load_user_books()

    def handle_settle_fine(self, loan_id, action):
        verb = "mark this fine as PAID" if action == "PAID" else "WAIVE this fine"
        confirm = QMessageBox.question(
            self,
            "Confirm Fine Settlement",
            f"Do you want to {verb} for transaction {format_log_id_display(loan_id)}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.db.settle_loan_fine(loan_id, action=action)
        if success:
            self.data_updated.emit()
            show_success(self, "Fine Updated", message)
            self.load_user_books()
        else:
            show_warning(self, "Fine Settlement Failed", message)

    def handle_return_action(self, book_id):
        confirm = QMessageBox.question(
            self,
            "Confirm Return",
            f"Return Book {book_id} for User {self.user_id}?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            success, fine, message = self.db.return_book(
                book_id,
                self.user_id
            )

            if success:
                self.data_updated.emit()

                result = "Book successfully returned!"

                if fine > 0:
                    result += f"\nFine: {money(fine)}"

                show_success(self, "Return Successful", result)
                self.load_user_books()
            else:
                show_warning(self, "Return Failed", message)

        except Exception as error:
            show_error(self, "Return Error", error)


# ============================================================
# BARCODE GENERATOR
# ============================================================

class BarcodeGeneratorDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(
        self,
        db,
        book_id="",
        title="",
        author="",
        publisher="",
        parent=None
    ):
        super().__init__(parent)

        self.db = db
        self.generated_image = None

        configure_dialog(
            self,
            "Barcode Generator",
            460,
            660,
            min_width=360,
            min_height=380,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)

        layout.addWidget(create_heading("🏷️ Book Barcode Generator"))

        body_host = QWidget()
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(10)

        self.input_book_id = QLineEdit(str(book_id))
        self.input_book_id.setPlaceholderText("Book ID")

        self.input_book_title = QLineEdit(str(title))
        self.input_book_title.setPlaceholderText("Book Title")

        self.input_book_author = QLineEdit(str(author))
        self.input_book_author.setPlaceholderText("Author")

        self.input_book_publisher = QLineEdit(str(publisher))
        self.input_book_publisher.setPlaceholderText("Publisher")

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=9)

        form.addRow("Book ID:", self.input_book_id)
        form.addRow("Title:", self.input_book_title)
        form.addRow("Author:", self.input_book_author)
        form.addRow("Publisher:", self.input_book_publisher)

        body_layout.addLayout(form)

        self.lbl_preview = QLabel("Barcode Preview")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumHeight(140)
        self.lbl_preview.setProperty("class", "barcode-preview")
        body_layout.addWidget(self.lbl_preview)

        self.chk_box_db = QCheckBox("Save book to database")

        if book_id:
            self.chk_box_db.setVisible(False)
        else:
            self.chk_box_db.setChecked(True)

        body_layout.addWidget(self.chk_box_db)
        body_layout.addStretch()

        layout.addWidget(wrap_in_scroll_area(body_host, object_name="BarcodeDialogScroll"), 1)

        self.btn_generate = create_button(
            "⚙ Generate Barcode",
            self.generate_barcode,
            variant="PrimaryButton",
        )

        self.btn_save = create_button(
            "💾 Export PNG",
            self.save_png,
            enabled=False,
            variant="SuccessButton",
        )

        layout.addWidget(self.btn_generate)
        layout.addWidget(self.btn_save)

        if book_id and title:
            self.generate_barcode()

    def generate_barcode(self):
        book_id = self.input_book_id.text().strip()
        title = self.input_book_title.text().strip()
        author = self.input_book_author.text().strip()
        publisher = self.input_book_publisher.text().strip()

        if not book_id or not title:
            show_warning(
                self,
                "Missing Information",
                "Book ID and title are required."
            )
            return

        if self.chk_box_db.isVisible() and self.chk_box_db.isChecked():
            if not author or not publisher:
                show_warning(
                    self,
                    "Missing Information",
                    "Author and publisher are required to save a new book."
                )
                return

            try:
                success, message = self.db.insert_book(
                    book_id,
                    title,
                    author,
                    publisher,
                    1,
                    1
                )

                if not success:
                    show_warning(self, "Database Error", message)
                    return

                self.data_updated.emit()
                self.chk_box_db.setChecked(False)
                self.chk_box_db.setVisible(False)

                show_success(self, "Book Saved", message)

            except Exception as error:
                show_error(self, "Database Error", error)
                return

        try:
            barcode_class = barcode.get_barcode_class("code128")

            options = {
                "module_width": 0.35,
                "module_height": 15,
                "quiet_zone": 5,
                "font_size": 12,
                "text_distance": 5,
                "write_text": True
            }

            code = barcode_class(
                book_id,
                writer=ImageWriter()
            )

            buffer = io.BytesIO()
            code.write(buffer, options=options)

            raw = buffer.getvalue()

            self.generated_image = Image.open(
                io.BytesIO(raw)
            ).convert("RGB")

            pixmap = QPixmap()
            pixmap.loadFromData(raw, "PNG")

            target_w = max(160, self.lbl_preview.width() - 20)
            target_h = max(100, self.lbl_preview.height() - 20)
            self.lbl_preview.setPixmap(
                pixmap.scaled(
                    target_w,
                    target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )

            self.btn_save.setEnabled(True)

        except Exception as error:
            self.generated_image = None
            self.btn_save.setEnabled(False)
            show_error(self, "Barcode Generation Error", error)

    def save_png(self):
        if self.generated_image is None:
            show_warning(
                self,
                "No Barcode",
                "Generate a barcode before exporting."
            )
            return

        book_id = self.input_book_id.text().strip()
        filename = f"Barcode_{book_id}.png"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Barcode",
            filename,
            "PNG Images (*.png)"
        )

        if not path:
            return

        if not path.lower().endswith(".png"):
            path += ".png"

        try:
            self.generated_image.save(path, format="PNG")
            show_success(
                self,
                "Export Successful",
                f"Barcode saved successfully:\n{path}"
            )
        except Exception as error:
            show_error(self, "Export Error", error)


# ============================================================
# QUICK BARCODE SCANNER
# ============================================================

class QuickScanDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self.book_id = None
        self.cap = None
        self.barcode_detector = None
        self._user_edited_days = False

        configure_dialog(
            self,
            "Quick Barcode Scanner",
            480,
            680,
            min_width=380,
            min_height=380,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)

        layout.addWidget(create_heading("📷 Quick Barcode Scanner"))

        scan_host = QWidget()
        scan_layout = QVBoxLayout(scan_host)
        scan_layout.setContentsMargins(0, 0, 4, 0)
        scan_layout.setSpacing(10)

        self.lbl_capture = QLabel(
            "Initializing camera..."
        )
        self.lbl_capture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_capture.setMinimumHeight(140)
        self.lbl_capture.setProperty("class", "camera-preview")

        scan_layout.addWidget(self.lbl_capture)

        scan_layout.addWidget(QLabel("Book ID — USB Scanner or Manual"))

        self.input_book_id = QLineEdit()
        self.input_book_id.setPlaceholderText(
            "Scan barcode or enter Book ID"
        )
        self.input_book_id.returnPressed.connect(
            self.on_physical_scan
        )
        self.input_book_id.textChanged.connect(
            self.on_manual_text_change
        )

        scan_layout.addWidget(self.input_book_id)

        c_scan = get_dialog_colors(self)
        self.lbl_status = QLabel("Waiting for barcode...")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            f"color: {c_scan['muted']}; font-weight: 600;"
        )
        scan_layout.addWidget(self.lbl_status)

        scan_layout.addWidget(QLabel("User ID / PIN"))

        self.input_user_id = QLineEdit()
        self.input_user_id.setPlaceholderText("Enter User ID")
        self.input_user_id.textChanged.connect(self._update_scan_context)
        scan_layout.addWidget(self.input_user_id)

        self.lbl_user_policy = QLabel("")
        self.lbl_user_policy.setWordWrap(True)
        self.lbl_user_policy.setStyleSheet(
            f"color: {c_scan['cyan']}; font-weight: 600;"
        )
        scan_layout.addWidget(self.lbl_user_policy)

        scan_layout.addWidget(QLabel("Loan Duration"))

        try:
            days = int(self.db.get_setting("default_days", 14))
        except (ValueError, TypeError):
            days = 14

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setValue(max(1, min(days, 365)))
        self.spin_days.setSuffix(" days")
        self.spin_days.valueChanged.connect(self._on_spin_days_edited)

        scan_layout.addWidget(self.spin_days)
        scan_layout.addStretch()

        layout.addWidget(wrap_in_scroll_area(scan_host, object_name="QuickScanDialogScroll"), 1)

        buttons_host = QWidget()
        buttons = FlowLayout(buttons_host, margin=0, h_spacing=8, v_spacing=6)

        self.issue_btn = create_button(
            "📤 Issue Book",
            lambda: self.process_circulation("issue"),
            False,
            variant="PrimaryButton",
        )

        self.renew_btn = create_button(
            "🔄 Renew Book",
            lambda: self.process_circulation("renew"),
            False,
            variant="InfoButton",
        )

        self.return_btn = create_button(
            "📥 Return Book",
            lambda: self.process_circulation("return"),
            False,
            variant="SuccessButton",
        )

        buttons.addWidget(self.issue_btn)
        buttons.addWidget(self.renew_btn)
        buttons.addWidget(self.return_btn)

        layout.addWidget(buttons_host)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)

        self._init_camera()
        self.input_book_id.setFocus()

    def _init_camera(self):
        try:
            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY

            self.cap = cv2.VideoCapture(0, backend)

            if hasattr(cv2, "barcode"):
                self.barcode_detector = cv2.barcode.BarcodeDetector()

            if self.cap and self.cap.isOpened():
                self.timer.start(30)
            else:
                self.lbl_capture.setText(
                    "Camera unavailable\nUse USB scanner or manual input."
                )

        except Exception:
            self.cap = None
            self.lbl_capture.setText(
                "Camera unavailable\nUse USB scanner or manual input."
            )

    def _release_camera(self):
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()

        if self.cap is not None:
            try:
                if self.cap.isOpened():
                    self.cap.release()
            except Exception:
                pass

            self.cap = None

    def _on_spin_days_edited(self):
        if not self.spin_days.signalsBlocked():
            self._user_edited_days = True

    def _update_scan_context(self, *_):
        c = get_dialog_colors(self)
        code = self.input_book_id.text().strip()
        user_id = self.input_user_id.text().strip()
        self.book_id = code or None

        has_book = bool(code)
        self.issue_btn.setEnabled(has_book)
        self.return_btn.setEnabled(has_book)
        self.renew_btn.setEnabled(has_book and bool(user_id))

        if user_id:
            ok, user = self.db.get_user_details(user_id)
            if ok and user:
                role = user[3]
                policy = self.db.get_loan_policy(role)
                if not self._user_edited_days:
                    self.spin_days.blockSignals(True)
                    self.spin_days.setValue(max(1, min(int(policy.get("default_days", 14)), 365)))
                    self.spin_days.blockSignals(False)
                active_loan_id = (
                    self.db.get_active_loan_id(code, user_id)
                    if has_book
                    else None
                )
                if active_loan_id:
                    self.lbl_user_policy.setText(
                        f"{user[1]} ({role}) · Active loan {format_log_id_display(active_loan_id)} detected for {code}"
                    )
                    self.lbl_user_policy.setStyleSheet(
                        f"background: {c['cyan_soft']}; color: {c['cyan']}; "
                        f"border: 1px solid {c['cyan']}; border-radius: 6px; "
                        "padding: 5px 8px; font-weight: 700;"
                    )
                else:
                    self.lbl_user_policy.setText(
                        f"{user[1]} ({role}) · Policy: {policy.get('default_days', 14)} days, "
                        f"Max {policy.get('max_books', 3)} books, ₹{policy.get('fine_rate', 2.0):.2f}/day"
                    )
                    self.lbl_user_policy.setStyleSheet(
                        f"background: {c['primary_soft']}; color: {c['primary']}; "
                        f"border: 1px solid {c['primary']}; border-radius: 6px; "
                        "padding: 5px 8px; font-weight: 600;"
                    )
            else:
                self.lbl_user_policy.setText("Member ID not found.")
                self.lbl_user_policy.setStyleSheet(
                    f"color: {c['danger']}; font-weight: 600;"
                )
        else:
            self.lbl_user_policy.setText("")
            self.lbl_user_policy.setStyleSheet("")

    def on_manual_text_change(self, text):
        c = get_dialog_colors(self)
        code = text.strip()
        self.book_id = code or None

        if code:
            ok, book = self.db.get_book_details(code)
            if ok and book:
                self.lbl_status.setText(
                    f"Book: {book[1]} ({int(book[5] or 0)}/{int(book[4] or 0)} available)"
                )
                self.lbl_status.setStyleSheet(
                    f"background: {c['success_soft']}; color: {c['success']}; "
                    f"border: 1px solid {c['success']}; border-radius: 6px; "
                    "padding: 5px 8px; font-weight: 700;"
                )
            else:
                self.lbl_status.setText(f"Book detected: {code}")
                self.lbl_status.setStyleSheet(
                    f"color: {c['primary']}; font-weight: 600;"
                )
        else:
            self.lbl_status.setText("Waiting for barcode...")
            self.lbl_status.setStyleSheet(
                f"color: {c['muted']}; font-weight: 600;"
            )

        self._update_scan_context()

    def on_physical_scan(self):
        code = self.input_book_id.text().strip()

        if code:
            self.set_camera_scanned_book_id(
                code,
                "USB Scanner"
            )
            self.input_user_id.setFocus()

    def update_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return

        success, frame = self.cap.read()

        if not success or frame is None:
            return

        if self.barcode_detector is not None:
            try:
                result = self.barcode_detector.detectAndDecode(frame)

                if result and len(result) >= 2:
                    decoded = result[1]

                    if isinstance(decoded, (list, tuple)):
                        codes = decoded
                    else:
                        codes = [decoded]

                    for code in codes:
                        if code and str(code).strip():
                            self.set_camera_scanned_book_id(
                                str(code).strip(),
                                "Camera"
                            )
                            break

            except Exception:
                pass

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape

            image = QImage(
                rgb.data,
                width,
                height,
                width * channels,
                QImage.Format.Format_RGB888
            ).copy()

            pixmap = QPixmap.fromImage(image)

            cap_w = max(120, self.lbl_capture.width())
            cap_h = max(100, self.lbl_capture.height())
            self.lbl_capture.setPixmap(
                pixmap.scaled(
                    cap_w,
                    cap_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )

        except Exception:
            pass

    def set_camera_scanned_book_id(self, code, source=""):
        if not code:
            return

        self.book_id = code

        self.input_book_id.blockSignals(True)
        self.input_book_id.setText(code)
        self.input_book_id.blockSignals(False)

        self.lbl_status.setText(
            f"Detected using {source}: {code}"
        )

        self._update_scan_context()

        if self.timer.isActive():
            self.timer.stop()

    def process_circulation(self, action):
        user_id = self.input_user_id.text().strip()

        if not self.book_id or not user_id:
            show_warning(
                self,
                "Missing Information",
                "Both Book ID and User ID are required."
            )
            return

        if action == "renew":
            loan_id = self.db.get_active_loan_id(self.book_id, user_id)
            if loan_id is None:
                show_warning(
                    self,
                    "Active Loan Not Found",
                    f"No active loan found matching Book ID '{self.book_id}' and User ID '{user_id}'."
                )
                return
            dialog = RenewLoanDialog(self.db, loan_id, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.data_updated.emit()
                show_success(
                    self,
                    "Loan Renewed",
                    dialog.result_message or "Loan renewed successfully."
                )
                self._release_camera()
                self.accept()
            return

        try:
            if action == "issue":
                success, message = self.db.issue_book(
                    self.book_id,
                    user_id,
                    days_allowed=self.spin_days.value()
                )

                fine = 0

            else:
                success, fine, message = self.db.return_book(
                    self.book_id,
                    user_id
                )

            if success:
                self.data_updated.emit()

                if action == "return" and fine > 0:
                    show_success(
                        self,
                        "Return Successful",
                        f"{message}\nFine: {money(fine)}"
                    )
                else:
                    show_success(self, "Success", message)

                self._release_camera()
                self.accept()

            else:
                show_warning(self, "Transaction Failed", message)
                self.reset_for_retry()

        except Exception as error:
            show_error(self, "Transaction Error", error)
            self.reset_for_retry()

    def reset_for_retry(self):
        self.book_id = None
        self.input_book_id.clear()

        self.issue_btn.setEnabled(False)
        self.renew_btn.setEnabled(False)
        self.return_btn.setEnabled(False)

        if self.cap and self.cap.isOpened() and not self.timer.isActive():
            self.timer.start(30)

    def reject(self):
        self._release_camera()
        super().reject()

    def closeEvent(self, event):
        self._release_camera()
        event.accept()


# ============================================================
# ADMINISTRATOR LOGIN
# ============================================================

class LoginDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self._verification_in_progress = False

        configure_dialog(
            self,
            f"{APP_NAME} — Administrator Login",
            400,
            360,
            min_width=320,
            min_height=280,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(
            create_heading("🔒 Administrator Login")
        )

        layout.addWidget(QLabel("Administrator Password"))

        self.input_admin_password = QLineEdit()
        self.input_admin_password.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.input_admin_password.setPlaceholderText(
            "Enter administrator password"
        )

        self.input_admin_password.returnPressed.connect(
            self.verify_password
        )

        layout.addWidget(self.input_admin_password)

        self.btn_login = create_button(
            "Verify Password →",
            self.verify_password,
            variant="PrimaryButton",
        )

        self.btn_login.setDefault(False)
        self.btn_login.setAutoDefault(False)
        layout.addWidget(self.btn_login)

        self.btn_forgot_password = create_button(
            "Forgot password?",
            self.open_password_recovery,
            variant="SecondaryButton",
        )
        self.btn_forgot_password.setDefault(False)
        self.btn_forgot_password.setAutoDefault(False)
        layout.addWidget(self.btn_forgot_password)

        c = get_dialog_colors(self)
        self.app_credit_label = QLabel(
            f"{APP_NAME}\n{APP_DEVELOPER_CREDIT}"
        )
        self.app_credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app_credit_label.setWordWrap(True)
        self.app_credit_label.setStyleSheet(
            f"color: {c['muted']}; font-size: 11px;"
        )
        layout.addWidget(self.app_credit_label)

        self.input_admin_password.setFocus()

    def verify_password(self):
        if self._verification_in_progress:
            return

        self._verification_in_progress = True

        try:
            entered = self.input_admin_password.text()

            if not self.db.verify_admin_password(entered):
                show_error(
                    self,
                    "Access Denied",
                    "Incorrect administrator password."
                )

                self.input_admin_password.clear()
                self.input_admin_password.setFocus()
                return

            if not self.db.has_admin_recovery_code():
                setup_dialog = RecoveryCodeSetupDialog(self)
                if setup_dialog.exec() != QDialog.DialogCode.Accepted:
                    return

                if not self.db.set_admin_recovery_code(
                    setup_dialog.recovery_code
                ):
                    show_error(
                        self,
                        "Recovery Setup Failed",
                        "The recovery code could not be saved. "
                        "Please try again before continuing.",
                    )
                    return

            self.accept()

        except Exception as error:
            show_error(self, "Authentication Error", error)
        finally:
            self._verification_in_progress = False

    def open_password_recovery(self):
        try:
            has_recovery_code = self.db.has_admin_recovery_code()
        except Exception as error:
            show_error(self, "Recovery Error", error)
            return

        if not has_recovery_code:
            show_warning(
                self,
                "Recovery Not Set Up",
                "A recovery code has not been configured. "
                "Password recovery is only available after a "
                "librarian saves a recovery code in the application.",
            )
            return

        dialog = AdminPasswordRecoveryDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            show_success(
                self,
                "Password Reset",
                "The administrator password has been reset. "
                "Save the new recovery code shown during recovery, "
                "then sign in with the new password.",
            )
            self.input_admin_password.clear()
            self.input_admin_password.setFocus()


class RecoveryCodeSetupDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        raw_code = secrets.token_hex(16).upper()
        self.recovery_code = "-".join(
            raw_code[index:index + 4]
            for index in range(0, len(raw_code), 4)
        )

        configure_dialog(
            self,
            "Save Administrator Recovery Code",
            640,
            470,
            min_width=360,
            min_height=340,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(10)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        layout.addWidget(
            create_heading("Save this recovery code")
        )
        description = QLabel(
            "Keep this code somewhere secure and separate from the "
            "computer. It is shown only once and is required to reset "
            "the administrator password."
        )
        configure_wrapped_label(description)
        layout.addWidget(description)

        c = get_dialog_colors(self)
        self._colors = c
        self.code_input = QLineEdit(self.recovery_code)
        self.code_input.setReadOnly(True)
        self.code_input.setMinimumWidth(0)
        self.code_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setStyleSheet(
            f"background: {c['primary_soft']}; color: {c['primary']}; "
            f"border: 1.5px solid {c['primary']}; border-radius: 8px; "
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 13px; font-weight: 700; letter-spacing: 0.5px; "
            "padding: 6px 10px;"
        )
        self.code_input.setMinimumHeight(42)
        layout.addWidget(self.code_input)

        code_actions_host = QWidget()
        code_actions_host.setMinimumWidth(0)
        code_actions = FlowLayout(
            code_actions_host,
            margin=0,
            h_spacing=8,
            v_spacing=6,
        )
        self.copy_button = create_button(
            "Copy Recovery Code",
            self.copy_recovery_code,
            variant="InfoButton",
        )
        self.save_button = create_button(
            "Save .txt File...",
            self.save_recovery_code_to_file,
            variant="SecondaryButton",
        )
        self.copy_button.setMinimumWidth(0)
        self.save_button.setMinimumWidth(0)
        code_actions.addWidget(self.copy_button)
        code_actions.addWidget(self.save_button)
        layout.addWidget(code_actions_host)

        self.copy_feedback_label = QLabel(
            "Click 'Copy Recovery Code' or 'Save .txt File...', then check the confirmation box below."
        )
        configure_wrapped_label(self.copy_feedback_label)
        self.copy_feedback_label.setStyleSheet(
            f"background: {c['surface_alt']}; color: {c['muted']}; "
            f"border: 1px solid {c['border']}; border-radius: 8px; "
            "padding: 8px 10px; font-size: 12px;"
        )
        layout.addWidget(self.copy_feedback_label)
        layout.addStretch()

        outer.addWidget(wrap_in_scroll_area(body, object_name="RecoverySetupScroll"), 1)

        self.saved_checkbox = QCheckBox(
            "I have saved this code somewhere secure."
        )
        outer.addWidget(self.saved_checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_button = create_button("Cancel", self.reject, variant="SecondaryButton")
        buttons.addWidget(cancel_button)

        self.confirm_button = create_button(
            "Continue",
            self.accept,
            enabled=False,
            variant="PrimaryButton",
        )
        buttons.addWidget(self.confirm_button)
        outer.addLayout(buttons)

        self.saved_checkbox.toggled.connect(
            self.confirm_button.setEnabled
        )

    def copy_recovery_code(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.recovery_code)
        self.code_input.selectAll()
        c = self._colors
        self.copy_button.setText("Copied to Clipboard")
        self.copy_feedback_label.setStyleSheet(
            f"background: {c['success_soft']}; color: {c['success']}; "
            f"border: 1px solid {c['success']}; border-radius: 8px; "
            "padding: 8px 10px; font-size: 12px; font-weight: 700;"
        )
        self.copy_feedback_label.setText(
            "Recovery code copied to clipboard! Paste it in a safe place, "
            "check 'I have saved this code somewhere secure', and click Continue."
        )
        self.saved_checkbox.setFocus()
        QTimer.singleShot(2800, self._restore_copy_button_text)

    def _restore_copy_button_text(self):
        if not sip.isdeleted(self) and not sip.isdeleted(self.copy_button):
            self.copy_button.setText("Copy Recovery Code")

    def save_recovery_code_to_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Administrator Recovery Code",
            "library-recovery-code.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            content = (
                f"{APP_NAME} — Administrator Recovery Code\n"
                f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
                f"Recovery Code: {self.recovery_code}\n\n"
                "Keep this file in a secure location separate from the computer.\n"
            )
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as error:
            show_error(self, "Save Recovery Code Failed", error)
            return

        c = self._colors
        self.copy_feedback_label.setStyleSheet(
            f"background: {c['success_soft']}; color: {c['success']}; "
            f"border: 1px solid {c['success']}; border-radius: 8px; "
            "padding: 8px 10px; font-size: 12px; font-weight: 700;"
        )
        self.copy_feedback_label.setText(
            f"Saved recovery code to {os.path.basename(path)}. "
            "Check 'I have saved this code somewhere secure' and click Continue."
        )
        self.saved_checkbox.setFocus()


class AdminPasswordRecoveryDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        configure_dialog(
            self,
            "Reset Administrator Password",
            450,
            320,
            min_width=320,
            min_height=250,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(11)

        layout.addWidget(
            create_heading("Verify your recovery code")
        )

        self.recovery_code_input = QLineEdit()
        self.recovery_code_input.setPlaceholderText(
            "Enter the saved recovery code"
        )
        layout.addWidget(self.recovery_code_input)

        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.new_password_input.setPlaceholderText(
            "New password (at least 8 characters)"
        )
        layout.addWidget(self.new_password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.confirm_password_input.setPlaceholderText(
            "Confirm new password"
        )
        self.confirm_password_input.returnPressed.connect(
            self.reset_password
        )
        layout.addWidget(self.confirm_password_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = create_button("Cancel", self.reject, variant="SecondaryButton")
        buttons.addWidget(cancel_button)
        reset_button = create_button(
            "Reset Password",
            self.reset_password,
            variant="WarningButton",
        )
        buttons.addWidget(reset_button)
        layout.addLayout(buttons)

    def reset_password(self):
        recovery_code = self.recovery_code_input.text().strip()
        new_password = self.new_password_input.text()
        confirmation = self.confirm_password_input.text()

        if not recovery_code:
            show_warning(
                self,
                "Recovery Code Required",
                "Enter the saved administrator recovery code.",
            )
            return

        if len(new_password) < 8:
            show_warning(
                self,
                "Weak Password",
                "The new password must contain at least 8 characters.",
            )
            return

        if new_password != confirmation:
            show_warning(
                self,
                "Password Mismatch",
                "The new password and confirmation do not match.",
            )
            return

        try:
            recovery_code_valid = self.db.verify_admin_recovery_code(
                recovery_code
            )
        except Exception as error:
            show_error(self, "Recovery Error", error)
            return

        if not recovery_code_valid:
            show_error(
                self,
                "Recovery Failed",
                "The recovery code is incorrect.",
            )
            self.recovery_code_input.clear()
            self.recovery_code_input.setFocus()
            return

        setup_dialog = RecoveryCodeSetupDialog(self)
        if setup_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            reset = self.db.reset_admin_password_with_recovery(
                recovery_code,
                new_password,
                setup_dialog.recovery_code,
            )
            if not reset:
                show_error(
                    self,
                    "Recovery Failed",
                    "The recovery code is incorrect or has already "
                    "been replaced.",
                )
                return
        except Exception as error:
            show_error(self, "Password Reset Failed", error)
            return

        self.accept()


# ============================================================
# CUSTOM SPLASH SCREEN
# ============================================================

class CustomSplashScreen(QDialog):

    def __init__(self, image_path):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.SplashScreen |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        clamp_widget_to_screen(
            self,
            450,
            415,
            max_width_ratio=0.90,
            max_height_ratio=0.88,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)

            if not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(
                        160,
                        160,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
            else:
                self.icon_label.setText("📚")
        else:
            self.icon_label.setText("📚")

        layout.addWidget(self.icon_label)

        self.text_label = QLabel(APP_NAME)
        self.text_label.setFont(
            QFont("Segoe UI", 17, QFont.Weight.Bold)
        )
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)

        layout.addWidget(self.text_label)

        c = get_dialog_colors(self)
        self.developer_label = QLabel(APP_DEVELOPER_CREDIT)
        self.developer_label.setFont(
            QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        )
        self.developer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.developer_label.setWordWrap(True)
        self.developer_label.setStyleSheet(f"color: {c['muted']};")

        layout.addWidget(self.developer_label)

        self.sub_label = QLabel(
            "Loading database and application services..."
        )
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setWordWrap(True)

        layout.addWidget(self.sub_label)

    def set_status(self, message):
        self.sub_label.setText(str(message))

    def finish(self, _main_window=None):
        self.close()
        self.deleteLater()


# ============================================================
# BOOK CIRCULATION AUDIT HISTORY
# ============================================================

class BookHistoryDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, book_id, book_title, parent=None):
        super().__init__(parent)

        self.db = db
        self.book_id = book_id
        self.book_title = book_title
        self.history_data = []
        self._splitter_vertical = None
        self._compact_table_mode = None

        configure_dialog(
            self,
            f"Book History — {book_title}",
            1050,
            620,
            min_width=480,
            min_height=360,
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        main_layout.addWidget(
            create_heading(
                f"📖 Circulation Audit — {book_title}"
            )
        )

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(6)

        self.table = QTableWidget()
        self.table.setColumnCount(8)

        self.table.setHorizontalHeaderLabels([
            "Log ID",
            "Borrower ID",
            "Status",
            "Issue Date",
            "Due Date",
            "Return Date",
            "Renewals",
            "Fine"
        ])

        configure_table(self.table)
        self.table.setMinimumHeight(160)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._apply_table_column_modes()

        self.detail_container = QFrame()
        self.detail_container.setObjectName("DialogInspector")
        c_panel = get_dialog_colors(self)
        self.detail_container.setStyleSheet(
            f"#DialogInspector {{ background-color: {c_panel['surface']}; "
            f"border: 1px solid {c_panel['border']}; border-radius: 12px; }}"
        )

        detail_outer = QVBoxLayout(self.detail_container)
        detail_outer.setContentsMargins(10, 10, 10, 10)
        detail_outer.setSpacing(0)

        self.detail_content = QWidget()
        self.detail_content.setObjectName("AuditInspectorContent")
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(4, 4, 6, 4)
        self.detail_layout.setSpacing(10)

        self.detail_scroll = wrap_in_scroll_area(
            self.detail_content,
            object_name="AuditInspectorScroll",
        )
        detail_outer.addWidget(self.detail_scroll)

        self.table.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        self.content_splitter.addWidget(self.table)
        self.content_splitter.addWidget(self.detail_container)
        self._sync_responsive_layout()

        main_layout.addWidget(self.content_splitter, 1)

        self.show_default_inspector()
        self.load_history()

    def _apply_table_column_modes(self):
        compact = self.width() < 860
        if compact == self._compact_table_mode:
            return
        self._compact_table_mode = compact
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(55)
        for col in (0, 2, 3, 4, 5, 6, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        if compact:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(1, 140)
        else:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _sync_responsive_layout(self):
        self._splitter_vertical = sync_responsive_splitter(
            self.content_splitter,
            self.detail_container,
            self.width() - 36,
            breakpoint=820,
            max_panel_width=340,
            min_panel_width=240,
            min_panel_height=190,
            current_vertical=self._splitter_vertical,
        )
        self._apply_table_column_modes()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "content_splitter"):
            self._sync_responsive_layout()

    def show_default_inspector(self):
        clear_layout(self.detail_layout)

        self.detail_layout.addWidget(
            create_heading("🔍 Audit Inspector")
        )

        hint = QLabel(
            "Select a record to inspect the borrower, "
            "loan dates and fine information."
        )
        hint.setWordWrap(True)

        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_history(self):
        try:
            cursor = self.db.conn.cursor()

            cursor.execute(
                """
                SELECT
                    COALESCE(NULLIF(log_code, ''), CAST(id AS TEXT)),
                    user_id,
                    checkout_date,
                    due_date,
                    return_date,
                    fine_amount,
                    status,
                    COALESCE(renewal_count, 0),
                    COALESCE(last_renewed_at, ''),
                    COALESCE(fine_settled, 0),
                    COALESCE(fine_settlement_action, '')
                FROM circulation_logs
                WHERE book_id = ?
                ORDER BY id DESC
                """,
                (self.book_id,)
            )

            self.history_data = cursor.fetchall()
            self._max_renewals = self.db.get_max_renewals()
            today_str = datetime.date.today().isoformat()

            self.table.blockSignals(True)
            self.table.setRowCount(len(self.history_data))

            for row_index, record in enumerate(self.history_data):
                (
                    log_id, user_id, checkout, due, returned, fine,
                    status, ren_count, _last_renewed, fine_settled, fine_action
                ) = record

                raw_status = str(status).upper()
                due_text = safe_text(due)
                if raw_status == "ISSUED" and due_text and due_text[:10] < today_str:
                    status_text = "OVERDUE"
                elif raw_status == "ISSUED" and due_text and due_text[:10] == today_str:
                    status_text = "DUE TODAY"
                else:
                    status_text = raw_status

                try:
                    fine_val = float(fine or 0.0)
                except (TypeError, ValueError):
                    fine_val = 0.0
                is_settled = bool(int(fine_settled or 0) == 1 or raw_status == "PAID")
                fine_text = money(fine_val)
                if fine_val > 0 and is_settled:
                    fine_text += f" ({'Waived' if str(fine_action).upper() == 'WAIVED' else 'Paid'})"

                ren_text = (
                    f"{int(ren_count)}/{self._max_renewals}"
                    if self._max_renewals > 0
                    else str(int(ren_count))
                )

                values = [
                    safe_text(log_id),
                    safe_text(user_id),
                    status_text,
                    safe_text(checkout),
                    due_text,
                    safe_text(returned) or "—",
                    ren_text,
                    fine_text,
                ]

                c = get_dialog_colors(self)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if column == 0:
                        item.setForeground(QColor(c["primary"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 2:
                        if status_text == "OVERDUE":
                            item.setForeground(QColor(c["danger"]))
                        elif status_text == "DUE TODAY":
                            item.setForeground(QColor(c["warning"]))
                        elif status_text == "ISSUED":
                            item.setForeground(QColor(c["primary"]))
                        else:
                            item.setForeground(QColor(c["success"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 6 and int(ren_count or 0) > 0:
                        item.setForeground(QColor(c["cyan"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif column == 7 and fine_val > 0 and not is_settled:
                        item.setForeground(QColor(c["danger"]))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)

                    self.table.setItem(row_index, column, item)

            self.table.blockSignals(False)

            if self.history_data:
                self.table.selectRow(0)
                self.display_record_details(self.history_data[0])
            else:
                self.show_default_inspector()

        except Exception as error:
            self.table.blockSignals(False)
            show_error(self, "History Error", error)

    def on_selection_changed(self, *args):
        selected = self.table.selectionModel().selectedRows()

        if not selected:
            self.show_default_inspector()
            return

        row = selected[0].row()

        if 0 <= row < len(self.history_data):
            self.display_record_details(
                self.history_data[row]
            )

    def display_record_details(self, record):
        (
            log_id, user_id, checkout, due, returned, fine,
            status, ren_count, last_renewed, fine_settled_flag, fine_action
        ) = record

        clear_layout(self.detail_layout)

        raw_status = str(status).upper()
        is_issued = raw_status == "ISSUED"
        today_str = datetime.date.today().isoformat()
        is_overdue = bool(is_issued and safe_text(due) and safe_text(due)[:10] < today_str)
        try:
            fine_val = float(fine or 0.0)
        except (TypeError, ValueError):
            fine_val = 0.0
        fine_settled = bool(int(fine_settled_flag or 0) == 1 or raw_status == "PAID")

        self.detail_layout.addWidget(
            create_heading("Audit Control Center")
        )

        banner = QLabel(
            "🔴 Overdue Loan"
            if is_overdue else
            "🟠 Issued Book"
            if is_issued else
            "🟢 Completed Loan"
        )

        banner.setWordWrap(True)

        set_status_property(
            banner,
            "overdue" if is_overdue else "issued" if is_issued else "returned"
        )

        self.detail_layout.addWidget(banner)

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=10, vertical_spacing=7)

        max_r = getattr(self, "_max_renewals", 0)
        ren_display = f"{ren_count} / {max_r}" if max_r > 0 else f"{ren_count} (Unlimited)"
        if fine_val <= 0:
            fine_status = "No Fine"
        elif fine_settled:
            fine_status = "Waived" if str(fine_action).upper() == "WAIVED" else "Paid"
        else:
            fine_status = "Unpaid Balance"

        details = [
            ("Log ID:", format_log_id_display(log_id)),
            ("Book ID:", self.book_id),
            ("Borrower ID:", user_id),
            ("Status:", "OVERDUE" if is_overdue else status),
            ("Issue Date:", checkout),
            ("Due Date:", due),
            ("Renewals:", ren_display),
            ("Last Renewed:", last_renewed or "—"),
            ("Returned:", returned or "Not yet returned"),
            ("Fine:", f"{money(fine_val)} ({fine_status})")
        ]

        for label, value in details:
            key_label = QLabel(label)
            key_label.setMinimumWidth(0)
            key_label.setWordWrap(True)
            value_label = QLabel(safe_text(value))
            configure_wrapped_label(value_label)
            form.addRow(key_label, value_label)

        self.detail_layout.addLayout(form)

        if is_issued:
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "🔄 Renew Loan",
                        lambda: self.handle_renew_action(log_id),
                        variant="InfoButton",
                    )
                )
            )
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "↩ Return Book",
                        lambda: self.handle_return_action(user_id),
                        variant="SuccessButton",
                    )
                )
            )

        if fine_val > 0 and not fine_settled:
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "💳 Mark Fine Paid",
                        lambda: self.handle_settle_fine(log_id, "PAID"),
                        variant="SuccessButton",
                    )
                )
            )
            self.detail_layout.addWidget(
                configure_inspector_button(
                    create_button(
                        "Waive Fine",
                        lambda: self.handle_settle_fine(log_id, "WAIVED"),
                        variant="WarningButton",
                    )
                )
            )

        self.detail_layout.addStretch()

    def handle_renew_action(self, log_id):
        dialog = RenewLoanDialog(self.db, log_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.data_updated.emit()
            show_success(
                self,
                "Loan Renewed",
                dialog.result_message or "Loan renewed successfully."
            )
            self.load_history()

    def handle_settle_fine(self, log_id, action):
        verb = "mark this fine as PAID" if action == "PAID" else "WAIVE this fine"
        confirm = QMessageBox.question(
            self,
            "Confirm Fine Settlement",
            f"Do you want to {verb} for transaction {format_log_id_display(log_id)}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        success, message = self.db.settle_loan_fine(log_id, action=action)
        if success:
            self.data_updated.emit()
            show_success(self, "Fine Updated", message)
            self.load_history()
        else:
            show_warning(self, "Fine Settlement Failed", message)

    def handle_return_action(self, user_id):
        confirm = QMessageBox.question(
            self,
            "Confirm Return",
            f"Return Book {self.book_id} for User {user_id}?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            success, fine, message = self.db.return_book(
                self.book_id,
                user_id
            )

            if success:
                self.data_updated.emit()

                result = "Book successfully returned!"

                if fine > 0:
                    result += f"\nFine: {money(fine)}"

                show_success(self, "Return Successful", result)
                self.load_history()

            else:
                show_warning(self, "Return Failed", message)

        except Exception as error:
            show_error(self, "Return Error", error)


# ============================================================
# EDIT / ADD DEPARTMENT & BRANCH DIALOG
# ============================================================


class EditDepartmentDialog(QDialog):
    """Dialog for adding or updating a college branch or faculty department."""

    def __init__(
        self,
        name="",
        category="STUDENT",
        duration=3,
        parent=None,
        branch_code="",
        mode="edit",
        user_count=0,
    ):
        super().__init__(parent)
        self._mode = "add" if mode == "add" or not str(name or "").strip() else "edit"

        configure_dialog(
            self,
            "Add Branch / Department" if self._mode == "add" else "Update Branch / Department",
            490,
            400,
            min_width=360,
            min_height=310,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(
            create_heading(
                "+ Add Branch / Department"
                if self._mode == "add"
                else "Update Branch / Department"
            )
        )

        body_host = QWidget()
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(10)

        self.form_layout = QFormLayout()
        configure_inspector_form(self.form_layout, horizontal_spacing=12, vertical_spacing=11)

        self.input_name = QLineEdit(str(name or ""))
        self.input_name.setMaxLength(120)
        self.input_name.setPlaceholderText("e.g. Artificial Intelligence & ML")

        self.input_code = QLineEdit(str(branch_code or "").upper())
        self.input_code.setMaxLength(12)
        self.input_code.setPlaceholderText("Optional code (e.g. CS, AI, PH)")
        self.input_code.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"^[A-Za-z0-9_-]{0,12}$"),
                self.input_code,
            )
        )

        self.combo_cat = QComboBox()
        self.combo_cat.addItem("Students & Faculty (Academic Branch)", "STUDENT")
        self.combo_cat.addItem("Faculty & Staff Only", "FACULTY")
        cat_code = str(category or "STUDENT").strip().upper()
        cat_idx = self.combo_cat.findData(cat_code)
        self.combo_cat.setCurrentIndex(cat_idx if cat_idx >= 0 else 0)
        self.combo_cat.currentIndexChanged.connect(self.on_category_changed)

        self.combo_duration = QComboBox()
        for yrs in range(1, 7):
            label = "1 Year" if yrs == 1 else f"{yrs} Years"
            self.combo_duration.addItem(label, yrs)

        try:
            duration_val = int(duration)
        except (ValueError, TypeError):
            duration_val = 3

        index = self.combo_duration.findData(duration_val)
        if index < 0:
            index = self.combo_duration.findData(3)
        self.combo_duration.setCurrentIndex(index if index >= 0 else 2)

        self.duration_label = QLabel("Course Duration:")

        self.form_layout.addRow("Branch / Department:", self.input_name)
        self.form_layout.addRow("Short Code:", self.input_code)
        self.form_layout.addRow("Available To:", self.combo_cat)
        self.form_layout.addRow(self.duration_label, self.combo_duration)
        body_layout.addLayout(self.form_layout)

        if self._mode == "edit" and int(user_count or 0) > 0:
            cascade_note = QLabel(
                f"Currently assigned to {int(user_count)} member(s). "
                "Renaming automatically updates those member records."
            )
            cascade_note.setWordWrap(True)
            cascade_note.setStyleSheet(
                f"background: {c['cyan_soft']}; color: {c['text']}; "
                f"border: 1px solid {c['cyan']}; border-left: 4px solid {c['cyan']}; "
                "border-radius: 7px; padding: 7px 10px; font-weight: 600; font-size: 11px;"
            )
            body_layout.addWidget(cascade_note)

        body_layout.addStretch()
        layout.addWidget(wrap_in_scroll_area(body_host, object_name="EditDeptScroll"), 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(
            create_button("Cancel", self.reject, variant="SecondaryButton")
        )
        buttons.addWidget(
            create_button(
                "Add Branch / Dept" if self._mode == "add" else "Save Changes",
                self.validate_and_accept,
                variant="PrimaryButton",
            )
        )
        layout.addLayout(buttons)

        self.on_category_changed()

    def on_category_changed(self, *args):
        cat_code = str(self.combo_cat.currentData() or self.combo_cat.currentText()).upper()
        is_student = cat_code == "STUDENT"
        self.duration_label.setVisible(is_student)
        self.combo_duration.setVisible(is_student)

    def validate_and_accept(self):
        name = " ".join(self.input_name.text().split()).strip()
        if not name:
            show_warning(
                self,
                "Name Required",
                "Enter a branch or department name.",
            )
            return
        code = self.input_code.text().strip().upper()
        if code and not re.fullmatch(r"[A-Z0-9_-]{1,12}", code):
            show_warning(
                self,
                "Invalid Short Code",
                "Short code may only use letters, numbers, '-' or '_' (up to 12 characters).",
            )
            return
        self.input_name.setText(name)
        self.input_code.setText(code)
        self.accept()

    def get_data(self):
        cat_code = str(self.combo_cat.currentData() or self.combo_cat.currentText()).upper()
        duration = (
            int(self.combo_duration.currentData() or 3)
            if cat_code == "STUDENT"
            else 3
        )
        return (
            self.input_name.text().strip(),
            cat_code,
            duration,
        )

    def get_full_data(self):
        name, cat_code, duration = self.get_data()
        code = self.input_code.text().strip().upper()
        return name, cat_code, duration, code


class ReassignDepartmentDialog(QDialog):
    """Prompt to reassign users from one branch/department into another."""

    def __init__(
        self,
        source_name,
        target_options,
        user_count,
        student_count=0,
        title="Reassign Members",
        confirm_text="Reassign Members",
        parent=None,
    ):
        super().__init__(parent)
        configure_dialog(self, title, 470, 290, min_width=360, min_height=240)
        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(create_heading(title))

        note = QLabel(
            f"{int(user_count)} member(s)"
            + (f" (including {int(student_count)} student(s))" if int(student_count or 0) > 0 else "")
            + f" currently belong to '{source_name}'. Select the destination branch/department:"
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {c['text']}; font-weight: 600;")
        layout.addWidget(note)

        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(0)
        self.target_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.target_combo.setMinimumContentsLength(20)
        for opt in target_options:
            self.target_combo.addItem(str(opt), str(opt))
        layout.addWidget(self.target_combo)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(create_button("Cancel", self.reject, variant="SecondaryButton"))
        buttons.addWidget(
            create_button(
                confirm_text,
                self.accept,
                variant="DangerButton" if "Delete" in confirm_text else "PrimaryButton",
            )
        )
        layout.addLayout(buttons)

    def selected_target(self):
        return str(self.target_combo.currentData() or self.target_combo.currentText() or "").strip()


# ============================================================
# DEPARTMENT MANAGER
# ============================================================


class DepartmentManagerDialog(QDialog):
    departments_changed = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self._all_rows = []
        self._filtered_rows = []

        configure_dialog(
            self,
            "Branches & Departments Manager",
            860,
            610,
            min_width=480,
            min_height=380,
        )

        c = get_dialog_colors(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(
            create_heading("Branches & Departments Manager")
        )

        self.summary_badge = QLabel()
        self.summary_badge.setWordWrap(True)
        self.summary_badge.setMinimumWidth(0)
        self.summary_badge.setStyleSheet(
            f"background: {c['primary_soft']}; color: {c['primary']}; "
            f"border: 1px solid {c['primary']}; border-radius: 10px; "
            "padding: 5px 10px; font-weight: 700; font-size: 11px;"
        )
        self.info_label = QLabel(
            "Student branches appear for Students & Faculty; Faculty/Staff departments apply to staff only."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setMinimumWidth(0)
        self.info_label.setStyleSheet(f"color: {c['muted']}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.summary_badge)
        layout.addWidget(self.info_label)

        self.unlisted_banner = QLabel()
        self.unlisted_banner.setWordWrap(True)
        self.unlisted_banner.setMinimumWidth(0)
        self.unlisted_banner.setStyleSheet(
            f"background: {c['warning_soft']}; color: {c['text']}; "
            f"border: 1px solid {c['warning']}; border-left: 4px solid {c['warning']}; "
            "border-radius: 7px; padding: 6px 10px; font-weight: 600; font-size: 11px;"
        )
        self.unlisted_banner.hide()
        layout.addWidget(self.unlisted_banner)

        filter_host = QWidget()
        filter_host.setMinimumWidth(0)
        filter_grid = QGridLayout(filter_host)
        filter_grid.setContentsMargins(0, 0, 0, 0)
        filter_grid.setHorizontalSpacing(8)
        filter_grid.setVerticalSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(0)
        self.search_input.setPlaceholderText("Search branch name or short code...")
        self.search_input.textChanged.connect(self._render_rows)

        self.category_filter = QComboBox()
        self.category_filter.setMinimumWidth(0)
        self.category_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.category_filter.setMinimumContentsLength(16)
        self.category_filter.addItem("All", "ALL")
        self.category_filter.addItem("Students & Faculty", "STUDENT")
        self.category_filter.addItem("Faculty & Staff Only", "FACULTY")
        self.category_filter.currentIndexChanged.connect(self._render_rows)

        filter_grid.addWidget(self.search_input, 0, 0)
        filter_grid.addWidget(QLabel("Scope:"), 0, 1)
        filter_grid.addWidget(self.category_filter, 0, 2)
        filter_grid.setColumnStretch(0, 1)
        layout.addWidget(filter_host)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Code",
            "Branch / Department",
            "Available To",
            "Duration",
            "Members",
        ])

        configure_table(self.table)
        self.table.setMinimumHeight(160)
        self.table.doubleClicked.connect(lambda _idx: self.handle_edit_department())

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)

        layout.addWidget(self.table, 1)

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)

        actions.addWidget(
            create_button(
                "+ Add Branch / Dept",
                self.handle_add_department,
                variant="SuccessButton",
            )
        )
        actions.addWidget(
            create_button(
                "Update Selected",
                self.handle_edit_department,
                variant="PrimaryButton",
            )
        )
        actions.addWidget(
            create_button(
                "Reassign Members",
                self.handle_reassign_members,
                variant="InfoButton",
            )
        )
        actions.addWidget(
            create_button(
                "Delete Selected",
                self.handle_delete_department,
                variant="DangerButton",
            )
        )
        actions.addWidget(
            create_button(
                "Restore Defaults",
                self.handle_restore_defaults,
                variant="SecondaryButton",
            )
        )
        actions.addWidget(
            create_button("Close", self.accept, variant="SecondaryButton")
        )

        layout.addWidget(actions_host)

        self.load_data()

    def _selected_department_record(self):
        selected = self.table.currentRow()
        if selected < 0:
            return None
        if 0 <= selected < len(self._filtered_rows):
            return self._filtered_rows[selected]
        return None

    def load_data(self):
        try:
            if hasattr(self.db, "get_departments_detailed"):
                self._all_rows = self.db.get_departments_detailed()
            else:
                rows = self.db.conn.execute(
                    """
                    SELECT id, name, category, duration_years, ''
                    FROM departments
                    ORDER BY CASE WHEN UPPER(category) = 'STUDENT' THEN 0 ELSE 1 END,
                             name COLLATE NOCASE ASC
                    """
                ).fetchall()
                self._all_rows = [
                    {
                        "id": int(r[0]),
                        "name": str(r[1] or ""),
                        "category": str(r[2] or "STUDENT").upper(),
                        "duration_years": int(r[3] or 3),
                        "branch_code": str(r[4] or ""),
                        "user_count": 0,
                        "student_count": 0,
                        "staff_count": 0,
                    }
                    for r in rows
                ]

            unlisted = (
                self.db.get_unlisted_user_departments()
                if hasattr(self.db, "get_unlisted_user_departments")
                else []
            )
            if unlisted:
                sample = ", ".join(f"{u['name']} ({u['user_count']})" for u in unlisted[:3])
                more = f" +{len(unlisted) - 3} more" if len(unlisted) > 3 else ""
                self.unlisted_banner.setText(
                    f"Note: Member records reference unlisted department(s): {sample}{more}. "
                    "Add matching entries here so dropdowns stay in sync."
                )
                self.unlisted_banner.show()
            else:
                self.unlisted_banner.hide()

            student_cnt = sum(1 for r in self._all_rows if r["category"] == "STUDENT")
            faculty_cnt = sum(1 for r in self._all_rows if r["category"] != "STUDENT")
            member_cnt = sum(int(r.get("user_count") or 0) for r in self._all_rows)
            self.summary_badge.setText(
                f"{student_cnt} Student Branches · {faculty_cnt} Faculty / Staff Depts · {member_cnt} Members"
            )
            self._render_rows()
        except Exception as error:
            show_error(self, "Department Loading Error", error)

    def _render_rows(self):
        c = get_dialog_colors(self)
        query = self.search_input.text().strip().casefold()
        cat_filter = str(self.category_filter.currentData() or "ALL").upper()

        filtered = []
        for rec in self._all_rows:
            if cat_filter != "ALL" and rec["category"] != cat_filter:
                continue
            if query:
                hay = f"{rec['name']} {rec.get('branch_code', '')}".casefold()
                if query not in hay:
                    continue
            filtered.append(rec)

        self._filtered_rows = filtered
        self.table.setRowCount(len(filtered))

        for row_index, rec in enumerate(filtered):
            raw_category = rec["category"]
            code_item = QTableWidgetItem(rec.get("branch_code") or "—")
            code_item.setForeground(QColor(c["primary"] if rec.get("branch_code") else c["muted"]))
            f_code = code_item.font()
            f_code.setBold(bool(rec.get("branch_code")))
            code_item.setFont(f_code)

            name_item = QTableWidgetItem(rec["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, rec["id"])
            f_name = name_item.font()
            f_name.setBold(True)
            name_item.setFont(f_name)

            available_label = (
                "Students & Faculty"
                if raw_category == "STUDENT"
                else "Faculty & Staff Only"
            )
            category_item = QTableWidgetItem(available_label)
            category_item.setData(Qt.ItemDataRole.UserRole, raw_category)
            category_item.setForeground(
                QColor(c["success"] if raw_category == "STUDENT" else c["purple"])
            )
            f_cat = category_item.font()
            f_cat.setBold(True)
            category_item.setFont(f_cat)

            duration = int(rec.get("duration_years") or 3)
            duration_text = (
                ("1 Year" if duration == 1 else f"{duration} Years")
                if raw_category == "STUDENT"
                else "N/A"
            )
            duration_item = QTableWidgetItem(duration_text)
            duration_item.setForeground(
                QColor(c["cyan"] if raw_category == "STUDENT" else c["muted"])
            )

            count = int(rec.get("user_count") or 0)
            members_item = QTableWidgetItem(str(count))
            members_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            members_item.setForeground(QColor(c["text"] if count > 0 else c["muted"]))

            self.table.setItem(row_index, 0, code_item)
            self.table.setItem(row_index, 1, name_item)
            self.table.setItem(row_index, 2, category_item)
            self.table.setItem(row_index, 3, duration_item)
            self.table.setItem(row_index, 4, members_item)

    def handle_add_department(self):
        dialog = EditDepartmentDialog(
            name="",
            category="STUDENT",
            duration=3,
            parent=self,
            branch_code="",
            mode="add",
            user_count=0,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, new_category, new_duration, new_code = dialog.get_full_data()
        success, message = self.db.add_department(
            new_name,
            new_category,
            new_duration,
            branch_code=new_code,
        )
        if success:
            self.load_data()
            self.departments_changed.emit()
            show_success(self, "Branch / Department Added", message)
        else:
            show_warning(self, "Add Failed", message)

    def handle_edit_department(self):
        rec = self._selected_department_record()
        if not rec:
            show_warning(
                self,
                "Selection Required",
                "Select a branch or department row to update.",
            )
            return

        dialog = EditDepartmentDialog(
            rec["name"],
            rec["category"],
            rec["duration_years"],
            self,
            branch_code=rec.get("branch_code") or "",
            mode="edit",
            user_count=rec.get("user_count") or 0,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name, new_category, new_duration, new_code = dialog.get_full_data()
        try:
            success, message = self.db.update_department(
                rec["id"],
                new_name,
                new_category,
                new_duration,
                branch_code=new_code,
            )
            if success:
                self.load_data()
                self.departments_changed.emit()
                show_success(self, "Updated", message)
            else:
                show_warning(self, "Update Failed", message)
        except Exception as error:
            show_error(self, "Database Error", error)

    def handle_reassign_members(self):
        rec = self._selected_department_record()
        if not rec:
            show_warning(
                self,
                "Selection Required",
                "Select a branch or department whose members you want to move.",
            )
            return
        user_count = int(rec.get("user_count") or 0)
        student_count = int(rec.get("student_count") or 0)
        if user_count == 0:
            show_warning(
                self,
                "No Assigned Members",
                f"No members are currently assigned to '{rec['name']}'.",
            )
            return
        targets = [
            r["name"]
            for r in self._all_rows
            if r["id"] != rec["id"]
            and (student_count == 0 or r["category"] == "STUDENT")
        ]
        if not targets:
            show_warning(
                self,
                "No Compatible Target",
                "Add another compatible branch first before reassigning these members.",
            )
            return
        dlg = ReassignDepartmentDialog(
            rec["name"],
            targets,
            user_count,
            student_count=student_count,
            title="Reassign Branch / Department Members",
            confirm_text="Move Members",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target = dlg.selected_target()
        success, message = self.db.reassign_department_users(rec["name"], target)
        if success:
            self.load_data()
            self.departments_changed.emit()
            show_success(self, "Members Reassigned", message)
        else:
            show_warning(self, "Reassignment Failed", message)

    def handle_delete_department(self):
        rec = self._selected_department_record()
        if not rec:
            show_warning(
                self,
                "Selection Required",
                "Select a branch or department row to delete.",
            )
            return

        user_count = int(rec.get("user_count") or 0)
        student_count = int(rec.get("student_count") or 0)
        reassign_to = None
        if user_count > 0:
            targets = [
                r["name"]
                for r in self._all_rows
                if r["id"] != rec["id"]
                and (student_count == 0 or r["category"] == "STUDENT")
            ]
            if not targets:
                show_warning(
                    self,
                    "Cannot Delete Branch",
                    f"'{rec['name']}' still has {user_count} assigned member(s) and no other compatible branch exists.",
                )
                return
            dlg = ReassignDepartmentDialog(
                rec["name"],
                targets,
                user_count,
                student_count=student_count,
                title=f"Reassign & Delete '{rec['name']}'",
                confirm_text="Reassign & Delete",
                parent=self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            reassign_to = dlg.selected_target()
        else:
            answer = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete branch / department '{rec['name']}'?\n\n"
                "You can re-add it later or click Restore Defaults.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        success, message = self.db.delete_department(rec["id"], reassign_to=reassign_to)
        if success:
            self.load_data()
            self.departments_changed.emit()
            show_success(self, "Deleted", message)
        else:
            show_warning(self, "Delete Failed", message)

    def handle_restore_defaults(self):
        success, message = self.db.restore_default_departments()
        if success:
            self.load_data()
            self.departments_changed.emit()
            show_success(self, "Default Branches", message)
        else:
            show_warning(self, "Restore Failed", message)


# ============================================================
# ISSUE BOOK WIZARD
# ============================================================

class IssueBookDialog(QDialog):
    """Dialog for collecting book issue information."""

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db
        self._user_edited_days = False

        configure_dialog(
            self,
            "Issue Book",
            470,
            370,
            min_width=360,
            min_height=300,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(
            create_heading("📤 Issue a Book")
        )

        form_host = QWidget()
        form_host_layout = QVBoxLayout(form_host)
        form_host_layout.setContentsMargins(0, 0, 4, 0)
        form_host_layout.setSpacing(10)

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=10)

        self.input_book = QLineEdit()
        self.input_book.setPlaceholderText(
            "Enter Book ID or scan barcode"
        )

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText(
            "Enter User ID or PIN"
        )
        self.input_user.textChanged.connect(self._update_user_policy_hint)

        try:
            default_days = int(
                self.db.get_setting("default_days", 14)
            )
        except (ValueError, TypeError):
            default_days = 14

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setValue(
            max(1, min(default_days, 365))
        )
        self.spin_days.setSuffix(" days")
        self.spin_days.valueChanged.connect(self._on_spin_days_edited)

        form.addRow("Book ID:", self.input_book)
        form.addRow("User ID:", self.input_user)
        form.addRow("Loan Duration:", self.spin_days)

        form_host_layout.addLayout(form)

        c_hint = get_dialog_colors(self)
        self.lbl_policy_hint = QLabel(
            "Loan duration automatically adopts the member's role policy when User ID is entered."
        )
        self.lbl_policy_hint.setWordWrap(True)
        self.lbl_policy_hint.setStyleSheet(
            f"background: {c_hint['surface_alt']}; color: {c_hint['muted']}; "
            f"border: 1px solid {c_hint['border']}; border-radius: 7px; padding: 7px 10px;"
        )
        form_host_layout.addWidget(self.lbl_policy_hint)
        form_host_layout.addStretch()

        layout.addWidget(wrap_in_scroll_area(form_host, object_name="IssueDialogScroll"), 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(
            create_button("Cancel", self.reject, variant="SecondaryButton")
        )

        buttons.addWidget(
            create_button(
                "📤 Issue Book",
                self.validate_and_accept,
                variant="PrimaryButton",
            )
        )

        layout.addLayout(buttons)

    def _on_spin_days_edited(self):
        if not self.spin_days.signalsBlocked():
            self._user_edited_days = True

    def _update_user_policy_hint(self, *_):
        c = get_dialog_colors(self)
        uid = self.input_user.text().strip()
        if not uid:
            self.lbl_policy_hint.setText(
                "Loan duration automatically adopts the member's role policy when User ID is entered."
            )
            self.lbl_policy_hint.setStyleSheet(
                f"background: {c['surface_alt']}; color: {c['muted']}; "
                f"border: 1px solid {c['border']}; border-radius: 7px; padding: 7px 10px;"
            )
            return
        ok, user = self.db.get_user_details(uid)
        if not ok or not user:
            self.lbl_policy_hint.setText("Member ID not found in directory.")
            self.lbl_policy_hint.setStyleSheet(
                f"background: {c['danger_soft']}; color: {c['danger']}; "
                f"border: 1px solid {c['danger']}; border-radius: 7px; padding: 7px 10px; font-weight: 600;"
            )
            return
        role = user[3]
        policy = self.db.get_loan_policy(role)
        role_days = max(1, min(int(policy.get("default_days", 14)), 365))
        if not self._user_edited_days:
            self.spin_days.blockSignals(True)
            self.spin_days.setValue(role_days)
            self.spin_days.blockSignals(False)
        pending_fines = self.db.get_user_pending_fines_total(user[0])
        fine_note = f" · Unpaid fines: {money(pending_fines)}" if pending_fines > 0 else ""
        self.lbl_policy_hint.setText(
            f"{user[1]} ({role}) · Max {policy.get('max_books', 3)} books · "
            f"Default {role_days} days · ₹{policy.get('fine_rate', 2.0):.2f}/day{fine_note}"
        )
        banner_key = "warning" if pending_fines > 0 else "primary"
        self.lbl_policy_hint.setStyleSheet(
            f"background: {c[banner_key + '_soft']}; color: {c[banner_key]}; "
            f"border: 1px solid {c[banner_key]}; border-radius: 7px; padding: 7px 10px; font-weight: 600;"
        )

    def validate_and_accept(self):
        if not self.input_book.text().strip():
            show_warning(
                self,
                "Missing Book ID",
                "Enter a Book ID."
            )
            self.input_book.setFocus()
            return

        if not self.input_user.text().strip():
            show_warning(
                self,
                "Missing User ID",
                "Enter a User ID."
            )
            self.input_user.setFocus()
            return

        self.accept()

    def get_data(self):
        return (
            self.input_book.text().strip(),
            self.input_user.text().strip(),
            self.spin_days.value()
        )


# ============================================================
# RETURN BOOK WIZARD
# ============================================================

class ReturnBookDialog(QDialog):
    """Dialog for collecting book return information."""

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        configure_dialog(
            self,
            "Return Book",
            440,
            280
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(
            create_heading("📥 Process Book Return")
        )

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=10)

        self.input_book = QLineEdit()
        self.input_book.setPlaceholderText("Enter Book ID")

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Enter User ID or PIN")

        form.addRow("Book ID:", self.input_book)
        form.addRow("User ID:", self.input_user)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(
            create_button("Cancel", self.reject, variant="SecondaryButton")
        )

        buttons.addWidget(
            create_button(
                "📥 Confirm Return",
                self.validate_and_accept,
                variant="SuccessButton",
            )
        )

        layout.addLayout(buttons)

    def validate_and_accept(self):
        if not self.input_book.text().strip():
            show_warning(
                self,
                "Missing Book ID",
                "Enter a Book ID."
            )
            self.input_book.setFocus()
            return

        if not self.input_user.text().strip():
            show_warning(
                self,
                "Missing User ID",
                "Enter a User ID."
            )
            self.input_user.setFocus()
            return

        self.accept()

    def get_data(self):
        return (
            self.input_book.text().strip(),
            self.input_user.text().strip()
        )


class BatchCirculationDialog(QDialog):
    """Collect the common user or book details for a batch operation."""

    def __init__(
        self,
        db,
        mode,
        selected_ids,
        selection_type,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self._user_edited_days = False
        self.mode = str(mode).upper()
        self.selected_ids = [str(value) for value in selected_ids]
        self.selection_type = selection_type
        self.is_book_selection = selection_type == "books"
        operation = "Issue" if self.mode == "ISSUE" else "Return"
        selected_label = "books" if self.is_book_selection else "users"
        target_label = "User ID" if self.is_book_selection else "Book ID"

        configure_dialog(
            self,
            f"{operation} Books for Selected {selected_label.title()}",
            480,
            380 if self.mode == "ISSUE" else 330,
            min_width=360,
            min_height=290,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(
            create_heading(
                f"{operation} {len(self.selected_ids)} selected "
                f"{selected_label}"
            )
        )

        body_host = QWidget()
        body_layout = QVBoxLayout(body_host)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(10)

        details = QLabel(", ".join(self.selected_ids))
        details.setWordWrap(True)
        body_layout.addWidget(details)

        hint = (
            "All selected books will be processed for this user."
            if self.is_book_selection
            else "The selected book will be processed for each user."
        )
        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        body_layout.addWidget(hint_label)

        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=10)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText(
            f"Enter {target_label} or scan barcode"
        )
        form.addRow(f"{target_label}:", self.target_input)

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        try:
            default_days = int(db.get_setting("default_days", 14))
        except (TypeError, ValueError):
            default_days = 14
        self.spin_days.setValue(max(1, min(default_days, 365)))
        self.spin_days.setSuffix(" days")
        self.spin_days.valueChanged.connect(self._on_spin_days_edited)
        if self.mode == "ISSUE":
            form.addRow("Loan Duration:", self.spin_days)

        body_layout.addLayout(form)

        self.lbl_policy_hint = QLabel("")
        self.lbl_policy_hint.setWordWrap(True)
        body_layout.addWidget(self.lbl_policy_hint)
        if self.is_book_selection and self.mode == "ISSUE":
            self.target_input.textChanged.connect(self._update_target_policy_hint)
        else:
            self.lbl_policy_hint.setVisible(False)

        body_layout.addStretch()
        layout.addWidget(wrap_in_scroll_area(body_host, object_name="BatchCircDialogScroll"), 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(create_button("Cancel", self.reject, variant="SecondaryButton"))
        buttons.addWidget(
            create_button(
                f"{operation} Selected",
                self.validate_and_accept,
                variant="PrimaryButton" if self.mode == "ISSUE" else "SuccessButton",
            )
        )
        layout.addLayout(buttons)

    def _on_spin_days_edited(self):
        if not self.spin_days.signalsBlocked():
            self._user_edited_days = True

    def _update_target_policy_hint(self, *_):
        c = get_dialog_colors(self)
        uid = self.target_input.text().strip()
        if not uid:
            self.lbl_policy_hint.setText("")
            self.lbl_policy_hint.setStyleSheet("")
            return
        ok, user = self.db.get_user_details(uid)
        if not ok or not user:
            self.lbl_policy_hint.setText("Member ID not found.")
            self.lbl_policy_hint.setStyleSheet(
                f"color: {c['danger']}; font-weight: 600;"
            )
            return
        role = user[3]
        policy = self.db.get_loan_policy(role)
        role_days = max(1, min(int(policy.get("default_days", 14)), 365))
        if not self._user_edited_days:
            self.spin_days.blockSignals(True)
            self.spin_days.setValue(role_days)
            self.spin_days.blockSignals(False)
        self.lbl_policy_hint.setText(
            f"{user[1]} ({role}) · Max {policy.get('max_books', 3)} books · "
            f"Default {role_days} days · ₹{policy.get('fine_rate', 2.0):.2f}/day"
        )
        self.lbl_policy_hint.setStyleSheet(
            f"background: {c['primary_soft']}; color: {c['primary']}; "
            f"border: 1px solid {c['primary']}; border-radius: 7px; padding: 6px 10px; font-weight: 600;"
        )

    def validate_and_accept(self):
        if not self.target_input.text().strip():
            target = "User ID" if self.is_book_selection else "Book ID"
            show_warning(
                self,
                f"Missing {target}",
                f"Enter a {target}.",
            )
            self.target_input.setFocus()
            return
        self.accept()

    def get_data(self):
        return self.target_input.text().strip(), self.spin_days.value()


class CustomEmailDialog(QDialog):
    """Compose a one-off message for a library user."""

    def __init__(
        self,
        recipient_name,
        parent=None,
        initial_subject="",
        initial_body="",
    ):
        super().__init__(parent)
        configure_dialog(
            self,
            "Send Email to User",
            540,
            430,
            min_width=380,
            min_height=320,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(
            create_heading(f"Compose message for {recipient_name}")
        )

        form_host = QWidget()
        form_host_layout = QVBoxLayout(form_host)
        form_host_layout.setContentsMargins(0, 0, 4, 0)
        form = QFormLayout()
        configure_inspector_form(form, horizontal_spacing=12, vertical_spacing=10)
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Email subject")
        if initial_subject:
            self.subject_input.setText(str(initial_subject))
        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText("Write your message...")
        self.body_input.setMinimumHeight(130)
        if initial_body:
            self.body_input.setPlainText(str(initial_body))
        form.addRow("Subject:", self.subject_input)
        form.addRow("Message:", self.body_input)
        form_host_layout.addLayout(form, 1)
        layout.addWidget(wrap_in_scroll_area(form_host, object_name="CustomEmailScroll"), 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        send_btn = buttons.addButton(
            "Send",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        if send_btn is not None:
            send_btn.setObjectName("PrimaryButton")
            send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setObjectName("SecondaryButton")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self):
        if not self.subject_input.text().strip():
            show_warning(self, "Missing Subject", "Enter an email subject.")
            self.subject_input.setFocus()
            return
        if not self.body_input.toPlainText().strip():
            show_warning(self, "Missing Message", "Enter a message.")
            self.body_input.setFocus()
            return
        self.accept()

    def get_data(self):
        return (
            self.subject_input.text().strip(),
            self.body_input.toPlainText().strip(),
        )


# ============================================================
# ADVANCED LOAN RENEWAL DIALOG
# ============================================================

class RenewLoanDialog(QDialog):
    """Advanced loan renewal dialog with live projection, presets,
    fine resolution, policy override, and renewal history audit.
    """

    data_updated = pyqtSignal()

    def __init__(self, db, loan_id, parent=None):
        super().__init__(parent)

        self.db = db
        self.loan_id = loan_id
        display_loan_id = format_log_id_display(loan_id)
        self.preview = {}
        self.result_details = {}
        self.result_message = ""

        configure_dialog(
            self,
            f"Renew Loan — Transaction {display_loan_id}",
            760,
            765,
            min_width=460,
            min_height=360,
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(10)

        main_layout.addWidget(
            create_heading(f"🔄 Advanced Loan Renewal — {display_loan_id}")
        )

        scroll_area = QScrollArea()
        scroll_area.setObjectName("RenewScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.viewport().setObjectName("RenewScrollViewport")
        scroll_area.setStyleSheet(
            "QScrollArea#RenewScrollArea, "
            "QWidget#RenewScrollViewport, "
            "QWidget#RenewScrollContent { background: transparent; border: none; }"
        )

        scroll_content = QWidget()
        scroll_content.setObjectName("RenewScrollContent")
        scroll_content.setMinimumWidth(0)
        sections_layout = QVBoxLayout(scroll_content)
        sections_layout.setContentsMargins(0, 0, 4, 0)
        sections_layout.setSpacing(8)

        # 1. Loan & Member Snapshot
        summary_group = QGroupBox("Loan && Policy Snapshot")
        summary_grid = QGridLayout(summary_group)
        summary_grid.setContentsMargins(6, 4, 6, 4)
        summary_grid.setHorizontalSpacing(12)
        summary_grid.setVerticalSpacing(5)
        summary_grid.setColumnStretch(1, 1)
        summary_grid.setColumnStretch(2, 1)

        self.lbl_book = configure_wrapped_label(QLabel())
        self.lbl_member = configure_wrapped_label(QLabel())
        self.lbl_dates = configure_wrapped_label(QLabel())
        self.lbl_status_badge = QLabel()
        self.lbl_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status_badge.setMinimumHeight(26)
        self.lbl_stock_info = configure_wrapped_label(QLabel())
        self.lbl_renewal_quota = configure_wrapped_label(QLabel(), expanding_width=False)

        summary_grid.addWidget(QLabel("<b>Book:</b>"), 0, 0)
        summary_grid.addWidget(self.lbl_book, 0, 1, 1, 2)
        summary_grid.addWidget(self.lbl_status_badge, 0, 3)

        summary_grid.addWidget(QLabel("<b>Borrower:</b>"), 1, 0)
        summary_grid.addWidget(self.lbl_member, 1, 1, 1, 3)

        summary_grid.addWidget(QLabel("<b>Loan Window:</b>"), 2, 0)
        summary_grid.addWidget(self.lbl_dates, 2, 1, 1, 3)

        summary_grid.addWidget(QLabel("<b>Shelf & Quota:</b>"), 3, 0)
        summary_grid.addWidget(self.lbl_stock_info, 3, 1, 1, 2)
        summary_grid.addWidget(self.lbl_renewal_quota, 3, 3)

        sections_layout.addWidget(summary_group)

        # 2. Extension Schedule Configurator
        schedule_group = QGroupBox("Extension Schedule && Live Preview")
        schedule_layout = QVBoxLayout(schedule_group)
        schedule_layout.setContentsMargins(6, 4, 6, 4)
        schedule_layout.setSpacing(8)

        presets_host = QWidget()
        presets_row = FlowLayout(presets_host, margin=0, h_spacing=6, v_spacing=6)
        presets_row.addWidget(QLabel("Quick Extend:"))

        self.btn_preset_7 = create_button("+7 Days", lambda: self.set_extend_days(7), variant="SecondaryButton")
        self.btn_preset_14 = create_button("+14 Days", lambda: self.set_extend_days(14), variant="SecondaryButton")
        self.btn_preset_policy = create_button(
            "Role Default",
            lambda: self.set_extend_days(self.preview.get("default_days", 14)),
            variant="InfoButton",
        )
        for btn in (self.btn_preset_7, self.btn_preset_14, self.btn_preset_policy):
            presets_row.addWidget(btn)

        presets_row.addWidget(QLabel("Custom:"))

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setSuffix(" days")
        self.spin_days.setMinimumWidth(104)
        self.spin_days.setMinimumHeight(34)
        self.spin_days.valueChanged.connect(self.update_preview)
        presets_row.addWidget(self.spin_days)
        schedule_layout.addWidget(presets_host)

        base_row = QHBoxLayout()
        base_row.setSpacing(10)
        base_row.addWidget(QLabel("Calculate From:"))

        self.combo_base_mode = QComboBox()
        self.combo_base_mode.setMinimumHeight(34)
        self.combo_base_mode.setMinimumWidth(240)
        self.combo_base_mode.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.combo_base_mode.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo_base_mode.setMinimumContentsLength(22)
        self.combo_base_mode.addItem("Current Due Date (Keep unused days)", "DUE_DATE")
        self.combo_base_mode.addItem("Today (Reset overdue window from now)", "TODAY")
        self.combo_base_mode.currentIndexChanged.connect(self.update_preview)
        base_row.addWidget(self.combo_base_mode, 1)
        schedule_layout.addLayout(base_row)

        self.projection_card = QFrame()
        self.projection_card.setObjectName("ProjectionCard")
        self.projection_card.setFrameShape(QFrame.Shape.StyledPanel)
        self.projection_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        projection_layout = QHBoxLayout(self.projection_card)
        projection_layout.setContentsMargins(12, 9, 12, 9)
        projection_layout.setSpacing(10)

        self.lbl_projection = configure_wrapped_label(QLabel())
        self.lbl_projection.setMinimumHeight(20)
        projection_layout.addWidget(self.lbl_projection, 1)
        schedule_layout.addWidget(self.projection_card)

        sections_layout.addWidget(schedule_group)

        # 3. Overdue Fine Handling & Policy Controls
        self.policy_group = QGroupBox("Fine Resolution, Notes && Policy")
        policy_layout = QFormLayout(self.policy_group)
        policy_layout.setContentsMargins(6, 4, 6, 4)
        configure_inspector_form(policy_layout, horizontal_spacing=10, vertical_spacing=7)

        self.lbl_fine_summary = configure_wrapped_label(QLabel())
        self.combo_fine_action = QComboBox()
        self.combo_fine_action.setMinimumHeight(34)
        self.combo_fine_action.setMinimumWidth(260)
        self.combo_fine_action.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.combo_fine_action.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo_fine_action.setMinimumContentsLength(26)
        self.combo_fine_action.addItem(
            "Carry fine onto loan balance (collect at return)",
            "CARRY",
        )
        self.combo_fine_action.addItem(
            "Collected overdue fine now",
            "COLLECTED",
        )
        self.combo_fine_action.addItem(
            "Waive overdue fine",
            "WAIVED",
        )

        self.lbl_fine_row_title = QLabel("Overdue Fine:")
        self.lbl_fine_row_title.setMinimumWidth(0)
        self.lbl_action_row_title = QLabel("Fine Handling:")
        self.lbl_action_row_title.setMinimumWidth(0)
        policy_layout.addRow(self.lbl_fine_row_title, self.lbl_fine_summary)
        policy_layout.addRow(self.lbl_action_row_title, self.combo_fine_action)

        self.chk_override = QCheckBox(
            "Librarian Override — Allow renewal beyond policy limit"
        )
        self.chk_override.toggled.connect(self.update_preview)
        policy_layout.addRow("", self.chk_override)

        self.input_notes = QLineEdit()
        self.input_notes.setMinimumHeight(34)
        self.input_notes.setPlaceholderText(
            "Optional renewal reason or remark (e.g. Exam extension, Project use)..."
        )
        note_lbl = QLabel("Renewal Note:")
        note_lbl.setMinimumWidth(0)
        policy_layout.addRow(note_lbl, self.input_notes)

        self.lbl_alert = configure_wrapped_label(QLabel())
        self.lbl_alert.setMinimumHeight(28)
        policy_layout.addRow("", self.lbl_alert)

        sections_layout.addWidget(self.policy_group)

        # 4. Prior Renewal Timeline
        history_group = QGroupBox("Renewal Audit History")
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(6, 4, 6, 4)
        history_layout.setSpacing(6)

        self.lbl_no_history = QLabel("No previous renewals recorded for this loan.")
        history_layout.addWidget(self.lbl_no_history)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "Renewed On", "Previous Due", "New Due", "Extended", "Fine & Notes"
        ])
        configure_table(self.history_table)
        self.history_table.setMinimumHeight(90)
        self.history_table.setMaximumHeight(130)
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.history_table)

        sections_layout.addWidget(history_group)
        sections_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # 5. Footer
        buttons = QHBoxLayout()
        buttons.addStretch()

        self.btn_cancel = create_button("Cancel", self.reject, variant="SecondaryButton")
        self.btn_confirm = create_button("🔄 Confirm Renewal", self.confirm_renewal, variant="PrimaryButton")

        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_confirm)
        main_layout.addLayout(buttons)

        self._initialize_from_preview()

    def _initialize_from_preview(self):
        initial = self.db.get_loan_renewal_preview(self.loan_id, base_mode="auto")
        self.preview = initial

        if not initial.get("found"):
            self.lbl_alert.setText(initial.get("block_reason", "Loan not found."))
            self.btn_confirm.setEnabled(False)
            return

        default_days = max(1, min(int(initial.get("default_days", 14)), 365))
        self.btn_preset_policy.setText(f"+{default_days}d (Policy)")

        self.spin_days.blockSignals(True)
        self.spin_days.setValue(default_days)
        self.spin_days.blockSignals(False)

        mode_index = self.combo_base_mode.findData(
            initial.get("effective_base_mode", "DUE_DATE")
        )
        if mode_index >= 0:
            self.combo_base_mode.blockSignals(True)
            self.combo_base_mode.setCurrentIndex(mode_index)
            self.combo_base_mode.blockSignals(False)

        self._populate_history(initial.get("history", []))
        self.update_preview()

    def set_extend_days(self, days):
        clamped = max(1, min(int(days), 365))
        self.spin_days.setValue(clamped)

    def _populate_history(self, history):
        if not history:
            self.lbl_no_history.show()
            self.history_table.hide()
            return

        self.lbl_no_history.hide()
        self.history_table.show()
        self.history_table.setRowCount(len(history))
        for row_idx, entry in enumerate(history):
            fine_assessed = float(entry.get("fine_assessed", 0.0) or 0.0)
            fine_action = entry.get("fine_action", "NONE")
            note = entry.get("notes", "")
            parts = []
            if fine_assessed > 0:
                parts.append(f"Fine ₹{fine_assessed:.2f} ({fine_action.title()})")
            if note:
                parts.append(note)
            summary = " · ".join(parts) if parts else "Standard renewal"
            mode_label = (
                "From Today"
                if entry.get("base_mode") == "TODAY"
                else "From Due Date"
            )
            values = [
                entry.get("renewed_at", ""),
                entry.get("previous_due_date", ""),
                entry.get("new_due_date", ""),
                f"+{entry.get('extended_days', 0)}d ({mode_label})",
                summary,
            ]
            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setToolTip(str(val))
                self.history_table.setItem(row_idx, col_idx, item)

    def update_preview(self):
        base_mode = self.combo_base_mode.currentData() or "DUE_DATE"
        extend_days = self.spin_days.value()
        override = self.chk_override.isChecked()

        self.preview = self.db.get_loan_renewal_preview(
            self.loan_id,
            extend_days=extend_days,
            base_mode=base_mode,
            allow_limit_override=override,
        )
        p = self.preview
        if not p.get("found"):
            self.btn_confirm.setEnabled(False)
            self.lbl_alert.setText(p.get("block_reason", "Loan record missing."))
            return

        self.lbl_book.setText(f"{p['book_title']}  (ID: {p['book_id']})")
        self.lbl_member.setText(
            f"{p['user_name']}  (ID: {p['user_id']} · {p['user_role']})"
        )
        self.lbl_dates.setText(
            f"Issued: {p['checkout_date'] or '—'}    |    Current Due: {p['due_date'] or '—'}"
        )
        self.lbl_stock_info.setText(
            f"Copies on shelf: {p['available_copies']} / {p['total_copies']}   ·   "
            f"Member active loans: {p['active_loans_count']} / {p['max_books']}"
        )

        max_r = int(p.get("max_renewals", 0))
        used_r = int(p.get("renewal_count", 0))
        quota_text = (
            f"Renewals: {used_r} / {max_r}"
            if max_r > 0
            else f"Renewals: {used_r} (Unlimited)"
        )
        self.lbl_renewal_quota.setText(f"<b>{quota_text}</b>")

        c = get_dialog_colors(self)
        display_status = p["display_status"]
        if display_status == "OVERDUE":
            badge_text = f"OVERDUE ({p['overdue_days']}d)"
            badge_bg, badge_fg = c["danger_soft"], c["danger"]
        elif display_status == "DUE TODAY":
            badge_text = "DUE TODAY"
            badge_bg, badge_fg = c["warning_soft"], c["warning"]
        elif display_status == "RETURNED":
            badge_text = "RETURNED"
            badge_bg, badge_fg = c["success_soft"], c["success"]
        else:
            badge_text = "ISSUED"
            badge_bg, badge_fg = c["primary_soft"], c["primary"]
        self.lbl_status_badge.setText(badge_text)
        self.lbl_status_badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; "
            f"border: 1px solid {badge_fg}; border-radius: 10px; "
            "padding: 4px 10px; font-weight: 700; font-size: 11px;"
        )

        # Format projected date nicely
        new_due_str = p.get("new_due_date", "")
        day_label = ""
        try:
            dt = datetime.datetime.strptime(new_due_str, "%Y-%m-%d %H:%M")
            day_label = dt.strftime("%a, %d %b %Y · %H:%M")
        except ValueError:
            day_label = new_due_str

        net_days = int(p.get("net_days_from_today", 0))
        net_desc = (
            f"{net_days} day(s) from today"
            if net_days >= 0
            else f"{abs(net_days)} day(s) in the past"
        )
        base_desc = (
            "Today" if p.get("effective_base_mode") == "TODAY" else "Current Due Date"
        )
        self.lbl_projection.setText(
            f"<b>Projected New Due Date:</b>  {day_label}  "
            f"<i>(+{extend_days} days from {base_desc} · {net_desc})</i>"
        )

        # Fine controls visibility
        accrued = float(p.get("accrued_fine", 0.0) or 0.0)
        show_fines = accrued > 0
        self.lbl_fine_row_title.setVisible(show_fines)
        self.lbl_fine_summary.setVisible(show_fines)
        self.lbl_action_row_title.setVisible(show_fines)
        self.combo_fine_action.setVisible(show_fines)
        if show_fines:
            carried = float(p.get("carried_fine", 0.0) or 0.0)
            extra = f" (plus ₹{carried:.2f} prior carried balance)" if carried > 0 else ""
            self.lbl_fine_summary.setText(
                f"₹{accrued:.2f}  ({p['overdue_days']} overdue day(s) × "
                f"₹{p['fine_rate']:.2f}/day){extra}"
            )

        show_override = bool(p.get("requires_override")) and p.get("status") == "ISSUED"
        self.chk_override.setVisible(show_override)

        block_reason = p.get("block_reason", "")
        warnings = list(p.get("warnings", []))
        if block_reason:
            self.lbl_alert.setText(f"⛔ {block_reason}")
            self.lbl_alert.setStyleSheet(
                f"background: {c['danger_soft']}; color: {c['danger']}; "
                f"border: 1px solid {c['danger']}; border-radius: 7px; "
                "padding: 6px 10px; font-weight: 700;"
            )
        elif warnings:
            self.lbl_alert.setText("⚠️ " + "  |  ".join(warnings))
            self.lbl_alert.setStyleSheet(
                f"background: {c['warning_soft']}; color: {c['warning']}; "
                f"border: 1px solid {c['warning']}; border-radius: 7px; "
                "padding: 6px 10px; font-weight: 700;"
            )
        else:
            self.lbl_alert.setText("✅ Eligible for standard renewal.")
            self.lbl_alert.setStyleSheet(
                f"background: {c['success_soft']}; color: {c['success']}; "
                f"border: 1px solid {c['success']}; border-radius: 7px; "
                "padding: 6px 10px; font-weight: 700;"
            )

        self.btn_confirm.setEnabled(bool(p.get("eligible")))

    def confirm_renewal(self):
        if not self.preview.get("eligible"):
            show_warning(
                self,
                "Cannot Renew Loan",
                self.preview.get("block_reason", "Loan is not eligible for renewal."),
            )
            return

        extend_days = self.spin_days.value()
        base_mode = self.combo_base_mode.currentData() or "DUE_DATE"
        fine_action = (
            self.combo_fine_action.currentData()
            if self.combo_fine_action.isVisible()
            else "NONE"
        )
        notes = self.input_notes.text().strip()
        override = self.chk_override.isChecked() and self.chk_override.isVisible()

        try:
            success, details, message = self.db.renew_loan(
                self.loan_id,
                extend_days=extend_days,
                base_mode=base_mode,
                fine_action=fine_action,
                notes=notes,
                allow_limit_override=override,
            )
            if success:
                self.result_details = details
                self.result_message = message
                self.data_updated.emit()
                self.accept()
            else:
                show_warning(self, "Renewal Failed", message)
                self.update_preview()
        except Exception as error:
            show_error(self, "Renewal Error", error)


# ============================================================
# ADVANCED PENDING FINES COLLECTION & WAIVER DESK
# ============================================================

class PendingFinesDialog(QDialog):
    """Interactive desk to review, collect, waive, and export pending library fines."""

    data_updated = pyqtSignal()

    HEADERS = [
        "Log ID",
        "User ID",
        "Member Name",
        "Book ID",
        "Book Title",
        "Loan Status",
        "Date Ref",
        "Renewals",
        "Fine Balance",
    ]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.all_rows = []
        self.filtered_rows = []
        self._compact_table_mode = None

        configure_dialog(
            self,
            "Pending Fines & Collection Desk",
            1140,
            650,
            min_width=500,
            min_height=380,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(create_heading("💳 Pending Fines & Collection Desk"), 1)
        refresh_btn = create_button("↻ Refresh", self.load_fines, variant="InfoButton")
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        c = get_dialog_colors(self)
        self.summary_label.setStyleSheet(
            f"background: {c['amber_tint']}; color: {c['text']}; "
            f"border: 1px solid {c['warning']}; border-left: 4px solid {c['warning']}; "
            "border-radius: 8px; padding: 9px 12px; font-size: 12px; font-weight: 700;"
        )
        layout.addWidget(self.summary_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Filter by User ID, member name, Book ID, book title, or Log ID..."
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.apply_filter)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        configure_table(self.table)
        self.table.setMinimumHeight(160)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._apply_table_column_modes()
        self.table.itemSelectionChanged.connect(self._update_action_states)
        layout.addWidget(self.table, 1)

        actions_host = QWidget()
        actions = FlowLayout(actions_host, margin=0, h_spacing=8, v_spacing=6)
        self.collect_btn = create_button(
            "💳 Mark Selected Paid",
            lambda: self.settle_selected("PAID"),
            False,
            variant="SuccessButton",
        )
        self.waive_btn = create_button(
            "Waive Selected Fine",
            lambda: self.settle_selected("WAIVED"),
            False,
            variant="WarningButton",
        )
        self.collect_user_btn = create_button(
            "Collect All for Selected User",
            self.settle_selected_user_all,
            False,
            variant="PrimaryButton",
        )
        self.export_btn = create_button(
            "Export CSV",
            self.export_csv,
            False,
            variant="InfoButton",
        )
        close_btn = create_button("Close", self.accept, variant="SecondaryButton")

        actions.addWidget(self.collect_btn)
        actions.addWidget(self.waive_btn)
        actions.addWidget(self.collect_user_btn)
        actions.addWidget(self.export_btn)
        actions.addWidget(close_btn)
        layout.addWidget(actions_host)

        self.load_fines()

    def _apply_table_column_modes(self):
        compact = self.width() < 920
        if compact == self._compact_table_mode:
            return
        self._compact_table_mode = compact
        fines_header = self.table.horizontalHeader()
        fines_header.setMinimumSectionSize(44)
        if compact:
            fines_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            for col, width in (
                (0, 122),
                (1, 102),
                (2, 140),
                (3, 64),
                (4, 190),
                (5, 86),
                (6, 120),
                (7, 70),
                (8, 96),
            ):
                self.table.setColumnWidth(col, width)
        else:
            for col in (0, 1, 3, 5, 6, 7, 8):
                fines_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            fines_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(2, 155)
            fines_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self._apply_table_column_modes()

    def load_fines(self):
        c = get_dialog_colors(self)
        try:
            ok, rows = self.db.get_pending_fines_detailed()
            self.all_rows = list(rows or []) if ok else []
            summary = self.db.get_fines_financial_summary()
            has_pending = float(summary.get("pending_fines", 0.0) or 0.0) > 0
            accent_key = "warning" if has_pending else "success"
            bg_tint = c.get("amber_tint", c["warning_soft"]) if has_pending else c["success_soft"]
            self.summary_label.setStyleSheet(
                f"background: {bg_tint}; color: {c['text']}; "
                f"border: 1px solid {c[accent_key]}; border-left: 4px solid {c[accent_key]}; "
                "border-radius: 8px; padding: 9px 12px; font-size: 12px; font-weight: 700;"
            )
            self.summary_label.setText(
                f"Pending Items: {len(self.all_rows)}   |   "
                f"Unpaid Balance: {money(summary['pending_fines'])}   |   "
                f"Collected (All Time): {money(summary['total_collected'])}   |   "
                f"Waived (All Time): {money(summary['waived_total'])}"
            )
        except Exception as error:
            self.all_rows = []
            show_error(self, "Pending Fines Error", error)
        self.apply_filter()

    def apply_filter(self, *_):
        query = self.search_input.text().strip().casefold()
        if not query:
            self.filtered_rows = list(self.all_rows)
        else:
            self.filtered_rows = [
                row for row in self.all_rows
                if query in " ".join(safe_text(v) for v in row).casefold()
            ]
        self.populate_table()

    def populate_table(self):
        c = get_dialog_colors(self)
        self.table.setRowCount(len(self.filtered_rows))
        for r_idx, row in enumerate(self.filtered_rows):
            (
                log_id, user_id, user_name, book_id, book_title,
                fine_amount, status, due_date, return_date, ren_count,
            ) = row
            date_ref = return_date or due_date or "—"
            raw_status = str(status or "").upper()
            vals = [
                format_log_id_display(log_id),
                safe_text(user_id),
                safe_text(user_name),
                safe_text(book_id),
                safe_text(book_title),
                safe_text(status),
                safe_text(date_ref),
                str(int(ren_count or 0)),
                money(fine_amount),
            ]
            for c_idx, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                    item.setForeground(QColor(c["primary"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif c_idx == 5:
                    color_key = (
                        "danger"
                        if raw_status == "OVERDUE"
                        else "primary"
                        if raw_status == "ISSUED"
                        else "success"
                    )
                    item.setForeground(QColor(c[color_key]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif c_idx == 7 and int(ren_count or 0) > 0:
                    item.setForeground(QColor(c["cyan"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                elif c_idx == 8:
                    item.setForeground(QColor(c["danger"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table.setItem(r_idx, c_idx, item)
        self.export_btn.setEnabled(bool(self.filtered_rows))
        if self.filtered_rows:
            self.table.selectRow(0)
        self._update_action_states()

    def _selected_record(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_action_states(self):
        has_sel = self._selected_record() is not None
        self.collect_btn.setEnabled(has_sel)
        self.waive_btn.setEnabled(has_sel)
        self.collect_user_btn.setEnabled(has_sel)

    def settle_selected(self, action):
        rec = self._selected_record()
        if not rec:
            return
        log_id, user_id, user_name, book_id, _title, fine_amount = rec[:6]
        verb = "collect & mark PAID" if action == "PAID" else "WAIVE"
        answer = QMessageBox.question(
            self,
            "Confirm Fine Settlement",
            f"Do you want to {verb} {money(fine_amount)} for {user_name} ({user_id}) "
            f"on book {book_id} (Transaction {format_log_id_display(log_id)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = self.db.settle_loan_fine(log_id, action=action)
        if success:
            self.data_updated.emit()
            show_success(self, "Fine Updated", message)
            self.load_fines()
        else:
            show_warning(self, "Settlement Failed", message)

    def settle_selected_user_all(self):
        rec = self._selected_record()
        if not rec:
            return
        user_id, user_name = rec[1], rec[2]
        user_total = self.db.get_user_pending_fines_total(user_id)
        answer = QMessageBox.question(
            self,
            "Collect All User Fines",
            f"Mark all unpaid fines totaling {money(user_total)} for "
            f"{user_name} ({user_id}) as PAID?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = self.db.settle_all_user_fines(user_id, action="PAID")
        if success:
            self.data_updated.emit()
            show_success(self, "All Fines Settled", message)
            self.load_fines()
        else:
            show_warning(self, "Bulk Settlement Failed", message)

    def export_csv(self):
        if not self.filtered_rows:
            return
        filename = (
            "pending_fines_"
            + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pending Fines",
            filename,
            "CSV Files (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(self.HEADERS)
                for row in self.filtered_rows:
                    writer.writerow([
                        row[0], row[1], row[2], row[3], row[4],
                        row[6], row[8] or row[7], row[9], f"{float(row[5] or 0):.2f}",
                    ])
            show_success(self, "Export Successful", f"Pending fines exported to:\n{path}")
        except Exception as error:
            show_error(self, "Export Failed", error)

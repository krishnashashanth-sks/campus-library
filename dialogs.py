import io
import os
import secrets
import cv2
import barcode

from barcode.writer import ImageWriter
from PIL import Image

from PyQt6.QtWidgets import (
    QApplication, QDialog, QPushButton, QLineEdit, QMessageBox, QVBoxLayout,
    QComboBox, QLabel, QSpinBox, QFileDialog, QHBoxLayout,
    QCheckBox, QFrame, QTableWidget, QWidget, QSizePolicy,
    QHeaderView, QFormLayout, QTableWidgetItem, QAbstractItemView,
    QDialogButtonBox, QGridLayout, QGroupBox, QPlainTextEdit,
)

from PyQt6.QtCore import (
    pyqtSignal, Qt, QTimer, QRegularExpression
)

from PyQt6.QtGui import (
    QPixmap, QImage, QFont, QRegularExpressionValidator,
    QIntValidator, QColor
)

from utils import (
    clear_layout,
    is_valid_book_id,
    is_valid_phone_number,
    is_valid_user_id,
)


# ============================================================
# SHARED HELPERS
# ============================================================

def configure_dialog(dialog, title, width=None, height=None):
    """Apply common dialog configuration without overriding ThemeManager."""
    dialog.setWindowTitle(title)

    if width and height:
        dialog.resize(width, height)

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
    label.setProperty("class", "dialog-heading")
    return label


def create_button(text, callback=None, enabled=True):
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setEnabled(enabled)

    if callback:
        button.clicked.connect(callback)

    return button


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
            470
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)

        heading = create_heading(
            "📚 Add New Book" if book_id is None
            else f"✏️ Edit Book — {book_id}"
        )
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(13)

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

        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = create_button("Cancel", self.reject)
        save = create_button(
            "💾 Save Book" if book_id is None else "💾 Update Book",
            self.save_book
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

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

        configure_dialog(self, "Record Library Complaint", 560, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(create_heading("New library complaint"))

        form = QFormLayout()
        self.user_combo = QComboBox()
        self.user_combo.addItem("General / anonymous", "")

        success, users = self.db.get_users()
        if not success:
            raise RuntimeError("Unable to load users for the complaint form.")
        for user in users:
            self.user_combo.addItem(
                f"{user[1]} ({user[0]})",
                str(user[0]),
            )

        self.subject_input = QLineEdit()
        self.subject_input.setMaxLength(160)
        self.subject_input.setPlaceholderText("Short summary")

        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText(
            "Describe the issue, suggestion, or complaint..."
        )
        self.body_input.setMinimumHeight(170)

        form.addRow("User:", self.user_combo)
        form.addRow("Subject:", self.subject_input)
        form.addRow("Details:", self.body_input)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(create_button("Cancel", self.reject))
        buttons.addWidget(
            create_button("Submit Complaint", self.submit_complaint)
        )
        layout.addLayout(buttons)

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

        show_success(
            self,
            "Complaint Submitted",
            f"Complaint #{complaint[0]} was saved and its notifications were "
            "added to the email queue.",
        )
        self.accept()


class ComplaintManagementDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.complaints = []
        configure_dialog(self, "Library Complaints", 900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(create_heading("Complaint inbox"))

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID", "User", "Subject", "Status", "Received",
        ])
        configure_table(self.table)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(
            self.show_selected_complaint
        )
        layout.addWidget(self.table, 1)

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setMaximumHeight(110)
        layout.addWidget(self.body_view)

        actions = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItem("Open", "OPEN")
        self.status_combo.addItem("In Progress", "IN_PROGRESS")
        self.status_combo.addItem("Resolved", "RESOLVED")
        self.update_status_button = create_button(
            "Update Status",
            self.update_status,
        )
        close_button = create_button("Close", self.accept)
        actions.addWidget(self.status_combo)
        actions.addWidget(self.update_status_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.load_complaints()

    def load_complaints(self):
        try:
            self.complaints = self.db.get_complaints()
        except Exception as error:
            show_error(self, "Complaint Loading Error", error)
            return

        self.table.setRowCount(len(self.complaints))
        for row_index, complaint in enumerate(self.complaints):
            user_label = (
                f"{complaint[2]} ({complaint[1]})"
                if complaint[1]
                else "General / anonymous"
            )
            values = (
                complaint[0],
                user_label,
                complaint[4],
                complaint[6].replace("_", " ").title(),
                complaint[7],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    int(complaint[0]),
                )
                self.table.setItem(row_index, column, item)

        if self.complaints:
            self.table.selectRow(0)
        else:
            self.body_view.setPlainText("No complaints have been recorded.")
            self.update_status_button.setEnabled(False)

    def show_selected_complaint(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        complaint_id = self.table.item(
            rows[0].row(),
            0,
        ).data(Qt.ItemDataRole.UserRole)
        complaint = next(
            (
                item for item in self.complaints
                if int(item[0]) == complaint_id
            ),
            None,
        )
        if not complaint:
            return

        self.body_view.setPlainText(
            f"From: {complaint[2]} ({complaint[1] or 'anonymous'})\n"
            f"Email: {complaint[3] or 'Not provided'}\n\n"
            f"{complaint[5]}"
        )
        index = self.status_combo.findData(complaint[6])
        if index >= 0:
            self.status_combo.setCurrentIndex(index)
        self.update_status_button.setEnabled(True)

    def update_status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            show_warning(
                self,
                "Select a Complaint",
                "Select a complaint to update its status.",
            )
            return

        complaint_id = self.table.item(
            rows[0].row(),
            0,
        ).data(Qt.ItemDataRole.UserRole)
        success, message = self.db.update_complaint_status(
            complaint_id,
            self.status_combo.currentData(),
        )
        if not success:
            show_error(self, "Status Update Failed", message)
            return

        self.load_complaints()


class EmailQueueManagementDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.email_items = []
        configure_dialog(self, "Email Queue Manager", 1100, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(create_heading("Email queue"))
        layout.addWidget(QLabel(
            "Review messages without sending them. Delete selected messages, "
            "including sent history, or clear all pending and failed messages."
        ))

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Show:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All", None)
        self.status_filter.addItem("Pending", "PENDING")
        self.status_filter.addItem("Failed", "FAILED")
        self.status_filter.addItem("Sent", "SENT")
        self.status_filter.currentIndexChanged.connect(self.load_items)
        self.count_label = QLabel()
        filters.addWidget(self.status_filter)
        filters.addStretch()
        filters.addWidget(self.count_label)
        layout.addLayout(filters)

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
        self.body_view.setMaximumHeight(120)
        layout.addWidget(self.body_view)

        actions = QHBoxLayout()
        refresh_button = create_button("Refresh", self.load_items)
        self.delete_selected_button = create_button(
            "Delete Selected",
            self.delete_selected,
        )
        self.delete_all_button = create_button(
            "Delete All Pending / Failed",
            self.delete_all_unsent,
        )
        close_button = create_button("Close", self.accept)
        actions.addWidget(refresh_button)
        actions.addWidget(self.delete_selected_button)
        actions.addWidget(self.delete_all_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)
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

        self.count_label.setText(
            f"{counts['pending']} pending · {counts['failed']} failed · "
            f"{counts['sent']} sent"
        )
        self.delivery_warning.setText(
            "Queued delivery is enabled. Disable it in Settings before "
            "managing queued messages."
            if delivery_enabled
            else "Queued delivery is disabled. Messages will stay queued "
            "until you explicitly enable delivery in Settings."
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
        self.table.setRowCount(len(visible_items))
        for row_index, email in enumerate(visible_items):
            (
                email_id, recipient, subject, trigger, status,
                retry_count, created_at, _sent_at, _body,
            ) = email
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
    ):
        super().__init__(parent)
        self.releases = list(releases)
        self.current_version = current_version
        self.can_install = can_install
        self.selected_release = None
        configure_dialog(self, "Application Version Manager", 980, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addWidget(create_heading("Published application versions"))
        layout.addWidget(QLabel(
            f"Installed version: {current_version}. Select a published "
            "release to install it or roll back to it."
        ))

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Version", "Published", "Package", "Availability",
        ])
        configure_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.itemSelectionChanged.connect(self.show_release_details)
        self.table.cellDoubleClicked.connect(
            lambda _row, _column: self.install_selected()
        )
        layout.addWidget(self.table, 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)

        self.install_button = create_button(
            "Install / Roll Back to Selected",
            self.install_selected,
            enabled=False,
        )
        if not can_install:
            self.install_button.setText(
                "Install Requires Packaged Windows App"
            )
        actions = QHBoxLayout()
        refresh_note = QLabel(
            "Only stable releases with a verified Library-Windows.zip can "
            "be installed."
        )
        refresh_note.setWordWrap(True)
        close_button = create_button("Close", self.reject)
        actions.addWidget(refresh_note, 1)
        actions.addWidget(self.install_button)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self._populate()

    def _populate(self):
        self.table.setRowCount(len(self.releases))
        for row, release in enumerate(self.releases):
            package_text = (
                "Verified"
                if release.get("installable")
                else "Unavailable"
            )
            availability = (
                "Installed version"
                if release.get("current")
                else (
                    "Ready to install"
                    if release.get("installable")
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
                self.table.setItem(row, column, item)
        if self.releases:
            self.table.selectRow(0)
        else:
            self.details.setPlainText(
                "No stable numeric releases were found."
            )

    def show_release_details(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.details.clear()
            self.install_button.setEnabled(False)
            return
        index = self.table.item(
            rows[0].row(),
            0,
        ).data(Qt.ItemDataRole.UserRole)
        release = self.releases[index]
        notes = release.get("release_notes", "").strip()
        self.details.setPlainText(
            f"{release['tag_name']} — "
            f"{'Currently installed' if release.get('current') else 'Published release'}\n\n"
            f"{notes or release.get('reason') or 'No release notes.'}"
        )
        self.install_button.setEnabled(
            self.can_install
            and release.get("installable", False)
            and not release.get("current", False)
        )

    def install_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        index = self.table.item(
            rows[0].row(),
            0,
        ).data(Qt.ItemDataRole.UserRole)
        release = self.releases[index]
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
            520
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)

        layout.addWidget(
            create_heading(
                "👤 Register New User" if user_id is None
                else f"✏️ Edit User — {user_id}"
            )
        )

        form = QFormLayout()
        form.setSpacing(13)

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

        layout.addLayout(form)
        layout.addStretch()

        self.combo_role.currentTextChanged.connect(
            self.on_role_changed
        )

        if user_id is not None:
            self.load_user_data()

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(create_button("Cancel", self.reject))
        buttons.addWidget(
            create_button(
                "💾 Save User",
                self.save_user
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

            role = str(row[3] or "")
            department = str(row[4] or "")

            self.combo_role.setCurrentText(role)
            self.on_role_changed(role)

            index = self.combo_department.findText(department)

            if index >= 0:
                self.combo_department.setCurrentIndex(index)

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
            self.lbl_department.setText("Teaching Department:")

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
            regex = QRegularExpression(r"^[A-Za-z]{2}[0-9]{6}$")
            placeholder = "Branch code + 6 digits (e.g. CS000001)"

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
                "(for example, 24001-CS-097). Employee IDs must use a "
                "2-letter branch code followed by 6 digits.",
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

        configure_dialog(
            self,
            f"Circulation History — {user_id}",
            1050,
            620
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(16)

        main_layout.addWidget(
            create_heading(f"📋 Circulation History — User {user_id}")
        )

        content = QHBoxLayout()
        content.setSpacing(16)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Book ID",
            "Title",
            "Author",
            "Status",
            "Issue Date",
            "Due Date",
            "Fine"
        ])

        configure_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.detail_container = QFrame()
        self.detail_container.setMinimumWidth(280)
        self.detail_container.setMaximumWidth(310)

        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(16, 16, 16, 16)
        self.detail_layout.setSpacing(12)

        self.table.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        content.addWidget(self.table, 3)
        content.addWidget(self.detail_container, 1)

        main_layout.addLayout(content)

        self.show_default_inspector()
        self.load_user_books()

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

                status_text = str(status).upper()

                values = [
                    safe_text(book_id),
                    safe_text(title),
                    safe_text(author),
                    status_text,
                    safe_text(checkout),
                    safe_text(due),
                    money(fine)
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if column == 3:
                        item.setForeground(
                            QColor("#f59e0b")
                            if status_text == "ISSUED"
                            else QColor("#10b981")
                        )

                    self.table.setItem(row_index, column, item)

            self.table.blockSignals(False)

            if self.books_data:
                self.table.selectRow(0)
                self.display_record_details(self.books_data[0])
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
            self.display_record_details(self.books_data[row])

    def display_record_details(self, book):
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

        clear_layout(self.detail_layout)

        is_issued = str(status).upper() == "ISSUED"

        self.detail_layout.addWidget(
            create_heading("Loan Control Center")
        )

        banner = QLabel(
            "🟠 Issued Book"
            if is_issued else
            "🟢 Returned Record"
        )
        banner.setWordWrap(True)
        set_status_property(
            banner,
            "issued" if is_issued else "returned"
        )

        self.detail_layout.addWidget(banner)

        form = QFormLayout()
        form.setSpacing(9)

        details = [
            ("Book ID:", book_id),
            ("Title:", title),
            ("Author:", author),
            ("Publisher:", publisher),
            ("Issue Date:", checkout),
            ("Due Date:", due),
            ("Returned:", returned or "Not yet returned"),
            ("Fine:", money(fine))
        ]

        for label, value in details:
            value_label = QLabel(safe_text(value))
            value_label.setWordWrap(True)
            form.addRow(label, value_label)

        self.detail_layout.addLayout(form)

        if is_issued:
            button = create_button(
                "↩ Return Book",
                lambda: self.handle_return_action(book_id)
            )
            self.detail_layout.addWidget(button)

        self.detail_layout.addStretch()

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
            660
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(create_heading("🏷️ Book Barcode Generator"))

        self.input_book_id = QLineEdit(str(book_id))
        self.input_book_id.setPlaceholderText("Book ID")

        self.input_book_title = QLineEdit(str(title))
        self.input_book_title.setPlaceholderText("Book Title")

        self.input_book_author = QLineEdit(str(author))
        self.input_book_author.setPlaceholderText("Author")

        self.input_book_publisher = QLineEdit(str(publisher))
        self.input_book_publisher.setPlaceholderText("Publisher")

        form = QFormLayout()
        form.setSpacing(10)

        form.addRow("Book ID:", self.input_book_id)
        form.addRow("Title:", self.input_book_title)
        form.addRow("Author:", self.input_book_author)
        form.addRow("Publisher:", self.input_book_publisher)

        layout.addLayout(form)

        self.lbl_preview = QLabel("Barcode Preview")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumHeight(180)
        self.lbl_preview.setProperty("class", "barcode-preview")
        layout.addWidget(self.lbl_preview)

        self.chk_box_db = QCheckBox("Save book to database")

        if book_id:
            self.chk_box_db.setVisible(False)
        else:
            self.chk_box_db.setChecked(True)

        layout.addWidget(self.chk_box_db)

        self.btn_generate = create_button(
            "⚙ Generate Barcode",
            self.generate_barcode
        )

        self.btn_save = create_button(
            "💾 Export PNG",
            self.save_png,
            enabled=False
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

            self.lbl_preview.setPixmap(
                pixmap.scaled(
                    self.lbl_preview.width() - 20,
                    self.lbl_preview.height() - 20,
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

        configure_dialog(
            self,
            "Quick Barcode Scanner",
            440,
            650
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        layout.addWidget(create_heading("📷 Quick Barcode Scanner"))

        self.lbl_capture = QLabel(
            "Initializing camera..."
        )
        self.lbl_capture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_capture.setMinimumHeight(190)
        self.lbl_capture.setProperty("class", "camera-preview")

        layout.addWidget(self.lbl_capture)

        layout.addWidget(QLabel("Book ID — USB Scanner or Manual"))

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

        layout.addWidget(self.input_book_id)

        self.lbl_status = QLabel("Waiting for barcode...")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        layout.addWidget(QLabel("User ID / PIN"))

        self.input_user_id = QLineEdit()
        self.input_user_id.setPlaceholderText("Enter User ID")
        layout.addWidget(self.input_user_id)

        layout.addWidget(QLabel("Loan Duration"))

        try:
            days = int(self.db.get_setting("default_days", 14))
        except (ValueError, TypeError):
            days = 14

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setValue(max(1, min(days, 365)))
        self.spin_days.setSuffix(" days")

        layout.addWidget(self.spin_days)

        buttons = QHBoxLayout()

        self.issue_btn = create_button(
            "📤 Issue Book",
            lambda: self.process_circulation("issue"),
            False
        )

        self.return_btn = create_button(
            "📥 Return Book",
            lambda: self.process_circulation("return"),
            False
        )

        buttons.addWidget(self.issue_btn)
        buttons.addWidget(self.return_btn)

        layout.addLayout(buttons)

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

    def on_manual_text_change(self, text):
        code = text.strip()
        self.book_id = code or None

        self.issue_btn.setEnabled(bool(code))
        self.return_btn.setEnabled(bool(code))

        if code:
            self.lbl_status.setText(
                f"Book detected: {code}"
            )
        else:
            self.lbl_status.setText("Waiting for barcode...")

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

            self.lbl_capture.setPixmap(
                pixmap.scaled(
                    self.lbl_capture.width(),
                    self.lbl_capture.height(),
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

        self.issue_btn.setEnabled(True)
        self.return_btn.setEnabled(True)

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
            "Library System Security",
            390,
            320
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)

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
            self.verify_password
        )

        self.btn_login.setDefault(False)
        self.btn_login.setAutoDefault(False)
        layout.addWidget(self.btn_login)

        self.btn_forgot_password = create_button(
            "Forgot password?",
            self.open_password_recovery,
        )
        self.btn_forgot_password.setDefault(False)
        self.btn_forgot_password.setAutoDefault(False)
        layout.addWidget(self.btn_forgot_password)

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
            500,
            280,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        layout.addWidget(
            create_heading("Save this recovery code")
        )
        description = QLabel(
            "Keep this code somewhere secure and separate from the "
            "computer. It is shown only once and is required to reset "
            "the administrator password."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.code_input = QLineEdit(self.recovery_code)
        self.code_input.setReadOnly(True)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setStyleSheet(
            "font-size: 15px; font-weight: 700; letter-spacing: 1px;"
        )
        self.code_input.setMinimumHeight(42)
        layout.addWidget(self.code_input)

        copy_button = create_button(
            "Copy Recovery Code",
            lambda: QApplication.clipboard().setText(self.recovery_code),
        )
        layout.addWidget(copy_button)

        self.saved_checkbox = QCheckBox(
            "I have saved this code somewhere secure."
        )
        layout.addWidget(self.saved_checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_button = create_button("Cancel", self.reject)
        buttons.addWidget(cancel_button)

        self.confirm_button = create_button(
            "Continue",
            self.accept,
            enabled=False,
        )
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

        self.saved_checkbox.toggled.connect(
            self.confirm_button.setEnabled
        )


class AdminPasswordRecoveryDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        configure_dialog(
            self,
            "Reset Administrator Password",
            450,
            310,
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
        cancel_button = create_button("Cancel", self.reject)
        buttons.addWidget(cancel_button)
        reset_button = create_button(
            "Reset Password",
            self.reset_password,
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

        self.setFixedSize(440, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(18)

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

        self.text_label = QLabel("Library Management System")
        self.text_label.setFont(
            QFont("Segoe UI", 17, QFont.Weight.Bold)
        )
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.text_label)

        self.sub_label = QLabel(
            "Loading database and application services..."
        )
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label.setWordWrap(True)

        layout.addWidget(self.sub_label)

    def set_status(self, message):
        self.sub_label.setText(str(message))


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

        configure_dialog(
            self,
            f"Book History — {book_title}",
            1050,
            620
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(16)

        main_layout.addWidget(
            create_heading(
                f"📖 Circulation Audit — {book_title}"
            )
        )

        content = QHBoxLayout()
        content.setSpacing(16)

        self.table = QTableWidget()
        self.table.setColumnCount(6)

        self.table.setHorizontalHeaderLabels([
            "Borrower ID",
            "Status",
            "Issue Date",
            "Due Date",
            "Return Date",
            "Fine"
        ])

        configure_table(self.table)

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.detail_container = QFrame()
        self.detail_container.setMinimumWidth(280)
        self.detail_container.setMaximumWidth(310)

        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(16, 16, 16, 16)
        self.detail_layout.setSpacing(12)

        self.table.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )

        content.addWidget(self.table, 3)
        content.addWidget(self.detail_container, 1)

        main_layout.addLayout(content)

        self.show_default_inspector()
        self.load_history()

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
                    user_id,
                    checkout_date,
                    due_date,
                    return_date,
                    fine_amount,
                    status
                FROM circulation_logs
                WHERE book_id = ?
                ORDER BY id DESC
                """,
                (self.book_id,)
            )

            self.history_data = cursor.fetchall()

            self.table.blockSignals(True)
            self.table.setRowCount(len(self.history_data))

            for row_index, record in enumerate(self.history_data):
                user_id, checkout, due, returned, fine, status = record

                status_text = str(status).upper()

                values = [
                    safe_text(user_id),
                    status_text,
                    safe_text(checkout),
                    safe_text(due),
                    safe_text(returned),
                    money(fine)
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if column == 1:
                        item.setForeground(
                            QColor("#f59e0b")
                            if status_text == "ISSUED"
                            else QColor("#10b981")
                        )

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
        user_id, checkout, due, returned, fine, status = record

        clear_layout(self.detail_layout)

        is_issued = str(status).upper() == "ISSUED"

        self.detail_layout.addWidget(
            create_heading("Audit Control Center")
        )

        banner = QLabel(
            "🟠 Issued Book"
            if is_issued else
            "🟢 Completed Loan"
        )

        banner.setWordWrap(True)

        set_status_property(
            banner,
            "issued" if is_issued else "returned"
        )

        self.detail_layout.addWidget(banner)

        form = QFormLayout()
        form.setSpacing(9)

        details = [
            ("Book ID:", self.book_id),
            ("Borrower ID:", user_id),
            ("Status:", status),
            ("Issue Date:", checkout),
            ("Due Date:", due),
            ("Returned:", returned or "Not yet returned"),
            ("Fine:", money(fine))
        ]

        for label, value in details:
            value_label = QLabel(safe_text(value))
            value_label.setWordWrap(True)
            form.addRow(label, value_label)

        self.detail_layout.addLayout(form)

        if is_issued:
            self.detail_layout.addWidget(
                create_button(
                    "↩ Return Book",
                    lambda: self.handle_return_action(user_id)
                )
            )

        self.detail_layout.addStretch()

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
# EDIT DEPARTMENT DIALOG
# ============================================================

class EditDepartmentDialog(QDialog):
    """Dialog for editing a department or student branch."""

    def __init__(self, name, category, duration, parent=None):
        super().__init__(parent)

        configure_dialog(
            self,
            "Edit Department",
            430,
            320
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(
            create_heading("✏️ Edit Department Details")
        )

        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(13)

        self.input_name = QLineEdit(str(name))
        self.input_name.setMaxLength(100)

        self.combo_cat = QComboBox()
        self.combo_cat.addItems(["STUDENT", "FACULTY"])
        self.combo_cat.setCurrentText(str(category).upper())

        self.combo_duration = QComboBox()
        self.combo_duration.addItems([
            "2 Years",
            "3 Years",
            "4 Years",
            "5 Years"
        ])

        try:
            duration = int(duration)
        except (ValueError, TypeError):
            duration = 3

        index = self.combo_duration.findText(
            f"{duration} Years"
        )

        self.combo_duration.setCurrentIndex(
            index if index >= 0 else 1
        )

        self.duration_label = QLabel("Duration:")

        self.form_layout.addRow("Department Name:", self.input_name)
        self.form_layout.addRow("Category:", self.combo_cat)
        self.form_layout.addRow(
            self.duration_label,
            self.combo_duration
        )

        layout.addLayout(self.form_layout)
        layout.addStretch()

        self.combo_cat.currentIndexChanged.connect(
            self.on_category_changed
        )

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(
            create_button("Cancel", self.reject)
        )

        buttons.addWidget(
            create_button("Save Changes", self.validate_and_accept)
        )

        layout.addLayout(buttons)

        self.on_category_changed()

    def on_category_changed(self, *args):
        is_student = (
            self.combo_cat.currentText() == "STUDENT"
        )

        self.duration_label.setVisible(is_student)
        self.combo_duration.setVisible(is_student)

    def validate_and_accept(self):
        if not self.input_name.text().strip():
            show_warning(
                self,
                "Validation Error",
                "Department name cannot be empty."
            )
            return

        self.accept()

    def get_data(self):
        duration = (
            int(self.combo_duration.currentText().split()[0])
            if self.combo_cat.currentText() == "STUDENT"
            else 3
        )

        return (
            self.input_name.text().strip(),
            self.combo_cat.currentText(),
            duration
        )


# ============================================================
# DEPARTMENT MANAGER
# ============================================================

class DepartmentManagerDialog(QDialog):

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        configure_dialog(
            self,
            "Department Management",
            720,
            610
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)

        layout.addWidget(
            create_heading("🏛️ Branch & Department Management")
        )

        self.table = QTableWidget()
        self.table.setColumnCount(3)

        self.table.setHorizontalHeaderLabels([
            "Department / Branch",
            "Category",
            "Duration"
        ])

        configure_table(self.table)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents
        )

        layout.addWidget(self.table)

        layout.addWidget(QLabel("Add New Department"))

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_new_dept = QLineEdit()
        self.input_new_dept.setPlaceholderText(
            "Enter department or branch name"
        )
        self.input_new_dept.setMaxLength(100)

        self.combo_cat = QComboBox()
        self.combo_cat.addItems(["STUDENT", "FACULTY"])

        self.combo_duration = QComboBox()
        self.combo_duration.addItems([
            "2 Years",
            "3 Years",
            "4 Years",
            "5 Years"
        ])
        self.combo_duration.setCurrentIndex(1)

        self.btn_add = create_button(
            "＋ Add",
            self.handle_add_department
        )

        input_row.addWidget(self.input_new_dept, 3)
        input_row.addWidget(self.combo_cat)
        input_row.addWidget(self.combo_duration)
        input_row.addWidget(self.btn_add)

        layout.addLayout(input_row)

        self.combo_cat.currentIndexChanged.connect(
            self.on_category_changed
        )

        actions = QHBoxLayout()

        actions.addWidget(
            create_button(
                "✏️ Edit Selected",
                self.handle_edit_department
            )
        )

        actions.addWidget(
            create_button(
                "🗑 Remove Selected",
                self.handle_delete_department
            )
        )

        layout.addLayout(actions)

        self.load_data()

    def on_category_changed(self, *args):
        self.combo_duration.setVisible(
            self.combo_cat.currentText() == "STUDENT"
        )

    def load_data(self):
        try:
            cursor = self.db.conn.cursor()

            cursor.execute(
                """
                SELECT id, name, category, duration_years
                FROM departments
                ORDER BY name ASC
                """
            )

            rows = cursor.fetchall()

            self.table.setRowCount(len(rows))

            for row_index, row in enumerate(rows):
                dept_id, name, category, duration = row

                name_item = QTableWidgetItem(str(name))
                name_item.setData(
                    Qt.ItemDataRole.UserRole,
                    dept_id
                )

                category_item = QTableWidgetItem(str(category))

                duration_text = (
                    f"{duration} Years"
                    if str(category).upper() == "STUDENT"
                    else "N/A"
                )

                duration_item = QTableWidgetItem(duration_text)

                self.table.setItem(row_index, 0, name_item)
                self.table.setItem(row_index, 1, category_item)
                self.table.setItem(row_index, 2, duration_item)

        except Exception as error:
            show_error(self, "Department Loading Error", error)

    def handle_add_department(self):
        name = self.input_new_dept.text().strip()
        category = self.combo_cat.currentText()

        if not name:
            show_warning(
                self,
                "Validation Error",
                "Enter a department name."
            )
            return

        duration = (
            int(self.combo_duration.currentText().split()[0])
            if category == "STUDENT"
            else 3
        )

        try:
            success, message = self.db.add_department(
                name,
                category,
                duration
            )

            if success:
                self.input_new_dept.clear()
                self.combo_duration.setCurrentIndex(1)
                self.load_data()
                show_success(self, "Department Added", message)
            else:
                show_warning(self, "Unable to Add", message)

        except Exception as error:
            show_error(self, "Database Error", error)

    def handle_edit_department(self):
        selected = self.table.currentRow()

        if selected < 0:
            show_warning(
                self,
                "Selection Required",
                "Select a department to edit."
            )
            return

        name_item = self.table.item(selected, 0)
        category_item = self.table.item(selected, 1)
        duration_item = self.table.item(selected, 2)

        if not name_item:
            return

        dept_id = name_item.data(Qt.ItemDataRole.UserRole)
        current_name = name_item.text()

        current_category = (
            category_item.text()
            if category_item else "STUDENT"
        )

        try:
            current_duration = int(
                duration_item.text().split()[0]
            )
        except (ValueError, AttributeError, IndexError):
            current_duration = 3

        dialog = EditDepartmentDialog(
            current_name,
            current_category,
            current_duration,
            self
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name, new_category, new_duration = dialog.get_data()

        try:
            success, message = self.db.update_department(
                dept_id,
                new_name,
                new_category,
                new_duration
            )

            if success:
                self.load_data()
                show_success(self, "Updated", message)
            else:
                show_warning(self, "Update Failed", message)

        except Exception as error:
            show_error(self, "Database Error", error)

    def handle_delete_department(self):
        selected = self.table.currentRow()

        if selected < 0:
            show_warning(
                self,
                "Selection Required",
                "Select a department to remove."
            )
            return

        name_item = self.table.item(selected, 0)

        if not name_item:
            return

        department_name = name_item.text()

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Remove department '{department_name}'?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            success, message = self.db.delete_department(
                department_name
            )

            if success:
                self.load_data()
                show_success(self, "Department Removed", message)
            else:
                show_warning(self, "Delete Failed", message)

        except Exception as error:
            show_error(self, "Database Error", error)


# ============================================================
# ISSUE BOOK WIZARD
# ============================================================

class IssueBookDialog(QDialog):
    """Dialog for collecting book issue information."""

    def __init__(self, db, parent=None):
        super().__init__(parent)

        self.db = db

        configure_dialog(
            self,
            "Issue Book",
            440,
            330
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(
            create_heading("📤 Issue a Book")
        )

        form = QFormLayout()
        form.setSpacing(13)

        self.input_book = QLineEdit()
        self.input_book.setPlaceholderText(
            "Enter Book ID or scan barcode"
        )

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText(
            "Enter User ID or PIN"
        )

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

        form.addRow("Book ID:", self.input_book)
        form.addRow("User ID:", self.input_user)
        form.addRow("Loan Duration:", self.spin_days)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()

        buttons.addWidget(
            create_button("Cancel", self.reject)
        )

        buttons.addWidget(
            create_button(
                "📤 Issue Book",
                self.validate_and_accept
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
        form.setSpacing(13)

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
            create_button("Cancel", self.reject)
        )

        buttons.addWidget(
            create_button(
                "📥 Confirm Return",
                self.validate_and_accept
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
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(
            create_heading(
                f"{operation} {len(self.selected_ids)} selected "
                f"{selected_label}"
            )
        )

        details = QLabel(", ".join(self.selected_ids))
        details.setWordWrap(True)
        layout.addWidget(details)

        hint = (
            "All selected books will be processed for this user."
            if self.is_book_selection
            else "The selected book will be processed for each user."
        )
        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        form = QFormLayout()
        form.setSpacing(12)
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
        if self.mode == "ISSUE":
            form.addRow("Loan Duration:", self.spin_days)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(create_button("Cancel", self.reject))
        buttons.addWidget(
            create_button(
                f"{operation} Selected",
                self.validate_and_accept,
            )
        )
        layout.addLayout(buttons)

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

    def __init__(self, recipient_name, parent=None):
        super().__init__(parent)
        configure_dialog(self, "Send Email to User", 540, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(
            create_heading(f"Compose message for {recipient_name}")
        )

        form = QFormLayout()
        form.setSpacing(12)
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Email subject")
        self.body_input = QPlainTextEdit()
        self.body_input.setPlaceholderText("Write your message...")
        self.body_input.setMinimumHeight(190)
        form.addRow("Subject:", self.subject_input)
        form.addRow("Message:", self.body_input)
        layout.addLayout(form, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Send
            | QDialogButtonBox.StandardButton.Cancel
        )
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
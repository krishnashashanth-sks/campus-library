import io
import os
import cv2
import barcode

from barcode.writer import ImageWriter
from PIL import Image

from PyQt6.QtWidgets import (
    QDialog, QPushButton, QLineEdit, QMessageBox, QVBoxLayout,
    QComboBox, QLabel, QSpinBox, QFileDialog, QHBoxLayout,
    QCheckBox, QFrame, QTableWidget, QWidget, QSizePolicy,
    QHeaderView, QFormLayout, QTableWidgetItem, QAbstractItemView,
    QDialogButtonBox, QGridLayout, QGroupBox
)

from PyQt6.QtCore import (
    pyqtSignal, Qt, QTimer, QRegularExpression
)

from PyQt6.QtGui import (
    QPixmap, QImage, QFont, QRegularExpressionValidator,
    QIntValidator, QValidator, QColor
)

from utils import clear_layout


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
        self.input_id.setPlaceholderText("Example: CS-101")
        self.input_id.setMaxLength(50)

        id_regex = QRegularExpression(
            r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$"
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
            470
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
        self.input_phoneno.setMaxLength(13)

        phone_regex = QRegularExpression(r"^\+?[0-9]{10,12}$")
        self.input_phoneno.setValidator(
            QRegularExpressionValidator(
                phone_regex,
                self.input_phoneno
            )
        )

        form.addRow("Role:", self.combo_role)
        form.addRow(self.lbl_department, self.combo_department)
        form.addRow("User ID / PIN:", self.input_id)
        form.addRow("Full Name:", self.input_name)
        form.addRow("Phone:", self.input_phoneno)

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
                r"^[0-9]{5}-[A-Za-z]{2,4}-[0-9]{3}$"
            )
            placeholder = "Example: 24001-CS-097"

        elif role in (
            "Faculty",
            "Guest Lecturer",
            "Admin",
            "Librarian"
        ):
            regex = QRegularExpression(r"^[0-9]{5}$")
            placeholder = "5-digit Staff ID"

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

        if phone and not phone.lstrip("+").isdigit():
            show_warning(
                self,
                "Invalid Phone",
                "Enter a valid phone number."
            )
            return

        validator = self.input_id.validator()

        if validator:
            state = validator.validate(user_id, 0)[0]

            if state != QValidator.State.Acceptable:
                show_warning(
                    self,
                    "Invalid User ID",
                    "The User ID format is invalid for the selected role."
                )
                return

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
                    department
                )
            else:
                success, message = self.db.edit_user(
                    self.user_id,
                    name,
                    phone,
                    role,
                    department
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
            "Checkout",
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
            "🟠 Active Checkout"
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
            ("Checkout:", checkout),
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

        configure_dialog(
            self,
            "Library System Security",
            390,
            250
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

        self.btn_login.setDefault(True)
        layout.addWidget(self.btn_login)

        self.input_admin_password.setFocus()

    def verify_password(self):
        try:
            password = self.db.get_setting(
                "admin_password",
                "admin123"
            )

            entered = self.input_admin_password.text()

            if entered == str(password):
                self.accept()
            else:
                show_error(
                    self,
                    "Access Denied",
                    "Incorrect administrator password."
                )

                self.input_admin_password.clear()
                self.input_admin_password.setFocus()

        except Exception as error:
            show_error(self, "Authentication Error", error)


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
            "Checkout",
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
            "🟠 Active Checkout"
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
            ("Checkout:", checkout),
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
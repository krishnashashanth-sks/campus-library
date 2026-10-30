from PyQt6.QtWidgets import (
    QDialog, QPushButton, QLineEdit, QMessageBox, QVBoxLayout, QComboBox, QLabel, QSpinBox,
    QFileDialog, QHBoxLayout, QCheckBox, QFrame, QScrollArea, QTableWidget, QWidget, QSizePolicy,
    QHeaderView, QFormLayout, QTableWidgetItem
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer,QRegularExpression
from PyQt6.QtGui import QPixmap, QImage, QFont,QRegularExpressionValidator, QIntValidator, QValidator
import cv2
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageQt

from PyQt6.QtCore import pyqtSignal, QRegularExpression
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, 
    QComboBox, QMessageBox
)
from utils import clear_layout

class BookDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, book_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.book_id = book_id
        self.setWindowTitle("New Book" if book_id is None else "Edit Book")
        self.setFixedSize(400, 350)
        layout = QVBoxLayout(self)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("Book ID")
        self.input_id.setValidator(QIntValidator(1, 99999, self.input_id))

        if book_id is not None:
            self.input_id.setText(str(book_id))
            self.input_id.setReadOnly(True)

        title_regex = QRegularExpression(r"^[A-Za-z0-9][A-Za-z0-9\s.,:;!?()'&+\-/]{0,199}$")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Title")
        self.input_title.setValidator(QRegularExpressionValidator(title_regex, self.input_title))

        author_regex = QRegularExpression(r"^[A-Za-z][A-Za-z .'-]{0,99}$")
        self.input_author = QLineEdit()
        self.input_author.setPlaceholderText("Author")
        self.input_author.setValidator(QRegularExpressionValidator(author_regex, self.input_author))

        publisher_regex = QRegularExpression(r"^[A-Za-z0-9][A-Za-z0-9\s.,&()\-]{0,99}$")
        self.input_publisher = QLineEdit()
        self.input_publisher.setPlaceholderText("Publisher")
        self.input_publisher.setValidator(QRegularExpressionValidator(publisher_regex, self.input_publisher))

        # Total & Available Copies
        self.input_total = QLineEdit()
        self.input_total.setPlaceholderText("Total Copies")
        self.input_total.setValidator(QIntValidator(0, 99999, self.input_total))

        self.input_available = QLineEdit()
        self.input_available.setPlaceholderText("Available Copies")
        self.input_available.setValidator(QIntValidator(0, 99999, self.input_available))

        # Populate data if editing (after widgets are created)
        if book_id is not None:
            book_data = self.get_book_data(book_id)
            self.input_title.setText(book_data.get("title", ""))
            self.input_author.setText(book_data.get("author", ""))
            self.input_publisher.setText(book_data.get("publisher", ""))
            self.input_total.setText(str(book_data.get("total", 1)))
            self.input_available.setText(str(book_data.get("available", 1)))
        else:
            self.input_total.setText("1")
            self.input_available.setText("1")

        self.btn = QPushButton("New Book" if book_id is None else "Update Book")
        self.btn.clicked.connect(self.add_book if book_id is None else self.edit_book)

        layout.addWidget(self.input_id)
        layout.addWidget(self.input_title)
        layout.addWidget(self.input_author)
        layout.addWidget(self.input_publisher)
        layout.addWidget(self.input_total)
        layout.addWidget(self.input_available)
        layout.addWidget(self.btn)

    def add_book(self):
        book_id = self.input_id.text().strip()
        title = self.input_title.text().strip()
        author = self.input_author.text().strip()
        publisher = self.input_publisher.text().strip()
        
        try:
            total = int(self.input_total.text().strip() or 1)
            available = int(self.input_available.text().strip() or 1)
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Copies count must be numeric.")
            return

        if not book_id or not title or not author or not publisher:
            QMessageBox.warning(self, "Validation Error", "All fields are required")
            return

        success, message = self.db.insert_book(book_id, title, author, publisher, total, available)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Error", message)

    def edit_book(self):
        title = self.input_title.text().strip()
        author = self.input_author.text().strip()
        publisher = self.input_publisher.text().strip()
        
        try:
            total = int(self.input_total.text().strip())
            available = int(self.input_available.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Copies count must be numeric.")
            return

        if not title or not author or not publisher:
            QMessageBox.warning(self, "Validation Error", "All fields are required.")
            return

        success, message = self.db.edit_book(self.book_id, title, author, publisher, total, available)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Error", message)

    def get_book_data(self, book_id):
        success, row = self.db.get_book_details(book_id)
        if success and row:
            return {
                "title": row[1] or "",
                "author": row[2] or "",
                "publisher": row[3] or "",
                "total": row[4] or 1,
                "available": row[5] or 1
            }
        return {}


class UserDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, user_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.user_id = user_id
        self.setWindowTitle("New User" if user_id is None else "Edit User")
        self.setFixedSize(350, 320)
        layout = QVBoxLayout(self)

        # 1. Role Selection comes first
        self.combo_role = QComboBox()
        self.combo_role.addItems([
            "Select Role", "Student", "Faculty", "Librarian", "Admin"
        ])
        self.combo_role.currentTextChanged.connect(self.set_id_validator)

        # 2. Department Selection
        self.combo_department = QComboBox()
        self.combo_department.addItems([
            "Select Department", "CSE", "ECE", "EEE", "CE", 
            "ME", "AU", "PH", "EV", "ET"
        ])

        # 3. User ID field (depends on Role)
        self.input_id = QLineEdit()
        self.input_id.setEnabled(False)  # Disabled until role is chosen
        self.input_id.setPlaceholderText("Select a role first")

        # 4. Name and Phone
        name_regex = QRegularExpression(r"^[A-Za-z][A-Za-z .'-]{0,99}$")
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Full Name")
        self.input_name.setValidator(QRegularExpressionValidator(name_regex, self.input_name))

        self.input_phoneno = QLineEdit()
        self.input_phoneno.setPlaceholderText("Phone Number")
        phone_regex = QRegularExpression(r"^\+?[1-9]\d{9}$")
        self.input_phoneno.setValidator(QRegularExpressionValidator(phone_regex, self.input_phoneno))

       # Populate user data if editing
        if user_id is not None:
            user_data = self.get_user_data(user_id)
            
            # 1. Populate and lock ID first so the field is ready
            self.input_id.setText(str(user_id))
            self.input_id.setReadOnly(True)
            self.input_id.setEnabled(True)
            
            # 2. Populate name and phone
            self.input_name.setText(user_data.get("full_name", ""))
            self.input_phoneno.setText(user_data.get("phone_number", ""))
            
            # 3. Set dropdowns last (this triggers signals safely after fields exist)
            role = user_data.get("role", "")
            if self.combo_role.findText(role) >= 0:
                self.combo_role.setCurrentText(role)
                
            dept = user_data.get("department", "")
            if self.combo_department.findText(dept) >= 0:
                self.combo_department.setCurrentText(dept)

        self.btn = QPushButton("Add User" if user_id is None else "Update User")
        self.btn.clicked.connect(self.add_student if user_id is None else self.edit_user)

        # Add to layout in the correct logical sequence
        layout.addWidget(self.combo_role)
        layout.addWidget(self.combo_department)
        layout.addWidget(self.input_id)
        layout.addWidget(self.input_name)
        layout.addWidget(self.input_phoneno)
        layout.addWidget(self.btn)

    def set_id_validator(self, role):
        if role == "Student":
            regex = QRegularExpression(r"^[0-9]{5}-[A-Za-z]{2}-[0-9]{3}$")
            self.input_id.setEnabled(True)
            if not self.input_id.isReadOnly():
                self.input_id.setPlaceholderText("e.g., 12345-CSE-123")
        elif role in ["Faculty", "Admin", "Librarian"]:
            regex = QRegularExpression(r"^[0-9]{5}$")
            self.input_id.setEnabled(True)
            if not self.input_id.isReadOnly():
                self.input_id.setPlaceholderText("e.g., 12345")
        else:
            regex = QRegularExpression(r"")
            if not self.input_id.isReadOnly():
                self.input_id.clear()
                self.input_id.setEnabled(False)
                self.input_id.setPlaceholderText("Select a role first")
                
        self.input_id.setValidator(QRegularExpressionValidator(regex, self.input_id))

    def add_student(self):
        user_id = self.input_id.text().strip()
        name = self.input_name.text().strip()
        phone_number = self.input_phoneno.text().strip()
        department = self.combo_department.currentText()
        role = self.combo_role.currentText()

        # Basic presence check
        if not user_id or not name or department == "Select Department" or role == "Select Role":
            QMessageBox.warning(self, "Validation Error", "All fields are required!")
            return

        # Ensure user ID fully satisfies the regex criteria before submitting
        validator = self.input_id.validator()
        if validator:
            state, _, _ = validator.validate(user_id, 0)
            if state != QValidator.State.Acceptable:
                QMessageBox.warning(
                    self, 
                    "Validation Error", 
                    "The User ID format is incomplete or invalid for the selected role."
                )
                return

        success, message = self.db.insert_user(user_id, name, phone_number, role, department)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Warning", message)

    def get_user_data(self, user_id):
        success, row = self.db.get_user_details(user_id)
        if success and row:
            return {
                "full_name": row[1] or "",
                "phone_number": row[2] or "",
                "role": row[3] or "",
                "department": row[4] or ""
            }
        return {}

    def edit_user(self):
        name = self.input_name.text().strip()
        phone_number = self.input_phoneno.text().strip()
        role = self.combo_role.currentText()
        dept = self.combo_department.currentText()

        if not name or dept == "Select Department" or role == "Select Role":
            QMessageBox.warning(self, "Validation Error", "Full name, Role, and Department are required.")
            return

        success, message = self.db.edit_user(self.user_id, name, phone_number, role, dept)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Error", message)
class ViewBooksDialog(QDialog):
    def __init__(self, db, user_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.user_id = user_id
        self.books_data = []
        
        self.setWindowTitle(f"User Assigned Books & History — ID: {user_id}")
        self.resize(950, 550)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header Title
        lbl_header = QLabel(f"Circulation History for User: <b>{user_id}</b>")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        main_layout.addWidget(lbl_header)

        # Main Layout: Table (Left) + Inspector Panel (Right)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # --- Table View ---
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["Book ID", "Title", "Author", "Status", "Checkout", "Due Date", "Fine"])
        
        # Professional Table Styling matching CatalogView
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #f1f5f9;
                color: #1e293b;
                selection-background-color: #eff6ff;
                selection-color: #1d4ed8;
                outline: none;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
                outline: none;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: bold;
                font-size: 12px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 10px 8px;
            }
            QHeaderView::section:first { border-top-left-radius: 12px; }
            QHeaderView::section:last { border-top-right-radius: 12px; }
        """)

        self.table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        content_layout.addWidget(self.table, stretch=3)

        # --- Right-Side Inspector Panel ---
        self.detail_container = QFrame()
        self.detail_container.setFixedWidth(280)
        self.detail_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(16, 16, 16, 16)
        self.detail_layout.setSpacing(12)
        
        self.show_default_inspector()
        content_layout.addWidget(self.detail_container, stretch=0)

        main_layout.addLayout(content_layout)
        self.setStyleSheet("background-color: #f8fafc;")

        self.load_user_books()

    def show_default_inspector(self):
        clear_layout(self.detail_layout)
        lbl_header = QLabel("Record Inspector")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self.detail_layout.addWidget(lbl_header)
        
        hint = QLabel("Select any book row from the table to view complete loan details, return dates, and fine calculations.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 20px;")
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_user_books(self):
        books = self.db.get_user_books_status(self.user_id)
        if not books:
            self.table.setRowCount(0)
            self.books_data = []
            self.show_default_inspector()
            return

        self.table.setRowCount(len(books))
        self.books_data = books  # Cache for detail views

        for row_idx, book in enumerate(books):
            book_id, title, author, publisher, status, checkout_date, due_date, return_date, fine = book
            
            # Map columns: Book ID, Title, Author, Status, Checkout, Due, Fine
            row_values = [
                str(book_id),
                str(title),
                str(author),
                str(status),
                str(checkout_date) if checkout_date else "N/A",
                str(due_date) if due_date else "N/A",
                f"₹{float(fine):.2f}" if fine else "₹0.00"
            ]

            for col_idx, val in enumerate(row_values):
                item = QTableWidgetItem(val)
                # Highlight active status column text
                if col_idx == 3:
                    item.setForeground(Qt.GlobalColor.darkGreen if val == 'ISSUED' else Qt.GlobalColor.darkGray)
                self.table.setItem(row_idx, col_idx, item)

    def on_selection_changed(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.show_default_inspector()
            return
            
        row = selected[0].row()
        if row < len(self.books_data):
            self.display_record_details(self.books_data[row])

    def display_record_details(self, book):
        book_id, title, author, publisher, status, checkout_date, due_date, return_date, fine = book
        
        clear_layout(self.detail_layout)
        
        lbl_header = QLabel("Loan Control Center")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        
        is_issued = str(status) == 'ISSUED'
        status_banner = QLabel("🔴 Active Checkout" if is_issued else "🟢 Returned Record")
        banner_style = (
            "background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca;" 
            if is_issued else 
            "background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"
        )
        status_banner.setStyleSheet(f"{banner_style} border-radius: 6px; padding: 8px; font-size: 12px; font-weight: 600;")
        status_banner.setWordWrap(True)

        self.detail_layout.addWidget(lbl_header)
        self.detail_layout.addWidget(status_banner)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        form_layout.addRow(QLabel("<b>Book ID:</b>"), QLabel(str(book_id)))
        form_layout.addRow(QLabel("<b>Title:</b>"), QLabel(str(title)))
        form_layout.addRow(QLabel("<b>Author:</b>"), QLabel(str(author)))
        form_layout.addRow(QLabel("<b>Publisher:</b>"), QLabel(str(publisher)))
        form_layout.addRow(QLabel("<b>Checkout:</b>"), QLabel(str(checkout_date or "N/A")))
        form_layout.addRow(QLabel("<b>Due Date:</b>"), QLabel(str(due_date or "N/A")))
        form_layout.addRow(QLabel("<b>Returned:</b>"), QLabel(str(return_date or "Not yet returned")))
        form_layout.addRow(QLabel("<b>Fine:</b>"), QLabel(f"₹{float(fine or 0.0):.2f}"))
        
        for i in range(form_layout.rowCount()):
            lbl_item = form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            val_item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if lbl_item and lbl_item.widget():
                lbl_item.widget().setStyleSheet("color: #64748b; font-size: 11px; border: none; background: transparent;")
            if val_item and val_item.widget():
                val_item.widget().setStyleSheet("color: #334155; font-size: 11px; border: none; background: transparent;")
                val_item.widget().setWordWrap(True)

        self.detail_layout.addLayout(form_layout)

        # Contextual Action: If the book is currently checked out to this user, show direct Return button
        if is_issued:
            self.btn_return = QPushButton("🔄 Return Book")
            self.btn_return.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: 600;
                    border-radius: 6px;
                    padding: 8px 12px;
                    border: none;
                }
                QPushButton:hover { background-color: #0369a1; }
            """)
            self.btn_return.clicked.connect(lambda: self.handle_return_action(book_id))
            self.detail_layout.addWidget(self.btn_return)

        self.detail_layout.addStretch()

    def handle_return_action(self, book_id):
        """Processes the return of the book directly from the user's loan history inspector."""
        confirm = QMessageBox.question(
            self, "Confirm Return",
            f"Process return for Book ID '{book_id}' borrowed by User ID '{self.user_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            success, fine, err_msg = self.db.return_book(book_id, self.user_id)
            if success:
                msg = "Book successfully returned!"
                if fine > 0:
                    msg += f"\nCollected Fine: ₹{fine:.2f}"
                QMessageBox.information(self, "Return Success", msg)
                self.load_user_books()  # Refresh the user books table and status banner
            else:
                QMessageBox.warning(self, "Return Failed", f"Could not process return:\n{err_msg or 'Unknown error'}")

class BarcodeGeneratorDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, book_id="", title="", author="", publisher="", parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Barcode Generator & Export")
        self.setFixedSize(380, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Book ID :"))
        self.input_book_id = QLineEdit(book_id)
        layout.addWidget(self.input_book_id)

        layout.addWidget(QLabel("Book Title:"))
        self.input_book_title = QLineEdit(title)
        layout.addWidget(self.input_book_title)

        layout.addWidget(QLabel("Author:"))
        self.input_book_author = QLineEdit(author)
        layout.addWidget(self.input_book_author)

        layout.addWidget(QLabel("Publisher:"))
        self.input_book_publisher = QLineEdit(publisher)
        layout.addWidget(self.input_book_publisher)

        self.lbl_preview = QLabel("Barcode Preview")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 2px dashed #cbd5e1; border-radius: 6px; background-color: #f8fafc;")
        self.lbl_preview.setFixedHeight(180)
        layout.addWidget(self.lbl_preview)

        self.chk_box_db = QCheckBox("Save Book to the Database")
        
        # If opened from Catalog view for an existing book, hide or uncheck DB save option
        if book_id:
            self.chk_box_db.setChecked(False)
            self.chk_box_db.setVisible(False)
        else:
            self.chk_box_db.setChecked(True)
            
        self.chk_box_db.setStyleSheet("font-weight: bold; margin-top: 5px; margin-bottom: 5px;")
        layout.addWidget(self.chk_box_db)

        self.btn_generate = QPushButton("Generate Barcode")
        self.btn_generate.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 8px 12px; border-radius: 6px;")
        self.btn_generate.clicked.connect(self.generate_barcode)
        layout.addWidget(self.btn_generate)

        self.btn_save = QPushButton("Save PNG")
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; padding: 8px 12px; border-radius: 6px;")
        self.btn_save.clicked.connect(self.save_png)
        layout.addWidget(self.btn_save)

        self.generated_image = None

        # Automatically generate preview if pre-filled from catalog view
        if book_id and title:
            self.generate_barcode()

    def generate_barcode(self):
        book_id = self.input_book_id.text().strip()
        book_title = self.input_book_title.text().strip() or None
        book_author = self.input_book_author.text().strip() or ""
        book_publisher = self.input_book_publisher.text().strip() or ""

        if not book_id or not book_title:
            QMessageBox.warning(self, "Validation Error", "Please enter the Book ID and Title.")
            return

        if self.chk_box_db.isVisible() and self.chk_box_db.isChecked():
            try:
                success, message = self.db.insert_book(book_id, book_title, book_author, book_publisher)
                if success:
                    self.data_updated.emit()
                    QMessageBox.information(self, "Success", message)
                else:
                    QMessageBox.warning(self, "Failed", message)
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to save book to database: {e}")
                return

        try:
            Code128 = barcode.get_barcode_class('code128')
            
            writer_options = {
                'module_width': 0.4,       
                'module_height': 15.0,     
                'quiet_zone': 6.0,         
                'font_size': 12,           
                'text_distance': 6.0,      
                'write_text': True
            }
            
            code128 = Code128(book_id, writer=ImageWriter())
            
            buffer = io.BytesIO()
            code128.write(buffer, options=writer_options)
            
            pil_img = Image.open(buffer).convert("RGB")
            self.generated_image = pil_img

            q_img = ImageQt.ImageQt(pil_img)
            pixmap = QPixmap.fromImage(q_img)
            
            scaled_pixmap = pixmap.scaled(
                self.lbl_preview.width() - 20, 
                self.lbl_preview.height() - 20, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.lbl_preview.setPixmap(scaled_pixmap)
            self.btn_save.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Generation Error", f"Could not generate barcode: {e}")

    def save_png(self):
        book_id = self.input_book_id.text().strip()
        default_filepath = f"Barcode_{book_id}.png"

        path, _ = QFileDialog.getSaveFileName(self, "Save Barcode as PNG", default_filepath, "PNG Files (*.png)")
        if path and self.generated_image:
            try:
                self.generated_image.save(path)
                QMessageBox.information(self, "Successfully Saved", f"Saved Barcode PNG of {book_id} at {path}")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to save Barcode PNG: {e}")

class QuickScanDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.book_id = None
        self.setWindowTitle("Quick Barcode Scan")
        self.setFixedSize(340, 520)

        layout = QVBoxLayout(self)

        # 1. Camera View Widget
        self.lbl_capture = QLabel("Initializing Camera...")
        self.lbl_capture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_capture.setStyleSheet("background-color: #000; color: #fff; border-radius: 8px;")
        self.lbl_capture.setFixedHeight(200)
        layout.addWidget(self.lbl_capture)

        # 2. Input line for Physical USB Handheld Scanner or Manual typing
        layout.addWidget(QLabel("<b>Book ID (Physical Scanner or Manual):</b>"))
        self.input_book_id = QLineEdit()
        self.input_book_id.setPlaceholderText("Scan with hardware scanner or type here...")
        
        # Physical USB scanners trigger returnPressed on completion
        self.input_book_id.returnPressed.connect(self.on_physical_scan)
        # Dynamic text change update for manual typing
        self.input_book_id.textChanged.connect(self.on_manual_text_change)
        layout.addWidget(self.input_book_id)

        # 3. Status Display
        self.lbl_status = QLabel("<b>Status:</b> Align Barcode in camera view or type ID")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # 4. User ID Input
        self.input_user_id = QLineEdit()
        self.input_user_id.setPlaceholderText("User ID")
        layout.addWidget(self.input_user_id)

        # 5. Due Days Input
        default_days = self.db.get_setting("default_days", 14)
        try:
            default_days = int(default_days)
        except (ValueError, TypeError):
            default_days = 14

        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 365)
        self.spin_days.setValue(default_days)
        layout.addWidget(self.spin_days)

        # 6. Action Buttons
        btn_layout = QHBoxLayout()

        self.issue_btn = QPushButton("Issue")
        self.issue_btn.setEnabled(False)
        self.issue_btn.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; padding: 6px;")
        self.issue_btn.clicked.connect(lambda: self.process_circulation("issue"))

        self.return_btn = QPushButton("Return")
        self.return_btn.setEnabled(False)
        self.return_btn.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold; padding: 6px;")
        self.return_btn.clicked.connect(lambda: self.process_circulation("return"))

        btn_layout.addWidget(self.issue_btn)
        btn_layout.addWidget(self.return_btn)
        layout.addLayout(btn_layout)

        # Camera setup
        self.cap = cv2.VideoCapture(0,cv2.CAP_DSHOW)
        self.barcode_detector = cv2.barcode.BarcodeDetector()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        # Focus line edit so USB hardware scanners work immediately
        self.input_book_id.setFocus()

    def on_manual_text_change(self, text):
        code = text.strip()
        if code:
            self.book_id = code
            self.lbl_status.setText(f"<b>Book ID (Manual):</b> <font color='#10b981'>{self.book_id}</font>")
            self.issue_btn.setEnabled(True)
            self.return_btn.setEnabled(True)
        else:
            self.book_id = None
            self.lbl_status.setText("<b>Status:</b> Align Barcode in camera view or type ID")
            self.issue_btn.setEnabled(False)
            self.return_btn.setEnabled(False)

    def on_physical_scan(self):
        scanned_text = self.input_book_id.text().strip()
        if scanned_text:
            self.set_camera_scanned_book_id(scanned_text, source="Physical Scanner")

    def update_frame(self):
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        try:
            result = self.barcode_detector.detectAndDecode(frame)
            if result and len(result) >= 2:
                ok = result[0]
                decoded_info = result[1]

                if ok and decoded_info:
                    scanned_code = decoded_info[0] if isinstance(decoded_info, (list, tuple)) else decoded_info
                    if scanned_code:
                        self.set_camera_scanned_book_id(str(scanned_code).strip(), source="Camera")
        except Exception:
            pass

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        q_img = QImage(rgb_frame.data, w, h, w * ch, QImage.Format.Format_RGB888)
        self.lbl_capture.setPixmap(QPixmap.fromImage(q_img).scaled(280, 180, Qt.AspectRatioMode.KeepAspectRatio))

    def set_camera_scanned_book_id(self, code, source=""):
        if code:
            self.book_id = code

            # Block signals to prevent textChanged loop recursion
            self.input_book_id.blockSignals(True)
            self.input_book_id.setText(code)
            self.input_book_id.blockSignals(False)

            self.lbl_status.setText(f"<b>Book ID ({source}):</b> <font color='#10b981'>{self.book_id}</font>")
            self.issue_btn.setEnabled(True)
            self.return_btn.setEnabled(True)

            # Freeze camera scan on successful detection
            if self.timer.isActive():
                self.timer.stop()

    def process_circulation(self, action):
        user_id = self.input_user_id.text().strip()
        default_days = self.spin_days.value()

        if not self.book_id or not user_id:
            QMessageBox.warning(self, "Validation Error", "Both Book ID and User ID are required.")
            return

        fine = 0.0

        if action == "issue":
            success, message = self.db.issue_book(self.book_id, user_id, days_allowed=default_days)
        else:
            success, fine, message = self.db.return_book(self.book_id, user_id)

        if success:
            if action == "return" and fine > 0:
                QMessageBox.warning(
                    self, 
                    "Overdue Fine", 
                    f"{message}\n\nOverdue Fine Charged: ${fine:.2f}"
                )
            else:
                QMessageBox.information(self, "Success", message)

            if self.timer.isActive():
                self.timer.stop()
            if self.cap.isOpened():
                self.cap.release()
            self.accept()
        else:
            QMessageBox.critical(self, "Error", message)
            # Reset state on failure so user can try another book immediately
            self.reset_for_retry()

    def reset_for_retry(self):
        self.book_id = None
        self.input_book_id.clear()
        self.lbl_status.setText("<b>Status:</b> Scan using handheld device or align with camera")
        self.issue_btn.setEnabled(False)
        self.return_btn.setEnabled(False)
        if not self.timer.isActive():
            self.timer.start(30)

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap.isOpened():
            self.cap.release()
        event.accept()

class LoginDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Library System Security")
        self.setFixedSize(320, 200)
        # self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        
        main_layout = QVBoxLayout(self)

        self.input_admin_password = QLineEdit()
        self.input_admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_admin_password.setPlaceholderText("Admin Password")
        main_layout.addWidget(self.input_admin_password)

        btn_login = QPushButton("Verify Password")
        btn_login.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        btn_login.clicked.connect(self.verify_password)
        btn_login.setAutoDefault(True)
        btn_login.setDefault(True)
        main_layout.addWidget(btn_login)

    def verify_password(self):
        password = self.db.get_setting("admin_password")
        if self.input_admin_password.text().strip() == password:
            self.accept()
        else:
            QMessageBox.critical(self, "Password Incorrect", "Password is incorrect. Try again.")
            self.input_admin_password.clear()

class CustomSplashScreen(QDialog):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(400, 400)  
        self.setStyleSheet("background-color: white;")  

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        self.icon_label = QLabel()
        pixmap = QPixmap(image_path)
        scaled_pixmap = pixmap.scaled(
            180, 180, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.icon_label.setPixmap(scaled_pixmap)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("Library Management System")
        self.text_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setStyleSheet("color: black;")
        layout.addWidget(self.text_label)
class BookHistoryDialog(QDialog):
    def __init__(self, db, book_id, book_title, parent=None):
        super().__init__(parent)
        self.db = db
        self.book_id = book_id
        self.history_data = []

        self.setWindowTitle(f"Audit History — {book_title} (ID: {book_id})")
        self.resize(950, 550)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header Title
        lbl_header = QLabel(f"Circulation Log for: <b>{book_title}</b>")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        main_layout.addWidget(lbl_header)

        # Main Layout: Table (Left) + Inspector Panel (Right)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # --- Table View ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["Borrower ID", "Status", "Checkout Date", "Due Date", "Return Date", "Fine"])
        
        # Professional Table Styling matching CatalogView
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #f1f5f9;
                color: #1e293b;
                selection-background-color: #eff6ff;
                selection-color: #1d4ed8;
                outline: none;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
                outline: none;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: bold;
                font-size: 12px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 10px 8px;
            }
            QHeaderView::section:first { border-top-left-radius: 12px; }
            QHeaderView::section:last { border-top-right-radius: 12px; }
        """)

        self.table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        content_layout.addWidget(self.table, stretch=3)

        # --- Right-Side Inspector Panel ---
        self.detail_container = QFrame()
        self.detail_container.setFixedWidth(280)
        self.detail_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(16, 16, 16, 16)
        self.detail_layout.setSpacing(12)
        
        self.show_default_inspector()
        content_layout.addWidget(self.detail_container, stretch=0)

        main_layout.addLayout(content_layout)
        self.setStyleSheet("background-color: #f8fafc;")

        self.load_history()

    def show_default_inspector(self):
        clear_layout(self.detail_layout)
        lbl_header = QLabel("Record Inspector")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self.detail_layout.addWidget(lbl_header)
        
        hint = QLabel("Select any log row from the table to view complete audit details, borrower info, and fine calculations.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 20px;")
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_history(self):
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT user_id, checkout_date, due_date, return_date, fine_amount, status
                FROM circulation_logs
                WHERE book_id = ?
                ORDER BY id DESC
            """, (self.book_id,))
            rows = cursor.fetchall()

            if not rows:
                self.table.setRowCount(0)
                self.history_data = []
                self.show_default_inspector()
                return

            self.table.setRowCount(len(rows))
            self.history_data = rows

            for row_idx, row_data in enumerate(rows):
                user_id, checkout, due, return_dt, fine, status = row_data
                
                row_values = [
                    str(user_id),
                    str(status),
                    str(checkout) if checkout else "N/A",
                    str(due) if due else "N/A",
                    str(return_dt) if return_dt else "N/A",
                    f"₹{float(fine or 0.0):.2f}"
                ]

                for col_idx, val in enumerate(row_values):
                    item = QTableWidgetItem(val)
                    if col_idx == 1:
                        item.setForeground(Qt.GlobalColor.darkGreen if val == 'ISSUED' else Qt.GlobalColor.darkGray)
                    self.table.setItem(row_idx, col_idx, item)

        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load book history: {e}")

    def on_selection_changed(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self.show_default_inspector()
            return
            
        row = selected[0].row()
        if row < len(self.history_data):
            self.display_record_details(self.history_data[row])

    def display_record_details(self, record):
        user_id, checkout, due, return_dt, fine, status = record
        
        clear_layout(self.detail_layout)
        
        lbl_header = QLabel("Audit Control Center")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        
        is_issued = str(status) == 'ISSUED'
        status_banner = QLabel("🔴 Active Checkout" if is_issued else "🟢 Completed Loan")
        banner_style = (
            "background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca;" 
            if is_issued else 
            "background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0;"
        )
        status_banner.setStyleSheet(f"{banner_style} border-radius: 6px; padding: 8px; font-size: 12px; font-weight: 600;")
        status_banner.setWordWrap(True)

        self.detail_layout.addWidget(lbl_header)
        self.detail_layout.addWidget(status_banner)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        form_layout.addRow(QLabel("<b>Borrower ID:</b>"), QLabel(str(user_id)))
        form_layout.addRow(QLabel("<b>Status:</b>"), QLabel(str(status)))
        form_layout.addRow(QLabel("<b>Checkout:</b>"), QLabel(str(checkout or "N/A")))
        form_layout.addRow(QLabel("<b>Due Date:</b>"), QLabel(str(due or "N/A")))
        form_layout.addRow(QLabel("<b>Returned:</b>"), QLabel(str(return_dt or "Not yet returned")))
        form_layout.addRow(QLabel("<b>Fine:</b>"), QLabel(f"₹{float(fine or 0.0):.2f}"))
        
        for i in range(form_layout.rowCount()):
            lbl_item = form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            val_item = form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)
            if lbl_item and lbl_item.widget():
                lbl_item.widget().setStyleSheet("color: #64748b; font-size: 11px; border: none; background: transparent;")
            if val_item and val_item.widget():
                val_item.widget().setStyleSheet("color: #334155; font-size: 11px; border: none; background: transparent;")
                val_item.widget().setWordWrap(True)

        self.detail_layout.addLayout(form_layout)

        # Contextual Action: If the book is currently checked out, show direct Return button
        if is_issued:
            self.btn_return = QPushButton("🔄 Return Book")
            self.btn_return.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: 600;
                    border-radius: 6px;
                    padding: 8px 12px;
                    border: none;
                }
                QPushButton:hover { background-color: #0369a1; }
            """)
            self.btn_return.clicked.connect(lambda: self.handle_return_action(user_id))
            self.detail_layout.addWidget(self.btn_return)

        self.detail_layout.addStretch()

    def handle_return_action(self, user_id):
        """Processes the return of the book directly from the audit history inspector."""
        confirm = QMessageBox.question(
            self, "Confirm Return",
            f"Process return for this book borrowed by User ID '{user_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            success, fine, err_msg = self.db.return_book(self.book_id, user_id)
            if success:
                msg = "Book successfully returned!"
                if fine > 0:
                    msg += f"\nCollected Fine: ₹{fine:.2f}"
                QMessageBox.information(self, "Return Success", msg)
                self.load_history()  # Refresh the history table and status banner
            else:
                QMessageBox.warning(self, "Return Failed", f"Could not process return:\n{err_msg or 'Unknown error'}")
from PyQt6.QtWidgets import (
    QDialog, QPushButton, QLineEdit, QMessageBox, QVBoxLayout, QComboBox, QLabel, QSpinBox,
    QFileDialog, QHBoxLayout, QCheckBox, QFrame, QScrollArea, QGridLayout, QWidget
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer,QRegularExpression
from PyQt6.QtGui import QPixmap, QImage, QFont,QRegularExpressionValidator
import cv2
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageQt

class NewBookDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("New Book")
        self.setFixedSize(400, 300)
        layout = QVBoxLayout(self)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("Book ID")

        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Title")

        self.input_author = QLineEdit()
        self.input_author.setPlaceholderText("Author")

        self.input_publisher = QLineEdit()
        self.input_publisher.setPlaceholderText("Publisher")

        self.add_btn = QPushButton("New Book")
        self.add_btn.clicked.connect(self.add_book)

        layout.addWidget(self.input_id)
        layout.addWidget(self.input_title)
        layout.addWidget(self.input_author)
        layout.addWidget(self.input_publisher)
        layout.addWidget(self.add_btn)

    def add_book(self):
        book_id = self.input_id.text().strip()
        title = self.input_title.text().strip()
        author = self.input_author.text().strip()
        publisher = self.input_publisher.text().strip()

        if not book_id or not title or not author or not publisher:
            QMessageBox.warning(self, "Validation Error", "All fields are required")
            return

        success, message = self.db.insert_book(book_id, title, author, publisher)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Error", message)


class NewUserDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("New User")
        self.setFixedSize(350, 300)
        layout = QVBoxLayout(self)

        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("User ID:")

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Full Name")

        self.input_phoneno = QLineEdit()
        self.input_phoneno.setPlaceholderText("Phone Number")

        phone_regex=QRegularExpression(r"^\+?[1-9]\d{6,14}$")
        validator=QRegularExpressionValidator(phone_regex,self)
        self.input_phoneno.setValidator(validator)

        self.combo_department = QComboBox()
        self.combo_department.addItems([
            "Select Department", "CSE", "ECE", "EEE", "CE", 
            "ME", "AU", "PH", "EV", "ET"
        ])

        self.combo_role = QComboBox()
        self.combo_role.addItems([
            "Select Role", "Student", "Faculty", "Librarian", "Admin"
        ])

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_student)

        layout.addWidget(self.input_id)
        layout.addWidget(self.input_name)
        layout.addWidget(self.input_phoneno)
        layout.addWidget(self.combo_department)
        layout.addWidget(self.combo_role)
        layout.addWidget(self.add_btn)

    def add_student(self):
        user_id = self.input_id.text().strip()
        name = self.input_name.text().strip()
        phone_number = self.input_phoneno.text().strip()
        department = self.combo_department.currentText()
        role = self.combo_role.currentText()

        if not user_id or not name or department == "Select Department" or role == "Select Role":
            QMessageBox.warning(self, "Validation Error", "All fields are required!")
            return

        success, message = self.db.insert_user(user_id, name, phone_number, role, department)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Warning", message)


class EditUserDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, user_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.user_id = user_id
        self.setWindowTitle("Edit User")
        self.setFixedSize(350, 300)

        user_data = self.get_user_data(user_id)
        layout = QVBoxLayout(self)

        self.input_name = QLineEdit(user_data.get("full_name", ""))
        self.input_name.setPlaceholderText("Full Name")

        self.input_phoneno = QLineEdit(user_data.get("phone_number", ""))
        self.input_phoneno.setPlaceholderText("Phone Number")

        self.combo_department = QComboBox()
        self.combo_department.addItems([
            "Select Department", "CSE", "ECE", "EEE", "CE", 
            "ME", "AU", "PH", "EV", "ET"
        ])
        current_dept = user_data.get("department", "")
        dept_index = self.combo_department.findText(current_dept)
        if dept_index >= 0:
            self.combo_department.setCurrentIndex(dept_index)

        self.combo_role = QComboBox()
        self.combo_role.addItems([
            "Student", "Faculty", "Librarian", "Admin"
        ])
        current_role = user_data.get("role", "")
        role_index = self.combo_role.findText(current_role)
        if role_index >= 0:
            self.combo_role.setCurrentIndex(role_index)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_user)

        layout.addWidget(self.input_name)
        layout.addWidget(self.input_phoneno)
        layout.addWidget(self.combo_department)
        layout.addWidget(self.combo_role)
        layout.addWidget(self.edit_btn)

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

        if not name or dept == "Select Department":
            QMessageBox.warning(self, "Validation Error", "Full name and Department are required.")
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
        
        self.setWindowTitle("User Borrowed Books")
        self.resize(850, 600)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        lbl_header = QLabel("Book History & Status")
        lbl_header.setStyleSheet("font-size: 20px; font-weight: bold; color: #0f172a; margin-bottom: 10px;")
        main_layout.addWidget(lbl_header)

        books = self.db.get_user_books_status(user_id)

        if not books:
            lbl_empty = QLabel("No book history found for this user.")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_empty.setStyleSheet("color: #64748b; font-size: 14px; margin-top: 50px;")
            main_layout.addWidget(lbl_empty)
            return

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container_widget = QWidget()
        grid_layout = QGridLayout(container_widget)
        grid_layout.setSpacing(15)

        cols = 2
        for idx, book in enumerate(books):
            row = idx // cols
            col = idx % cols
            card = self.create_book_tile(book)
            grid_layout.addWidget(card, row, col)

        grid_layout.setRowStretch(grid_layout.rowCount(), 1)

        scroll_area.setWidget(container_widget)
        main_layout.addWidget(scroll_area)

    def create_book_tile(self, book):
        book_id, title, author, publisher, status, checkout_date, due_date,return_date,fine = book
        
        is_checkout = str(status) == 'ISSUED'
        status_text = "ISSUED" if is_checkout else "RETURNED"
        badge_bg = "#dcfce7" if is_checkout else "#e0f2fe"
        badge_color = "#15803d" if is_checkout else "#0369a1"

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 10px;
                border: 1px solid #e2e8f0;
            }
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(6)

        top_bar = QHBoxLayout()
        lbl_id = QLabel(f"ID: {book_id}")
        lbl_id.setStyleSheet("color: #64748b; font-size: 11px; font-weight: bold; border: none;")
        
        lbl_badge = QLabel(status_text)
        lbl_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_color};
            font-size: 11px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
            border: none;
        """)
        
        top_bar.addWidget(lbl_id)
        top_bar.addStretch()
        top_bar.addWidget(lbl_badge)
        card_layout.addLayout(top_bar)

        lbl_title = QLabel(str(title))
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("color: #0f172a; font-size: 16px; font-weight: bold; border: none; margin-top: 4px;")
        card_layout.addWidget(lbl_title)

        lbl_meta = QLabel(f"By {author}  •  {publisher}")
        lbl_meta.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
        card_layout.addWidget(lbl_meta)

        checkout_str = str(checkout_date) if checkout_date else "N/A"
        lbl_checkout= QLabel(f"Issued Date: {checkout_str}")
        lbl_checkout.setStyleSheet("color: black; font-size: 11px; border: none; margin-top: 6px;")
        card_layout.addWidget(lbl_checkout)
        
        due_str = str(due_date) if due_date else "N/A"
        lbl_due_date = QLabel(f"Due Date: {due_str}")
        lbl_due_date.setStyleSheet("color: black; font-size: 11px; border: none;")
        card_layout.addWidget(lbl_due_date)

        return_str = str(return_date) if return_date else "N/A"
        lbl_return_date = QLabel(f"Return Date: {return_str}")
        lbl_return_date.setStyleSheet("color: black; font-size: 11px; border: none;")
        card_layout.addWidget(lbl_return_date)

        fine_str = str(fine) if return_date else "0.0"
        lbl_fine_date = QLabel(f"Fine: {fine_str}")
        lbl_fine_date.setStyleSheet("color: black; font-size: 11px; border: none;")
        card_layout.addWidget(lbl_fine_date)

        return card


class EditBookDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, book_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.book_id = book_id
        self.setWindowTitle("Edit Book")
        self.setFixedSize(350, 300)

        book_data = self.get_book_data(book_id)

        layout = QVBoxLayout(self)

        self.input_title = QLineEdit(book_data.get("title", ""))
        self.input_title.setPlaceholderText("Title")

        self.input_author = QLineEdit(book_data.get("author", ""))
        self.input_author.setPlaceholderText("Author")

        self.input_publisher = QLineEdit(book_data.get("publisher", ""))
        self.input_publisher.setPlaceholderText("Publisher")

        self.input_total = QLineEdit(str(book_data.get("total", "")))
        self.input_total.setPlaceholderText("Total Copies")

        self.input_available = QLineEdit(str(book_data.get("available", "")))
        self.input_available.setPlaceholderText("Available Copies")

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_book)

        layout.addWidget(self.input_title)
        layout.addWidget(self.input_author)
        layout.addWidget(self.input_publisher)
        layout.addWidget(self.input_total)
        layout.addWidget(self.input_available)
        layout.addWidget(self.edit_btn)

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

        if not title:
            QMessageBox.warning(self, "Validation Error", "Title cannot be empty.")
            return

        success, message = self.db.edit_book(self.book_id, title, author, publisher, total, available)
        if success:
            self.data_updated.emit()
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Error", message)


class BarcodeGeneratorDialog(QDialog):
    data_updated = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Barcode Generator")
        self.setFixedSize(380, 580)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Book ID :"))
        self.input_book_id = QLineEdit()
        layout.addWidget(self.input_book_id)

        layout.addWidget(QLabel("Book Title:"))
        self.input_book_title = QLineEdit()
        layout.addWidget(self.input_book_title)

        layout.addWidget(QLabel("Author:"))
        self.input_book_author = QLineEdit()
        layout.addWidget(self.input_book_author)

        layout.addWidget(QLabel("Publisher:"))
        self.input_book_publisher = QLineEdit()
        layout.addWidget(self.input_book_publisher)

        self.lbl_preview = QLabel("Barcode Preview")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 2px dashed #cbd5e1; border-radius: 6px;")
        self.lbl_preview.setFixedHeight(200)
        layout.addWidget(self.lbl_preview)

        self.chk_box_db = QCheckBox("Save Book to the Database")
        self.chk_box_db.setChecked(True)
        self.chk_box_db.setStyleSheet("font-weight: bold; margin-top: 5px; margin-bottom: 5px;")
        layout.addWidget(self.chk_box_db)

        self.btn_generate = QPushButton("Generate Barcode")
        self.btn_generate.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_generate.clicked.connect(self.generate_barcode)
        layout.addWidget(self.btn_generate)

        self.btn_save = QPushButton("Save PNG")
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_save.clicked.connect(self.save_png)
        layout.addWidget(self.btn_save)

        self.generated_image = None

    def generate_barcode(self):
        book_id = self.input_book_id.text().strip()
        book_title = self.input_book_title.text().strip() or None
        book_author = self.input_book_author.text().strip() or ""
        book_publisher = self.input_book_publisher.text().strip() or ""

        if not book_id or not book_title:
            QMessageBox.warning(self, "Validation Error", "Please enter the Book ID and Title.")
            return

        if self.chk_box_db.isChecked():
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
            
            # Configure writer options to ensure correct horizontal aspect ratio for scanners
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
            # Pass writer options into write()
            code128.write(buffer, options=writer_options)
            
            pil_img = Image.open(buffer).convert("RGB")
            self.generated_image = pil_img

            # Convert to QPixmap and apply smooth scaling
            q_img = ImageQt.ImageQt(pil_img)
            pixmap = QPixmap.fromImage(q_img)
            
            # Fit inside preview box while preserving correct aspect ratio
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
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        
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

        self.text_label = QLabel("LibCore")
        self.text_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setStyleSheet("color: black;")
        layout.addWidget(self.text_label)
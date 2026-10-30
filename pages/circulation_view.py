from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QInputDialog,
    QMessageBox, QFrame, QHBoxLayout, QPushButton, QLineEdit,QSizePolicy,QHeaderView
)
from PyQt6.QtCore import Qt

class CirculationView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db

        main_layout = QVBoxLayout(self)

        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px;")
        form_layout = QHBoxLayout(form_frame)

        self.input_book_id = QLineEdit()
        self.input_book_id.setPlaceholderText("Enter the book ID...")
        self.input_book_id.setStyleSheet("background-color:black;color:white;")

        self.input_user_id = QLineEdit()
        self.input_user_id.setPlaceholderText("Enter the user ID...")
        self.input_user_id.setStyleSheet("background-color:black;color:white;")

        btn_issue = QPushButton("Issue Book")
        btn_issue.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_issue.clicked.connect(lambda:self.issue_book())

        btn_return = QPushButton("Return Book")
        btn_return.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        btn_return.clicked.connect(self.return_book)

        lbl_book = QLabel("<b>Book ID:</b>")
        lbl_book.setStyleSheet("background-color: white; color: black;")

        lbl_user=QLabel("<b>User ID:</b>")
        lbl_user.setStyleSheet("background-color:white;color:black")

        form_layout.addWidget(lbl_book)
        form_layout.addWidget(self.input_book_id)
        form_layout.addWidget(lbl_user)
        form_layout.addWidget(self.input_user_id)
        form_layout.addWidget(btn_issue)
        form_layout.addWidget(btn_return)
        
        main_layout.addWidget(form_frame)

        lbl_title = QLabel("<b>Circulation Logs</b>")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(lbl_title)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Log ID", 
            "Book ID", 
            "User ID", 
            "Status", 
            "Checkout Date", 
            "Due Date", 
            "Return Date", 
            "Fine"
        ])
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table)
        
        self.load_circulation()

    def load_circulation(self):
        success, rows = self.db.get_logs()
        if not success:
            return

        self.table.setRowCount(len(rows))
        
        for row_idx, row in enumerate(rows):
            log_id, book_id, user_id, checkout_date, due_date, return_date, fine, status = row

            # Format fine amount safely
            fine_str = f"₹{float(fine):.2f}" if fine is not None else "₹0.00"

            # Set items into table columns
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(log_id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(book_id)))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(user_id)))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(status)))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(checkout_date or "")))
            self.table.setItem(row_idx, 5, QTableWidgetItem(str(due_date or "")))
            self.table.setItem(row_idx, 6, QTableWidgetItem(str(return_date or "N/A")))
            self.table.setItem(row_idx, 7, QTableWidgetItem(fine_str))

    def handle_issue_book(self, book_id, book_title):
        """Quick action to issue the selected book with a custom loan duration."""
        # 1. Prompt for User ID
        user_id, ok = QInputDialog.getText(
            self, 
            "Issue Book", 
            f"Enter User ID to issue '{book_title}':"
        )
        if not ok or not user_id.strip():
            return

        # 2. Prompt for Allowed Days (using your precise configuration)
        default_days = 14  # Standard default loan period (e.g., 2 weeks)
        days_allowed, ok_days = QInputDialog.getInt(
            self,
            "Issue Duration",
            "Enter the number of days allowed?",
            int(default_days),
            1,
            365,
            1
        )
        if not ok_days:
            return

        # 3. Call backend database method (passing days_allowed)
        # Note: Ensure your db.issue_book method accepts `days_allowed` as an argument.
        success, msg = self.db.issue_book(book_id, user_id.strip(), days_allowed)
        
        if success:
            QMessageBox.information(
                self, 
                "Success", 
                f"Book successfully issued for {days_allowed} days!"
            )
            self.load_books_to_table()
            self.show_default_inspector()
        else:
            QMessageBox.warning(self, "Action Failed", msg)

    def return_book(self):
        book_id = self.input_book_id.text().strip()
        user_id = self.input_user_id.text().strip()

        if not book_id or not user_id:
            QMessageBox.warning(self, "Validation Error", "All fields are required.")
            return
        success, fine, message = self.db.return_book(book_id, user_id)

        if success:
            if fine > 0:
                QMessageBox.warning(
                    self, 
                    "Overdue Fine", 
                    f"{message}\n\nOverdue Fine Charged: Rs. {fine:.2f}"
                )
            else:
                QMessageBox.information(self, "Success", f"{message}\nNo fine charged.")

            # Clear input fields and refresh UI table
            self.input_book_id.clear()
            self.input_user_id.clear()
            self.load_circulation()
        else:
            QMessageBox.critical(self, "Database Error", message)       
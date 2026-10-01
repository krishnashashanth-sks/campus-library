from PyQt6.QtWidgets import(
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QSizePolicy, QFrame, QLabel, QMessageBox, QFormLayout
)
from utils import clear_layout
from dialogs import NewUserDialog, EditUserDialog, ViewBooksDialog
from PyQt6.QtCore import Qt

class UserManagementView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search User...")
        self.search_input.textChanged.connect(self.filter_users)

        self.add_btn = QPushButton("Add New User")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b7ade;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #1d64d8; }
        """)
        self.add_btn.clicked.connect(self.open_userform)

        top_layout.addWidget(self.search_input)
        top_layout.addWidget(self.add_btn)
        main_layout.addLayout(top_layout)

        bottom_layout = QHBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["ID", "Full Name", "Phone Number", "Role", "Department", "Created At"])
        self.table.cellClicked.connect(self.display_user_details)
        bottom_layout.addWidget(self.table)

        # --- Updated QSS for User Details Panel (Matching Catalog View) ---
        self.detail_container = QFrame()
        self.detail_container.setFixedWidth(300)
        self.detail_container.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #f1f5f9;
                font-size: 16px;
                border:none;
            }
        """)
        
        self.detail_layout = QVBoxLayout(self.detail_container)
        bottom_layout.addWidget(self.detail_container, stretch=1)
        main_layout.addLayout(bottom_layout)
        self.load_users_to_table()

    def load_users_to_table(self):
        success,rows=self.db.get_users()
        if not success:
            QMessageBox.warning(self,"Failed","Unable to load users")
            return 
        self.table.setRowCount(len(rows))
        for row_id, row_data in enumerate(rows):
            for col_id, col_data in enumerate(row_data):
                self.table.setItem(row_id, col_id, QTableWidgetItem(str(col_data) or ""))

    def open_userform(self):
        dialog = NewUserDialog(self.db)
        dialog.data_updated.connect(self.load_users_to_table)
        dialog.exec()
        
    def filter_users(self):
        query = self.search_input.text().lower().strip()
        for row in range(self.table.rowCount()):
            match_found = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match_found = True
                    break
            self.table.setRowHidden(row, not match_found)

    def display_user_details(self, row, col):
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        user_id = id_item.text()
        success,user=self.db.get_user_details(user_id)
        if not success:
            QMessageBox.warning(self, "Failed", "Unable to load user details.")
            return 
            
        clear_layout(self.detail_layout)
        
        lbl_header = QLabel("User Profile")
        lbl_header.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; margin-bottom: 10px;")
        
        self.lbl_id = QLabel(user[0])
        self.lbl_name = QLabel(user[1])
        self.lbl_email = QLabel(user[2])
        self.lbl_role = QLabel(user[3])
        self.lbl_department = QLabel(user[4])
        self.lbl_created = QLabel(user[5])
        
        for lbl in (self.lbl_id, self.lbl_name, self.lbl_email, self.lbl_role, self.lbl_department, self.lbl_created):
            lbl.setStyleSheet("qproperty-alignment:'AlignRight | AlignVCenter'; color: #cbd5e1;")

        view_books_btn = QPushButton("View Books")
        view_books_btn.clicked.connect(lambda: self.view_books(user[0]))

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(lambda: self.edit_user(user[0]))

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(lambda: self.delete_user(user[0]))
        
        for btn in [edit_btn, delete_btn, view_books_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b7ade;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover { background-color: #1d64d8; }
            """)
            
        self.detail_layout.addWidget(lbl_header)
        form_layout=QFormLayout()
        form_layout.addRow(QLabel(f"<b>ID:</b>"),self.lbl_id)
        form_layout.addRow(QLabel(f"<b>Name:</b>"),self.lbl_name)
        form_layout.addRow(QLabel(f"<b>Phone No.:</b>"),self.lbl_email)
        form_layout.addRow(QLabel(f"<b>Role:</b>"),self.lbl_role)
        form_layout.addRow(QLabel(f"<b>Department:</b>"),self.lbl_department)
        form_layout.addRow(QLabel(f"<b>Created:</b>"),self.lbl_created)
        self.detail_layout.addLayout(form_layout)
        self.detail_layout.addStretch()
        self.detail_layout.addWidget(view_books_btn)
        self.detail_layout.addWidget(edit_btn)
        self.detail_layout.addWidget(delete_btn)

    def edit_user(self, user_id):
        dialog = EditUserDialog(self.db, user_id)
        dialog.exec()
        self.load_users_to_table()

    def delete_user(self, user_id):
        confirm = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete user {user_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success,message=self.db.delete_user(user_id)
            if success:
                QMessageBox.information(self, "Deleted",message )
                clear_layout(self.detail_layout)
                self.load_users_to_table()
            else:
                QMessageBox.warning(self, "Failed", message)

    def view_books(self, user_id):
        dialog = ViewBooksDialog(self.db, user_id)
        dialog.exec()
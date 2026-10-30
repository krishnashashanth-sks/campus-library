from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QSizePolicy, QFrame, QLabel, QMessageBox, QFormLayout,
    QMenu
)
from utils import clear_layout
from dialogs import UserDialog, ViewBooksDialog
from PyQt6.QtCore import Qt

class UserManagementView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setObjectName("UserManagementView")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # --- Top Action Bar (Search + Add Button) ---
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search users by name, phone, role, department...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid #3b82f6;
            }
        """)
        self.search_input.textChanged.connect(self.filter_users)

        self.add_btn = QPushButton("＋ Add New User")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: 600;
                font-size: 13px;
                border-radius: 8px;
                padding: 10px 18px;
                border: none;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        self.add_btn.clicked.connect(self.add_user)

        top_layout.addWidget(self.search_input, stretch=4)
        top_layout.addWidget(self.add_btn, stretch=1)
        main_layout.addLayout(top_layout)

        # --- Bottom Section: Table + Inspector Drawer ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Connect selection model change safely
        self.table.selectionModel().selectionChanged.connect(self.on_users_selection_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["ID", "Full Name", "Phone Number", "Role", "Department", "Created At"])
        
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
                padding: 12px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
                outline: none;
            }
            QTableWidget::item:focus {
                border: none;
                outline: none;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-weight: bold;
                font-size: 12px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                padding: 12px 10px;
            }
            QHeaderView::section:first {
                border-top-left-radius: 12px;
            }
            QHeaderView::section:last {
                border-top-right-radius: 12px;
            }
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        bottom_layout.addWidget(self.table, stretch=3)

        # --- Right-Side Inspector Panel (Clean SaaS Card) ---
        self.detail_container = QFrame()
        self.detail_container.setFixedWidth(300)
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

        bottom_layout.addWidget(self.detail_container, stretch=0)
        main_layout.addLayout(bottom_layout)

        self.setStyleSheet("""
            #UserManagementView {
                background-color: #f8fafc;
            }
        """)
        self.load_users_to_table()

    def show_default_inspector(self):
        clear_layout(self.detail_layout)
        lbl_header = QLabel("User Inspector")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self.detail_layout.addWidget(lbl_header)
        
        hint = QLabel("Select any user row from the table to view their full profile, assigned books, or manage records.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 20px;")
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_users_to_table(self):
        success, rows = self.db.get_users()
        if not success:
            QMessageBox.warning(self, "Failed", "Unable to load users")
            return 
        self.table.setRowCount(len(rows))
        for row_id, row_data in enumerate(rows):
            for col_id, col_data in enumerate(row_data):
                item = QTableWidgetItem(str(col_data) or "")
                self.table.setItem(row_id, col_id, item)

    def add_user(self):
        dialog = UserDialog(self.db, parent=self)
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

    def on_users_selection_changed(self):
        """Triggers when rows are selected, handling single or batch selection cleanly."""
        selected_indexes = self.table.selectionModel().selectedRows()
        
        if not selected_indexes:
            self.show_default_inspector()
            return
            
        selected_rows = list(set(index.row() for index in selected_indexes))
        
        if len(selected_rows) == 1:
            self.display_user_details(selected_rows[0])
        else:
            clear_layout(self.detail_layout)
            
            lbl_header = QLabel(f"Batch Actions ({len(selected_rows)} Users)")
            lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
            self.detail_layout.addWidget(lbl_header)
            
            hint = QLabel("Multiple users selected. Choose a batch operation to apply to all selected items simultaneously.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 10px; padding-bottom: 10px;")
            self.detail_layout.addWidget(hint)
            
            batch_delete_btn = QPushButton("🗑️ Batch Delete Selected")
            batch_delete_btn.clicked.connect(lambda: self.handle_batch_delete(selected_rows))
            
            batch_delete_btn.setStyleSheet("""
                QPushButton { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; font-weight: 600; font-size: 12px; padding: 10px; text-align: left; }
                QPushButton:hover { background-color: #ef4444; color: white; }
            """)
            
            self.detail_layout.addStretch()
            self.detail_layout.addWidget(batch_delete_btn)

    def display_user_details(self, row):
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        user_id = id_item.text()
        success, user = self.db.get_user_details(user_id)
        if not success:
            QMessageBox.warning(self, "Failed", "Unable to load user details.")
            return 
            
        clear_layout(self.detail_layout)
        
        lbl_header = QLabel("User Profile Control")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        
        self.lbl_id = QLabel(str(user[0]))
        self.lbl_name = QLabel(str(user[1]))
        self.lbl_email = QLabel(str(user[2]))
        self.lbl_role = QLabel(str(user[3]))
        self.lbl_department = QLabel(str(user[4]))
        self.lbl_created = QLabel(str(user[5]))
        
        for lbl in (self.lbl_id, self.lbl_name, self.lbl_email, self.lbl_role, self.lbl_department, self.lbl_created):
            lbl.setStyleSheet("color: #334155; font-size: 12px; border: none; background: transparent;")
            lbl.setWordWrap(True)

        view_books_btn = QPushButton("📖  View Assigned Books")
        edit_btn = QPushButton("✏️  Edit User Profile")
        delete_btn = QPushButton("🗑️  Delete User")
        
        view_books_btn.clicked.connect(lambda: self.view_books(user[0]))
        edit_btn.clicked.connect(lambda: self.edit_user(user[0]))
        delete_btn.clicked.connect(lambda: self.delete_user(user[0]))
        
        view_books_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; border: none; } QPushButton:hover { background-color: #1d4ed8; }")
        edit_btn.setStyleSheet("QPushButton { background-color: #f1f5f9; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; } QPushButton:hover { background-color: #e2e8f0; }")
        delete_btn.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; } QPushButton:hover { background-color: #ef4444; color: white; }")

        self.detail_layout.addWidget(lbl_header)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        form_layout.addRow(QLabel("<b>ID:</b>"), self.lbl_id)
        form_layout.addRow(QLabel("<b>Name:</b>"), self.lbl_name)
        form_layout.addRow(QLabel("<b>Phone:</b>"), self.lbl_email)
        form_layout.addRow(QLabel("<b>Role:</b>"), self.lbl_role)
        form_layout.addRow(QLabel("<b>Department:</b>"), self.lbl_department)
        form_layout.addRow(QLabel("<b>Created:</b>"), self.lbl_created)
        
        for i in range(form_layout.rowCount()):
            label_item = form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setStyleSheet("color: #64748b; font-size: 12px; border: none; background: transparent;")

        self.detail_layout.addLayout(form_layout)
        self.detail_layout.addStretch()
        
        self.detail_layout.addWidget(view_books_btn)
        self.detail_layout.addWidget(edit_btn)
        self.detail_layout.addWidget(delete_btn)

    def edit_user(self, user_id):
        dialog = UserDialog(self.db, user_id=user_id, parent=self)
        if dialog.exec():
            current_row = self.table.currentRow()
            self.load_users_to_table()
            if current_row >= 0 and current_row < self.table.rowCount():
                self.table.selectRow(current_row)
                self.display_user_details(current_row)

    def delete_user(self, user_id):
        confirm = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete user {user_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success, message = self.db.delete_user(user_id)
            if success:
                QMessageBox.information(self, "Deleted", message)
                self.show_default_inspector()
                self.load_users_to_table()
            else:
                QMessageBox.warning(self, "Failed", message)

    def handle_batch_delete(self, rows):
        user_ids = [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]
        if not user_ids:
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Batch Deletion",
            f"Are you sure you want to delete {len(user_ids)} selected users? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            success_count = 0
            errors = []
            
            for u_id in user_ids:
                success, err_msg = self.db.delete_user(u_id)
                if success:
                    success_count += 1
                else:
                    errors.append(f"• User ID {u_id}: {err_msg or 'Cannot delete user (possibly has active checkouts)'}")
                    
            msg = f"Successfully removed {success_count} out of {len(user_ids)} users from the database."
            if errors:
                msg += f"\n\nFailed items:\n" + "\n".join(errors)
                QMessageBox.warning(self, "Batch Deletion Completed with Errors", msg)
            else:
                QMessageBox.information(self, "Batch Deleted", msg)

            self.load_users_to_table()
            self.show_default_inspector()

    def view_books(self, user_id):
        dialog = ViewBooksDialog(self.db, user_id, parent=self)
        dialog.exec()

    def show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        user_id = id_item.text()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: white;
            }
        """)
        books_action = menu.addAction("📖 View Assigned Books")
        menu.addSeparator()
        edit_action = menu.addAction("✏️ Edit User")
        delete_action = menu.addAction("🗑️ Delete User")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == books_action:
            self.view_books(user_id)
        elif action == edit_action:
            self.edit_user(user_id)
        elif action == delete_action:
            self.delete_user(user_id)
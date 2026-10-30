from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLineEdit, QHBoxLayout,
    QSizePolicy, QHeaderView, QPushButton, QFrame, QLabel, QMessageBox, QFormLayout,
    QMenu, QInputDialog, QFileDialog
)
from dialogs import BookDialog, BarcodeGeneratorDialog, BookHistoryDialog
from utils import clear_layout
from PyQt6.QtCore import Qt
import csv
from datetime import date

class CatalogView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setObjectName("CatalogView")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # --- Top Action Bar (Search + Add Button) ---
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search books by title, author, publisher...")
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
        self.search_input.textChanged.connect(self.filter_books)

        self.import_btn = QPushButton("📥  Import CSV")
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                font-weight: 600;
                font-size: 13px;
                border-radius: 8px;
                padding: 10px 14px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.import_btn.clicked.connect(self.import_books_from_csv)

        self.addbook_btn = QPushButton("＋ Add New Book")
        self.addbook_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: 600;
                font-size: 13px;
                border-radius: 8px;
                padding: 10px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.addbook_btn.clicked.connect(self.add_book)
        
        top_layout.addWidget(self.search_input, stretch=4)
        top_layout.addWidget(self.import_btn, stretch=1)
        top_layout.addWidget(self.addbook_btn, stretch=1)
        main_layout.addLayout(top_layout)

        # --- Bottom Section: Table + Inspector Drawer ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(20)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        
        # Connect selection model change safely
        self.table.selectionModel().selectionChanged.connect(self.on_books_selection_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["ID", "Title", "Author", "Publisher", "Total", "Available", "Added On"])
        
        # Professional Table Styling with Smooth Rounded Corners & No Focus Lines
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
        
        # REMOVED self.table.cellClicked.connect to prevent conflict with selectionChanged!
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
            #CatalogView {
                background-color: #f8fafc;
            }
        """)
        self.load_books_to_table()
        
    def show_default_inspector(self):
        clear_layout(self.detail_layout)
        lbl_header = QLabel("Book Inspector")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self.detail_layout.addWidget(lbl_header)
        
        hint = QLabel("Select any book row from the catalog table to view full details, check stock levels, or manage records.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 20px;")
        self.detail_layout.addWidget(hint)
        self.detail_layout.addStretch()

    def load_books_to_table(self):
        success, rows = self.db.get_books()
        if not success:
            QMessageBox.warning(self, "Failed", "Unable to load the books")
            return 
        self.table.setRowCount(len(rows))
        for row_id, row_data in enumerate(rows):
            for col_id, col_data in enumerate(row_data):
                item = QTableWidgetItem(str(col_data) or "")
                self.table.setItem(row_id, col_id, item)

    def display_book_details(self, row):
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        book_id = id_item.text()
        success, book = self.db.get_book_details(book_id)
        if not success:
            QMessageBox.warning(self, "Failed", f"Unable to load book ({book_id}) details")
            return
            
        clear_layout(self.detail_layout)
        
        lbl_header = QLabel("Book Control Center")
        lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        
        self.lbl_id = QLabel(str(book[0]))
        self.lbl_title = QLabel(str(book[1]))
        self.lbl_author = QLabel(str(book[2]))
        self.lbl_publisher = QLabel(str(book[3]))
        self.lbl_total = QLabel(str(book[4]))
        self.lbl_available = QLabel(str(book[5]))
        self.lbl_created = QLabel(str(book[6]))
        
        for lbl in (self.lbl_id, self.lbl_title, self.lbl_author, self.lbl_publisher, self.lbl_total, self.lbl_available, self.lbl_created):
            lbl.setStyleSheet("color: #334155; font-size: 12px; border: none; background: transparent;")
            lbl.setWordWrap(True)
            
        self.lbl_available.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px; border: none; background: transparent;")

        # --- LIVE CHECKOUT STATUS QUERY ---
        status_text = "🟢 Available on Shelf"
        status_style = "background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px; font-size: 12px; font-weight: 600;"
        
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT user_id, due_date FROM circulation_logs 
                WHERE book_id = ? AND status = 'ISSUED' LIMIT 1
            """, (book_id,))
            active_loan = cursor.fetchone()
            if active_loan:
                borrower_id, due_date = active_loan
                status_text = f"🔴 Checked Out\n• User ID: {borrower_id}\n• Due: {due_date}"
                status_style = "background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca; border-radius: 6px; padding: 8px; font-size: 12px; font-weight: 600;"
        except Exception:
            pass

        self.lbl_status_banner = QLabel(status_text)
        self.lbl_status_banner.setWordWrap(True)
        self.lbl_status_banner.setStyleSheet(status_style)

        # --- Action Buttons ---
        issue_btn = QPushButton("📤 Issue Book")
        return_btn = QPushButton("📥 Return Book")
        barcode_btn = QPushButton("🖨️ Print Barcode")
        history_btn = QPushButton("📜 View Audit History")
        edit_btn = QPushButton("✏️ Edit Record")
        delete_btn = QPushButton("🗑️ Delete Book")
        
        issue_btn.clicked.connect(lambda: self.handle_issue_book(book[0], book[1]))
        return_btn.clicked.connect(lambda: self.handle_return_book(book[0], book[1]))
        barcode_btn.clicked.connect(lambda: self.open_barcode_dialog_for_selected(book[0]))
        history_btn.clicked.connect(lambda: self.open_book_history(book[0], book[1]))
        edit_btn.clicked.connect(lambda: self.edit_book(book[0]))
        delete_btn.clicked.connect(lambda: self.delete_book(book[0]))
        
        # Styles for buttons...
        issue_btn.setStyleSheet("QPushButton { background-color: #2563eb; color: white; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; border: none; } QPushButton:hover { background-color: #1d4ed8; }")
        return_btn.setStyleSheet("QPushButton { background-color: #10b981; color: white; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; border: none; } QPushButton:hover { background-color: #059669; }")

        for btn in [barcode_btn, history_btn, edit_btn]:
            btn.setStyleSheet("QPushButton { background-color: #f1f5f9; color: #1e293b; border: 1px solid #cbd5e1; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; } QPushButton:hover { background-color: #e2e8f0; }")

        delete_btn.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; font-weight: 600; font-size: 12px; padding: 8px 12px; text-align: left; } QPushButton:hover { background-color: #ef4444; color: white; }")

        self.detail_layout.addWidget(lbl_header)
        self.detail_layout.addWidget(self.lbl_status_banner) # Add the gorgeous status card right at the top!
        
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        form_layout.addRow(QLabel("<b>ID:</b>"), self.lbl_id)
        form_layout.addRow(QLabel("<b>Title:</b>"), self.lbl_title)
        form_layout.addRow(QLabel("<b>Author:</b>"), self.lbl_author)
        form_layout.addRow(QLabel("<b>Publisher:</b>"), self.lbl_publisher)
        form_layout.addRow(QLabel("<b>Total:</b>"), self.lbl_total)
        form_layout.addRow(QLabel("<b>Available:</b>"), self.lbl_available)
        form_layout.addRow(QLabel("<b>Added:</b>"), self.lbl_created)
        
        for i in range(form_layout.rowCount()):
            label_item = form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setStyleSheet("color: #64748b; font-size: 12px; border: none; background: transparent;")

        self.detail_layout.addLayout(form_layout)
        self.detail_layout.addStretch()
        
        self.detail_layout.addWidget(issue_btn)
        self.detail_layout.addWidget(return_btn)
        self.detail_layout.addWidget(barcode_btn)
        self.detail_layout.addWidget(history_btn)
        self.detail_layout.addWidget(edit_btn)
        self.detail_layout.addWidget(delete_btn)
            
    def add_book(self):
        dialog = BookDialog(self.db)
        dialog.data_updated.connect(self.load_books_to_table)
        dialog.exec()
        
    def filter_books(self):
        query = self.search_input.text().lower().strip()
        for row in range(self.table.rowCount()):
            match_found = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match_found = True
                    break
            self.table.setRowHidden(row, not match_found)
            
    def handle_issue_book(self, book_id, book_title):
        user_id, ok = QInputDialog.getText(self, "Issue Book", f"Enter User ID to issue '{book_title}':")
        if not ok or not user_id.strip():
            return

        days_allowed, ok_days = QInputDialog.getInt(self, "Issue Duration", "Enter the number of days allowed?", 14, 1, 365, 1)
        if not ok_days:
            return

        success, msg = self.db.issue_book(book_id, user_id.strip(), days_allowed)
        if success:
            QMessageBox.information(self, "Success", f"Book successfully issued for {days_allowed} days!")
            
            current_row = self.table.currentRow()
            self.load_books_to_table()
            if current_row >= 0 and current_row < self.table.rowCount():
                self.table.selectRow(current_row)
                self.display_book_details(current_row)  # <--- Explicitly refresh the control center!
            else:
                self.show_default_inspector()
        else:
            QMessageBox.warning(self, "Action Failed", msg)

    def handle_return_book(self, book_id, book_title):
        user_id, ok = QInputDialog.getText(self, "Return Book", f"Enter User ID returning '{book_title}':")
        if not ok or not user_id.strip():
            return

        success, fine, msg = self.db.return_book(book_id, user_id.strip())
        
        if success:
            if fine > 0.0:
                QMessageBox.information(
                    self, 
                    "Book Returned with Fine", 
                    f"Book returned successfully!\n\n⚠️ Overdue Fine Applied: ₹{fine:.2f}"
                )
            else:
                QMessageBox.information(self, "Success", f"{msg}\nNo overdue fines.")
            
            current_row = self.table.currentRow()
            self.load_books_to_table()
            if current_row >= 0 and current_row < self.table.rowCount():
                self.table.selectRow(current_row)
                self.display_book_details(current_row)  # <--- Explicitly refresh the control center!
            else:
                self.show_default_inspector()
        else:
            QMessageBox.warning(self, "Action Failed", str(msg))
            
    def edit_book(self, book_id):
        dialog = BookDialog(self.db, book_id=book_id)
        dialog.exec()
        self.load_books_to_table()
        self.show_default_inspector()
        
    def delete_book(self, book_id):
        confirm = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete book {book_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success, message = self.db.delete_book(book_id)
            if success:
                QMessageBox.information(self, "Success", message)
                self.show_default_inspector()
                self.load_books_to_table()
            else:
                QMessageBox.warning(self, "Failed", message)
                
    def show_context_menu(self, pos):
        """Displays a rich context menu with all book management and circulation actions."""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        row = index.row()
        id_item = self.table.item(row, 0)
        title_item = self.table.item(row, 1)
        
        if not id_item:
            return
            
        book_id = id_item.text()
        book_title = title_item.text() if title_item else "Unknown Title"

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

        # Actions
        issue_action = menu.addAction("📤 Issue Book")
        return_action = menu.addAction("📥 Return Book")
        menu.addSeparator()
        barcode_action = menu.addAction("🖨️ Print Barcode")
        edit_action = menu.addAction("✏️ Edit Book")
        delete_action = menu.addAction("🗑️ Delete Book")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if action == issue_action:
            self.handle_issue_book(book_id, book_title)
        elif action == return_action:
            self.handle_return_book(book_id, book_title)
        elif action == barcode_action:
            self.open_barcode_dialog_for_selected(book_id)
        elif action == edit_action:
            self.edit_book(book_id)
        elif action == delete_action:
            self.delete_book(book_id)

    def open_barcode_dialog_for_selected(self, book_id=""):
        if book_id:
            success, book = self.db.get_book_details(book_id)
            if success and book:
                dialog = BarcodeGeneratorDialog(
                    self.db, 
                    book_id=str(book[0]), 
                    title=str(book[1]), 
                    author=str(book[2]), 
                    publisher=str(book[3]), 
                    parent=self
                )
                dialog.exec()
            else:
                QMessageBox.warning(self, "Error", "Could not fetch book details.")
        else:
            dialog = BarcodeGeneratorDialog(self.db, parent=self)
            dialog.data_updated.connect(self.load_books_to_table)
            dialog.exec()

    def on_books_selection_changed(self):
        """Triggers when rows are selected, handling single or batch selection cleanly."""
        selected_indexes = self.table.selectionModel().selectedRows()
        
        if not selected_indexes:
            return
            
        selected_rows = list(set(index.row() for index in selected_indexes))
        
        if len(selected_rows) == 1:
            self.display_book_details(selected_rows[0])
        else:
            clear_layout(self.detail_layout)
            
            lbl_header = QLabel(f"Batch Actions ({len(selected_rows)} Books)")
            lbl_header.setStyleSheet("color: #0f172a; font-size: 15px; font-weight: bold; border: none; background: transparent;")
            self.detail_layout.addWidget(lbl_header)
            
            hint = QLabel("Multiple books selected. Choose a batch operation to apply to all selected items simultaneously.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #64748b; font-size: 13px; border: none; background: transparent; padding-top: 10px; padding-bottom: 10px;")
            self.detail_layout.addWidget(hint)
            
            batch_issue_btn = QPushButton("📤 Batch Issue Books")
            batch_return_btn = QPushButton("📥 Batch Return Books")
            batch_delete_btn = QPushButton("🗑️ Batch Delete Selected")
            
            batch_issue_btn.clicked.connect(lambda: self.handle_batch_issue(selected_rows))
            batch_return_btn.clicked.connect(lambda: self.handle_batch_return(selected_rows))
            batch_delete_btn.clicked.connect(lambda: self.handle_batch_delete(selected_rows))
            
            batch_issue_btn.setStyleSheet("""
                QPushButton { background-color: #2563eb; color: white; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 10px; border: none; text-align: left; }
                QPushButton:hover { background-color: #1d4ed8; }
            """)
            batch_return_btn.setStyleSheet("""
                QPushButton { background-color: #10b981; color: white; border-radius: 6px; font-weight: 600; font-size: 12px; padding: 10px; border: none; text-align: left; }
                QPushButton:hover { background-color: #059669; }
            """)
            batch_delete_btn.setStyleSheet("""
                QPushButton { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; font-weight: 600; font-size: 12px; padding: 10px; text-align: left; }
                QPushButton:hover { background-color: #ef4444; color: white; }
            """)
            
            self.detail_layout.addStretch()
            self.detail_layout.addWidget(batch_issue_btn)
            self.detail_layout.addWidget(batch_return_btn)
            self.detail_layout.addWidget(batch_delete_btn)

    def handle_batch_issue(self, rows):
        book_ids = [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]
        if not book_ids:
            return
            
        user_id, ok = QInputDialog.getText(self, "Batch Issue", f"Enter User ID to issue these {len(book_ids)} books to:")
        if not ok or not user_id.strip():
            return
            
        days_allowed, ok_days = QInputDialog.getInt(self, "Issue Duration", "Days allowed for this batch?", 14, 1, 365, 1)
        if not ok_days:
            return
            
        success_count = 0
        errors = []

        for b_id in book_ids:
            success, err_msg = self.db.issue_book(b_id, user_id.strip(), days_allowed)
            if success:
                success_count += 1
            else:
                errors.append(f"• ID {b_id}: {err_msg or 'Unknown error'}")
                
        # Build message summary
        msg = f"Successfully issued {success_count} out of {len(book_ids)} books to user {user_id.strip()}."
        if errors:
            msg += f"\n\nFailed items:\n" + "\n".join(errors)
            QMessageBox.warning(self, "Batch Issue Completed with Errors", msg)
        else:
            QMessageBox.information(self, "Batch Complete", msg)

        self.load_books_to_table()
        self.show_default_inspector()

    def handle_batch_return(self, rows):
        """Processes return for multiple selected books and tallies total fines, capturing any errors."""
        book_ids = [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]
        if not book_ids:
            return
            
        user_id, ok = QInputDialog.getText(self, "Batch Return", f"Enter User ID returning these {len(book_ids)} books:")
        if not ok or not user_id.strip():
            return
            
        success_count = 0
        total_fine = 0.0
        errors = []
        
        for b_id in book_ids:
            # Assuming return_book returns (success, fine, message)
            res = self.db.return_book(b_id, user_id.strip())
            if len(res) == 3:
                success, fine, err_msg = res
            else:
                success, fine = res[0], res[1]
                err_msg = "Return failed"

            if success:
                success_count += 1
                total_fine += fine
            else:
                errors.append(f"• ID {b_id}: {err_msg or 'Not currently checked out by this user'}")
                
        msg = (
            f"Successfully processed returns for {success_count} out of {len(book_ids)} books.\n"
            f"Total Collected Fines: ₹{total_fine:.2f}"
        )
        if errors:
            msg += f"\n\nFailed items:\n" + "\n".join(errors)
            QMessageBox.warning(self, "Batch Return Completed with Errors", msg)
        else:
            QMessageBox.information(self, "Batch Return Complete", msg)

        self.load_books_to_table()
        self.show_default_inspector()

    def handle_batch_delete(self, rows):
        book_ids = [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]
        if not book_ids:
            return
            
        confirm = QMessageBox.question(
            self, "Confirm Batch Deletion",
            f"Are you sure you want to delete {len(book_ids)} selected books? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            success_count = 0
            errors = []
            
            for b_id in book_ids:
                success, err_msg = self.db.delete_book(b_id)
                if success:
                    success_count += 1
                else:
                    errors.append(f"• ID {b_id}: {err_msg or 'Cannot delete (possibly checked out)'}")
                    
            msg = f"Successfully removed {success_count} out of {len(book_ids)} books from the database."
            if errors:
                msg += f"\n\nFailed items:\n" + "\n".join(errors)
                QMessageBox.warning(self, "Batch Deletion Completed with Errors", msg)
            else:
                QMessageBox.information(self, "Batch Deleted", msg)

            self.load_books_to_table()
            self.show_default_inspector()
            
    def open_book_history(self, book_id, book_title):
        dialog = BookHistoryDialog(self.db, book_id, book_title, parent=self)
        dialog.exec()
    def import_books_from_csv(self):
        """Opens a file dialog to select a CSV file and batch-imports/updates books in the database."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Book Catalog CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return

        imported_count = 0
        error_count = 0
        books_to_insert = []
        
        # Get today's clean date (YYYY-MM-DD format without seconds/time)
        current_date = date.today().isoformat()

        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                rows = list(reader)
                
                if len(rows) < 2:
                    QMessageBox.warning(self, "Invalid CSV", "The CSV file is empty or missing data rows.")
                    return

                # Clean header row to strip invisible characters, BOMs, or quotes
                header = [h.lower().strip().replace('\ufeff', '').replace('"', '') for h in rows[0]]
                
                # Identify column positions (supporting both 'book_id' and 'id')
                id_idx = header.index('book_id') if 'book_id' in header else (header.index('id') if 'id' in header else -1)
                title_idx = header.index('title') if 'title' in header else -1
                author_idx = header.index('author') if 'author' in header else -1
                pub_idx = header.index('publisher') if 'publisher' in header else -1
                copies_idx = header.index('total_copies') if 'total_copies' in header else -1

                if id_idx == -1 or title_idx == -1:
                    QMessageBox.warning(
                        self, 
                        "Missing Mandatory Headers", 
                        f"The CSV file must contain both 'book_id' (or 'id') and 'title' column headers.\nFound headers: {header}"
                    )
                    return

                for r in rows[1:]:
                    if not r or len(r) <= max(id_idx, title_idx):
                        error_count += 1
                        continue

                    b_id = r[id_idx].strip() if len(r) > id_idx else ""
                    title = r[title_idx].strip() if len(r) > title_idx else ""
                    author = r[author_idx].strip() if author_idx != -1 and len(r) > author_idx and r[author_idx].strip() else "Unknown Author"
                    publisher = r[pub_idx].strip() if pub_idx != -1 and len(r) > pub_idx and r[pub_idx].strip() else "Unknown Publisher"
                    
                    copies_str = r[copies_idx].strip() if copies_idx != -1 and len(r) > copies_idx and r[copies_idx].strip() else "1"
                    try:
                        total_copies = int(copies_str)
                    except ValueError:
                        total_copies = 1

                    available_copies = total_copies

                    if b_id and title:
                        # Append with the clean date string instead of a timestamp with seconds
                        books_to_insert.append((b_id, title, author, publisher, total_copies, available_copies, current_date))
                    else:
                        error_count += 1

            if books_to_insert:
                cursor = self.db.conn.cursor()
                
                # UPSERT query including the clean 'added_on' date column
                cursor.executemany("""
                    INSERT INTO books (id, title, author, publisher, total_copies, available_copies, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        total_copies = total_copies + excluded.total_copies,
                        available_copies = available_copies + excluded.total_copies,
                        title = COALESCE(excluded.title, title),
                        author = COALESCE(excluded.author, author),
                        publisher = COALESCE(excluded.publisher, publisher)
                """, books_to_insert)
                
                self.db.conn.commit()
                imported_count = len(books_to_insert)

            msg = f"Successfully processed {imported_count} catalog records!"
            if error_count > 0:
                msg += f"\n(Skipped {error_count} rows due to missing 'book_id' or 'title')."
                
            QMessageBox.information(self, "Import Complete", msg)
            self.load_books_to_table()

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"An error occurred while processing the file:\n{e}")
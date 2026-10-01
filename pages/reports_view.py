import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, 
    QMessageBox, QFileDialog, QHBoxLayout, QPushButton, QSizePolicy, QHeaderView
)

class ReportsView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        main_layout = QVBoxLayout(self)

        title_label = QLabel("<b>Library Analytics & Reports</b>")
        title_label.setStyleSheet("font-size: 18px; color: white; margin-bottom: 10px;")
        main_layout.addWidget(title_label)

        action_layout = QHBoxLayout()

        self.btn_export = QPushButton("Export Circulation CSV")
        self.btn_export.setStyleSheet("background-color: #2b7ade; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_export.clicked.connect(self.export_to_csv)
        
        action_layout.addWidget(self.btn_export)
        action_layout.addStretch()
        main_layout.addLayout(action_layout)

        self.table_reports = QTableWidget()
        self.table_reports.setColumnCount(8)
        self.table_reports.setHorizontalHeaderLabels([
            "Log ID", 
            "Book ID", 
            "User ID", 
            "Status", 
            "Checkout Date", 
            "Due Date", 
            "Return Date", 
            "Fine"
        ])
        self.table_reports.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        header = self.table_reports.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        main_layout.addWidget(self.table_reports)
        self.load_data()

    def load_data(self):
        success, rows = self.db.get_logs()
        if not success:
            return

        self.table_reports.setRowCount(len(rows))
        
        for row_idx, row in enumerate(rows):
            log_id, book_id, user_id, checkout_date, due_date, return_date, fine, status = row

            fine_str = f"₹{float(fine):.2f}" if fine is not None else "₹0.00"

            self.table_reports.setItem(row_idx, 0, QTableWidgetItem(str(log_id)))
            self.table_reports.setItem(row_idx, 1, QTableWidgetItem(str(book_id)))
            self.table_reports.setItem(row_idx, 2, QTableWidgetItem(str(user_id)))
            self.table_reports.setItem(row_idx, 3, QTableWidgetItem(str(status)))
            self.table_reports.setItem(row_idx, 4, QTableWidgetItem(str(checkout_date or "")))
            self.table_reports.setItem(row_idx, 5, QTableWidgetItem(str(due_date or "")))
            self.table_reports.setItem(row_idx, 6, QTableWidgetItem(str(return_date or "N/A")))
            self.table_reports.setItem(row_idx, 7, QTableWidgetItem(fine_str))

    def export_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Report", "library_report.csv", "CSV Files (*.csv)")
        if path:
            try:
                with open(path, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    header_labels = [
                        self.table_reports.horizontalHeaderItem(i).text() 
                        for i in range(self.table_reports.columnCount())
                    ]
                    writer.writerow(header_labels)

                    for row in range(self.table_reports.rowCount()):
                        row_data = []
                        for col in range(self.table_reports.columnCount()):
                            item = self.table_reports.item(row, col)
                            row_data.append(item.text() if item else "")
                        writer.writerow(row_data)

                QMessageBox.information(self, "Success", f"Successfully exported to:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Unable to export CSV: {e}")
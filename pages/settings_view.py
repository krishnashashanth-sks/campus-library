from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QGroupBox, QLineEdit,
    QPushButton, QVBoxLayout, QFileDialog, QMessageBox,
    QDoubleSpinBox, QSpinBox
)

class SettingsView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Page Header
        lbl_title = QLabel("Application Settings")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; border: none;")
        main_layout.addWidget(lbl_title)

        # 1. Circulation & Fine Rules
        group_rules = QGroupBox("Circulation & Fine Rules")
        rules_layout = QVBoxLayout(group_rules)

        fine_layout = QHBoxLayout()
        fine_layout.addWidget(QLabel("Daily Fine Amount (Rs):"))
        self.spin_daily_fine = QDoubleSpinBox()
        self.spin_daily_fine.setRange(0.00, 1000.00)
        self.spin_daily_fine.setSingleStep(0.50)
        self.spin_daily_fine.setFixedWidth(120)
        fine_layout.addWidget(self.spin_daily_fine)
        fine_layout.addStretch()
        rules_layout.addLayout(fine_layout)

        days_layout = QHBoxLayout()
        days_layout.addWidget(QLabel("Default Borrowing Duration:"))
        self.spin_default_days = QSpinBox()
        self.spin_default_days.setRange(1, 365)
        self.spin_default_days.setSuffix(" days")
        self.spin_default_days.setFixedWidth(120)
        days_layout.addWidget(self.spin_default_days)
        days_layout.addStretch()
        rules_layout.addLayout(days_layout)

        main_layout.addWidget(group_rules)

        # 2. Database Maintenance
        group_database = QGroupBox("Database Maintenance")
        db_layout = QVBoxLayout(group_database)
        db_layout.setSpacing(10)

        self.db_backup_btn = QPushButton("Back Up Database File")
        self.db_backup_btn.clicked.connect(self.database_backup)
        db_layout.addWidget(self.db_backup_btn)

        lbl_info = QLabel("Danger zone: Permanent deletion of circulation logs (cannot be undone)")
        lbl_info.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold; border: none;")
        db_layout.addWidget(lbl_info)

        clear_logs_btn = QPushButton("Clear All Circulation Logs")
        clear_logs_btn.setStyleSheet("background-color: #ef4444; color: white;")
        clear_logs_btn.clicked.connect(self.clear_all_logs)
        db_layout.addWidget(clear_logs_btn)

        main_layout.addWidget(group_database)

        # 3. Security & Password Section
        group_security = QGroupBox("Admin Password Security")
        sec_layout = QVBoxLayout(group_security)
        sec_layout.setSpacing(14)

        row_cur = QHBoxLayout()
        lbl_cur = QLabel("Current Password:")
        lbl_cur.setFixedWidth(140)
        self.input_cur_psw = QLineEdit()
        self.input_cur_psw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_cur_psw.setPlaceholderText("Enter current password")
        row_cur.addWidget(lbl_cur)
        row_cur.addWidget(self.input_cur_psw)

        row_new = QHBoxLayout()
        lbl_new = QLabel("New Password:")
        lbl_new.setFixedWidth(140)
        self.input_new_psw = QLineEdit()
        self.input_new_psw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_new_psw.setPlaceholderText("Enter new password")
        row_new.addWidget(lbl_new)
        row_new.addWidget(self.input_new_psw)

        row_con = QHBoxLayout()
        lbl_con = QLabel("Confirm Password:")
        lbl_con.setFixedWidth(140)
        self.input_con_psw = QLineEdit()
        self.input_con_psw.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_con_psw.setPlaceholderText("Re-enter new password")
        row_con.addWidget(lbl_con)
        row_con.addWidget(self.input_con_psw)

        sec_layout.addLayout(row_cur)
        sec_layout.addLayout(row_new)
        sec_layout.addLayout(row_con)

        btn_change = QPushButton("Update Password")
        btn_change.clicked.connect(self.change_password)
        sec_layout.addWidget(btn_change)

        main_layout.addWidget(group_security)
        main_layout.addStretch()

        # Save Settings Action Button
        bottom_layout = QHBoxLayout()
        self.btn_reset = QPushButton("Reset All Settings")
        self.btn_reset.setStyleSheet("background-color: #10b981; color: white; min-height: 38px; font-size: 14px;")
        self.btn_reset.clicked.connect(self.reset_settings)
        bottom_layout.addWidget(self.btn_reset)

        self.btn_save = QPushButton("Save All Settings")
        self.btn_save.setStyleSheet("background-color: #10b981; color: white; min-height: 38px; font-size: 14px;")
        self.btn_save.clicked.connect(self.save_settings)
        bottom_layout.addWidget(self.btn_save)

        main_layout.addLayout(bottom_layout)

    def load_settings(self):
        fine_val = self.db.get_setting('daily_fine', 10.00)
        default_days = self.db.get_setting('default_days', 14)

        try:
            self.spin_daily_fine.setValue(float(fine_val))
            self.spin_default_days.setValue(int(default_days))
        except (ValueError, TypeError):
            pass

    def save_settings(self):
        fine_val = self.spin_daily_fine.value()
        days_val = self.spin_default_days.value()

        self.db.set_setting("daily_fine", fine_val)
        self.db.set_setting("default_days", days_val)

        QMessageBox.information(self, "Settings Saved", "Your settings have been saved successfully!")

    def reset_settings(self):
        self.db.set_setting("daily_fine", 10.00)
        self.db.set_setting("default_days", 14)

        QMessageBox.information(self, "Settings Reset", "Your settings have been reset successfully!")
        self.load_settings()

    def database_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "Database Backup", "library_backup.db", "Database Files (*.db)")
        if path:
            try:
                with open("local_library.db", "rb") as src, open(path, "wb") as dst:
                    dst.write(src.read())
                QMessageBox.information(self, "Success", f"Database backed up to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to back up database:\n{e}")

    def clear_all_logs(self):
        reply = QMessageBox.warning(
            self, "Confirm Deletion",
            "Are you sure you want to delete all circulation logs?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.db.conn.cursor()
                cursor.execute("DELETE FROM circulation_logs")
                self.db.conn.commit()
                QMessageBox.information(self, "Success", "Circulation logs cleared successfully.")
            except Exception as e:
                self.db.conn.rollback()
                QMessageBox.critical(self, "Database Error", f"Unable to clear logs: {e}")

    def change_password(self):
        cur_psw = self.input_cur_psw.text().strip()
        new_psw = self.input_new_psw.text().strip()
        con_psw = self.input_con_psw.text().strip()

        if not cur_psw or not new_psw or not con_psw:
            QMessageBox.warning(self, "Validation Error", "Please fill in all password fields.")
            return
        if new_psw != con_psw:
            QMessageBox.warning(self, "Validation Error", "New password and confirm password must match.")
            return
        if len(new_psw) < 4:
            QMessageBox.warning(self, "Validation Error", "Password must be at least 4 characters long.")
            return

        stored_psw = self.db.get_setting("admin_password", "admin123")
        if stored_psw != cur_psw:
            QMessageBox.critical(self, "Access Denied", "Incorrect current password.")
            return

        self.db.set_setting("admin_password", new_psw)
        QMessageBox.information(self, "Success", "Password updated successfully!")

        self.input_cur_psw.clear()
        self.input_new_psw.clear()
        self.input_con_psw.clear()
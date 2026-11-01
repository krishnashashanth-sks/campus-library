import os
import sqlite3
import datetime

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QFileDialog,
    QMessageBox, QDoubleSpinBox, QSpinBox, QComboBox,
    QScrollArea, QFrame, QInputDialog, QApplication,
    QGridLayout, QSizePolicy
)

from dialogs import DepartmentManagerDialog


class SettingsView(QWidget):

    DEFAULTS = {
        "daily_fine": 10.00,
        "default_days": 14,
        "theme_mode": "Dark",
    }

    THEMES = ("Dark", "Light", "System")

    def __init__(self, db):
        super().__init__()

        self.db = db
        self._loading_settings = False
        self._saving_settings = False
        self._theme_manager = None

        self.setObjectName("SettingsView")

        self.init_ui()
        self.apply_theme()
        self.connect_theme_manager()
        self.load_settings()

    # =========================================================
    # THEME MANAGEMENT
    # =========================================================

    def get_theme_manager(self):
        app = QApplication.instance()

        manager = getattr(app, "theme_manager", None) if app else None

        if manager:
            return manager

        parent = self.parent()

        while parent:
            manager = getattr(parent, "theme_manager", None)

            if manager:
                return manager

            parent = parent.parent()

        return None

    def connect_theme_manager(self):
        self._theme_manager = self.get_theme_manager()

        if self._theme_manager:
            signal = getattr(
                self._theme_manager,
                "themeChanged",
                None
            )

            if signal:
                signal.connect(self.on_global_theme_changed)

    def apply_theme(self, *_):
        manager = self._theme_manager or self.get_theme_manager()
        theme = getattr(manager, "active_theme", "Dark")
        colors = getattr(manager, "COLORS", {}).get(theme)

        if colors is None:
            palette = QApplication.palette()
            colors = {
                "window": palette.color(
                    palette.ColorRole.Window
                ).name(),
                "surface": palette.color(
                    palette.ColorRole.Button
                ).name(),
                "surface_alt": palette.color(
                    palette.ColorRole.AlternateBase
                ).name(),
                "input": palette.color(
                    palette.ColorRole.Base
                ).name(),
                "border": palette.color(
                    palette.ColorRole.Mid
                ).name(),
                "text": palette.color(
                    palette.ColorRole.Text
                ).name(),
                "muted": palette.color(
                    palette.ColorRole.PlaceholderText
                ).name(),
                "primary": palette.color(
                    palette.ColorRole.Highlight
                ).name(),
                "primary_hover": palette.color(
                    palette.ColorRole.Highlight
                ).darker(115).name(),
                "danger": "#DC2626",
            }

        c = colors
        self.setStyleSheet(f"""
            QWidget#SettingsView {{
                background-color: {c["window"]};
                color: {c["text"]};
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QLabel {{
                color: {c["text"]};
                background: transparent;
                border: none;
            }}

            QLabel#PageTitle {{
                color: {c["text"]};
                font-size: 23px;
                font-weight: 700;
            }}

            QLabel#PageSubtitle,
            QLabel#SectionDescription,
            QLabel#MutedLabel {{
                color: {c["muted"]};
                font-size: 12px;
            }}

            QLabel#SectionTitle {{
                color: {c["text"]};
                font-size: 14px;
                font-weight: 700;
            }}

            QLabel#FieldLabel {{
                color: {c["text"]};
                font-size: 12px;
                font-weight: 600;
            }}

            QLabel#DangerTitle {{
                color: {c["danger"]};
                font-size: 14px;
                font-weight: 700;
            }}

            QFrame#SettingsCard,
            QFrame#SettingsActionBar {{
                background-color: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 10px;
            }}

            QFrame#InfoFrame {{
                background-color: {c["surface_alt"]};
                border: 1px solid {c["border"]};
                border-radius: 8px;
            }}

            QFrame#DangerFrame {{
                background-color: {c["surface_alt"]};
                border: 1px solid {c["danger"]};
                border-radius: 8px;
            }}

            QFrame#SettingsSeparator {{
                color: {c["border"]};
            }}

            QPushButton {{
                color: {c["text"]};
                font-size: 12px;
                font-weight: 600;
                border-radius: 7px;
                padding: 8px 13px;
            }}

            QPushButton#PrimaryButton {{
                background-color: {c["primary"]};
                color: white;
                border: none;
            }}

            QPushButton#PrimaryButton:hover {{
                background-color: {c["primary_hover"]};
            }}

            QPushButton#SecondaryButton,
            QPushButton#SmallButton {{
                background-color: {c["surface_alt"]};
                border: 1px solid {c["border"]};
            }}

            QPushButton#SecondaryButton:hover,
            QPushButton#SmallButton:hover {{
                border-color: {c["primary"]};
            }}

            QPushButton#DangerButton {{
                background-color: {c["danger"]};
                color: white;
                border: none;
            }}

            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 7px 10px;
                font-size: 12px;
            }}

            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus {{
                border-color: {c["primary"]};
            }}
        """)

    def apply_selected_theme(self, theme_name):
        manager = self._theme_manager or self.get_theme_manager()
        self._theme_manager = manager

        if not manager:
            return False

        try:
            manager.set_theme(theme_name)
            return True

        except Exception as error:
            QMessageBox.warning(
                self,
                "Theme Error",
                f"Unable to change application theme:\n\n{error}"
            )
            return False

    def on_global_theme_changed(self, theme_name):
        self.apply_theme()
        self.update_theme_description()

    def on_theme_changed(self, theme_name):
        if self._loading_settings:
            return

        self.apply_selected_theme(theme_name)
        self.update_theme_description()

    def update_theme_description(self):
        theme = self.combo_theme.currentText()

        descriptions = {
            "Dark": "Dark appearance is selected.",
            "Light": "Light appearance is selected.",
            "System": "The application follows the system theme.",
        }

        self.theme_description.setText(
            descriptions.get(
                theme,
                "Configure the application appearance."
            )
        )

    # =========================================================
    # UI HELPERS
    # =========================================================

    def create_card_frame(self, object_name="SettingsCard"):
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        return frame

    def create_section_header(self, title, description=""):
        wrapper = QWidget()
        wrapper.setObjectName("SettingsSectionHeader")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 8, 0, 3)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")

        layout.addWidget(title_label)

        if description:
            desc = QLabel(description)
            desc.setObjectName("SectionDescription")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        return wrapper

    def create_info_frame(self, text):
        frame = QFrame()
        frame.setObjectName("InfoFrame")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(13, 11, 13, 11)

        label = QLabel(text)
        label.setObjectName("MutedLabel")
        label.setWordWrap(True)

        layout.addWidget(label)
        return frame

    def create_field_label(self, text):
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def create_button(self, text, object_name="SecondaryButton"):
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(40)
        return button

    def create_password_field(self, placeholder):
        field = QLineEdit()
        field.setObjectName("PasswordField")
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setMinimumHeight(40)
        field.setClearButtonEnabled(True)
        return field

    def create_password_row(self, label_text, placeholder):
        wrapper = QWidget()

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        label = self.create_field_label(label_text)
        label.setMinimumWidth(155)

        field = self.create_password_field(placeholder)

        toggle = self.create_button("Show", "SmallButton")
        toggle.setCheckable(True)
        toggle.setMinimumWidth(65)

        def toggle_visibility(visible):
            field.setEchoMode(
                QLineEdit.EchoMode.Normal
                if visible
                else QLineEdit.EchoMode.Password
            )

            toggle.setText("Hide" if visible else "Show")

        toggle.toggled.connect(toggle_visibility)

        layout.addWidget(label)
        layout.addWidget(field, 1)
        layout.addWidget(toggle)

        return wrapper, field

    def create_separator(self):
        line = QFrame()
        line.setObjectName("SettingsSeparator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        return line

    # =========================================================
    # MAIN INTERFACE
    # =========================================================

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header
        header = QHBoxLayout()

        title_group = QVBoxLayout()
        title_group.setSpacing(2)

        title = QLabel("Settings & Configuration")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Manage application preferences, circulation policies, "
            "academic records, security and database maintenance."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        header.addLayout(title_group)
        header.addStretch()

        main_layout.addLayout(header)

        # Scrollable content
        self.scroll = QScrollArea()
        self.scroll.setObjectName("SettingsScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.container = QWidget()
        self.container.setObjectName("SettingsContainer")

        self.content_layout = QVBoxLayout(self.container)
        self.content_layout.setContentsMargins(2, 5, 12, 15)
        self.content_layout.setSpacing(12)

        self.build_department_section()
        self.build_rollover_section()
        self.build_appearance_section()
        self.build_circulation_section()
        self.build_database_section()
        self.build_security_section()

        self.content_layout.addStretch()

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll, 1)

        # Action bar
        action_frame = self.create_card_frame("SettingsActionBar")

        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(15, 12, 15, 12)
        action_layout.setSpacing(10)

        self.btn_reset = self.create_button(
            "Reset Defaults",
            "SecondaryButton"
        )
        self.btn_reset.clicked.connect(self.reset_defaults)

        self.btn_save = self.create_button(
            "Save All Settings",
            "PrimaryButton"
        )
        self.btn_save.clicked.connect(self.save_settings)

        action_layout.addWidget(self.btn_reset)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_save)

        main_layout.addWidget(action_frame)

    # =========================================================
    # 1. DEPARTMENT MANAGEMENT
    # =========================================================

    def build_department_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Academic Departments",
                "Manage the academic branches and departments "
                "available in your institution."
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(12)

        layout.addWidget(
            self.create_info_frame(
                "Add, edit and remove academic departments. "
                "Department changes are managed separately from "
                "general application settings."
            )
        )

        self.btn_manage_depts = self.create_button(
            "Manage Departments",
            "PrimaryButton"
        )
        self.btn_manage_depts.clicked.connect(
            self.open_department_manager
        )

        layout.addWidget(self.btn_manage_depts)
        self.content_layout.addWidget(card)

    # =========================================================
    # 2. ACADEMIC ROLLOVER
    # =========================================================

    def build_rollover_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Academic Year Rollover",
                "Archive graduating students and remove eligible "
                "records from the active database."
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(13)

        layout.addWidget(
            self.create_info_frame(
                "This operation exports graduating student records "
                "to a CSV archive before removing eligible records "
                "from the active database."
            )
        )

        self.chk_skip_active = QCheckBox(
            "Skip students who currently have active loans"
        )
        self.chk_skip_active.setChecked(True)

        layout.addWidget(self.chk_skip_active)

        self.btn_archive_batch = self.create_button(
            "Export & Clear Graduating Batch",
            "SecondaryButton"
        )
        self.btn_archive_batch.clicked.connect(
            self.handle_batch_rollover_action
        )

        layout.addWidget(self.btn_archive_batch)
        self.content_layout.addWidget(card)

    # =========================================================
    # 3. APPEARANCE
    # =========================================================

    def build_appearance_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Appearance & Interface",
                "Configure the visual appearance of the application."
            )
        )

        card = self.create_card_frame()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(15)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        label = self.create_field_label("Application Theme")

        self.theme_description = QLabel(
            "Choose the appearance used throughout the application."
        )
        self.theme_description.setObjectName("MutedLabel")
        self.theme_description.setWordWrap(True)

        text_layout.addWidget(label)
        text_layout.addWidget(self.theme_description)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(self.THEMES)
        self.combo_theme.setMinimumWidth(180)
        self.combo_theme.setMinimumHeight(40)
        self.combo_theme.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.combo_theme.currentTextChanged.connect(
            self.on_theme_changed
        )

        layout.addLayout(text_layout, 1)
        layout.addWidget(self.combo_theme)

        self.content_layout.addWidget(card)

    # =========================================================
    # 4. CIRCULATION POLICIES
    # =========================================================

    def build_circulation_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Circulation Policies",
                "Configure borrowing duration and overdue fine calculation."
            )
        )

        card = self.create_card_frame()
        layout = QGridLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setHorizontalSpacing(22)
        layout.setVerticalSpacing(13)

        fine_label = self.create_field_label("Daily Overdue Fine")

        self.spin_daily_fine = QDoubleSpinBox()
        self.spin_daily_fine.setRange(0, 1000)
        self.spin_daily_fine.setDecimals(2)
        self.spin_daily_fine.setSingleStep(0.50)
        self.spin_daily_fine.setPrefix("₹ ")
        self.spin_daily_fine.setMinimumHeight(40)

        fine_description = QLabel(
            "Amount charged for each overdue day."
        )
        fine_description.setObjectName("MutedLabel")

        days_label = self.create_field_label("Default Loan Duration")

        self.spin_default_days = QSpinBox()
        self.spin_default_days.setRange(1, 365)
        self.spin_default_days.setSuffix(" days")
        self.spin_default_days.setMinimumHeight(40)

        days_description = QLabel(
            "Default number of days allowed for borrowing."
        )
        days_description.setObjectName("MutedLabel")

        layout.addWidget(fine_label, 0, 0)
        layout.addWidget(days_label, 0, 1)

        layout.addWidget(self.spin_daily_fine, 1, 0)
        layout.addWidget(self.spin_default_days, 1, 1)

        layout.addWidget(fine_description, 2, 0)
        layout.addWidget(days_description, 2, 1)

        self.content_layout.addWidget(card)

    # =========================================================
    # 5. DATABASE MAINTENANCE
    # =========================================================

    def build_database_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Database Maintenance",
                "Back up your library database and manage circulation logs."
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(15)

        backup_row = QHBoxLayout()
        backup_row.setSpacing(15)

        backup_text = QVBoxLayout()
        backup_text.setSpacing(5)

        backup_title = self.create_field_label("Database Backup")

        backup_desc = QLabel(
            "Create an independent copy of the current SQLite database."
        )
        backup_desc.setObjectName("MutedLabel")
        backup_desc.setWordWrap(True)

        backup_text.addWidget(backup_title)
        backup_text.addWidget(backup_desc)

        self.db_backup_btn = self.create_button(
            "Create Backup",
            "SecondaryButton"
        )
        self.db_backup_btn.clicked.connect(self.database_backup)

        backup_row.addLayout(backup_text, 1)
        backup_row.addWidget(self.db_backup_btn)

        layout.addLayout(backup_row)
        layout.addWidget(self.create_separator())

        danger_frame = self.create_card_frame("DangerFrame")

        danger_layout = QVBoxLayout(danger_frame)
        danger_layout.setContentsMargins(14, 13, 14, 13)
        danger_layout.setSpacing(10)

        danger_title = QLabel("Danger Zone")
        danger_title.setObjectName("DangerTitle")

        danger_desc = QLabel(
            "Permanently delete all circulation activity logs. "
            "This operation cannot be undone."
        )
        danger_desc.setWordWrap(True)
        danger_desc.setObjectName("MutedLabel")

        self.clear_logs_btn = self.create_button(
            "Clear All Circulation Logs",
            "DangerButton"
        )
        self.clear_logs_btn.clicked.connect(self.clear_all_logs)

        danger_layout.addWidget(danger_title)
        danger_layout.addWidget(danger_desc)
        danger_layout.addWidget(self.clear_logs_btn)

        layout.addWidget(danger_frame)
        self.content_layout.addWidget(card)

    # =========================================================
    # 6. ADMINISTRATOR SECURITY
    # =========================================================

    def build_security_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Administrator Security",
                "Update the administrator password used for "
                "protected system operations."
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(13)

        layout.addWidget(
            self.create_info_frame(
                "Leave all password fields empty if you do not "
                "want to change the administrator password."
            )
        )

        current_row, self.input_cur_psw = self.create_password_row(
            "Current Password",
            "Enter current administrator password"
        )

        new_row, self.input_new_psw = self.create_password_row(
            "New Password",
            "Enter new password"
        )

        confirm_row, self.input_con_psw = self.create_password_row(
            "Confirm Password",
            "Re-enter new password"
        )

        layout.addWidget(current_row)
        layout.addWidget(new_row)
        layout.addWidget(confirm_row)

        self.content_layout.addWidget(card)

    # =========================================================
    # DEPARTMENT MANAGER
    # =========================================================

    def open_department_manager(self):
        try:
            dialog = DepartmentManagerDialog(self.db, self)
            dialog.exec()

        except Exception as error:
            QMessageBox.critical(
                self,
                "Department Manager Error",
                f"Unable to open department manager:\n\n{error}"
            )

    # =========================================================
    # LOAD SETTINGS
    # =========================================================

    def load_settings(self):
        self._loading_settings = True

        try:
            fine = self.db.get_setting(
                "daily_fine",
                self.DEFAULTS["daily_fine"]
            )

            days = self.db.get_setting(
                "default_days",
                self.DEFAULTS["default_days"]
            )

            theme = self.db.get_setting(
                "theme_mode",
                self.DEFAULTS["theme_mode"]
            )

            fine = float(fine)
            days = int(days)

            legacy_themes = {
                "Dark Slate (Default)": "Dark",
                "Classic Dark": "Dark",
                "Light Modern": "Light",
            }

            theme = legacy_themes.get(theme, theme)

            if theme not in self.THEMES:
                theme = self.DEFAULTS["theme_mode"]

            self.spin_daily_fine.setValue(fine)
            self.spin_default_days.setValue(days)
            self.combo_theme.setCurrentText(theme)

        except Exception as error:
            QMessageBox.warning(
                self,
                "Settings Loading Error",
                f"Some settings could not be loaded:\n\n{error}"
            )

        finally:
            self._loading_settings = False

        self.update_theme_description()
        self.apply_selected_theme(self.combo_theme.currentText())

    # =========================================================
    # ADMINISTRATOR AUTHORIZATION
    # =========================================================

    def verify_admin_password(self, title, message):
        password, ok = QInputDialog.getText(
            self,
            title,
            message,
            QLineEdit.EchoMode.Password
        )

        if not ok:
            return False

        try:
            stored_password = self.db.get_setting(
                "admin_password",
                "admin123"
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Authorization Error",
                f"Unable to verify administrator credentials:\n\n{error}"
            )
            return False

        if password != str(stored_password):
            QMessageBox.warning(
                self,
                "Access Denied",
                "Incorrect administrator password."
            )
            return False

        return True

    # =========================================================
    # ACADEMIC ROLLOVER
    # =========================================================

    def handle_batch_rollover_action(self):
        if not self.verify_admin_password(
            "Administrator Authorization",
            "Enter the administrator password:"
        ):
            return

        current_year = datetime.date.today().year
        graduating_batch = current_year - 3

        skip_active = self.chk_skip_active.isChecked()

        confirm = QMessageBox.warning(
            self,
            "Confirm Academic Rollover",
            (
                f"Graduating batch: {graduating_batch}\n\n"
                "This operation will export graduating student "
                "records and remove eligible records from the "
                "active database.\n\n"
                f"Students with active loans will "
                f"{'be skipped' if skip_active else 'not be skipped'}.\n\n"
                "Create a database backup before continuing.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Archive Destination"
        )

        if not folder_path:
            return

        self.btn_archive_batch.setEnabled(False)

        try:
            success, count, message = (
                self.db.export_and_delete_final_year_students(
                    folder_path,
                    skip_active_loans=skip_active
                )
            )

            if success:
                filename = (
                    f"Graduated_Batch_{graduating_batch}_Archive.csv"
                )

                QMessageBox.information(
                    self,
                    "Rollover Completed",
                    (
                        f"{message}\n\n"
                        f"Archived records: {count}\n"
                        f"Archive file: {filename}\n"
                        f"Destination: {folder_path}"
                    )
                )

            else:
                QMessageBox.warning(
                    self,
                    "Rollover Not Completed",
                    str(message)
                )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Rollover Error",
                f"Academic rollover failed:\n\n{error}"
            )

        finally:
            self.btn_archive_batch.setEnabled(True)

    # =========================================================
    # DATABASE BACKUP
    # =========================================================

    def database_backup(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create Database Backup",
            "library_backup.db",
            "SQLite Database (*.db);;All Files (*)"
        )

        if not file_path:
            return

        source_conn = getattr(self.db, "conn", None)

        if source_conn is None:
            QMessageBox.critical(
                self,
                "Backup Failed",
                "The active database connection is unavailable."
            )
            return

        absolute_path = os.path.abspath(file_path)

        source_database = getattr(self.db, "db_path", None)

        if source_database:
            try:
                if os.path.samefile(
                    absolute_path,
                    os.path.abspath(str(source_database))
                ):
                    QMessageBox.warning(
                        self,
                        "Invalid Backup Location",
                        "The backup destination cannot be the active database."
                    )
                    return
            except (OSError, ValueError):
                pass

        if os.path.exists(absolute_path):
            confirm = QMessageBox.question(
                self,
                "Overwrite Backup",
                "A file already exists at this location.\n\nReplace it?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if confirm != QMessageBox.StandardButton.Yes:
                return

        destination_conn = None

        try:
            destination_conn = sqlite3.connect(absolute_path)

            source_conn.backup(destination_conn)
            destination_conn.commit()

            result = destination_conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError(
                    "The backup integrity check failed."
                )

            QMessageBox.information(
                self,
                "Backup Successful",
                (
                    "Database backup created and verified successfully.\n\n"
                    f"Saved to:\n{absolute_path}"
                )
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Backup Failed",
                f"Unable to create database backup:\n\n{error}"
            )

        finally:
            if destination_conn:
                destination_conn.close()

    # =========================================================
    # CLEAR CIRCULATION LOGS
    # =========================================================

    def clear_all_logs(self):
        if not self.verify_admin_password(
            "Administrator Authorization",
            "Enter the administrator password:"
        ):
            return

        confirm = QMessageBox.warning(
            self,
            "Permanent Deletion",
            (
                "You are about to permanently delete all "
                "circulation activity logs.\n\n"
                "This operation cannot be undone.\n\n"
                "Create a database backup before continuing.\n\n"
                "Are you absolutely sure?"
            ),
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.clear_logs_btn.setEnabled(False)

        try:
            success, message = self.db.clear_all_logs()

            if success:
                QMessageBox.information(
                    self,
                    "Logs Cleared",
                    str(message)
                )
            else:
                QMessageBox.warning(
                    self,
                    "Deletion Failed",
                    str(message)
                )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Unable to clear circulation logs:\n\n{error}"
            )

        finally:
            self.clear_logs_btn.setEnabled(True)

    # =========================================================
    # RESET DEFAULTS
    # =========================================================

    def reset_defaults(self):
        confirm = QMessageBox.question(
            self,
            "Reset Application Settings",
            (
                "Restore the default circulation and appearance settings?\n\n"
                "This will not delete books, users or circulation logs.\n\n"
                "Click Save All Settings to persist the changes."
            ),
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.spin_daily_fine.setValue(
            self.DEFAULTS["daily_fine"]
        )

        self.spin_default_days.setValue(
            self.DEFAULTS["default_days"]
        )

        self.chk_skip_active.setChecked(True)

        blocker = QSignalBlocker(self.combo_theme)
        self.combo_theme.setCurrentText(
            self.DEFAULTS["theme_mode"]
        )
        del blocker

        self.apply_selected_theme(
            self.DEFAULTS["theme_mode"]
        )

        self.update_theme_description()

        self.input_cur_psw.clear()
        self.input_new_psw.clear()
        self.input_con_psw.clear()

        QMessageBox.information(
            self,
            "Defaults Restored",
            (
                "Default values have been restored in the interface.\n\n"
                "Click Save All Settings to save them permanently."
            )
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate_settings(self):
        fine = self.spin_daily_fine.value()
        days = self.spin_default_days.value()
        theme = self.combo_theme.currentText()

        if fine < 0:
            QMessageBox.warning(
                self,
                "Invalid Fine",
                "The daily overdue fine cannot be negative."
            )
            return False

        if not 1 <= days <= 365:
            QMessageBox.warning(
                self,
                "Invalid Loan Duration",
                "The loan duration must be between 1 and 365 days."
            )
            return False

        if theme not in self.THEMES:
            QMessageBox.warning(
                self,
                "Invalid Theme",
                "Select a valid application theme."
            )
            return False

        return True

    def validate_password_change(self):
        current_password = self.input_cur_psw.text()
        new_password = self.input_new_psw.text()
        confirm_password = self.input_con_psw.text()

        if not any((
            current_password,
            new_password,
            confirm_password
        )):
            return True

        if not all((
            current_password,
            new_password,
            confirm_password
        )):
            QMessageBox.warning(
                self,
                "Incomplete Password Details",
                "Complete all three password fields."
            )
            return False

        if new_password != confirm_password:
            QMessageBox.warning(
                self,
                "Password Mismatch",
                "The new password and confirmation do not match."
            )
            return False

        if len(new_password) < 8:
            QMessageBox.warning(
                self,
                "Weak Password",
                "The new password must contain at least 8 characters."
            )
            return False

        try:
            stored_password = self.db.get_setting(
                "admin_password",
                "admin123"
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Password Verification Error",
                str(error)
            )
            return False

        if current_password != str(stored_password):
            QMessageBox.warning(
                self,
                "Incorrect Password",
                "The current administrator password is incorrect."
            )
            return False

        return True

    # =========================================================
    # SAVE SETTINGS
    # =========================================================

    def save_settings(self):
        if self._saving_settings:
            return

        if not self.validate_settings():
            return

        if not self.validate_password_change():
            return

        self._saving_settings = True
        self.btn_save.setEnabled(False)

        try:
            self.db.set_setting(
                "daily_fine",
                self.spin_daily_fine.value()
            )

            self.db.set_setting(
                "default_days",
                self.spin_default_days.value()
            )

            theme_name = self.combo_theme.currentText()

            self.db.set_setting(
                "theme_mode",
                theme_name
            )

            new_password = self.input_new_psw.text()

            if new_password:
                self.db.set_setting(
                    "admin_password",
                    new_password
                )

            self.apply_selected_theme(theme_name)
            self.update_theme_description()

            self.input_cur_psw.clear()
            self.input_new_psw.clear()
            self.input_con_psw.clear()

            QMessageBox.information(
                self,
                "Settings Saved",
                "Application settings have been saved successfully."
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Save Failed",
                (
                    "Unable to save all settings.\n\n"
                    f"Error: {error}\n\n"
                    "Check your saved settings before retrying."
                )
            )

        finally:
            self._saving_settings = False
            self.btn_save.setEnabled(True)

    # =========================================================
    # CLEANUP
    # =========================================================

    def closeEvent(self, event):
        manager = self._theme_manager

        if manager:
            signal = getattr(manager, "themeChanged", None)

            if signal:
                try:
                    signal.disconnect(self.on_global_theme_changed)
                except (TypeError, RuntimeError):
                    pass

        super().closeEvent(event)
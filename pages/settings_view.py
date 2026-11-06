import os
import sqlite3
import datetime
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSignalBlocker, QThreadPool, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QFileDialog,
    QMessageBox, QDoubleSpinBox, QSpinBox, QComboBox,
    QScrollArea, QFrame, QInputDialog, QApplication,
    QGridLayout, QSizePolicy, QProgressBar
)

from dialogs import (
    DepartmentManagerDialog,
    EmailQueueManagementDialog,
    RecoveryCodeSetupDialog,
    VersionManagerDialog,
)
from email_queue import EmailTestWorker
from email_service import SMTP_CREDENTIAL_TARGET
from secure_storage import delete_secret, store_secret
from app_version import get_app_version
from update_service import (
    PACKAGE_NAME,
    RELEASES_PAGE_URL,
    UpdateCheckWorker,
    UpdateDownloadWorker,
    VersionHistoryWorker,
    can_replace_application,
    is_packaged_application,
    is_newer_version,
    schedule_application_update,
)


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
        self._update_pool = QThreadPool(self)
        self._update_worker = None
        self._pending_update = None
        self._email_test_worker = None

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
        main_layout.setContentsMargins(20, 16, 20, 16)
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
        self.build_email_section()
        self.build_update_section()
        self.build_database_section()
        self.build_cloud_backup_section()
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
            "Skip students with issued books"
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

    def build_email_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Email Notifications & Complaints",
                "Send due-date reminders to users and forward submitted "
                "complaints to the library contact. Pause delivery and review "
                "or remove queued messages at any time.",
            )
        )

        card = self.create_card_frame()
        layout = QGridLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)

        self.email_sender_input = QLineEdit()
        self.email_sender_input.setPlaceholderText(
            "Gmail address used to send messages"
        )
        self.library_contact_input = QLineEdit()
        self.library_contact_input.setPlaceholderText(
            "Library inbox for complaints"
        )
        self.smtp_app_password_input = QLineEdit()
        self.smtp_app_password_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.smtp_app_password_input.setPlaceholderText(
            "Gmail app password (saved in Windows Credential Manager)"
        )

        layout.addWidget(self.create_field_label("Gmail sender"), 0, 0)
        layout.addWidget(self.create_field_label("Library contact"), 0, 1)
        layout.addWidget(self.email_sender_input, 1, 0)
        layout.addWidget(self.library_contact_input, 1, 1)
        layout.addWidget(
            self.create_field_label("Gmail app password"),
            2,
            0,
            1,
            2,
        )
        layout.addWidget(self.smtp_app_password_input, 3, 0, 1, 2)

        actions = QHBoxLayout()
        self.save_email_btn = self.create_button(
            "Save Email Settings",
            "SecondaryButton",
        )
        self.save_email_btn.clicked.connect(self.save_email_settings)
        self.test_email_btn = self.create_button(
            "Send Test Email",
            "SecondaryButton",
        )
        self.test_email_btn.clicked.connect(self.send_test_email)
        self.clear_email_secret_btn = self.create_button(
            "Remove Saved App Password",
            "SecondaryButton",
        )
        self.clear_email_secret_btn.clicked.connect(
            self.remove_email_secret
        )

        actions.addWidget(self.save_email_btn)
        actions.addWidget(self.test_email_btn)
        actions.addWidget(self.clear_email_secret_btn)
        actions.addStretch()
        layout.addLayout(actions, 4, 0, 1, 2)

        self.email_reminders_checkbox = QCheckBox(
            "Send one reminder on the due date and one when a loan becomes overdue"
        )
        self.email_delivery_checkbox = QCheckBox(
            "Enable sending queued emails to recipient addresses"
        )
        self.email_delivery_checkbox.setToolTip(
            "Only enable after confirming all queued recipient addresses are "
            "real and intended. Fake test-user addresses will fail delivery."
        )
        self.email_delivery_checkbox.toggled.connect(
            self.set_email_delivery_enabled
        )
        layout.addWidget(
            self.email_delivery_checkbox,
            5,
            0,
            1,
            2,
        )
        layout.addWidget(
            self.email_reminders_checkbox,
            6,
            0,
            1,
            2,
        )

        queue_actions = QHBoxLayout()
        self.email_queue_status = QLabel("Email queue status unavailable")
        self.email_queue_status.setObjectName("MutedLabel")
        self.sync_email_btn = self.create_button(
            "Sync Now",
            "SecondaryButton",
        )
        self.sync_email_btn.setEnabled(
            self.email_delivery_checkbox.isChecked()
        )
        self.sync_email_btn.clicked.connect(self.sync_email_queue)
        self.manage_email_queue_btn = self.create_button(
            "Manage Queue",
            "SecondaryButton",
        )
        self.manage_email_queue_btn.clicked.connect(
            self.manage_email_queue
        )
        queue_actions.addWidget(self.email_queue_status, 1)
        queue_actions.addWidget(self.manage_email_queue_btn)
        queue_actions.addWidget(self.sync_email_btn)
        layout.addLayout(queue_actions, 7, 0, 1, 2)

        app = QApplication.instance()
        self._email_sync_manager = (
            getattr(app, "email_sync_manager", None) if app else None
        )
        if self._email_sync_manager:
            self._email_sync_manager.status_changed.connect(
                self.email_queue_status.setText
            )
            self._email_sync_manager.refresh_status()

        self.content_layout.addWidget(card)

    def sync_email_queue(self):
        manager = self._email_sync_manager
        if manager:
            manager.retry_failed_now()
        else:
            QMessageBox.warning(
                self,
                "Email Sync Unavailable",
                "The background email service is not available.",
            )

    def manage_email_queue(self):
        dialog = EmailQueueManagementDialog(self.db, self)
        dialog.exec()
        if self._email_sync_manager:
            self._email_sync_manager.refresh_status()

    def build_update_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Application Updates",
                "Check for a newer Windows build and update from within "
                "the application.",
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(10)

        description = QLabel(
            f"Installed version: {get_app_version()}. Update checks use the "
            "official GitHub Releases page. A downloaded update is "
            "validated and applied after you confirm; the application "
            "will close and restart."
        )
        description.setObjectName("MutedLabel")
        description.setWordWrap(True)
        layout.addWidget(description)

        actions = QHBoxLayout()
        self.update_status_label = QLabel("Ready to check for updates")
        self.update_status_label.setObjectName("MutedLabel")
        self.update_button = self.create_button(
            "Check for Updates",
            "SecondaryButton",
        )
        self.update_button.clicked.connect(self.check_for_updates)
        actions.addWidget(self.update_status_label, 1)
        actions.addWidget(self.update_button)
        self.manage_versions_button = self.create_button(
            "Manage Versions",
            "SecondaryButton",
        )
        self.manage_versions_button.clicked.connect(
            self.manage_application_versions
        )
        actions.addWidget(self.manage_versions_button)
        layout.addLayout(actions)

        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        self.update_progress_bar.setTextVisible(True)
        self.update_progress_bar.hide()
        layout.addWidget(self.update_progress_bar)

        self.content_layout.addWidget(card)

    def check_for_updates(self):
        if self._update_worker is not None:
            return

        self.update_button.setEnabled(False)
        self.update_status_label.setText("Checking for updates...")
        worker = UpdateCheckWorker()
        worker.signals.finished.connect(
            self._on_update_check_finished
        )
        self._update_worker = worker
        self._update_pool.start(worker)

    def manage_application_versions(self):
        if self._update_worker is not None:
            return
        if not self.verify_admin_password(
            "Administrator Authorization",
            "Enter the administrator password to manage application versions:",
        ):
            return

        self.update_button.setEnabled(False)
        self.manage_versions_button.setEnabled(False)
        self.update_status_label.setText("Loading published versions...")
        worker = VersionHistoryWorker()
        worker.signals.finished.connect(
            self._on_version_history_finished
        )
        self._update_worker = worker
        self._update_pool.start(worker)

    def _on_version_history_finished(self, result):
        self._update_worker = None
        self.update_button.setEnabled(True)
        self.manage_versions_button.setEnabled(True)
        if result.get("error"):
            self.update_status_label.setText(
                "Could not load published versions"
            )
            QMessageBox.warning(
                self,
                "Version History Failed",
                f"Could not load published versions:\n{result['error']}",
            )
            return

        can_install = is_packaged_application() and can_replace_application(
            Path(sys.executable).resolve().parent
        )
        dialog = VersionManagerDialog(
            result.get("releases", []),
            result.get("current_version", get_app_version()),
            can_install,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.update_status_label.setText(
                f"Installed version: v{get_app_version()}"
            )
            return

        selected_release = dialog.selected_release
        if selected_release:
            self._on_update_check_finished(selected_release)

    def _on_update_check_finished(self, result):
        self._update_worker = None
        self.update_button.setEnabled(True)

        if result.get("error"):
            self.update_status_label.setText("Update check failed")
            QMessageBox.warning(
                self,
                "Update Check Failed",
                f"Could not check for updates:\n{result['error']}",
            )
            return

        if result.get("release_not_published"):
            self.update_status_label.setText(
                "No published update is available"
            )
            message = QMessageBox(self)
            message.setWindowTitle("No Published Update")
            message.setIcon(QMessageBox.Icon.Information)
            message.setText(
                "GitHub has no published stable release for this app yet. "
                "The updater can check again after a release is published "
                f"with the {PACKAGE_NAME} package."
            )
            open_releases = message.addButton(
                "Open GitHub Releases",
                QMessageBox.ButtonRole.AcceptRole,
            )
            message.addButton(
                QMessageBox.StandardButton.Close
            )
            message.exec()
            if message.clickedButton() is open_releases:
                QDesktopServices.openUrl(QUrl(RELEASES_PAGE_URL))
            return

        current_version = get_app_version()
        latest_version = result.get("latest_version", current_version)
        if not result.get("available"):
            self.update_status_label.setText(
                f"You are up to date (v{current_version})"
            )
            QMessageBox.information(
                self,
                "No Updates Available",
                f"You are running the latest version ({current_version}).",
            )
            return

        self.update_status_label.setText(
            f"Update available: v{latest_version}"
        )
        if not is_packaged_application():
            self.update_status_label.setText(
                f"Update available: v{latest_version} "
                "(packaged Windows app required)"
            )
            QMessageBox.information(
                self,
                "Update Available",
                "A newer release is available. Automatic replacement "
                "works only in the packaged Windows application.",
            )
            return

        if not can_replace_application(
            Path(sys.executable).resolve().parent
        ):
            QMessageBox.warning(
                self,
                "Update Permission Required",
                "Windows does not allow this account to replace the "
                "application files. Reinstall the application in a "
                "writable user folder before updating.",
            )
            return

        notes = result.get("release_notes", "").strip()
        if result.get("version_selection"):
            action = (
                "upgrade to"
                if is_newer_version(latest_version, current_version)
                else "roll back to"
            )
            message = (
                f"Version {latest_version} is selected. Do you want to "
                f"{action} this release? The application will close and "
                "restart."
            )
        else:
            message = (
                f"Version {latest_version} is available.\n\n"
                "Install it now? The application will close and restart."
            )
        if notes:
            message += f"\n\nRelease notes:\n{notes[:2500]}"

        answer = QMessageBox.question(
            self,
            "Application Update Available",
            message,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.update_status_label.setText(
                f"Update available: v{latest_version}"
            )
            return

        self._pending_update = result
        self.update_button.setEnabled(False)
        self.update_status_label.setText("Downloading update...")
        self.update_progress_bar.setRange(0, 0)
        self.update_progress_bar.show()
        worker = UpdateDownloadWorker(result)
        worker.signals.progress.connect(
            self._on_update_progress
        )
        worker.signals.finished.connect(
            self._on_update_download_finished
        )
        self._update_worker = worker
        self._update_pool.start(worker)

    def _on_update_progress(self, progress):
        if self.update_progress_bar.minimum() != 0:
            return
        if self.update_progress_bar.maximum() == 0:
            self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(progress)

    def _on_update_download_finished(self, result):
        self._update_worker = None
        self.update_progress_bar.hide()
        self.update_button.setEnabled(True)

        if result.get("error"):
            self._pending_update = None
            self.update_status_label.setText("Update download failed")
            QMessageBox.warning(
                self,
                "Update Download Failed",
                f"The update was not applied:\n{result['error']}",
            )
            return

        staged_path = result["staged_path"]
        try:
            schedule_application_update(staged_path)
        except Exception as error:
            shutil.rmtree(
                Path(staged_path).parent,
                ignore_errors=True,
            )
            self._pending_update = None
            self.update_status_label.setText("Update could not be applied")
            QMessageBox.critical(
                self,
                "Update Could Not Be Applied",
                str(error),
            )
            return

        latest_version = (
            self._pending_update.get("latest_version", "new version")
            if self._pending_update
            else "new version"
        )
        self._pending_update = None
        self.update_status_label.setText(
            f"Installing v{latest_version} and restarting..."
        )
        application = QApplication.instance()
        if application:
            QTimer.singleShot(400, application.quit)

    def build_cloud_backup_section(self):
        self.content_layout.addWidget(
            self.create_section_header(
                "Encrypted Google Drive Backup",
                "Connect a Google account and upload an encrypted "
                "SQLite backup to its Drive.",
            )
        )

        card = self.create_card_frame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(10)

        description = QLabel(
            "The backup is encrypted before upload. Its encryption key "
            "is kept in this Windows account's Credential Manager; "
            "backups cannot be restored if that Windows profile and key "
            "are lost."
        )
        description.setObjectName("MutedLabel")
        description.setWordWrap(True)
        layout.addWidget(description)

        actions = QHBoxLayout()
        self.drive_backup_btn = self.create_button(
            "Back Up to Google Drive",
            "SecondaryButton",
        )
        self.drive_backup_btn.clicked.connect(
            self.backup_to_google_drive
        )
        actions.addWidget(self.drive_backup_btn)
        self.drive_restore_btn = self.create_button(
            "Restore Backup to a Separate File",
            "SecondaryButton",
        )
        self.drive_restore_btn.clicked.connect(
            self.restore_from_google_drive
        )
        actions.addWidget(self.drive_restore_btn)
        self.drive_key_btn = self.create_button(
            "Export Backup Recovery Key",
            "SecondaryButton",
        )
        self.drive_key_btn.clicked.connect(
            self.export_drive_recovery_key
        )
        actions.addWidget(self.drive_key_btn)
        self.auto_drive_backup_checkbox = QCheckBox(
            "Automatically upload one encrypted backup per day while the app is running"
        )
        self.save_drive_settings_btn = self.create_button(
            "Save Backup Settings",
            "SecondaryButton",
        )
        self.save_drive_settings_btn.clicked.connect(
            self.save_drive_backup_settings
        )
        layout.addWidget(self.auto_drive_backup_checkbox)
        layout.addWidget(self.save_drive_settings_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self.content_layout.addWidget(card)

    def save_email_settings(self, show_confirmation=True):
        sender = self.email_sender_input.text().strip().casefold()
        library_contact = (
            self.library_contact_input.text().strip().casefold()
        )
        for label, address in (
            ("Gmail sender", sender),
            ("Library contact", library_contact),
        ):
            if address and (
                "@" not in address
                or address.startswith("@")
                or "." not in address.rsplit("@", 1)[-1]
            ):
                QMessageBox.warning(
                    self,
                    "Invalid Email Address",
                    f"Enter a valid {label} email address.",
                )
                return False

        password = self.smtp_app_password_input.text().strip()
        try:
            if password:
                store_secret(
                    SMTP_CREDENTIAL_TARGET,
                    "".join(password.split()),
                    sender,
                )

            for key, value in (
                ("email_sender", sender),
                ("library_contact_email", library_contact),
                (
                    "due_email_reminders_enabled",
                    "1" if self.email_reminders_checkbox.isChecked() else "0",
                ),
            ):
                if not self.db.set_setting(key, value):
                    raise RuntimeError(f"Unable to save {key}.")

            self.smtp_app_password_input.clear()
            if show_confirmation:
                QMessageBox.information(
                    self,
                    "Email Settings Saved",
                    "Email settings saved. The app password is protected "
                    "by Windows Credential Manager.",
                )
            return True
        except Exception as error:
            QMessageBox.critical(
                self,
                "Email Settings Error",
                str(error),
            )
            return False

    def set_email_delivery_enabled(self, enabled):
        if self._loading_settings:
            return

        if enabled:
            try:
                counts = self.db.get_email_queue_counts()
                queued = counts["pending"] + counts["failed"]
            except Exception as error:
                self._set_email_delivery_checkbox(False)
                QMessageBox.critical(
                    self,
                    "Email Queue Unavailable",
                    str(error),
                )
                return

            if queued:
                queue_summary = (
                    f"{counts['pending']} pending and {counts['failed']} "
                    "failed email(s)"
                )
            else:
                queue_summary = "No emails are currently queued"

            answer = QMessageBox.warning(
                self,
                "Confirm Email Delivery",
                f"{queue_summary}. Enabling delivery allows these and future "
                "queued messages to be sent to their saved recipient "
                "addresses. Continue only if those addresses are real and "
                "intended; fake test-user addresses will fail delivery.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._set_email_delivery_checkbox(False)
                return

        try:
            if not self.db.set_setting(
                "email_delivery_enabled",
                "1" if enabled else "0",
            ):
                raise RuntimeError(
                    "Unable to save the email delivery setting."
                )
            self.sync_email_btn.setEnabled(enabled)
            if self._email_sync_manager:
                self._email_sync_manager.sync_now()
        except Exception as error:
            self._set_email_delivery_checkbox(not enabled)
            QMessageBox.critical(
                self,
                "Email Delivery Setting Error",
                str(error),
            )

    def _set_email_delivery_checkbox(self, enabled):
        self.email_delivery_checkbox.blockSignals(True)
        self.email_delivery_checkbox.setChecked(enabled)
        self.email_delivery_checkbox.blockSignals(False)
        if hasattr(self, "sync_email_btn"):
            self.sync_email_btn.setEnabled(enabled)

    def send_test_email(self):
        if not self.email_sender_input.text().strip():
            QMessageBox.warning(
                self,
                "Email Setup Required",
                "Enter the Gmail sender address first.",
            )
            return

        if self._email_test_worker is not None:
            return
        if not self.save_email_settings(show_confirmation=False):
            return

        worker = EmailTestWorker(self.db.database_path)
        worker.signals.finished.connect(
            self._on_test_email_finished
        )
        self._email_test_worker = worker
        self.test_email_btn.setEnabled(False)
        self.update_status_label_if_available(
            "Sending test email to the configured sender..."
        )
        QThreadPool.globalInstance().start(worker)

    def _on_test_email_finished(self, result):
        self._email_test_worker = None
        self.test_email_btn.setEnabled(True)
        if result.get("sent"):
            QMessageBox.information(
                self,
                "Test Email Sent",
                "The test email was sent directly to the configured Gmail "
                "sender. The queued user emails were not sent.",
            )
            return
        QMessageBox.warning(
            self,
            "Test Email Failed",
            f"The test email could not be sent:\n{result.get('error', 'Unknown error')}",
        )

    def update_status_label_if_available(self, message):
        if hasattr(self, "email_queue_status"):
            self.email_queue_status.setText(message)

    def remove_email_secret(self):
        answer = QMessageBox.question(
            self,
            "Remove App Password",
            "Remove the saved Gmail app password? Automated email "
            "notifications will stop until a new password is saved.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_secret(SMTP_CREDENTIAL_TARGET)
            QMessageBox.information(
                self,
                "App Password Removed",
                "The Gmail app password was removed from Windows "
                "Credential Manager.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Credential Error",
                str(error),
            )

    def backup_to_google_drive(self):
        client_secret_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Google OAuth Desktop Client JSON",
            "",
            "JSON Files (*.json);;All Files (*)",
        )

        try:
            from google_drive_backup import (
                upload_encrypted_database_backup,
            )

            result = upload_encrypted_database_backup(
                self.db,
                client_secret_file or None,
            )
            self.db.set_setting(
                "google_drive_last_backup",
                datetime.date.today().isoformat(),
            )
            QMessageBox.information(
                self,
                "Google Drive Backup Complete",
                f"Encrypted backup uploaded:\n{result.get('name', 'Library backup')}",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Google Drive Backup Failed",
                str(error),
            )

    def save_drive_backup_settings(self):
        try:
            if not self.db.set_setting(
                "google_drive_auto_backup_enabled",
                "1" if self.auto_drive_backup_checkbox.isChecked() else "0",
            ):
                raise RuntimeError("Unable to save Google Drive backup settings.")
            QMessageBox.information(
                self,
                "Backup Settings Saved",
                "Automatic backup settings were saved. Automatic uploads "
                "run once per day while the application is open and Drive "
                "has already been connected.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Backup Settings Error",
                str(error),
            )

    def restore_from_google_drive(self):
        client_secret_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Google OAuth Desktop Client JSON (or cancel if already connected)",
            "",
            "JSON Files (*.json);;All Files (*)",
        )

        try:
            from google_drive_backup import list_drive_backups

            backups = list_drive_backups(client_secret_file or None)
            if not backups:
                QMessageBox.information(
                    self,
                    "No Backups Found",
                    "No encrypted library backups were found in this Drive.",
                )
                return

            choices = [
                f"{item['name']}  ·  {item.get('createdTime', '')}"
                for item in backups
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                "Choose a Backup",
                "Google Drive backup:",
                choices,
                0,
                False,
            )
            if not accepted:
                return

            selected_index = choices.index(selected)
            backup = backups[selected_index]
            destination, _ = QFileDialog.getSaveFileName(
                self,
                "Restore Backup to a Separate File",
                str(os.path.expanduser("~/library_restored.db")),
                "SQLite Database (*.db)",
            )
            if not destination:
                return
            if not destination.lower().endswith(".db"):
                destination += ".db"

            recovery_key_file, _ = QFileDialog.getOpenFileName(
                self,
                "Select Backup Recovery Key (optional on this Windows account)",
                "",
                "Recovery Key (*.txt);;All Files (*)",
            )

            from google_drive_backup import download_and_decrypt_backup

            restored_path = download_and_decrypt_backup(
                backup["id"],
                destination,
                client_secret_file or None,
                recovery_key_file or None,
                getattr(self.db, "database_path", None),
            )
            QMessageBox.information(
                self,
                "Backup Restored",
                "The backup was downloaded, decrypted, and integrity-checked.\n\n"
                f"Restored database:\n{restored_path}\n\n"
                "The running application was not changed.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Google Drive Restore Failed",
                str(error),
            )

    def export_drive_recovery_key(self):
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Google Drive Backup Recovery Key",
            str(os.path.expanduser("~/library_backup_recovery_key.txt")),
            "Recovery Key (*.txt)",
        )
        if not destination:
            return
        if not destination.lower().endswith(".txt"):
            destination += ".txt"

        try:
            from google_drive_backup import export_backup_recovery_key

            export_backup_recovery_key(destination)
            QMessageBox.warning(
                self,
                "Protect Your Recovery Key",
                "The recovery key was exported. Keep it offline in a "
                "secure location separate from this computer and Google "
                "Drive. Anyone with both a backup and this key can read "
                "the database.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Recovery Key Export Failed",
                str(error),
            )

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

        self.btn_recovery_code = self.create_button(
            "Generate / Replace Recovery Code",
            "SecondaryButton",
        )
        self.btn_recovery_code.clicked.connect(
            self.generate_recovery_code
        )
        layout.addWidget(self.btn_recovery_code)

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
            email_sender = self.db.get_setting("email_sender", "")
            library_contact = self.db.get_setting(
                "library_contact_email",
                "",
            )
            reminders_enabled = self.db.get_setting(
                "due_email_reminders_enabled",
                "0",
            )
            email_delivery_enabled = self.db.get_setting(
                "email_delivery_enabled",
                "0",
            )
            auto_backup_enabled = self.db.get_setting(
                "google_drive_auto_backup_enabled",
                "0",
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
            self.email_sender_input.setText(email_sender or "")
            self.library_contact_input.setText(
                library_contact or ""
            )
            self.email_reminders_checkbox.setChecked(
                str(reminders_enabled).casefold()
                in ("1", "true", "yes")
            )
            self.email_delivery_checkbox.setChecked(
                str(email_delivery_enabled).casefold()
                in ("1", "true", "yes")
            )
            self.sync_email_btn.setEnabled(
                self.email_delivery_checkbox.isChecked()
            )
            self.auto_drive_backup_checkbox.setChecked(
                str(auto_backup_enabled).casefold()
                in ("1", "true", "yes")
            )

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
            valid_password = self.db.verify_admin_password(password)
        except Exception as error:
            QMessageBox.critical(
                self,
                "Authorization Error",
                f"Unable to verify administrator credentials:\n\n{error}"
            )
            return False

        if not valid_password:
            QMessageBox.warning(
                self,
                "Access Denied",
                "Incorrect administrator password."
            )
            return False

        return True

    def generate_recovery_code(self):
        if not self.verify_admin_password(
            "Administrator Authorization",
            "Enter the current administrator password to replace "
            "the recovery code:"
        ):
            return

        dialog = RecoveryCodeSetupDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            if not self.db.set_admin_recovery_code(
                dialog.recovery_code
            ):
                raise RuntimeError("The recovery code could not be saved.")

            QMessageBox.information(
                self,
                "Recovery Code Saved",
                "The new recovery code is active. The previous code "
                "can no longer be used.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Recovery Code Error",
                f"Unable to save the recovery code:\n\n{error}",
            )

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
                f"Students with issued books will "
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
            valid_password = self.db.verify_admin_password(
                current_password
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Password Verification Error",
                str(error)
            )
            return False

        if not valid_password:
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

            self.db.set_setting(
                "due_email_reminders_enabled",
                "1" if self.email_reminders_checkbox.isChecked() else "0",
            )

            new_password = self.input_new_psw.text()

            if new_password:
                if not self.db.set_admin_password(new_password):
                    raise RuntimeError(
                        "The administrator password could not be saved."
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
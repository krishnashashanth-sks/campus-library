import os
import sqlite3
import datetime
import shutil
import sys
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import Qt, QSignalBlocker, QThreadPool, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QFileDialog,
    QMessageBox, QDoubleSpinBox, QSpinBox, QComboBox,
    QScrollArea, QFrame, QInputDialog, QApplication,
    QGridLayout, QSizePolicy, QProgressBar, QTabWidget,
    QPlainTextEdit
)
from ui_responsive import (
    FlowLayout,
    clamp_widget_to_screen,
    configure_wrapped_label,
    wrap_in_scroll_area,
)
from utils import rgba_color

from dialogs import (
    DepartmentManagerDialog,
    EmailQueueManagementDialog,
    RecoveryCodeSetupDialog,
    VersionManagerDialog,
    markdown_to_plain_text,
)
from email_queue import EmailTestWorker
from email_service import SMTP_CREDENTIAL_TARGET
from secure_storage import delete_secret, store_secret
from app_version import APP_DEVELOPER_CREDIT, APP_NAME, get_app_version
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


class _WrappedCheckLabel(QLabel):
    """Clickable multi-line label paired with a QCheckBox so long descriptions wrap cleanly."""

    def __init__(self, text, checkbox, parent=None):
        super().__init__(text, parent)
        self._checkbox = checkbox

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.pos())
            and self._checkbox is not None
            and self._checkbox.isEnabled()
        ):
            self._checkbox.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _GoogleDriveSetupDialog(QDialog):
    """Guided one-time Google Drive OAuth client configuration dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client_json_text = ""
        self.setWindowTitle("Connect Google Drive (One-Time Setup)")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Google Drive Backup Setup")
        title.setStyleSheet("font-size: 16px; font-weight: 800;")
        configure_wrapped_label(title)
        root.addWidget(title)

        guide = QLabel(
            "You only need to do this ONCE per computer — the librarian will never "
            "be asked for client.json again after connecting.\n\n"
            "Easy alternatives:\n"
            "• Recommended for librarians: Cancel here and use 'Synced Folder Backup' "
            "below with Google Drive for Desktop or OneDrive (zero client.json needed).\n"
            "• IT deployment: Copy 'google_drive_client.json' beside Library.exe or into "
            "assets/google_drive_client.json before building an internal installer.\n\n"
            "To set up Google OAuth manually once:\n"
            "1. Open Google Cloud Console → Enable Google Drive API.\n"
            "2. Go to Credentials → Create Credentials → OAuth client ID → Desktop app.\n"
            "3. Choose the downloaded .json file below or paste its text."
        )
        configure_wrapped_label(guide)
        root.addWidget(guide)

        self.json_editor = QPlainTextEdit()
        self.json_editor.setPlaceholderText(
            'Paste Google OAuth Desktop JSON here (starts with {"installed": ...}) '
            "or click 'Browse client.json...'"
        )
        self.json_editor.setMinimumHeight(110)
        root.addWidget(self.json_editor, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        browse_btn = QPushButton("Browse client.json...")
        browse_btn.clicked.connect(self._browse_file)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        connect_btn = QPushButton("Save && Connect Google")
        connect_btn.setDefault(True)
        connect_btn.clicked.connect(self._accept_json)

        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(connect_btn)
        root.addLayout(btn_row)

        clamp_widget_to_screen(self, 560, 460, min_width=360, min_height=300)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Google OAuth Desktop Client JSON",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            self.json_editor.setPlainText(content)
        except Exception as error:
            QMessageBox.warning(self, "Could Not Read File", str(error))

    def _accept_json(self):
        raw_text = self.json_editor.toPlainText().strip()
        try:
            from google_drive_backup import validate_and_parse_drive_client_json

            validate_and_parse_drive_client_json(raw_text)
        except Exception as error:
            QMessageBox.warning(self, "Invalid Client JSON", str(error))
            return
        self.client_json_text = raw_text
        self.accept()


class SettingsView(QWidget):

    DEFAULTS = {
        "daily_fine": 10.00,
        "default_days": 14,
        "max_renewals": 2,
        "allow_overdue_renewal": True,
        "theme_mode": "Dark",
    }

    DEFAULT_ROLE_POLICIES = (
        ("Student", 3, 14, 2.00),
        ("Faculty", 8, 30, 1.00),
        ("Guest Lecturer", 5, 21, 2.00),
        ("Admin", 15, 60, 0.00),
        ("Librarian", 10, 30, 0.00),
    )

    THEMES = ("Dark", "Light", "System")

    def __init__(self, db):
        super().__init__()

        self.db = db
        self._loading_settings = False
        self._saving_settings = False
        self._has_loaded_once = False
        self._theme_manager = None
        self._update_pool = QThreadPool(self)
        self._update_worker = None
        self._pending_update = None
        self._email_test_worker = None
        self._closing = False
        self.role_policy_controls = {}
        self.role_policy_rows = []
        self.role_policy_headers = []
        self._role_policy_mode = None
        self._settings_compact = None
        self._settings_stacked = None
        self._action_bar_stacked = None
        self._password_rows = []

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
        tm_colors = getattr(manager, "COLORS", {}).get(theme)

        if theme == "Light":
            colors = {
                "window": "#D2DFEF",
                "surface": "#E3ECF9",
                "surface_alt": "#CFDDF3",
                "surface_elevated": "#BED0EC",
                "input": "#DAE6F7",
                "border": "#88A4CE",
                "border_bright": "#5A7CB2",
                "text": "#0A1628",
                "muted": "#283D5E",
                "primary": "#1D4ED8",
                "primary_hover": "#1E40AF",
                "primary_soft": "rgba(29, 78, 216, 0.20)",
                "selection": "#1D4ED8",
                "indigo": "#4338CA",
                "indigo_hover": "#3730A3",
                "indigo_soft": "rgba(67, 56, 202, 0.20)",
                "cyan": "#0369A1",
                "cyan_hover": "#075985",
                "cyan_soft": "rgba(3, 105, 161, 0.20)",
                "teal": "#0F766E",
                "purple": "#6D28D9",
                "purple_soft": "rgba(109, 40, 217, 0.20)",
                "success": "#047857",
                "success_hover": "#065F46",
                "success_soft": "rgba(4, 120, 87, 0.20)",
                "warning": "#B45309",
                "warning_hover": "#92400E",
                "warning_soft": "rgba(180, 83, 9, 0.22)",
                "danger": "#BE123C",
                "danger_hover": "#9F1239",
                "danger_soft": "rgba(190, 18, 60, 0.20)",
            }
        else:
            colors = {
                "window": "#090E1A",
                "surface": "#111A2E",
                "surface_alt": "#182542",
                "surface_elevated": "#1F2F52",
                "input": "#0C1426",
                "border": "#28385C",
                "border_bright": "#384F82",
                "text": "#F8FAFC",
                "muted": "#9BB0CE",
                "primary": "#3B82F6",
                "primary_hover": "#2563EB",
                "primary_soft": "rgba(59, 130, 246, 0.16)",
                "selection": "#2563EB",
                "indigo": "#818CF8",
                "indigo_hover": "#6366F1",
                "indigo_soft": "rgba(129, 140, 248, 0.16)",
                "cyan": "#22D3EE",
                "cyan_hover": "#06B6D4",
                "cyan_soft": "rgba(34, 211, 238, 0.16)",
                "teal": "#2DD4BF",
                "purple": "#A78BFA",
                "purple_soft": "rgba(167, 139, 250, 0.16)",
                "success": "#10B981",
                "success_hover": "#059669",
                "success_soft": "rgba(16, 185, 129, 0.16)",
                "warning": "#F59E0B",
                "warning_hover": "#D97706",
                "warning_soft": "rgba(245, 158, 11, 0.16)",
                "danger": "#F43F5E",
                "danger_hover": "#E11D48",
                "danger_soft": "rgba(244, 63, 94, 0.16)",
            }

        if isinstance(tm_colors, dict):
            colors.update(tm_colors)

        c = colors
        self.setStyleSheet(f"""
            QWidget#SettingsView {{
                background-color: {c["window"]};
                color: {c["text"]};
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QWidget#SettingsContainer {{
                background: transparent;
            }}

            QScrollArea#SettingsScrollArea {{
                background: transparent;
                border: none;
            }}

            QLabel {{
                color: {c["text"]};
                background: transparent;
                border: none;
            }}

            QLabel#PageTitle {{
                color: {c["text"]};
                font-size: 23px;
                font-weight: 800;
            }}

            QLabel#PageSubtitle,
            QLabel#SectionDescription,
            QLabel#MutedLabel {{
                color: {c["muted"]};
                font-size: 12px;
            }}

            QLabel#SectionTitle {{
                color: {c["text"]};
                font-size: 15px;
                font-weight: 800;
            }}

            QFrame#SectionAccentBar {{
                border-radius: 2px;
                border: none;
                background-color: {c["primary"]};
            }}

            QFrame#SectionAccentBar[accentRole="primary"] {{ background-color: {c["primary"]}; }}
            QFrame#SectionAccentBar[accentRole="warning"] {{ background-color: {c["warning"]}; }}
            QFrame#SectionAccentBar[accentRole="purple"] {{ background-color: {c["purple"]}; }}
            QFrame#SectionAccentBar[accentRole="indigo"] {{ background-color: {c["indigo"]}; }}
            QFrame#SectionAccentBar[accentRole="cyan"] {{ background-color: {c["cyan"]}; }}
            QFrame#SectionAccentBar[accentRole="teal"] {{ background-color: {c["teal"]}; }}
            QFrame#SectionAccentBar[accentRole="danger"] {{ background-color: {c["danger"]}; }}
            QFrame#SectionAccentBar[accentRole="success"] {{ background-color: {c["success"]}; }}

            QLabel#FieldLabel {{
                color: {c["text"]};
                font-size: 12px;
                font-weight: 600;
            }}

            QLabel#RoleBadge {{
                border-radius: 7px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }}

            QLabel#RoleBadge[roleAccent="student"] {{
                background-color: {c["success_soft"]};
                color: {c["success"]};
                border: 1px solid {rgba_color(c["success"], 0.40)};
            }}

            QLabel#RoleBadge[roleAccent="faculty"] {{
                background-color: {c["cyan_soft"]};
                color: {c["cyan"]};
                border: 1px solid {rgba_color(c["cyan"], 0.40)};
            }}

            QLabel#RoleBadge[roleAccent="guest"] {{
                background-color: {c["warning_soft"]};
                color: {c["warning"]};
                border: 1px solid {rgba_color(c["warning"], 0.40)};
            }}

            QLabel#RoleBadge[roleAccent="admin"] {{
                background-color: {c["purple_soft"]};
                color: {c["purple"]};
                border: 1px solid {rgba_color(c["purple"], 0.40)};
            }}

            QLabel#RoleBadge[roleAccent="librarian"] {{
                background-color: {c["indigo_soft"]};
                color: {c["indigo"]};
                border: 1px solid {rgba_color(c["indigo"], 0.40)};
            }}

            QLabel#DangerTitle {{
                color: {c["danger"]};
                font-size: 14px;
                font-weight: 800;
            }}

            QFrame#SettingsCard {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border"]};
                border-left: 4px solid {c["primary"]};
                border-radius: 11px;
            }}

            QFrame#SettingsCard[accentRole="primary"] {{ border-left: 4px solid {c["primary"]}; }}
            QFrame#SettingsCard[accentRole="warning"] {{ border-left: 4px solid {c["warning"]}; }}
            QFrame#SettingsCard[accentRole="purple"] {{ border-left: 4px solid {c["purple"]}; }}
            QFrame#SettingsCard[accentRole="indigo"] {{ border-left: 4px solid {c["indigo"]}; }}
            QFrame#SettingsCard[accentRole="cyan"] {{ border-left: 4px solid {c["cyan"]}; }}
            QFrame#SettingsCard[accentRole="teal"] {{ border-left: 4px solid {c["teal"]}; }}
            QFrame#SettingsCard[accentRole="danger"] {{ border-left: 4px solid {c["danger"]}; }}
            QFrame#SettingsCard[accentRole="success"] {{ border-left: 4px solid {c["success"]}; }}

            QFrame#SettingsActionBar {{
                background-color: {c["surface"]};
                border: 1.5px solid {c["border_bright"]};
                border-top: 2px solid {c["primary"]};
                border-radius: 11px;
            }}

            QFrame#InfoFrame {{
                background-color: {c["primary_soft"]};
                border: 1px solid {rgba_color(c["primary"], 0.35)};
                border-left: 3px solid {c["primary"]};
                border-radius: 9px;
            }}

            QFrame#InfoFrame QLabel#MutedLabel {{
                color: {c["text"]};
            }}

            QFrame#DangerFrame {{
                background-color: {c["danger_soft"]};
                border: 1px solid {rgba_color(c["danger"], 0.55)};
                border-left: 4px solid {c["danger"]};
                border-radius: 9px;
            }}

            QFrame#SettingsSeparator {{
                color: {c["border_bright"]};
            }}

            QPushButton {{
                color: {c["text"]};
                font-size: 12px;
                font-weight: 600;
                border-radius: 8px;
                padding: 6px 13px;
            }}

            QPushButton#PrimaryButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["primary"]};
                font-weight: 700;
            }}

            QPushButton#PrimaryButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary_hover"]}, stop:1 {c["indigo_hover"]}
                );
            }}

            QPushButton#SuccessButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["success"]}, stop:1 {c["teal"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["success"]};
                font-weight: 700;
            }}

            QPushButton#SuccessButton:hover {{
                background-color: {c["success_hover"]};
            }}

            QPushButton#InfoButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["cyan"]}, stop:1 {c["primary"]}
                );
                color: #FFFFFF;
                border: 1px solid {c["cyan"]};
                font-weight: 700;
            }}

            QPushButton#InfoButton:hover {{
                background-color: {c["cyan_hover"]};
            }}

            QPushButton#WarningButton {{
                background-color: {c["warning"]};
                color: #FFFFFF;
                border: 1px solid {c["warning"]};
                font-weight: 700;
            }}

            QPushButton#WarningButton:hover {{
                background-color: {c["warning_hover"]};
            }}

            QPushButton#SecondaryButton,
            QPushButton#SmallButton {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
            }}

            QPushButton#SecondaryButton:hover,
            QPushButton#SmallButton:hover {{
                background-color: {c["surface_elevated"]};
                border-color: {c["primary"]};
                color: {c["primary"]};
            }}

            QPushButton#DangerButton {{
                background-color: {c["danger_soft"]};
                color: {c["danger"]};
                border: 1px solid {rgba_color(c["danger"], 0.65)};
                font-weight: 700;
            }}

            QPushButton#DangerButton:hover {{
                background-color: {c["danger"]};
                color: #FFFFFF;
                border-color: {c["danger"]};
            }}

            QPushButton#PrimaryButton:disabled,
            QPushButton#SuccessButton:disabled,
            QPushButton#InfoButton:disabled,
            QPushButton#WarningButton:disabled,
            QPushButton#SecondaryButton:disabled,
            QPushButton#SmallButton:disabled,
            QPushButton#DangerButton:disabled {{
                background: {c["input"]};
                background-color: {c["input"]};
                color: {c["muted"]};
                border: 1px solid {c["border"]};
            }}

            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox {{
                background-color: {c["input"]};
                color: {c["text"]};
                border: 1.5px solid {c["border"]};
                border-radius: 8px;
                padding: 5px 9px;
                font-size: 12px;
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
            }}

            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus {{
                border: 1.5px solid {c["primary"]};
            }}

            QComboBox QAbstractItemView {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border_bright"]};
                selection-background-color: {c["selection"]};
                selection-color: #FFFFFF;
            }}

            QProgressBar {{
                background-color: {c["input"]};
                border: 1px solid {c["border"]};
                border-radius: 6px;
                text-align: center;
                color: {c["text"]};
                font-weight: 700;
            }}

            QProgressBar::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["cyan"]}, stop:0.5 {c["primary"]}, stop:1 {c["success"]}
                );
                border-radius: 5px;
            }}

            QTabWidget#SettingsCategoryTabs::pane {{
                background: transparent;
                border: 1.5px solid {c["border"]};
                border-radius: 11px;
                top: -1px;
            }}

            QTabWidget#SettingsCategoryTabs > QTabBar::tab {{
                background-color: {c["surface_alt"]};
                color: {c["muted"]};
                border: 1px solid {c["border"]};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 7px 14px;
                margin-right: 4px;
                font-size: 12px;
                font-weight: 700;
            }}

            QTabWidget#SettingsCategoryTabs > QTabBar::tab:hover {{
                background-color: {c["surface_elevated"]};
                color: {c["text"]};
                border-color: {c["primary"]};
            }}

            QTabWidget#SettingsCategoryTabs > QTabBar::tab:selected {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c["primary"]}, stop:1 {c["indigo"]}
                );
                color: #FFFFFF;
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
        manager = self._theme_manager or self.get_theme_manager()
        if manager and hasattr(self, "combo_theme"):
            selected_theme = manager.get_theme()
            if (
                selected_theme in self.THEMES
                and self.combo_theme.currentText() != selected_theme
            ):
                blocker = QSignalBlocker(self.combo_theme)
                self.combo_theme.setCurrentText(selected_theme)
                del blocker
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

    def create_card_frame(self, object_name="SettingsCard", accent_role=None):
        frame = QFrame()
        frame.setObjectName(object_name)
        if accent_role:
            frame.setProperty("accentRole", accent_role)
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        return frame

    def create_section_header(self, title, description="", accent_role="primary"):
        wrapper = QWidget()
        wrapper.setObjectName("SettingsSectionHeader")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 4, 0, 2)
        layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        accent_bar = QFrame()
        accent_bar.setObjectName("SectionAccentBar")
        accent_bar.setProperty("accentRole", accent_role)
        accent_bar.setFixedSize(4, 16)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        configure_wrapped_label(title_label)

        title_row.addWidget(accent_bar)
        title_row.addWidget(title_label, 1)
        layout.addLayout(title_row)

        if description:
            desc = QLabel(description)
            desc.setObjectName("SectionDescription")
            configure_wrapped_label(desc)
            layout.addWidget(desc)

        wrapper.setMinimumWidth(0)
        return wrapper

    def create_info_frame(self, text):
        frame = QFrame()
        frame.setObjectName("InfoFrame")
        frame.setMinimumWidth(0)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        label = QLabel(text)
        label.setObjectName("MutedLabel")
        configure_wrapped_label(label)

        layout.addWidget(label, 1)
        return frame

    def create_field_label(self, text):
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        configure_wrapped_label(label, expanding_width=False)
        return label

    def create_button(self, text, object_name="SecondaryButton"):
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumWidth(0)
        button.setMinimumHeight(34)
        return button

    def create_wrapped_checkbox(self, text, checked=False, tooltip=None):
        """Return (row_container, QCheckBox) where the label wraps cleanly on narrow screens."""
        container = QWidget()
        container.setMinimumWidth(0)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        checkbox = QCheckBox()
        checkbox.setAccessibleName(text)
        checkbox.setChecked(checked)
        checkbox.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        text_label = _WrappedCheckLabel(text, checkbox, container)
        configure_wrapped_label(text_label)
        text_label.setCursor(Qt.CursorShape.PointingHandCursor)

        if tooltip:
            checkbox.setToolTip(tooltip)
            text_label.setToolTip(tooltip)
            container.setToolTip(tooltip)

        row.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(text_label, 1)
        return container, checkbox

    def create_password_field(self, placeholder):
        field = QLineEdit()
        field.setObjectName("PasswordField")
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setMinimumWidth(0)
        field.setMinimumHeight(34)
        field.setClearButtonEnabled(True)
        return field

    def create_password_row(self, label_text, placeholder):
        wrapper = QWidget()
        wrapper.setMinimumWidth(0)

        layout = QGridLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        label = self.create_field_label(label_text)
        label.setMinimumWidth(145)

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

        layout.addWidget(label, 0, 0)
        layout.addWidget(field, 0, 1)
        layout.addWidget(toggle, 0, 2)
        layout.setColumnStretch(1, 1)
        self._password_rows.append((layout, label, field, toggle))

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

    def _add_settings_tab(self, title, object_name):
        container = QWidget()
        container.setObjectName("SettingsContainer")
        container.setMinimumWidth(0)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        scroll = wrap_in_scroll_area(container, object_name=object_name)
        self.tab_scrolls.append(scroll)
        self.tab_containers.append(container)
        self.tab_layouts.append(layout)
        self.settings_tabs.addTab(scroll, title)
        return scroll, container, layout

    def _on_settings_tab_changed(self, index):
        if 0 <= index < len(self.tab_scrolls):
            self.scroll = self.tab_scrolls[index]
            self.container = self.tab_containers[index]
        self._reflow_layout()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 40)
        main_layout.setSpacing(8)
        self.main_layout = main_layout

        # Header
        title_group = QVBoxLayout()
        title_group.setContentsMargins(0, 0, 0, 0)
        title_group.setSpacing(2)

        title = QLabel("Settings & Configuration")
        title.setObjectName("PageTitle")
        configure_wrapped_label(title)

        subtitle = QLabel(
            "Manage application preferences, circulation policies, "
            "academic records, security and database maintenance."
        )
        subtitle.setObjectName("PageSubtitle")
        configure_wrapped_label(subtitle)

        title_group.addWidget(title)
        title_group.addWidget(subtitle)
        main_layout.addLayout(title_group)

        # Category tabs so each section stays readable without a giant vertical scroll wall
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("SettingsCategoryTabs")
        self.settings_tabs.tabBar().setExpanding(False)
        self.settings_tabs.tabBar().setUsesScrollButtons(True)
        self.tab_scrolls = []
        self.tab_containers = []
        self.tab_layouts = []

        _s0, _c0, tab_policies_layout = self._add_settings_tab(
            "Policies && Theme", "SettingsPoliciesScroll"
        )
        _s1, _c1, tab_academic_layout = self._add_settings_tab(
            "Academic && Rollover", "SettingsAcademicScroll"
        )
        _s2, _c2, tab_comms_layout = self._add_settings_tab(
            "Email && Updates", "SettingsCommsScroll"
        )
        _s3, _c3, tab_backup_layout = self._add_settings_tab(
            "Backup && Security", "SettingsSecurityScroll"
        )

        self.content_layout = tab_policies_layout
        self.build_appearance_section()
        self.build_circulation_section()
        tab_policies_layout.addStretch()

        self.content_layout = tab_academic_layout
        self.build_department_section()
        self.build_rollover_section()
        tab_academic_layout.addStretch()

        self.content_layout = tab_comms_layout
        self.build_email_section()
        self.build_update_section()
        tab_comms_layout.addStretch()

        self.content_layout = tab_backup_layout
        self.build_cloud_backup_section()
        self.build_database_section()
        self.build_security_section()
        tab_backup_layout.addStretch()

        self.content_layout = tab_policies_layout
        self.scroll = self.tab_scrolls[0]
        self.container = self.tab_containers[0]
        self.settings_tabs.currentChanged.connect(self._on_settings_tab_changed)

        main_layout.addWidget(self.settings_tabs, 1)

        # Action bar
        action_frame = self.create_card_frame("SettingsActionBar")

        self.action_bar_layout = QGridLayout(action_frame)
        self.action_bar_layout.setContentsMargins(14, 9, 14, 9)
        self.action_bar_layout.setHorizontalSpacing(10)
        self.action_bar_layout.setVerticalSpacing(6)

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

        self.action_bar_layout.addWidget(self.btn_reset, 0, 0)
        self.action_bar_layout.addWidget(self.btn_save, 0, 2)
        self.action_bar_layout.setColumnStretch(1, 1)

        main_layout.addWidget(action_frame)
        self._reflow_layout()

    # =========================================================
    # 1. DEPARTMENT MANAGEMENT
    # =========================================================

    def build_department_section(self):
        header = self.create_section_header(
            "Academic Departments",
            "Manage the academic branches and departments "
            "available in your institution.",
            accent_role="primary",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="primary")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(9)

        layout.addWidget(
            self.create_info_frame(
                "View fixed college branches and faculty departments, "
                "and adjust course durations for student branches."
            )
        )

        self.btn_manage_depts = self.create_button(
            "View Branches && Departments",
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
        header = self.create_section_header(
            "Academic Year Rollover",
            "Archive graduating students and remove eligible "
            "records from the active database.",
            accent_role="warning",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="warning")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(9)

        layout.addWidget(
            self.create_info_frame(
                "This operation exports graduating student records "
                "to a CSV archive before removing eligible records "
                "from the active database."
            )
        )

        chk_skip_row, self.chk_skip_active = self.create_wrapped_checkbox(
            "Skip students with issued books",
            checked=True,
        )

        layout.addWidget(chk_skip_row)

        self.btn_archive_batch = self.create_button(
            "Export && Clear Graduating Batch",
            "WarningButton"
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
        header = self.create_section_header(
            "Appearance & Interface",
            "Configure the visual appearance of the application.",
            accent_role="purple",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="purple")
        self.appearance_layout = QGridLayout(card)
        self.appearance_layout.setContentsMargins(14, 11, 14, 11)
        self.appearance_layout.setHorizontalSpacing(14)
        self.appearance_layout.setVerticalSpacing(8)

        self.appearance_text_host = QWidget()
        self.appearance_text_host.setMinimumWidth(0)
        text_layout = QVBoxLayout(self.appearance_text_host)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)

        label = self.create_field_label("Application Theme")

        self.theme_description = QLabel(
            "Choose the appearance used throughout the application."
        )
        self.theme_description.setObjectName("MutedLabel")
        configure_wrapped_label(self.theme_description)

        text_layout.addWidget(label)
        text_layout.addWidget(self.theme_description)

        self.combo_theme = QComboBox()
        self.combo_theme.addItems(self.THEMES)
        self.combo_theme.setMinimumWidth(160)
        self.combo_theme.setMinimumHeight(34)
        self.combo_theme.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.combo_theme.currentTextChanged.connect(
            self.on_theme_changed
        )

        self.appearance_layout.addWidget(self.appearance_text_host, 0, 0)
        self.appearance_layout.addWidget(self.combo_theme, 0, 1)
        self.appearance_layout.setColumnStretch(0, 1)

        self.content_layout.addWidget(card)

    # =========================================================
    # 4. CIRCULATION POLICIES
    # =========================================================

    def build_circulation_section(self):
        header = self.create_section_header(
            "Circulation Policies",
            "Configure borrowing duration and overdue fine calculation.",
            accent_role="indigo",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="indigo")
        self.circ_form_layout = QGridLayout(card)
        self.circ_form_layout.setContentsMargins(14, 11, 14, 11)
        self.circ_form_layout.setHorizontalSpacing(16)
        self.circ_form_layout.setVerticalSpacing(8)

        self.circ_fine_label = self.create_field_label("Daily Overdue Fine")

        self.spin_daily_fine = QDoubleSpinBox()
        self.spin_daily_fine.setRange(0, 1000)
        self.spin_daily_fine.setDecimals(2)
        self.spin_daily_fine.setSingleStep(0.50)
        self.spin_daily_fine.setPrefix("₹ ")
        self.spin_daily_fine.setMinimumWidth(0)
        self.spin_daily_fine.setMinimumHeight(34)
        self.spin_daily_fine.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.circ_fine_desc = QLabel(
            "Amount charged for each overdue day."
        )
        self.circ_fine_desc.setObjectName("MutedLabel")
        configure_wrapped_label(self.circ_fine_desc)

        self.circ_days_label = self.create_field_label("Default Loan Duration")

        self.spin_default_days = QSpinBox()
        self.spin_default_days.setRange(1, 365)
        self.spin_default_days.setSuffix(" days")
        self.spin_default_days.setMinimumWidth(0)
        self.spin_default_days.setMinimumHeight(34)
        self.spin_default_days.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.circ_days_desc = QLabel(
            "Default number of days allowed for borrowing."
        )
        self.circ_days_desc.setObjectName("MutedLabel")
        configure_wrapped_label(self.circ_days_desc)

        self.circ_max_renew_label = self.create_field_label("Max Renewals per Loan")

        self.spin_max_renewals = QSpinBox()
        self.spin_max_renewals.setRange(0, 20)
        self.spin_max_renewals.setSpecialValueText("Unlimited")
        self.spin_max_renewals.setSuffix(" times")
        self.spin_max_renewals.setMinimumWidth(0)
        self.spin_max_renewals.setMinimumHeight(34)
        self.spin_max_renewals.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.circ_max_renew_desc = QLabel(
            "Maximum standard renewals per checkout (0 allows unlimited renewals)."
        )
        self.circ_max_renew_desc.setObjectName("MutedLabel")
        configure_wrapped_label(self.circ_max_renew_desc)

        self.chk_allow_overdue_row, self.chk_allow_overdue_renew = (
            self.create_wrapped_checkbox(
                "Allow renewing overdue loans (assesses overdue fines upon renewal)"
            )
        )

        self.circ_form_layout.addWidget(self.circ_fine_label, 0, 0)
        self.circ_form_layout.addWidget(self.circ_days_label, 0, 1)
        self.circ_form_layout.addWidget(self.spin_daily_fine, 1, 0)
        self.circ_form_layout.addWidget(self.spin_default_days, 1, 1)
        self.circ_form_layout.addWidget(self.circ_fine_desc, 2, 0)
        self.circ_form_layout.addWidget(self.circ_days_desc, 2, 1)
        self.circ_form_layout.addWidget(self.circ_max_renew_label, 3, 0, 1, 2)
        self.circ_form_layout.addWidget(self.spin_max_renewals, 4, 0)
        self.circ_form_layout.addWidget(self.circ_max_renew_desc, 4, 1)
        self.circ_form_layout.addWidget(self.chk_allow_overdue_row, 5, 0, 1, 2)
        self.circ_form_layout.setColumnStretch(0, 1)
        self.circ_form_layout.setColumnStretch(1, 1)

        self.content_layout.addWidget(card)

        # Role-Based Loan & Fine Policies Editor
        role_card = self.create_card_frame(accent_role="cyan")
        self.role_policy_card = role_card
        self.role_policy_layout = QGridLayout(role_card)
        self.role_policy_layout.setContentsMargins(14, 11, 14, 11)
        self.role_policy_layout.setHorizontalSpacing(10)
        self.role_policy_layout.setVerticalSpacing(7)

        self.role_policy_title = self.create_field_label("Role-Based Borrowing & Fine Policies")
        configure_wrapped_label(self.role_policy_title)
        self.role_policy_subtitle = QLabel(
            "Configure concurrent book limits, default checkout/renewal durations, "
            "and daily overdue fine rates for each user role."
        )
        self.role_policy_subtitle.setObjectName("MutedLabel")
        configure_wrapped_label(self.role_policy_subtitle)

        self.role_policy_headers = []
        for col_text in (
            "Member Role",
            "Max Books Allowed",
            "Default Loan Days",
            "Daily Fine (₹)",
        ):
            hdr = self.create_field_label(col_text)
            hdr.setParent(role_card)
            configure_wrapped_label(hdr)
            self.role_policy_headers.append(hdr)

        role_accent_map = {
            "Student": "student",
            "Faculty": "faculty",
            "Guest Lecturer": "guest",
            "Admin": "admin",
            "Librarian": "librarian",
        }
        self.role_policy_rows = []
        for idx, (role_name, def_books, def_days, def_fine) in enumerate(
            self.DEFAULT_ROLE_POLICIES
        ):
            lbl_role = QLabel(role_name, role_card)
            lbl_role.setObjectName("RoleBadge")
            configure_wrapped_label(lbl_role, expanding_width=False)
            lbl_role.setProperty(
                "roleAccent",
                role_accent_map.get(role_name, "student"),
            )

            spin_books = QSpinBox(role_card)
            spin_books.setRange(0, 100)
            spin_books.setValue(def_books)
            spin_books.setSuffix(" books")
            spin_books.setMinimumWidth(0)
            spin_books.setMinimumHeight(31)
            spin_books.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

            spin_days = QSpinBox(role_card)
            spin_days.setRange(1, 365)
            spin_days.setValue(def_days)
            spin_days.setSuffix(" days")
            spin_days.setMinimumWidth(0)
            spin_days.setMinimumHeight(31)
            spin_days.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

            spin_fine = QDoubleSpinBox(role_card)
            spin_fine.setRange(0, 1000)
            spin_fine.setDecimals(2)
            spin_fine.setSingleStep(0.50)
            spin_fine.setPrefix("₹ ")
            spin_fine.setValue(def_fine)
            spin_fine.setMinimumWidth(0)
            spin_fine.setMinimumHeight(31)
            spin_fine.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

            lbl_books = self.create_field_label("Max Books Allowed")
            lbl_books.setParent(role_card)
            lbl_days = self.create_field_label("Default Loan Days")
            lbl_days.setParent(role_card)
            lbl_fine = self.create_field_label("Daily Fine (₹)")
            lbl_fine.setParent(role_card)
            divider = (
                self.create_separator()
                if idx < len(self.DEFAULT_ROLE_POLICIES) - 1
                else None
            )
            if divider is not None:
                divider.setParent(role_card)

            self.role_policy_rows.append(
                {
                    "badge": lbl_role,
                    "lbl_books": lbl_books,
                    "spin_books": spin_books,
                    "lbl_days": lbl_days,
                    "spin_days": spin_days,
                    "lbl_fine": lbl_fine,
                    "spin_fine": spin_fine,
                    "divider": divider,
                }
            )

            self.role_policy_controls[role_name] = {
                "max_books": spin_books,
                "default_days": spin_days,
                "fine_per_day": spin_fine,
            }

        self.content_layout.addWidget(role_card)

    def build_email_section(self):
        header = self.create_section_header(
            "Email Notifications & Complaints",
            "Send due-date reminders to users and forward submitted "
            "complaints to the library contact. Pause delivery and review "
            "or remove queued messages at any time.",
            accent_role="cyan",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="cyan")
        self.email_form_layout = QGridLayout(card)
        self.email_form_layout.setContentsMargins(14, 11, 14, 11)
        self.email_form_layout.setHorizontalSpacing(14)
        self.email_form_layout.setVerticalSpacing(8)

        self.email_sender_label = self.create_field_label("Gmail sender")
        self.library_contact_label = self.create_field_label("Library contact")
        self.email_sender_input = QLineEdit()
        self.email_sender_input.setMinimumWidth(0)
        self.email_sender_input.setPlaceholderText(
            "Gmail address used to send messages"
        )
        self.library_contact_input = QLineEdit()
        self.library_contact_input.setMinimumWidth(0)
        self.library_contact_input.setPlaceholderText(
            "Library inbox for complaints"
        )
        self.smtp_app_password_label = self.create_field_label("Gmail app password")
        self.smtp_app_password_input = QLineEdit()
        self.smtp_app_password_input.setMinimumWidth(0)
        self.smtp_app_password_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.smtp_app_password_input.setPlaceholderText(
            "Gmail app password (saved in Windows Credential Manager)"
        )

        self.email_form_layout.addWidget(self.email_sender_label, 0, 0)
        self.email_form_layout.addWidget(self.library_contact_label, 0, 1)
        self.email_form_layout.addWidget(self.email_sender_input, 1, 0)
        self.email_form_layout.addWidget(self.library_contact_input, 1, 1)
        self.email_form_layout.addWidget(
            self.smtp_app_password_label,
            2,
            0,
            1,
            2,
        )
        self.email_form_layout.addWidget(self.smtp_app_password_input, 3, 0, 1, 2)

        self.email_actions_host = QWidget()
        self.email_actions_host.setMinimumWidth(0)
        actions = FlowLayout(self.email_actions_host, margin=0, h_spacing=8, v_spacing=8)
        self.save_email_btn = self.create_button(
            "Save Email Settings",
            "SuccessButton",
        )
        self.save_email_btn.clicked.connect(self.save_email_settings)
        self.test_email_btn = self.create_button(
            "Send Test Email",
            "InfoButton",
        )
        self.test_email_btn.clicked.connect(self.send_test_email)
        self.clear_email_secret_btn = self.create_button(
            "Remove Saved App Password",
            "WarningButton",
        )
        self.clear_email_secret_btn.clicked.connect(
            self.remove_email_secret
        )

        actions.addWidget(self.save_email_btn)
        actions.addWidget(self.test_email_btn)
        actions.addWidget(self.clear_email_secret_btn)
        self.email_form_layout.addWidget(self.email_actions_host, 4, 0, 1, 2)

        self.email_delivery_row, self.email_delivery_checkbox = (
            self.create_wrapped_checkbox(
                "Enable sending queued emails to recipient addresses",
                tooltip=(
                    "Only enable after confirming all queued recipient addresses are "
                    "real and intended. Fake test-user addresses will fail delivery."
                ),
            )
        )
        self.email_delivery_checkbox.toggled.connect(
            self.set_email_delivery_enabled
        )
        self.email_reminders_row, self.email_reminders_checkbox = (
            self.create_wrapped_checkbox(
                "Send one reminder on the due date and one when a loan becomes overdue"
            )
        )
        self.email_form_layout.addWidget(
            self.email_delivery_row,
            5,
            0,
            1,
            2,
        )
        self.email_form_layout.addWidget(
            self.email_reminders_row,
            6,
            0,
            1,
            2,
        )

        self.email_queue_row = QWidget()
        self.email_queue_row.setMinimumWidth(0)
        self.email_queue_layout = QGridLayout(self.email_queue_row)
        self.email_queue_layout.setContentsMargins(0, 0, 0, 0)
        self.email_queue_layout.setHorizontalSpacing(10)
        self.email_queue_layout.setVerticalSpacing(8)
        self.email_queue_status = QLabel("Email queue status unavailable")
        self.email_queue_status.setObjectName("MutedLabel")
        configure_wrapped_label(self.email_queue_status)
        self.email_queue_btns = QWidget()
        self.email_queue_btns.setMinimumWidth(0)
        queue_btns_flow = FlowLayout(self.email_queue_btns, margin=0, h_spacing=8, v_spacing=8)
        self.sync_email_btn = self.create_button(
            "Sync Now",
            "PrimaryButton",
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
        queue_btns_flow.addWidget(self.manage_email_queue_btn)
        queue_btns_flow.addWidget(self.sync_email_btn)
        self.email_queue_layout.addWidget(self.email_queue_status, 0, 0)
        self.email_queue_layout.addWidget(self.email_queue_btns, 0, 1)
        self.email_queue_layout.setColumnStretch(0, 1)
        self.email_form_layout.addWidget(self.email_queue_row, 7, 0, 1, 2)
        self.email_form_layout.setColumnStretch(0, 1)
        self.email_form_layout.setColumnStretch(1, 1)

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
        header = self.create_section_header(
            "Application Updates",
            "Check for a newer Windows build and update from within "
            "the application.",
            accent_role="teal",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="teal")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)

        about_label = QLabel(f"{APP_NAME} — {APP_DEVELOPER_CREDIT}")
        about_label.setObjectName("FieldLabel")
        configure_wrapped_label(about_label)
        layout.addWidget(about_label)

        description = QLabel(
            f"Installed version: {get_app_version()}. Update checks use the "
            "official GitHub Releases page. A downloaded update is "
            "validated and applied after you confirm; the application "
            "will close and restart."
        )
        description.setObjectName("MutedLabel")
        configure_wrapped_label(description)
        layout.addWidget(description)

        self.update_actions_layout = QGridLayout()
        self.update_actions_layout.setHorizontalSpacing(10)
        self.update_actions_layout.setVerticalSpacing(8)
        self.update_status_label = QLabel("Ready to check for updates")
        self.update_status_label.setObjectName("MutedLabel")
        configure_wrapped_label(self.update_status_label)
        self.update_btns_host = QWidget()
        self.update_btns_host.setMinimumWidth(0)
        update_btns_flow = FlowLayout(self.update_btns_host, margin=0, h_spacing=8, v_spacing=8)
        self.update_button = self.create_button(
            "Check for Updates",
            "InfoButton",
        )
        self.update_button.clicked.connect(self.check_for_updates)
        update_btns_flow.addWidget(self.update_button)
        self.manage_versions_button = self.create_button(
            "Manage Versions",
            "SecondaryButton",
        )
        self.manage_versions_button.clicked.connect(
            self.manage_application_versions
        )
        update_btns_flow.addWidget(self.manage_versions_button)
        self.update_actions_layout.addWidget(self.update_status_label, 0, 0)
        self.update_actions_layout.addWidget(self.update_btns_host, 0, 1)
        self.update_actions_layout.setColumnStretch(0, 1)
        layout.addLayout(self.update_actions_layout)

        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        self.update_progress_bar.setTextVisible(True)
        self.update_progress_bar.hide()
        layout.addWidget(self.update_progress_bar)

        self.content_layout.addWidget(card)

    def check_for_updates(self):
        if self._closing or self._update_worker is not None:
            return

        self.update_button.setEnabled(False)
        self.manage_versions_button.setEnabled(False)
        self.update_status_label.setText("Checking for updates...")
        worker = UpdateCheckWorker()
        worker.signals.finished.connect(
            self._on_update_check_finished
        )
        self._update_worker = worker
        self._update_pool.start(worker)

    def manage_application_versions(self):
        if self._closing or self._update_worker is not None:
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
        if getattr(self, "_closing", False) or sip.isdeleted(self):
            self._update_worker = None
            return
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

        packaged = is_packaged_application()
        writable = packaged and can_replace_application(
            Path(sys.executable).resolve().parent
        )
        can_install = packaged and writable
        if not packaged:
            install_reason = (
                "Running from Python source — automatic in-app replacement works only "
                "in the installed Windows app (Library.exe). Click 'Download Installer on GitHub' "
                "to download LibraryInstaller.exe."
            )
        elif not writable:
            install_reason = (
                "This installation folder is read-only for your Windows account. "
                "Click 'Download Installer on GitHub' to reinstall into your user folder."
            )
        else:
            install_reason = ""
        dialog = VersionManagerDialog(
            result.get("releases", []),
            result.get("current_version", get_app_version()),
            can_install,
            self,
            install_reason=install_reason,
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
        if getattr(self, "_closing", False) or sip.isdeleted(self):
            self._update_worker = None
            return
        self._update_worker = None
        self.update_button.setEnabled(True)
        self.manage_versions_button.setEnabled(True)

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
            clean_notes = markdown_to_plain_text(notes)[:2500]
            if clean_notes:
                message += f"\n\nRelease notes:\n{clean_notes}"

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
        self.manage_versions_button.setEnabled(False)
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
        if getattr(self, "_closing", False) or sip.isdeleted(self):
            return
        if self.update_progress_bar.minimum() != 0:
            return
        if self.update_progress_bar.maximum() == 0:
            self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(progress)

    def _on_update_download_finished(self, result):
        if getattr(self, "_closing", False) or sip.isdeleted(self):
            self._update_worker = None
            return
        self._update_worker = None
        self.update_progress_bar.hide()
        self.update_button.setEnabled(True)
        self.manage_versions_button.setEnabled(True)

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
        header = self.create_section_header(
            "Cloud & Synced Folder Backup",
            "Back up your library database with AES-256 encryption to "
            "Google Drive or a synced desktop folder.",
            accent_role="success",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="success")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(9)

        description = QLabel(
            "Backups are encrypted before saving. The encryption key is kept "
            "in this Windows account's Credential Manager; export a Recovery "
            "Key once and store it safely offline so backups can be restored "
            "on another computer."
        )
        description.setObjectName("MutedLabel")
        configure_wrapped_label(description)
        layout.addWidget(description)

        self.drive_status_label = QLabel("Google Drive: Checking status...")
        self.drive_status_label.setObjectName("FieldLabel")
        configure_wrapped_label(self.drive_status_label)
        layout.addWidget(self.drive_status_label)

        self.drive_actions_host = QWidget()
        self.drive_actions_host.setMinimumWidth(0)
        actions = FlowLayout(self.drive_actions_host, margin=0, h_spacing=8, v_spacing=8)

        self.drive_connect_btn = self.create_button(
            "Connect Google Drive",
            "PrimaryButton",
        )
        self.drive_connect_btn.clicked.connect(
            self.connect_google_drive
        )
        actions.addWidget(self.drive_connect_btn)

        self.drive_backup_btn = self.create_button(
            "Back Up to Google Drive",
            "InfoButton",
        )
        self.drive_backup_btn.clicked.connect(
            self.backup_to_google_drive
        )
        actions.addWidget(self.drive_backup_btn)

        self.drive_restore_btn = self.create_button(
            "Restore Encrypted Backup",
            "SecondaryButton",
        )
        self.drive_restore_btn.clicked.connect(
            self.restore_from_google_drive
        )
        actions.addWidget(self.drive_restore_btn)

        self.drive_key_btn = self.create_button(
            "Export Recovery Key",
            "WarningButton",
        )
        self.drive_key_btn.clicked.connect(
            self.export_drive_recovery_key
        )
        actions.addWidget(self.drive_key_btn)

        self.drive_disconnect_btn = self.create_button(
            "Disconnect Drive",
            "DangerButton",
        )
        self.drive_disconnect_btn.clicked.connect(
            self.disconnect_google_drive
        )
        actions.addWidget(self.drive_disconnect_btn)

        auto_drive_row, self.auto_drive_backup_checkbox = self.create_wrapped_checkbox(
            "Automatically upload one encrypted backup to Google Drive per day while open"
        )
        layout.addWidget(self.drive_actions_host)
        layout.addWidget(auto_drive_row)
        layout.addWidget(self.create_separator())

        sync_title = self.create_field_label(
            "Synced Folder Backup (Zero Client JSON Needed)"
        )
        sync_desc = QLabel(
            "Recommended for librarians: choose a folder synced by Google Drive "
            "for Desktop, OneDrive, a shared campus drive, or a USB drive. No "
            "Google Cloud client.json setup is required."
        )
        sync_desc.setObjectName("MutedLabel")
        configure_wrapped_label(sync_desc)
        layout.addWidget(sync_title)
        layout.addWidget(sync_desc)

        self.sync_folder_input = QLineEdit()
        self.sync_folder_input.setMinimumWidth(0)
        self.sync_folder_input.setPlaceholderText(
            "Select folder (e.g. G:\\My Drive\\Library Backups or C:\\LibraryBackups)"
        )
        layout.addWidget(self.sync_folder_input)

        self.sync_actions_host = QWidget()
        self.sync_actions_host.setMinimumWidth(0)
        sync_actions = FlowLayout(self.sync_actions_host, margin=0, h_spacing=8, v_spacing=8)

        self.browse_sync_folder_btn = self.create_button(
            "Choose Folder...",
            "SecondaryButton",
        )
        self.browse_sync_folder_btn.clicked.connect(
            self.choose_sync_backup_folder
        )
        sync_actions.addWidget(self.browse_sync_folder_btn)

        self.sync_folder_backup_btn = self.create_button(
            "Back Up to Folder Now",
            "InfoButton",
        )
        self.sync_folder_backup_btn.clicked.connect(
            self.backup_to_selected_sync_folder
        )
        sync_actions.addWidget(self.sync_folder_backup_btn)

        layout.addWidget(self.sync_actions_host)

        auto_folder_row, self.auto_folder_backup_checkbox = self.create_wrapped_checkbox(
            "Automatically save one encrypted backup per day to this folder while open"
        )
        layout.addWidget(auto_folder_row)

        self.save_drive_settings_btn = self.create_button(
            "Save Backup Settings",
            "SuccessButton",
        )
        self.save_drive_settings_btn.clicked.connect(
            self.save_drive_backup_settings
        )
        layout.addWidget(self.save_drive_settings_btn)

        self.refresh_drive_status_ui()
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
        if self._closing:
            return
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
        self._update_pool.start(worker)

    def _on_test_email_finished(self, result):
        if getattr(self, "_closing", False) or sip.isdeleted(self):
            self._email_test_worker = None
            return
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

    def refresh_drive_status_ui(self):
        if not hasattr(self, "drive_status_label"):
            return
        try:
            from google_drive_backup import get_drive_status

            status = get_drive_status()
        except Exception:
            status = {
                "connected": False,
                "has_client_config": False,
                "client_source": "",
            }

        connected = bool(status.get("connected"))
        has_cfg = bool(status.get("has_client_config"))
        source = status.get("client_source") or "saved configuration"

        if connected:
            self.drive_status_label.setText(
                "Google Drive Status: Connected (ready — no client.json needed again)"
            )
            self.drive_connect_btn.setText("Reconnect Drive")
        elif has_cfg:
            self.drive_status_label.setText(
                f"Google Drive Status: Ready to sign in ({source}) — click Connect Google Drive once."
            )
            self.drive_connect_btn.setText("Connect Google Drive")
        else:
            self.drive_status_label.setText(
                "Google Drive Status: Not connected — use Connect Google Drive (one-time) "
                "or Synced Folder Backup below."
            )
            self.drive_connect_btn.setText("Connect Google Drive")

        self.drive_disconnect_btn.setEnabled(connected or has_cfg)

    def _obtain_drive_client_json_once(self):
        dialog = _GoogleDriveSetupDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.client_json_text or None

    def connect_google_drive(self):
        try:
            from google_drive_backup import connect_drive, get_drive_status

            status = get_drive_status()
            client_json_text = None
            force_reauth = False

            if status["connected"]:
                answer = QMessageBox.question(
                    self,
                    "Google Drive Already Connected",
                    "Google Drive is already signed in. Do you want to sign in "
                    "again with another Google account?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False
                force_reauth = True

            if not status["has_client_config"]:
                client_json_text = self._obtain_drive_client_json_once()
                if not client_json_text:
                    return False

            connect_drive(
                client_json_text=client_json_text,
                force_reauth=force_reauth,
            )
            self.refresh_drive_status_ui()
            QMessageBox.information(
                self,
                "Google Drive Connected",
                "Google Drive is connected and saved in Windows Credential "
                "Manager. You will not need to select client.json again.",
            )
            return True
        except Exception as error:
            QMessageBox.critical(
                self,
                "Google Drive Connection Failed",
                str(error),
            )
            return False

    def disconnect_google_drive(self):
        answer = QMessageBox.question(
            self,
            "Disconnect Google Drive",
            "Sign out of the connected Google Drive account?\n\n"
            "Your saved encryption recovery key will be kept so previously "
            "created backups can still be restored.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            from google_drive_backup import disconnect_drive

            disconnect_drive(clear_client_config=False)
            self.refresh_drive_status_ui()
            QMessageBox.information(
                self,
                "Google Drive Disconnected",
                "Google Drive sign-in was removed from Windows Credential Manager.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Google Drive Error",
                str(error),
            )

    def choose_sync_backup_folder(self):
        start_dir = self.sync_folder_input.text().strip() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Synced Backup Folder (Google Drive Desktop / OneDrive / USB)",
            start_dir,
        )
        if folder:
            self.sync_folder_input.setText(folder)

    def backup_to_selected_sync_folder(self):
        folder = self.sync_folder_input.text().strip()
        if not folder:
            self.choose_sync_backup_folder()
            folder = self.sync_folder_input.text().strip()
        if not folder:
            return

        try:
            from google_drive_backup import backup_to_sync_folder

            result = backup_to_sync_folder(self.db, folder)
            self.db.set_setting("sync_backup_folder", folder)
            self.db.set_setting("sync_last_backup", datetime.date.today().isoformat())
            QMessageBox.information(
                self,
                "Folder Backup Complete",
                f"Encrypted backup saved successfully:\n{result.get('path', '')}",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Folder Backup Failed",
                str(error),
            )

    def backup_to_google_drive(self):
        try:
            from google_drive_backup import (
                connect_drive,
                get_drive_status,
                upload_encrypted_database_backup,
            )

            status = get_drive_status()
            if not status["connected"] and not status["has_client_config"]:
                client_json_text = self._obtain_drive_client_json_once()
                if not client_json_text:
                    return
                connect_drive(client_json_text=client_json_text)

            result = upload_encrypted_database_backup(self.db)
            self.db.set_setting(
                "google_drive_last_backup",
                datetime.date.today().isoformat(),
            )
            self.refresh_drive_status_ui()
            QMessageBox.information(
                self,
                "Google Drive Backup Complete",
                f"Encrypted backup uploaded:\n{result.get('name', 'Library backup')}",
            )
        except Exception as error:
            self.refresh_drive_status_ui()
            QMessageBox.critical(
                self,
                "Google Drive Backup Failed",
                str(error),
            )

    def save_drive_backup_settings(self):
        try:
            sync_folder = self.sync_folder_input.text().strip()
            if self.auto_folder_backup_checkbox.isChecked() and not sync_folder:
                raise RuntimeError(
                    "Choose a synced backup folder before enabling automatic folder backups."
                )
            for key, value in (
                (
                    "google_drive_auto_backup_enabled",
                    "1" if self.auto_drive_backup_checkbox.isChecked() else "0",
                ),
                ("sync_backup_folder", sync_folder),
                (
                    "sync_auto_backup_enabled",
                    "1" if self.auto_folder_backup_checkbox.isChecked() else "0",
                ),
            ):
                if not self.db.set_setting(key, value):
                    raise RuntimeError(f"Unable to save backup setting '{key}'.")
            QMessageBox.information(
                self,
                "Backup Settings Saved",
                "Automatic backup settings were saved. Backups run once per day "
                "while the application is open for Google Drive (when connected) "
                "and for any configured synced folder.",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Backup Settings Error",
                str(error),
            )

    def restore_from_google_drive(self):
        try:
            from google_drive_backup import (
                connect_drive,
                decrypt_backup_file,
                download_and_decrypt_backup,
                get_drive_status,
                has_backup_encryption_key,
                list_drive_backups,
            )

            status = get_drive_status()
            source_box = QMessageBox(self)
            source_box.setWindowTitle("Restore Encrypted Backup")
            source_box.setIcon(QMessageBox.Icon.Question)
            source_box.setText("Where would you like to restore the encrypted backup from?")
            drive_btn = source_box.addButton(
                "Google Drive Cloud",
                QMessageBox.ButtonRole.AcceptRole,
            )
            local_btn = source_box.addButton(
                "Local / Synced Folder (.clbk)",
                QMessageBox.ButtonRole.ActionRole,
            )
            source_box.addButton(QMessageBox.StandardButton.Cancel)
            source_box.exec()
            clicked = source_box.clickedButton()
            if clicked not in (drive_btn, local_btn):
                return

            if clicked is local_btn:
                start_folder = self.sync_folder_input.text().strip() or ""
                clbk_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Encrypted Library Backup (.clbk)",
                    start_folder,
                    "Encrypted Library Backup (*.clbk);;All Files (*)",
                )
                if not clbk_path:
                    return

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

                recovery_key_file = None
                if not has_backup_encryption_key():
                    recovery_key_file, _ = QFileDialog.getOpenFileName(
                        self,
                        "Select Backup Recovery Key (.txt)",
                        "",
                        "Recovery Key (*.txt);;All Files (*)",
                    )
                    if not recovery_key_file:
                        return

                restored_path = decrypt_backup_file(
                    clbk_path,
                    destination,
                    recovery_key_file or None,
                    getattr(self.db, "database_path", None),
                )
                QMessageBox.information(
                    self,
                    "Backup Restored",
                    "The backup was decrypted and integrity-checked.\n\n"
                    f"Restored database:\n{restored_path}\n\n"
                    "The running application was not changed.",
                )
                return

            if not status["connected"] and not status["has_client_config"]:
                client_json_text = self._obtain_drive_client_json_once()
                if not client_json_text:
                    return
                connect_drive(client_json_text=client_json_text)

            backups = list_drive_backups()
            self.refresh_drive_status_ui()
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

            backup = backups[choices.index(selected)]
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

            recovery_key_file = None
            if not has_backup_encryption_key():
                recovery_key_file, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Backup Recovery Key (.txt)",
                    "",
                    "Recovery Key (*.txt);;All Files (*)",
                )
                if not recovery_key_file:
                    return

            try:
                restored_path = download_and_decrypt_backup(
                    backup["id"],
                    destination,
                    None,
                    recovery_key_file or None,
                    getattr(self.db, "database_path", None),
                )
            except RuntimeError as first_error:
                if recovery_key_file is None and "decrypt" in str(first_error).lower():
                    key_path, _ = QFileDialog.getOpenFileName(
                        self,
                        "Select Backup Recovery Key From Original Computer",
                        "",
                        "Recovery Key (*.txt);;All Files (*)",
                    )
                    if not key_path:
                        raise
                    restored_path = download_and_decrypt_backup(
                        backup["id"],
                        destination,
                        None,
                        key_path,
                        getattr(self.db, "database_path", None),
                    )
                else:
                    raise

            QMessageBox.information(
                self,
                "Backup Restored",
                "The backup was downloaded, decrypted, and integrity-checked.\n\n"
                f"Restored database:\n{restored_path}\n\n"
                "The running application was not changed.",
            )
        except Exception as error:
            self.refresh_drive_status_ui()
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
        header = self.create_section_header(
            "Database Maintenance",
            "Back up your library database and manage circulation logs.",
            accent_role="danger",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="danger")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)

        self.db_backup_row_layout = QGridLayout()
        self.db_backup_row_layout.setHorizontalSpacing(15)
        self.db_backup_row_layout.setVerticalSpacing(10)

        self.db_backup_text_host = QWidget()
        self.db_backup_text_host.setMinimumWidth(0)
        backup_text = QVBoxLayout(self.db_backup_text_host)
        backup_text.setContentsMargins(0, 0, 0, 0)
        backup_text.setSpacing(5)

        backup_title = self.create_field_label("Database Backup")

        backup_desc = QLabel(
            "Create an independent copy of the current SQLite database."
        )
        backup_desc.setObjectName("MutedLabel")
        configure_wrapped_label(backup_desc)

        backup_text.addWidget(backup_title)
        backup_text.addWidget(backup_desc)

        self.db_backup_btn = self.create_button(
            "Create Backup",
            "InfoButton"
        )
        self.db_backup_btn.clicked.connect(self.database_backup)

        self.db_backup_row_layout.addWidget(self.db_backup_text_host, 0, 0)
        self.db_backup_row_layout.addWidget(self.db_backup_btn, 0, 1)
        self.db_backup_row_layout.setColumnStretch(0, 1)

        layout.addLayout(self.db_backup_row_layout)
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
        danger_desc.setObjectName("MutedLabel")
        configure_wrapped_label(danger_desc)

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
        header = self.create_section_header(
            "Administrator Security",
            "Update the administrator password used for "
            "protected system operations.",
            accent_role="indigo",
        )
        self.content_layout.addWidget(header)

        card = self.create_card_frame(accent_role="indigo")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(9)

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
            "WarningButton",
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

            max_renewals = self.db.get_setting(
                "max_renewals",
                self.DEFAULTS["max_renewals"],
            )

            allow_overdue_renewal = self.db.get_setting(
                "allow_overdue_renewal",
                "1" if self.DEFAULTS["allow_overdue_renewal"] else "0",
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
            sync_folder = self.db.get_setting(
                "sync_backup_folder",
                "",
            )
            auto_folder_backup = self.db.get_setting(
                "sync_auto_backup_enabled",
                "0",
            )

            fine = float(fine)
            days = int(days)
            max_renewals_int = max(0, min(int(max_renewals), 20))

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
            self.spin_max_renewals.setValue(max_renewals_int)
            self.chk_allow_overdue_renew.setChecked(
                str(allow_overdue_renewal).casefold()
                in ("1", "true", "yes")
            )
            manager = self._theme_manager or self.get_theme_manager()
            display_theme = theme
            if self._has_loaded_once and manager is not None:
                live_theme = manager.get_theme()
                if live_theme in self.THEMES:
                    display_theme = live_theme
            self.combo_theme.setCurrentText(display_theme)
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
            if hasattr(self, "sync_folder_input"):
                self.sync_folder_input.setText(sync_folder or "")
            if hasattr(self, "auto_folder_backup_checkbox"):
                self.auto_folder_backup_checkbox.setChecked(
                    str(auto_folder_backup).casefold()
                    in ("1", "true", "yes")
                )
            self.refresh_drive_status_ui()

            policies_ok, policy_rows = self.db.get_all_loan_policies()
            if policies_ok and policy_rows:
                policy_map = {
                    str(r[0]).casefold(): (int(r[1]), int(r[2]), float(r[3]))
                    for r in policy_rows
                    if len(r) >= 4
                }
                for role_name, ctrls in self.role_policy_controls.items():
                    vals = policy_map.get(role_name.casefold())
                    if vals:
                        ctrls["max_books"].setValue(vals[0])
                        ctrls["default_days"].setValue(vals[1])
                        ctrls["fine_per_day"].setValue(vals[2])

        except Exception as error:
            QMessageBox.warning(
                self,
                "Settings Loading Error",
                f"Some settings could not be loaded:\n\n{error}"
            )

        finally:
            self._loading_settings = False

        self.update_theme_description()
        if not self._has_loaded_once:
            self._has_loaded_once = True
            manager = self._theme_manager or self.get_theme_manager()
            selected_theme = self.combo_theme.currentText()
            if (
                manager is None
                or selected_theme != manager.get_theme()
                or selected_theme == "System"
            ):
                self.apply_selected_theme(selected_theme)

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

        self.spin_max_renewals.setValue(
            self.DEFAULTS["max_renewals"]
        )

        self.chk_allow_overdue_renew.setChecked(
            self.DEFAULTS["allow_overdue_renewal"]
        )

        for role_name, def_books, def_days, def_fine in self.DEFAULT_ROLE_POLICIES:
            ctrls = self.role_policy_controls.get(role_name)
            if ctrls:
                ctrls["max_books"].setValue(def_books)
                ctrls["default_days"].setValue(def_days)
                ctrls["fine_per_day"].setValue(def_fine)

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

            self.db.set_setting(
                "max_renewals",
                self.spin_max_renewals.value()
            )

            self.db.set_setting(
                "allow_overdue_renewal",
                "1" if self.chk_allow_overdue_renew.isChecked() else "0"
            )

            for role_name, ctrls in self.role_policy_controls.items():
                ok, err = self.db.update_loan_policy(
                    role_name,
                    ctrls["max_books"].value(),
                    ctrls["default_days"].value(),
                    ctrls["fine_per_day"].value(),
                )
                if not ok:
                    raise RuntimeError(f"Role '{role_name}' policy error: {err}")

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
    # RESPONSIVE REFLOW & CLEANUP
    # =========================================================

    def _reflow_role_policy_layout(self, avail_w):
        if not hasattr(self, "role_policy_layout") or not self.role_policy_rows:
            return
        self.role_policy_layout.setHorizontalSpacing(6 if avail_w < 680 else 12)

        role_mode = (
            "table"
            if avail_w >= 900
            else ("three_up" if avail_w >= 680 else "stacked")
        )
        if role_mode == self._role_policy_mode:
            return
        self._role_policy_mode = role_mode

        layout = self.role_policy_layout
        layout.removeWidget(self.role_policy_title)
        layout.removeWidget(self.role_policy_subtitle)
        for hdr in self.role_policy_headers:
            layout.removeWidget(hdr)
            hdr.setHidden(role_mode != "table")
        for row_info in self.role_policy_rows:
            for key in (
                "badge",
                "lbl_books",
                "spin_books",
                "lbl_days",
                "spin_days",
                "lbl_fine",
                "spin_fine",
                "divider",
            ):
                wid = row_info.get(key)
                if wid is not None:
                    layout.removeWidget(wid)

        col_span = 4 if role_mode == "table" else (3 if role_mode == "three_up" else 2)
        layout.addWidget(self.role_policy_title, 0, 0, 1, col_span)
        layout.addWidget(self.role_policy_subtitle, 1, 0, 1, col_span)

        for col_idx in range(4):
            layout.setColumnStretch(col_idx, 0)

        if role_mode == "table":
            for col_idx, hdr in enumerate(self.role_policy_headers):
                hdr.setHidden(False)
                layout.addWidget(hdr, 2, col_idx)
            for idx, row_info in enumerate(self.role_policy_rows):
                grid_row = 3 + idx
                for hidden_key in ("lbl_books", "lbl_days", "lbl_fine", "divider"):
                    wid = row_info.get(hidden_key)
                    if wid is not None:
                        wid.setHidden(True)
                layout.addWidget(row_info["badge"], grid_row, 0)
                layout.addWidget(row_info["spin_books"], grid_row, 1)
                layout.addWidget(row_info["spin_days"], grid_row, 2)
                layout.addWidget(row_info["spin_fine"], grid_row, 3)
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            layout.setColumnStretch(3, 1)
        elif role_mode == "three_up":
            grid_row = 2
            for row_info in self.role_policy_rows:
                layout.addWidget(
                    row_info["badge"],
                    grid_row,
                    0,
                    1,
                    3,
                    Qt.AlignmentFlag.AlignLeft,
                )
                grid_row += 1
                for col_idx, lbl_key in enumerate(("lbl_books", "lbl_days", "lbl_fine")):
                    row_info[lbl_key].setHidden(False)
                    layout.addWidget(row_info[lbl_key], grid_row, col_idx)
                grid_row += 1
                for col_idx, spin_key in enumerate(("spin_books", "spin_days", "spin_fine")):
                    layout.addWidget(row_info[spin_key], grid_row, col_idx)
                grid_row += 1
                if row_info["divider"] is not None:
                    row_info["divider"].setHidden(False)
                    layout.addWidget(row_info["divider"], grid_row, 0, 1, 3)
                    grid_row += 1
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
        else:
            grid_row = 2
            for row_info in self.role_policy_rows:
                layout.addWidget(
                    row_info["badge"],
                    grid_row,
                    0,
                    1,
                    2,
                    Qt.AlignmentFlag.AlignLeft,
                )
                grid_row += 1
                for lbl_key, spin_key in (
                    ("lbl_books", "spin_books"),
                    ("lbl_days", "spin_days"),
                    ("lbl_fine", "spin_fine"),
                ):
                    row_info[lbl_key].setHidden(False)
                    layout.addWidget(row_info[lbl_key], grid_row, 0)
                    layout.addWidget(row_info[spin_key], grid_row, 1)
                    grid_row += 1
                if row_info["divider"] is not None:
                    row_info["divider"].setHidden(False)
                    layout.addWidget(row_info["divider"], grid_row, 0, 1, 2)
                    grid_row += 1
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)

    def _reflow_layout(self):
        if not hasattr(self, "main_layout"):
            return
        sb = self.scroll.verticalScrollBar() if hasattr(self, "scroll") else None
        sb_w = sb.width() if (sb is not None and sb.isVisible()) else 0
        avail_w = max(320, self.width() - sb_w) if self.width() > 0 else 1080

        compact_outer = avail_w < 840
        if compact_outer != self._settings_compact:
            self._settings_compact = compact_outer
            margin = 12 if compact_outer else 16
            v_margin = 8 if compact_outer else 10
            self.main_layout.setContentsMargins(margin, v_margin, margin, 40)

        h_m = 6 if avail_w < 720 else 10
        for tab_layout in getattr(self, "tab_layouts", ()):
            tab_layout.setContentsMargins(h_m, 8, h_m, 10)

        self._reflow_role_policy_layout(avail_w)

        action_stacked = avail_w < 440
        if action_stacked != self._action_bar_stacked and hasattr(self, "action_bar_layout"):
            self._action_bar_stacked = action_stacked
            self.action_bar_layout.removeWidget(self.btn_reset)
            self.action_bar_layout.removeWidget(self.btn_save)
            if action_stacked:
                self.action_bar_layout.addWidget(self.btn_reset, 0, 0)
                self.action_bar_layout.addWidget(self.btn_save, 1, 0)
                self.action_bar_layout.setColumnStretch(0, 1)
                self.action_bar_layout.setColumnStretch(1, 0)
                self.action_bar_layout.setColumnStretch(2, 0)
            else:
                self.action_bar_layout.addWidget(self.btn_reset, 0, 0)
                self.action_bar_layout.addWidget(self.btn_save, 0, 2)
                self.action_bar_layout.setColumnStretch(0, 0)
                self.action_bar_layout.setColumnStretch(1, 1)
                self.action_bar_layout.setColumnStretch(2, 0)

        stacked = avail_w < 580
        if stacked == self._settings_stacked:
            return
        self._settings_stacked = stacked

        if hasattr(self, "appearance_layout"):
            self.appearance_layout.removeWidget(self.appearance_text_host)
            self.appearance_layout.removeWidget(self.combo_theme)
            self.combo_theme.setMinimumWidth(0 if stacked else 160)
            if stacked:
                self.appearance_layout.addWidget(self.appearance_text_host, 0, 0)
                self.appearance_layout.addWidget(self.combo_theme, 1, 0)
            else:
                self.appearance_layout.addWidget(self.appearance_text_host, 0, 0)
                self.appearance_layout.addWidget(self.combo_theme, 0, 1)
            self.appearance_layout.setColumnStretch(0, 1)
            self.appearance_layout.setColumnStretch(1, 0)

        if hasattr(self, "circ_form_layout"):
            circ_widgets = (
                self.circ_fine_label,
                self.spin_daily_fine,
                self.circ_fine_desc,
                self.circ_days_label,
                self.spin_default_days,
                self.circ_days_desc,
                self.circ_max_renew_label,
                self.spin_max_renewals,
                self.circ_max_renew_desc,
                self.chk_allow_overdue_row,
            )
            for w in circ_widgets:
                self.circ_form_layout.removeWidget(w)
            if stacked:
                for row_idx, w in enumerate(circ_widgets):
                    self.circ_form_layout.addWidget(w, row_idx, 0)
                self.circ_form_layout.setColumnStretch(0, 1)
                self.circ_form_layout.setColumnStretch(1, 0)
            else:
                self.circ_form_layout.addWidget(self.circ_fine_label, 0, 0)
                self.circ_form_layout.addWidget(self.circ_days_label, 0, 1)
                self.circ_form_layout.addWidget(self.spin_daily_fine, 1, 0)
                self.circ_form_layout.addWidget(self.spin_default_days, 1, 1)
                self.circ_form_layout.addWidget(self.circ_fine_desc, 2, 0)
                self.circ_form_layout.addWidget(self.circ_days_desc, 2, 1)
                self.circ_form_layout.addWidget(self.circ_max_renew_label, 3, 0, 1, 2)
                self.circ_form_layout.addWidget(self.spin_max_renewals, 4, 0)
                self.circ_form_layout.addWidget(self.circ_max_renew_desc, 4, 1)
                self.circ_form_layout.addWidget(self.chk_allow_overdue_row, 5, 0, 1, 2)
                self.circ_form_layout.setColumnStretch(0, 1)
                self.circ_form_layout.setColumnStretch(1, 1)

        if hasattr(self, "email_form_layout"):
            email_widgets = (
                self.email_sender_label,
                self.email_sender_input,
                self.library_contact_label,
                self.library_contact_input,
                self.smtp_app_password_label,
                self.smtp_app_password_input,
                self.email_actions_host,
                self.email_delivery_row,
                self.email_reminders_row,
                self.email_queue_row,
            )
            for w in email_widgets:
                self.email_form_layout.removeWidget(w)
            if stacked:
                for row_idx, w in enumerate(email_widgets):
                    self.email_form_layout.addWidget(w, row_idx, 0)
                self.email_form_layout.setColumnStretch(0, 1)
                self.email_form_layout.setColumnStretch(1, 0)
            else:
                self.email_form_layout.addWidget(self.email_sender_label, 0, 0)
                self.email_form_layout.addWidget(self.library_contact_label, 0, 1)
                self.email_form_layout.addWidget(self.email_sender_input, 1, 0)
                self.email_form_layout.addWidget(self.library_contact_input, 1, 1)
                self.email_form_layout.addWidget(self.smtp_app_password_label, 2, 0, 1, 2)
                self.email_form_layout.addWidget(self.smtp_app_password_input, 3, 0, 1, 2)
                self.email_form_layout.addWidget(self.email_actions_host, 4, 0, 1, 2)
                self.email_form_layout.addWidget(self.email_delivery_row, 5, 0, 1, 2)
                self.email_form_layout.addWidget(self.email_reminders_row, 6, 0, 1, 2)
                self.email_form_layout.addWidget(self.email_queue_row, 7, 0, 1, 2)
                self.email_form_layout.setColumnStretch(0, 1)
                self.email_form_layout.setColumnStretch(1, 1)

        if hasattr(self, "email_queue_layout"):
            self.email_queue_layout.removeWidget(self.email_queue_status)
            self.email_queue_layout.removeWidget(self.email_queue_btns)
            self.email_queue_layout.addWidget(self.email_queue_status, 0, 0)
            if stacked:
                self.email_queue_layout.addWidget(self.email_queue_btns, 1, 0)
            else:
                self.email_queue_layout.addWidget(self.email_queue_btns, 0, 1)
            self.email_queue_layout.setColumnStretch(0, 1)

        if hasattr(self, "update_actions_layout"):
            self.update_actions_layout.removeWidget(self.update_status_label)
            self.update_actions_layout.removeWidget(self.update_btns_host)
            self.update_actions_layout.addWidget(self.update_status_label, 0, 0)
            if stacked:
                self.update_actions_layout.addWidget(self.update_btns_host, 1, 0)
            else:
                self.update_actions_layout.addWidget(self.update_btns_host, 0, 1)
            self.update_actions_layout.setColumnStretch(0, 1)

        if hasattr(self, "db_backup_row_layout"):
            self.db_backup_row_layout.removeWidget(self.db_backup_text_host)
            self.db_backup_row_layout.removeWidget(self.db_backup_btn)
            self.db_backup_row_layout.addWidget(self.db_backup_text_host, 0, 0)
            if stacked:
                self.db_backup_row_layout.addWidget(self.db_backup_btn, 1, 0)
            else:
                self.db_backup_row_layout.addWidget(self.db_backup_btn, 0, 1)
            self.db_backup_row_layout.setColumnStretch(0, 1)

        for pw_layout, lbl, fld, tgl in self._password_rows:
            pw_layout.removeWidget(lbl)
            pw_layout.removeWidget(fld)
            pw_layout.removeWidget(tgl)
            if stacked:
                lbl.setMinimumWidth(0)
                pw_layout.addWidget(lbl, 0, 0, 1, 2)
                pw_layout.addWidget(fld, 1, 0)
                pw_layout.addWidget(tgl, 1, 1)
                pw_layout.setColumnStretch(0, 1)
                pw_layout.setColumnStretch(1, 0)
                pw_layout.setColumnStretch(2, 0)
            else:
                lbl.setMinimumWidth(145)
                pw_layout.addWidget(lbl, 0, 0)
                pw_layout.addWidget(fld, 0, 1)
                pw_layout.addWidget(tgl, 0, 2)
                pw_layout.setColumnStretch(0, 0)
                pw_layout.setColumnStretch(1, 1)
                pw_layout.setColumnStretch(2, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow_layout()

    def stop_workers(self, wait_ms=1000):
        self._closing = True
        manager = self._theme_manager

        if manager:
            signal = getattr(manager, "themeChanged", None)

            if signal:
                try:
                    signal.disconnect(self.on_global_theme_changed)
                except (TypeError, RuntimeError):
                    pass

        for worker_attr, slot in (
            ("_update_worker", self._on_update_check_finished),
            ("_update_worker", self._on_version_history_finished),
            ("_update_worker", self._on_update_download_finished),
            ("_email_test_worker", self._on_test_email_finished),
        ):
            worker = getattr(self, worker_attr, None)
            if worker is not None:
                signals = getattr(worker, "signals", None)
                finished = getattr(signals, "finished", None)
                if finished is not None:
                    try:
                        finished.disconnect(slot)
                    except (TypeError, RuntimeError):
                        pass

        pool = getattr(self, "_update_pool", None)
        if pool is not None:
            try:
                pool.waitForDone(wait_ms)
            except (RuntimeError, AttributeError):
                pass
        self._update_worker = None
        self._email_test_worker = None

    def closeEvent(self, event):
        self.stop_workers(wait_ms=1000)
        super().closeEvent(event)
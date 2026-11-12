from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
)

from app_version import APP_DEVELOPER_CREDIT, APP_NAME, get_app_version
from ui_responsive import clamp_widget_to_screen


class HelpDialog(QDialog):
    SECTIONS = (
        (
            "Getting Started",
            "Navigation & Quick Desk Actions\n"
            "Use the left sidebar to switch between Dashboard, Books, Users, "
            "Circulation, Reports, and Settings. Click ⚡ Quick Actions in the "
            "bottom-right corner on any page (or press Ctrl+K) to open the "
            "Quick Desk Actions drawer without scrolling.\n\n"
            "Global search\n"
            "Type a book ID, title, author, ISBN, member ID, member name, "
            "or transaction detail in the search field at the top of the "
            "window. Matching books, members, and transactions appear "
            "beneath the field as you type. Select a match to open its "
            "record in the relevant section, or press Enter to open the "
            "first match. Press Ctrl+F to focus the search field.",
        ),
        (
            "Books",
            "Open Books from the sidebar to search and manage the catalog. "
            "Select a row to inspect a book and use the available actions "
            "to add, edit, or remove records. Use Generate Barcode to "
            "create a barcode for a book.\n\n"
            "Catalog files\n"
            "Import CSV or XLSX files to add catalog records or update "
            "stock. Imports merge copies with matching records; review the "
            "import summary for skipped or invalid rows. Export saves the "
            "catalog as CSV.",
        ),
        (
            "Users",
            "Open Users from the sidebar to search or filter the directory. "
            "Select a user to view their profile and available actions, or "
            "use Add User to create a record. CSV and XLSX imports support "
            "batch onboarding; duplicate IDs and conflicting phone numbers "
            "are skipped or reported.\n\n"
            "Select multiple users to issue or return one title for each "
            "selected user. For one user, use Actions to compose a custom "
            "email. Messages are queued for delivery if the mail service "
            "is unavailable. Use Complaint Inbox to review submitted "
            "complaints.",
        ),
        (
            "Batch Circulation",
            "Issue, return, renew, or settle multiple records at once:\n"
            "• In Books, Ctrl-click or Shift-click multiple books, then "
            "open Actions to issue or return the selected titles for one "
            "user.\n"
            "• In Users, select multiple users, then open Actions to issue "
            "or return one title for each selected user.\n"
            "• In Circulation, select multiple transactions to batch renew "
            "active loans, batch return books, or mark selected unpaid "
            "fines as paid.\n\n"
            "Each transaction is processed separately. Review the result "
            "summary for successful and failed items; the selection remains "
            "available so you can check or retry failures.",
        ),
        (
            "Circulation",
            "Issue, renew, and return books\n"
            "Use Issue Book, Return Book, or the Express Desk on the "
            "Dashboard, or open Circulation from the sidebar. On the Express "
            "Desk, press Enter to issue, click ↻ Renew when an active loan "
            "exists for the entered Member ID + Book ID, or press Shift+Enter "
            "to return.\n\n"
            "Recent circulation & Fines\n"
            "Use the Dashboard activity filters to view recent activity, "
            "today's issues, items due today, overdue alerts, or renewed "
            "loans. Renew opens the Advanced Renewal configurator to extend "
            "the due date with preset or custom days, overdue fine handling, "
            "policy limits and overrides, and renewal history tracking. "
            "Inspect opens the selected transaction's full details and "
            "renewal timeline, and View All opens searchable history.\n\n"
            "Pending Fines Desk\n"
            "Click Unpaid Fines on the Dashboard or Pending Fines in "
            "Circulation to inspect unpaid/carried fines, mark individual "
            "or member-wide fines as Paid or Waived, and export CSVs. "
            "Individual loans can also have fines settled from Circulation, "
            "Users (View Assigned Books / Inspector), and Book History.",
        ),
        (
            "Quick Scan",
            "Open Quick Scan from Quick Desk Actions (bottom-right ⚡ Quick Actions) "
            "or press Ctrl+Shift+K from anywhere in the application. Scan with the "
            "camera or a USB barcode scanner, or type the book ID manually. "
            "Enter the member ID/PIN to preview live copy availability, "
            "member role defaults, and active loan status, then choose "
            "Issue Book, Renew Book, or Return Book. If the camera is "
            "unavailable, the USB scanner and manual entry remain available.",
        ),
        (
            "Email && Offline Use",
            "Email notifications are saved to the local queue before "
            "delivery. When the network or mail service is unavailable, "
            "queued messages remain pending and are retried by background "
            "sync. The top-bar badge shows the current sync status. In "
            "Settings, configure the email sender and credentials, test the "
            "configuration, enable due reminders, or select Sync Now.",
        ),
        (
            "Reports && Settings",
            "Use Reports to analyze Books Issued, Books Returned, Loan "
            "Renewals (+extension days), Issued vs. Overdue breakdowns, "
            "and Fine collections/waivers/pending balances, and export "
            "detailed CSV reports.\n\n"
            "Settings contains global circulation/renewal rules, Role-Based "
            "Borrowing & Fine Policies (Max Books, Loan Days, Daily Fine per "
            "role), theme preferences, academic and security options, "
            "database maintenance, email configuration, and Application "
            "Updates. Check for Updates compares the installed version with "
            "the latest stable release; confirm before applying an update "
            "and restarting the app. Review confirmation dialogs before "
            "maintenance or security-sensitive actions.",
        ),
        (
            "Keyboard Shortcuts",
            "General\n"
            "F1 - Open Help\n"
            "Ctrl+K - Open Quick Desk Actions drawer (available on every page)\n"
            "Ctrl+F - Focus global search\n\n"
            "Circulation and records\n"
            "Ctrl+I - Open Issue Book\n"
            "Ctrl+R - Open Return Book\n"
            "Ctrl+B - Add a book\n"
            "Ctrl+U - Add a user\n"
            "Ctrl+G - Open barcode generator\n"
            "Ctrl+Shift+K - Open Quick Scan\n\n"
            "Dashboard\n"
            "Ctrl+H - Open activity history\n"
            "F5 - Refresh dashboard data",
        ),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Help")
        clamp_widget_to_screen(self, 920, 560, min_width=460, min_height=340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        heading = QLabel(f"📖  {APP_NAME} Guide")
        heading.setWordWrap(True)
        heading.setProperty("class", "dialog-heading")
        layout.addWidget(heading)

        introduction = QLabel(
            "Quick guidance for common workflows, batch operations, renewals, fines, and offline email sync."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        app = QApplication.instance()
        tm = app.property("theme_manager") if app is not None else None
        colors = None
        if tm is not None and hasattr(tm, "COLORS"):
            active = tm.get_active_theme() if hasattr(tm, "get_active_theme") else "Dark"
            colors = tm.COLORS.get(active)
        if not colors:
            colors = {
                "surface_alt": "#CFDDF3",
                "muted": "#283D5E",
                "border": "#88A4CE",
                "primary": "#1D4ED8",
                "indigo": "#4338CA",
                "primary_soft": "rgba(29, 78, 216, 0.20)",
                "text": "#0A1628",
            }

        credit = QLabel(
            f"{APP_NAME} v{get_app_version()}  •  {APP_DEVELOPER_CREDIT}"
        )
        credit.setWordWrap(True)
        credit.setStyleSheet(
            f"color: {colors['muted']}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(credit)

        tabs = QTabWidget()
        tabs.setObjectName("HelpTabs")
        tabs.tabBar().setExpanding(False)
        tabs.tabBar().setUsesScrollButtons(True)
        tabs.setStyleSheet(
            f"QTabWidget#HelpTabs QTabBar::tab {{"
            f" background-color: {colors['surface_alt']};"
            f" color: {colors['muted']};"
            f" border: 1px solid {colors['border']};"
            f" border-bottom: none;"
            f" border-top-left-radius: 8px;"
            f" border-top-right-radius: 8px;"
            f" padding: 7px 10px;"
            f" margin-right: 3px;"
            f" font-size: 11px;"
            f" font-weight: 600;"
            f"}}"
            f"QTabWidget#HelpTabs QTabBar::tab:hover {{"
            f" background-color: {colors['primary_soft']};"
            f" color: {colors['text']};"
            f"}}"
            f"QTabWidget#HelpTabs QTabBar::tab:selected {{"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {colors['primary']}, stop:1 {colors['indigo']});"
            f" color: #FFFFFF;"
            f" border-color: {colors['primary']};"
            f" font-weight: 700;"
            f"}}"
        )
        for title, content in self.SECTIONS:
            page = QPlainTextEdit()
            page.setReadOnly(True)
            page.setPlainText(content)
            page.setLineWrapMode(
                QPlainTextEdit.LineWrapMode.WidgetWidth
            )
            tabs.addTab(page, title)
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_button = buttons.button(
            QDialogButtonBox.StandardButton.Close
        )
        if close_button:
            close_button.setObjectName("PrimaryButton")
            close_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(buttons)

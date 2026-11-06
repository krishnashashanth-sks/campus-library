from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
)


class HelpDialog(QDialog):
    SECTIONS = (
        (
            "Getting Started",
            "Navigation\n"
            "Use the left sidebar to switch between Dashboard, Books, Users, "
            "Circulation, Reports, and Settings. The Dashboard summarizes "
            "inventory and loans, provides the Express Desk and Quick "
            "Actions, and lists recent circulation.\n\n"
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
            "Issue or return several records in one operation:\n"
            "• In Books, Ctrl-click or Shift-click multiple books, then "
            "open Actions to issue or return the selected titles for one "
            "user.\n"
            "• In Users, select multiple users, then open Actions to issue "
            "or return one title for each selected user.\n\n"
            "Each transaction is processed separately. Review the result "
            "summary for successful and failed items; the selection remains "
            "available so you can check or retry failures.",
        ),
        (
            "Circulation",
            "Issue and return books\n"
            "Use Issue Book or Return Book on the Dashboard or open "
            "Circulation from the sidebar. Follow the prompts and check "
            "the selected user and book before confirming. The Express "
            "Desk accepts a member ID and book ID; press Enter to issue or "
            "Shift+Enter to return.\n\n"
            "Recent circulation\n"
            "Use the Dashboard activity filters to view recent activity, "
            "today's issues, items due today, or overdue alerts. Return "
            "processes an eligible loan. Inspect opens the selected "
            "transaction's details. View All opens searchable activity "
            "history. The Circulation page's table and inspector show "
            "transaction details and available actions.",
        ),
        (
            "Quick Scan",
            "Open Quick Scan from the Dashboard's Quick Actions or press "
            "Ctrl+Shift+K from anywhere in the application. Scan with the "
            "camera or a USB barcode scanner, or type the book ID manually. "
            "Enter the member ID/PIN, choose a loan duration, then select "
            "Issue Book or Return Book. If the camera is unavailable, the "
            "USB scanner and manual entry remain available.",
        ),
        (
            "Email & Offline Use",
            "Email notifications are saved to the local queue before "
            "delivery. When the network or mail service is unavailable, "
            "queued messages remain pending and are retried by background "
            "sync. The top-bar badge shows the current sync status. In "
            "Settings, configure the email sender and credentials, test the "
            "configuration, enable due reminders, or select Sync Now.",
        ),
        (
            "Reports & Settings",
            "Use Reports to review library activity and available summaries. "
            "Settings contains circulation policies, theme preferences, "
            "academic and security options, database maintenance, email "
            "configuration, and Application Updates. Check for Updates "
            "compares the installed version with the latest stable release; "
            "confirm before applying an update and restarting the app. "
            "Review confirmation dialogs before maintenance or security-"
            "sensitive actions.",
        ),
        (
            "Keyboard Shortcuts",
            "General\n"
            "F1 - Open Help\n"
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
        self.setWindowTitle("Library Management System Help")
        self.setMinimumSize(600, 420)
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        introduction = QLabel(
            "Quick guidance for common workflows and offline email sync."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        tabs = QTabWidget()
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
            close_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(buttons)

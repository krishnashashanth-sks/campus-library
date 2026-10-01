from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QStackedWidget, QPushButton, QLabel
)
from PyQt6.QtGui import QIcon
from pages.bookcatalog_view import CatalogView
from pages.circulation_view import CirculationView
from pages.reports_view import ReportsView
from pages.usermanagement_view import UserManagementView
from pages.settings_view import SettingsView
from pages.dashboard_view import DashboardView

class MainWindow(QMainWindow):
    def __init__(self,db):
        super().__init__()
        self.setWindowTitle("LibCore")
        self.setMinimumSize(900, 600)
        self.setWindowIcon(QIcon("assets/library_icon.png"))
        self.db=db
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # Main vertical layout for the whole window (Topbar on top, Content below)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Topbar
        topbar = QFrame()
        topbar.setFixedHeight(80)
        topbar.setStyleSheet(
            """
            QFrame {
                background-color: #2D333D;
                border-bottom: 2px solid #FFFFFF;
            }
            QLabel {
                font-size: 20px;
                font-weight: bold;
                color: white;
                border: none;
                margin-left: 20px;
            }
            """
        )
        top_layout = QHBoxLayout(topbar)
        top_layout.addWidget(QLabel("LibCore"))
        main_layout.addWidget(topbar)

        # 2. Content Area (Sidebar + Stacked Pages)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            """
            QFrame {
                background-color: #2D333D;
                border-right: 2px solid #FFFFFF;
            }
            QPushButton {
                background-color: #3A414E;
                color: white;
                border: none;
                text-align: left;
                padding-left: 15px;
                font-size: 14px;
                height: 45px;
                margin: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4E5767;
            }
            QPushButton:checked {
                background-color: #1A73E8;
            }
            """
        )

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 10, 0, 10)

        # Initialize Buttons
        self.dashboard_btn = QPushButton("Dashboard")
        self.bookcatalog_btn = QPushButton("Books Details")
        self.usermanagement_btn = QPushButton("Users Details")
        self.circulation_btn = QPushButton("Circulation")
        self.reports_btn = QPushButton("Reports")
        self.settings_btn = QPushButton("Settings")

        buttons = [
            (self.dashboard_btn, 0),
            (self.bookcatalog_btn, 1),
            (self.usermanagement_btn, 2),
            (self.circulation_btn, 3),
            (self.reports_btn, 4),
            (self.settings_btn, 5)
        ]

        for btn, index in buttons:
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=index: self.switch_page(idx))
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()
        content_layout.addWidget(sidebar)

        # 3. Stacked Pages
        self.pages = QStackedWidget()
        self.catalog_view=CatalogView(db)
        self.usermanagement_view=UserManagementView(db)
        self.circulation_view=CirculationView(db)
        self.reports_view=ReportsView(db)
        self.pages.addWidget(DashboardView(db))
        self.pages.addWidget(self.catalog_view)
        self.pages.addWidget(self.usermanagement_view)
        self.pages.addWidget(self.circulation_view)
        self.pages.addWidget(self.reports_view)
        self.pages.addWidget(SettingsView(db))

        content_layout.addWidget(self.pages)
        main_layout.addWidget(content_widget)

        # Set default active page and button
        self.switch_page(0)

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        self.catalog_view.load_books_to_table()
        self.usermanagement_view.load_users_to_table()
        self.circulation_view.load_circulation()
        self.reports_view.load_data()
        # Update button checked states
        buttons = [
            self.dashboard_btn,
            self.bookcatalog_btn,
            self.usermanagement_btn,
            self.circulation_btn,
            self.reports_btn,
            self.settings_btn
        ]
        
        for i, btn in enumerate(buttons):
            btn.setChecked(i == index)
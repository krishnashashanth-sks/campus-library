from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QStackedWidget, QPushButton, QLabel, QSizePolicy,
    QMessageBox
)
from PyQt6.QtGui import QIcon, QFont
from pages.bookcatalog_view import CatalogView
from pages.circulation_view import CirculationView
from pages.reports_view import ReportsView
from pages.usermanagement_view import UserManagementView
from pages.settings_view import SettingsView
from pages.dashboard_view import DashboardView
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

class MainWindow(QMainWindow):
    def __init__(self,db):
        super().__init__()
        self.setWindowTitle("Library Management System")
        self.setMinimumSize(900, 600)
        self.setWindowIcon(QIcon("assets/library_icon.jpeg"))
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
        self.toggle_btn=QPushButton("☰")
        self.toggle_btn.setFixedSize(45,45)
        self.toggle_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3A414E;
                color: white;
                font-size: 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4E5767;
            }
            """
        )
        self.toggle_btn.clicked.connect(self.toggle_sidebar)
        top_layout.addWidget(self.toggle_btn)

        custom_font = QFont("Arial", 16, QFont.Weight.Bold)
        title_label=QLabel("Library Management System")
        title_label.setFont(custom_font)
        top_layout.addWidget(title_label)
        main_layout.addWidget(topbar)

        # 2. Content Area (Sidebar + Stacked Pages)
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(220)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.sidebar.setStyleSheet(
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

        sidebar_layout = QVBoxLayout(self.sidebar)
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
        
        exit_btn=QPushButton("⏻ Exit System")
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.1);
                color: #f87171;
                text-align: left;
                padding: 10px 14px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid rgba(239, 68, 68, 0.2);
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: #ffffff;
            }
        """)
        exit_btn.clicked.connect(self.confirm_exit)
        sidebar_layout.addWidget(exit_btn)
        
        content_layout.addWidget(self.sidebar)

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
    def toggle_sidebar(self):
        self.animation=QPropertyAnimation(self.sidebar,b"maximumWidth")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        current_width=self.sidebar.width()
        if current_width>0:
            self.animation.setStartValue(current_width)
            self.animation.setEndValue(0)
        else:
            self.animation.setStartValue(0)
            self.animation.setEndValue(220)
        self.animation.start()
    def confirm_exit(self):
        reply=QMessageBox.question(
            self,"Exit System",
            "Are you sure you want to close the Library Management System?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply==QMessageBox.StandardButton.Yes:
            exit()
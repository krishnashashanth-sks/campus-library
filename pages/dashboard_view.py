from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, 
    QPushButton, QLabel, QScrollArea, QStyleOption, QStyle, QWidget as QBaseWidget
)
from dialogs import UserDialog, BookDialog, BarcodeGeneratorDialog, QuickScanDialog
from utils import clear_layout

class DashboardView(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.value_labels = {}
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)
        
        # 1. Top Section: 2-Row Grid for Metric Cards (Clean & Balanced)
        self.tiles_grid = QGridLayout()
        self.tiles_grid.setSpacing(16)
        main_layout.addLayout(self.tiles_grid)
        
        # 2. Lower Section: Activity Stream (Left) & Quick Actions (Right)
        lower_layout = QHBoxLayout()
        lower_layout.setSpacing(20)
        
        # --- Activity Stream Container ---
        feed_container = QFrame()
        feed_container.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e2e8f0;
            }
        """)
        feed_layout = QVBoxLayout(feed_container)
        feed_layout.setContentsMargins(20, 20, 20, 20)
        
        feed_title = QLabel("Recent Activity Stream")
        feed_title.setStyleSheet("font-weight: bold; font-size: 15px; color: #0f172a; border: none; background: transparent;")
        feed_layout.addWidget(feed_title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.feed_content_widget = QBaseWidget()
        self.feed_content_widget.setStyleSheet("background: transparent;")
        self.feed_inner_layout = QVBoxLayout(self.feed_content_widget)
        self.feed_inner_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_inner_layout.setSpacing(10)
        self.feed_inner_layout.addStretch()
        
        self.scroll_area.setWidget(self.feed_content_widget)
        feed_layout.addWidget(self.scroll_area)
        
        lower_layout.addWidget(feed_container, stretch=4)

        # --- Sleek Quick Actions Panel (Right) ---
        quick_actions_widget = self.create_quickactions()
        quick_actions_widget.setFixedWidth(240)
        lower_layout.addWidget(quick_actions_widget, stretch=0)
        
        main_layout.addLayout(lower_layout)

        self.setObjectName("DashboardView")
        self.setStyleSheet("""
            #DashboardView {
                background-color: #f8fafc;
            }
        """)

        self.init_ui()
        self.load_activity_log()

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)

    def init_ui(self):
        (
            total_students, 
            total_books, 
            today_issued_books, 
            today_due_books, 
            today_return_books,
            available_books,
            unpaid_fines
        ) = self.db.get_dashboard_details()

        tile_configs = [
            ("Total Users", str(total_students), "Active Users", "#3b82f6", 0, 0),
            ("Total Books", str(total_books), "Total Titles", "#f59e0b", 0, 1),
            ("Available Books", str(available_books), "On Shelf", "#06b6d4", 0, 2),
            ("Issued Today", str(today_issued_books), "Checkouts", "#10b981", 0, 3),
            ("Returned Today", str(today_return_books), "Check-ins", "#61ef44", 1, 0),
            ("Overdue Books", str(today_due_books), "Action Required", "#ef4444", 1, 1),
            ("Unpaid Fines", f"₹{unpaid_fines:.2f}", "Pending Collection", "#ff0000", 1, 2)
        ]

        for title, value, subtitle, color, row, col in tile_configs:
            card = self.create_tile(title, value, subtitle, color)
            self.tiles_grid.addWidget(card, row, col)

    def create_tile(self, title_text, value_text, subtitle_text, accent_color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border-radius: 10px;
                border-left: 4px solid {accent_color};
                border-top: 1px solid #e2e8f0;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(4)

        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600; border: none; background: transparent;")
        card_layout.addWidget(lbl_title)

        lbl_value = QLabel(value_text)
        lbl_value.setStyleSheet("color: #0f172a; font-size: 22px; font-weight: bold; border: none; background: transparent;")
        card_layout.addWidget(lbl_value)

        lbl_subtitle = QLabel(subtitle_text)
        lbl_subtitle.setStyleSheet("color: #94a3b8; font-size: 10px; border: none; background: transparent;")
        card_layout.addWidget(lbl_subtitle)
        
        return card

    def create_quickactions(self):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border-radius: 12px;
                border: 1px solid #334155;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                font-weight: 600;
                font-size: 13px;
                border-radius: 6px;
                border: none;
                padding: 12px 16px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: white;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)

        lbl_title = QLabel("Quick Actions")
        lbl_title.setStyleSheet("background: transparent; font-size: 15px; font-weight: bold; color: #f8fafc; padding: 6px;")
        layout.addWidget(lbl_title)

        adduser_btn = QPushButton("👤  New User")
        addbook_btn = QPushButton("📚  New Book")
        bargenerate_btn = QPushButton("🖨️  Generate Barcode")
        quickscan_btn = QPushButton("📷  Quick Scan")
        refersh_btn = QPushButton("🔄  Refresh Data")

        adduser_btn.clicked.connect(self.open_userform)
        addbook_btn.clicked.connect(self.open_bookform)
        bargenerate_btn.clicked.connect(self.open_bargenerate_form)
        quickscan_btn.clicked.connect(self.open_quick_scan)
        refersh_btn.clicked.connect(self.refersh_dashboard)

        layout.addWidget(adduser_btn)
        layout.addWidget(addbook_btn)
        layout.addWidget(bargenerate_btn)
        layout.addWidget(quickscan_btn)
        layout.addWidget(refersh_btn)
        layout.addStretch()

        return card

    def load_activity_log(self):
        while self.feed_inner_layout.count() > 1:
            item = self.feed_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        success, logs = self.db.get_recent_activity_logs(limit=8)
        
        if success and logs:
            for action_type, book_details, user_name, timestamp in logs:
                event_card = QFrame()
                event_card.setStyleSheet("""
                    QFrame {
                        background-color: #f8fafc;
                        border: 1px solid #e2e8f0;
                        border-radius: 8px;
                        padding: 4px;
                    }
                """)
                card_layout = QHBoxLayout(event_card)
                card_layout.setContentsMargins(12, 8, 12, 8)
            
                lbl_info = QLabel(
                    f"<span style='color: #2563eb; font-weight: bold;'>{action_type}</span> — "
                    f"<b style='color: #0f172a;'>{book_details}</b><br>"
                    f"<span style='color: #64748b; font-size: 11px;'>User: {user_name} &nbsp;|&nbsp; {timestamp}</span>"
                )
                lbl_info.setStyleSheet("border: none; background: transparent;")
                card_layout.addWidget(lbl_info)

                self.feed_inner_layout.insertWidget(self.feed_inner_layout.count() - 1, event_card)
        else:
            empty_card = QFrame()
            empty_card.setStyleSheet("background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px;")
            empty_layout = QVBoxLayout(empty_card)
            empty_lbl = QLabel("✨ No recent circulation activity yet.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #64748b; border: none; background: transparent; font-size: 12px; padding: 20px;")
            empty_layout.addWidget(empty_lbl)
            self.feed_inner_layout.insertWidget(0, empty_card)

    def refersh_dashboard(self):
        while self.tiles_grid.count():
            item = self.tiles_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.init_ui()
        self.load_activity_log()

    def open_userform(self):
        dialog = UserDialog(self.db, parent=self)
        if dialog.exec():
            self.refersh_dashboard()

    def open_bookform(self):
        dialog = BookDialog(self.db, parent=self)
        if dialog.exec():
            self.refersh_dashboard()

    def open_bargenerate_form(self):
        dialog = BarcodeGeneratorDialog(self.db, parent=self)
        dialog.exec()

    def open_quick_scan(self):
        dialog = QuickScanDialog(self.db, parent=self)
        dialog.exec()
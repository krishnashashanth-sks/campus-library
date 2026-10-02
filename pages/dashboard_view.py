from PyQt6.QtWidgets import(
    QWidget,QVBoxLayout,QHBoxLayout,QFrame,QPushButton,QLabel,QStyleOption,QStyle
)
from dialogs import NewUserDialog,NewBookDialog,BarcodeGeneratorDialog,QuickScanDialog
from utils import clear_layout
from PyQt6.QtGui import QPainter

class DashboardView(QWidget):
    def __init__(self,db):
        super().__init__()
        self.db=db
        layout=QVBoxLayout(self)
        
        self.tiles_layout=QHBoxLayout()
        self.tiles_layout.setSpacing(15)
        
        layout.addLayout(self.tiles_layout)
        layout.addStretch()

        bottom_layout=QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.create_quickactions())
        layout.addLayout(bottom_layout)

        self.setObjectName("DashboardView")
        
        self.setStyleSheet("""
            #DashboardView {
                background-color: #f5f6fa;
                background-image: url('assets/dashboard_background.jpg');
            }
        """)

        self.init_ui()

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

        # Core Stats
        self.tiles_layout.addWidget(self.create_tile("Total Users", str(total_students), "Active Users", "#3b82f6"))
        self.tiles_layout.addWidget(self.create_tile("Total Books", str(total_books), "Total Titles", "#f59e0b"))
        self.tiles_layout.addWidget(self.create_tile("Available Books", str(available_books), "On Shelf", "#06b6d4"))
        
        # Today's Circulation
        self.tiles_layout.addWidget(self.create_tile("Issued Today", str(today_issued_books), "Checkouts", "#10b981"))
        self.tiles_layout.addWidget(self.create_tile("Returned Today", str(today_return_books), "Check-ins", "#61ef44"))
        
        # Action Items / Alerts
        self.tiles_layout.addWidget(self.create_tile("Overdue Books", str(today_due_books), "Action Required", "#ef4444"))
        self.tiles_layout.addWidget(self.create_tile("Unpaid Fines", f"₹{unpaid_fines:.2f}", "Pending Collection", "#f43f5e"))
    def create_tile(self,title_text,value_text,subtitle_text,accent_color):
        card=QFrame()
        card.setStyleSheet(f"""
        QFrame{{
        background-color:white;
        border-radius:8px;
        border-left:5px solid {accent_color};
        border-top:1px solid #e2e8f0;
        border-right:1px solid #e2e8f0;
        border-bottom:1px solid #e2e8f0;
        }}
        """)
        card_layout=QVBoxLayout(card)
        card_layout.setContentsMargins(15,15,15,15)

        lbl_title=QLabel(title_text)
        lbl_title.setStyleSheet("color:#64748b;font-size:12px;font-weight:bold;border:none;")
        card_layout.addWidget(lbl_title)

        lbl_value=QLabel(value_text)
        lbl_value.setStyleSheet("color:#0f172a;font=size:24px;font-weight:bold;border:none;")
        card_layout.addWidget(lbl_value)

        lbl_subtitle=QLabel(subtitle_text)
        lbl_subtitle.setStyleSheet("color:#94a3b8;font-size:11px;border:none;")
        card_layout.addWidget(lbl_subtitle)
        
        return card
    def create_quickactions(self):
        card=QFrame()
        card.setStyleSheet("""
    QFrame {
        background-color: #1e293b;
        border: 2px solid white;
        border-radius: 8px;
        min-width: 100px;
        min-height: 30px;
    }
    QPushButton {
        background-color: white;
        color: black;
        font-weight: bold;
        border-radius: 4px;
        border: none;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background-color: black;
        color: white;
    }
""")
        layout=QVBoxLayout(card)

        lbl_title=QLabel("     Quick Actions")
        lbl_title.setStyleSheet("background:black;font-size=30px;font-weight:bold;color:white")
        layout.addWidget(lbl_title)

        adduser_btn=QPushButton("New User")
        addbook_btn=QPushButton("New Book")
        bargenerate_btn=QPushButton("Generate Bar Code")
        quickscan_btn=QPushButton("Quick Scan")
        refersh_btn=QPushButton("Refersh")

        adduser_btn.clicked.connect(self.open_userform)
        addbook_btn.clicked.connect(self.open_bookform)
        refersh_btn.clicked.connect(self.refersh_dashboard)
        bargenerate_btn.clicked.connect(self.open_bargenerate_form)
        quickscan_btn.clicked.connect(self.open_quick_scan)

        layout.addWidget(adduser_btn)
        layout.addWidget(addbook_btn)
        layout.addWidget(bargenerate_btn)
        layout.addWidget(quickscan_btn)
        layout.addWidget(refersh_btn)

        return card
    def open_userform(self):
        dialog=NewUserDialog(self.db)
        dialog.exec()
    def open_bookform(self):
        dialog=NewBookDialog(self.db)
        dialog.exec()
    def refersh_dashboard(self):
        clear_layout(self.tiles_layout)
        self.init_ui()
    def open_bargenerate_form(self):
        dialog=BarcodeGeneratorDialog(self.db)
        dialog.exec()
    def open_quick_scan(self):
        dialog=QuickScanDialog(self.db)
        dialog.exec()
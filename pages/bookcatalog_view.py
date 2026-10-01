from PyQt6.QtWidgets import(
    QWidget,QVBoxLayout,QTableWidget,QTableWidgetItem,QLineEdit,QHBoxLayout,
    QSizePolicy,QHeaderView,QPushButton,QFrame,QLabel,QMessageBox,QFormLayout
)
from dialogs import NewBookDialog,EditBookDialog
from utils import clear_layout

class CatalogView(QWidget):
    def __init__(self,db):
        super().__init__()
        self.db=db
        main_layout=QVBoxLayout(self)

        top_layout=QHBoxLayout()
        self.search_input=QLineEdit()
        self.search_input.setPlaceholderText("Search Book...")
        self.search_input.textChanged.connect(self.filter_books)
        self.addbook_btn=QPushButton("Add New Book")
        self.addbook_btn.setStyleSheet("background-color:#2b7ade;color:white;font-weight:bold;padding:6px;")
        self.addbook_btn.clicked.connect(self.open_form)
        top_layout.addWidget(self.search_input)
        top_layout.addWidget(self.addbook_btn)

        main_layout.addLayout(top_layout)
        bottom_layout=QHBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        header=self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["ID","Title","Author","Publisher","Total Copies","Available Copies","Created At"])
        self.table.cellClicked.connect(self.display_book_details)
        bottom_layout.addWidget(self.table)
        
        self.detail_container=QFrame()
        self.detail_container.setFixedWidth(300)
        self.detail_container.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #f1f5f9;
                font-size: 16px;
                border:none;
            }
        """)
        
        self.detail_layout=QVBoxLayout(self.detail_container)
        bottom_layout.addWidget(self.detail_container,stretch=1)
        main_layout.addLayout(bottom_layout)
        self.load_books_to_table()
        
    def load_books_to_table(self):
        success,rows=self.db.get_books()
        if not success:
            QMessageBox.warning(self,"Failed","Unable to load the books")
            return 
        self.table.setRowCount(len(rows))
        for row_id,row_data in enumerate(rows):
            for col_id,col_data in enumerate(row_data):
                self.table.setItem(row_id,col_id,QTableWidgetItem(str(col_data) or ""))
                
    def open_form(self):
        dialog=NewBookDialog(self.db)
        dialog.data_updated.connect(self.load_books_to_table)
        dialog.exec()
        
    def filter_books(self):
        query=self.search_input.text().lower().strip()
        for row in range(self.table.rowCount()):
            match_found=False
            for col in range(self.table.columnCount()):
                item=self.table.item(row,col)
                if item and query in item.text().lower():
                    match_found=True
                    break
            self.table.setRowHidden(row,not match_found)
            
    def display_book_details(self,row,col):
            id_item=self.table.item(row,0)
            if not id_item:
                return
            book_id=id_item.text()
            success,book=self.db.get_book_details(book_id)
            if not success:
                QMessageBox.warning(self,"Failed",f"Unable to load book ({book_id}) details")
                return
            clear_layout(self.detail_layout)
            
            lbl_header=QLabel("<b>Book Details</b>")
            lbl_header.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold; margin-bottom: 10px;")
            
            self.lbl_id=QLabel(book[0])
            self.lbl_title=QLabel(book[1])
            self.lbl_author=QLabel(book[2])
            self.lbl_publisher=QLabel(book[3])
            self.lbl_total=QLabel(str(book[4]))
            self.lbl_available=QLabel(str(book[5]))
            self.lbl_created=QLabel(book[6])
            for lbl in (self.lbl_id,self.lbl_title,self.lbl_author,self.lbl_publisher,self.lbl_total,self.lbl_available,self.lbl_created):
                lbl.setStyleSheet("qproperty-alignment:'AlignRight | AlignVCenter'; color: #cbd5e1;")
                
            edit_btn=QPushButton("Edit")
            edit_btn.clicked.connect(lambda:self.edit_book(book[0]))
    
            delete_btn=QPushButton("Delete")
            delete_btn.clicked.connect(lambda:self.delete_book(book[0]))
            
            for btn in [edit_btn,delete_btn]:
                btn.setStyleSheet("background-color:#2b7ade;color:white;font-weight:bold;padding:6px;")
    
            self.detail_layout.addWidget(lbl_header)
            form_layout=QFormLayout()
            form_layout.addRow(QLabel("<b>ID:</b>"),self.lbl_id)
            form_layout.addRow(QLabel("<b>Title:</b>"),self.lbl_title)
            form_layout.addRow(QLabel("<b>Author:</b>"),self.lbl_author)
            form_layout.addRow(QLabel("<b>Publisher:</b>"),self.lbl_publisher)
            form_layout.addRow(QLabel("<b>Total:</b>"),self.lbl_total)
            form_layout.addRow(QLabel("<b>Available:</b>"),self.lbl_available)
            form_layout.addRow(QLabel("<b>Created:</b>"),self.lbl_created)
            self.detail_layout.addLayout(form_layout)
            self.detail_layout.addStretch()
            self.detail_layout.addWidget(edit_btn)
            self.detail_layout.addWidget(delete_btn)
            
    def edit_book(self,book_id):
        dialog=EditBookDialog(self.db,book_id)
        dialog.exec()
        self.load_books_to_table()
        
    def delete_book(self,book_id):
        confirm=QMessageBox.question(
            self,"Confirm Deletion",
            f"Are you sure you want to delete book {book_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm==QMessageBox.StandardButton.Yes:
            success,message=self.db.delete_book(book_id)
            if success:
                QMessageBox.warning(self,"Success", message)
                clear_layout(self.detail_layout)
                self.load_books_to_table()
            else:
                QMessageBox.warning(self,"Failed", message)
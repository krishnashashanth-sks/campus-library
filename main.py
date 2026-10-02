import sys
import time
import os
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtGui import QIcon

from mainwindow import MainWindow
from database import LocalDatabase
from dialogs import LoginDialog,CustomSplashScreen

if __name__ == "__main__":
    app = QApplication(sys.argv)

    base_dir = os.path.dirname(__file__)
    
    icon_path = os.path.join(base_dir, "assets/library_icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    image_path = os.path.join(base_dir, "assets/library_icon.jpeg")
    splash = CustomSplashScreen(image_path)
    splash.show()
    app.processEvents()

    time.sleep(2)
    db = LocalDatabase()
    
    splash.close()

    login_dialog = LoginDialog(db)
    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        window = MainWindow(db)
        window.showMaximized()
        sys.exit(app.exec())
    else:
        sys.exit(0)
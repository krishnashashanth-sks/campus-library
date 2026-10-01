import os

def get_appdata_db_path():
    # Gets C:\Users\<Username>\AppData\Roaming\LibraryApp
    app_data_dir = os.path.join(os.getenv('APPDATA'), 'LibCore')
    
    # Create folder if it doesn't exist
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)
        
    return os.path.join(app_data_dir, "local_library.db")
    
def clear_layout(layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    # Remove the widget from the screen and delete it from memory
                    widget.setParent(None)
                    widget.deleteLater()
                elif item.layout() is not None:
                    # If there's a nested layout, clear it recursively
                    clear_layout(item.layout())

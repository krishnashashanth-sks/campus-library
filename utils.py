import os
from PIL import Image

def get_appdata_db_path():
    # Gets C:\Users\<Username>\AppData\Roaming\LibraryApp
    app_data_dir = os.path.join(os.getenv('APPDATA'), 'Library')
    
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

def convert_to_ico(input_image_path, output_ico_path):
    # 1. Open the original high-resolution logo image
    img = Image.open(input_image_path)
    
    # 2. Define standard icon size sets up to maximum crisp 256x256 resolution
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # 3. Save the image as an ICO container packed with all resolutions
    img.save(output_ico_path, format="ICO", sizes=icon_sizes)
    print(f"Success! High-resolution icon created at: {output_ico_path}")
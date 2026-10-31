import os
import sys
from PIL import Image


def get_resource_path(relative_path: str) -> str:
    """Returns the absolute path to project assets for both IDE execution and PyInstaller builds."""
    if hasattr(sys, "_MEIPASS"):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, *relative_path.split("/"))


def get_appdata_db_path() -> str:
    """Returns the path to local_library.db inside AppData/Roaming/Library, creating the folder if needed."""
    base_appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    app_data_dir = os.path.join(base_appdata, "Library")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "local_library.db")


def clear_layout(layout):
    """Recursively removes and deletes all widgets and nested layouts from a QLayout."""
    if layout is None:
        return

    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue

        widget = item.widget()
        child_layout = item.layout()

        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
            child_layout.setParent(None)
            child_layout.deleteLater()


def convert_to_ico(input_image_path: str, output_ico_path: str) -> bool:
    """Converts a source image (JPEG/PNG) into a multi-resolution Windows .ico file."""
    if not os.path.exists(input_image_path):
        print(f"Error: Input image not found at {input_image_path}")
        return False

    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    try:
        with Image.open(input_image_path) as img:
            rgba_img = img.convert("RGBA")
            rgba_img.save(output_ico_path, format="ICO", sizes=icon_sizes)
        print(f"Success! High-resolution icon created at: {output_ico_path}")
        return True
    except Exception as e:
        print(f"Failed to create .ico file: {e}")
        return False
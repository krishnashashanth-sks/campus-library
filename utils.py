import os
import re
import sys
from PIL import Image, ImageChops, ImageFilter


USER_ROLES = {
    "student": "Student",
    "faculty": "Faculty",
    "guest lecturer": "Guest Lecturer",
    "librarian": "Librarian",
    "admin": "Admin",
}


def normalize_user_role(role):
    """Return a canonical supported role, or None for an unknown role."""
    return USER_ROLES.get(str(role or "").strip().casefold())


def is_valid_book_id(book_id):
    return re.fullmatch(r"[0-9]{5}", str(book_id or "").strip()) is not None


def is_valid_phone_number(phone):
    return re.fullmatch(r"[0-9]{10}", str(phone or "").strip()) is not None


def is_valid_user_id(user_id, role):
    value = str(user_id or "").strip()
    canonical_role = normalize_user_role(role)
    if canonical_role == "Student":
        return re.fullmatch(r"[0-9]{5}-[A-Za-z]{2}-[0-9]{3}", value) is not None
    if canonical_role:
        return re.fullmatch(r"[A-Za-z]{2}[0-9]{6}", value) is not None
    return False


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


def rgba_color(color: str, opacity: float) -> str:
    """Return a Qt stylesheet rgba() color from a hex color and opacity."""
    value = str(color).strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Color must be a six-digit hex value.")
    red, green, blue = (
        int(value[index:index + 2], 16)
        for index in (0, 2, 4)
    )
    alpha = round(max(0.0, min(1.0, float(opacity))) * 255)
    return f"rgba({red}, {green}, {blue}, {alpha})"


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


def make_transparent_ico(image_path, output_path):
    # 1. Open the image and ensure it has an Alpha (transparency) channel
    img = Image.open(image_path).convert("RGBA")
    
    # 2. Extract and refine alpha (Removing the dark background)
    # We create a mask where pixels darker than a specific threshold are transparent
    # This keys out the dark outer background while preserving the glowing effects.
    r, g, b, a = img.split()
    
    # Analyze brightness to find where the dark background ends and the icon starts
    # Calculate luminance/brightness: Y = 0.299R + 0.587G + 0.114B
    gray = img.convert("L")
    
    # Create a mask of the background (dark pixels)
    # 12 is a threshold for near-black. Adjust if the glow feels too sharp or cut off.
    mask = gray.point(lambda p: 255 if p > 12 else 0)
    
    # Smooth the edges of the transparency mask (Anti-aliasing / Feathering)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.5))
    
    # Apply the mask to our image
    img.putalpha(mask)
    
    # Crop the image to tightly fit the logo, stripping excess empty space
    # This prevents the icon from looking smaller than standard desktop icons.
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        
    # Resize the image to square proportions if it isn't, and pad with transparency 
    # to maintain the original aspect ratio
    max_dim = max(img.size)
    padded_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
    padded_img.paste(img, ((max_dim - img.size[0]) // 2, (max_dim - img.size[1]) // 2))

    # 3. Save as a multi-resolution .ico file
    # Windows requires icons to be packaged in multiple dimensions 
    # so they appear crisp on the Taskbar (16x16 / 32x32), Desktop (48x48 / 64x64), 
    # and Search/Explorer screens (256x256).
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    padded_img.save(output_path, format="ICO", sizes=icon_sizes)
    print(f"Successfully created native transparent icon: {output_path}")
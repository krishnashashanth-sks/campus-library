"""Shared responsive layout and multi-DPI screen-fitting utilities for PyQt6."""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


def active_screen_geometry(widget=None) -> QRect:
    """Return the available geometry of the screen holding widget or cursor."""
    screen = None

    if widget is not None:
        try:
            screen = widget.screen()
        except Exception:
            screen = None
        if screen is None:
            parent = getattr(widget, "parentWidget", lambda: None)()
            if parent is not None:
                try:
                    screen = parent.screen()
                except Exception:
                    screen = None

    if screen is None:
        try:
            screen = QApplication.screenAt(QCursor.pos())
        except Exception:
            screen = None

    if screen is None:
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()

    if screen is not None:
        avail = screen.availableGeometry()
        if avail.isValid() and avail.width() > 0 and avail.height() > 0:
            return avail

    return QRect(0, 0, 1280, 720)


def clamp_widget_to_screen(
    widget,
    target_width=None,
    target_height=None,
    min_width=None,
    min_height=None,
    max_width_ratio=0.94,
    max_height_ratio=0.92,
    center=True,
) -> QSize:
    """Clamp widget initial and minimum size so it fits smaller displays."""
    avail = active_screen_geometry(widget)
    max_w = max(320, int(avail.width() * max_width_ratio))
    max_h = max(240, int(avail.height() * max_height_ratio))

    cur_min_w = widget.minimumWidth()
    cur_min_h = widget.minimumHeight()
    eff_min_w = min(min_width if min_width is not None else cur_min_w, max_w)
    eff_min_h = min(min_height if min_height is not None else cur_min_h, max_h)
    eff_min_w = max(0, int(eff_min_w))
    eff_min_h = max(0, int(eff_min_h))

    if min_width is not None or min_height is not None or cur_min_w > max_w or cur_min_h > max_h:
        widget.setMinimumSize(eff_min_w, eff_min_h)

    desired_w = int(target_width) if target_width is not None else widget.width()
    desired_h = int(target_height) if target_height is not None else widget.height()
    final_w = min(max_w, max(eff_min_w, desired_w))
    final_h = min(max_h, max(eff_min_h, desired_h))

    if widget.maximumWidth() < final_w or widget.maximumHeight() < final_h:
        # Handle fixed-size dialogs (such as splash screens) safely on tiny displays.
        if widget.maximumWidth() == cur_min_w and cur_min_w > max_w:
            widget.setMaximumWidth(max_w)
        if widget.maximumHeight() == cur_min_h and cur_min_h > max_h:
            widget.setMaximumHeight(max_h)

    widget.resize(final_w, final_h)

    if center and (isinstance(widget, QDialog) or widget.isWindow()):
        x = avail.x() + max(0, (avail.width() - final_w) // 2)
        y = avail.y() + max(0, (avail.height() - final_h) // 2)
        widget.move(x, y)

    return QSize(final_w, final_h)


def wrap_in_scroll_area(
    content_widget,
    horizontal_policy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
    vertical_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    object_name="ResponsiveScrollArea",
) -> QScrollArea:
    """Wrap content_widget inside a frameless, transparent QScrollArea."""
    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(horizontal_policy)
    scroll.setVerticalScrollBarPolicy(vertical_policy)
    scroll.setMinimumWidth(0)
    scroll.setMinimumHeight(0)
    scroll.viewport().setObjectName(f"{object_name}Viewport")
    scroll.setAutoFillBackground(False)
    scroll.viewport().setAutoFillBackground(False)
    content_widget.setAutoFillBackground(False)
    content_widget.setMinimumWidth(0)
    scroll.setStyleSheet(
        f"QScrollArea#{object_name}, "
        f"QWidget#{object_name}Viewport {{ background: transparent; border: none; }}"
    )
    scroll.setWidget(content_widget)
    return scroll


def make_scrollable_tab(
    tab_widget,
    title,
    margins=(8, 8, 8, 8),
    spacing=8,
    object_name="InspectorTabScroll",
):
    """Add a vertically scrollable tab returning (scroll_widget, inner_layout, content_widget).

    Returning `scroll_widget` as the tab widget reference guarantees calls like
    `tab_widget.setCurrentWidget(tab_ref)` continue to work seamlessly while
    `inner_layout` targets the scrollable content container inside it.
    """
    content = QWidget()
    content.setObjectName(f"{object_name}Content")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    scroll = wrap_in_scroll_area(content, object_name=object_name)
    tab_widget.addTab(scroll, title)
    return scroll, layout, content


def configure_inspector_form(
    form_layout: QFormLayout,
    horizontal_spacing: int = 10,
    vertical_spacing: int = 7,
) -> None:
    """Configure a QFormLayout to wrap long key/value rows cleanly in narrow panels."""
    form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form_layout.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
    )
    form_layout.setLabelAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    form_layout.setFormAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    if horizontal_spacing is not None:
        form_layout.setHorizontalSpacing(horizontal_spacing)
    if vertical_spacing is not None:
        form_layout.setVerticalSpacing(vertical_spacing)


def configure_wrapped_label(label, expanding_width=True):
    """Allow a QLabel to wrap across multiple lines and shrink safely in narrow layouts."""
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    h_policy = (
        QSizePolicy.Policy.Expanding
        if expanding_width
        else QSizePolicy.Policy.Preferred
    )
    label.setSizePolicy(h_policy, QSizePolicy.Policy.Preferred)
    return label


def configure_inspector_button(button: QPushButton) -> QPushButton:
    """Prevent long button captions from forcing an inspector wider than its panel."""
    button.setMinimumWidth(0)
    button.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        QSizePolicy.Policy.Fixed,
    )
    return button


def sync_responsive_splitter(
    splitter: QSplitter,
    detail_container: QWidget,
    available_width: int,
    breakpoint: int = 960,
    max_panel_width: int = 360,
    min_panel_width: int = 240,
    min_panel_height: int = 190,
    current_vertical=None,
):
    """Switch a [table, inspector] QSplitter between horizontal and vertical layouts.

    Returns the resulting `is_vertical` boolean so callers can track state changes
    without resetting user splitter handles unnecessarily.
    """
    is_vertical = available_width < breakpoint
    if is_vertical == current_vertical:
        return current_vertical

    if is_vertical:
        splitter.setOrientation(Qt.Orientation.Vertical)
        detail_container.setMinimumWidth(0)
        detail_container.setMaximumWidth(16777215)
        detail_container.setMinimumHeight(min_panel_height)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([300, 260])
    else:
        splitter.setOrientation(Qt.Orientation.Horizontal)
        detail_container.setMinimumWidth(min_panel_width)
        detail_container.setMaximumWidth(max_panel_width)
        detail_container.setMinimumHeight(0)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        side_w = min(max_panel_width, max(min_panel_width, int(available_width * 0.30)))
        splitter.setSizes([max(360, available_width - side_w), side_w])

    return is_vertical


class FlowLayout(QLayout):
    """Responsive wrapping layout for buttons, filter pills, and action bars."""

    def __init__(self, parent=None, margin=-1, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._items = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        if margin >= 0:
            self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item is not None:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, max(1, width), 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(max(0, left) + max(0, right), max(0, top) + max(0, bottom))
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        avail_w = max(1, effective.width())
        rows = []
        current_row = []
        line_height = 0

        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisibleTo(wid.parentWidget() or wid):
                continue
            item_size = item.sizeHint()
            item_w = min(item_size.width(), avail_w)
            item_h = item_size.height()
            if item.hasHeightForWidth() and item_w < item_size.width():
                item_h = item.heightForWidth(item_w)

            next_x = x + item_w + self._h_space
            if next_x - self._h_space > effective.right() + 1 and line_height > 0:
                rows.append((y, line_height, current_row))
                current_row = []
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + item_w + self._h_space
                line_height = 0

            current_row.append((item, x, item_w, item_h))
            x = next_x
            line_height = max(line_height, item_h)

        if current_row:
            rows.append((y, line_height, current_row))

        if not test_only:
            for row_y, row_height, row_items in rows:
                for item, item_x, item_w, item_h in row_items:
                    offset_y = max(0, (row_height - item_h) // 2)
                    item.setGeometry(
                        QRect(QPoint(item_x, row_y + offset_y), QSize(item_w, item_h))
                    )

        return y + line_height - rect.y() + bottom


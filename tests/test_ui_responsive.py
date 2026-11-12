import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import database
import ui_responsive
from dialogs import (
    AdminPasswordRecoveryDialog,
    BarcodeGeneratorDialog,
    BatchCirculationDialog,
    BookDialog,
    BookHistoryDialog,
    ComplaintDialog,
    ComplaintManagementDialog,
    CustomEmailDialog,
    CustomSplashScreen,
    DepartmentManagerDialog,
    EditDepartmentDialog,
    EmailQueueManagementDialog,
    IssueBookDialog,
    LoginDialog,
    PendingFinesDialog,
    QuickScanDialog,
    RecoveryCodeSetupDialog,
    RenewLoanDialog,
    ReturnBookDialog,
    UserDialog,
    VersionManagerDialog,
    ViewBooksDialog,
    markdown_to_plain_text,
    markdown_to_themed_html,
)
from help_dialog import HelpDialog
from mainwindow import MainWindow
from pages.dashboard_view import (
    ActivityDetailDialog,
    ActivityHistoryDialog,
    CirculationAnalyticsWidget,
    MetricDetailDialog,
)
from pages.settings_view import SettingsView
from theme_manager import ThemeManager


REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_ui_responsive"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=3):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


def _create_populated_db(tmp_dir):
    db_path = os.path.join(tmp_dir, "responsive_test.db")
    db = database.LocalDatabase(db_path)
    try:
        ok, msg = db.insert_book(
            "10001",
            "Algorithms and Data Structures in Python with Extended Subtitle for Narrow Panels",
            "Robert Sedgewick & Kevin Wayne",
            "Academic Computing Press",
            5,
            5,
        )
        assert ok, msg

        ok, msg = db.insert_book(
            "10002",
            "Distributed Systems Architecture",
            "Martin Kleppmann",
            "Systems Engineering House",
            3,
            3,
        )
        assert ok, msg

        ok, msg = db.insert_user(
            "24001-CS-001",
            "Aarav Sharma",
            "9876543210",
            "Student",
            "Computer Science & Engineering",
            "aarav@example.com",
        )
        assert ok, msg

        ok, msg = db.insert_user(
            "100201",
            "Dr. Diya Nair",
            "9876543211",
            "Faculty",
            "Electronics & Communication Engineering",
            "diya@example.com",
        )
        assert ok, msg

        ok, msg = db.issue_book("10001", "24001-CS-001", 14)
        assert ok, msg

        loan_id = db.get_active_loan_id("10001", "24001-CS-001")
        assert loan_id is not None
        ok, _details, msg = db.renew_loan(loan_id, extend_days=7, base_mode="DUE_DATE")
        assert ok, msg

        ok, msg = db.issue_book("10002", "100201", 14)
        assert ok, msg

        overdue_due = (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y-%m-%d 18:00")
        db.conn.execute(
            "UPDATE circulation_logs SET due_date = ?, fine_amount = 15.0 WHERE book_id = ? AND user_id = ?",
            (overdue_due, "10002", "100201"),
        )
        db.conn.commit()

        ok, _complaint = db.create_complaint(
            "24001-CS-001",
            "Scanner latency check",
            "Barcode scanner needed two scans on glare-heavy jacket.",
        )
        assert ok

        db.enqueue_email("aarav@example.com", "Library Notice", "Sample queued body.")
        return db
    except Exception:
        db.close()
        raise


class ResponsiveLayoutUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_high_dpi_policy_and_flow_layout(self):
        self.assertEqual(
            QApplication.highDpiScaleFactorRoundingPolicy(),
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
        )

        host = QWidget()
        layout = ui_responsive.FlowLayout(host, margin=4, h_spacing=6, v_spacing=6)
        buttons = []
        for idx in range(5):
            btn = QPushButton(f"Action Button {idx}")
            btn.setMinimumWidth(90)
            layout.addWidget(btn)
            buttons.append(btn)

        tall_h = layout.heightForWidth(220)
        wide_h = layout.heightForWidth(650)
        self.assertGreater(tall_h, wide_h)
        host.deleteLater()

    def test_inspector_helpers_wrap_without_zero_collapse(self):
        host = QWidget()
        host.resize(260, 400)
        outer = QVBoxLayout(host)

        lbl = QLabel(
            "Very Long Publisher & Classification Metadata Line That Must Wrap "
            "Inside A Narrow Laptop Control Center Panel Without Overflowing"
        )
        ui_responsive.configure_wrapped_label(lbl)
        btn = QPushButton("Open Extended Book Circulation Audit & Actions")
        ui_responsive.configure_inspector_button(btn)
        outer.addWidget(lbl)
        outer.addWidget(btn)

        host.show()
        _pump(2)

        self.assertGreater(lbl.width(), 100)
        self.assertLessEqual(lbl.width(), host.width())
        self.assertGreater(lbl.height(), 20)
        self.assertLessEqual(btn.width(), host.width())
        host.close()
        host.deleteLater()


class MainWindowAndControlCenterResponsiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = _create_populated_db(cls.tmp.name)
        cls.window = MainWindow(cls.db)
        cls.window.show()
        _pump(4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.window.email_sync_manager.sync_timer.stop()
            cls.window.email_sync_manager.status_timer.stop()
            cls.window.email_sync_manager.thread_pool.waitForDone(3000)
        except Exception:
            pass
        cls.window.close()
        cls.window.deleteLater()
        _pump(3)
        cls.db.close()
        cls.tmp.cleanup()

    def _assert_topbar_contained(self, window_width):
        self.assertFalse(hasattr(self.window, "quick_actions_button"))
        topbar_w = self.window.topbar.width()
        for child in (
            self.window.toggle_btn,
            self.window.title_label,
            self.window.version_badge,
            self.window.global_search_input,
            self.window.issue_header_button,
            self.window.return_header_button,
            self.window.theme_button,
            self.window.help_button,
            self.window.status_badge,
        ):
            if not child.isVisible():
                continue
            geom = child.geometry()
            self.assertGreaterEqual(
                geom.x(),
                0,
                f"{child.objectName()} clipped on left at width={window_width}: {geom}",
            )
            self.assertLessEqual(
                geom.right(),
                topbar_w + 1,
                f"{child.objectName()} overflowed TopBar right edge at width={window_width}: {geom} vs {topbar_w}",
            )
            self.assertGreater(
                geom.width(),
                0,
                f"{child.objectName()} has zero width at width={window_width}",
            )

    def _assert_page_control_center(self, page, name, small_size=(910, 512), wide_size=(1440, 900)):
        # Below 680px width the splitter stacks vertically so Control Center keeps readable width.
        self.window.resize(660, 700)
        _pump(4)
        self.assertEqual(
            page.content_splitter.orientation(),
            Qt.Orientation.Vertical,
            f"{name} splitter should stack vertically on ultra-narrow display (660, 700)",
        )

        # Standard desktop / laptop widths keep table + Control Center side-by-side without outer page scroll
        for desktop_size in ((1280, 820), (1366, 768)):
            self.window.resize(*desktop_size)
            _pump(4)
            self.assertEqual(
                page.table.horizontalScrollBar().maximum(),
                0,
                f"{name} table unexpectedly needed horizontal scroll at {desktop_size}",
            )

        for narrow_size in ((800, 520), small_size):
            self.window.resize(*narrow_size)
            _pump(4)
            if page.table.rowCount() > 0:
                page.table.selectRow(0)
                _pump(3)

            self.assertTrue(
                page.detail_container.isVisible(),
                f"{name} Control Center was hidden on small display {narrow_size}",
            )
            self.assertEqual(
                page.content_splitter.orientation(),
                Qt.Orientation.Horizontal,
                f"{name} splitter should sit side-by-side at {narrow_size}",
            )
            self.assertIsInstance(page.tab_overview, QScrollArea)
            self.assertIsInstance(page.tab_actions, QScrollArea)
            self.assertGreater(page.inspector_title.width(), 80)
            self.assertGreater(page.inspector_title.height(), 0)
            self.assertGreaterEqual(
                page.detail_container.height(),
                120,
                f"{name} Control Center height collapsed to {page.detail_container.height()}",
            )

            inspector_w = page.detail_container.width()
            page.tab_widget.setCurrentWidget(page.tab_overview)
            _pump(4)
            for lbl in page.tab_overview.findChildren(QLabel):
                if lbl.isVisibleTo(page.detail_container):
                    self.assertLessEqual(
                        lbl.width(),
                        inspector_w,
                        f"{name} overview label '{lbl.text()[:40]}' wider than Control Center at {narrow_size}",
                    )
                    self.assertGreater(lbl.height(), 0)

            page.tab_widget.setCurrentWidget(page.tab_actions)
            _pump(4)
            for btn in page.tab_actions.findChildren(QPushButton):
                if btn.isVisibleTo(page.detail_container):
                    self.assertLessEqual(
                        btn.width(),
                        inspector_w,
                        f"{name} action button '{btn.text()}' wider than Control Center at {narrow_size}",
                    )
                    self.assertGreater(btn.height(), 0)
            page.tab_widget.setCurrentWidget(page.tab_overview)
            _pump(2)

        # Standard desktop / wide viewport + filter count alignment check
        self.window.resize(*wide_size)
        _pump(4)
        self.assertTrue(page.detail_container.isVisible())
        self.assertEqual(
            page.content_splitter.orientation(),
            Qt.Orientation.Horizontal,
            f"{name} splitter should sit side-by-side on wide display {wide_size}",
        )
        filters_host = page.lbl_count.parentWidget().findChild(QWidget, "FilterButtonsHost")
        self.assertIsNotNone(filters_host)
        count_center_y = page.lbl_count.mapTo(page, page.lbl_count.rect().center()).y()
        host_center_y = filters_host.mapTo(page, filters_host.rect().center()).y()
        self.assertLessEqual(
            abs(count_center_y - host_center_y),
            3,
            f"{name} filter bar count label misaligned vertically ({count_center_y} vs {host_center_y})",
        )
        self.assertEqual(page.lbl_count.height(), 28)
        self.assertGreater(page.lbl_count.x(), filters_host.geometry().right())

    def test_mainwindow_fits_active_screen_and_adapts_shell(self):
        avail = ui_responsive.active_screen_geometry(self.window)
        min_sz = self.window.minimumSize()
        self.assertLessEqual(min_sz.width(), avail.width())
        self.assertLessEqual(min_sz.height(), avail.height())

        for size in ((910, 512), (1024, 576), (800, 520)):
            self.window.resize(*size)
            _pump(3)
            self.assertFalse(
                self.window.sidebar_expanded,
                f"Sidebar should auto-collapse at {size}",
            )
            self.assertEqual(
                self.window.sidebar.width(),
                MainWindow.SIDEBAR_COLLAPSED_WIDTH,
            )
            self._assert_topbar_contained(size[0])

        self.window.resize(1440, 900)
        _pump(3)
        self.assertTrue(self.window.sidebar_expanded)
        self.assertTrue(self.window.version_badge.isVisible())
        self._assert_topbar_contained(1440)

    def test_all_pages_render_and_control_centers_stay_visible(self):
        # 0: DashboardView + analytics stacking
        self.window.switch_page(0)
        self.window.resize(910, 512)
        _pump(4)
        self.assertTrue(self.window.dashboard_view.activity_table.isVisible())
        self.assertGreater(self.window.dashboard_view.activity_table.height(), 100)

        chart = CirculationAnalyticsWidget()
        chart.set_data(
            [{"label": d, "issued": i + 1, "returned": i} for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])],
            [
                {"label": "Available on Shelf", "count": 6},
                {"label": "Currently Issued", "count": 1},
                {"label": "Due Today / Reserved", "count": 0},
                {"label": "Overdue / Missing", "count": 1},
            ],
        )
        for chart_size, expected_stacked in (
            (QSize(380, 340), True),
            (QSize(720, 220), False),
        ):
            chart.resize(chart_size)
            chart.show()
            _pump(2)
            self.assertIs(chart._is_stacked, expected_stacked)
            pixmap = chart.grab()
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.size(), chart_size)
        self.assertLessEqual(chart.minimumSizeHint().height(), 220)
        chart.close()
        chart.deleteLater()

        # 1: Book Control Center (CatalogView)
        self.window.switch_page(1)
        self._assert_page_control_center(self.window.catalog_view, "Book Control Center")

        # 2: User Control Center (UserManagementView) - verify ClickableMetricCard.set_value & no error dialog
        with mock.patch("pages.usermanagement_view.QMessageBox.critical") as mock_crit:
            self.window.usermanagement_view.load_users_to_table()
            mock_crit.assert_not_called()
        self.assertEqual(self.window.usermanagement_view.stat_total.lbl_value.text(), "2")
        self.window.switch_page(2)
        self._assert_page_control_center(self.window.usermanagement_view, "User Control Center")

        # 3: Transaction Control Center (CirculationView)
        self.window.switch_page(3)
        self._assert_page_control_center(self.window.circulation_view, "Transaction Control Center")

        # 4: ReportsView
        self.window.switch_page(4)
        for size in ((1092, 614), (1280, 720), (1366, 768), (1280, 820)):
            self.window.resize(*size)
            _pump(3)
            self.assertEqual(
                self.window.reports_view.scroll_area.verticalScrollBar().maximum(),
                0,
                f"Reports scrolled vertically at desktop size {size}",
            )
        for size in ((800, 520), (910, 512), (1440, 900)):
            self.window.resize(*size)
            _pump(3)
            self.assertTrue(self.window.reports_view.chart_view.isVisible())
            self.assertGreater(self.window.reports_view.graph_title.height(), 0)
            self.assertGreater(self.window.reports_view.hover_readout.height(), 0)
            reports_vp_w = self.window.reports_view.scroll_area.viewport().width()
            self.assertLessEqual(
                self.window.reports_view.content.width(),
                reports_vp_w + 2,
                f"Reports content wider than viewport at {size}: {self.window.reports_view.content.width()} vs {reports_vp_w}",
            )
            for key, card in self.window.reports_view.cards.items():
                self.assertGreater(card.width(), 60, f"Reports card {key} collapsed horizontally at {size}")
                self.assertGreater(card.height(), 60, f"Reports card {key} collapsed vertically at {size}")
                self.assertLessEqual(
                    card.geometry().right(),
                    self.window.reports_view.content.width(),
                    f"Reports card {key} overflowed at {size}",
                )

        # 5: SettingsView (4 tabs, collapsed sidebar + expanded sidebar narrow check + desktop)
        self.window.switch_page(5)
        settings_page = self.window.settings_view
        self.assertEqual(settings_page.settings_tabs.count(), 4)
        for size, expected_role_mode in (
            ((800, 520), "three_up"),
            ((910, 512), "three_up"),
            ((1440, 900), "table"),
        ):
            self.window.resize(*size)
            _pump(4)
            self.assertTrue(settings_page.btn_save.isVisible())
            self.assertGreater(settings_page.btn_save.height(), 0)
            self.assertEqual(settings_page._role_policy_mode, expected_role_mode)
            for tab_idx in range(settings_page.settings_tabs.count()):
                settings_page.settings_tabs.setCurrentIndex(tab_idx)
                _pump(2)
                viewport_w = settings_page.scroll.viewport().width()
                self.assertLessEqual(
                    settings_page.container.width(),
                    viewport_w + 2,
                    f"Settings tab {tab_idx} content wider than viewport at {size}: {settings_page.container.width()} vs {viewport_w}",
                )
        settings_page.settings_tabs.setCurrentIndex(0)
        _pump(2)

        # Verify SettingsView also stays within viewport if sidebar is manually expanded on 800x520
        self.window.resize(800, 520)
        self.window._set_sidebar_expanded(True, automatic=False)
        _pump(4)
        self.assertEqual(settings_page._role_policy_mode, "stacked")
        narrow_viewport_w = settings_page.scroll.viewport().width()
        self.assertLessEqual(
            settings_page.container.width(),
            narrow_viewport_w + 2,
            f"Settings content wider than viewport with expanded sidebar at (800, 520): {settings_page.container.width()} vs {narrow_viewport_w}",
        )
        self.window._set_sidebar_expanded(False, automatic=True)
        _pump(2)

    def test_quick_actions_fab_and_drawer_across_all_pages(self):
        def _global_rect(widget):
            return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())

        pages = [
            ("Dashboard", 0),
            ("Books Details", 1),
            ("Users Details", 2),
            ("Circulation", 3),
            ("Reports", 4),
            ("Settings", 5),
        ]
        self.assertFalse(hasattr(self.window, "quick_actions_button"))
        self.assertTrue(hasattr(self.window, "quick_actions_fab"))
        fab = self.window.quick_actions_fab
        self.assertFalse(fab.isWindow())
        self.assertTrue(fab.isCheckable())
        self.assertFalse(fab.isChecked())

        try:
            for size in ((1280, 820), (1366, 768), (800, 520)):
                self.window.resize(*size)
                _pump(3)
                expected_compact = size[0] < 900
                for label, idx in pages:
                    self.window.switch_page(idx)
                    _pump(3)
                    page = self.window.page_views[idx]
                    self.assertFalse(hasattr(page, "quick_actions_btn"))
                    self.assertFalse(hasattr(page, "quick_actions_requested"))
                    self.assertTrue(
                        fab.isVisible(),
                        f"quick_actions_fab not visible on {label} at {size}",
                    )
                    self.assertFalse(fab.isChecked())
                    self.assertGreaterEqual(fab.x(), 0)
                    self.assertGreaterEqual(fab.y(), self.window.topbar.height())
                    self.assertLessEqual(fab.geometry().right(), self.window.width())
                    self.assertLessEqual(fab.geometry().bottom(), self.window.height())

                    if expected_compact:
                        self.assertEqual(fab.text(), "⚡")
                        self.assertLessEqual(fab.width(), 40)
                    else:
                        self.assertEqual(fab.text(), "⚡ Quick Actions")

                    fab_rect = _global_rect(fab)
                    if idx == 0 and size[0] >= 1200:
                        self.assertFalse(
                            fab_rect.intersects(
                                _global_rect(self.window.dashboard_view.activity_table)
                            ),
                            f"quick_actions_fab overlapped Dashboard activity_table at {size}",
                        )
                    elif idx == 4 and size[0] >= 1200:
                        sb = self.window.reports_view.scroll_area.verticalScrollBar()
                        sb.setValue(sb.maximum())
                        _pump(1)
                        self.assertFalse(
                            fab_rect.intersects(
                                _global_rect(self.window.reports_view.graph_frame)
                            ),
                            f"quick_actions_fab overlapped Reports graph_frame at {size}",
                        )
                        sb.setValue(0)
                    elif idx == 5:
                        self.assertFalse(
                            fab_rect.intersects(
                                _global_rect(self.window.settings_view.btn_save)
                            ),
                            f"quick_actions_fab overlapped Settings btn_save at {size}",
                        )

                    top_count_before = len(QApplication.topLevelWidgets())
                    fab.click()
                    _pump(3)
                    popup = self.window.quick_actions_popup
                    self.assertTrue(
                        popup.isVisible(),
                        f"Quick Desk Actions drawer failed to open from {label} at {size}",
                    )
                    self.assertTrue(fab.isChecked())
                    self.assertFalse(
                        popup.isWindow(),
                        "Quick Desk Actions drawer must be an in-window child widget",
                    )
                    self.assertEqual(
                        [w for w in QApplication.topLevelWidgets() if w.isVisible()],
                        [self.window],
                        f"Opening Quick Desk Actions on {label} created unexpected visible window",
                    )
                    self.assertEqual(
                        len(QApplication.topLevelWidgets()),
                        top_count_before,
                        f"Opening Quick Desk Actions on {label} created unexpected top-level widget",
                    )
                    self.assertGreaterEqual(popup.x(), 0)
                    self.assertGreaterEqual(popup.y(), self.window.topbar.height())
                    self.assertLessEqual(popup.geometry().right(), self.window.width())
                    self.assertLess(popup.geometry().bottom(), fab.y())
                    self.assertLessEqual(popup.width(), 284)

                    if idx == 0 and size[1] >= 760:
                        kpi_card = self.window.dashboard_view.metric_widgets["unpaid_fines"]
                        self.assertGreater(
                            _global_rect(popup).top(),
                            _global_rect(kpi_card).bottom(),
                            f"Quick Desk Actions drawer overlapped KPI row at {size}",
                        )

                    rows = popup.findChildren(QPushButton, "QuickActionRow")
                    self.assertEqual(
                        len(rows),
                        8 if idx == 0 else 7,
                        f"Expected compact classic action count on {label}",
                    )
                    self.assertEqual(
                        self.window.quick_actions_page_badge.text(),
                        label,
                    )
                    if size[1] >= 800 and idx == 0:
                        self.assertEqual(
                            self.window.quick_actions_scroll.verticalScrollBar().maximum(),
                            0,
                            f"Quick Desk Actions drawer scrolled internally at {size}",
                        )

                    QTest.keyClick(popup, Qt.Key.Key_Escape)
                    _pump(2)
                    self.assertFalse(popup.isVisible())
                    self.assertFalse(fab.isChecked())

            # Outside click, page switch, and action click dismiss drawer cleanly
            self.window.resize(1280, 820)
            self.window.switch_page(0)
            _pump(3)
            fab.click()
            _pump(2)
            self.assertTrue(self.window.quick_actions_popup.isVisible())
            QTest.mouseClick(
                self.window.dashboard_view,
                Qt.MouseButton.LeftButton,
                pos=QPoint(30, 30),
            )
            _pump(2)
            self.assertFalse(self.window.quick_actions_popup.isVisible())
            self.assertFalse(fab.isChecked())

            fab.click()
            _pump(2)
            self.assertTrue(self.window.quick_actions_popup.isVisible())
            self.window.switch_page(1)
            _pump(2)
            self.assertFalse(self.window.quick_actions_popup.isVisible())
            self.assertFalse(fab.isChecked())

            fab.click()
            _pump(2)
            refresh_btn = next(
                btn
                for btn in self.window.quick_actions_popup.findChildren(
                    QPushButton, "QuickActionRow"
                )
                if btn.accessibleName() == "Refresh Books"
            )
            refresh_btn.click()
            _pump(2)
            self.assertFalse(self.window.quick_actions_popup.isVisible())
            self.assertFalse(fab.isChecked())
        finally:
            self.window.hide_quick_actions_popup()
            self.window.switch_page(0)
            _pump(2)

    def test_dashboard_fit_no_settings_jump_bar_and_themes(self):
        dash = self.window.dashboard_view
        self.assertIsNone(dash.quick_actions_card)

        for size in ((1092, 614), (1280, 720), (1366, 768), (1280, 820)):
            self.window.resize(*size)
            self.window.switch_page(0)
            _pump(4)
            self.assertEqual(
                dash.activity_table.horizontalScrollBar().maximum(),
                0,
                f"Dashboard activity_table horizontally scrolled at {size}",
            )
            if size[1] >= 720:
                self.assertEqual(
                    dash.dashboard_scroll.verticalScrollBar().maximum(),
                    0,
                    f"Dashboard vertically scrolled at {size}",
                )
            else:
                self.assertLessEqual(
                    dash.dashboard_scroll.verticalScrollBar().maximum(),
                    90,
                    f"Dashboard vertical scroll excessive at compact {size}",
                )
            self.assertEqual(dash.dashboard_scroll.verticalScrollBar().value(), 0)
            title_lbl = dash.findChild(QLabel, "PageTitle")
            self.assertIsNotNone(title_lbl)
            self.assertGreaterEqual(
                title_lbl.mapTo(dash.dashboard_scroll.viewport(), QPoint(0, 0)).y(),
                0,
                f"Dashboard title clipped above viewport at {size}",
            )
            if dash.activity_table.rowCount() > 0:
                actions_w = dash.activity_table.cellWidget(0, 6)
                self.assertIsNotNone(actions_w)
                for btn in actions_w.findChildren(QPushButton, "RowAction"):
                    self.assertGreaterEqual(btn.height(), 22)
                    self.assertLessEqual(
                        btn.geometry().bottom(),
                        actions_w.height() - 1,
                        f"RowAction button {btn.text()} clipped inside cell at {size}: {btn.geometry()} vs {actions_w.size()}",
                    )

        self.window.switch_page(5)
        settings_page = self.window.settings_view
        self.assertFalse(hasattr(settings_page, "section_jump_bar"))
        self.assertFalse(hasattr(settings_page, "section_jump_buttons"))
        self.assertFalse(hasattr(settings_page, "jump_to_section"))
        for size in ((800, 520), (910, 512), (1440, 900)):
            self.window.resize(*size)
            _pump(4)
            self.assertLessEqual(
                settings_page.container.width(),
                settings_page.scroll.viewport().width() + 2,
            )

        # Verify Light theme applies across shell, FAB, drawer, and pages cleanly
        try:
            self.window.theme_manager.set_theme("Light")
            self.window.switch_page(0)
            self.window.show_quick_actions_popup(self.window.quick_actions_fab)
            _pump(3)
            self.assertEqual(self.window.theme_manager.get_active_theme(), "Light")
            self.assertTrue(self.window.quick_actions_popup.isVisible())
            self.assertTrue(self.window.quick_actions_fab.isChecked())
        finally:
            self.window.hide_quick_actions_popup()
            self.window.theme_manager.set_theme("Dark")
            _pump(2)


class ResponsiveDialogsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = _create_populated_db(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        _pump(2)
        cls.db.close()
        cls.tmp.cleanup()

    def _check_dialog_fits_screen(self, dlg, name):
        avail = ui_responsive.active_screen_geometry(dlg)
        dlg.show()
        _pump(3)
        self.assertLessEqual(
            dlg.width(),
            avail.width(),
            f"{name} width {dlg.width()} exceeds available screen width {avail.width()}",
        )
        self.assertLessEqual(
            dlg.height(),
            avail.height(),
            f"{name} height {dlg.height()} exceeds available screen height {avail.height()}",
        )
        self.assertLessEqual(
            dlg.minimumSize().width(),
            avail.width(),
            f"{name} minWidth exceeds screen",
        )
        self.assertLessEqual(
            dlg.minimumSize().height(),
            avail.height(),
            f"{name} minHeight exceeds screen",
        )
        dlg.close()
        dlg.deleteLater()
        _pump(2)

    def test_loan_and_audit_control_center_dialogs(self):
        for name, dlg in (
            ("Loan Control Center (ViewBooksDialog)", ViewBooksDialog(self.db, "24001-CS-001")),
            ("Audit Control Center (BookHistoryDialog)", BookHistoryDialog(self.db, "10001", "Algorithms")),
        ):
            dlg.show()
            _pump(3)
            if dlg.table.rowCount() > 0:
                dlg.table.selectRow(0)
                _pump(2)

            self.assertIsInstance(dlg.detail_scroll, QScrollArea)
            self.assertTrue(dlg.detail_container.isVisible())

            dlg.resize(700, 500)
            _pump(2)
            self.assertTrue(dlg.detail_container.isVisible(), f"{name} hidden on narrow width")
            self.assertEqual(dlg.content_splitter.orientation(), Qt.Orientation.Vertical)

            dlg.resize(1000, 580)
            _pump(2)
            self.assertEqual(dlg.content_splitter.orientation(), Qt.Orientation.Horizontal)

            dlg.close()
            dlg.deleteLater()
            _pump(2)

    def test_all_operational_and_management_dialogs(self):
        loan_id = self.db.get_active_loan_id("10001", "24001-CS-001")
        icon_path = str(REPO_ROOT / "assets" / "library_icon.png")

        with mock.patch("dialogs.cv2.VideoCapture", side_effect=RuntimeError("No camera in test")):
            dialogs = [
                ("HelpDialog", HelpDialog()),
                ("LoginDialog", LoginDialog(self.db)),
                ("RecoveryCodeSetupDialog", RecoveryCodeSetupDialog()),
                ("AdminPasswordRecoveryDialog", AdminPasswordRecoveryDialog(self.db)),
                ("CustomSplashScreen", CustomSplashScreen(icon_path)),
                ("BookDialog (new)", BookDialog(self.db)),
                ("BookDialog (edit)", BookDialog(self.db, book_id="10001")),
                ("UserDialog (new)", UserDialog(self.db)),
                ("UserDialog (edit)", UserDialog(self.db, user_id="24001-CS-001")),
                ("ComplaintDialog", ComplaintDialog(self.db)),
                ("ComplaintManagementDialog", ComplaintManagementDialog(self.db)),
                ("EmailQueueManagementDialog", EmailQueueManagementDialog(self.db)),
                ("VersionManagerDialog", VersionManagerDialog([], "2.0", False)),
                ("DepartmentManagerDialog", DepartmentManagerDialog(self.db)),
                ("EditDepartmentDialog", EditDepartmentDialog("Computer Science", "STUDENT", 4)),
                ("IssueBookDialog", IssueBookDialog(self.db)),
                ("ReturnBookDialog", ReturnBookDialog(self.db)),
                ("BatchCirculationDialog", BatchCirculationDialog(self.db, "ISSUE", ["10001"], "books")),
                ("CustomEmailDialog", CustomEmailDialog("Aarav Sharma")),
                ("BarcodeGeneratorDialog", BarcodeGeneratorDialog(self.db, book_id="10001", title="Algorithms")),
                ("QuickScanDialog", QuickScanDialog(self.db)),
                ("RenewLoanDialog", RenewLoanDialog(self.db, loan_id)),
                ("PendingFinesDialog", PendingFinesDialog(self.db)),
                ("MetricDetailDialog", MetricDetailDialog("Books", ["Book ID", "Title", "Author", "Publisher", "Total", "Avail"], [["10001", "Algorithms", "Sedgewick", "Press", 5, 4]])),
                ("ActivityDetailDialog", ActivityDetailDialog("ISSUED", "Algorithms", "Aarav Sharma", "Today", details=[("Loan ID", str(loan_id)), ("Status", "Issued")])),
                ("ActivityHistoryDialog", ActivityHistoryDialog(self.db)),
            ]

            for name, dlg in dialogs:
                with self.subTest(dialog=name):
                    self._check_dialog_fits_screen(dlg, name)


class VersionManagerAndFirstRunFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = _create_populated_db(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        _pump(2)
        cls.db.close()
        cls.tmp.cleanup()

    def _sample_releases(self):
        return [
            {
                "tag_name": "v1.0",
                "published_at": "2026-11-12",
                "installable": True,
                "current": True,
                "reason": "Installed version",
                "release_notes": (
                    "### Installation (Windows)\n"
                    "- **New installs & manual upgrades:** Download and run `LibraryInstaller.exe`.\n"
                    "- **Existing packaged installations:** Open **Settings -> Application Updates**.\n\n"
                    "| File | Purpose |\n|---|---|\n| `LibraryInstaller.exe` | Installer |\n\n"
                    "### SHA-256 Checksums\n"
                    "```text\nabcd1234 *LibraryInstaller.exe\n```\n\n"
                    "**Full Changelog**: https://github.com/krishnashashanth-sks/campus-library/commits/v1.0"
                ),
                "release_url": "https://github.com/krishnashashanth-sks/campus-library/releases/tag/v1.0",
                "download_url": "https://github.com/krishnashashanth-sks/campus-library/releases/download/v1.0/Library-Windows.zip",
                "digest": "sha256:" + ("a" * 64),
                "size": 95 * 1024 * 1024,
            },
            {
                "tag_name": "v1.1",
                "published_at": "2026-11-15",
                "installable": True,
                "current": False,
                "reason": "",
                "release_notes": "### Highlights\n- Faster navigation and **Markdown** notes.",
                "release_url": "https://github.com/krishnashashanth-sks/campus-library/releases/tag/v1.1",
                "download_url": "https://github.com/krishnashashanth-sks/campus-library/releases/download/v1.1/Library-Windows.zip",
                "digest": "sha256:" + ("b" * 64),
                "size": 98 * 1024 * 1024,
            },
        ]

    def test_version_manager_markdown_and_button_states_across_modes(self):
        releases = self._sample_releases()
        plain = markdown_to_plain_text(releases[0]["release_notes"])
        self.assertNotIn("###", plain)
        self.assertNotIn("**", plain)
        self.assertNotIn("```", plain)
        rendered_html = markdown_to_themed_html(
            releases[0]["release_notes"],
            title="v1.0",
            subtitle="Currently Installed",
        )
        self.assertIn("<h3", rendered_html)
        self.assertIn("<pre", rendered_html)
        self.assertIn("<a ", rendered_html)

        settings_view = SettingsView(self.db)
        try:
            # Verify SettingsView stylesheet defines explicit disabled styling for buttons
            self.assertIn("QPushButton#PrimaryButton:disabled", settings_view.styleSheet())

            # Source / non-packaged mode: install_button is clearly disabled SecondaryButton; GitHub download is active PrimaryButton
            dlg_src = VersionManagerDialog(
                releases,
                "1.0",
                can_install=False,
                parent=settings_view,
                install_reason="Running from Python source — use GitHub installer.",
            )
            dlg_src.show()
            _pump(2)
            self.assertIsInstance(dlg_src.details, QTextBrowser)
            details_plain = dlg_src.details.toPlainText()
            self.assertNotIn("###", details_plain)
            self.assertNotIn("**", details_plain)
            self.assertNotIn("```", details_plain)
            self.assertIn("<a href=", dlg_src.details.toHtml())
            self.assertFalse(dlg_src.install_button.isEnabled())
            self.assertEqual(dlg_src.install_button.objectName(), "SecondaryButton")
            self.assertTrue(dlg_src.open_release_button.isEnabled())
            self.assertEqual(dlg_src.open_release_button.objectName(), "PrimaryButton")

            with mock.patch("dialogs.QDesktopServices.openUrl", return_value=True) as spy_open:
                dlg_src.open_release_button.click()
                self.assertEqual(spy_open.call_count, 1)
                self.assertEqual(spy_open.call_args[0][0].toString(), releases[0]["release_url"])

            # Switching to v1.1 in source mode explains requirement clearly & double-click prompts action dialog
            dlg_src.table.selectRow(1)
            _pump(2)
            self.assertFalse(dlg_src.install_button.isEnabled())
            self.assertIn("GitHub", dlg_src.install_status_label.text())
            with mock.patch.object(QMessageBox, "exec", return_value=0) as spy_msg:
                dlg_src._on_row_double_clicked(1, 0)
                self.assertEqual(spy_msg.call_count, 1)

            dlg_src.close()
            dlg_src.deleteLater()

            # Packaged mode: selecting current row disables install; selecting v1.1 enables install & sets selected_release
            dlg_pkg = VersionManagerDialog(releases, "1.0", can_install=True, parent=settings_view)
            dlg_pkg.show()
            _pump(2)
            self.assertFalse(dlg_pkg.install_button.isEnabled())
            self.assertIn("Installed", dlg_pkg.install_button.text())

            dlg_pkg.table.selectRow(1)
            _pump(2)
            self.assertTrue(dlg_pkg.install_button.isEnabled())
            self.assertEqual(dlg_pkg.install_button.objectName(), "PrimaryButton")
            self.assertIn("Install Update", dlg_pkg.install_button.text())

            dlg_pkg.install_button.click()
            _pump(1)
            self.assertEqual(dlg_pkg.result(), int(dlg_pkg.DialogCode.Accepted))
            self.assertIsNotNone(dlg_pkg.selected_release)
            self.assertEqual(dlg_pkg.selected_release["latest_version"], "v1.1")
            self.assertTrue(dlg_pkg.selected_release["version_selection"])
            dlg_pkg.close()
            dlg_pkg.deleteLater()
        finally:
            settings_view._closing = True
            settings_view.close()
            settings_view.deleteLater()
            _pump(2)

    def test_recovery_code_copy_and_save_feedback_visible_and_unclipped(self):
        with tempfile.TemporaryDirectory() as td:
            out_txt = Path(td) / "recovery-code.txt"
            dlg = RecoveryCodeSetupDialog()
            dlg.show()
            _pump(3)

            scroll = dlg.findChild(QScrollArea, "RecoverySetupScroll")
            self.assertIsNotNone(scroll)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
            self.assertTrue(dlg.saved_checkbox.isVisible())
            self.assertTrue(dlg.confirm_button.isVisible())
            self.assertFalse(dlg.confirm_button.isEnabled())

            # Clicking Copy gives immediate clipboard copy + visual feedback without hiding Continue
            QApplication.clipboard().clear()
            dlg.copy_button.click()
            _pump(2)
            self.assertEqual(QApplication.clipboard().text(), dlg.recovery_code)
            self.assertIn("Copied", dlg.copy_button.text())
            self.assertIn("copied", dlg.copy_feedback_label.text().lower())
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertTrue(dlg.saved_checkbox.isVisible())
            self.assertTrue(dlg.confirm_button.isVisible())

            # Saving as .txt writes the exact recovery code cleanly
            with mock.patch("dialogs.QFileDialog.getSaveFileName", return_value=(str(out_txt), "Text Files (*.txt)")):
                dlg.save_button.click()
                _pump(2)
            self.assertTrue(out_txt.exists())
            saved_body = out_txt.read_text(encoding="utf-8")
            self.assertIn(dlg.recovery_code, saved_body)
            self.assertIn(out_txt.name, dlg.copy_feedback_label.text())

            # Narrow window still keeps checkbox and Continue completely visible outside scroll area
            dlg.resize(400, 380)
            _pump(2)
            self.assertTrue(dlg.saved_checkbox.isVisible())
            self.assertTrue(dlg.confirm_button.isVisible())
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

            dlg.saved_checkbox.setChecked(True)
            _pump(1)
            self.assertTrue(dlg.confirm_button.isEnabled())

            dlg.close()
            dlg.deleteLater()
            _pump(2)

    def test_theme_manager_defines_disabled_button_styles(self):
        app = _ensure_app()
        qss = ThemeManager._create_stylesheet(ThemeManager.COLORS["Dark"])
        for btn_id in (
            "PrimaryButton",
            "SuccessButton",
            "WarningButton",
            "InfoButton",
            "SecondaryButton",
            "DangerButton",
        ):
            self.assertIn(f"QPushButton#{btn_id}:disabled", qss)

    def test_custom_splash_finish_and_main_startup_handoff(self):
        import main as app_main

        icon_path = str(REPO_ROOT / "assets" / "library_icon.png")
        splash = CustomSplashScreen(icon_path)
        splash.set_status("Opening Library Management Workspace...")
        splash.show()
        _pump(1)
        splash.finish(None)
        _pump(1)
        self.assertFalse(splash.isVisible())

        # Exercise main.main() handoff from accepted LoginDialog -> loading splash -> MainWindow
        # Re-use the existing QApplication instance safely.
        existing_app = _ensure_app()
        with tempfile.TemporaryDirectory() as td:
            db = database.LocalDatabase(os.path.join(td, "startup_handoff.db"))
            created_windows = []
            orig_quit_flag = existing_app.quitOnLastWindowClosed()

            class _FakeMainWindow(MainWindow):
                def __init__(self, database_conn):
                    super().__init__(database_conn)
                    created_windows.append(self)

            with (
                mock.patch.object(app_main, "SPLASH_DURATION", 0),
                mock.patch.object(app_main, "QApplication", return_value=existing_app),
                mock.patch.object(app_main, "initialize_database", return_value=db),
                mock.patch.object(app_main, "MainWindow", _FakeMainWindow),
                mock.patch.object(app_main.LoginDialog, "exec", return_value=int(app_main.QDialog.DialogCode.Accepted)),
                mock.patch.object(existing_app, "exec", return_value=0),
            ):
                app_main.QApplication.setHighDpiScaleFactorRoundingPolicy = QApplication.setHighDpiScaleFactorRoundingPolicy
                app_main.QApplication.setOverrideCursor = QApplication.setOverrideCursor
                app_main.QApplication.restoreOverrideCursor = QApplication.restoreOverrideCursor
                app_main.QApplication.activeModalWidget = QApplication.activeModalWidget
                app_main.QApplication.widgetAt = QApplication.widgetAt
                rc = app_main.main()

            self.assertEqual(rc, 0)
            self.assertEqual(len(created_windows), 1)
            win = created_windows[0]
            try:
                win._shutdown_background_workers()
                win.close()
                win.deleteLater()
                _pump(2)
            finally:
                existing_app.setQuitOnLastWindowClosed(orig_quit_flag)
                db.close()


if __name__ == "__main__":
    unittest.main()

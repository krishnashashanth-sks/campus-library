import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from unittest import mock

import barcode
from barcode.writer import ImageWriter
import cv2
import numpy as np
from PIL import Image
import qrcode

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

import database
from barcode_scanner import BarcodeDecoder, decode_image_file
from dialogs import QuickScanDialog
from theme_manager import ThemeManager


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_quick_scan"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=4):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


def _make_code128_bgr(value: str) -> np.ndarray:
    buf = io.BytesIO()
    barcode.get_barcode_class("code128")(value, writer=ImageWriter()).write(
        buf,
        options={
            "module_width": 0.35,
            "module_height": 15,
            "quiet_zone": 5,
            "font_size": 12,
            "text_distance": 5,
            "write_text": True,
        },
    )
    arr = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


class _FakeVideoCapture:
    def __init__(self, frames):
        self._frames = list(frames)
        self._idx = 0
        self._opened = True

    def isOpened(self):
        return self._opened

    def set(self, *_args):
        return True

    def read(self):
        if not self._opened or not self._frames:
            return False, None
        frame = self._frames[min(self._idx, len(self._frames) - 1)]
        self._idx += 1
        return True, frame.copy()

    def release(self):
        self._opened = False


class BarcodeDecoderTests(unittest.TestCase):
    def setUp(self):
        self.decoder = BarcodeDecoder()

    def test_decodes_code128_variants_and_orientations(self):
        for value in ("10001", "98765", "24001-CS-001", "LIB-A9"):
            img = _make_code128_bgr(value)
            for label, variant in (
                ("upright", img),
                ("180", cv2.rotate(img, cv2.ROTATE_180)),
                ("90cw", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
            ):
                with self.subTest(value=value, orientation=label):
                    res = self.decoder.decode(variant, thorough=True)
                    self.assertIsNotNone(res)
                    self.assertEqual(res.code, value)
                    self.assertEqual(res.symbology, "CODE128")

    def test_decodes_tilted_blurry_webcam_scene(self):
        scene = np.full((480, 640, 3), (110, 100, 90), dtype=np.uint8)
        lbl = cv2.resize(_make_code128_bgr("10001"), (260, 110))
        rot = cv2.getRotationMatrix2D((130, 55), 16, 1.0)
        tilted = cv2.warpAffine(lbl, rot, (260, 110), borderValue=(220, 220, 220))
        scene[185:295, 190:450] = tilted
        scene = cv2.GaussianBlur(scene, (3, 3), 0)

        res = self.decoder.decode(scene, thorough=True)
        self.assertIsNotNone(res)
        self.assertEqual(res.code, "10001")

    def test_decodes_qr_and_image_file(self):
        qr_img = cv2.cvtColor(
            np.array(qrcode.make("BOOK:10002").convert("RGB")),
            cv2.COLOR_RGB2BGR,
        )
        res = self.decoder.decode(qr_img)
        self.assertIsNotNone(res)
        self.assertEqual(res.code, "10002")
        self.assertEqual(res.symbology, "QR")

        with tempfile.TemporaryDirectory() as tmp:
            png_path = os.path.join(tmp, "book_10001.png")
            cv2.imwrite(png_path, _make_code128_bgr("10001"))
            file_res = decode_image_file(png_path)
            self.assertIsNotNone(file_res)
            self.assertEqual(file_res.code, "10001")

    def test_no_false_positives_on_blurry_brown_noise(self):
        rng = np.random.default_rng(42)
        for _ in range(5):
            noise = rng.integers(60, 125, size=(480, 640, 3), dtype=np.uint8)
            blurry = cv2.GaussianBlur(noise, (15, 15), 0)
            self.assertIsNone(self.decoder.decode(blurry, thorough=True))


class QuickScanDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()
        cls.tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls.tmp.name, "quick_scan_test.db")
        cls.db = database.LocalDatabase(db_path)
        ok, msg = cls.db.insert_book("10001", "Algorithms", "Sedgewick", "Press", 4, 4)
        assert ok, msg
        ok, msg = cls.db.insert_book("10002", "Clean Code", "Martin", "Prentice", 2, 2)
        assert ok, msg
        ok, msg = cls.db.insert_user("24001-CS-001", "Aarav Sharma", "9876543210", "Student", "CSE", "aarav@example.com")
        assert ok, msg
        ok, msg = cls.db.issue_book("10001", "24001-CS-001", 14)
        assert ok, msg

    @classmethod
    def tearDownClass(cls):
        _pump(2)
        cls.db.close()
        cls.tmp.cleanup()

    def test_preview_height_does_not_grow_across_frames(self):
        portrait_brown = np.full((800, 480, 3), (70, 95, 110), dtype=np.uint8)
        fake_cap = _FakeVideoCapture([portrait_brown] * 30)

        with mock.patch("dialogs.cv2.VideoCapture", return_value=fake_cap):
            dlg = QuickScanDialog(self.db)
            dlg.show()
            _pump(4)

            initial_size = dlg.lbl_capture.size()
            for _ in range(25):
                dlg.update_frame()
                _pump(1)

            after_size = dlg.lbl_capture.size()
            self.assertEqual(initial_size.height(), after_size.height())
            self.assertEqual(initial_size.width(), after_size.width())
            self.assertTrue(dlg.input_book_id.isVisible())
            self.assertTrue(dlg.input_user_id.isVisible())
            self.assertTrue(dlg.issue_btn.isVisible())
            dlg.close()
            dlg.deleteLater()
            _pump(3)

    def test_scanned_book_resolves_details_and_active_borrower(self):
        scene = np.full((480, 640, 3), (245, 245, 245), dtype=np.uint8)
        lbl = cv2.resize(_make_code128_bgr("10001"), (340, 140))
        scene[170:310, 150:490] = lbl
        fake_cap = _FakeVideoCapture([scene])

        with mock.patch("dialogs.cv2.VideoCapture", return_value=fake_cap):
            dlg = QuickScanDialog(self.db)
            dlg.show()
            _pump(3)

            res = dlg._decoder.decode(scene, thorough=True)
            self.assertIsNotNone(res)
            dlg._on_background_decoded(res, scene)
            _pump(3)

            self.assertEqual(dlg.input_book_id.text(), "10001")
            self.assertIn("Algorithms", dlg.lbl_status.text())
            self.assertTrue(dlg.active_borrower_widget.isVisible())
            self.assertIn("Aarav Sharma", dlg.lbl_active_borrower.text())

            dlg.btn_use_borrower.click()
            _pump(2)
            self.assertEqual(dlg.input_user_id.text(), "24001-CS-001")
            self.assertTrue(dlg.renew_btn.isEnabled())
            self.assertTrue(dlg.return_btn.isEnabled())

            dlg.close()
            dlg.deleteLater()
            _pump(3)

    def test_target_toggle_fills_user_id_and_batch_mode_issue_return(self):
        with mock.patch("dialogs.cv2.VideoCapture", side_effect=RuntimeError("No camera")):
            dlg = QuickScanDialog(self.db)
            dlg.show()
            _pump(2)

            dlg.set_camera_scanned_book_id("10002", "USB Scanner")
            dlg._toggle_scan_target()
            user_scene = _make_code128_bgr("24001-CS-001")
            user_res = dlg._decoder.decode(user_scene, thorough=True)
            self.assertIsNotNone(user_res)
            dlg._handle_decoded_result(user_res, source_prefix="Camera")
            _pump(2)

            self.assertEqual(dlg.input_book_id.text(), "10002")
            self.assertEqual(dlg.input_user_id.text(), "24001-CS-001")

            dlg.chk_batch_mode.setChecked(True)
            with mock.patch.object(QMessageBox, "information"), mock.patch.object(QMessageBox, "warning"):
                dlg.process_circulation("issue")
                _pump(2)
                self.assertTrue(dlg.isVisible())
                self.assertIn("ISSUED 10002", dlg.lbl_session_log.text())
                self.assertEqual(dlg.input_book_id.text(), "")

                # Now return 10002 without typing user_id again (single active borrower auto-fallback)
                dlg.input_user_id.clear()
                dlg.set_camera_scanned_book_id("10002", "USB Scanner")
                dlg.process_circulation("return")
                _pump(2)
                self.assertIn("RETURNED 10002", dlg.lbl_session_log.text())

            dlg.close()
            dlg.deleteLater()
            _pump(3)

    def test_camera_backend_fallback_and_mirror_toggle_refresh(self):
        class _ClosedCap:
            def isOpened(self):
                return False

            def release(self):
                pass

        frame = np.full((240, 320, 3), (40, 80, 120), dtype=np.uint8)
        open_cap = _FakeVideoCapture([frame])

        with mock.patch(
            "dialogs.cv2.VideoCapture",
            side_effect=[_ClosedCap(), open_cap],
        ) as mocked_vc:
            dlg = QuickScanDialog(self.db)
            dlg.show()
            _pump(2)

            self.assertGreaterEqual(mocked_vc.call_count, 2)
            self.assertIs(dlg.cap, open_cap)
            dlg.update_frame()
            _pump(1)
            dlg.btn_mirror.setChecked(True)
            _pump(1)
            self.assertTrue(dlg._mirror_preview)

            dlg.close()
            dlg.deleteLater()
            _pump(3)


if __name__ == "__main__":
    unittest.main()

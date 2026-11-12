import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datetime
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

import database
import google_drive_backup
import ui_responsive
from mainwindow import MainWindow
from pages.settings_view import SettingsView, _GoogleDriveSetupDialog
from theme_manager import ThemeManager


VALID_CLIENT_JSON = json.dumps(
    {
        "installed": {
            "client_id": "1234567890-test.apps.googleusercontent.com",
            "project_id": "library-test-project",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "GOCSPX-test-secret",
            "redirect_uris": ["http://localhost"],
        }
    }
)


def _ensure_app():
    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(["test_page_refresh_and_backup"])
    if getattr(app, "theme_manager", None) is None:
        app.theme_manager = ThemeManager(app, initial_theme="Dark")
    return app


def _pump(rounds=2):
    app = _ensure_app()
    for _ in range(rounds):
        app.processEvents()


class _FakeSecretVault:
    def __init__(self):
        self.store = {}

    def store_secret(self, target, secret, username=""):
        self.store[str(target)] = str(secret)

    def read_secret(self, target):
        return self.store.get(str(target))

    def delete_secret(self, target):
        self.store.pop(str(target), None)


class PageSwitchCachingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "library.db")
        self.db = database.LocalDatabase(self.db_path)
        self.db.insert_book("10001", "Clean Architecture", "Robert Martin", "Prentice Hall", 4, 4)
        self.db.insert_user("24001-CS-001", "9876543210", "Asha Rao", "Student", "Computer Science")

    def tearDown(self):
        try:
            self.db.close()
        finally:
            self.tmp.cleanup()

    def test_data_stamp_tracks_local_and_external_commits(self):
        stamp0 = self.db.get_data_stamp()
        self.assertEqual(stamp0, self.db.get_data_stamp())

        ok, msg = self.db.insert_book("10002", "Operating Systems", "Tanenbaum", "Pearson", 2, 2)
        self.assertTrue(ok, msg)
        stamp1 = self.db.get_data_stamp()
        self.assertNotEqual(stamp0, stamp1)

        # Raw commit through a separate SQLite connection should flip PRAGMA data_version
        other = database.LocalDatabase(self.db_path)
        try:
            other.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("sync_backup_folder", "C:/LibraryBackups"),
            )
            other.conn.commit()
        finally:
            other.close()

        stamp2 = self.db.get_data_stamp()
        self.assertNotEqual(stamp1, stamp2)

    def test_switch_page_skips_unchanged_reloads_and_forces_when_requested(self):
        win = MainWindow(self.db)
        _pump(3)
        try:
            with (
                mock.patch.object(
                    win.dashboard_view,
                    "refresh_dashboard",
                    wraps=win.dashboard_view.refresh_dashboard,
                ) as spy_dash,
                mock.patch.object(
                    win.catalog_view,
                    "load_books_to_table",
                    wraps=win.catalog_view.load_books_to_table,
                ) as spy_books,
                mock.patch.object(
                    win.usermanagement_view,
                    "load_users_to_table",
                    wraps=win.usermanagement_view.load_users_to_table,
                ) as spy_users,
                mock.patch.object(
                    win.circulation_view,
                    "load_circulation",
                    wraps=win.circulation_view.load_circulation,
                ) as spy_circ,
                mock.patch.object(
                    win.reports_view,
                    "load_data",
                    wraps=win.reports_view.load_data,
                ) as spy_reports,
                mock.patch.object(
                    win.settings_view,
                    "load_settings",
                    wraps=win.settings_view.load_settings,
                ) as spy_settings,
            ):
                spies = (spy_dash, spy_books, spy_users, spy_circ, spy_reports, spy_settings)

                # Initial switch passes through all 6 pages without any redundant reloads
                for idx in range(6):
                    win.switch_page(idx)
                    _pump(1)
                for idx, spy in enumerate(spies):
                    self.assertEqual(spy.call_count, 0, f"Page {idx} reloaded needlessly while unchanged")

                # Modify database state: only visited pages reload once until clean again
                ok, msg = self.db.insert_book("10003", "Computer Networks", "Kurose", "Pearson", 3, 3)
                self.assertTrue(ok, msg)

                win.switch_page(1)
                win.switch_page(1)
                self.assertEqual(spy_books.call_count, 1)

                win.switch_page(0)
                win.switch_page(0)
                self.assertEqual(spy_dash.call_count, 1)

                # Date rollover invalidates cached stamps
                tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
                with mock.patch.object(
                    win.db,
                    "get_data_stamp",
                    return_value=(999999, 999999, tomorrow),
                ):
                    win.switch_page(4)
                    self.assertEqual(spy_reports.call_count, 1)
                    win.switch_page(4)
                    self.assertEqual(spy_reports.call_count, 1)

                # Active theme switch triggers refresh on destination page once
                try:
                    win.theme_manager.set_theme("Light")
                    win.switch_page(2)
                    win.switch_page(2)
                    self.assertEqual(spy_users.call_count, 1)
                finally:
                    win.theme_manager.set_theme("Dark")

                # Explicit F5 / force=True refresh always reloads regardless of unchanged stamp
                before_forced = spy_reports.call_count
                win.refresh_page(4, force=True)
                self.assertEqual(spy_reports.call_count, before_forced + 1)

                # Settings forced reload always invokes load_settings
                before_settings = spy_settings.call_count
                win.refresh_page(5, force=True)
                self.assertEqual(spy_settings.call_count, before_settings + 1)
        finally:
            win._shutdown_background_workers()
            win.close()
            win.deleteLater()
            _pump(2)


class GoogleDriveAndSyncBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.vault = _FakeSecretVault()
        self.patches = [
            mock.patch.object(google_drive_backup, "store_secret", side_effect=self.vault.store_secret),
            mock.patch.object(google_drive_backup, "read_secret", side_effect=self.vault.read_secret),
            mock.patch.object(google_drive_backup, "delete_secret", side_effect=self.vault.delete_secret),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_validate_client_json_variants(self):
        parsed, compact = google_drive_backup.validate_and_parse_drive_client_json(VALID_CLIENT_JSON)
        self.assertIn("installed", parsed)
        self.assertNotIn("\n", compact)

        web_json = json.dumps(
            {
                "web": {
                    "client_id": "abc",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        )
        parsed_web, _ = google_drive_backup.validate_and_parse_drive_client_json(web_json)
        self.assertIn("web", parsed_web)

        for bad_payload in (
            "",
            "{not valid json",
            "[1, 2, 3]",
            json.dumps({"type": "service_account", "client_email": "x@y.iam"}),
            json.dumps({"other": {}}),
            json.dumps({"installed": {"client_id": "id-only"}}),
        ):
            with self.assertRaises(RuntimeError):
                google_drive_backup.validate_and_parse_drive_client_json(bad_payload)

    def test_client_config_discovery_vault_and_sidecar(self):
        missing_sidecar = self.tmp_path / "missing_client.json"
        with mock.patch.object(
            google_drive_backup,
            "_candidate_drive_client_paths",
            return_value=[missing_sidecar],
        ):
            status0 = google_drive_backup.get_drive_status()
            self.assertFalse(status0["connected"])
            self.assertFalse(status0["has_client_config"])
            self.assertEqual(status0["client_source"], "")

            # Save once into Credential Manager -> no file needed anymore
            google_drive_backup.save_drive_client_config(client_json_text=VALID_CLIENT_JSON)
            status1 = google_drive_backup.get_drive_status()
            self.assertTrue(status1["has_client_config"])
            self.assertIn("Credential Manager", status1["client_source"])

            google_drive_backup.clear_drive_client_config()
            self.assertFalse(google_drive_backup.has_drive_client_config())

            # Sidecar auto-discovery for IT deployments
            missing_sidecar.write_text(VALID_CLIENT_JSON, encoding="utf-8")
            # Re-name to google_drive_client.json to verify expected filename reporting
            it_sidecar = self.tmp_path / google_drive_backup.DEFAULT_CLIENT_FILENAME
            it_sidecar.write_text(VALID_CLIENT_JSON, encoding="utf-8")

        with mock.patch.object(
            google_drive_backup,
            "_candidate_drive_client_paths",
            return_value=[it_sidecar],
        ):
            cfg, source = google_drive_backup.resolve_drive_client_config()
            self.assertIsNotNone(cfg)
            self.assertIn(google_drive_backup.DEFAULT_CLIENT_FILENAME, source)

    def test_connect_reuses_and_refreshes_token_without_reprompting(self):
        fake_creds = mock.MagicMock()
        fake_creds.valid = True
        fake_creds.expired = False
        fake_creds.refresh_token = "refresh-tok"
        fake_creds.to_json.return_value = json.dumps(
            {
                "token": "access-1",
                "refresh_token": "refresh-tok",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "csec",
            }
        )

        fake_flow = mock.MagicMock()
        fake_flow.run_local_server.return_value = fake_creds

        with (
            mock.patch.object(
                google_drive_backup,
                "_candidate_drive_client_paths",
                return_value=[],
            ),
            mock.patch(
                "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                return_value=fake_flow,
            ) as mock_flow_ctor,
        ):
            status = google_drive_backup.connect_drive(client_json_text=VALID_CLIENT_JSON)
            self.assertTrue(status["connected"])
            self.assertTrue(status["has_client_config"])
            mock_flow_ctor.assert_called_once()
            fake_flow.run_local_server.assert_called_once()

            # Ensure encryption key survives disconnect_drive(clear_client_config=False)
            key = google_drive_backup._get_encryption_key()
            self.assertEqual(len(key), 32)
            self.assertTrue(google_drive_backup.has_backup_encryption_key())

            # Subsequent credential fetch reuses stored token without re-running browser OAuth
            reused_creds = mock.MagicMock()
            reused_creds.valid = True
            reused_creds.expired = False
            with mock.patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_info",
                return_value=reused_creds,
            ) as mock_from_info:
                got = google_drive_backup._get_drive_credentials()
                self.assertIs(got, reused_creds)
                mock_from_info.assert_called_once()
                self.assertEqual(mock_flow_ctor.call_count, 1)

            # Expired stored token refreshes transparently
            expired_creds = mock.MagicMock()
            expired_creds.valid = False
            expired_creds.expired = True
            expired_creds.refresh_token = "refresh-tok"
            expired_creds.to_json.return_value = json.dumps({"token": "refreshed"})
            with (
                mock.patch(
                    "google.oauth2.credentials.Credentials.from_authorized_user_info",
                    return_value=expired_creds,
                ),
                mock.patch("google.auth.transport.requests.Request") as mock_req,
            ):
                got_refreshed = google_drive_backup._get_drive_credentials()
                self.assertIs(got_refreshed, expired_creds)
                expired_creds.refresh.assert_called_once_with(mock_req.return_value)

            after_disc = google_drive_backup.disconnect_drive(clear_client_config=False)
            self.assertFalse(after_disc["connected"])
            self.assertTrue(after_disc["has_client_config"])
            self.assertTrue(google_drive_backup.has_backup_encryption_key())

            google_drive_backup.disconnect_drive(clear_client_config=True)
            with self.assertRaises(RuntimeError) as ctx:
                google_drive_backup._get_drive_credentials()
            self.assertIn("Synced Folder Backup", str(ctx.exception))

    def test_sync_folder_backup_pruning_and_decrypt_restore(self):
        db_path = self.tmp_path / "live_library.db"
        sync_dir = self.tmp_path / "synced_drive"
        db = database.LocalDatabase(os.fspath(db_path))
        try:
            ok, msg = db.insert_book("10999", "Encrypted Backup Book", "Auth", "Pub", 3, 2)
            self.assertTrue(ok, msg)

            created_paths = []
            for _ in range(4):
                info = google_drive_backup.backup_to_sync_folder(db, sync_dir, max_keep=3)
                created_paths.append(Path(info["path"]))

            remaining = list(sync_dir.glob("library-backup-*.clbk"))
            self.assertEqual(len(remaining), 3)
            latest = max(remaining, key=lambda p: p.stat().st_mtime)
            self.assertTrue(latest.read_bytes().startswith(google_drive_backup.BACKUP_HEADER))

            # Active database cannot be overwritten
            with self.assertRaises(ValueError):
                google_drive_backup.decrypt_backup_file(
                    latest,
                    db_path,
                    active_database_path=db_path,
                )

            restored_db_path = self.tmp_path / "restored_from_sync.db"
            out = google_drive_backup.decrypt_backup_file(
                latest,
                restored_db_path,
                active_database_path=db_path,
            )
            self.assertEqual(Path(out).resolve(), restored_db_path.resolve())
            conn = sqlite3.connect(out)
            try:
                title = conn.execute(
                    "SELECT title FROM books WHERE id = ?",
                    ("10999",),
                ).fetchone()
                self.assertEqual(title, ("Encrypted Backup Book",))
            finally:
                conn.close()

            # Recovery key workflow (restoring on another computer without saved vault key)
            key_file = self.tmp_path / "recovery.key.txt"
            google_drive_backup.export_backup_recovery_key(key_file)
            self.vault.delete_secret(google_drive_backup.DRIVE_KEY_TARGET)

            with self.assertRaises(RuntimeError):
                google_drive_backup.decrypt_backup_file(
                    latest,
                    self.tmp_path / "no_key.db",
                )

            restored_with_file = self.tmp_path / "restored_via_keyfile.db"
            google_drive_backup.decrypt_backup_file(
                latest,
                restored_with_file,
                recovery_key_file=key_file,
            )
            self.assertTrue(restored_with_file.is_file())

            wrong_key_file = self.tmp_path / "wrong.key.txt"
            wrong_key_file.write_text("00" * 32, encoding="ascii")
            with self.assertRaises(RuntimeError):
                google_drive_backup.decrypt_backup_file(
                    latest,
                    self.tmp_path / "wrong_out.db",
                    recovery_key_file=wrong_key_file,
                )
        finally:
            db.close()

    def test_settings_view_backup_controls_and_setup_dialog(self):
        app = _ensure_app()
        db = database.LocalDatabase(os.fspath(self.tmp_path / "settings_ui.db"))
        view = None
        try:
            with (
                mock.patch.object(
                    google_drive_backup,
                    "_candidate_drive_client_paths",
                    return_value=[],
                ),
                mock.patch("pages.settings_view.QMessageBox.warning") as mock_warn,
                mock.patch("pages.settings_view.QMessageBox.information") as mock_info,
                mock.patch("pages.settings_view.QMessageBox.critical") as mock_crit,
            ):
                view = SettingsView(db)
                _pump(2)

                self.assertEqual(view.settings_tabs.count(), 4)
                self.assertIn("Not connected", view.drive_status_label.text())

                # Enabling auto folder backup without choosing a folder shows friendly error
                view.sync_folder_input.setText("")
                view.auto_folder_backup_checkbox.setChecked(True)
                view.save_drive_backup_settings()
                mock_crit.assert_called_once()
                self.assertEqual(db.get_setting("sync_auto_backup_enabled", "0"), "0")

                sync_target = self.tmp_path / "DesktopDriveSync"
                view.sync_folder_input.setText(os.fspath(sync_target))
                view.auto_folder_backup_checkbox.setChecked(True)
                view.auto_drive_backup_checkbox.setChecked(False)
                view.save_drive_backup_settings()
                mock_info.assert_called_once()
                self.assertEqual(db.get_setting("sync_backup_folder", ""), os.fspath(sync_target))
                self.assertEqual(db.get_setting("sync_auto_backup_enabled", "0"), "1")

                # Guided one-time client.json setup dialog validates & fits screen
                dlg = _GoogleDriveSetupDialog(view)
                try:
                    avail = ui_responsive.active_screen_geometry(dlg)
                    dlg.show()
                    _pump(2)
                    self.assertLessEqual(dlg.width(), avail.width())
                    self.assertLessEqual(dlg.height(), avail.height())

                    dlg.json_editor.setPlainText("{invalid json")
                    dlg._accept_json()
                    self.assertEqual(mock_warn.call_count, 1)
                    self.assertEqual(dlg.result(), 0)

                    dlg.json_editor.setPlainText(VALID_CLIENT_JSON)
                    dlg._accept_json()
                    self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)
                    self.assertEqual(dlg.client_json_text, VALID_CLIENT_JSON)
                finally:
                    dlg.close()
                    dlg.deleteLater()
                    _pump(2)

                # Connected status label reflects Credential Manager saved state
                self.vault.store_secret(google_drive_backup.DRIVE_TOKEN_TARGET, '{"token":"ok"}')
                view.refresh_drive_status_ui()
                self.assertIn("Connected", view.drive_status_label.text())
                self.assertIn("Reconnect", view.drive_connect_btn.text())
        finally:
            if view is not None:
                view.stop_workers()
                view.close()
                view.deleteLater()
                _pump(2)
            db.close()
            assert app is not None


if __name__ == "__main__":
    unittest.main()


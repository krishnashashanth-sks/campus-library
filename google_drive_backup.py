import datetime
import io
import json
import os
import secrets
import sqlite3
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow

from secure_storage import read_secret, store_secret


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DRIVE_TOKEN_TARGET = "CampusLibrary/GoogleDriveOAuth"
DRIVE_KEY_TARGET = "CampusLibrary/GoogleDriveBackupKey"
BACKUP_HEADER = b"CLBK1"


def is_drive_connected():
    return bool(read_secret(DRIVE_TOKEN_TARGET))


def _get_drive_credentials(client_secret_file=None):
    stored_token = read_secret(DRIVE_TOKEN_TARGET)
    credentials = None

    if stored_token:
        credentials = Credentials.from_authorized_user_info(
            json.loads(stored_token),
            DRIVE_SCOPES,
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not client_secret_file:
                raise RuntimeError(
                    "Select a Google OAuth desktop client JSON file to connect Drive."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_file,
                DRIVE_SCOPES,
            )
            credentials = flow.run_local_server(
                host="127.0.0.1",
                port=0,
                open_browser=True,
                access_type="offline",
                prompt="consent",
            )

        store_secret(
            DRIVE_TOKEN_TARGET,
            credentials.to_json(),
        )

    return credentials


def _get_encryption_key():
    stored_key = read_secret(DRIVE_KEY_TARGET)
    if stored_key:
        try:
            key = bytes.fromhex(stored_key)
        except ValueError as error:
            raise RuntimeError(
                "The saved Google Drive backup encryption key is invalid."
            ) from error
        if len(key) != 32:
            raise RuntimeError(
                "The saved Google Drive backup encryption key is invalid."
            )
        return key

    key = secrets.token_bytes(32)
    store_secret(DRIVE_KEY_TARGET, key.hex())
    return key


def _get_key_from_file(recovery_key_file):
    try:
        key = bytes.fromhex(
            Path(recovery_key_file).read_text(encoding="ascii").strip()
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError("The backup recovery key file is invalid.") from error
    if len(key) != 32:
        raise RuntimeError("The backup recovery key file is invalid.")
    return key


def export_backup_recovery_key(destination):
    key = _get_encryption_key()
    Path(destination).write_text(key.hex(), encoding="ascii")


def list_drive_backups(client_secret_file=None):
    credentials = _get_drive_credentials(client_secret_file)
    drive = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )
    response = drive.files().list(
        q="name contains 'library-backup-' and trashed = false",
        orderBy="createdTime desc",
        pageSize=100,
        fields="files(id,name,createdTime,size)",
    ).execute()
    return response.get("files", [])


def download_and_decrypt_backup(
    file_id,
    destination,
    client_secret_file=None,
    recovery_key_file=None,
    active_database_path=None,
):
    destination = Path(destination).resolve()
    if (
        active_database_path
        and destination == Path(active_database_path).resolve()
    ):
        raise ValueError(
            "Restore to a separate file. The active database cannot be overwritten."
        )

    credentials = _get_drive_credentials(client_secret_file)
    drive = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    with tempfile.TemporaryDirectory(prefix="library-drive-restore-") as folder:
        encrypted_path = Path(folder) / "backup.clbk"
        request = drive.files().get_media(fileId=file_id)
        with encrypted_path.open("wb") as file:
            downloader = MediaIoBaseDownload(file, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        encrypted = encrypted_path.read_bytes()
        if not encrypted.startswith(BACKUP_HEADER) or len(encrypted) < 33:
            raise RuntimeError("The selected Drive file is not a valid library backup.")

        if recovery_key_file:
            key = _get_key_from_file(recovery_key_file)
        else:
            stored_key = read_secret(DRIVE_KEY_TARGET)
            if not stored_key:
                raise RuntimeError(
                    "This Windows account has no backup encryption key. "
                    "Select the recovery key file exported from the original computer."
                )
            key = _get_encryption_key()

        nonce = encrypted[len(BACKUP_HEADER):len(BACKUP_HEADER) + 12]
        ciphertext = encrypted[len(BACKUP_HEADER) + 12:]
        try:
            database_bytes = AESGCM(key).decrypt(
                nonce,
                ciphertext,
                BACKUP_HEADER,
            )
        except Exception as error:
            raise RuntimeError(
                "Could not decrypt this backup. Check that the recovery key matches."
            ) from error

        restored_path = Path(folder) / "restored.db"
        restored_path.write_bytes(database_bytes)
        restored_db = sqlite3.connect(os.fspath(restored_path))
        try:
            integrity = restored_db.execute(
                "PRAGMA integrity_check"
            ).fetchone()
        finally:
            restored_db.close()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("The decrypted database failed its integrity check.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(database_bytes)

    return os.fspath(destination)


def upload_encrypted_database_backup(db, client_secret_file=None):
    credentials = _get_drive_credentials(client_secret_file)
    drive = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )
    key = _get_encryption_key()

    with tempfile.TemporaryDirectory(prefix="library-drive-backup-") as folder:
        folder_path = Path(folder)
        database_path = folder_path / "library.db"
        encrypted_path = folder_path / "library-backup.clbk"

        success, result = db.backup_database(database_path)
        if not success:
            raise RuntimeError(f"Unable to create local backup: {result}")

        nonce = secrets.token_bytes(12)
        aes_gcm = AESGCM(key)
        ciphertext = aes_gcm.encrypt(
            nonce,
            database_path.read_bytes(),
            BACKUP_HEADER,
        )
        encrypted_path.write_bytes(
            BACKUP_HEADER + nonce + ciphertext
        )

        filename = (
            f"library-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}.clbk"
        )
        media = MediaFileUpload(
            os.fspath(encrypted_path),
            mimetype="application/octet-stream",
            resumable=True,
        )
        result = drive.files().create(
            body={
                "name": filename,
                "description": (
                    "Encrypted campus library SQLite backup. "
                    "The decryption key is stored in this Windows account's "
                    "Credential Manager."
                ),
            },
            media_body=media,
            fields="id,name",
        ).execute()

    return result

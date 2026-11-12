import datetime
import json
import os
import secrets
import sqlite3
import sys
import tempfile
from pathlib import Path

from secure_storage import delete_secret, read_secret, store_secret
from utils import get_appdata_db_path


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DRIVE_TOKEN_TARGET = "CampusLibrary/GoogleDriveOAuth"
DRIVE_CLIENT_TARGET = "CampusLibrary/GoogleDriveClientConfig"
DRIVE_KEY_TARGET = "CampusLibrary/GoogleDriveBackupKey"
BACKUP_HEADER = b"CLBK1"
DEFAULT_CLIENT_FILENAME = "google_drive_client.json"


def _safe_read_secret(target):
    try:
        return read_secret(target)
    except OSError:
        return None


def is_drive_connected():
    return bool(_safe_read_secret(DRIVE_TOKEN_TARGET))


def validate_and_parse_drive_client_json(raw_text_or_dict):
    """Validate Google OAuth Desktop Client JSON and return (dict, compact_json)."""
    if isinstance(raw_text_or_dict, dict):
        parsed = raw_text_or_dict
    else:
        raw_text = str(raw_text_or_dict or "").strip()
        if not raw_text:
            raise RuntimeError("The Google OAuth client JSON is empty.")
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"The selected client configuration is not valid JSON: {error.msg}"
            ) from error

    if not isinstance(parsed, dict):
        raise RuntimeError("Invalid Google OAuth client JSON structure.")

    if parsed.get("type") == "service_account":
        raise RuntimeError(
            "This file is a Google Service Account key. Create and select an "
            "OAuth 2.0 'Desktop app' client JSON instead."
        )

    section = parsed.get("installed") or parsed.get("web")
    if not isinstance(section, dict):
        raise RuntimeError(
            "Invalid Google OAuth client JSON. Expected a Desktop App JSON "
            "containing an 'installed' configuration block."
        )

    for required_key in ("client_id", "auth_uri", "token_uri"):
        if not str(section.get(required_key) or "").strip():
            raise RuntimeError(
                f"The Google OAuth client JSON is missing '{required_key}'."
            )

    return parsed, json.dumps(parsed, separators=(",", ":"))


def _candidate_drive_client_paths():
    """Return prioritized non-committed paths checked for pre-configured OAuth client JSON."""
    candidates = []
    try:
        candidates.append(Path(get_appdata_db_path()).parent / DEFAULT_CLIENT_FILENAME)
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        candidates.append(
            Path(sys.executable).resolve().parent / DEFAULT_CLIENT_FILENAME
        )

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / DEFAULT_CLIENT_FILENAME)
        candidates.append(Path(meipass) / DEFAULT_CLIENT_FILENAME)

    module_dir = Path(__file__).resolve().parent
    candidates.append(module_dir / "assets" / DEFAULT_CLIENT_FILENAME)
    candidates.append(module_dir / DEFAULT_CLIENT_FILENAME)

    unique = []
    seen = set()
    for path in candidates:
        key = os.fspath(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def save_drive_client_config(client_secret_file=None, client_json_text=None):
    """Validate and save OAuth client JSON once into Windows Credential Manager."""
    if client_secret_file:
        try:
            raw_text = Path(client_secret_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeError(
                f"Could not read the selected client JSON file: {error}"
            ) from error
    else:
        raw_text = client_json_text

    parsed, normalized_json = validate_and_parse_drive_client_json(raw_text)
    store_secret(DRIVE_CLIENT_TARGET, normalized_json)
    return parsed


def clear_drive_client_config():
    """Remove saved Google OAuth client JSON from Windows Credential Manager."""
    delete_secret(DRIVE_CLIENT_TARGET)


def resolve_drive_client_config(client_secret_file=None):
    """Locate OAuth client JSON from explicit file, Credential Manager, or IT-deployed sidecar."""
    if client_secret_file:
        try:
            parsed = save_drive_client_config(client_secret_file=client_secret_file)
            return parsed, "Saved from imported file"
        except OSError:
            raw_text = Path(client_secret_file).read_text(encoding="utf-8")
            parsed, _ = validate_and_parse_drive_client_json(raw_text)
            return parsed, "Loaded from file"

    stored_client = _safe_read_secret(DRIVE_CLIENT_TARGET)
    if stored_client:
        try:
            parsed, _ = validate_and_parse_drive_client_json(stored_client)
            return parsed, "Saved in Windows Credential Manager"
        except RuntimeError:
            pass

    for candidate in _candidate_drive_client_paths():
        if candidate.is_file():
            try:
                raw_text = candidate.read_text(encoding="utf-8")
                parsed, _ = validate_and_parse_drive_client_json(raw_text)
                return parsed, f"Pre-configured file ({candidate.name})"
            except (OSError, UnicodeError, RuntimeError):
                continue

    return None, None


def has_drive_client_config():
    config, _ = resolve_drive_client_config()
    return config is not None


def get_drive_status():
    """Return current Google Drive connection & OAuth client configuration state."""
    connected = is_drive_connected()
    config, source = resolve_drive_client_config()
    return {
        "connected": connected,
        "has_client_config": config is not None,
        "client_source": source or "",
    }


def _get_drive_credentials(client_secret_file=None, force_reauth=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    stored_token = None if force_reauth else _safe_read_secret(DRIVE_TOKEN_TARGET)
    credentials = None

    if stored_token:
        credentials = Credentials.from_authorized_user_info(
            json.loads(stored_token),
            DRIVE_SCOPES,
        )

    if not credentials or not credentials.valid:
        if (
            not force_reauth
            and credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(Request())
        else:
            client_config, _ = resolve_drive_client_config(client_secret_file)
            if client_config is None:
                raise RuntimeError(
                    "Google Drive OAuth is not set up yet. Click 'Connect Google Drive' "
                    "once to sign in with an OAuth client JSON, ask IT to pre-place "
                    f"'{DEFAULT_CLIENT_FILENAME}', or use Synced Folder Backup below "
                    "(works with Google Drive for Desktop / OneDrive / USB with zero client.json)."
                )
            flow = InstalledAppFlow.from_client_config(
                client_config,
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


def connect_drive(client_secret_file=None, client_json_text=None, force_reauth=False):
    """Save optional OAuth client JSON (once) and complete Google sign-in."""
    if client_json_text is not None and str(client_json_text).strip():
        save_drive_client_config(client_json_text=client_json_text)
    _get_drive_credentials(
        client_secret_file=client_secret_file,
        force_reauth=force_reauth,
    )
    return get_drive_status()


def disconnect_drive(clear_client_config=False):
    """Sign out of Google Drive while preserving the backup encryption key."""
    delete_secret(DRIVE_TOKEN_TARGET)
    if clear_client_config:
        clear_drive_client_config()
    return get_drive_status()


def _get_encryption_key():
    stored_key = _safe_read_secret(DRIVE_KEY_TARGET)
    if stored_key:
        try:
            key = bytes.fromhex(stored_key)
        except ValueError as error:
            raise RuntimeError(
                "The saved backup encryption key is invalid."
            ) from error
        if len(key) != 32:
            raise RuntimeError(
                "The saved backup encryption key is invalid."
            )
        return key

    key = secrets.token_bytes(32)
    store_secret(DRIVE_KEY_TARGET, key.hex())
    return key


def has_backup_encryption_key():
    return bool(_safe_read_secret(DRIVE_KEY_TARGET))


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
    from googleapiclient.discovery import build

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


def decrypt_backup_file(
    encrypted_file_path,
    destination,
    recovery_key_file=None,
    active_database_path=None,
):
    """Decrypt and verify a .clbk backup file into a standalone SQLite database file."""
    destination = Path(destination).resolve()
    if (
        active_database_path
        and destination == Path(active_database_path).resolve()
    ):
        raise ValueError(
            "Restore to a separate file. The active database cannot be overwritten."
        )

    encrypted = Path(encrypted_file_path).read_bytes()
    if not encrypted.startswith(BACKUP_HEADER) or len(encrypted) < 33:
        raise RuntimeError("The selected file is not a valid encrypted library backup.")

    if recovery_key_file:
        key = _get_key_from_file(recovery_key_file)
    else:
        stored_key = _safe_read_secret(DRIVE_KEY_TARGET)
        if not stored_key:
            raise RuntimeError(
                "This Windows account has no backup encryption key. "
                "Select the recovery key file exported from the original computer."
            )
        key = _get_encryption_key()

    nonce = encrypted[len(BACKUP_HEADER):len(BACKUP_HEADER) + 12]
    ciphertext = encrypted[len(BACKUP_HEADER) + 12:]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        database_bytes = AESGCM(key).decrypt(
            nonce,
            ciphertext,
            BACKUP_HEADER,
        )
    except Exception as error:
        raise RuntimeError(
            "Could not decrypt this backup. Check that the recovery key matches."
        ) from error

    with tempfile.TemporaryDirectory(prefix="library-verify-restore-") as folder:
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

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

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

        return decrypt_backup_file(
            encrypted_path,
            destination,
            recovery_key_file=recovery_key_file,
            active_database_path=active_database_path,
        )


def create_encrypted_backup_file(db, destination_path):
    """Create an AES-256-GCM encrypted backup of the SQLite database at destination_path."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    destination = Path(destination_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    key = _get_encryption_key()

    with tempfile.TemporaryDirectory(prefix="library-backup-stage-") as folder:
        stage_db = Path(folder) / "library.db"
        success, result = db.backup_database(stage_db)
        if not success:
            raise RuntimeError(f"Unable to create local backup: {result}")

        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(
            nonce,
            stage_db.read_bytes(),
            BACKUP_HEADER,
        )

        temp_out = destination.with_name(f"{destination.name}.{secrets.token_hex(4)}.tmp")
        try:
            temp_out.write_bytes(BACKUP_HEADER + nonce + ciphertext)
            os.replace(temp_out, destination)
        finally:
            if temp_out.exists():
                try:
                    temp_out.unlink()
                except OSError:
                    pass

    return os.fspath(destination)


def backup_to_sync_folder(db, folder_path, max_keep=30):
    """Save an encrypted backup into a local/synced folder (Google Drive Desktop, OneDrive, USB)."""
    folder_text = str(folder_path or "").strip()
    if not folder_text:
        raise ValueError("Select a destination folder for synced folder backup.")

    target_dir = Path(folder_text).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"library-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}.clbk"
    dest = target_dir / filename
    counter = 1
    while dest.exists():
        filename = f"library-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}-{counter}.clbk"
        dest = target_dir / filename
        counter += 1

    saved_path = create_encrypted_backup_file(db, dest)

    if max_keep and max_keep > 0:
        existing = sorted(
            target_dir.glob("library-backup-*.clbk"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in existing[max_keep:]:
            try:
                stale.unlink()
            except OSError:
                pass

    return {"name": Path(saved_path).name, "path": saved_path}


def upload_encrypted_database_backup(db, client_secret_file=None):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    credentials = _get_drive_credentials(client_secret_file)
    drive = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    with tempfile.TemporaryDirectory(prefix="library-drive-backup-") as folder:
        encrypted_path = Path(folder) / "library-backup.clbk"
        create_encrypted_backup_file(db, encrypted_path)

        filename = (
            f"library-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}.clbk"
        )
        with encrypted_path.open("rb") as encrypted_file:
            media = MediaIoBaseUpload(
                encrypted_file,
                mimetype="application/octet-stream",
                resumable=True,
            )
            result = drive.files().create(
                body={
                    "name": filename,
                    "description": (
                        "Encrypted library SQLite backup. "
                        "The decryption key is stored in this Windows account's "
                        "Credential Manager."
                    ),
                },
                media_body=media,
                fields="id,name",
            ).execute()

    return result

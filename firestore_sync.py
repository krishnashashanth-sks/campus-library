"""Authenticated, incremental desktop-to-Firestore book synchronization."""

import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
from urllib.parse import quote, urlsplit

import requests

from firebase_sync_config import (
    FIREBASE_API_KEY,
    FIREBASE_PROJECT_ID,
    FIRESTORE_DATABASE_ID,
)

logger = logging.getLogger(__name__)

FIREBASE_SYNC_PASSWORD_TARGET = "CampusLib.FirebaseSync.Password"
FIREBASE_SYNC_REFRESH_TOKEN_TARGET = "CampusLib.FirebaseSync.RefreshToken"
_BOOK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_WRITES_PER_COMMIT = 400
_QUERY_PAGE_SIZE = 1000
_CURSOR_OVERLAP_SECONDS = 60


def find_service_account_path():
    """Discover a Google Cloud / Firebase service account key in known locations."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_data = os.getenv("APPDATA") or os.path.expanduser("~")
    candidates = [
        os.path.join(base_dir, "serviceAccountKey.json"),
        os.path.join(base_dir, "assets", "serviceAccountKey.json"),
        os.path.abspath(os.path.join(base_dir, "..", "CampusLib", "serviceAccountKey.json")),
        os.path.join(app_data, "Library", "serviceAccountKey.json"),
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


class FirestoreSyncError(RuntimeError):
    """A network, authentication, Firestore, or local-sync failure."""


class EmailVerificationRequiredError(FirestoreSyncError):
    """The staff account cannot sync until its email address is verified."""

    def __init__(
        self,
        message,
        *,
        email_sent=False,
        email_recently_sent=False,
        send_error=None,
    ):
        super().__init__(message)
        self.email_sent = email_sent
        self.email_recently_sent = email_recently_sent
        self.send_error = send_error


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _time_text(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        parsed = value
    else:
        parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _encode_value(value):
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_encode_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {key: _encode_value(item) for key, item in value.items()}}}
    return {"stringValue": str(value)}


def _decode_value(value):
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "nullValue" in value:
        return None
    if "arrayValue" in value:
        return [_decode_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {
            key: _decode_value(item)
            for key, item in value["mapValue"].get("fields", {}).items()
        }
    return None


def _decode_document(document):
    fields = {
        key: _decode_value(value)
        for key, value in document.get("fields", {}).items()
    }
    name = document.get("name", "")
    return {
        "id": name.rsplit("/", 1)[-1],
        "fields": fields,
        "updateTime": document.get("updateTime"),
        "name": name,
    }


def _book_payload(book):
    book_id = str(book["id"]).strip()
    if not _BOOK_ID_RE.fullmatch(book_id):
        raise FirestoreSyncError(
            f"Book ID {book_id!r} cannot be used as a Firestore document ID. "
            "Use letters, numbers, underscores, or hyphens."
        )

    title = str(book.get("title") or "").strip()
    if not title or len(title) > 240:
        raise FirestoreSyncError(
            f"Book {book_id} has an empty title or a title longer than 240 characters."
        )

    try:
        total = int(book.get("total_copies") or 0)
        available = int(book.get("available_copies") or 0)
    except (TypeError, ValueError) as exc:
        raise FirestoreSyncError(f"Book {book_id} has invalid copy counts.") from exc
    if total < 0 or total > 10000 or available < 0 or available > total:
        raise FirestoreSyncError(
            f"Book {book_id} has invalid copy counts "
            f"(available={available}, total={total})."
        )
    return {
        "id": book_id,
        "isbn": str(book.get("isbn") or "")[:32],
        "title": title,
        "author": str(book.get("author") or "")[:160],
        "publisher": str(book.get("publisher") or "")[:160],
        "category": str(book.get("category") or "General")[:80],
        "shelfLocation": str(book.get("shelf_location") or "Main Stack")[:64],
        "totalCopies": total,
        "availableCopies": available,
    }


def _book_hash(book):
    payload = _book_payload(book)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _remote_book_payload(document):
    fields = document["fields"]
    return {
        "id": document["id"],
        "isbn": fields.get("isbn", ""),
        "title": fields.get("title", ""),
        "author": fields.get("author", ""),
        "publisher": fields.get("publisher", ""),
        "category": fields.get("category") or "General",
        "shelfLocation": fields.get("shelfLocation") or "Main Stack",
        "totalCopies": fields.get("totalCopies", 0),
        "availableCopies": fields.get("availableCopies", 0),
    }


def _local_is_newer(local_book, remote_document):
    local_time = _parse_time(local_book.get("updated_at"))
    remote_time = _parse_time(remote_document["fields"].get("updatedAt"))
    if local_time is None:
        return False
    if remote_time is None:
        return True
    return local_time > remote_time


class FirestoreRestClient:
    def __init__(self, session=None, timeout=20, send_verification_email=True):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.send_verification_email = send_verification_email
        self.id_token = None
        self.refresh_token = None
        self.uid = None
        self.is_service_account = False
        self._sa_creds = None
        self._sa_transport = None
        self._sa_path = None
        self._database_root = (
            f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
            f"/databases/{quote(FIRESTORE_DATABASE_ID, safe='')}/documents"
        )

    def _auth_url(self, action):
        return (
            f"https://identitytoolkit.googleapis.com/v1/accounts:{action}"
            f"?key={quote(FIREBASE_API_KEY, safe='')}"
        )

    def _token_url(self):
        return (
            "https://securetoken.googleapis.com/v1/token"
            f"?key={quote(FIREBASE_API_KEY, safe='')}"
        )

    def _raise_response_error(self, response, operation):
        try:
            data = response.json()
        except ValueError:
            data = {}
        raw_error = data.get("error") if isinstance(data, dict) else None
        message = raw_error.get("message") if isinstance(raw_error, dict) else raw_error
        if raw_error == "invalid_grant":
            message = "The saved Firebase session expired or was revoked. Reconnect the staff account."
        if message in ("INVALID_LOGIN_CREDENTIALS", "EMAIL_NOT_FOUND", "INVALID_PASSWORD"):
            message = "The Firebase email or password is incorrect."
        elif message == "EMAIL_NOT_VERIFIED":
            raise EmailVerificationRequiredError(
                f"{operation} failed: The account email is not verified. "
                "Use the website's Resend verification email option, then sync again."
            )
        elif message in ("USER_DISABLED", "TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_NOT_FOUND"):
            message = "The saved Firebase session expired or was revoked. Reconnect the staff account."
        elif not message:
            message = f"HTTP {response.status_code}"
        raise FirestoreSyncError(f"{operation} failed: {message}")

    def _post_auth(self, url, payload, operation, *, form=False):
        try:
            request_payload = {"data": payload} if form else {"json": payload}
            response = self.session.post(url, timeout=self.timeout, **request_payload)
        except requests.RequestException as exc:
            raise FirestoreSyncError(f"{operation} network error: {exc}") from exc
        if not response.ok:
            self._raise_response_error(response, operation)
        try:
            data = response.json()
        except ValueError as exc:
            raise FirestoreSyncError(f"{operation} returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise FirestoreSyncError(f"{operation} returned an invalid response.")
        return data

    def _ensure_email_verified(self, email):
        if not self.id_token:
            raise FirestoreSyncError(
                "Firebase did not return an ID token to verify the account status."
            )

        data = self._post_auth(
            self._auth_url("lookup"),
            {"idToken": self.id_token},
            "Firebase account status check",
        )
        users = data.get("users")
        if not isinstance(users, list) or not users or not isinstance(users[0], dict):
            raise FirestoreSyncError(
                "Firebase account status check returned no user profile."
            )

        user = users[0]
        verified_email = str(user.get("email") or "").strip().casefold()
        expected_email = str(email or "").strip().casefold()
        if verified_email and expected_email and verified_email != expected_email:
            raise FirestoreSyncError(
                "Firebase signed in a different email account than the one configured "
                "for desktop sync. Reconnect using the intended staff account."
            )
        if user.get("localId") and self.uid and user["localId"] != self.uid:
            raise FirestoreSyncError(
                "Firebase account status did not match the signed-in user."
            )
        self.uid = user.get("localId") or self.uid

        if user.get("emailVerified"):
            return

        if not self.send_verification_email:
            raise EmailVerificationRequiredError(
                "Firebase still reports this account's email as unverified. "
                "A verification email was sent recently; check Inbox and Spam/Junk.",
                email_recently_sent=True,
            )

        try:
            self._post_auth(
                self._auth_url("sendOobCode"),
                {"requestType": "VERIFY_EMAIL", "idToken": self.id_token},
                "Firebase verification email",
            )
        except FirestoreSyncError as exc:
            raise EmailVerificationRequiredError(
                "Firebase still reports this account's email as unverified, and "
                f"could not send a verification email: {exc}",
                send_error=str(exc),
            ) from exc
        raise EmailVerificationRequiredError(
            "Firebase still reports this account's email as unverified. A new "
            "verification link was sent; open the newest link, then select "
            "Sync with Cloud Now.",
            email_sent=True,
        )

    def auth_service_account(self, sa_path=None):
        """Authenticate using Google Cloud Service Account credentials (Root Authority)."""
        path = sa_path or find_service_account_path()
        if not path or not os.path.isfile(path):
            raise FirestoreSyncError("No serviceAccountKey.json file found.")
        try:
            from google.oauth2 import service_account
            import google.auth.transport.requests

            creds = service_account.Credentials.from_service_account_file(
                path,
                scopes=[
                    "https://www.googleapis.com/auth/cloud-platform",
                    "https://www.googleapis.com/auth/datastore",
                ],
            )
            transport = google.auth.transport.requests.Request()
            last_err = None
            for attempt in range(4):
                try:
                    creds.refresh(transport)
                    last_err = None
                    break
                except Exception as ref_exc:
                    last_err = ref_exc
                    import time
                    time.sleep(1.0 * (attempt + 1))
            if last_err is not None:
                raise last_err
            self._sa_creds = creds
            self._sa_transport = transport
            self._sa_path = path
            self.id_token = creds.token
            self.uid = f"service_account:{creds.service_account_email}"
            self.is_service_account = True
            logger.info("Authenticated FirestoreRestClient via Service Account (%s)", creds.service_account_email)
            return self.uid
        except Exception as exc:
            raise FirestoreSyncError(f"Service Account authentication failed: {exc}") from exc

    def sign_in(self, email, password):
        if not email or not password:
            raise FirestoreSyncError("Enter the verified Firebase staff account email and password.")
        data = self._post_auth(
            self._auth_url("signInWithPassword"),
            {"email": email, "password": password, "returnSecureToken": True},
            "Firebase sign-in",
        )
        self.id_token = data.get("idToken")
        self.refresh_token = data.get("refreshToken")
        self.uid = data.get("localId")
        if not self.id_token or not self.refresh_token or not self.uid:
            raise FirestoreSyncError("Firebase sign-in did not return a complete staff session.")
        self._ensure_email_verified(email)
        return self.uid

    def refresh_session(self, refresh_token):
        data = self._post_auth(
            self._token_url(),
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            "Firebase session refresh",
            form=True,
        )
        self.id_token = data.get("id_token")
        self.refresh_token = data.get("refresh_token") or refresh_token
        self.uid = data.get("user_id")
        if not self.id_token or not self.uid:
            raise FirestoreSyncError("Firebase session refresh returned an incomplete session.")
        self._ensure_email_verified(None)
        return self.uid

    def _request_json(self, method, url, operation, *, params=None, payload=None):
        for attempt in range(5):
            headers = {"Authorization": f"Bearer {self.id_token}"}
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                try:
                    self.session.close()
                    self.session = requests.Session()
                except Exception:
                    pass
                if attempt < 4:
                    logger.warning("%s attempt %d failed with network error (%s), retrying in %.1fs...", operation, attempt + 1, exc, 1.5 * (attempt + 1))
                    import time
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise FirestoreSyncError(f"{operation} network error: {exc}") from exc
            if response.status_code == 401 and attempt == 0:
                if getattr(self, "is_service_account", False) and self._sa_creds:
                    try:
                        self._sa_creds.refresh(self._sa_transport)
                        self.id_token = self._sa_creds.token
                        continue
                    except Exception as refresh_err:
                        logger.warning("Service Account token refresh failed: %s", refresh_err)
                elif self.refresh_token:
                    self.refresh_session(self.refresh_token)
                    continue
            if not response.ok:
                if (
                    response.status_code == 403
                    and operation == "Firestore book catalog read"
                ):
                    request = getattr(response, "request", None)
                    request_headers = getattr(request, "headers", {}) or {}
                    bearer_present = str(
                        request_headers.get("Authorization", "")
                    ).startswith("Bearer ")
                    response_url = urlsplit(getattr(response, "url", url))
                    redirect_count = len(getattr(response, "history", None) or [])
                    operation = (
                        f"{operation} [HTTP 403; endpoint="
                        f"{response_url.netloc}{response_url.path}; "
                        f"Firebase bearer header="
                        f"{'present' if bearer_present else 'missing'}; "
                        f"redirects={redirect_count}]"
                    )
                self._raise_response_error(response, operation)
            try:
                return response.json()
            except ValueError as exc:
                raise FirestoreSyncError(f"{operation} returned invalid JSON.") from exc
        raise FirestoreSyncError(f"{operation} failed after refreshing the Firebase session.")

    def _book_document_url(self, book_id):
        if not _BOOK_ID_RE.fullmatch(str(book_id)):
            raise FirestoreSyncError(f"Invalid Firestore book ID: {book_id!r}")
        return f"{self._database_root}/books/{quote(str(book_id), safe='')}"

    def list_books(self):
        documents = {}
        page_token = None
        while True:
            params = {"pageSize": _QUERY_PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            response = self._request_json(
                "GET",
                f"{self._database_root}/books",
                "Firestore book catalog read",
                params=params,
            )
            for raw_document in response.get("documents", []):
                document = _decode_document(raw_document)
                documents[document["id"]] = document
            page_token = response.get("nextPageToken")
            if not page_token:
                return documents

    def get_books_since(self, cursor):
        cursor_time = _parse_time(cursor)
        if cursor_time is None:
            return self.list_books(), None
        cursor_time -= datetime.timedelta(seconds=_CURSOR_OVERLAP_SECONDS)
        filter_value = {"timestampValue": _time_text(cursor_time)}
        documents = {}
        read_time = None
        start_after = None

        while True:
            query = {
                "from": [{"collectionId": "books"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "updatedAt"},
                        "op": "GREATER_THAN_OR_EQUAL",
                        "value": filter_value,
                    }
                },
                "orderBy": [
                    {"field": {"fieldPath": "updatedAt"}, "direction": "ASCENDING"},
                    {"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"},
                ],
                "limit": _QUERY_PAGE_SIZE,
            }
            if start_after:
                query["startAt"] = {
                    "values": [
                        {"timestampValue": start_after["updatedAt"]},
                        {"referenceValue": start_after["name"]},
                    ],
                    "before": False,
                }
            rows = self._request_json(
                "POST",
                f"{self._database_root}:runQuery",
                "Incremental Firestore book read",
                payload={"structuredQuery": query},
            )
            page_documents = []
            for row in rows if isinstance(rows, list) else []:
                if row.get("error"):
                    message = row["error"].get("message", "Firestore query failed.")
                    raise FirestoreSyncError(f"Incremental Firestore book read failed: {message}")
                read_time = max(
                    filter(None, (read_time, row.get("readTime"))),
                    default=read_time,
                )
                raw_document = row.get("document")
                if raw_document:
                    document = _decode_document(raw_document)
                    documents[document["id"]] = document
                    page_documents.append(document)
            if len(page_documents) < _QUERY_PAGE_SIZE:
                return documents, read_time
            last_document = page_documents[-1]
            updated_at = last_document["fields"].get("updatedAt")
            if not updated_at:
                raise FirestoreSyncError(
                    f"Firestore book {last_document['id']} has no updatedAt timestamp."
                )
            start_after = {
                "updatedAt": updated_at,
                "name": last_document["name"],
            }

    def get_books_by_ids(self, book_ids):
        documents = {}
        ids = list(book_ids)
        for start in range(0, len(ids), _MAX_WRITES_PER_COMMIT):
            invalid_ids = [
                str(book_id)
                for book_id in ids[start:start + _MAX_WRITES_PER_COMMIT]
                if not _BOOK_ID_RE.fullmatch(str(book_id))
            ]
            if invalid_ids:
                raise FirestoreSyncError(
                    "Cannot look up invalid Firestore book ID(s): "
                    + ", ".join(repr(book_id) for book_id in invalid_ids)
                )
            names = [
                (
                    f"projects/{FIREBASE_PROJECT_ID}/databases/"
                    f"{FIRESTORE_DATABASE_ID}/documents/books/"
                    f"{quote(str(book_id), safe='')}"
                )
                for book_id in ids[start:start + _MAX_WRITES_PER_COMMIT]
            ]
            response = self._request_json(
                "POST",
                f"{self._database_root}:batchGet",
                "Firestore book lookup",
                payload={"documents": names},
            )
            for result in response if isinstance(response, list) else []:
                raw_document = result.get("found")
                if raw_document:
                    document = _decode_document(raw_document)
                    documents[document["id"]] = document
        return documents

    def _book_write(self, book, existing, uid):
        payload = _book_payload(book)
        document_url = self._book_document_url(payload["id"])
        document_name = document_url[len("https://firestore.googleapis.com/v1/"):]
        fields = {key: _encode_value(value) for key, value in payload.items()}
        fields["updatedBy"] = _encode_value(uid)
        fields["source"] = _encode_value("offline_app")
        transforms = [
            {"fieldPath": "updatedAt", "setToServerValue": "REQUEST_TIME"},
            {"fieldPath": "lastUpdated", "setToServerValue": "REQUEST_TIME"},
        ]
        write = {
            "update": {"name": document_name, "fields": fields},
            "updateMask": {
                "fieldPaths": list(payload.keys()) + ["updatedBy", "source"]
            },
            "updateTransforms": transforms,
        }
        if existing:
            update_time = existing.get("updateTime")
            if update_time:
                write["currentDocument"] = {"updateTime": update_time}
            return write

        write["updateTransforms"].insert(
            0,
            {"fieldPath": "createdAt", "setToServerValue": "REQUEST_TIME"},
        )
        write["currentDocument"] = {"exists": False}
        return write

    def commit_book_writes(self, books, existing_by_id, uid):
        updated_times = {}
        for start in range(0, len(books), _MAX_WRITES_PER_COMMIT):
            batch = books[start:start + _MAX_WRITES_PER_COMMIT]
            writes = [
                self._book_write(book, existing_by_id.get(str(book["id"])), uid)
                for book in batch
            ]
            response = self._request_json(
                "POST",
                f"{self._database_root}:commit",
                "Firestore book write",
                payload={"writes": writes},
            )
            results = response.get("writeResults", [])
            if len(results) != len(batch):
                raise FirestoreSyncError(
                    "Firestore confirmed an unexpected number of book writes."
                )
            for book, result in zip(batch, results):
                updated_times[str(book["id"])] = result.get("updateTime") or response.get("commitTime")
        return updated_times

    def write_sync_metadata(self, book_count, synced_books, members_count=None, circulation_logs_count=None):
        document_name = (
            f"projects/{FIREBASE_PROJECT_ID}/databases/{FIRESTORE_DATABASE_ID}"
            "/documents/metadata/sync_state"
        )
        fields = {
            "status": _encode_value("SUCCESS"),
            "bookCount": _encode_value(int(book_count)),
            "lastError": _encode_value(""),
            "source": _encode_value("offline_desktop"),
            "syncedBooks": _encode_value(int(synced_books)),
        }
        if members_count is not None:
            fields["membersCount"] = _encode_value(int(members_count))
        if circulation_logs_count is not None:
            fields["circulationLogsCount"] = _encode_value(int(circulation_logs_count))
        payload = {
            "writes": [{
                "update": {"name": document_name, "fields": fields},
                "updateMask": {"fieldPaths": list(fields.keys())},
                "updateTransforms": [
                    {"fieldPath": "lastOfflineSyncAt", "setToServerValue": "REQUEST_TIME"},
                    {"fieldPath": "lastClbkSyncAt", "setToServerValue": "REQUEST_TIME"},
                ],
            }]
        }
        self._request_json(
            "POST",
            f"{self._database_root}:commit",
            "Firestore sync status update",
            payload=payload,
        )


def _ensure_sync_tables(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS firestore_book_sync_state (
            book_id TEXT PRIMARY KEY COLLATE NOCASE,
            local_hash TEXT NOT NULL,
            remote_updated_at TEXT,
            remote_update_time TEXT
        )
    """)


def _load_local_books(connection):
    rows = connection.execute("""
        SELECT id, isbn, title, author, publisher, category, shelf_location,
               total_copies, available_copies, created_at, updated_at
        FROM books
    """).fetchall()
    return {str(row["id"]): dict(row) for row in rows}


def _load_sync_state(connection):
    rows = connection.execute("""
        SELECT book_id, local_hash, remote_updated_at, remote_update_time
        FROM firestore_book_sync_state
    """).fetchall()
    return {str(row["book_id"]): dict(row) for row in rows}


def _apply_remote_book(connection, document):
    fields = _remote_book_payload(document)
    created_at = document["fields"].get("createdAt")
    updated_at = document["fields"].get("updatedAt")
    connection.execute("""
        INSERT INTO books (
            id, isbn, title, author, publisher, category, shelf_location,
            total_copies, available_copies, created_at, updated_at, last_modified_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'web')
        ON CONFLICT(id) DO UPDATE SET
            isbn = excluded.isbn,
            title = excluded.title,
            author = excluded.author,
            publisher = excluded.publisher,
            category = excluded.category,
            shelf_location = excluded.shelf_location,
            total_copies = excluded.total_copies,
            available_copies = excluded.available_copies,
            created_at = COALESCE(books.created_at, excluded.created_at),
            updated_at = excluded.updated_at,
            last_modified_by = 'web'
    """, (
        fields["id"],
        fields["isbn"] or None,
        fields["title"],
        fields["author"],
        fields["publisher"],
        fields["category"],
        fields["shelfLocation"],
        fields["totalCopies"],
        fields["availableCopies"],
        created_at,
        updated_at,
    ))


def _store_sync_state(connection, book_id, local_hash, remote_document):
    fields = remote_document["fields"] if remote_document else {}
    connection.execute("""
        INSERT INTO firestore_book_sync_state (
            book_id, local_hash, remote_updated_at, remote_update_time
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(book_id) DO UPDATE SET
            local_hash = excluded.local_hash,
            remote_updated_at = excluded.remote_updated_at,
            remote_update_time = excluded.remote_update_time
    """, (
        book_id,
        local_hash,
        fields.get("updatedAt"),
        remote_document.get("updateTime") if remote_document else None,
    ))


def _set_setting(connection, key, value):
    connection.execute("""
        INSERT INTO settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))


def sync_books(
    database_path,
    email=None,
    *,
    password=None,
    refresh_token=None,
    service_account_path=None,
    send_verification_email=True,
    force_full_scan=False,
    client=None,
    on_refresh_token=None,
):
    """Reconcile the desktop book catalog with Firestore without deleting either side."""
    client = client or FirestoreRestClient(
        send_verification_email=send_verification_email
    )
    connection = sqlite3.connect(database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 15000")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_sync_tables(connection)
        connection.commit()

        uid = None

        # 1. Automatic Service Account authentication (Root Authority)
        if getattr(client, "is_service_account", False):
            uid = client.uid
        elif service_account_path or (not refresh_token and not password):
            candidate_sa = service_account_path or find_service_account_path()
            if candidate_sa and hasattr(client, "auth_service_account"):
                try:
                    uid = client.auth_service_account(candidate_sa)
                except Exception as sa_exc:
                    logger.warning("Could not authenticate with serviceAccountKey.json: %s", sa_exc)
                    uid = None

        # 2. Staff Account Session Refresh or Sign-In
        if uid is None and refresh_token:
            try:
                uid = client.refresh_session(refresh_token)
            except EmailVerificationRequiredError:
                raise
            except FirestoreSyncError:
                if not password:
                    raise
        if uid is None:
            if not email:
                raise FirestoreSyncError(
                    "Cloud Firestore synchronization requires serviceAccountKey.json or a verified staff email and password."
                )
            uid = client.sign_in(email, password)
        next_refresh_token = getattr(client, "refresh_token", None)
        if on_refresh_token and next_refresh_token:
            on_refresh_token(next_refresh_token)

        cursor_row = connection.execute(
            "SELECT value FROM settings WHERE key = 'firestore_books_cursor'"
        ).fetchone()
        last_full_row = connection.execute(
            "SELECT value FROM settings WHERE key = 'firestore_books_full_scan_at'"
        ).fetchone()
        cursor = cursor_row["value"] if cursor_row else None
        last_full_scan = _parse_time(last_full_row["value"]) if last_full_row else None
        full_scan = force_full_scan or not cursor or not last_full_scan or (
            _utc_now() - last_full_scan
        ).total_seconds() >= 86400

        local_books = _load_local_books(connection)
        sync_state = _load_sync_state(connection)
        if full_scan:
            remote_changes = client.list_books()
            query_read_time = None
            remote_count = len(remote_changes)
        else:
            remote_changes, query_read_time = client.get_books_since(cursor)
            count_row = connection.execute(
                "SELECT value FROM settings WHERE key = 'firestore_books_count'"
            ).fetchone()
            remote_count = int(count_row["value"]) if count_row else len(local_books)

            unresolved_ids = [
                book_id
                for book_id in local_books
                if book_id not in sync_state and book_id not in remote_changes
            ]
            if unresolved_ids:
                remote_changes.update(client.get_books_by_ids(unresolved_ids))

        to_push = []
        to_pull = {}
        unchanged = {}

        for book_id, local_book in local_books.items():
            state = sync_state.get(book_id)
            remote_document = remote_changes.get(book_id)
            local_hash = _book_hash(local_book)
            local_changed = state is None or local_hash != state["local_hash"]

            if remote_document is None and state is not None:
                if local_changed or full_scan:
                    to_push.append((local_book, None))
                continue

            if remote_document is None:
                if local_changed:
                    to_push.append((local_book, None))
                continue

            if state is None:
                local_wins = _local_is_newer(local_book, remote_document)
                if local_wins:
                    to_push.append((local_book, remote_document))
                else:
                    to_pull[book_id] = remote_document
                continue

            remote_time = _parse_time(remote_document["fields"].get("updatedAt"))
            previous_remote_time = _parse_time(state.get("remote_updated_at"))
            remote_changed = (
                remote_time is not None
                and (previous_remote_time is None or remote_time > previous_remote_time)
            )
            if local_changed and remote_changed:
                if _local_is_newer(local_book, remote_document):
                    to_push.append((local_book, remote_document))
                else:
                    to_pull[book_id] = remote_document
            elif local_changed:
                to_push.append((local_book, remote_document))
            elif remote_changed:
                to_pull[book_id] = remote_document
            else:
                unchanged[book_id] = (local_hash, remote_document)

        for book_id, remote_document in remote_changes.items():
            if book_id not in local_books:
                previous_state = sync_state.get(book_id)
                remote_time = _parse_time(remote_document["fields"].get("updatedAt"))
                previous_remote_time = _parse_time(
                    previous_state.get("remote_updated_at")
                ) if previous_state else None
                if previous_state is None or (
                    remote_time is not None
                    and (previous_remote_time is None or remote_time > previous_remote_time)
                ):
                    to_pull[book_id] = remote_document

        push_books = [book for book, _ in to_push]
        push_existing = {str(book["id"]): existing for book, existing in to_push}
        write_times = client.commit_book_writes(push_books, push_existing, uid) if push_books else {}

        for book, existing in to_push:
            book_id = str(book["id"])
            update_time = write_times.get(book_id)
            if not update_time:
                raise FirestoreSyncError(
                    f"Firestore did not confirm the write for book {book_id}."
                )

        for book_id, document in to_pull.items():
            if book_id in local_books:
                remote_time = _parse_time(document["fields"].get("updatedAt"))
                previous_time = _parse_time(sync_state.get(book_id, {}).get("remote_updated_at"))
                if (
                    sync_state.get(book_id)
                    and remote_time is not None
                    and previous_time is not None
                    and remote_time <= previous_time
                    and not full_scan
                ):
                    continue
            _apply_remote_book(connection, document)

        with connection:
            for book_id, local_book in local_books.items():
                if book_id in to_pull:
                    continue
                if book_id in write_times:
                    remote_document = {
                        "id": book_id,
                        "fields": {"updatedAt": write_times[book_id]},
                        "updateTime": write_times[book_id],
                    }
                    _store_sync_state(
                        connection,
                        book_id,
                        _book_hash(local_book),
                        remote_document,
                    )
                elif book_id in unchanged:
                    local_hash, remote_document = unchanged[book_id]
                    _store_sync_state(connection, book_id, local_hash, remote_document)
                elif book_id in remote_changes and book_id not in to_pull:
                    _store_sync_state(
                        connection,
                        book_id,
                        _book_hash(local_book),
                        remote_changes[book_id],
                    )

            for book_id, document in to_pull.items():
                row = connection.execute(
                    "SELECT id, isbn, title, author, publisher, category, shelf_location, "
                    "total_copies, available_copies FROM books WHERE id = ?",
                    (book_id,),
                ).fetchone()
                if row:
                    _store_sync_state(
                        connection,
                        book_id,
                        _book_hash(dict(row)),
                        document,
                    )

            all_books_after = _load_local_books(connection)

            if full_scan:
                remote_count = len(remote_changes) + sum(
                    1 for book, existing in to_push if existing is None
                )
                _set_setting(connection, "firestore_books_full_scan_at", _time_text(_utc_now()))
            else:
                remote_count += sum(1 for book, existing in to_push if existing is None)

            next_cursor = query_read_time
            if full_scan:
                remote_times = [
                    _parse_time(doc["fields"].get("updatedAt"))
                    for doc in remote_changes.values()
                ]
                valid_times = [item for item in remote_times if item is not None]
                high_water = max(valid_times) if valid_times else _utc_now()
                next_cursor = _time_text(
                    high_water - datetime.timedelta(seconds=_CURSOR_OVERLAP_SECONDS)
                )
            elif not next_cursor:
                next_cursor = cursor
            _set_setting(connection, "firestore_books_cursor", next_cursor or _time_text(_utc_now()))
            _set_setting(connection, "firestore_books_count", remote_count)

        u_row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
        c_row = connection.execute("SELECT COUNT(*) FROM circulation_logs").fetchone()
        u_count = u_row[0] if u_row else 2008
        c_count = c_row[0] if c_row else 7
        try:
            client.write_sync_metadata(
                remote_count,
                len(push_books) + len(to_pull),
                members_count=u_count,
                circulation_logs_count=c_count,
            )
        except TypeError:
            client.write_sync_metadata(
                remote_count,
                len(push_books) + len(to_pull),
            )
        return {
            "success": True,
            "book_count": len(all_books_after),
            "firestore_book_count": remote_count,
            "uploaded_books": len(push_books),
            "downloaded_books": len(to_pull),
        }
    except (sqlite3.Error, FirestoreSyncError):
        raise
    except Exception as exc:
        logger.exception("Unexpected Firestore desktop sync failure")
        raise FirestoreSyncError(f"Unexpected sync failure: {exc}") from exc
    finally:
        connection.close()

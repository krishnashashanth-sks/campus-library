import os
import shutil
import tempfile
import unittest

from database import LocalDatabase
from firestore_sync import (
    EmailVerificationRequiredError,
    FirestoreRestClient,
    FirestoreSyncError,
    sync_books,
)


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self.data


class FakeAuthSession:
    def __init__(self):
        self.posts = []
        self.responses = [
            {
                "idToken": "id-token",
                "refreshToken": "refresh-token",
                "localId": "staff-uid",
                "emailVerified": True,
            },
            {
                "users": [
                    {
                        "localId": "staff-uid",
                        "email": "librarian@example.com",
                        "emailVerified": True,
                    }
                ]
            },
            {
                "id_token": "new-id-token",
                "refresh_token": "rotated-token",
                "user_id": "staff-uid",
            },
            {
                "users": [
                    {
                        "localId": "staff-uid",
                        "email": "librarian@example.com",
                        "emailVerified": True,
                    }
                ]
            },
        ]

    def post(self, url, timeout, **payload):
        self.posts.append((url, payload))
        return FakeResponse(self.responses.pop(0))


class FakeFirestoreClient:
    def __init__(self, documents=None):
        self.documents = dict(documents or {})
        self.incremental_documents = {}
        self.metadata_updates = []
        self.write_count = 0
        self.uid = "verified-staff-uid"
        self.refresh_token = "test-refresh-token"

    def sign_in(self, email, password):
        self.assert_credentials(email, password)
        return self.uid

    @staticmethod
    def assert_credentials(email, password):
        if email != "librarian@example.com" or password != "test-password":
            raise AssertionError("Unexpected test credentials")

    def refresh_session(self, refresh_token):
        if refresh_token != "test-refresh-token":
            raise AssertionError("Unexpected test refresh token")
        self.refresh_token = "rotated-refresh-token"
        return self.uid

    def list_books(self):
        return dict(self.documents)

    def get_books_since(self, cursor):
        return dict(self.incremental_documents), "2026-04-04T00:00:00Z"

    def get_books_by_ids(self, book_ids):
        return {
            book_id: self.documents[book_id]
            for book_id in book_ids
            if book_id in self.documents
        }

    def commit_book_writes(self, books, existing_by_id, uid):
        if uid != self.uid:
            raise AssertionError("Sync did not use the verified Firebase user.")
        self.write_count += len(books)
        updated_times = {}
        for book in books:
            book_id = str(book["id"])
            updated_at = f"2026-04-04T00:00:{self.write_count % 60:02d}Z"
            self.documents[book_id] = {
                "id": book_id,
                "fields": {
                    "id": book_id,
                    "isbn": book.get("isbn") or "",
                    "title": book["title"],
                    "author": book.get("author") or "",
                    "publisher": book.get("publisher") or "",
                    "category": book.get("category") or "General",
                    "shelfLocation": book.get("shelf_location") or "Main Stack",
                    "totalCopies": book["total_copies"],
                    "availableCopies": book["available_copies"],
                    "createdAt": updated_at,
                    "updatedAt": updated_at,
                },
                "updateTime": updated_at,
                "name": f"projects/test/databases/test/documents/books/{book_id}",
            }
            updated_times[book_id] = updated_at
        return updated_times

    def write_sync_metadata(self, book_count, synced_books, *args, **kwargs):
        self.metadata_updates.append((book_count, synced_books))


def firestore_book(book_id, number):
    timestamp = "2024-01-02T00:00:00Z"
    return {
        "id": book_id,
        "fields": {
            "id": book_id,
            "isbn": "",
            "title": f"Book {number}",
            "author": "Author",
            "publisher": "Publisher",
            "category": "General",
            "shelfLocation": "Main Stack",
            "totalCopies": 1,
            "availableCopies": 1,
            "createdAt": "2020-01-01T00:00:00Z",
            "updatedAt": timestamp,
        },
        "updateTime": timestamp,
        "name": f"projects/test/databases/test/documents/books/{book_id}",
    }


class FirestoreBookSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_firestore_book_sync_")
        self.database_path = os.path.join(self.temp_dir, "library.db")
        self.database = LocalDatabase(self.database_path)

    def tearDown(self):
        self.database.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_batch_get_uses_relative_firestore_document_names(self):
        class BatchGetResponse(FakeResponse):
            def __init__(self):
                super().__init__([], 200)

        class BatchGetSession:
            def __init__(self):
                self.calls = []

            def request(self, method, url, **kwargs):
                self.calls.append((method, url, kwargs))
                return BatchGetResponse()

        session = BatchGetSession()
        client = FirestoreRestClient(session=session)

        self.assertEqual(client.get_books_by_ids(["BK-10001"]), {})
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(":batchGet"))
        document_name = kwargs["json"]["documents"][0]
        self.assertTrue(document_name.startswith("projects/"))
        self.assertIn("/documents/books/BK-10001", document_name)
        self.assertFalse(document_name.startswith("http"))

    def test_batch_get_rejects_invalid_document_ids_before_request(self):
        client = FirestoreRestClient(session=object())

        with self.assertRaisesRegex(
            FirestoreSyncError,
            "Cannot look up invalid Firestore book ID",
        ):
            client.get_books_by_ids(["invalid/book/id"])

    def test_create_write_uses_server_timestamps_and_precondition(self):
        client = FirestoreRestClient(session=object())
        book = {
            "id": "BK-10001",
            "title": "Local Book",
            "author": "Author",
            "publisher": "Publisher",
            "total_copies": 2,
            "available_copies": 1,
            "category": "General",
            "shelf_location": "Main Stack",
        }

        write = client._book_write(book, None, "staff-uid")

        transforms = {
            item["fieldPath"]: item["setToServerValue"]
            for item in write["updateTransforms"]
        }
        self.assertEqual(transforms["createdAt"], "REQUEST_TIME")
        self.assertEqual(transforms["updatedAt"], "REQUEST_TIME")
        self.assertEqual(write["currentDocument"], {"exists": False})

    def test_firebase_auth_uses_password_json_then_refresh_form(self):
        session = FakeAuthSession()
        client = FirestoreRestClient(session=session)

        self.assertEqual(client.sign_in("librarian@example.com", "password"), "staff-uid")
        self.assertEqual(client.refresh_session("refresh-token"), "staff-uid")

        sign_in_url, sign_in_payload = session.posts[0]
        self.assertIn("accounts:signInWithPassword", sign_in_url)
        self.assertEqual(
            sign_in_payload["json"],
            {
                "email": "librarian@example.com",
                "password": "password",
                "returnSecureToken": True,
            },
        )
        refresh_url, refresh_payload = session.posts[1]
        self.assertIn("accounts:lookup", refresh_url)
        self.assertEqual(
            refresh_payload["json"],
            {"idToken": "id-token"},
        )
        refresh_url, refresh_payload = session.posts[2]
        self.assertIn("securetoken.googleapis.com", refresh_url)
        self.assertEqual(
            refresh_payload["data"],
            {"grant_type": "refresh_token", "refresh_token": "refresh-token"},
        )
        self.assertNotIn("json", refresh_payload)

    def test_book_read_permission_error_reports_safe_request_diagnostics(self):
        response = FakeResponse(
            {"error": {"message": "Missing or insufficient permissions."}},
            status_code=403,
        )
        response.url = (
            "https://firestore.googleapis.com/v1/projects/project-id/"
            "databases/database-id/documents/books?pageSize=1000"
        )
        response.request = type(
            "Request",
            (),
            {"headers": {"Authorization": "Bearer private-token"}},
        )()
        response.history = []

        class FakeRequestSession:
            @staticmethod
            def request(*args, **kwargs):
                return response

        client = FirestoreRestClient(session=FakeRequestSession())
        client.id_token = "private-token"

        with self.assertRaisesRegex(
            FirestoreSyncError,
            "endpoint=firestore.googleapis.com/v1/projects/project-id/"
            "databases/database-id/documents/books; "
            "Firebase bearer header=present; redirects=0",
        ) as error:
            client._request_json(
                "GET",
                response.url,
                "Firestore book catalog read",
            )

        self.assertNotIn("private-token", str(error.exception))

    def test_unverified_firebase_account_has_actionable_auth_error(self):
        session = FakeAuthSession()
        session.responses[0]["emailVerified"] = False
        session.responses[1]["users"][0]["emailVerified"] = False
        session.responses.append({"email": "librarian@example.com"})
        client = FirestoreRestClient(session=session)

        with self.assertRaises(EmailVerificationRequiredError) as error:
            client.sign_in("librarian@example.com", "password")

        self.assertTrue(error.exception.email_sent)
        verification_url, verification_payload = session.posts[2]
        self.assertIn("accounts:sendOobCode", verification_url)
        self.assertEqual(
            verification_payload["json"],
            {"requestType": "VERIFY_EMAIL", "idToken": "id-token"},
        )

    def test_account_lookup_accepts_verification_completed_after_stale_signin_state(self):
        session = FakeAuthSession()
        session.responses[0]["emailVerified"] = False
        session.responses[1]["users"][0]["emailVerified"] = True
        client = FirestoreRestClient(session=session)

        self.assertEqual(
            client.sign_in("librarian@example.com", "password"),
            "staff-uid",
        )
        self.assertEqual(len(session.posts), 2)

    def test_recently_sent_verification_email_is_not_resent(self):
        session = FakeAuthSession()
        session.responses[0]["emailVerified"] = False
        session.responses[1]["users"][0]["emailVerified"] = False
        client = FirestoreRestClient(
            session=session,
            send_verification_email=False,
        )

        with self.assertRaises(EmailVerificationRequiredError) as error:
            client.sign_in("librarian@example.com", "password")

        self.assertTrue(error.exception.email_recently_sent)
        self.assertEqual(len(session.posts), 2)

    def test_missing_desktop_book_is_added_without_truncating_ids(self):
        local_rows = []
        remote_documents = {}
        for number in range(1, 5006):
            book_id = f"BK-{number:05d}"
            local_rows.append((
                book_id,
                f"Book {number}",
                "Author",
                "Publisher",
                1,
                1,
                "2020-01-01",
                "2020-01-01T00:00:00Z",
                "desktop",
            ))
            if number <= 5004:
                remote_documents[book_id] = firestore_book(book_id, number)

        self.database.conn.executemany("""
            INSERT INTO books (
                id, title, author, publisher, total_copies, available_copies,
                created_at, updated_at, last_modified_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, local_rows)
        self.database.conn.commit()
        client = FakeFirestoreClient(remote_documents)

        result = sync_books(
            self.database_path,
            "librarian@example.com",
            password="test-password",
            client=client,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["book_count"], 5005)
        self.assertEqual(result["firestore_book_count"], 5005)
        self.assertEqual(result["uploaded_books"], 1)
        self.assertEqual(client.write_count, 1)
        self.assertIn("BK-05005", client.documents)
        self.assertEqual(client.metadata_updates[-1][0], 5005)
        self.assertEqual(
            self.database.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            5005,
        )

        unchanged = sync_books(
            self.database_path,
            "librarian@example.com",
            password="test-password",
            client=client,
        )
        self.assertEqual(unchanged["uploaded_books"], 0)
        self.assertEqual(unchanged["downloaded_books"], 0)
        self.assertEqual(client.write_count, 1)

    def test_refresh_token_is_used_for_an_existing_sync_session(self):
        self.database.insert_book(
            "BK-REFRESH",
            "Refresh Test Book",
            "Author",
            "Publisher",
            1,
            1,
        )
        client = FakeFirestoreClient()
        saved_tokens = []

        result = sync_books(
            self.database_path,
            "librarian@example.com",
            refresh_token="test-refresh-token",
            client=client,
            on_refresh_token=saved_tokens.append,
        )

        self.assertTrue(result["success"])
        self.assertEqual(saved_tokens, ["rotated-refresh-token"])

    def test_service_account_sync_succeeds_without_password(self):
        self.database.insert_book(
            "BK-SA-1",
            "Service Account Test Book",
            "Author",
            "Publisher",
            1,
            1,
        )
        client = FakeFirestoreClient()
        client.is_service_account = True
        client.uid = "service_account:test@example.iam.gserviceaccount.com"

        result = sync_books(
            self.database_path,
            client=client,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["uploaded_books"], 1)


if __name__ == "__main__":
    unittest.main()

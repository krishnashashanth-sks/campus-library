import os
import sqlite3
import tempfile
import unittest

from database import LocalDatabase


class TestCaseInsensitiveIdentifiers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "library.db")

    def tearDown(self):
        if hasattr(self, "db"):
            self.db.conn.close()
        self.temp_dir.cleanup()

    def test_issue_and_return_accept_mixed_case_ids_in_legacy_schema(self):
        connection = sqlite3.connect(self.database_path)
        connection.executescript("""
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                phone_number TEXT UNIQUE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT,
                email TEXT,
                created_at TIMESTAMP
            );
            CREATE TABLE books (
                id TEXT PRIMARY KEY,
                isbn TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT,
                publisher TEXT,
                total_copies INTEGER NOT NULL DEFAULT 1,
                available_copies INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'General',
                shelf_location TEXT NOT NULL DEFAULT 'Main Stack',
                created_at TIMESTAMP
            );
            INSERT INTO users(id, full_name, role)
            VALUES ('24001-CS-097', 'Test Student', 'Student');
            INSERT INTO books(id, title, total_copies, available_copies)
            VALUES ('BK-001', 'Test Book', 1, 1);
        """)
        connection.close()

        self.db = LocalDatabase(self.database_path)

        issued, issue_message = self.db.issue_book("bk-001", "24001-cs-097")
        self.assertTrue(issued, issue_message)
        self.assertEqual(self.db.get_user_borrowing_status("24001-cs-097")["active_count"], 1)

        returned, _fine, return_message = self.db.return_book("Bk-001", "24001-cS-097")
        self.assertTrue(returned, return_message)
        self.assertEqual(self.db.get_user_borrowing_status("24001-cs-097")["active_count"], 0)

        log = self.db.conn.execute(
            "SELECT book_id, user_id, status FROM circulation_logs"
        ).fetchone()
        self.assertEqual(log, ("BK-001", "24001-CS-097", "RETURNED"))

    def test_new_ids_are_canonicalized_and_case_variants_rejected(self):
        self.db = LocalDatabase(self.database_path)

        user_ok, user_message = self.db.insert_user(
            "24001-cs-097", "Test Student", "9876543210", "Student", "CSE"
        )
        self.assertTrue(user_ok, user_message)
        duplicate_user, _ = self.db.insert_user(
            "24001-CS-097", "Duplicate Student", "9876543211", "Student", "CSE"
        )
        self.assertFalse(duplicate_user)

        book_ok, book_message = self.db.insert_book(
            "bk-001", "Test Book", "Author", "Publisher", 1, 1
        )
        self.assertTrue(book_ok, book_message)
        duplicate_book, _ = self.db.insert_book(
            "BK-001", "Duplicate Book", "Author", "Publisher", 1, 1
        )
        self.assertFalse(duplicate_book)

        self.assertEqual(
            self.db.conn.execute("SELECT id FROM users").fetchone()[0],
            "24001-CS-097",
        )
        self.assertEqual(
            self.db.conn.execute("SELECT id FROM books").fetchone()[0],
            "BK-001",
        )

import os
import csv
import sqlite3
import datetime
import logging
import hashlib
import hmac
import re
import secrets
from contextlib import contextmanager
from typing import Optional, Iterable, Sequence, Any

from utils import get_appdata_db_path


class LocalDatabase:
    """
    SQLite data-access layer for the Library Management System.

    Compatibility:
      - Keeps the existing public method names and return-value shapes.
      - Keeps `self.conn` available for legacy dialogs that query SQLite directly.
      - Uses parameterized SQL and explicit transactions for write operations.
    """

    def __init__(self, database_path=None):
        self.database_path = os.fspath(database_path or get_appdata_db_path())
        parent = os.path.dirname(os.path.abspath(self.database_path))
        os.makedirs(parent, exist_ok=True)

        self.conn = sqlite3.connect(
            self.database_path,
            timeout=15,
            check_same_thread=False,
            isolation_level="DEFERRED",
        )
        self.conn.row_factory = None
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 15000")
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.DatabaseError:
            logging.warning("WAL mode could not be enabled; continuing with SQLite defaults.")

        self.create_tables()

    @contextmanager
    def _transaction(self, immediate=False):
        """Commit the complete operation or roll it back on any exception."""
        try:
            if immediate:
                self.conn.execute("BEGIN IMMEDIATE")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    @staticmethod
    def _clean(value):
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _money(value, default=0.0):
        try:
            result = float(value)
            return round(result, 2) if result >= 0 else default
        except (TypeError, ValueError):
            return default

    def _parse_db_error(self, error: Exception, context: str = "") -> str:
        message = str(error).lower()

        if isinstance(error, sqlite3.IntegrityError):
            if "unique constraint" in message or "primary key" in message:
                if "users.id" in message:
                    return "A user with this ID / PIN already exists."
                if "users.phone_number" in message:
                    return "A user with this Phone Number already exists."
                if "books.id" in message or "books.isbn" in message:
                    return "A book with this ID or ISBN already exists."
                if "departments.name" in message:
                    return "A department or branch with this name already exists."
                return "This entry already exists in the system."
            if "foreign key" in message:
                return "The referenced User or Book record does not exist."
            if "check constraint" in message:
                return "Invalid data entered. Please check your inputs."

        if isinstance(error, sqlite3.OperationalError):
            if "locked" in message or "busy" in message:
                return "The database is currently busy. Please try again in a moment."
            if "no such table" in message:
                return "Database structure mismatch. Please restart the application."
            if "readonly" in message:
                return "The database is read-only. Check folder permissions."

        logging.exception("Database error [%s]: %s", context, error)
        return f"An unexpected error occurred while processing {context or 'the request'}."

    def create_tables(self):
        """Create tables, indexes, and seed data without deleting existing records."""
        with self._transaction():
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY COLLATE NOCASE,
                    phone_number TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT,
                    email TEXT,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY COLLATE NOCASE,
                    isbn TEXT UNIQUE,
                    title TEXT NOT NULL,
                    author TEXT,
                    publisher TEXT,
                    total_copies INTEGER NOT NULL DEFAULT 1 CHECK(total_copies >= 0),
                    available_copies INTEGER NOT NULL DEFAULT 1
                        CHECK(available_copies >= 0 AND available_copies <= total_copies),
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS circulation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    checkout_date TIMESTAMP,
                    due_date TIMESTAMP,
                    return_date TIMESTAMP,
                    fine_amount DECIMAL(10, 2) DEFAULT 0.00,
                    status TEXT DEFAULT 'ISSUED',
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS email_notifications (
                    loan_id INTEGER NOT NULL,
                    reminder_type TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (loan_id, reminder_type),
                    FOREIGN KEY(loan_id) REFERENCES circulation_logs(id)
                        ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                        ON DELETE SET NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE COLLATE NOCASE,
                    category TEXT DEFAULT 'STUDENT',
                    duration_years INTEGER DEFAULT 3 CHECK(duration_years > 0)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS loan_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT UNIQUE COLLATE NOCASE,
                    max_books_allowed INTEGER DEFAULT 3 CHECK(max_books_allowed >= 0),
                    default_loan_days INTEGER DEFAULT 14 CHECK(default_loan_days > 0),
                    fine_per_day DECIMAL(10, 2) DEFAULT 2.00 CHECK(fine_per_day >= 0)
                )
            """)

            # Lightweight additive migrations for databases created by earlier versions.
            self._ensure_column("books", "isbn", "TEXT")
            self._ensure_column("circulation_logs", "status", "TEXT DEFAULT 'ISSUED'")
            self._ensure_column("circulation_logs", "fine_amount", "DECIMAL(10, 2) DEFAULT 0.00")
            self._ensure_column("users", "email", "TEXT")

            cur.executescript("""
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_users_department ON users(department);
                CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
                CREATE INDEX IF NOT EXISTS idx_logs_user_status ON circulation_logs(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_logs_book_status ON circulation_logs(book_id, status);
                CREATE INDEX IF NOT EXISTS idx_logs_due_status ON circulation_logs(due_date, status);
                CREATE INDEX IF NOT EXISTS idx_logs_checkout ON circulation_logs(checkout_date);
            """)

            if cur.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
                # Retained for compatibility with the existing login dialog.
                # Change this default immediately after first launch.
                cur.executemany(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    [("admin_password", "admin123"), ("daily_fine", "10.0"), ("default_days", "14")],
                )

            if cur.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
                departments = [
                    ("CSE (Computer Science & Engineering)", "STUDENT", 3),
                    ("ECE (Electronics & Communication)", "STUDENT", 3),
                    ("EEE (Electrical & Electronics)", "STUDENT", 3),
                    ("Advanced Manufacturing Technology (AMT)", "STUDENT", 3),
                    ("Electrical Engineering and Electric Vehicle Technology", "STUDENT", 3),
                    ("Interior Design (ID)", "STUDENT", 3),
                    ("Civil Engineering", "STUDENT", 3),
                    ("Mechanical Engineering", "STUDENT", 3),
                    ("Automobile Engineering", "STUDENT", 3),
                    ("Pharmacy", "STUDENT", 2),
                    ("Sciences & Humanities Department", "FACULTY", 3),
                    ("Computer Engineering Department", "FACULTY", 3),
                    ("Electronics & Communication Department", "FACULTY", 3),
                    ("Electrical & EV Department", "FACULTY", 3),
                    ("Mechanical & AMT Department", "FACULTY", 3),
                    ("Civil & Interior Design Department", "FACULTY", 3),
                    ("Automobile Engineering Department", "FACULTY", 3),
                    ("Pharmacy Department", "FACULTY", 3),
                    ("General Administration", "FACULTY", 3),
                ]
                cur.executemany(
                    "INSERT OR IGNORE INTO departments(name, category, duration_years) VALUES (?, ?, ?)",
                    departments,
                )

            if cur.execute("SELECT COUNT(*) FROM loan_policies").fetchone()[0] == 0:
                cur.executemany("""
                    INSERT OR IGNORE INTO loan_policies
                    (role, max_books_allowed, default_loan_days, fine_per_day)
                    VALUES (?, ?, ?, ?)
                """, [
                    ("Student", 3, 14, 2.00),
                    ("Faculty", 8, 30, 1.00),
                    ("Guest Lecturer", 5, 21, 2.00),
                    ("Admin", 15, 60, 0.00),
                    ("Librarian", 10, 30, 0.00),
                ])

    def _ensure_column(self, table, column, declaration):
        existing = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    # SETTINGS
    def get_setting(self, key, default=None):
        try:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default
        except sqlite3.Error as exc:
            logging.error("Could not read setting %s: %s", key, exc)
            return default

    def set_setting(self, key, value):
        try:
            with self._transaction():
                self.conn.execute("""
                    INSERT INTO settings(key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """, (str(key), str(value)))
            return True
        except Exception as exc:
            logging.error("Could not save setting %s: %s", key, exc)
            return False

    @staticmethod
    def _hash_admin_secret(secret):
        iterations = 310000
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode("utf-8"),
            salt,
            iterations,
        )
        return "pbkdf2_sha256${}${}${}".format(
            iterations,
            salt.hex(),
            digest.hex(),
        )

    @staticmethod
    def _verify_admin_secret(secret, encoded_hash):
        try:
            algorithm, iterations, salt_hex, digest_hex = (
                encoded_hash.split("$", 3)
            )
            if algorithm != "pbkdf2_sha256":
                return False

            iterations = int(iterations)
            if not 100000 <= iterations <= 1000000:
                return False

            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                secret.encode("utf-8"),
                salt,
                iterations,
            )
            return hmac.compare_digest(actual, expected)
        except (AttributeError, TypeError, ValueError):
            return False

    @staticmethod
    def _normalize_recovery_code(code):
        normalized = re.sub(r"[\s-]", "", str(code or "")).upper()
        return normalized if re.fullmatch(r"[0-9A-F]{32}", normalized) else ""

    def verify_admin_password(self, password):
        password = str(password or "")
        password_hash = self.get_setting("admin_password_hash")

        if password_hash:
            return self._verify_admin_secret(password, password_hash)

        legacy_password = self.get_setting("admin_password", "admin123")
        if not hmac.compare_digest(password, str(legacy_password)):
            return False

        if not self.set_admin_password(password):
            raise RuntimeError("Unable to securely migrate the administrator password.")
        return True

    def set_admin_password(self, password):
        password = str(password or "")
        if len(password) < 8:
            raise ValueError("The administrator password must contain at least 8 characters.")

        password_hash = self._hash_admin_secret(password)
        with self._transaction(immediate=True):
            self.conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES ('admin_password_hash', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (password_hash,),
            )
            self.conn.execute(
                "DELETE FROM settings WHERE key = 'admin_password'"
            )
        return True

    def has_admin_recovery_code(self):
        return bool(self.get_setting("admin_recovery_code_hash"))

    def set_admin_recovery_code(self, code):
        normalized = self._normalize_recovery_code(code)
        if not normalized:
            raise ValueError("The recovery code is invalid.")

        code_hash = self._hash_admin_secret(normalized)
        with self._transaction(immediate=True):
            self.conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES ('admin_recovery_code_hash', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (code_hash,),
            )
        return True

    def _verify_admin_recovery_code_hash(self, code, encoded_hash):
        normalized = self._normalize_recovery_code(code)
        return bool(
            normalized
            and encoded_hash
            and self._verify_admin_secret(normalized, encoded_hash)
        )

    def verify_admin_recovery_code(self, code):
        return self._verify_admin_recovery_code_hash(
            code,
            self.get_setting("admin_recovery_code_hash"),
        )

    def reset_admin_password_with_recovery(
        self,
        recovery_code,
        new_password,
        new_recovery_code,
    ):
        new_password = str(new_password or "")
        normalized_recovery = self._normalize_recovery_code(
            new_recovery_code
        )
        if len(new_password) < 8:
            raise ValueError("The administrator password must contain at least 8 characters.")
        if not normalized_recovery:
            raise ValueError("The new recovery code is invalid.")

        new_password_hash = self._hash_admin_secret(new_password)
        new_recovery_hash = self._hash_admin_secret(normalized_recovery)

        with self._transaction(immediate=True):
            stored_hash = self.conn.execute(
                """
                SELECT value FROM settings
                WHERE key = 'admin_recovery_code_hash'
                """
            ).fetchone()
            if not stored_hash or not self._verify_admin_recovery_code_hash(
                recovery_code,
                stored_hash[0],
            ):
                return False

            self.conn.executemany(
                """
                INSERT INTO settings(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [
                    ("admin_password_hash", new_password_hash),
                    ("admin_recovery_code_hash", new_recovery_hash),
                ],
            )
            self.conn.execute(
                "DELETE FROM settings WHERE key = 'admin_password'"
            )
        return True

    # DEPARTMENTS
    def get_departments(self, category=None):
        try:
            if category:
                category = self._clean(category).upper()
                if category == "STUDENT":
                    role_filter = "LOWER(role) LIKE '%student%'"
                elif category == "FACULTY":
                    role_filter = (
                        "LOWER(role) LIKE '%faculty%' "
                        "OR LOWER(role) LIKE '%staff%' "
                        "OR LOWER(role) LIKE '%guest%'"
                    )
                else:
                    return []

                rows = self.conn.execute(
                    f"""
                    SELECT name FROM departments WHERE category = ?
                    UNION
                    SELECT department FROM users
                    WHERE department IS NOT NULL
                        AND TRIM(department) != ''
                        AND ({role_filter})
                    ORDER BY 1 COLLATE NOCASE
                    """,
                    (category,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT name FROM departments
                    UNION
                    SELECT department FROM users
                    WHERE department IS NOT NULL AND TRIM(department) != ''
                    ORDER BY 1 COLLATE NOCASE
                    """
                ).fetchall()
            values = {
                self._clean(row[0])
                for row in rows
                if row[0] and self._clean(row[0])
            }
            return sorted(values, key=str.casefold)
        except sqlite3.Error:
            logging.exception("Could not fetch departments")
            return []

    def get_course_duration(self, department_name: str) -> int:
        name = self._clean(department_name)
        if not name or name.upper() in ("N/A", "GENERAL ADMINISTRATION"):
            return 3
        try:
            row = self.conn.execute(
                "SELECT duration_years FROM departments WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if row and row[0]:
                return int(row[0])
        except (sqlite3.Error, TypeError, ValueError):
            logging.exception("Could not read course duration")
        lower = name.lower()
        if "pharm" in lower:
            return 2
        if "arch" in lower:
            return 5
        if "b.tech" in lower or "btech" in lower:
            return 4
        return 3

    def add_department(self, name, category="STUDENT", duration_years=3):
        clean_name = self._clean(name)
        category = self._clean(category).upper()
        try:
            duration = int(duration_years)
            if not clean_name or category not in ("STUDENT", "FACULTY") or duration < 1:
                return False, "Enter a valid department name, category, and course duration."
            with self._transaction():
                self.conn.execute("""
                    INSERT INTO departments(name, category, duration_years) VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        category = excluded.category,
                        duration_years = excluded.duration_years
                """, (clean_name, category, duration))
            return True, "Department and duration saved successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "adding department")

    def update_department(self, dept_id, name, category, duration_years):
        clean_name = self._clean(name)
        category = self._clean(category).upper()
        try:
            duration = int(duration_years)
            if not clean_name or category not in ("STUDENT", "FACULTY") or duration < 1:
                return False, "Enter valid department details."
            with self._transaction():
                row = self.conn.execute(
                    "SELECT name FROM departments WHERE id = ?", (dept_id,)
                ).fetchone()
                if not row:
                    return False, "Department not found."
                old_name = row[0]
                self.conn.execute("""
                    UPDATE departments SET name = ?, category = ?, duration_years = ?
                    WHERE id = ?
                """, (clean_name, category, duration, dept_id))
                if old_name.lower() != clean_name.lower():
                    self.conn.execute(
                        "UPDATE users SET department = ? WHERE department = ? COLLATE NOCASE",
                        (clean_name, old_name),
                    )
            return True, "Department updated successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "department update")

    def delete_department(self, name):
        try:
            with self._transaction():
                cur = self.conn.execute(
                    "DELETE FROM departments WHERE name = ? COLLATE NOCASE", (self._clean(name),)
                )
                if cur.rowcount == 0:
                    return False, "Department not found."
            return True, "Department removed successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "deleting department")

    # LOAN POLICIES
    def get_loan_policy(self, role):
        try:
            row = self.conn.execute("""
                SELECT max_books_allowed, default_loan_days, fine_per_day
                FROM loan_policies WHERE role = ? COLLATE NOCASE
            """, (self._clean(role),)).fetchone()
            if row:
                return {
                    "max_books": int(row[0]),
                    "default_days": int(row[1]),
                    "fine_rate": float(row[2]),
                }
        except (sqlite3.Error, TypeError, ValueError):
            logging.exception("Could not read loan policy")
        try:
            days = max(1, int(self.get_setting("default_days", 14)))
        except (ValueError, TypeError):
            days = 14
        fine = self._money(self.get_setting("daily_fine", 2.0), 2.0)
        return {"max_books": 3, "default_days": days, "fine_rate": fine}

    def get_all_loan_policies(self):
        try:
            rows = self.conn.execute("""
                SELECT role, max_books_allowed, default_loan_days, fine_per_day
                FROM loan_policies ORDER BY id
            """).fetchall()
            return True, rows
        except sqlite3.Error:
            logging.exception("Could not fetch loan policies")
            return False, []

    def update_loan_policy(self, role, max_books, default_days, fine_per_day):
        try:
            role = self._clean(role)
            max_books, default_days = int(max_books), int(default_days)
            fine = float(fine_per_day)
            if not role or max_books < 0 or default_days < 1 or fine < 0:
                return False, "Enter a valid role, non-negative book limit/fine, and loan duration above zero."
            with self._transaction():
                self.conn.execute("""
                    INSERT INTO loan_policies(role, max_books_allowed, default_loan_days, fine_per_day)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role) DO UPDATE SET
                        max_books_allowed = excluded.max_books_allowed,
                        default_loan_days = excluded.default_loan_days,
                        fine_per_day = excluded.fine_per_day
                """, (role, max_books, default_days, fine))
            return True, f"Loan policy for '{role}' updated."
        except Exception as exc:
            return False, self._parse_db_error(exc, "loan policy update")

    # USERS
    def insert_user(
        self,
        user_id,
        full_name,
        phone_number,
        role,
        department,
        email="",
    ):
        uid, name = self._clean(user_id).upper(), self._clean(full_name)
        phone = self._clean(phone_number) or None
        role, dept = self._clean(role), self._clean(department)
        email = self._clean(email).casefold() or None
        if not uid or not name or not role:
            return False, "User ID, full name, and role are required."
        created = datetime.date.today().isoformat()
        try:
            with self._transaction():
                self.conn.execute("""
                    INSERT INTO users(
                        id, full_name, phone_number, role, department,
                        email, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (uid, name, phone, role, dept, email, created))
            return True, "User created successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "user registration")

    def get_users(self):
        try:
            rows = self.conn.execute("""
                SELECT id, full_name, COALESCE(phone_number, ''), role,
                    department, created_at, COALESCE(email, '')
                FROM users ORDER BY full_name COLLATE NOCASE
            """).fetchall()
            return True, rows
        except sqlite3.Error:
            logging.exception("Could not fetch users")
            return False, []

    def get_user_details(self, user_id):
        try:
            row = self.conn.execute("""
                SELECT id, full_name, COALESCE(phone_number, ''), role,
                    department, created_at, COALESCE(email, '')
                FROM users WHERE id = ?
            """, (self._clean(user_id),)).fetchone()
            return True, row
        except sqlite3.Error:
            logging.exception("Could not fetch user details")
            return False, None

    def edit_user(
        self,
        user_id,
        name,
        phone_number,
        role,
        dept,
        email="",
    ):
        name, role = self._clean(name), self._clean(role)
        phone = self._clean(phone_number) or None
        email = self._clean(email).casefold() or None
        if not name or not role:
            return False, "Full name and role are required."
        try:
            with self._transaction():
                cur = self.conn.execute("""
                    UPDATE users SET full_name = ?, phone_number = ?,
                        role = ?, department = ?, email = ?
                    WHERE id = ?
                """, (
                    name,
                    phone,
                    role,
                    self._clean(dept),
                    email,
                    self._clean(user_id),
                ))
                if cur.rowcount == 0:
                    return False, "User not found."
            return True, "User details updated successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "user update")

    def delete_user(self, user_id):
        uid = self._clean(user_id)
        try:
            with self._transaction(immediate=True):
                active = self.conn.execute("""
                    SELECT 1 FROM circulation_logs WHERE user_id = ? AND status = 'ISSUED' LIMIT 1
                """, (uid,)).fetchone()
                if active:
                    return False, f"Cannot delete User ID ({uid}): They currently have active checked-out books."
                cur = self.conn.execute("DELETE FROM users WHERE id = ?", (uid,))
                if cur.rowcount == 0:
                    return False, "User not found."
            return True, "User has been removed successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "user deletion")

    # BOOKS
    def insert_book(self, book_id, title, author, publisher, total, available):
        bid, title = self._clean(book_id), self._clean(title)
        author, publisher = self._clean(author), self._clean(publisher)
        try:
            total, available = int(total), int(available)
            if not bid or not title or total < 1 or available < 0 or available > total:
                return False, "Enter a valid Book ID, title, total copies, and available copies."
            with self._transaction():
                self.conn.execute("""
                    INSERT INTO books(id, title, author, publisher, total_copies, available_copies, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (bid, title, author, publisher, total, available, datetime.date.today().isoformat()))
            return True, "Book added successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "book entry")

    def get_books(self):
        try:
            rows = self.conn.execute("""
                SELECT id, title, author, publisher, total_copies, available_copies, created_at
                FROM books ORDER BY title COLLATE NOCASE
            """).fetchall()
            return True, rows
        except sqlite3.Error:
            logging.exception("Could not fetch books")
            return False, []

    def get_book_details(self, book_id):
        try:
            row = self.conn.execute("""
                SELECT id, title, author, publisher, total_copies, available_copies, created_at
                FROM books WHERE id = ?
            """, (self._clean(book_id),)).fetchone()
            return True, row
        except sqlite3.Error:
            logging.exception("Could not fetch book details")
            return False, None

    def edit_book(self, book_id, title, author, publisher, total, available):
        try:
            total, available = int(total), int(available)
            if not self._clean(title) or total < 0 or available < 0 or available > total:
                return False, "Invalid book details or copy counts."
            with self._transaction(immediate=True):
                row = self.conn.execute("""
                    SELECT total_copies, available_copies FROM books WHERE id = ?
                """, (self._clean(book_id),)).fetchone()
                if not row:
                    return False, "Book not found."
                currently_issued = int(row[0]) - int(row[1])
                if total < currently_issued:
                    return False, f"Total copies cannot be less than currently issued copies ({currently_issued})."
                # Preserve actual checked-out count; do not trust a stale UI availability value.
                available = total - currently_issued
                self.conn.execute("""
                    UPDATE books SET title = ?, author = ?, publisher = ?,
                        total_copies = ?, available_copies = ?
                    WHERE id = ?
                """, (self._clean(title), self._clean(author), self._clean(publisher),
                      total, available, self._clean(book_id)))
            return True, "Book details updated successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "book update")

    def delete_book(self, book_id):
        bid = self._clean(book_id)
        try:
            with self._transaction(immediate=True):
                active = self.conn.execute("""
                    SELECT 1 FROM circulation_logs WHERE book_id = ? AND status = 'ISSUED' LIMIT 1
                """, (bid,)).fetchone()
                if active:
                    return False, f"Cannot delete Book ID ({bid}): Copies of this book are currently issued."
                cur = self.conn.execute("DELETE FROM books WHERE id = ?", (bid,))
                if cur.rowcount == 0:
                    return False, "Book not found."
            return True, f"Successfully deleted book ({bid})."
        except Exception as exc:
            return False, self._parse_db_error(exc, "book deletion")

    # CIRCULATION
    def issue_book(self, book_id, user_id, days_allowed=None):
        bid, uid = self._clean(book_id), self._clean(user_id)
        try:
            with self._transaction(immediate=True):
                user = self.conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
                if not user:
                    return False, f"User ID '{uid}' is not registered in the system."
                role = user[0]
                policy = self.get_loan_policy(role)
                try:
                    days = int(days_allowed) if days_allowed is not None else int(policy["default_days"])
                except (ValueError, TypeError):
                    days = int(policy["default_days"])
                if days < 1:
                    return False, "Loan duration must be at least one day."

                book = self.conn.execute(
                    "SELECT available_copies FROM books WHERE id = ?", (bid,)
                ).fetchone()
                if not book:
                    return False, f"Book ID '{bid}' is not registered in the system."
                if int(book[0]) <= 0:
                    return False, f"Book ID '{bid}' has no available copies to issue."

                duplicate = self.conn.execute("""
                    SELECT 1 FROM circulation_logs
                    WHERE book_id = ? AND user_id = ? AND status = 'ISSUED' LIMIT 1
                """, (bid, uid)).fetchone()
                if duplicate:
                    return False, f"User '{uid}' already has Book ID '{bid}' issued."

                active_count = self.conn.execute("""
                    SELECT COUNT(*) FROM circulation_logs WHERE user_id = ? AND status = 'ISSUED'
                """, (uid,)).fetchone()[0]
                if int(active_count) >= int(policy["max_books"]):
                    return False, (
                        f"Issue denied: User has reached the maximum allowed limit of "
                        f"{policy['max_books']} issued books for role '{role}'."
                    )

                now = datetime.datetime.now().replace(second=0, microsecond=0)
                due = now + datetime.timedelta(days=days)
                checkout_text = now.strftime("%Y-%m-%d %H:%M")
                due_text = due.strftime("%Y-%m-%d %H:%M")
                self.conn.execute("""
                    INSERT INTO circulation_logs(book_id, user_id, checkout_date, due_date, status)
                    VALUES (?, ?, ?, ?, 'ISSUED')
                """, (bid, uid, checkout_text, due_text))
                self.conn.execute("""
                    UPDATE books SET available_copies = available_copies - 1
                    WHERE id = ? AND available_copies > 0
                """, (bid,))
            return True, f"Book issued successfully! Due Date: {due_text}"
        except Exception as exc:
            return False, self._parse_db_error(exc, "book issue")

    def return_book(self, book_id, user_id):
        bid, uid = self._clean(book_id), self._clean(user_id)
        try:
            with self._transaction(immediate=True):
                book = self.conn.execute("""
                    SELECT total_copies, available_copies FROM books WHERE id = ?
                """, (bid,)).fetchone()
                if not book:
                    return False, 0.0, f"Book ID '{bid}' was not found in the library database."
                user = self.conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
                if not user:
                    return False, 0.0, f"User ID '{uid}' was not found in the library database."

                policy = self.get_loan_policy(user[0])
                record = self.conn.execute("""
                    SELECT id, due_date FROM circulation_logs
                    WHERE book_id = ? AND user_id = ? AND status = 'ISSUED'
                    ORDER BY id DESC LIMIT 1
                """, (bid, uid)).fetchone()
                if not record:
                    return False, 0.0, (
                        f"No active issue record found matching Book ID '{bid}' and User ID '{uid}'."
                    )

                log_id, due_text = record
                now = datetime.datetime.now().replace(second=0, microsecond=0)
                fine_rate = self._money(policy.get("fine_rate", 2.0), 2.0)
                fine = 0.0
                if due_text:
                    try:
                        due_dt = datetime.datetime.strptime(str(due_text), "%Y-%m-%d %H:%M")
                    except ValueError:
                        try:
                            due_dt = datetime.datetime.strptime(str(due_text)[:10], "%Y-%m-%d")
                        except ValueError:
                            due_dt = None
                    if due_dt and now > due_dt:
                        # Fine is charged per overdue calendar day, matching the app's date-based policy.
                        overdue_days = (now.date() - due_dt.date()).days
                        fine = round(max(0, overdue_days) * fine_rate, 2)

                returned_text = now.strftime("%Y-%m-%d %H:%M")
                self.conn.execute("""
                    UPDATE circulation_logs
                    SET return_date = ?, fine_amount = ?, status = 'RETURNED'
                    WHERE id = ? AND status = 'ISSUED'
                """, (returned_text, fine, log_id))
                self.conn.execute("""
                    UPDATE books SET available_copies = MIN(total_copies, available_copies + 1)
                    WHERE id = ?
                """, (bid,))
            return True, fine, "Book returned successfully."
        except Exception as exc:
            return False, 0.0, self._parse_db_error(exc, "book return")

    def get_logs(self):
        try:
            rows = self.conn.execute("""
                SELECT id, book_id, user_id, checkout_date, due_date, return_date, fine_amount, status
                FROM circulation_logs ORDER BY id DESC
            """).fetchall()
            return True, rows
        except sqlite3.Error:
            logging.exception("Could not fetch circulation logs")
            return False, []

    def clear_all_logs(self):
        try:
            with self._transaction(immediate=True):
                active = self.conn.execute(
                    "SELECT COUNT(*) FROM circulation_logs WHERE status = 'ISSUED'"
                ).fetchone()[0]
                if active:
                    return False, "Cannot clear circulation history while issued books exist."
                self.conn.execute("DELETE FROM circulation_logs")
                self.conn.execute("DELETE FROM sqlite_sequence WHERE name = 'circulation_logs'")
                self.conn.execute("UPDATE books SET available_copies = total_copies")
            return True, "Circulation logs cleared successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "clearing logs")

    def get_user_books_status(self, user_id):
        try:
            return self.conn.execute("""
                SELECT b.id, b.title, b.author, b.publisher, c.status,
                       c.checkout_date, c.due_date, c.return_date, c.fine_amount
                FROM circulation_logs c JOIN books b ON c.book_id = b.id
                WHERE c.user_id = ? ORDER BY c.id DESC
            """, (self._clean(user_id),)).fetchall()
        except sqlite3.Error:
            logging.exception("Error getting user books status")
            return []

    # DASHBOARD / REPORTS
    def get_dashboard_details(self):
        today = datetime.date.today().isoformat()
        try:
            row = self.conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users),
                    (SELECT COUNT(*) FROM books),
                    (SELECT COALESCE(SUM(total_copies), 0) FROM books),
                    (SELECT COALESCE(SUM(available_copies), 0) FROM books),
                    (SELECT COUNT(*) FROM circulation_logs WHERE status = 'ISSUED'),
                    (SELECT COUNT(*) FROM circulation_logs
                        WHERE status = 'ISSUED' AND substr(checkout_date, 1, 10) = ?),
                    (SELECT COUNT(*) FROM circulation_logs
                        WHERE status = 'ISSUED' AND substr(due_date, 1, 10) < ?),
                    (SELECT COUNT(*) FROM circulation_logs
                        WHERE status = 'ISSUED' AND substr(due_date, 1, 10) = ?),
                    (SELECT COALESCE(SUM(fine_amount), 0) FROM circulation_logs
                        WHERE fine_amount > 0 AND status != 'PAID')
            """, (today, today, today)).fetchone()
            return (*row[:8], float(row[8] or 0.0))
        except sqlite3.Error:
            logging.exception("Error fetching dashboard details")
            return (0, 0, 0, 0, 0, 0, 0, 0, 0.0)

    def get_recent_activity_logs(self, limit=10):
        try:
            limit = max(1, min(int(limit), 500))
            rows = self.conn.execute("""
                SELECT COALESCE(c.status, 'Activity'),
                    COALESCE(b.title, 'Unknown Book') || ' [ID: ' ||
                        COALESCE(c.book_id, 'N/A') || ']',
                    COALESCE(u.full_name, 'Unknown User'),
                    CASE WHEN UPPER(c.status) = 'RETURNED'
                        THEN COALESCE(c.return_date, c.checkout_date, 'N/A')
                        ELSE COALESCE(c.checkout_date, 'N/A') END
                FROM circulation_logs c
                LEFT JOIN books b ON c.book_id = b.id
                LEFT JOIN users u ON c.user_id = u.id
                ORDER BY c.id DESC LIMIT ?
            """, (limit,)).fetchall()
            return True, rows
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Error fetching recent logs")
            return False, []

    def get_book_circulation_status(self, book_id: str):
        try:
            return self.conn.execute("""
                SELECT user_id, due_date FROM circulation_logs
                WHERE book_id = ? AND status = 'ISSUED' ORDER BY id DESC LIMIT 1
            """, (self._clean(book_id),)).fetchone()
        except sqlite3.Error:
            logging.exception("Could not get book circulation status")
            return None

    def get_due_email_reminders(self, today=None):
        today = today or datetime.date.today().isoformat()
        try:
            return self.conn.execute("""
                SELECT c.id, u.email, u.full_name, b.title,
                    c.due_date,
                    CASE
                        WHEN substr(c.due_date, 1, 10) = ?
                        THEN 'due_today'
                        ELSE 'overdue'
                    END
                FROM circulation_logs c
                JOIN users u ON u.id = c.user_id
                JOIN books b ON b.id = c.book_id
                WHERE c.status = 'ISSUED'
                    AND COALESCE(u.email, '') != ''
                    AND substr(c.due_date, 1, 10) <= ?
                    AND NOT EXISTS (
                        SELECT 1 FROM email_notifications n
                        WHERE n.loan_id = c.id
                            AND n.reminder_type = CASE
                                WHEN substr(c.due_date, 1, 10) = ?
                                THEN 'due_today'
                                ELSE 'overdue'
                            END
                    )
                ORDER BY c.due_date, c.id
            """, (today, today, today)).fetchall()
        except sqlite3.Error:
            logging.exception("Could not fetch due email reminders")
            raise

    def mark_due_email_reminder_sent(
        self,
        loan_id,
        reminder_type,
        sent_at=None,
    ):
        if reminder_type not in ("due_today", "overdue"):
            raise ValueError("Invalid due-date reminder type.")

        sent_at = sent_at or datetime.datetime.now().isoformat(timespec="seconds")
        with self._transaction(immediate=True):
            self.conn.execute("""
                INSERT OR IGNORE INTO email_notifications(
                    loan_id, reminder_type, sent_at
                )
                VALUES (?, ?, ?)
            """, (int(loan_id), reminder_type, sent_at))
        return True

    def create_complaint(self, user_id, subject, body):
        uid = self._clean(user_id) or None
        subject = self._clean(subject)
        body = self._clean(body)
        if not subject or not body:
            return False, "Complaint subject and details are required."

        created_at = datetime.datetime.now().isoformat(timespec="seconds")
        try:
            with self._transaction():
                cursor = self.conn.execute("""
                    INSERT INTO complaints(
                        user_id, subject, body, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'OPEN', ?, ?)
                """, (uid, subject, body, created_at, created_at))
                complaint_id = cursor.lastrowid
                row = self.conn.execute("""
                    SELECT c.id, c.user_id, COALESCE(u.full_name, ''),
                        COALESCE(u.email, ''), c.subject, c.body,
                        c.created_at
                    FROM complaints c
                    LEFT JOIN users u ON u.id = c.user_id
                    WHERE c.id = ?
                """, (complaint_id,)).fetchone()
            return True, row
        except Exception as exc:
            logging.exception("Could not create library complaint")
            return False, str(exc)

    def get_complaints(self, status=None):
        try:
            query = """
                SELECT c.id, c.user_id, COALESCE(u.full_name, ''),
                    COALESCE(u.email, ''), c.subject, c.body, c.status,
                    c.created_at, c.updated_at
                FROM complaints c
                LEFT JOIN users u ON u.id = c.user_id
            """
            parameters = ()
            if status and status != "ALL":
                query += " WHERE c.status = ?"
                parameters = (str(status).upper(),)
            query += " ORDER BY c.created_at DESC, c.id DESC"
            return self.conn.execute(query, parameters).fetchall()
        except sqlite3.Error:
            logging.exception("Could not fetch library complaints")
            raise

    def update_complaint_status(self, complaint_id, status):
        normalized_status = self._clean(status).upper()
        if normalized_status not in ("OPEN", "IN_PROGRESS", "RESOLVED"):
            return False, "Invalid complaint status."

        try:
            with self._transaction():
                cursor = self.conn.execute("""
                    UPDATE complaints
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    normalized_status,
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    int(complaint_id),
                ))
                if cursor.rowcount == 0:
                    return False, "Complaint not found."
            return True, "Complaint status updated."
        except Exception as exc:
            logging.exception("Could not update complaint status")
            return False, str(exc)

    def get_active_loans_report(self):
        return self._report_query("""
            SELECT book_id, user_id, checkout_date, due_date
            FROM circulation_logs WHERE status = 'ISSUED' ORDER BY due_date
        """)

    def get_issued_today_report(self, today_str: str):
        return self._report_query("""
            SELECT book_id, user_id, checkout_date, due_date
            FROM circulation_logs
            WHERE status = 'ISSUED' AND substr(checkout_date, 1, 10) = ?
            ORDER BY checkout_date DESC
        """, (today_str,))

    def get_overdue_books_report(self, today_str: str):
        return self._report_query("""
            SELECT book_id, user_id, checkout_date, due_date
            FROM circulation_logs
            WHERE status = 'ISSUED' AND substr(due_date, 1, 10) < ?
            ORDER BY due_date
        """, (today_str,))

    def get_due_today_report(self, today_str: str):
        return self._report_query("""
            SELECT book_id, user_id, checkout_date, due_date
            FROM circulation_logs
            WHERE status = 'ISSUED' AND substr(due_date, 1, 10) = ?
            ORDER BY due_date
        """, (today_str,))

    def get_pending_fines_report(self):
        return self._report_query("""
            SELECT user_id, book_id, fine_amount, return_date
            FROM circulation_logs WHERE fine_amount > 0 AND status != 'PAID'
            ORDER BY fine_amount DESC
        """)

    def _report_query(self, query, params=()):
        try:
            return True, self.conn.execute(query, params).fetchall()
        except sqlite3.Error:
            logging.exception("Could not generate report")
            return False, []

    def get_all_user_departments(self):
        try:
            rows = self.conn.execute("""
                SELECT department FROM users
                WHERE department IS NOT NULL AND TRIM(department) != ''
                UNION
                SELECT name FROM departments
            """).fetchall()
            excluded = {"N/A", "GENERAL ADMINISTRATION"}
            values = {self._clean(row[0]) for row in rows
                      if row[0] and self._clean(row[0]).upper() not in excluded}
            return sorted(values, key=str.casefold)
        except sqlite3.Error:
            logging.exception("Could not fetch user departments")
            return []

    # IMPORT / EXPORT
    def import_books_batch(self, books_data: list):
        """Atomically insert or merge books; input rows retain the legacy 7-column format."""
        if not books_data:
            return True, 0
        try:
            normalized = []
            for row in books_data:
                if len(row) != 7:
                    raise ValueError("Each book import row must contain 7 values.")
                bid, title, author, publisher, total, available, created = row
                bid, title = self._clean(bid), self._clean(title)
                total, available = int(total), int(available)
                if not bid or not title or total < 0 or available < 0 or available > total:
                    raise ValueError(f"Invalid book import data for ID '{bid}'.")
                normalized.append((bid, title, self._clean(author), self._clean(publisher),
                                   total, available, created or datetime.date.today().isoformat()))
            with self._transaction(immediate=True):
                for row in normalized:
                    bid, title, author, publisher, total, available, created = row
                    existing = self.conn.execute(
                        "SELECT total_copies, available_copies FROM books WHERE id = ?", (bid,)
                    ).fetchone()
                    if existing:
                        issued = int(existing[0]) - int(existing[1])
                        new_total = int(existing[0]) + total
                        self.conn.execute("""
                            UPDATE books SET title = ?, author = ?, publisher = ?,
                                total_copies = ?, available_copies = ?
                            WHERE id = ?
                        """, (title, author, publisher, new_total, new_total - issued, bid))
                    else:
                        self.conn.execute("""
                            INSERT INTO books(id, title, author, publisher, total_copies,
                                available_copies, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, row)
            return True, len(normalized)
        except Exception as exc:
            self.conn.rollback()
            logging.exception("Book batch import failed")
            return False, str(exc)

    def import_users_batch(self, users_data: list):
        """Atomically upsert legacy or email-enabled user rows."""
        if not users_data:
            return True, 0
        try:
            normalized = []
            departments_to_register = {}
            for row in users_data:
                if len(row) not in (6, 7):
                    raise ValueError(
                        "Each user import row must contain 6 or 7 values."
                    )
                uid, name, phone, role, dept, created = row[:6]
                email = row[6] if len(row) == 7 else None
                uid, name, role = self._clean(uid).upper(), self._clean(name), self._clean(role)
                if not uid or not name or not role:
                    raise ValueError("Imported users require an ID, full name, and role.")
                department = self._clean(dept)
                role_key = role.casefold()
                department_category = (
                    "STUDENT"
                    if "student" in role_key
                    else "FACULTY"
                    if any(
                        kind in role_key
                        for kind in ("faculty", "staff", "guest")
                    )
                    else None
                )
                if (
                    department_category
                    and department
                    and department.casefold() not in {
                        "general",
                        "general administration",
                        "n/a",
                    }
                ):
                    departments_to_register.setdefault(
                        department.casefold(),
                        (department, department_category),
                    )
                normalized.append((uid, name, self._clean(phone) or None, role,
                                   department, self._clean(email).casefold() or None,
                                   created or datetime.date.today().isoformat()))
            with self._transaction(immediate=True):
                self.conn.executemany("""
                    INSERT INTO departments(name, category, duration_years)
                    VALUES (?, ?, 3)
                    ON CONFLICT(name) DO NOTHING
                """, list(departments_to_register.values()))
                self.conn.executemany("""
                    INSERT INTO users(
                        id, full_name, phone_number, role, department,
                        email, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        full_name = excluded.full_name,
                        phone_number = excluded.phone_number,
                        role = excluded.role,
                        department = excluded.department,
                        email = COALESCE(excluded.email, users.email)
                """, normalized)
            return True, len(normalized)
        except Exception as exc:
            self.conn.rollback()
            logging.exception("User batch import failed")
            return False, str(exc)

    def export_and_delete_final_year_students(self, output_directory: str,
                                              skip_active_loans: bool = True):
        try:
            os.makedirs(output_directory, exist_ok=True)
            current_year = datetime.date.today().year
            students = self.conn.execute("""
                SELECT id, full_name, COALESCE(phone_number, ''), role, department, created_at
                FROM users WHERE LOWER(role) = 'student'
            """).fetchall()

            graduating = []
            for student in students:
                try:
                    prefix = self._clean(student[0])[:2]
                    admission_year = int("20" + prefix)
                    duration = self.get_course_duration(student[4])
                    if current_year - admission_year >= duration - 1:
                        graduating.append(student)
                except (ValueError, TypeError):
                    continue

            if not graduating:
                return False, 0, "No graduating final-year students found across active course structures."

            ids = [s[0] for s in graduating]
            marks = ",".join("?" for _ in ids)
            active_rows = self.conn.execute(f"""
                SELECT DISTINCT u.id, u.full_name
                FROM circulation_logs c JOIN users u ON c.user_id = u.id
                WHERE c.user_id IN ({marks}) AND c.status = 'ISSUED'
            """, ids).fetchall()
            active_map = {r[0]: r[1] for r in active_rows}

            skipped = [s for s in graduating if s[0] in active_map]
            if skipped and not skip_active_loans:
                names = "\n".join(f"• {s[0]} - {s[1]}" for s in skipped[:10])
                if len(skipped) > 10:
                    names += f"\n...and {len(skipped) - 10} more."
                return False, 0, (
                    "Cannot archive batch because the following students have active unreturned books:\n\n"
                    + names
                )

            archive = [s for s in graduating if s[0] not in active_map]
            if not archive:
                return False, 0, "All final-year students have issued books and were skipped."

            filename = f"Graduated_Batch_{current_year - 3}_Archive.csv"
            path = os.path.join(output_directory, filename)
            temp_path = path + ".tmp"
            with open(temp_path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["PIN / ID", "Full Name", "Phone Number", "Role",
                                 "Department / Branch", "Created At"])
                writer.writerows(archive)
            os.replace(temp_path, path)

            archive_ids = [s[0] for s in archive]
            marks = ",".join("?" for _ in archive_ids)
            with self._transaction(immediate=True):
                # Recheck active loans inside the write transaction to avoid a race.
                active_now = self.conn.execute(f"""
                    SELECT COUNT(*) FROM circulation_logs
                    WHERE user_id IN ({marks}) AND status = 'ISSUED'
                """, archive_ids).fetchone()[0]
                if active_now:
                    return False, 0, "Archive cancelled: one or more selected students now have issued books."
                self.conn.execute(f"DELETE FROM users WHERE id IN ({marks})", archive_ids)

            message = f"Successfully archived {len(archive)} students from the graduating batch."
            if skipped:
                message += f"\n\nSkipped {len(skipped)} student(s) with issued books."
            return True, len(archive), message
        except Exception as exc:
            logging.exception("Final-year archive failed")
            return False, 0, self._parse_db_error(exc, "batch archiving final year students")

    # MAINTENANCE
    def backup_database(self, destination_path):
        """Create a consistent SQLite backup without copying a live WAL database manually."""
        try:
            destination_path = os.fspath(destination_path)
            os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
            backup_conn = sqlite3.connect(destination_path)
            try:
                self.conn.backup(backup_conn)
            finally:
                backup_conn.close()
            return True, destination_path
        except Exception as exc:
            logging.exception("Database backup failed")
            return False, str(exc)

    def get_database_stats(self):
        """Returns basic database health and storage statistics."""
        try:
            page_count = self.conn.execute("PRAGMA page_count").fetchone()[0]
            page_size = self.conn.execute("PRAGMA page_size").fetchone()[0]
            integrity = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
            return {
                "database_path": self.database_path,
                "size_bytes": page_count * page_size,
                "integrity": integrity,
                "journal_mode": self.conn.execute("PRAGMA journal_mode").fetchone()[0],
            }
        except sqlite3.Error:
            logging.exception("Could not read database statistics")
            return {}

    def close(self):
        """Close the SQLite connection cleanly. Safe to call more than once."""
        if getattr(self, "conn", None) is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                logging.exception("Error closing database")
            finally:
                self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

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

from utils import (
    COLLEGE_BRANCHES,
    COLLEGE_BRANCH_NAMES,
    DEFAULT_BRANCH_CODES,
    FACULTY_ADDITIONAL_DEPARTMENTS,
    FACULTY_ADDITIONAL_DEPARTMENT_NAMES,
    format_log_id_display,
    get_appdata_db_path,
    normalize_department_for_role as _normalize_static_department_for_role,
)


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

    def get_data_stamp(self):
        """Return a lightweight revision token changing on data writes, external commits, or date changes."""
        today = datetime.date.today().isoformat()
        conn = getattr(self, "conn", None)
        if conn is None:
            return (None, None, today)
        try:
            total_changes = int(conn.total_changes)
        except sqlite3.Error:
            total_changes = None
        try:
            row = conn.execute("PRAGMA data_version").fetchone()
            data_version = int(row[0]) if row else 0
        except sqlite3.Error:
            data_version = 0
        return (total_changes, data_version, today)

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
                    log_code TEXT,
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
                CREATE TABLE IF NOT EXISTS renewal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loan_id INTEGER NOT NULL,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    previous_due_date TIMESTAMP,
                    new_due_date TIMESTAMP,
                    extended_days INTEGER NOT NULL CHECK(extended_days > 0),
                    base_mode TEXT NOT NULL DEFAULT 'DUE_DATE',
                    fine_assessed DECIMAL(10, 2) DEFAULT 0.00,
                    fine_action TEXT NOT NULL DEFAULT 'NONE',
                    notes TEXT,
                    renewed_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(loan_id) REFERENCES circulation_logs(id)
                        ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fine_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loan_id INTEGER NOT NULL,
                    book_id TEXT COLLATE NOCASE,
                    user_id TEXT COLLATE NOCASE,
                    amount DECIMAL(10, 2) NOT NULL CHECK(amount >= 0),
                    action TEXT NOT NULL CHECK(action IN ('PAID', 'COLLECTED', 'WAIVED')),
                    note TEXT,
                    settled_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(loan_id) REFERENCES circulation_logs(id)
                        ON DELETE CASCADE
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
                CREATE TABLE IF NOT EXISTS email_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    trigger_type TEXT NOT NULL CHECK(
                        trigger_type IN (
                            'REGISTRATION', 'ISSUE', 'RETURN',
                            'DUE_ALERT', 'SYSTEM_ALERT'
                        )
                    ),
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(
                        status IN ('PENDING', 'SENT', 'FAILED')
                    ),
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP NULL,
                    dedupe_key TEXT UNIQUE,
                    reminder_loan_id INTEGER,
                    reminder_type TEXT,
                    next_attempt_at REAL NOT NULL DEFAULT 0
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
                CREATE TABLE IF NOT EXISTS complaint_email_imports (
                    message_key TEXT PRIMARY KEY,
                    sender_email TEXT,
                    subject TEXT,
                    action TEXT NOT NULL CHECK(action IN ('IMPORTED', 'IGNORED')),
                    complaint_id INTEGER,
                    processed_at TIMESTAMP NOT NULL
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
            self._ensure_column("circulation_logs", "log_code", "TEXT")
            self._ensure_column("circulation_logs", "status", "TEXT DEFAULT 'ISSUED'")
            self._ensure_column("circulation_logs", "fine_amount", "DECIMAL(10, 2) DEFAULT 0.00")
            self._ensure_column("circulation_logs", "renewal_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("circulation_logs", "last_renewed_at", "TIMESTAMP")
            self._ensure_column("circulation_logs", "fine_settled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("circulation_logs", "fine_settled_at", "TIMESTAMP")
            self._ensure_column("circulation_logs", "fine_settlement_action", "TEXT")
            self._ensure_column("circulation_logs", "fine_settlement_note", "TEXT")
            self._ensure_column("users", "email", "TEXT")
            self._ensure_column("departments", "branch_code", "TEXT DEFAULT ''")
            self._ensure_column("complaints", "source", "TEXT DEFAULT 'DESK'")
            self._ensure_column("complaints", "reporter_name", "TEXT")
            self._ensure_column("complaints", "reporter_email", "TEXT")
            self._ensure_column("complaints", "email_message_id", "TEXT")
            self._ensure_column("complaints", "staff_notes", "TEXT")

            self._backfill_circulation_log_codes(cur)

            cur.executescript("""
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
                CREATE INDEX IF NOT EXISTS idx_users_department ON users(department);
                CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_log_code ON circulation_logs(log_code COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_logs_user_status ON circulation_logs(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_logs_book_status ON circulation_logs(book_id, status);
                CREATE INDEX IF NOT EXISTS idx_logs_due_status ON circulation_logs(due_date, status);
                CREATE INDEX IF NOT EXISTS idx_logs_checkout ON circulation_logs(checkout_date);
                CREATE INDEX IF NOT EXISTS idx_renewal_logs_loan ON renewal_logs(loan_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_fine_payments_loan ON fine_payments(loan_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_fine_payments_user ON fine_payments(user_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_email_queue_status_created
                    ON email_queue(status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_complaints_email_message_id
                    ON complaints(email_message_id)
                    WHERE email_message_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_complaints_status_created
                    ON complaints(status, created_at DESC, id DESC);
            """)

            if cur.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
                # Retained for compatibility with the existing login dialog.
                # Change this default immediately after first launch.
                cur.executemany(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    [("admin_password", "admin123"), ("daily_fine", "10.0"), ("default_days", "14")],
                )

            cur.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                [
                    ("max_renewals", "2"),
                    ("allow_overdue_renewal", "1"),
                    ("email_complaint_import_enabled", "1"),
                    ("email_complaint_auto_reply", "1"),
                    ("email_complaint_filter_mode", "keywords"),
                ],
            )

            canonical_departments = [
                (name, "STUDENT", duration, DEFAULT_BRANCH_CODES.get(name, ""))
                for name, duration in COLLEGE_BRANCHES
            ] + [
                (name, "FACULTY", duration, DEFAULT_BRANCH_CODES.get(name, ""))
                for name, duration in FACULTY_ADDITIONAL_DEPARTMENTS
            ]
            dept_seeded_row = cur.execute(
                "SELECT value FROM settings WHERE key = 'departments_seeded_v2'"
            ).fetchone()
            dept_count = cur.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
            if dept_count == 0 or not dept_seeded_row or str(dept_seeded_row[0]) != "1":
                cur.executemany(
                    """
                    INSERT INTO departments(name, category, duration_years, branch_code)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        branch_code = COALESCE(NULLIF(departments.branch_code, ''), excluded.branch_code)
                    """,
                    canonical_departments,
                )
                cur.execute(
                    "INSERT OR REPLACE INTO settings(key, value) VALUES ('departments_seeded_v2', '1')"
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

    _LOG_CODE_PATTERN = re.compile(r"^CIR-(\d{6})-(\d+)$", re.IGNORECASE)
    _LOG_CODE_SQL = "COALESCE(NULLIF(log_code, ''), CAST(id AS TEXT))"
    _C_LOG_CODE_SQL = "COALESCE(NULLIF(c.log_code, ''), CAST(c.id AS TEXT))"

    @classmethod
    def _parse_loan_ref(cls, loan_ref):
        """Parse a user-facing log code ('CIR-...') or legacy integer PK."""
        if loan_ref is None or isinstance(loan_ref, bool):
            return None, None
        if isinstance(loan_ref, int):
            return ("PK", loan_ref) if loan_ref > 0 else (None, None)
        text = cls._clean(loan_ref)
        if text.startswith("#"):
            text = cls._clean(text[1:])
        if not text:
            return None, None
        if text.isdigit():
            pk = int(text)
            return ("PK", pk) if pk > 0 else (None, None)
        if cls._LOG_CODE_PATTERN.match(text):
            return "CODE", text.upper()
        return None, None

    def _resolve_loan_pk(self, loan_ref) -> Optional[int]:
        kind, val = self._parse_loan_ref(loan_ref)
        if kind == "PK":
            row = self.conn.execute(
                "SELECT id FROM circulation_logs WHERE id = ?",
                (val,),
            ).fetchone()
            return int(row[0]) if row else None
        if kind == "CODE":
            row = self.conn.execute(
                "SELECT id FROM circulation_logs WHERE log_code = ? COLLATE NOCASE",
                (val,),
            ).fetchone()
            return int(row[0]) if row else None
        return None

    def _backfill_circulation_log_codes(self, cur=None):
        """Assign structured CIR-YYMMDD-NNNN codes to any legacy rows lacking log_code."""
        cursor = cur or self.conn.cursor()
        rows = cursor.execute(
            "SELECT id, checkout_date, COALESCE(log_code, '') FROM circulation_logs ORDER BY id ASC"
        ).fetchall()
        if not rows:
            return

        used_codes = set()
        daily_max = {}
        pending = []
        for row_id, checkout_date, existing_code in rows:
            clean_code = self._clean(existing_code).upper()
            if clean_code:
                used_codes.add(clean_code)
                match = self._LOG_CODE_PATTERN.match(clean_code)
                if match:
                    date_key, seq_text = match.groups()
                    daily_max[date_key] = max(daily_max.get(date_key, 0), int(seq_text))
            else:
                pending.append((int(row_id), checkout_date))

        if not pending:
            return

        fallback_dt = datetime.datetime.now()
        updates = []
        for row_id, checkout_date in pending:
            ref_dt = self._parse_circulation_datetime(checkout_date) or fallback_dt
            date_key = ref_dt.strftime("%y%m%d")
            seq = daily_max.get(date_key, 0) + 1
            candidate = f"CIR-{date_key}-{seq:04d}"
            while candidate in used_codes:
                seq += 1
                candidate = f"CIR-{date_key}-{seq:04d}"
            daily_max[date_key] = seq
            used_codes.add(candidate)
            updates.append((candidate, row_id))

        cursor.executemany(
            "UPDATE circulation_logs SET log_code = ? WHERE id = ?",
            updates,
        )

    def _generate_next_log_code(self, ref_dt=None) -> str:
        """Generate the next unique CIR-YYMMDD-NNNN identifier for ref_dt."""
        ref = ref_dt or datetime.datetime.now()
        date_key = ref.strftime("%y%m%d")
        prefix = f"CIR-{date_key}-"
        rows = self.conn.execute(
            "SELECT log_code FROM circulation_logs WHERE log_code LIKE ?",
            (f"{prefix}%",),
        ).fetchall()
        max_seq = 0
        used_codes = set()
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
        for (code,) in rows:
            clean_code = self._clean(code).upper()
            if not clean_code:
                continue
            used_codes.add(clean_code)
            match = pattern.match(clean_code)
            if match:
                max_seq = max(max_seq, int(match.group(1)))
        seq = max_seq + 1
        candidate = f"{prefix}{seq:04d}"
        while candidate in used_codes:
            seq += 1
            candidate = f"{prefix}{seq:04d}"
        return candidate

    def _query_loan_columns_by_refs(self, columns_sql: str, log_ids=None):
        """Fetch columns from circulation_logs for None (all) or mixed PK/log_code refs."""
        if self.conn is None:
            return []
        if log_ids is None:
            rows = self.conn.execute(
                f"SELECT {self._LOG_CODE_SQL}, {columns_sql} FROM circulation_logs"
            ).fetchall()
            return [(str(row[0]), row[1:]) for row in rows]

        pk_map = {}
        code_map = {}
        for raw_ref in log_ids:
            kind, val = self._parse_loan_ref(raw_ref)
            if kind == "PK":
                pk_map.setdefault(val, []).append(raw_ref)
            elif kind == "CODE":
                code_map.setdefault(val, []).append(raw_ref)

        matched = []
        pk_list = list(pk_map.keys())
        for offset in range(0, len(pk_list), 500):
            batch = pk_list[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.conn.execute(
                f"SELECT id, {columns_sql} FROM circulation_logs WHERE id IN ({placeholders})",
                batch,
            ).fetchall()
            for row in rows:
                pk = int(row[0])
                payload = row[1:]
                for orig_ref in pk_map.get(pk, ()):
                    matched.append((orig_ref, payload))

        code_list = list(code_map.keys())
        for offset in range(0, len(code_list), 500):
            batch = code_list[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.conn.execute(
                f"SELECT log_code, {columns_sql} FROM circulation_logs "
                f"WHERE log_code COLLATE NOCASE IN ({placeholders})",
                batch,
            ).fetchall()
            for row in rows:
                code_key = self._clean(row[0]).upper()
                payload = row[1:]
                for orig_ref in code_map.get(code_key, ()):
                    matched.append((orig_ref, payload))

        return matched

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

    def _enqueue_email_in_transaction(
        self,
        recipient_email,
        subject,
        body,
        trigger_type,
        dedupe_key=None,
        reminder_loan_id=None,
        reminder_type=None,
    ):
        trigger_type = self._clean(trigger_type).upper()
        if trigger_type not in {
            "REGISTRATION", "ISSUE", "RETURN", "DUE_ALERT", "SYSTEM_ALERT"
        }:
            raise ValueError(f"Unsupported email trigger type: {trigger_type}")

        cursor = self.conn.execute("""
            INSERT INTO email_queue(
                recipient_email, subject, body, trigger_type, dedupe_key,
                reminder_loan_id, reminder_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
        """, (
            self._clean(recipient_email),
            self._clean(subject),
            str(body or ""),
            trigger_type,
            dedupe_key,
            reminder_loan_id,
            reminder_type,
        ))
        if cursor.rowcount:
            return cursor.lastrowid
        row = self.conn.execute(
            "SELECT id FROM email_queue WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        return row[0] if row else None

    def _queue_registration_email_in_transaction(
        self,
        user_id,
        full_name,
        recipient_email,
    ):
        if not recipient_email:
            return
        self._enqueue_email_in_transaction(
            recipient_email,
            "Library registration confirmation",
            (
                f"Hello {full_name},\n\n"
                "Your library account has been created "
                f"successfully. Your user ID is {user_id}.\n\n"
                "Library"
            ),
            "REGISTRATION",
        )

    def enqueue_email(
        self,
        recipient_email,
        subject,
        body,
        trigger_type="SYSTEM_ALERT",
        dedupe_key=None,
    ):
        recipient = self._clean(recipient_email)
        if not recipient:
            raise ValueError("The recipient email address is required.")
        with self._transaction(immediate=True):
            return self._enqueue_email_in_transaction(
                recipient,
                subject,
                body,
                trigger_type,
                dedupe_key,
            )

    def get_pending_emails(self, limit=100):
        limit = max(1, min(int(limit), 500))
        return self.conn.execute("""
            SELECT id, recipient_email, subject, body
            FROM email_queue
            WHERE status = 'PENDING' AND next_attempt_at <= ?
            ORDER BY created_at, id
            LIMIT ?
        """, (datetime.datetime.now().timestamp(), limit)).fetchall()

    def get_email_queue_counts(self):
        counts = dict(self.conn.execute("""
            SELECT status, COUNT(*) FROM email_queue GROUP BY status
        """).fetchall())
        return {
            "pending": int(counts.get("PENDING", 0)),
            "failed": int(counts.get("FAILED", 0)),
            "sent": int(counts.get("SENT", 0)),
        }

    def get_email_queue_items(self, status=None, limit=5000):
        allowed_statuses = {"PENDING", "FAILED", "SENT"}
        if status is not None:
            status = str(status).upper()
            if status not in allowed_statuses:
                raise ValueError(f"Unsupported email status: {status}")
            query = """
                SELECT id, recipient_email, subject, trigger_type, status,
                       retry_count, created_at, sent_at, body
                FROM email_queue
                WHERE status = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """
            parameters = (status, max(1, min(int(limit), 10000)))
        else:
            query = """
                SELECT id, recipient_email, subject, trigger_type, status,
                       retry_count, created_at, sent_at, body
                FROM email_queue
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            """
            parameters = (max(1, min(int(limit), 10000)),)
        return self.conn.execute(query, parameters).fetchall()

    def delete_unsent_email_queue_items(self, email_ids=None):
        with self._transaction(immediate=True):
            delivery_enabled = str(
                self.get_setting("email_delivery_enabled", "0")
            ).casefold() in ("1", "true", "yes")
            if delivery_enabled:
                raise RuntimeError(
                    "Disable queued email delivery before deleting messages."
                )
            if email_ids is None:
                cursor = self.conn.execute("""
                    DELETE FROM email_queue
                    WHERE status IN ('PENDING', 'FAILED')
                """)
                return cursor.rowcount

            return self._delete_email_queue_ids(email_ids)

    def delete_email_queue_items(self, email_ids):
        with self._transaction(immediate=True):
            delivery_enabled = str(
                self.get_setting("email_delivery_enabled", "0")
            ).casefold() in ("1", "true", "yes")
            if delivery_enabled:
                raise RuntimeError(
                    "Disable queued email delivery before deleting messages."
                )
            return self._delete_email_queue_ids(email_ids)

    def _delete_email_queue_ids(self, email_ids):
        ids = sorted({int(email_id) for email_id in email_ids})
        deleted = 0
        for offset in range(0, len(ids), 500):
            batch = ids[offset:offset + 500]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            cursor = self.conn.execute(
                f"""
                DELETE FROM email_queue
                WHERE id IN ({placeholders})
                """,
                batch,
            )
            deleted += cursor.rowcount
        return deleted

    def mark_email_sent(self, email_id, sent_at=None):
        sent_at = sent_at or datetime.datetime.now().isoformat(timespec="seconds")
        with self._transaction(immediate=True):
            row = self.conn.execute("""
                SELECT reminder_loan_id, reminder_type
                FROM email_queue
                WHERE id = ? AND status IN ('PENDING', 'FAILED')
            """, (int(email_id),)).fetchone()
            if not row:
                return False
            self.conn.execute("""
                UPDATE email_queue
                SET status = 'SENT', sent_at = ?
                WHERE id = ? AND status IN ('PENDING', 'FAILED')
            """, (sent_at, int(email_id)))
            loan_id, reminder_type = row
            if loan_id is not None and reminder_type:
                self.conn.execute("""
                    INSERT OR IGNORE INTO email_notifications(
                        loan_id, reminder_type, sent_at
                    )
                    VALUES (?, ?, ?)
                """, (loan_id, reminder_type, sent_at))
        return True

    def mark_email_failed(self, email_id, max_retries=5):
        with self._transaction(immediate=True):
            row = self.conn.execute("""
                SELECT retry_count FROM email_queue
                WHERE id = ? AND status = 'PENDING'
            """, (int(email_id),)).fetchone()
            if not row:
                return None
            retry_count = int(row[0]) + 1
            status = "FAILED" if retry_count >= max_retries else "PENDING"
            next_attempt_at = (
                datetime.datetime.now().timestamp()
                + min(60 * (2 ** (retry_count - 1)), 3600)
            )
            self.conn.execute("""
                UPDATE email_queue
                SET retry_count = ?, status = ?, next_attempt_at = ?
                WHERE id = ? AND status = 'PENDING'
            """, (retry_count, status, next_attempt_at, int(email_id)))
        return retry_count

    def requeue_failed_emails(self):
        with self._transaction(immediate=True):
            cursor = self.conn.execute("""
                UPDATE email_queue
                SET status = 'PENDING', next_attempt_at = 0
                WHERE status = 'FAILED'
            """)
        return cursor.rowcount

    def prepare_email_queue_for_manual_sync(self):
        with self._transaction(immediate=True):
            cursor = self.conn.execute("""
                UPDATE email_queue
                SET status = 'PENDING', next_attempt_at = 0
                WHERE status IN ('PENDING', 'FAILED')
            """)
        return cursor.rowcount

    def enqueue_due_email_reminders(self, today=None):
        today = today or datetime.date.today().isoformat()
        queued = 0
        for (
            loan_id, email, full_name, book_title, due_date, reminder_type
        ) in self.get_due_email_reminders(today):
            if reminder_type == "due_today":
                subject = f"Library book due today: {book_title}"
                body = (
                    f"Hello {full_name},\n\n"
                    f"'{book_title}' is due today ({due_date}). "
                    "Please return it to the library today or contact "
                    "the library if you need assistance.\n\nLibrary"
                )
            else:
                subject = f"Overdue library book: {book_title}"
                body = (
                    f"Hello {full_name},\n\n"
                    f"'{book_title}' was due on {due_date} and is now "
                    "overdue. Please return it to the library as soon "
                    "as possible. Contact the library if it has already "
                    "been returned.\n\nLibrary"
                )
            dedupe_key = f"due:{loan_id}:{reminder_type}:{today}"
            with self._transaction(immediate=True):
                existing = self.conn.execute(
                    "SELECT 1 FROM email_queue WHERE dedupe_key = ?",
                    (dedupe_key,),
                ).fetchone()
                self._enqueue_email_in_transaction(
                    email,
                    subject,
                    body,
                    "DUE_ALERT",
                    dedupe_key=dedupe_key,
                    reminder_loan_id=loan_id,
                    reminder_type=reminder_type,
                )
                if not existing:
                    queued += 1
        return queued

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
    @staticmethod
    def _clean_branch_code(branch_code) -> tuple[bool, str, str]:
        code = " ".join(str(branch_code or "").split()).upper()
        if not code:
            return True, "", ""
        if not re.fullmatch(r"[A-Z0-9_-]{1,12}", code):
            return (
                False,
                "",
                "Branch short code must be 1–12 characters (letters, numbers, '-' or '_').",
            )
        return True, code, ""

    def get_departments(self, category=None):
        try:
            category_key = self._clean(category).upper()
            student_rows = [
                str(r[0])
                for r in self.conn.execute(
                    """
                    SELECT name FROM departments
                    WHERE UPPER(COALESCE(category, 'STUDENT')) = 'STUDENT'
                    ORDER BY name COLLATE NOCASE ASC
                    """
                ).fetchall()
                if r[0]
            ]
            if category_key == "STUDENT":
                return student_rows

            faculty_rows = [
                str(r[0])
                for r in self.conn.execute(
                    """
                    SELECT name FROM departments
                    WHERE UPPER(COALESCE(category, 'STUDENT')) != 'STUDENT'
                    ORDER BY name COLLATE NOCASE ASC
                    """
                ).fetchall()
                if r[0]
            ]
            if not category_key or category_key == "FACULTY":
                return student_rows + faculty_rows
            return []
        except sqlite3.Error:
            logging.exception("Could not read departments table; using fallback defaults")
            branches = sorted(COLLEGE_BRANCH_NAMES, key=str.casefold)
            faculty_extras = list(FACULTY_ADDITIONAL_DEPARTMENT_NAMES)
            if self._clean(category).upper() == "STUDENT":
                return branches
            if not category or self._clean(category).upper() == "FACULTY":
                return branches + faculty_extras
            return []

    def get_departments_detailed(self):
        try:
            rows = self.conn.execute(
                """
                SELECT
                    d.id,
                    d.name,
                    UPPER(COALESCE(d.category, 'STUDENT')) AS category,
                    COALESCE(d.duration_years, 3) AS duration_years,
                    COALESCE(d.branch_code, '') AS branch_code,
                    COUNT(u.id) AS user_count,
                    SUM(CASE WHEN LOWER(COALESCE(u.role, '')) = 'student' THEN 1 ELSE 0 END) AS student_count,
                    SUM(CASE WHEN u.id IS NOT NULL AND LOWER(COALESCE(u.role, '')) != 'student' THEN 1 ELSE 0 END) AS staff_count
                FROM departments d
                LEFT JOIN users u
                    ON LOWER(TRIM(COALESCE(u.department, ''))) = LOWER(TRIM(COALESCE(d.name, '')))
                GROUP BY d.id, d.name, d.category, d.duration_years, d.branch_code
                ORDER BY
                    CASE WHEN UPPER(COALESCE(d.category, 'STUDENT')) = 'STUDENT' THEN 0 ELSE 1 END,
                    d.name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [
                {
                    "id": int(r[0]),
                    "name": str(r[1] or ""),
                    "category": str(r[2] or "STUDENT"),
                    "duration_years": int(r[3] or 3),
                    "branch_code": str(r[4] or ""),
                    "user_count": int(r[5] or 0),
                    "student_count": int(r[6] or 0),
                    "staff_count": int(r[7] or 0),
                }
                for r in rows
            ]
        except sqlite3.Error:
            logging.exception("Could not read detailed departments")
            return []

    def get_unlisted_user_departments(self):
        try:
            rows = self.conn.execute(
                """
                SELECT
                    TRIM(u.department) AS dept_name,
                    COUNT(*) AS user_count,
                    SUM(CASE WHEN LOWER(COALESCE(u.role, '')) = 'student' THEN 1 ELSE 0 END) AS student_count
                FROM users u
                WHERE TRIM(COALESCE(u.department, '')) != ''
                  AND NOT EXISTS (
                      SELECT 1 FROM departments d
                      WHERE LOWER(TRIM(COALESCE(d.name, ''))) = LOWER(TRIM(u.department))
                  )
                GROUP BY LOWER(TRIM(u.department))
                ORDER BY dept_name COLLATE NOCASE ASC
                """
            ).fetchall()
            return [
                {
                    "name": str(r[0]),
                    "user_count": int(r[1] or 0),
                    "student_count": int(r[2] or 0),
                }
                for r in rows
                if r[0]
            ]
        except sqlite3.Error:
            logging.exception("Could not check unlisted user departments")
            return []

    def normalize_department_for_role(self, department, role):
        key = " ".join(str(department or "").split()).casefold()
        if not key:
            return None
        try:
            rows = self.conn.execute(
                """
                SELECT name, UPPER(COALESCE(category, 'STUDENT')), COALESCE(branch_code, '')
                FROM departments
                """
            ).fetchall()
        except sqlite3.Error:
            rows = []

        if not rows:
            return _normalize_static_department_for_role(department, role)

        student_aliases = {}
        faculty_aliases = {}
        for name, category, code in rows:
            canonical = str(name or "").strip()
            if not canonical:
                continue
            faculty_aliases[canonical.casefold()] = canonical
            if code and str(code).strip():
                faculty_aliases.setdefault(str(code).strip().casefold(), canonical)
            if str(category or "").upper() == "STUDENT":
                student_aliases[canonical.casefold()] = canonical
                if code and str(code).strip():
                    student_aliases.setdefault(str(code).strip().casefold(), canonical)

        # Preserve historical alias translations when target exists in live DB
        legacy_static = {
            "humanities & science department": "Sciences & Humanities Department",
            "humanities and science department": "Sciences & Humanities Department",
            "sciences and humanities department": "Sciences & Humanities Department",
            "general administration department": "General Administration",
            "general adminstration department": "General Administration",
        }
        active_ci = {v.casefold(): v for v in faculty_aliases.values()}
        for alias_key, target_name in legacy_static.items():
            if target_name.casefold() in active_ci:
                faculty_aliases.setdefault(alias_key, active_ci[target_name.casefold()])

        return _normalize_static_department_for_role(
            department,
            role,
            student_aliases=student_aliases,
            faculty_aliases=faculty_aliases,
        )

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

    def add_department(self, name, category="STUDENT", duration_years=3, branch_code=""):
        clean_name = " ".join(str(name or "").split()).strip()
        category = self._clean(category).upper()
        if not clean_name:
            return False, "Enter a branch or department name."
        if len(clean_name) > 120:
            return False, "Branch / department name must be 120 characters or fewer."
        if category not in ("STUDENT", "FACULTY"):
            return False, "Select either Student & Faculty or Faculty & Staff Only."

        ok_code, clean_code, code_err = self._clean_branch_code(branch_code)
        if not ok_code:
            return False, code_err

        try:
            duration = int(duration_years) if category == "STUDENT" else 3
        except (TypeError, ValueError):
            return False, "Course duration must be between 1 and 6 years."
        if duration < 1 or duration > 6:
            return False, "Course duration must be between 1 and 6 years."

        try:
            with self._transaction(immediate=True):
                dup_name = self.conn.execute(
                    "SELECT id FROM departments WHERE name = ? COLLATE NOCASE",
                    (clean_name,),
                ).fetchone()
                if dup_name:
                    return False, f"A branch or department named '{clean_name}' already exists."
                if clean_code:
                    dup_code = self.conn.execute(
                        "SELECT name FROM departments WHERE UPPER(COALESCE(branch_code, '')) = ?",
                        (clean_code,),
                    ).fetchone()
                    if dup_code:
                        return (
                            False,
                            f"Short code '{clean_code}' is already assigned to '{dup_code[0]}'.",
                        )
                self.conn.execute(
                    """
                    INSERT INTO departments(name, category, duration_years, branch_code)
                    VALUES (?, ?, ?, ?)
                    """,
                    (clean_name, category, duration, clean_code),
                )
            return True, f"Added '{clean_name}' successfully."
        except Exception as exc:
            return False, self._parse_db_error(exc, "department creation")

    def update_department(
        self,
        dept_id,
        name,
        category,
        duration_years,
        branch_code="",
        cascade_users=True,
    ):
        clean_name = " ".join(str(name or "").split()).strip()
        category = self._clean(category).upper()
        if not clean_name:
            return False, "Enter a branch or department name."
        if len(clean_name) > 120:
            return False, "Branch / department name must be 120 characters or fewer."
        if category not in ("STUDENT", "FACULTY"):
            return False, "Select either Student & Faculty or Faculty & Staff Only."

        ok_code, clean_code, code_err = self._clean_branch_code(branch_code)
        if not ok_code:
            return False, code_err

        try:
            duration = int(duration_years) if category == "STUDENT" else 3
        except (TypeError, ValueError):
            return False, "Course duration must be between 1 and 6 years."
        if duration < 1 or duration > 6:
            return False, "Course duration must be between 1 and 6 years."

        try:
            with self._transaction(immediate=True):
                row = self.conn.execute(
                    "SELECT name, UPPER(COALESCE(category, 'STUDENT')) FROM departments WHERE id = ?",
                    (dept_id,),
                ).fetchone()
                if not row:
                    return False, "Department not found."
                old_name, old_category = str(row[0] or ""), str(row[1] or "STUDENT")

                dup_name = self.conn.execute(
                    "SELECT id FROM departments WHERE name = ? COLLATE NOCASE AND id != ?",
                    (clean_name, dept_id),
                ).fetchone()
                if dup_name:
                    return False, f"Another branch or department named '{clean_name}' already exists."

                if clean_code:
                    dup_code = self.conn.execute(
                        "SELECT name FROM departments WHERE UPPER(COALESCE(branch_code, '')) = ? AND id != ?",
                        (clean_code, dept_id),
                    ).fetchone()
                    if dup_code:
                        return (
                            False,
                            f"Short code '{clean_code}' is already assigned to '{dup_code[0]}'.",
                        )

                if old_category == "STUDENT" and category != "STUDENT":
                    other_student = self.conn.execute(
                        "SELECT COUNT(*) FROM departments WHERE UPPER(COALESCE(category, 'STUDENT')) = 'STUDENT' AND id != ?",
                        (dept_id,),
                    ).fetchone()[0]
                    if other_student == 0:
                        return (
                            False,
                            "At least one student branch must remain available.",
                        )
                    assigned_students = self.conn.execute(
                        """
                        SELECT COUNT(*) FROM users
                        WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                          AND LOWER(COALESCE(role, '')) = 'student'
                        """,
                        (old_name,),
                    ).fetchone()[0]
                    if assigned_students > 0:
                        return (
                            False,
                            f"Cannot restrict '{old_name}' to Faculty & Staff Only while "
                            f"{assigned_students} student(s) are assigned to it. Reassign those students first.",
                        )

                self.conn.execute(
                    """
                    UPDATE departments
                    SET name = ?, category = ?, duration_years = ?, branch_code = ?
                    WHERE id = ?
                    """,
                    (clean_name, category, duration, clean_code, dept_id),
                )

                updated_users = 0
                if cascade_users and clean_name != old_name:
                    cur = self.conn.execute(
                        """
                        UPDATE users
                        SET department = ?
                        WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                        """,
                        (clean_name, old_name),
                    )
                    updated_users = int(cur.rowcount or 0)

            msg = f"Updated '{clean_name}' successfully."
            if updated_users > 0:
                msg += f" Updated {updated_users} member record(s)."
            return True, msg
        except Exception as exc:
            return False, self._parse_db_error(exc, "department update")

    def reassign_department_users(self, source_name, target_name):
        src = self._clean(source_name)
        tgt = self._clean(target_name)
        if not src or not tgt:
            return False, "Select both source and target branches/departments."
        if src.casefold() == tgt.casefold():
            return False, "Source and target branch/department must be different."
        try:
            with self._transaction(immediate=True):
                tgt_row = self.conn.execute(
                    "SELECT name, UPPER(COALESCE(category, 'STUDENT')) FROM departments WHERE name = ? COLLATE NOCASE",
                    (tgt,),
                ).fetchone()
                if not tgt_row:
                    return False, f"Target branch/department '{tgt}' does not exist."
                canonical_target, tgt_cat = str(tgt_row[0]), str(tgt_row[1] or "STUDENT")
                student_cnt = self.conn.execute(
                    """
                    SELECT COUNT(*) FROM users
                    WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                      AND LOWER(COALESCE(role, '')) = 'student'
                    """,
                    (src,),
                ).fetchone()[0]
                if student_cnt > 0 and tgt_cat != "STUDENT":
                    return (
                        False,
                        f"Cannot move {student_cnt} student(s) into Faculty/Staff-only department '{canonical_target}'. "
                        "Select an academic student branch instead.",
                    )
                cur = self.conn.execute(
                    """
                    UPDATE users
                    SET department = ?
                    WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                    """,
                    (canonical_target, src),
                )
                moved = int(cur.rowcount or 0)
            return True, f"Reassigned {moved} member(s) from '{src}' to '{canonical_target}'."
        except Exception as exc:
            return False, self._parse_db_error(exc, "department reassignment")

    def delete_department(self, identifier, reassign_to=None):
        try:
            with self._transaction(immediate=True):
                if isinstance(identifier, int) or str(identifier or "").isdigit():
                    row = self.conn.execute(
                        "SELECT id, name, UPPER(COALESCE(category, 'STUDENT')) FROM departments WHERE id = ?",
                        (int(identifier),),
                    ).fetchone()
                else:
                    clean_name = self._clean(identifier)
                    row = self.conn.execute(
                        "SELECT id, name, UPPER(COALESCE(category, 'STUDENT')) FROM departments WHERE name = ? COLLATE NOCASE",
                        (clean_name,),
                    ).fetchone()

                if not row:
                    return False, "Branch or department not found."
                dept_id, name, category = int(row[0]), str(row[1]), str(row[2] or "STUDENT")

                if category == "STUDENT":
                    remaining_student = self.conn.execute(
                        "SELECT COUNT(*) FROM departments WHERE UPPER(COALESCE(category, 'STUDENT')) = 'STUDENT' AND id != ?",
                        (dept_id,),
                    ).fetchone()[0]
                    if remaining_student == 0:
                        return False, "At least one student academic branch must remain active."

                counts = self.conn.execute(
                    """
                    SELECT
                        COUNT(*),
                        SUM(CASE WHEN LOWER(COALESCE(role, '')) = 'student' THEN 1 ELSE 0 END)
                    FROM users
                    WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                    """,
                    (name,),
                ).fetchone()
                total_users = int(counts[0] or 0)
                student_users = int(counts[1] or 0)

                reassigned_msg = ""
                if total_users > 0:
                    if not self._clean(reassign_to):
                        return (
                            False,
                            f"Cannot delete '{name}' because {total_users} member(s) are assigned to it. "
                            "Choose a replacement branch/department to reassign those members first.",
                        )
                    tgt_row = self.conn.execute(
                        """
                        SELECT id, name, UPPER(COALESCE(category, 'STUDENT'))
                        FROM departments
                        WHERE name = ? COLLATE NOCASE AND id != ?
                        """,
                        (self._clean(reassign_to), dept_id),
                    ).fetchone()
                    if not tgt_row:
                        return False, f"Replacement branch/department '{reassign_to}' was not found."
                    tgt_name, tgt_cat = str(tgt_row[1]), str(tgt_row[2] or "STUDENT")
                    if student_users > 0 and tgt_cat != "STUDENT":
                        return (
                            False,
                            f"'{name}' has {student_users} student(s) and can only be reassigned to a student academic branch.",
                        )
                    self.conn.execute(
                        """
                        UPDATE users
                        SET department = ?
                        WHERE LOWER(TRIM(COALESCE(department, ''))) = LOWER(TRIM(?))
                        """,
                        (tgt_name, name),
                    )
                    reassigned_msg = f" Reassigned {total_users} member(s) to '{tgt_name}'."

                self.conn.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
            return True, f"Deleted '{name}'.{reassigned_msg}"
        except Exception as exc:
            return False, self._parse_db_error(exc, "department removal")

    def restore_default_departments(self):
        canonical_departments = [
            (name, "STUDENT", duration, DEFAULT_BRANCH_CODES.get(name, ""))
            for name, duration in COLLEGE_BRANCHES
        ] + [
            (name, "FACULTY", duration, DEFAULT_BRANCH_CODES.get(name, ""))
            for name, duration in FACULTY_ADDITIONAL_DEPARTMENTS
        ]
        try:
            added = 0
            with self._transaction(immediate=True):
                for name, category, duration, code in canonical_departments:
                    exists = self.conn.execute(
                        "SELECT id, COALESCE(branch_code, '') FROM departments WHERE name = ? COLLATE NOCASE",
                        (name,),
                    ).fetchone()
                    if not exists:
                        safe_code = code
                        if safe_code and self.conn.execute(
                            "SELECT 1 FROM departments WHERE UPPER(COALESCE(branch_code, '')) = ?",
                            (safe_code,),
                        ).fetchone():
                            safe_code = ""
                        self.conn.execute(
                            """
                            INSERT INTO departments(name, category, duration_years, branch_code)
                            VALUES (?, ?, ?, ?)
                            """,
                            (name, category, duration, safe_code),
                        )
                        added += 1
                    elif not exists[1] and code:
                        if not self.conn.execute(
                            "SELECT 1 FROM departments WHERE UPPER(COALESCE(branch_code, '')) = ? AND id != ?",
                            (code, exists[0]),
                        ).fetchone():
                            self.conn.execute(
                                "UPDATE departments SET branch_code = ? WHERE id = ?",
                                (code, exists[0]),
                            )
            if added:
                return True, f"Restored {added} default branch(es)/department(s)."
            return True, "All default college branches and departments are already present."
        except Exception as exc:
            return False, self._parse_db_error(exc, "default department restore")

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
                self._queue_registration_email_in_transaction(
                    uid,
                    name,
                    email,
                )
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
                log_code = self._generate_next_log_code(now)
                self.conn.execute("""
                    INSERT INTO circulation_logs(
                        log_code, book_id, user_id, checkout_date, due_date, status
                    )
                    VALUES (?, ?, ?, ?, ?, 'ISSUED')
                """, (log_code, bid, uid, checkout_text, due_text))
                self.conn.execute("""
                    UPDATE books SET available_copies = available_copies - 1
                    WHERE id = ? AND available_copies > 0
                """, (bid,))
                details = self.conn.execute("""
                    SELECT u.email, u.full_name, b.title
                    FROM users u
                    JOIN books b ON b.id = ?
                    WHERE u.id = ?
                """, (bid, uid)).fetchone()
                if details and details[0]:
                    email, full_name, title = details
                    self._enqueue_email_in_transaction(
                        email,
                        f"Book issued: {title}",
                        (
                            f"Hello {full_name},\n\n"
                            f"Book '{title}' (Book ID: {bid}) has been "
                            f"issued to your account (Transaction ID: {log_code}). "
                            f"It is due on {due_text}.\n\nLibrary"
                        ),
                        "ISSUE",
                        dedupe_key=f"issue:{log_code}",
                    )
            return True, f"Book issued successfully! Transaction ID: {log_code} · Due Date: {due_text}"
        except Exception as exc:
            return False, self._parse_db_error(exc, "book issue")

    @staticmethod
    def _parse_circulation_datetime(value):
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in (
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        try:
            return datetime.datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None

    def get_max_renewals(self):
        try:
            value = int(self.get_setting("max_renewals", 2))
            return max(0, value)
        except (TypeError, ValueError):
            return 2

    def get_allow_overdue_renewal(self):
        raw = str(self.get_setting("allow_overdue_renewal", "1")).strip().casefold()
        return raw in ("1", "true", "yes", "on")

    def get_renewal_counts(self, log_ids=None):
        return {
            loan_id: meta[0]
            for loan_id, meta in self.get_loan_renewal_meta(log_ids).items()
        }

    def get_loan_renewal_meta(self, log_ids=None):
        try:
            matched = self._query_loan_columns_by_refs(
                "COALESCE(renewal_count, 0), COALESCE(last_renewed_at, '')",
                log_ids=log_ids,
            )
            return {
                key: (int(vals[0] or 0), str(vals[1] or ""))
                for key, vals in matched
            }
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Could not fetch loan renewal metadata")
            return {}

    def get_renewal_history(self, loan_id):
        try:
            pk = self._resolve_loan_pk(loan_id)
            if pk is None:
                return []
            rows = self.conn.execute("""
                SELECT r.id,
                       COALESCE(NULLIF(c.log_code, ''), CAST(r.loan_id AS TEXT)),
                       r.book_id, r.user_id, r.previous_due_date, r.new_due_date,
                       r.extended_days, r.base_mode, r.fine_assessed, r.fine_action, r.notes, r.renewed_at
                FROM renewal_logs r
                LEFT JOIN circulation_logs c ON c.id = r.loan_id
                WHERE r.loan_id = ?
                ORDER BY r.id DESC
            """, (pk,)).fetchall()
            history = []
            for row in rows:
                history.append({
                    "id": int(row[0]),
                    "loan_id": str(row[1] or ""),
                    "book_id": str(row[2] or ""),
                    "user_id": str(row[3] or ""),
                    "previous_due_date": str(row[4] or ""),
                    "new_due_date": str(row[5] or ""),
                    "extended_days": int(row[6] or 0),
                    "base_mode": str(row[7] or "DUE_DATE"),
                    "fine_assessed": round(float(row[8] or 0.0), 2),
                    "fine_action": str(row[9] or "NONE"),
                    "notes": str(row[10] or ""),
                    "renewed_at": str(row[11] or ""),
                })
            return history
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Could not fetch renewal history for loan %s", loan_id)
            return []

    def get_active_loan_id(self, book_id, user_id):
        bid, uid = self._clean(book_id), self._clean(user_id)
        try:
            row = self.conn.execute(f"""
                SELECT {self._LOG_CODE_SQL} FROM circulation_logs
                WHERE book_id = ? AND user_id = ? AND status = 'ISSUED'
                ORDER BY id DESC LIMIT 1
            """, (bid, uid)).fetchone()
            return str(row[0]) if row else None
        except (sqlite3.Error, ValueError, TypeError):
            return None

    def get_loan_renewal_preview(
        self,
        loan_id,
        extend_days=None,
        base_mode="auto",
        allow_limit_override=False,
        now=None,
    ):
        now_dt = (now or datetime.datetime.now()).replace(second=0, microsecond=0)
        kind, _ = self._parse_loan_ref(loan_id)
        if kind is None:
            return {"found": False, "eligible": False, "block_reason": "Invalid transaction ID."}
        lid = self._resolve_loan_pk(loan_id)
        if lid is None:
            return {
                "found": False,
                "eligible": False,
                "block_reason": f"Transaction {format_log_id_display(loan_id)} was not found.",
            }

        row = self.conn.execute(f"""
            SELECT c.id, {self._C_LOG_CODE_SQL}, c.book_id, c.user_id, c.checkout_date, c.due_date, c.return_date,
                   COALESCE(c.fine_amount, 0), UPPER(COALESCE(c.status, 'ISSUED')),
                   COALESCE(c.renewal_count, 0), COALESCE(c.last_renewed_at, ''),
                   COALESCE(b.title, 'Unknown Book'), COALESCE(b.author, ''),
                   COALESCE(b.total_copies, 0), COALESCE(b.available_copies, 0),
                   COALESCE(u.full_name, 'Unknown User'), COALESCE(u.role, 'Student'),
                   COALESCE(u.department, ''), COALESCE(u.email, '')
            FROM circulation_logs c
            LEFT JOIN books b ON b.id = c.book_id
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.id = ?
        """, (lid,)).fetchone()
        if not row:
            return {
                "found": False,
                "eligible": False,
                "block_reason": f"Transaction {format_log_id_display(loan_id)} was not found.",
            }

        (
            _id, display_id, book_id, user_id, checkout_date, due_date, return_date,
            carried_fine, status, renewal_count, last_renewed_at,
            book_title, book_author, total_copies, available_copies,
            user_name, user_role, user_department, user_email,
        ) = row

        policy = self.get_loan_policy(user_role)
        default_days = max(1, int(policy.get("default_days", 14)))
        max_books = max(0, int(policy.get("max_books", 3)))
        fine_rate = self._money(policy.get("fine_rate", 2.0), 2.0)
        max_renewals = self.get_max_renewals()
        allow_overdue = self.get_allow_overdue_renewal()

        active_loans_count = int(self.conn.execute("""
            SELECT COUNT(*) FROM circulation_logs
            WHERE user_id = ? AND status = 'ISSUED'
        """, (user_id,)).fetchone()[0])

        try:
            days = default_days if extend_days is None else int(extend_days)
        except (TypeError, ValueError):
            days = default_days
        days_valid = 1 <= days <= 365

        due_dt = self._parse_circulation_datetime(due_date)
        due_text = str(due_date or "")
        is_overdue = bool(status == "ISSUED" and due_dt and due_dt.date() < now_dt.date())
        is_due_today = bool(status == "ISSUED" and due_dt and due_dt.date() == now_dt.date())
        overdue_days = max(0, (now_dt.date() - due_dt.date()).days) if is_overdue and due_dt else 0
        accrued_fine = round(overdue_days * fine_rate, 2)
        carried_fine_val = round(max(0.0, float(carried_fine or 0.0)), 2)

        mode_key = self._clean(base_mode or "auto").upper()
        if mode_key not in ("AUTO", "DUE_DATE", "TODAY"):
            mode_key = "AUTO"
        if mode_key == "AUTO":
            effective_mode = "TODAY" if is_overdue else "DUE_DATE"
        else:
            effective_mode = mode_key

        if effective_mode == "DUE_DATE" and due_dt is not None:
            if len(due_text.strip()) <= 10:
                base_dt = due_dt.replace(hour=now_dt.hour, minute=now_dt.minute)
            else:
                base_dt = due_dt.replace(second=0, microsecond=0)
        else:
            base_dt = now_dt

        new_due_dt = base_dt + datetime.timedelta(days=max(1, days))
        new_due_text = new_due_dt.strftime("%Y-%m-%d %H:%M")
        result_date_valid = new_due_dt.date() >= now_dt.date()
        net_days_from_today = (new_due_dt.date() - now_dt.date()).days

        if status != "ISSUED":
            display_status = "RETURNED"
        elif is_overdue:
            display_status = "OVERDUE"
        elif is_due_today:
            display_status = "DUE TODAY"
        else:
            display_status = "ISSUED"

        limit_reached = bool(max_renewals > 0 and int(renewal_count) >= max_renewals)
        overdue_restricted = bool(is_overdue and not allow_overdue)
        requires_override = bool(limit_reached or overdue_restricted)

        block_reason = ""
        if status != "ISSUED":
            block_reason = "This book has already been returned and cannot be renewed."
        elif not days_valid:
            block_reason = "Extension duration must be between 1 and 365 days."
        elif not result_date_valid:
            block_reason = (
                "The calculated due date is still in the past. Choose 'Extend from Today' "
                "or increase the extension days."
            )
        elif limit_reached and not allow_limit_override:
            block_reason = (
                f"Maximum renewal limit reached ({renewal_count}/{max_renewals}). "
                "Enable Librarian Override to extend further."
            )
        elif overdue_restricted and not allow_limit_override:
            block_reason = (
                "Overdue renewals are restricted by Circulation Settings. "
                "Enable Librarian Override to renew."
            )

        warnings = []
        if int(available_copies or 0) <= 0:
            warnings.append(
                f"No spare shelf copies are available right now (0/{int(total_copies or 0)} on shelf)."
            )
        if active_loans_count > max_books and max_books > 0:
            warnings.append(
                f"Member currently holds {active_loans_count} active books (role limit: {max_books})."
            )
        if is_overdue and accrued_fine > 0:
            warnings.append(
                f"Loan is {overdue_days} day(s) overdue with ₹{accrued_fine:.2f} accrued fine."
            )
        if carried_fine_val > 0:
            warnings.append(
                f"Loan already carries ₹{carried_fine_val:.2f} in unpaid prior fine."
            )

        remaining_renewals = (
            None if max_renewals == 0 else max(0, max_renewals - int(renewal_count))
        )

        return {
            "found": True,
            "loan_id": str(display_id or _id),
            "internal_id": int(_id),
            "book_id": str(book_id or ""),
            "book_title": str(book_title or "Unknown Book"),
            "book_author": str(book_author or ""),
            "total_copies": int(total_copies or 0),
            "available_copies": int(available_copies or 0),
            "user_id": str(user_id or ""),
            "user_name": str(user_name or "Unknown User"),
            "user_role": str(user_role or "Student"),
            "user_department": str(user_department or ""),
            "user_email": str(user_email or ""),
            "active_loans_count": active_loans_count,
            "max_books": max_books,
            "checkout_date": str(checkout_date or ""),
            "due_date": due_text,
            "return_date": str(return_date or ""),
            "status": status,
            "display_status": display_status,
            "renewal_count": int(renewal_count),
            "max_renewals": max_renewals,
            "remaining_renewals": remaining_renewals,
            "last_renewed_at": str(last_renewed_at or ""),
            "default_days": default_days,
            "fine_rate": fine_rate,
            "allow_overdue_renewal": allow_overdue,
            "is_overdue": is_overdue,
            "is_due_today": is_due_today,
            "overdue_days": overdue_days,
            "accrued_fine": accrued_fine,
            "carried_fine": carried_fine_val,
            "extend_days": days,
            "base_mode": mode_key,
            "effective_base_mode": effective_mode,
            "new_due_date": new_due_text,
            "net_days_from_today": net_days_from_today,
            "result_date_valid": result_date_valid,
            "limit_reached": limit_reached,
            "overdue_restricted": overdue_restricted,
            "requires_override": requires_override,
            "eligible": not bool(block_reason),
            "block_reason": block_reason,
            "warnings": warnings,
            "history": self.get_renewal_history(_id),
        }

    def renew_loan(
        self,
        loan_id,
        extend_days=None,
        base_mode="auto",
        fine_action="CARRY",
        notes="",
        allow_limit_override=False,
    ):
        kind, _ = self._parse_loan_ref(loan_id)
        if kind is None:
            return False, {}, "Invalid transaction ID."
        lid = self._resolve_loan_pk(loan_id)
        if lid is None:
            return False, {}, f"Transaction {format_log_id_display(loan_id)} was not found."

        fine_action_key = self._clean(fine_action or "CARRY").upper()
        if fine_action_key not in ("CARRY", "COLLECTED", "WAIVED", "NONE"):
            return False, {}, f"Unsupported fine action '{fine_action_key}'."

        clean_notes = self._clean(notes)[:300]
        now_dt = datetime.datetime.now().replace(second=0, microsecond=0)
        renewed_at = now_dt.strftime("%Y-%m-%d %H:%M")

        try:
            with self._transaction(immediate=True):
                preview = self.get_loan_renewal_preview(
                    lid,
                    extend_days=extend_days,
                    base_mode=base_mode,
                    allow_limit_override=allow_limit_override,
                    now=now_dt,
                )
                if not preview.get("found"):
                    return False, {}, preview.get("block_reason", "Loan record not found.")
                if not preview.get("eligible"):
                    return False, {}, preview.get("block_reason", "Loan cannot be renewed.")

                accrued_fine = float(preview["accrued_fine"])
                carried_fine = float(preview["carried_fine"])
                if accrued_fine <= 0:
                    effective_fine_action = "NONE"
                    new_fine_balance = carried_fine
                else:
                    if fine_action_key == "NONE":
                        fine_action_key = "CARRY"
                    effective_fine_action = fine_action_key
                    if effective_fine_action == "CARRY":
                        new_fine_balance = round(carried_fine + accrued_fine, 2)
                    else:
                        new_fine_balance = carried_fine

                new_renewal_count = int(preview["renewal_count"]) + 1
                previous_due = preview["due_date"]
                new_due = preview["new_due_date"]
                days = int(preview["extend_days"])
                effective_base = preview["effective_base_mode"]

                final_notes = clean_notes
                if allow_limit_override and preview.get("requires_override"):
                    prefix = "[Override]"
                    final_notes = f"{prefix} {clean_notes}".strip() if clean_notes else prefix

                cursor = self.conn.execute("""
                    UPDATE circulation_logs
                    SET due_date = ?,
                        fine_amount = ?,
                        renewal_count = ?,
                        last_renewed_at = ?,
                        fine_settled = CASE WHEN ? > 0 THEN 0 ELSE COALESCE(fine_settled, 0) END
                    WHERE id = ? AND status = 'ISSUED'
                """, (new_due, new_fine_balance, new_renewal_count, renewed_at, new_fine_balance, lid))
                if cursor.rowcount == 0:
                    return False, {}, "The loan is no longer active and could not be renewed."

                self.conn.execute("""
                    INSERT INTO renewal_logs(
                        loan_id, book_id, user_id, previous_due_date, new_due_date,
                        extended_days, base_mode, fine_assessed, fine_action, notes, renewed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lid,
                    preview["book_id"],
                    preview["user_id"],
                    previous_due,
                    new_due,
                    days,
                    effective_base,
                    accrued_fine,
                    effective_fine_action,
                    final_notes,
                    renewed_at,
                ))

                if accrued_fine > 0 and effective_fine_action in ("COLLECTED", "WAIVED"):
                    self.conn.execute("""
                        INSERT INTO fine_payments(
                            loan_id, book_id, user_id, amount, action, note, settled_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        lid,
                        preview["book_id"],
                        preview["user_id"],
                        accrued_fine,
                        effective_fine_action,
                        final_notes or f"Recorded during renewal #{new_renewal_count}",
                        renewed_at,
                    ))

                # Allow due-today and overdue reminders to evaluate cleanly for the new due date.
                self.conn.execute(
                    "DELETE FROM email_notifications WHERE loan_id = ?",
                    (lid,),
                )

                display_id = str(preview["loan_id"])
                email = preview.get("user_email", "")
                if email:
                    fine_line = ""
                    if accrued_fine > 0:
                        if effective_fine_action == "CARRY":
                            fine_line = (
                                f" Overdue fine of ₹{accrued_fine:.2f} was added to your loan "
                                f"balance (total due on return: ₹{new_fine_balance:.2f})."
                            )
                        elif effective_fine_action == "COLLECTED":
                            fine_line = (
                                f" Overdue fine of ₹{accrued_fine:.2f} was recorded as collected."
                            )
                        elif effective_fine_action == "WAIVED":
                            fine_line = (
                                f" Overdue fine of ₹{accrued_fine:.2f} was waived upon renewal."
                            )

                    self._enqueue_email_in_transaction(
                        email,
                        f"Book renewed: {preview['book_title']}",
                        (
                            f"Hello {preview['user_name']},\n\n"
                            f"Book '{preview['book_title']}' (Book ID: {preview['book_id']}, "
                            f"Transaction ID: {display_id}) "
                            f"has been renewed for +{days} day(s). Previous due date: {previous_due}. "
                            f"New due date: {new_due}.{fine_line}\n\n"
                            "Library"
                        ),
                        "ISSUE",
                        dedupe_key=f"renew:{display_id}:{new_renewal_count}",
                    )

            details = {
                "loan_id": display_id,
                "internal_id": lid,
                "book_id": preview["book_id"],
                "book_title": preview["book_title"],
                "user_id": preview["user_id"],
                "user_name": preview["user_name"],
                "previous_due_date": previous_due,
                "new_due_date": new_due,
                "extended_days": days,
                "effective_base_mode": effective_base,
                "renewal_count": new_renewal_count,
                "max_renewals": preview["max_renewals"],
                "accrued_fine": accrued_fine,
                "carried_fine": new_fine_balance,
                "fine_action": effective_fine_action,
                "notes": final_notes,
                "renewed_at": renewed_at,
            }
            return True, details, f"Loan {format_log_id_display(display_id)} renewed successfully! New Due Date: {new_due}"
        except Exception as exc:
            return False, {}, self._parse_db_error(exc, "loan renewal")

    def renew_book(
        self,
        book_id,
        user_id,
        extend_days=None,
        base_mode="auto",
        fine_action="CARRY",
        notes="",
        allow_limit_override=False,
    ):
        bid, uid = self._clean(book_id), self._clean(user_id)
        loan_id = self.get_active_loan_id(bid, uid)
        if loan_id is None:
            return False, {}, (
                f"No active issue record found matching Book ID '{bid}' and User ID '{uid}'."
            )
        return self.renew_loan(
            loan_id,
            extend_days=extend_days,
            base_mode=base_mode,
            fine_action=fine_action,
            notes=notes,
            allow_limit_override=allow_limit_override,
        )

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
                record = self.conn.execute(f"""
                    SELECT id, {self._LOG_CODE_SQL}, due_date, COALESCE(fine_amount, 0)
                    FROM circulation_logs
                    WHERE book_id = ? AND user_id = ? AND status = 'ISSUED'
                    ORDER BY id DESC LIMIT 1
                """, (bid, uid)).fetchone()
                if not record:
                    return False, 0.0, (
                        f"No active issue record found matching Book ID '{bid}' and User ID '{uid}'."
                    )

                log_id, log_code, due_text, carried_fine = record
                now = datetime.datetime.now().replace(second=0, microsecond=0)
                fine_rate = self._money(policy.get("fine_rate", 2.0), 2.0)
                overdue_fine = 0.0
                if due_text:
                    due_dt = self._parse_circulation_datetime(due_text)
                    if due_dt and now > due_dt:
                        # Fine is charged per overdue calendar day, matching the app's date-based policy.
                        overdue_days = (now.date() - due_dt.date()).days
                        overdue_fine = round(max(0, overdue_days) * fine_rate, 2)
                fine = round(max(0.0, float(carried_fine or 0.0)) + overdue_fine, 2)

                returned_text = now.strftime("%Y-%m-%d %H:%M")
                self.conn.execute("""
                    UPDATE circulation_logs
                    SET return_date = ?,
                        fine_amount = ?,
                        status = 'RETURNED',
                        fine_settled = CASE WHEN ? > 0 THEN 0 ELSE COALESCE(fine_settled, 0) END,
                        fine_settled_at = CASE WHEN ? > 0 THEN NULL ELSE fine_settled_at END,
                        fine_settlement_action = CASE WHEN ? > 0 THEN NULL ELSE fine_settlement_action END,
                        fine_settlement_note = CASE WHEN ? > 0 THEN NULL ELSE fine_settlement_note END
                    WHERE id = ? AND status = 'ISSUED'
                """, (returned_text, fine, fine, fine, fine, fine, log_id))
                self.conn.execute("""
                    UPDATE books SET available_copies = MIN(total_copies, available_copies + 1)
                    WHERE id = ?
                """, (bid,))
                details = self.conn.execute("""
                    SELECT u.email, u.full_name, b.title
                    FROM users u
                    JOIN books b ON b.id = ?
                    WHERE u.id = ?
                """, (bid, uid)).fetchone()
                if details and details[0]:
                    email, full_name, title = details
                    fine_status = (
                        f"A fine of {fine:.2f} is due."
                        if fine > 0
                        else "No fine is due."
                    )
                    self._enqueue_email_in_transaction(
                        email,
                        f"Book returned: {title}",
                        (
                            f"Hello {full_name},\n\n"
                            f"Book '{title}' (Book ID: {bid}, Transaction ID: {log_code}) was "
                            f"returned on {returned_text}. {fine_status}\n\n"
                            "Library"
                        ),
                        "RETURN",
                        dedupe_key=f"return:{log_code}",
                    )
            return True, fine, f"Book returned successfully. Transaction ID: {log_code}"
        except Exception as exc:
            return False, 0.0, self._parse_db_error(exc, "book return")

    def get_logs(self):
        try:
            rows = self.conn.execute(f"""
                SELECT {self._LOG_CODE_SQL}, book_id, user_id, checkout_date, due_date,
                       return_date, fine_amount, status
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
                self.conn.execute("DELETE FROM fine_payments")
                self.conn.execute("DELETE FROM sqlite_sequence WHERE name = 'fine_payments'")
                self.conn.execute("DELETE FROM renewal_logs")
                self.conn.execute("DELETE FROM sqlite_sequence WHERE name = 'renewal_logs'")
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
                    (SELECT COUNT(DISTINCT title) FROM books),
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
                        WHERE fine_amount > 0
                          AND COALESCE(fine_settled, 0) = 0
                          AND UPPER(COALESCE(status, '')) != 'PAID')
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

        pk = self._resolve_loan_pk(loan_id)
        if pk is None:
            raise ValueError("Invalid transaction ID.")

        sent_at = sent_at or datetime.datetime.now().isoformat(timespec="seconds")
        with self._transaction(immediate=True):
            self.conn.execute("""
                INSERT OR IGNORE INTO email_notifications(
                    loan_id, reminder_type, sent_at
                )
                VALUES (?, ?, ?)
            """, (pk, reminder_type, sent_at))
        return True

    _ID_TOKEN_PATTERN = re.compile(
        r"(?<![A-Za-z0-9-])([A-Za-z0-9][A-Za-z0-9_-]{3,40})(?![A-Za-z0-9-])"
    )

    def get_registered_user_emails(self):
        rows = self.conn.execute("""
            SELECT id, COALESCE(full_name, ''), LOWER(TRIM(email))
            FROM users
            WHERE COALESCE(TRIM(email), '') != ''
        """).fetchall()
        mapping = {}
        for uid, full_name, email in rows:
            mapping.setdefault(email, []).append((uid, full_name, email))
        return mapping

    def find_user_for_inbound_email(
        self,
        sender_email,
        subject="",
        body="",
        sender_name="",
    ):
        clean_email = self._clean(sender_email).casefold()
        clean_name = self._clean(sender_name)
        combined_text = f"{subject or ''}\n{body or ''}"

        # 1. Exact registered email lookup
        if clean_email:
            matches = self.conn.execute("""
                SELECT id, COALESCE(full_name, ''), COALESCE(email, '')
                FROM users
                WHERE LOWER(TRIM(COALESCE(email, ''))) = ?
            """, (clean_email,)).fetchall()
            if len(matches) == 1:
                uid, full_name, user_email = matches[0]
                return uid, full_name, user_email or clean_email, "Registered email"
            if len(matches) > 1:
                lowered_text = combined_text.casefold()
                narrowed = [
                    m for m in matches
                    if str(m[0] or "").casefold() in lowered_text
                ]
                if len(narrowed) == 1:
                    uid, full_name, user_email = narrowed[0]
                    return uid, full_name, user_email or clean_email, "Email + Roll No"

        # 2. Match a Roll No / PIN / User ID mentioned inside the subject or body
        tokens = {
            tok.upper()
            for tok in self._ID_TOKEN_PATTERN.findall(combined_text)
        }
        if tokens:
            rows = self.conn.execute("""
                SELECT id, COALESCE(full_name, ''), COALESCE(email, '')
                FROM users
            """).fetchall()
            id_matches = [
                row for row in rows
                if str(row[0] or "").strip().upper() in tokens
            ]
            if len(id_matches) == 1:
                uid, full_name, user_email = id_matches[0]
                return (
                    uid,
                    full_name,
                    user_email or clean_email,
                    "Roll No / ID in message",
                )

        return None, clean_name, clean_email, "External email sender"

    def get_complaint_import_map(self):
        mapping = {}
        for msg_key, action, complaint_id in self.conn.execute("""
            SELECT message_key, action, complaint_id
            FROM complaint_email_imports
        """).fetchall():
            if msg_key:
                mapping[str(msg_key)] = (str(action), complaint_id)
        for msg_key, cid in self.conn.execute("""
            SELECT email_message_id, id
            FROM complaints
            WHERE email_message_id IS NOT NULL
        """).fetchall():
            if msg_key and str(msg_key) not in mapping:
                mapping[str(msg_key)] = ("IMPORTED", cid)
        return mapping

    def mark_email_complaint_ignored(
        self,
        message_key,
        sender_email="",
        subject="",
    ):
        key = self._clean(message_key)
        if not key:
            return False
        now_text = datetime.datetime.now().isoformat(timespec="seconds")
        with self._transaction(immediate=True):
            existing = self.conn.execute(
                "SELECT action FROM complaint_email_imports WHERE message_key = ?",
                (key,),
            ).fetchone()
            if existing and existing[0] == "IMPORTED":
                return False
            self.conn.execute("""
                INSERT INTO complaint_email_imports(
                    message_key, sender_email, subject, action, complaint_id, processed_at
                )
                VALUES (?, ?, ?, 'IGNORED', NULL, ?)
                ON CONFLICT(message_key) DO UPDATE SET
                    sender_email = excluded.sender_email,
                    subject = excluded.subject,
                    action = 'IGNORED',
                    complaint_id = NULL,
                    processed_at = excluded.processed_at
            """, (
                key,
                self._clean(sender_email).casefold(),
                self._clean(subject)[:200],
                now_text,
            ))
        return True

    def create_complaint(
        self,
        user_id,
        subject,
        body,
        source="DESK",
        reporter_name=None,
        reporter_email=None,
        email_message_id=None,
        created_at=None,
        staff_notes=None,
    ):
        uid = self._clean(user_id) or None
        subject = self._clean(subject)
        body = str(body or "").strip()
        if not subject or not body:
            return False, "Complaint subject and details are required."

        normalized_source = (
            "EMAIL" if self._clean(source).upper() == "EMAIL" else "DESK"
        )
        rep_name = self._clean(reporter_name) or None
        rep_email = self._clean(reporter_email).casefold() or None
        msg_key = self._clean(email_message_id) or None
        notes = self._clean(staff_notes) or None
        now_text = datetime.datetime.now().isoformat(timespec="seconds")
        created_text = self._clean(created_at) or now_text

        try:
            with self._transaction():
                cursor = self.conn.execute("""
                    INSERT INTO complaints(
                        user_id, subject, body, status, created_at, updated_at,
                        source, reporter_name, reporter_email, email_message_id, staff_notes
                    )
                    VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?)
                """, (
                    uid,
                    subject,
                    body,
                    created_text,
                    now_text,
                    normalized_source,
                    rep_name,
                    rep_email,
                    msg_key,
                    notes,
                ))
                complaint_id = cursor.lastrowid
                row = self.conn.execute("""
                    SELECT c.id, c.user_id,
                        COALESCE(NULLIF(u.full_name, ''), NULLIF(c.reporter_name, ''), ''),
                        COALESCE(NULLIF(u.email, ''), NULLIF(c.reporter_email, ''), ''),
                        c.subject, c.body, c.created_at
                    FROM complaints c
                    LEFT JOIN users u ON u.id = c.user_id
                    WHERE c.id = ?
                """, (complaint_id,)).fetchone()
            return True, row
        except Exception as exc:
            logging.exception("Could not create library complaint")
            return False, str(exc)

    def import_emailed_complaint(
        self,
        message_key,
        sender_email,
        sender_name,
        subject,
        body,
        user_id=None,
        received_at=None,
        allow_if_ignored=False,
    ):
        key = self._clean(message_key)
        clean_sender_email = self._clean(sender_email).casefold()
        clean_sender_name = self._clean(sender_name)
        clean_subject = self._clean(subject)[:160] or "(No Subject)"
        clean_body = str(body or "").strip() or "(Empty email body)"
        if not key:
            return False, "Missing email message key.", None

        resolved_uid = self._clean(user_id) or None
        if resolved_uid is None:
            resolved_uid, matched_name, matched_email, _ = (
                self.find_user_for_inbound_email(
                    clean_sender_email,
                    clean_subject,
                    clean_body,
                    clean_sender_name,
                )
            )
            if not clean_sender_name and matched_name:
                clean_sender_name = matched_name
            if not clean_sender_email and matched_email:
                clean_sender_email = matched_email

        now_text = datetime.datetime.now().isoformat(timespec="seconds")
        created_text = self._clean(received_at) or now_text

        try:
            with self._transaction(immediate=True):
                imp = self.conn.execute(
                    "SELECT action, complaint_id FROM complaint_email_imports WHERE message_key = ?",
                    (key,),
                ).fetchone()
                if imp:
                    if imp[0] == "IMPORTED":
                        return False, "ALREADY_IMPORTED", None
                    if imp[0] == "IGNORED" and not allow_if_ignored:
                        return False, "IGNORED", None

                existing_complaint = self.conn.execute(
                    "SELECT id FROM complaints WHERE email_message_id = ?",
                    (key,),
                ).fetchone()
                if existing_complaint:
                    self.conn.execute("""
                        INSERT INTO complaint_email_imports(
                            message_key, sender_email, subject, action, complaint_id, processed_at
                        )
                        VALUES (?, ?, ?, 'IMPORTED', ?, ?)
                        ON CONFLICT(message_key) DO UPDATE SET
                            action = 'IMPORTED',
                            complaint_id = excluded.complaint_id,
                            processed_at = excluded.processed_at
                    """, (key, clean_sender_email, clean_subject, existing_complaint[0], now_text))
                    return False, "ALREADY_IMPORTED", None

                cursor = self.conn.execute("""
                    INSERT INTO complaints(
                        user_id, subject, body, status, created_at, updated_at,
                        source, reporter_name, reporter_email, email_message_id
                    )
                    VALUES (?, ?, ?, 'OPEN', ?, ?, 'EMAIL', ?, ?, ?)
                """, (
                    resolved_uid,
                    clean_subject,
                    clean_body,
                    created_text,
                    now_text,
                    clean_sender_name or None,
                    clean_sender_email or None,
                    key,
                ))
                complaint_id = cursor.lastrowid
                self.conn.execute("""
                    INSERT INTO complaint_email_imports(
                        message_key, sender_email, subject, action, complaint_id, processed_at
                    )
                    VALUES (?, ?, ?, 'IMPORTED', ?, ?)
                    ON CONFLICT(message_key) DO UPDATE SET
                        sender_email = excluded.sender_email,
                        subject = excluded.subject,
                        action = 'IMPORTED',
                        complaint_id = excluded.complaint_id,
                        processed_at = excluded.processed_at
                """, (key, clean_sender_email, clean_subject, complaint_id, now_text))

                row = self.conn.execute("""
                    SELECT c.id, c.user_id,
                        COALESCE(NULLIF(u.full_name, ''), NULLIF(c.reporter_name, ''), ''),
                        COALESCE(NULLIF(u.email, ''), NULLIF(c.reporter_email, ''), ''),
                        c.subject, c.body, c.created_at
                    FROM complaints c
                    LEFT JOIN users u ON u.id = c.user_id
                    WHERE c.id = ?
                """, (complaint_id,)).fetchone()
            return True, "IMPORTED", row
        except Exception as exc:
            logging.exception("Could not import emailed complaint")
            return False, str(exc), None

    def get_complaints(self, status=None):
        try:
            query = """
                SELECT c.id, c.user_id,
                    COALESCE(NULLIF(u.full_name, ''), NULLIF(c.reporter_name, ''), ''),
                    COALESCE(NULLIF(u.email, ''), NULLIF(c.reporter_email, ''), ''),
                    c.subject, c.body, c.status,
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

    def get_complaints_detailed(self, status=None, source=None, search=None):
        try:
            query = """
                SELECT c.id, c.user_id,
                    COALESCE(NULLIF(u.full_name, ''), NULLIF(c.reporter_name, ''), ''),
                    COALESCE(NULLIF(u.email, ''), NULLIF(c.reporter_email, ''), ''),
                    c.subject, c.body, c.status,
                    c.created_at, c.updated_at,
                    COALESCE(NULLIF(c.source, ''), 'DESK'),
                    COALESCE(c.reporter_name, ''),
                    COALESCE(c.reporter_email, ''),
                    COALESCE(c.email_message_id, ''),
                    COALESCE(c.staff_notes, '')
                FROM complaints c
                LEFT JOIN users u ON u.id = c.user_id
            """
            clauses = []
            params = []
            if status and status != "ALL":
                clauses.append("UPPER(COALESCE(c.status, 'OPEN')) = ?")
                params.append(self._clean(status).upper())
            if source and source != "ALL":
                clauses.append("UPPER(COALESCE(NULLIF(c.source, ''), 'DESK')) = ?")
                params.append(self._clean(source).upper())
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY c.created_at DESC, c.id DESC"
            rows = self.conn.execute(query, params).fetchall()

            search_key = self._clean(search).casefold()
            detailed = []
            for row in rows:
                entry = {
                    "id": int(row[0]),
                    "user_id": row[1] or "",
                    "full_name": row[2] or "",
                    "email": row[3] or "",
                    "subject": row[4] or "",
                    "body": row[5] or "",
                    "status": str(row[6] or "OPEN").upper(),
                    "created_at": row[7] or "",
                    "updated_at": row[8] or "",
                    "source": str(row[9] or "DESK").upper(),
                    "reporter_name": row[10] or "",
                    "reporter_email": row[11] or "",
                    "email_message_id": row[12] or "",
                    "staff_notes": row[13] or "",
                }
                if search_key:
                    haystack = " ".join(
                        str(entry.get(k) or "")
                        for k in (
                            "id",
                            "user_id",
                            "full_name",
                            "email",
                            "subject",
                            "body",
                            "staff_notes",
                        )
                    ).casefold()
                    if search_key not in haystack:
                        continue
                detailed.append(entry)
            return detailed
        except sqlite3.Error:
            logging.exception("Could not fetch detailed library complaints")
            raise

    def get_complaint_counts(self):
        counts = {
            "total": 0,
            "open": 0,
            "in_progress": 0,
            "resolved": 0,
            "unresolved": 0,
            "email": 0,
            "desk": 0,
        }
        try:
            for status, source in self.conn.execute("""
                SELECT UPPER(COALESCE(status, 'OPEN')),
                       UPPER(COALESCE(NULLIF(source, ''), 'DESK'))
                FROM complaints
            """).fetchall():
                counts["total"] += 1
                if status == "RESOLVED":
                    counts["resolved"] += 1
                elif status == "IN_PROGRESS":
                    counts["in_progress"] += 1
                    counts["unresolved"] += 1
                else:
                    counts["open"] += 1
                    counts["unresolved"] += 1
                if source == "EMAIL":
                    counts["email"] += 1
                else:
                    counts["desk"] += 1
        except sqlite3.Error:
            logging.exception("Could not summarize complaint counts")
        return counts

    def update_complaint_status(self, complaint_id, status, staff_notes=None):
        normalized_status = self._clean(status).upper()
        if normalized_status not in ("OPEN", "IN_PROGRESS", "RESOLVED"):
            return False, "Invalid complaint status."

        try:
            now_text = datetime.datetime.now().isoformat(timespec="seconds")
            with self._transaction():
                if staff_notes is None:
                    cursor = self.conn.execute("""
                        UPDATE complaints
                        SET status = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        normalized_status,
                        now_text,
                        int(complaint_id),
                    ))
                else:
                    cursor = self.conn.execute("""
                        UPDATE complaints
                        SET status = ?, staff_notes = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        normalized_status,
                        self._clean(staff_notes) or None,
                        now_text,
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
            FROM circulation_logs
            WHERE fine_amount > 0
              AND COALESCE(fine_settled, 0) = 0
              AND UPPER(COALESCE(status, '')) != 'PAID'
            ORDER BY fine_amount DESC
        """)

    def get_pending_fines_detailed(self):
        return self._report_query(f"""
            SELECT {self._C_LOG_CODE_SQL},
                   c.user_id,
                   COALESCE(u.full_name, 'Unknown User'),
                   c.book_id,
                   COALESCE(b.title, 'Unknown Book'),
                   COALESCE(c.fine_amount, 0),
                   UPPER(COALESCE(c.status, 'ISSUED')),
                   COALESCE(c.due_date, ''),
                   COALESCE(c.return_date, ''),
                   COALESCE(c.renewal_count, 0)
            FROM circulation_logs c
            LEFT JOIN users u ON u.id = c.user_id
            LEFT JOIN books b ON b.id = c.book_id
            WHERE c.fine_amount > 0
              AND COALESCE(c.fine_settled, 0) = 0
              AND UPPER(COALESCE(c.status, '')) != 'PAID'
            ORDER BY c.fine_amount DESC, c.id DESC
        """)

    def get_loan_fine_settlement_meta(self, log_ids=None):
        try:
            matched = self._query_loan_columns_by_refs(
                """
                COALESCE(fine_settled, 0),
                COALESCE(fine_settlement_action, ''),
                COALESCE(fine_settled_at, ''),
                COALESCE(fine_settlement_note, '')
                """,
                log_ids=log_ids,
            )
            return {
                key: (
                    int(vals[0] or 0),
                    str(vals[1] or ""),
                    str(vals[2] or ""),
                    str(vals[3] or ""),
                )
                for key, vals in matched
            }
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Could not fetch fine settlement metadata")
            return {}

    def get_user_pending_fines_total(self, user_id):
        try:
            row = self.conn.execute("""
                SELECT COALESCE(SUM(fine_amount), 0)
                FROM circulation_logs
                WHERE user_id = ?
                  AND fine_amount > 0
                  AND COALESCE(fine_settled, 0) = 0
                  AND UPPER(COALESCE(status, '')) != 'PAID'
            """, (self._clean(user_id),)).fetchone()
            return round(float(row[0] or 0.0), 2) if row else 0.0
        except sqlite3.Error:
            logging.exception("Could not fetch user pending fines total")
            return 0.0

    def settle_loan_fine(self, loan_id, action="PAID", note=""):
        kind, _ = self._parse_loan_ref(loan_id)
        if kind is None:
            return False, "Invalid transaction ID."
        lid = self._resolve_loan_pk(loan_id)
        if lid is None:
            return False, f"Transaction {format_log_id_display(loan_id)} was not found."

        action_key = self._clean(action or "PAID").upper()
        if action_key not in ("PAID", "WAIVED"):
            return False, f"Unsupported fine settlement action '{action_key}'."

        clean_note = self._clean(note)[:300]
        now_text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            with self._transaction(immediate=True):
                row = self.conn.execute(f"""
                    SELECT id, {self._LOG_CODE_SQL}, book_id, user_id, COALESCE(fine_amount, 0),
                           COALESCE(fine_settled, 0), UPPER(COALESCE(status, ''))
                    FROM circulation_logs
                    WHERE id = ?
                """, (lid,)).fetchone()
                if not row:
                    return False, f"Transaction {format_log_id_display(loan_id)} was not found."

                display_id = str(row[1] or lid)
                label = format_log_id_display(display_id)
                amount = round(float(row[4] or 0.0), 2)
                already_settled = int(row[5] or 0) == 1 or row[6] == "PAID"
                if amount <= 0:
                    return False, f"Transaction {label} has no recorded fine balance."
                if already_settled:
                    return False, f"Transaction {label} fine has already been settled."

                self.conn.execute("""
                    UPDATE circulation_logs
                    SET fine_settled = 1,
                        fine_settled_at = ?,
                        fine_settlement_action = ?,
                        fine_settlement_note = ?
                    WHERE id = ?
                """, (now_text, action_key, clean_note, lid))

                self.conn.execute("""
                    INSERT INTO fine_payments(
                        loan_id, book_id, user_id, amount, action, note, settled_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (lid, row[2], row[3], amount, action_key, clean_note, now_text))

            verb = "collected" if action_key == "PAID" else "waived"
            return True, f"Fine of ₹{amount:.2f} marked as {verb} for transaction {label}."
        except Exception as exc:
            return False, self._parse_db_error(exc, "fine settlement")

    def settle_all_user_fines(self, user_id, action="PAID", note=""):
        uid = self._clean(user_id)
        if not uid:
            return False, "User ID is required."

        action_key = self._clean(action or "PAID").upper()
        if action_key not in ("PAID", "WAIVED"):
            return False, f"Unsupported fine settlement action '{action_key}'."

        clean_note = self._clean(note)[:300]
        now_text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            with self._transaction(immediate=True):
                rows = self.conn.execute("""
                    SELECT id, book_id, user_id, COALESCE(fine_amount, 0)
                    FROM circulation_logs
                    WHERE user_id = ?
                      AND fine_amount > 0
                      AND COALESCE(fine_settled, 0) = 0
                      AND UPPER(COALESCE(status, '')) != 'PAID'
                    ORDER BY id
                """, (uid,)).fetchall()
                if not rows:
                    return False, f"No unpaid fines found for user '{uid}'."

                total = 0.0
                for lid, bid, row_uid, amount in rows:
                    amt = round(float(amount or 0.0), 2)
                    total += amt
                    self.conn.execute("""
                        UPDATE circulation_logs
                        SET fine_settled = 1,
                            fine_settled_at = ?,
                            fine_settlement_action = ?,
                            fine_settlement_note = ?
                        WHERE id = ?
                    """, (now_text, action_key, clean_note, lid))
                    self.conn.execute("""
                        INSERT INTO fine_payments(
                            loan_id, book_id, user_id, amount, action, note, settled_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (lid, bid, row_uid, amt, action_key, clean_note, now_text))

            verb = "collected" if action_key == "PAID" else "waived"
            return True, f"{len(rows)} fine(s) totaling ₹{total:.2f} marked as {verb} for {uid}."
        except Exception as exc:
            return False, self._parse_db_error(exc, "bulk fine settlement")

    def get_fine_payment_history(self, loan_id=None, limit=200):
        try:
            limit = max(1, min(int(limit), 1000))
            if loan_id is not None:
                pk = self._resolve_loan_pk(loan_id)
                if pk is None:
                    return []
                rows = self.conn.execute("""
                    SELECT f.id,
                           COALESCE(NULLIF(c.log_code, ''), CAST(f.loan_id AS TEXT)),
                           f.book_id, f.user_id, f.amount, f.action, COALESCE(f.note, ''), f.settled_at
                    FROM fine_payments f
                    LEFT JOIN circulation_logs c ON c.id = f.loan_id
                    WHERE f.loan_id = ?
                    ORDER BY f.id DESC LIMIT ?
                """, (pk, limit)).fetchall()
            else:
                rows = self.conn.execute("""
                    SELECT f.id,
                           COALESCE(NULLIF(c.log_code, ''), CAST(f.loan_id AS TEXT)),
                           f.book_id, f.user_id, f.amount, f.action, COALESCE(f.note, ''), f.settled_at
                    FROM fine_payments f
                    LEFT JOIN circulation_logs c ON c.id = f.loan_id
                    ORDER BY f.id DESC LIMIT ?
                """, (limit,)).fetchall()
            return [
                {
                    "id": int(r[0]),
                    "loan_id": str(r[1] or ""),
                    "book_id": str(r[2] or ""),
                    "user_id": str(r[3] or ""),
                    "amount": round(float(r[4] or 0.0), 2),
                    "action": str(r[5] or ""),
                    "note": str(r[6] or ""),
                    "settled_at": str(r[7] or ""),
                }
                for r in rows
            ]
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Could not fetch fine payment history")
            return []

    def get_fines_financial_summary(self, start_date=None, end_date=None):
        summary = {
            "pending_fines": 0.0,
            "settled_paid": 0.0,
            "collected_on_renewal": 0.0,
            "waived_total": 0.0,
            "total_collected": 0.0,
            "daily_collections": {},
        }
        try:
            pending_row = self.conn.execute("""
                SELECT COALESCE(SUM(fine_amount), 0)
                FROM circulation_logs
                WHERE fine_amount > 0
                  AND COALESCE(fine_settled, 0) = 0
                  AND UPPER(COALESCE(status, '')) != 'PAID'
            """).fetchone()
            summary["pending_fines"] = round(float(pending_row[0] or 0.0), 2) if pending_row else 0.0

            params = []
            where = ""
            if start_date and end_date:
                where = "WHERE substr(settled_at, 1, 10) BETWEEN ? AND ?"
                params = [str(start_date)[:10], str(end_date)[:10]]

            rows = self.conn.execute(f"""
                SELECT action, COALESCE(amount, 0), substr(settled_at, 1, 10)
                FROM fine_payments
                {where}
            """, params).fetchall()
            daily = {}
            for action, amount, day in rows:
                amt = round(float(amount or 0.0), 2)
                act = str(action or "").upper()
                if act == "PAID":
                    summary["settled_paid"] = round(summary["settled_paid"] + amt, 2)
                    if day:
                        daily[day] = round(daily.get(day, 0.0) + amt, 2)
                elif act == "COLLECTED":
                    summary["collected_on_renewal"] = round(
                        summary["collected_on_renewal"] + amt, 2
                    )
                    if day:
                        daily[day] = round(daily.get(day, 0.0) + amt, 2)
                elif act == "WAIVED":
                    summary["waived_total"] = round(summary["waived_total"] + amt, 2)

            summary["total_collected"] = round(
                summary["settled_paid"] + summary["collected_on_renewal"], 2
            )
            summary["daily_collections"] = daily
            return summary
        except sqlite3.Error:
            logging.exception("Could not fetch fines financial summary")
            return summary

    def get_renewal_analytics(self, start_date=None, end_date=None):
        analytics = {
            "total_renewals": 0,
            "total_extended_days": 0,
            "unique_loans_renewed": 0,
            "daily_renewals": {},
        }
        try:
            params = []
            where = ""
            if start_date and end_date:
                where = "WHERE substr(renewed_at, 1, 10) BETWEEN ? AND ?"
                params = [str(start_date)[:10], str(end_date)[:10]]

            rows = self.conn.execute(f"""
                SELECT loan_id, COALESCE(extended_days, 0), substr(renewed_at, 1, 10)
                FROM renewal_logs
                {where}
                ORDER BY renewed_at ASC
            """, params).fetchall()

            unique_loans = set()
            daily = {}
            total_days = 0
            for loan_id, ext_days, day in rows:
                unique_loans.add(int(loan_id))
                total_days += max(0, int(ext_days or 0))
                if day:
                    daily[day] = daily.get(day, 0) + 1

            analytics["total_renewals"] = len(rows)
            analytics["total_extended_days"] = total_days
            analytics["unique_loans_renewed"] = len(unique_loans)
            analytics["daily_renewals"] = daily
            return analytics
        except sqlite3.Error:
            logging.exception("Could not fetch renewal analytics")
            return analytics

    def get_circulation_log_details(self, loan_id):
        lid = self._resolve_loan_pk(loan_id)
        if lid is None:
            return None

        try:
            row = self.conn.execute(f"""
                SELECT c.id,
                       {self._C_LOG_CODE_SQL},
                       c.book_id,
                       COALESCE(b.title, 'Unknown Book'),
                       COALESCE(b.author, ''),
                       c.user_id,
                       COALESCE(u.full_name, 'Unknown User'),
                       COALESCE(u.role, 'Student'),
                       COALESCE(u.department, ''),
                       COALESCE(c.checkout_date, ''),
                       COALESCE(c.due_date, ''),
                       COALESCE(c.return_date, ''),
                       COALESCE(c.fine_amount, 0),
                       UPPER(COALESCE(c.status, 'ISSUED')),
                       COALESCE(c.renewal_count, 0),
                       COALESCE(c.last_renewed_at, ''),
                       COALESCE(c.fine_settled, 0),
                       COALESCE(c.fine_settlement_action, ''),
                       COALESCE(c.fine_settled_at, ''),
                       COALESCE(c.fine_settlement_note, '')
                FROM circulation_logs c
                LEFT JOIN books b ON b.id = c.book_id
                LEFT JOIN users u ON u.id = c.user_id
                WHERE c.id = ?
            """, (lid,)).fetchone()
            if not row:
                return None

            (
                _id, display_id, book_id, book_title, book_author,
                user_id, user_name, user_role, user_department,
                checkout_date, due_date, return_date,
                fine_amount, raw_status,
                renewal_count, last_renewed_at,
                fine_settled, fine_action, fine_settled_at, fine_note,
            ) = row

            today = datetime.date.today().isoformat()
            due_text = str(due_date or "")
            if raw_status == "ISSUED" and due_text and due_text[:10] < today:
                display_status = "OVERDUE"
            elif raw_status == "ISSUED" and due_text and due_text[:10] == today:
                display_status = "DUE TODAY"
            else:
                display_status = raw_status

            return {
                "log_id": str(display_id or _id),
                "internal_id": int(_id),
                "book_id": str(book_id or ""),
                "book_title": str(book_title or "Unknown Book"),
                "book_author": str(book_author or ""),
                "user_id": str(user_id or ""),
                "user_name": str(user_name or "Unknown User"),
                "user_role": str(user_role or "Student"),
                "user_department": str(user_department or ""),
                "checkout_date": str(checkout_date or ""),
                "due_date": due_text,
                "return_date": str(return_date or ""),
                "fine_amount": round(float(fine_amount or 0.0), 2),
                "raw_status": raw_status,
                "status": display_status,
                "renewal_count": int(renewal_count or 0),
                "max_renewals": self.get_max_renewals(),
                "last_renewed_at": str(last_renewed_at or ""),
                "fine_settled": bool(int(fine_settled or 0) == 1 or raw_status == "PAID"),
                "fine_settlement_action": str(fine_action or ""),
                "fine_settled_at": str(fine_settled_at or ""),
                "fine_settlement_note": str(fine_note or ""),
                "renewal_history": self.get_renewal_history(_id),
                "fine_payment_history": self.get_fine_payment_history(_id),
            }
        except sqlite3.Error:
            logging.exception("Could not fetch circulation log details for %s", loan_id)
            return None

    def get_activity_history_entries(self, limit=5000):
        try:
            limit = max(1, min(int(limit), 10000))
            today = datetime.date.today().isoformat()
            rows = self.conn.execute(f"""
                SELECT {self._C_LOG_CODE_SQL},
                       UPPER(COALESCE(c.status, 'ISSUED')),
                       COALESCE(b.title, 'Unknown Book') || ' [ID: ' ||
                           COALESCE(c.book_id, 'N/A') || ']',
                       COALESCE(u.full_name, 'Unknown User') || ' (' ||
                           COALESCE(c.user_id, 'N/A') || ')',
                       CASE
                           WHEN UPPER(COALESCE(c.status, '')) = 'RETURNED'
                               THEN COALESCE(c.return_date, c.checkout_date, 'N/A')
                           WHEN COALESCE(c.last_renewed_at, '') != ''
                               THEN c.last_renewed_at
                           ELSE COALESCE(c.checkout_date, 'N/A')
                       END,
                       COALESCE(c.renewal_count, 0),
                       COALESCE(c.fine_amount, 0),
                       COALESCE(c.fine_settled, 0),
                       COALESCE(c.fine_settlement_action, ''),
                       COALESCE(c.book_id, ''),
                       COALESCE(c.user_id, ''),
                       COALESCE(c.due_date, '')
                FROM circulation_logs c
                LEFT JOIN books b ON c.book_id = b.id
                LEFT JOIN users u ON c.user_id = u.id
                ORDER BY c.id DESC LIMIT ?
            """, (limit,)).fetchall()

            entries = []
            for row in rows:
                (
                    lid, raw_status, book_label, user_label, ts,
                    ren_count, fine_amt, fine_settled, fine_act,
                    bid, uid, due_date,
                ) = row
                due_text = str(due_date or "")
                if raw_status == "ISSUED" and due_text and due_text[:10] < today:
                    status_label = "OVERDUE"
                elif raw_status == "ISSUED" and due_text and due_text[:10] == today:
                    status_label = "DUE TODAY"
                else:
                    status_label = raw_status

                entries.append({
                    "log_id": str(lid),
                    "raw_status": raw_status,
                    "status": status_label,
                    "book_label": str(book_label or ""),
                    "user_label": str(user_label or ""),
                    "timestamp": str(ts or ""),
                    "renewal_count": int(ren_count or 0),
                    "fine_amount": round(float(fine_amt or 0.0), 2),
                    "fine_settled": bool(int(fine_settled or 0) == 1 or raw_status == "PAID"),
                    "fine_settlement_action": str(fine_act or ""),
                    "book_id": str(bid or ""),
                    "user_id": str(uid or ""),
                    "due_date": due_text,
                })
            return True, entries
        except (sqlite3.Error, ValueError, TypeError):
            logging.exception("Could not fetch activity history entries")
            return False, []

    def _report_query(self, query, params=()):
        try:
            return True, self.conn.execute(query, params).fetchall()
        except sqlite3.Error:
            logging.exception("Could not generate report")
            return False, []

    def get_all_user_departments(self, role_filter=None):
        is_student = self._clean(role_filter).upper() == "STUDENT"
        base = self.get_departments("STUDENT" if is_student else "FACULTY")
        seen = {d.casefold(): d for d in base}
        try:
            if is_student:
                rows = self.conn.execute(
                    """
                    SELECT DISTINCT TRIM(department) FROM users
                    WHERE LOWER(COALESCE(role, '')) = 'student'
                      AND TRIM(COALESCE(department, '')) != ''
                    ORDER BY TRIM(department) COLLATE NOCASE ASC
                    """
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT DISTINCT TRIM(department) FROM users
                    WHERE TRIM(COALESCE(department, '')) != ''
                    ORDER BY TRIM(department) COLLATE NOCASE ASC
                    """
                ).fetchall()
            for (dept_name,) in rows:
                if dept_name and dept_name.casefold() not in seen:
                    seen[dept_name.casefold()] = dept_name
                    base.append(dept_name)
        except sqlite3.Error:
            pass
        return base

    # IMPORT / EXPORT
    def import_books_batch(self, books_data: list):
        """Atomically insert or merge legacy 7-column or ISBN-aware 8-column rows."""
        if not books_data:
            return True, 0
        try:
            normalized = []
            seen_ids = set()
            seen_isbns = set()
            for row in books_data:
                if len(row) not in (7, 8):
                    raise ValueError("Each book import row must contain 7 or 8 values.")
                bid, title, author, publisher, total, available, created = row[:7]
                isbn = row[7] if len(row) == 8 else None
                bid, title = self._clean(bid), self._clean(title)
                total, available = int(total), int(available)
                if not bid or not title or total < 0 or available < 0 or available > total:
                    raise ValueError(f"Invalid book import data for ID '{bid}'.")
                id_key = bid.casefold()
                if id_key in seen_ids:
                    raise ValueError(f"Duplicate book ID '{bid}' in import batch.")
                seen_ids.add(id_key)
                normalized_isbn = self._clean(isbn) or None
                if normalized_isbn:
                    isbn_key = normalized_isbn.casefold()
                    if isbn_key in seen_isbns:
                        raise ValueError(
                            f"Duplicate ISBN '{normalized_isbn}' in import batch."
                        )
                    seen_isbns.add(isbn_key)
                normalized.append((bid, title, self._clean(author), self._clean(publisher),
                                   total, available, created or datetime.date.today().isoformat(),
                                   normalized_isbn))
            with self._transaction(immediate=True):
                self.conn.executemany("""
                    INSERT INTO books(
                        id, title, author, publisher, total_copies,
                        available_copies, created_at, isbn
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        author = excluded.author,
                        publisher = excluded.publisher,
                        total_copies = books.total_copies + excluded.total_copies,
                        available_copies =
                            books.available_copies + excluded.available_copies,
                        isbn = COALESCE(excluded.isbn, books.isbn)
                """, normalized)
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
            seen_ids = set()
            seen_phones = set()
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
                if uid in seen_ids:
                    raise ValueError(f"Duplicate user ID '{uid}' in import batch.")
                seen_ids.add(uid)
                phone_key = self._clean(phone).casefold()
                if phone_key and phone_key in seen_phones:
                    raise ValueError(
                        f"Duplicate phone number '{phone}' in import batch."
                    )
                if phone_key:
                    seen_phones.add(phone_key)
                department = self._clean(dept)
                normalized.append((uid, name, self._clean(phone) or None, role,
                                   department, self._clean(email).casefold() or None,
                                   created or datetime.date.today().isoformat()))
            with self._transaction(immediate=True):
                new_user_ids = {
                    row[0]
                    for row in normalized
                    if not self.conn.execute(
                        "SELECT 1 FROM users WHERE id = ?",
                        (row[0],),
                    ).fetchone()
                }
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
                for user_id in new_user_ids:
                    user = self.conn.execute("""
                        SELECT full_name, email FROM users WHERE id = ?
                    """, (user_id,)).fetchone()
                    if user:
                        self._queue_registration_email_in_transaction(
                            user_id,
                            user[0],
                            user[1],
                        )
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

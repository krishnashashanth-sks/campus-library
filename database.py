import sqlite3
import datetime
import logging
from utils import get_appdata_db_path

class LocalDatabase:
    def __init__(self):
        self.conn = sqlite3.connect(get_appdata_db_path(), check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.create_tables()

    def _parse_db_error(self, error: Exception, context: str = "") -> str:
        """Converts raw SQLite exceptions into clear, user-friendly error messages."""
        err_msg = str(error).lower()

        # Handle UNIQUE constraint failures
        if isinstance(error, sqlite3.IntegrityError):
            if "unique constraint" in err_msg or "primary key" in err_msg:
                if "users.id" in err_msg or "users.phone_number" in err_msg:
                    return "A user with this ID or Phone Number already exists."
                if "books.id" in err_msg or "books.isbn" in err_msg:
                    return "A book with this ID or ISBN already exists."
                return "This entry already exists in the system."
            
            # Handle FOREIGN KEY constraint failures
            if "foreign key" in err_msg:
                return "The referenced User or Book record does not exist."

            if "check constraint" in err_msg:
                return "Invalid data entered. Please check your inputs."

        # Handle database locking / IO issues
        if isinstance(error, sqlite3.OperationalError):
            if "locked" in err_msg or "busy" in err_msg:
                return "The database is currently busy. Please try again in a moment."
            if "no such table" in err_msg:
                return "Database structure mismatch. Please restart the application."

        # Fallback error for unexpected issues
        logging.error(f"Database Error [{context}]: {error}")
        return f"An unexpected error occurred while processing {context}."

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                phone_number TEXT UNIQUE,
                full_name TEXT,
                role TEXT,
                department TEXT,
                created_at TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                isbn TEXT UNIQUE,
                title TEXT,
                author TEXT,
                publisher TEXT,
                total_copies INTEGER DEFAULT 1,
                available_copies INTEGER DEFAULT 1,
                created_at TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS circulation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT,
                user_id TEXT,
                checkout_date TIMESTAMP,
                due_date TIMESTAMP,
                return_date TIMESTAMP,
                fine_amount DECIMAL(10, 2) DEFAULT 0.00,
                status TEXT,
                FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM settings")
        if cursor.fetchone()[0]==0:
            self.set_setting('admin_password', 'admin123')
            self.set_setting('daily_fine', 10.00)
            self.set_setting('default_days', 14)
        self.conn.commit()

    # --- SETTINGS MANAGEMENT ---

    def get_setting(self, key, default=None):
        try:
            cursor = self.conn.cursor()
            row = cursor.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default
        except Exception:
            return default
    def set_setting(self, key, value):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, str(value)))
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            return False

    # --- USER MANAGEMENT ---

    def insert_user(self, user_id, full_name, phone_number, role, department):
        cursor = self.conn.cursor()
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            cursor.execute("""
                INSERT INTO users (id, full_name, phone_number, role, department, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, full_name, phone_number, role, department, created_at))
            self.conn.commit()
            return True, "User created successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "user registration")

    def get_users(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id, full_name, phone_number, role, department, created_at FROM users")
            return True, cursor.fetchall()
        except Exception as e:
            return False, []

    def get_user_details(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id, full_name, phone_number, role, department, created_at FROM users WHERE id=?", (user_id,))
            return True, cursor.fetchone()
        except Exception:
            return False, None

    def edit_user(self, user_id, name, phone_number, role, dept):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                UPDATE users
                SET full_name=?, phone_number=?, role=?, department=?
                WHERE id=?
            """, (name, phone_number, role, dept, user_id))
            self.conn.commit()
            return True, "User details updated successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "user update")

    def delete_user(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT id FROM circulation_logs 
                WHERE user_id = ? AND status = 'ISSUED'
            """, (user_id,))
            if cursor.fetchone():
                return False, f"Cannot delete User ID ({user_id}): They currently have active checked-out books."

            cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
            self.conn.commit()
            return True, "User has been removed successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "user deletion")

    # --- BOOK MANAGEMENT ---

    def insert_book(self, book_id, title, author, publisher, copies=1):
        cursor = self.conn.cursor()
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            cursor.execute("""
                INSERT INTO books (id, title, author, publisher, total_copies, available_copies, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (book_id, title, author, publisher, copies, copies, created_at))
            self.conn.commit()
            return True, "Book added successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "book entry")

    def get_books(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id, title, author, publisher, total_copies, available_copies, created_at FROM books")
            return True, cursor.fetchall()
        except Exception:
            return False, []

    def get_book_details(self, book_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id, title, author, publisher, total_copies, available_copies, created_at FROM books WHERE id=?", (book_id,))
            return True, cursor.fetchone()
        except Exception:
            return False, None

    def edit_book(self, book_id, title, author, publisher, total, available):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE books
                SET title=?, author=?, publisher=?, total_copies=?, available_copies=?
                WHERE id=?
            """, (title, author, publisher, total, available, book_id))
            self.conn.commit()
            return True, "Book details updated successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "book update")

    def delete_book(self, book_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT id FROM circulation_logs 
                WHERE book_id = ? AND status = 'ISSUED'
            """, (book_id,))
            if cursor.fetchone():
                return False, f"Cannot delete Book ID ({book_id}): Copies of this book are currently checked out."

            cursor.execute("DELETE FROM books WHERE id=?", (book_id,))
            self.conn.commit()
            return True, f"Successfully deleted book ({book_id})."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "book deletion")

    # --- CIRCULATION MANAGEMENT ---

    def issue_book(self, book_id, user_id, days_allowed=None):
        if days_allowed is None:
            try:
                days_allowed = int(self.get_setting("default_days", 14))
            except (ValueError, TypeError):
                days_allowed = 14
        else:
            try:
                days_allowed = int(days_allowed)
            except (ValueError, TypeError):
                days_allowed = 14

        cursor = self.conn.cursor()
        now = datetime.datetime.now()
        checkout_date = now.strftime("%Y-%m-%d %H:%M")
        due_date = (now + datetime.timedelta(days=days_allowed)).strftime("%Y-%m-%d %H:%M")

        try:
            cursor.execute("SELECT available_copies FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            if not book:
                return False, f"Book ID '{book_id}' is not registered in the system."
            if book[0] <= 0:
                return False, f"Book ID '{book_id}' has no available copies for checkout."

            cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            if not cursor.fetchone():
                return False, f"User ID '{user_id}' is not registered in the system."

            cursor.execute("""
                INSERT INTO circulation_logs (book_id, user_id, checkout_date, due_date, status)
                VALUES (?, ?, ?, ?, 'ISSUED')
            """, (book_id, user_id, checkout_date, due_date))

            cursor.execute("UPDATE books SET available_copies = available_copies - 1 WHERE id = ?", (book_id,))

            self.conn.commit()
            return True, f"Book issued successfully! Due Date: {due_date}"

        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "book issue")

    def return_book(self, book_id, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id FROM books WHERE id = ?", (book_id,))
            if not cursor.fetchone():
                return False, 0.0, f"Book ID '{book_id}' was not found in the library database."

            cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            if not cursor.fetchone():
                return False, 0.0, f"User ID '{user_id}' was not found in the library database."

            now = datetime.datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M")

            cursor.execute("""
                SELECT id, due_date FROM circulation_logs
                WHERE book_id = ? AND user_id = ? AND status = 'ISSUED'
                ORDER BY id DESC LIMIT 1
            """, (book_id, user_id))
            
            record = cursor.fetchone()
            if not record:
                return False, 0.0, f"No active issue record found matching Book ID '{book_id}' and User ID '{user_id}'."

            log_id, due_date_str = record
            fine = 0.0

            try:
                daily_fine_rate = float(self.get_setting('daily_fine', 1.00))
            except (ValueError, TypeError):
                daily_fine_rate = 1.00

            if due_date_str:
                due_date = datetime.datetime.strptime(due_date_str, "%Y-%m-%d %H:%M")
                if now > due_date:
                    overdue_days = (now - due_date).days
                    fine = max(0.0, overdue_days * daily_fine_rate)

            cursor.execute("""
                UPDATE circulation_logs 
                SET return_date = ?, fine_amount = ?, status = 'RETURNED'
                WHERE id = ?
            """, (timestamp, fine, log_id))

            cursor.execute("UPDATE books SET available_copies = available_copies + 1 WHERE id = ?", (book_id,))

            self.conn.commit()
            return True, fine, "Book returned successfully."

        except Exception as e:
            self.conn.rollback()
            return False, 0.0, self._parse_db_error(e, "book return")

    def get_logs(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    id, book_id, user_id, 
                    checkout_date, due_date, return_date, 
                    fine_amount, status
                FROM circulation_logs 
                ORDER BY id DESC
            """)
            return True, cursor.fetchall()
        except Exception:
            return False, []

    def clear_all_logs(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM circulation_logs")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='circulation_logs'")
            self.conn.commit()
            return True, "Circulation logs cleared successfully."
        except Exception as e:
            self.conn.rollback()
            return False, self._parse_db_error(e, "clearing logs")

    # --- DASHBOARD & STATS ---

    def get_user_books_status(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    b.id AS book_id,
                    b.title,
                    b.author,
                    b.publisher,
                    c.status,          
                    c.checkout_date,   
                    c.due_date,        
                    c.return_date,     
                    c.fine_amount      
                FROM circulation_logs c
                JOIN books b ON c.book_id = b.id
                WHERE c.user_id = ?
                ORDER BY c.id DESC
            """, (user_id,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error getting user books status: {e}")
            return []

    def get_dashboard_details(self):
        cursor = self.conn.cursor()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            total_students = cursor.execute("SELECT COUNT(id) FROM users").fetchone()[0] or 0
            total_books = cursor.execute("SELECT COUNT(id) FROM books").fetchone()[0] or 0
            
            today_issued_books = cursor.execute("SELECT COUNT(*) FROM circulation_logs WHERE checkout_date LIKE ?", (f"{today_str}%",)).fetchone()[0] or 0
            today_return_books = cursor.execute("SELECT COUNT(*) FROM circulation_logs WHERE status = 'RETURNED' AND return_date LIKE ?", (f"{today_str}%",)).fetchone()[0] or 0
            
            today_due_books = cursor.execute("SELECT COUNT(*) FROM circulation_logs WHERE status = 'ISSUED' AND due_date < ?", (now_str,)).fetchone()[0] or 0
            available_books = cursor.execute("SELECT SUM(available_copies) FROM books").fetchone()[0] or 0
            
            unpaid_fines = cursor.execute("SELECT SUM(fine_amount) FROM circulation_logs WHERE status = 'RETURNED' AND fine_amount > 0").fetchone()[0] or 0.0

            return (
                total_students, 
                total_books, 
                today_issued_books, 
                today_due_books, 
                today_return_books,
                available_books,
                unpaid_fines
            )

        except Exception as e:
            logging.error(f"Error fetching dashboard metrics: {e}")
            return 0, 0, 0, 0, 0, 0, 0.0
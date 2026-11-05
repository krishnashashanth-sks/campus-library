import datetime
import smtplib
import ssl
from email.message import EmailMessage

from secure_storage import read_secret


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_CREDENTIAL_TARGET = "CampusLibrary/GmailSMTP"


class LibraryEmailService:
    def __init__(self, db):
        self.db = db

    def is_configured(self):
        return bool(
            self.db.get_setting("email_sender")
            and read_secret(SMTP_CREDENTIAL_TARGET)
        )

    def send(self, recipient, subject, body):
        sender = str(self.db.get_setting("email_sender", "")).strip()
        password = read_secret(SMTP_CREDENTIAL_TARGET)
        recipient = str(recipient or "").strip()

        if not sender or not password:
            raise RuntimeError(
                "Configure the Gmail sender and app password in Settings first."
            )
        if not recipient:
            raise ValueError("The recipient email address is missing.")

        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender, password)
            server.send_message(message)

    def send_due_reminders(self, today=None):
        today = today or datetime.date.today().isoformat()
        reminders = self.db.get_due_email_reminders(today)
        sent = 0
        failures = []

        for reminder in reminders:
            (
                loan_id,
                email,
                full_name,
                book_title,
                due_date,
                reminder_type,
            ) = reminder

            if reminder_type == "due_today":
                subject = f"Library book due today: {book_title}"
                message = (
                    f"Hello {full_name},\n\n"
                    f"'{book_title}' is due today ({due_date}). "
                    "Please return it to the library today or contact "
                    "the library if you need assistance.\n\n"
                    "Library"
                )
            else:
                subject = f"Overdue library book: {book_title}"
                message = (
                    f"Hello {full_name},\n\n"
                    f"'{book_title}' was due on {due_date} and is now "
                    "overdue. Please return it to the library as soon "
                    "as possible. Contact the library if it has already "
                    "been returned.\n\n"
                    "Library"
                )

            try:
                self.send(email, subject, message)
                self.db.mark_due_email_reminder_sent(
                    loan_id,
                    reminder_type,
                    today,
                )
                sent += 1
            except Exception as error:
                failures.append(
                    f"Loan {loan_id}: {error}"
                )

        return sent, failures

    def send_complaint_receipt(self, complaint):
        staff_email = str(
            self.db.get_setting("library_contact_email", "")
        ).strip()
        if not staff_email:
            raise RuntimeError(
                "Set the library contact email in Settings to receive complaints."
            )

        (
            complaint_id,
            user_id,
            full_name,
            user_email,
            subject,
            body,
            created_at,
        ) = complaint

        self.send(
            staff_email,
            f"Library complaint #{complaint_id}: {subject}",
            (
                f"Complaint #{complaint_id}\n"
                f"From: {full_name} ({user_id})\n"
                f"Student email: {user_email or 'Not provided'}\n"
                f"Received: {created_at}\n\n"
                f"{body}"
            ),
        )

        if user_email:
            self.send(
                user_email,
                f"We received your library feedback: {subject}",
                (
                    f"Hello {full_name},\n\n"
                    "The library has received your message. "
                    f"Your reference number is {complaint_id}.\n\n"
                    "Library"
                ),
            )

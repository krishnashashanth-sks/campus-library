import datetime
import email
import hashlib
import html
import imaplib
import re
import smtplib
import ssl
import time
from email import policy
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime

from secure_storage import read_secret


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_CREDENTIAL_TARGET = "CampusLibrary/GmailSMTP"

_IMAP_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

_AUTOMATED_LOCAL_PARTS = (
    "mailer-daemon",
    "postmaster",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notifications",
    "notification",
    "bounce",
    "bounces",
)

_AUTOMATED_DOMAINS = (
    "accounts.google.com",
    "mail.accounts.google.com",
    "github.com",
)

_SELF_SUBJECT_PREFIXES = (
    "library complaint #",
    "we received your library feedback:",
    "library email configuration test",
    "library registration confirmation",
)

_AUTOMATED_SUBJECT_SNIPPETS = (
    "delivery status notification",
    "mail delivery subsystem",
    "undelivered mail returned",
    "security alert",
    "critical security alert",
)

COMPLAINT_KEYWORDS = (
    "complaint",
    "complain",
    "grievance",
    "feedback",
    "issue",
    "problem",
    "suggestion",
    "damaged",
    "torn",
    "missing book",
    "lost book",
    "wrong fine",
    "fine issue",
    "overdue",
    "renewal",
    "library card",
    "request book",
    "book request",
    "broken",
)

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_BREAK_RE = re.compile(
    r"<(?:br\s*/?|/?(?:p|div|li|tr|h[1-6]|blockquote))>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def decode_mime_header(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return raw


def _decode_bytes_payload(raw_bytes, charset=None):
    if not raw_bytes:
        return ""
    candidates = []
    if charset:
        candidates.append(str(charset).strip())
    candidates.extend(("utf-8", "cp1252", "latin-1"))
    for enc in candidates:
        try:
            return raw_bytes.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def html_to_plain_text(html_text):
    if not html_text:
        return ""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", str(html_text))
    cleaned = _BLOCK_BREAK_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    lines = [line.strip() for line in cleaned.replace("\r\n", "\n").splitlines()]
    normalized = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def extract_email_body(msg):
    plain_parts = []
    html_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get("Content-Disposition") or "").casefold()
            if "attachment" in disp:
                continue
            ctype = str(part.get_content_type() or "").casefold()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = _decode_bytes_payload(payload, part.get_content_charset())
            if ctype == "text/plain" and text.strip():
                plain_parts.append(text.strip())
            elif ctype == "text/html" and text.strip():
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            text = _decode_bytes_payload(payload, msg.get_content_charset())
            if str(msg.get_content_type() or "").casefold() == "text/html":
                html_parts.append(text)
            elif text.strip():
                plain_parts.append(text.strip())
        elif isinstance(msg.get_payload(), str) and msg.get_payload().strip():
            plain_parts.append(msg.get_payload().strip())

    if plain_parts:
        combined = "\n\n".join(plain_parts).replace("\r\n", "\n")
    elif html_parts:
        combined = "\n\n".join(html_to_plain_text(p) for p in html_parts if p)
    else:
        combined = ""
    combined = re.sub(r"\n{3,}", "\n\n", combined).strip()
    return combined[:10000]


def parse_received_timestamp(date_header):
    raw = str(date_header or "").strip()
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.isoformat(timespec="seconds")
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.datetime.now().isoformat(timespec="seconds")


def is_automated_or_loop_email(
    sender_email,
    subject,
    headers_map,
    self_sender="",
):
    sender = str(sender_email or "").strip().casefold()
    self_addr = str(self_sender or "").strip().casefold()
    subj_lower = str(subject or "").strip().casefold()
    lowered_headers = {
        str(k or "").casefold(): str(v or "").strip()
        for k, v in (headers_map or {}).items()
    }

    if self_addr and sender == self_addr:
        return True, "Sent by configured library Gmail"
    if lowered_headers.get("x-campuslibrary-generated"):
        return True, "Generated by Library Management System"

    auto_sub = lowered_headers.get("auto-submitted", "").casefold()
    if auto_sub and auto_sub != "no":
        return True, "Auto-submitted system email"
    if lowered_headers.get("x-autoreply") or lowered_headers.get("x-autorespond"):
        return True, "Automated reply email"
    precedence = lowered_headers.get("precedence", "").casefold()
    if precedence in ("bulk", "junk", "list"):
        return True, f"Bulk/mailing-list message ({precedence})"
    if lowered_headers.get("list-unsubscribe"):
        return True, "Newsletter / mailing list"

    if "@" in sender:
        local_part, domain = sender.rsplit("@", 1)
        if any(
            local_part == token or local_part.startswith(token + "+") or local_part.startswith(token + "-")
            for token in _AUTOMATED_LOCAL_PARTS
        ):
            return True, f"Automated sender ({local_part})"
        if domain in _AUTOMATED_DOMAINS:
            return True, f"System notification ({domain})"

    for prefix in _SELF_SUBJECT_PREFIXES:
        if subj_lower.startswith(prefix):
            return True, "Library app notification copy"
    for snippet in _AUTOMATED_SUBJECT_SNIPPETS:
        if snippet in subj_lower:
            return True, "System / delivery alert"

    return False, ""


def matches_complaint_filter(
    subject,
    body,
    matched_user_id=None,
    sender_is_registered=False,
    mode="keywords",
):
    mode_key = str(mode or "keywords").strip().casefold()
    if mode_key == "all":
        return True, "All non-automated inbox messages"

    if sender_is_registered:
        return True, "Registered library member email"
    if matched_user_id:
        return True, f"Matched member ID ({matched_user_id})"

    haystack = f"{subject or ''}\n{body or ''}".casefold()
    for kw in COMPLAINT_KEYWORDS:
        if kw in haystack:
            return True, f"Keyword match: '{kw}'"

    return False, "No registered member or complaint keyword match"


def parse_raw_email_message(
    raw_bytes,
    uid="",
    is_seen=False,
    self_sender="",
):
    msg = email.message_from_bytes(bytes(raw_bytes or b""), policy=policy.compat32)
    raw_from = decode_mime_header(msg.get("From", ""))
    parsed_name, parsed_email = parseaddr(raw_from)
    sender_name = decode_mime_header(parsed_name)
    sender_email = str(parsed_email or "").strip().casefold()
    subject = decode_mime_header(msg.get("Subject", "")) or "(No Subject)"
    body = extract_email_body(msg)
    received_at = parse_received_timestamp(msg.get("Date", ""))

    raw_msg_id = str(msg.get("Message-ID") or "").strip()
    if raw_msg_id:
        message_key = raw_msg_id
    else:
        digest = hashlib.sha256(
            f"{sender_email}|{subject}|{msg.get('Date', '')}|{body[:256]}".encode(
                "utf-8",
                errors="replace",
            )
        ).hexdigest()
        message_key = f"hash:{digest}"

    headers_map = {k: str(v or "") for k, v in msg.items()}
    is_auto, skip_reason = is_automated_or_loop_email(
        sender_email,
        subject,
        headers_map,
        self_sender=self_sender,
    )

    return {
        "uid": str(uid or ""),
        "message_key": message_key,
        "sender_name": sender_name or sender_email,
        "sender_email": sender_email,
        "subject": subject[:160],
        "body": body,
        "received_at": received_at,
        "is_seen": bool(is_seen),
        "is_automated": is_auto,
        "skip_reason": skip_reason,
    }


_RFC822_SIZE_RE = re.compile(rb"RFC822\.SIZE\s+(\d+)", re.IGNORECASE)
_IMAP_TRANSIENT_MARKERS = (
    "socket error",
    "socket eof",
    "eof",
    "timed out",
    "timeout",
    "connection reset",
    "broken pipe",
    "connection aborted",
    "closed unexpectedly",
    "ssl",
)
_IMAP_AUTH_MARKERS = (
    "authenticationfailed",
    "invalid credentials",
    "configure the gmail sender",
)
_MAX_FULL_BODY_BYTES = 5 * 1024 * 1024


def is_transient_imap_error(error):
    """Return True if an IMAP failure is likely a transient socket/TLS/EOF drop."""
    seen = set()
    cur = error
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        detail = str(cur or "").casefold()
        if any(marker in detail for marker in _IMAP_AUTH_MARKERS):
            return False
        if isinstance(
            cur,
            (
                imaplib.IMAP4.abort,
                ssl.SSLError,
                TimeoutError,
                EOFError,
                ConnectionError,
                OSError,
            ),
        ):
            return True
        if any(marker in detail for marker in _IMAP_TRANSIENT_MARKERS):
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False


def _close_imap_quietly(imap):
    if imap is None:
        return
    try:
        state = getattr(imap, "state", None)
        if state is None or state == "SELECTED":
            imap.close()
    except Exception:
        pass
    try:
        imap.logout()
    except Exception:
        pass
    try:
        shutdown = getattr(imap, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception:
        pass


def _extract_imap_fetch_parts(msg_data):
    """Extract flags, optional RFC822.SIZE, and joined literal payload bytes from IMAP FETCH."""
    is_seen = False
    msg_size = None
    payload_chunks = []

    for part in msg_data or ():
        if isinstance(part, tuple) and len(part) >= 2:
            meta = part[0] or b""
            if isinstance(meta, (bytes, bytearray)):
                if b"\\Seen" in meta:
                    is_seen = True
                size_match = _RFC822_SIZE_RE.search(bytes(meta))
                if size_match:
                    try:
                        msg_size = int(size_match.group(1))
                    except ValueError:
                        pass
            if isinstance(part[1], (bytes, bytearray)) and part[1]:
                payload_chunks.append(bytes(part[1]))
        elif isinstance(part, (bytes, bytearray)):
            if b"\\Seen" in part:
                is_seen = True
            size_match = _RFC822_SIZE_RE.search(bytes(part))
            if size_match and msg_size is None:
                try:
                    msg_size = int(size_match.group(1))
                except ValueError:
                    pass

    if not payload_chunks:
        raw_bytes = None
    elif len(payload_chunks) == 1:
        raw_bytes = payload_chunks[0]
    else:
        raw_bytes = b"\r\n\r\n".join(payload_chunks)
    return is_seen, msg_size, raw_bytes


def _wait_before_retry(delay_seconds, stop_event=None):
    if delay_seconds <= 0:
        return
    if stop_event is not None and hasattr(stop_event, "wait"):
        stop_event.wait(delay_seconds)
    else:
        time.sleep(delay_seconds)


class LibraryEmailService:
    def __init__(self, db):
        self.db = db

    def is_configured(self):
        return bool(
            self.db.get_setting("email_sender")
            and read_secret(SMTP_CREDENTIAL_TARGET)
        )

    def send(self, recipient, subject, body, headers=None):
        sender = str(self.db.get_setting("email_sender", "")).strip()
        password = read_secret(SMTP_CREDENTIAL_TARGET)
        recipient = str(recipient or "").strip()

        if not sender or not password:
            raise RuntimeError(
                "Configure the Gmail sender and app password in Settings first."
            )
        if not recipient:
            raise ValueError("The recipient email address is missing.")

        message = MIMEText(body, "plain", "utf-8")
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message["X-CampusLibrary-Generated"] = "1"
        if headers:
            for key, value in headers.items():
                if key and value is not None:
                    message[str(key)] = str(value)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender, password)
            server.send_message(message)

    def send_due_reminders(self, today=None):
        today = today or datetime.date.today().isoformat()
        queued = self.db.enqueue_due_email_reminders(today)
        return queued, []

    def send_complaint_receipt(
        self,
        complaint,
        require_staff_email=True,
        notify_staff=True,
    ):
        sender_email = str(
            self.db.get_setting("email_sender", "")
        ).strip().casefold()
        staff_email = str(
            self.db.get_setting("library_contact_email", "")
        ).strip()
        if require_staff_email and not staff_email:
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

        display_name = str(full_name or "").strip() or (
            str(user_email or "").strip() or "Library User"
        )
        member_tag = str(user_id or "").strip() or "External / Anonymous"

        if notify_staff and staff_email:
            should_skip_self = (
                not require_staff_email
                and sender_email
                and staff_email.casefold() == sender_email
            )
            if not should_skip_self:
                self.db.enqueue_email(
                    staff_email,
                    f"Library complaint #{complaint_id}: {subject}",
                    (
                        f"Complaint #{complaint_id}\n"
                        f"From: {display_name} ({member_tag})\n"
                        f"Email: {user_email or 'Not provided'}\n"
                        f"Received: {created_at}\n\n"
                        f"{body}"
                    ),
                    "SYSTEM_ALERT",
                    dedupe_key=f"complaint:{complaint_id}:staff",
                )

        clean_user_email = str(user_email or "").strip()
        if clean_user_email and clean_user_email.casefold() != sender_email:
            self.db.enqueue_email(
                clean_user_email,
                f"We received your library feedback: {subject}",
                (
                    f"Hello {display_name},\n\n"
                    "The library has received your complaint/feedback. "
                    f"Your reference number is #{complaint_id}.\n\n"
                    "We will review it and follow up shortly.\n\n"
                    "Library"
                ),
                "SYSTEM_ALERT",
                dedupe_key=f"complaint:{complaint_id}:user",
            )

    def _classify_parsed_message(
        self,
        parsed,
        registered_emails,
        import_map,
        filter_mode,
    ):
        matched_uid, matched_name, matched_email, match_reason = (
            self.db.find_user_for_inbound_email(
                parsed["sender_email"],
                parsed["subject"],
                parsed["body"],
                parsed["sender_name"],
            )
        )
        sender_is_reg = parsed["sender_email"] in registered_emails
        is_match, filter_reason = matches_complaint_filter(
            parsed["subject"],
            parsed["body"],
            matched_user_id=matched_uid,
            sender_is_registered=sender_is_reg,
            mode=filter_mode,
        )
        imp_info = import_map.get(parsed["message_key"])

        parsed["matched_user_id"] = matched_uid or ""
        parsed["matched_user_name"] = matched_name or ""
        parsed["matched_user_email"] = matched_email or parsed["sender_email"]
        parsed["match_reason"] = match_reason
        parsed["matches_filter"] = bool(is_match and not parsed["is_automated"])
        parsed["filter_reason"] = (
            parsed["skip_reason"] if parsed["is_automated"] else filter_reason
        )
        parsed["import_status"] = imp_info[0] if imp_info else ""
        parsed["complaint_id"] = imp_info[1] if imp_info else None
        return parsed

    def fetch_inbox_messages(
        self,
        limit=40,
        lookback_days=14,
        skip_imported_bodies=False,
        stop_event=None,
    ):
        sender = str(self.db.get_setting("email_sender", "")).strip()
        password = str(read_secret(SMTP_CREDENTIAL_TARGET) or "").strip()
        if not sender or not password:
            raise RuntimeError(
                "Configure the Gmail sender and app password in Settings first."
            )

        limit = max(1, min(int(limit or 40), 100))
        lookback_days = max(1, min(int(lookback_days or 14), 90))
        since_date = datetime.date.today() - datetime.timedelta(days=lookback_days)
        since_str = (
            f"{since_date.day:02d}-{_IMAP_MONTHS[since_date.month - 1]}-{since_date.year}"
        )

        filter_mode = str(
            self.db.get_setting("email_complaint_filter_mode", "keywords")
        ).strip().casefold()
        registered_emails = self.db.get_registered_user_emails()
        import_map = self.db.get_complaint_import_map()

        target_uids = None
        results_by_uid = {}
        uid_failures = {}
        max_attempts = 3
        retry_delays = (0.35, 0.8)
        last_transient_error = None

        for attempt in range(max_attempts):
            if stop_event is not None and stop_event.is_set():
                break

            imap = None
            current_uid = None
            try:
                ssl_context = ssl.create_default_context()
                imap = imaplib.IMAP4_SSL(
                    IMAP_HOST,
                    IMAP_PORT,
                    ssl_context=ssl_context,
                    timeout=25,
                )
                imap.login(sender, password)
                status, _ = imap.select("INBOX", readonly=True)
                if status != "OK":
                    raise RuntimeError("Unable to open the Gmail INBOX folder.")

                if target_uids is None:
                    status, data = imap.uid("search", None, "SINCE", since_str)
                    if status != "OK":
                        raise RuntimeError("Unable to search Gmail INBOX messages.")

                    uid_tokens = (
                        data[0].decode("ascii", errors="ignore").split()
                        if data and data[0]
                        else []
                    )
                    if not uid_tokens:
                        return []

                    # Fetch oldest-to-newest among the latest `limit` messages so imported IDs ascend cleanly.
                    target_uids = uid_tokens[-limit:]

                for uid_str in target_uids:
                    if uid_str in results_by_uid:
                        continue
                    if stop_event is not None and stop_event.is_set():
                        break

                    current_uid = uid_str
                    uid_bytes = uid_str.encode("ascii")
                    msg_size = None

                    if skip_imported_bodies:
                        h_status, h_data = imap.uid(
                            "fetch",
                            uid_bytes,
                            "(FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])",
                        )
                        if h_status == "OK" and h_data:
                            h_seen, msg_size, h_bytes = _extract_imap_fetch_parts(h_data)
                            if h_bytes:
                                hdr_msg = email.message_from_bytes(
                                    h_bytes,
                                    policy=policy.compat32,
                                )
                                raw_msg_id = str(hdr_msg.get("Message-ID") or "").strip()
                                if raw_msg_id and raw_msg_id in import_map:
                                    imp_info = import_map[raw_msg_id]
                                    results_by_uid[uid_str] = {
                                        "uid": uid_str,
                                        "message_key": raw_msg_id,
                                        "sender_name": "",
                                        "sender_email": "",
                                        "subject": "",
                                        "body": "",
                                        "received_at": "",
                                        "is_seen": bool(h_seen),
                                        "is_automated": False,
                                        "skip_reason": "",
                                        "matched_user_id": "",
                                        "matched_user_name": "",
                                        "matched_user_email": "",
                                        "match_reason": "",
                                        "matches_filter": False,
                                        "filter_reason": "",
                                        "import_status": imp_info[0],
                                        "complaint_id": imp_info[1],
                                    }
                                    continue

                    use_partial = (
                        uid_failures.get(uid_str, 0) > 0
                        or (msg_size is not None and msg_size > _MAX_FULL_BODY_BYTES)
                    )
                    fetch_query = (
                        "(FLAGS BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.65536>)"
                        if use_partial
                        else "(FLAGS BODY.PEEK[])"
                    )
                    f_status, msg_data = imap.uid("fetch", uid_bytes, fetch_query)
                    if f_status != "OK" or not msg_data:
                        continue

                    is_seen, _, raw_bytes = _extract_imap_fetch_parts(msg_data)
                    if not raw_bytes:
                        continue

                    parsed = parse_raw_email_message(
                        raw_bytes,
                        uid=uid_str,
                        is_seen=is_seen,
                        self_sender=sender,
                    )
                    results_by_uid[uid_str] = self._classify_parsed_message(
                        parsed,
                        registered_emails,
                        import_map,
                        filter_mode,
                    )

                last_transient_error = None
                break
            except (
                imaplib.IMAP4.error,
                ssl.SSLError,
                TimeoutError,
                EOFError,
                ConnectionError,
                OSError,
            ) as error:
                detail = str(error)
                if any(marker in detail.casefold() for marker in _IMAP_AUTH_MARKERS):
                    raise RuntimeError(
                        "Gmail IMAP authentication failed. Verify the Gmail sender, "
                        "16-character App Password, and that IMAP is enabled in Gmail."
                    ) from error

                if not is_transient_imap_error(error):
                    raise RuntimeError(f"Gmail IMAP error: {detail}") from error

                last_transient_error = error
                if current_uid is not None:
                    uid_failures[current_uid] = uid_failures.get(current_uid, 0) + 1
                    # If one single mid-batch message still drops even on partial retry, skip only that message.
                    if uid_failures[current_uid] >= 2 and results_by_uid:
                        results_by_uid[current_uid] = None
                        last_transient_error = None

                if attempt + 1 < max_attempts:
                    _close_imap_quietly(imap)
                    imap = None
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    _wait_before_retry(delay, stop_event=stop_event)
                    continue

                if "eof" in detail.casefold():
                    raise RuntimeError(
                        "Gmail IMAP connection closed unexpectedly (socket EOF). "
                        "Check internet/VPN/antivirus SSL scanning and try again."
                    ) from error
                raise RuntimeError(f"Gmail IMAP error: {detail}") from error
            finally:
                _close_imap_quietly(imap)

        if last_transient_error is not None and not results_by_uid and target_uids:
            detail = str(last_transient_error)
            if "eof" in detail.casefold():
                raise RuntimeError(
                    "Gmail IMAP connection closed unexpectedly (socket EOF). "
                    "Check internet/VPN/antivirus SSL scanning and try again."
                ) from last_transient_error
            raise RuntimeError(f"Gmail IMAP error: {detail}") from last_transient_error

        if not target_uids:
            return []

        return [
            results_by_uid[uid_str]
            for uid_str in target_uids
            if results_by_uid.get(uid_str) is not None
        ]

    def sync_emailed_complaints(
        self,
        mode=None,
        auto_reply=None,
        limit=40,
        lookback_days=14,
        stop_event=None,
    ):
        if mode is None:
            mode = str(
                self.db.get_setting("email_complaint_filter_mode", "keywords")
            ).strip().casefold()
        if auto_reply is None:
            auto_reply = str(
                self.db.get_setting("email_complaint_auto_reply", "1")
            ).casefold() in ("1", "true", "yes")

        messages = self.fetch_inbox_messages(
            limit=limit,
            lookback_days=lookback_days,
            skip_imported_bodies=True,
            stop_event=stop_event,
        )
        summary = {
            "checked": len(messages),
            "imported": 0,
            "matched_users": 0,
            "skipped_automated": 0,
            "skipped_filter": 0,
            "already_processed": 0,
            "complaints": [],
        }

        registered_emails = self.db.get_registered_user_emails()

        for msg in messages:
            if msg.get("import_status"):
                summary["already_processed"] += 1
                continue
            if msg.get("is_automated"):
                summary["skipped_automated"] += 1
                continue

            is_match, _reason = matches_complaint_filter(
                msg.get("subject", ""),
                msg.get("body", ""),
                matched_user_id=msg.get("matched_user_id") or None,
                sender_is_registered=msg.get("sender_email", "") in registered_emails,
                mode=mode,
            )
            if not is_match:
                summary["skipped_filter"] += 1
                continue

            ok, status_code, complaint_row = self.db.import_emailed_complaint(
                message_key=msg["message_key"],
                sender_email=msg["sender_email"],
                sender_name=msg["sender_name"],
                subject=msg["subject"],
                body=msg["body"],
                user_id=msg.get("matched_user_id") or None,
                received_at=msg.get("received_at"),
            )
            if not ok:
                if status_code in ("ALREADY_IMPORTED", "IGNORED"):
                    summary["already_processed"] += 1
                continue

            summary["imported"] += 1
            if complaint_row and complaint_row[1]:
                summary["matched_users"] += 1
            if complaint_row:
                summary["complaints"].append(complaint_row)
                if auto_reply:
                    self.send_complaint_receipt(
                        complaint_row,
                        require_staff_email=False,
                        notify_staff=True,
                    )

        return summary

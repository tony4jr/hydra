"""IMAP reader for recovery email verification codes.

Used during Gmail signup — Google sends a 6-digit code to the recovery
address and HYDRA polls the inbox to fetch it automatically.

Supports common Korean + international providers; the IMAP host is
auto-detected from the email domain when `imap_host` is not provided.

NOTE on app passwords:
- Gmail requires an App Password (not the account password)
- Naver requires enabling IMAP + app password in 설정 → POP3/IMAP
- Daum works with the regular password if IMAP is enabled
- Most services require IMAP to be explicitly enabled
"""

import asyncio
import email
import email.header
import imaplib
import re
import ssl
from datetime import datetime, timedelta, timezone

from hydra.core.logger import get_logger

log = get_logger("imap")

# Auto-detect IMAP host for known providers
IMAP_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "naver.com": "imap.naver.com",
    "daum.net": "imap.daum.net",
    "hanmail.net": "imap.daum.net",
    "nate.com": "imap.nate.com",
    "kakao.com": "imap.kakao.com",
    "hotmail.com": "outlook.office365.com",
    "outlook.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com",
}


def detect_imap_host(email_address: str) -> str | None:
    """Guess the IMAP server for a given email address."""
    domain = email_address.split("@")[-1].lower()
    return IMAP_HOSTS.get(domain)


def _decode_mime_header(raw: str) -> str:
    """Decode RFC 2047 encoded header (e.g. '=?UTF-8?B?...?=')."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    out = []
    for data, charset in parts:
        if isinstance(data, bytes):
            out.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(data)
    return "".join(out)


def _body_from_message(msg) -> str:
    """Extract a plain-text body from a parsed email.message.Message."""
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" or ctype == "text/html":
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="replace"))
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
        except Exception:
            pass
    return "\n".join(parts)


class ImapClient:
    """Synchronous IMAP client wrapped for asyncio via to_thread."""

    def __init__(self, email_address: str, password: str,
                 host: str | None = None, port: int = 993):
        self.email_address = email_address
        self.password = password
        self.host = host or detect_imap_host(email_address)
        if not self.host:
            raise ValueError(f"Cannot auto-detect IMAP host for {email_address}")
        self.port = port
        self._conn: imaplib.IMAP4_SSL | None = None

    def _connect(self):
        ctx = ssl.create_default_context()
        self._conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx, timeout=30)
        self._conn.login(self.email_address, self.password)
        self._conn.select("INBOX")

    def _close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def _search_recent(self, since_utc: datetime, from_contains: str = "") -> list[str]:
        """Return list of message UIDs matching the criteria."""
        date_str = since_utc.strftime("%d-%b-%Y")
        query = f'(SINCE {date_str})'
        status, data = self._conn.search(None, query)
        if status != "OK":
            return []
        uids = data[0].split() if data and data[0] else []

        matches = []
        for uid in uids:
            status, fetched = self._conn.fetch(uid, "(RFC822.HEADER)")
            if status != "OK":
                continue
            raw = fetched[0][1] if fetched and fetched[0] else b""
            if not raw:
                continue
            header = email.message_from_bytes(raw)
            sender = _decode_mime_header(header.get("From", ""))
            if from_contains and from_contains.lower() not in sender.lower():
                continue
            matches.append(uid)
        return matches

    def _fetch_body(self, uid: bytes) -> str:
        status, data = self._conn.fetch(uid, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            return ""
        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        subject = _decode_mime_header(msg.get("Subject", ""))
        body = _body_from_message(msg)
        return f"Subject: {subject}\n\n{body}"

    def test_login(self) -> tuple[bool, str]:
        """Returns (success, error_message)."""
        try:
            self._connect()
            self._close()
            return True, ""
        except Exception as e:
            self._close()
            return False, str(e)

    def fetch_code(self, from_contains: str = "google",
                   timeout_sec: int = 180, poll_interval: int = 5,
                   since_minutes: int = 10) -> str | None:
        """Poll inbox until a matching message with a 6-digit code arrives."""
        try:
            self._connect()
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            elapsed = 0
            while elapsed < timeout_sec:
                try:
                    uids = self._search_recent(since, from_contains)
                    # Check newest first
                    for uid in reversed(uids):
                        body = self._fetch_body(uid)
                        m = re.search(r"\b(\d{6})\b", body)
                        if m:
                            return m.group(1)
                except Exception as e:
                    log.warning(f"IMAP search error: {e}")
                import time
                time.sleep(poll_interval)
                elapsed += poll_interval
            return None
        finally:
            self._close()


async def fetch_verification_code(email_address: str, password: str,
                                   host: str | None = None, port: int = 993,
                                   from_contains: str = "google",
                                   timeout_sec: int = 180) -> str | None:
    """Async wrapper — poll inbox for a Google verification code."""
    def _sync():
        client = ImapClient(email_address, password, host, port)
        return client.fetch_code(from_contains=from_contains, timeout_sec=timeout_sec)
    return await asyncio.to_thread(_sync)


async def test_imap_login(email_address: str, password: str,
                           host: str | None = None, port: int = 993) -> tuple[bool, str]:
    """Async wrapper for quick credential test."""
    def _sync():
        client = ImapClient(email_address, password, host, port)
        return client.test_login()
    return await asyncio.to_thread(_sync)

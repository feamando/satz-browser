from __future__ import annotations

import datetime
import email
import email.header
import email.policy
import email.utils
import hashlib
import html as html_lib
import imaplib
import json
import os
import poplib
import re
import smtplib
import sqlite3
import ssl
import threading
import time
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable


MAIL_PRESETS: dict[str, dict[str, Any]] = {
    "gmail": {
        "id": "gmail",
        "label": "Gmail",
        "protocol": "imap",
        "in_host": "imap.gmail.com",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "outlook": {
        "id": "outlook",
        "label": "Outlook / Hotmail",
        "protocol": "imap",
        "in_host": "outlook.office365.com",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "icloud": {
        "id": "icloud",
        "label": "iCloud",
        "protocol": "imap",
        "in_host": "imap.mail.me.com",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "gmx": {
        "id": "gmx",
        "label": "GMX",
        "protocol": "imap",
        "in_host": "imap.gmx.net",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "mail.gmx.net",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "webde": {
        "id": "webde",
        "label": "WEB.DE",
        "protocol": "imap",
        "in_host": "imap.web.de",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "smtp.web.de",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "custom_imap": {
        "id": "custom_imap",
        "label": "Custom IMAP",
        "protocol": "imap",
        "in_host": "",
        "in_port": 993,
        "in_security": "ssl",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
    "custom_pop3": {
        "id": "custom_pop3",
        "label": "Custom POP3",
        "protocol": "pop3",
        "in_host": "",
        "in_port": 995,
        "in_security": "ssl",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
}


def decode_mime_header(raw_val: str | None) -> str:
    if not raw_val:
        return ""
    try:
        parts = email.header.decode_header(str(raw_val))
        decoded: list[str] = []
        for chunk, enc in parts:
            if isinstance(chunk, bytes):
                decoded.append(chunk.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(str(chunk))
        return "".join(decoded).strip()
    except Exception:
        return str(raw_val).strip()


def parse_address_list(raw_val: str | list[str] | None) -> list[dict[str, str]]:
    if not raw_val:
        return []
    values = [raw_val] if isinstance(raw_val, str) else [str(x) for x in raw_val if x]
    pairs = email.utils.getaddresses(values)
    out: list[dict[str, str]] = []
    for name, addr in pairs:
        clean_addr = (addr or "").strip().lower()
        clean_name = decode_mime_header(name)
        if clean_addr or clean_name:
            out.append({"name": clean_name, "email": clean_addr})
    return out


def normalize_subject_for_thread(subject: str) -> str:
    s = (subject or "").strip()
    while True:
        next_s = re.sub(r"^\s*(?:re|fwd|fw|aw|wg)\s*(?:\[\d+\])?\s*:\s*", "", s, flags=re.IGNORECASE)
        if next_s == s:
            break
        s = next_s
    return re.sub(r"\s+", " ", s).strip().lower()


def compute_thread_id(
    message_id: str,
    in_reply_to: str,
    references: str,
    subject: str,
    from_addr: str,
    to_addrs: list[dict[str, str]],
) -> str:
    refs = [r.strip() for r in re.findall(r"<[^>]+>", references or "") if r.strip()]
    if refs:
        root_ref = refs[0]
        return "thr-" + hashlib.sha1(root_ref.encode("utf-8")).hexdigest()[:16]
    if in_reply_to:
        irt_match = re.search(r"<[^>]+>", in_reply_to)
        root_irt = irt_match.group(0) if irt_match else in_reply_to.strip()
        if root_irt:
            return "thr-" + hashlib.sha1(root_irt.encode("utf-8")).hexdigest()[:16]
    norm_subj = normalize_subject_for_thread(subject)
    if norm_subj:
        participants = sorted(
            {from_addr.lower().strip()}
            | {str(a.get("email") or "").lower().strip() for a in (to_addrs or []) if a.get("email")}
        )
        key = f"{norm_subj}|{'/'.join(p for p in participants if p)}"
        return "thr-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    fallback = message_id or str(uuid.uuid4())
    return "thr-" + hashlib.sha1(fallback.encode("utf-8")).hexdigest()[:16]


def strip_html_tags(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"(?is)<(script|style|head|noscript)\b[^>]*>.*?</\1>", " ", raw_html)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|blockquote)>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in cleaned.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def sanitize_email_html(raw_html: str, allow_remote_images: bool = False) -> str:
    """
    Section 4.6 (M13): Strips <script>, inline event handlers (on*), <iframe/object/embed>,
    and blocks remote http(s) images unless allow_remote_images is enabled for that sender.
    """
    if not raw_html:
        return "<html><body><pre>(empty message)</pre></body></html>"
    h = re.sub(r"(?is)<(script|iframe|object|embed|applet|meta|base|link)\b[^>]*>.*?</\1>", "", raw_html)
    h = re.sub(r"(?is)<(script|iframe|object|embed|applet|meta|base|link)\b[^>]*/?>", "", h)
    h = re.sub(r'(?i)\s+on[a-z0-9_]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', "", h)
    h = re.sub(r'(?i)(href|src)\s*=\s*["\']\s*javascript:[^"\']*["\']', r'\1="#"', h)
    if not allow_remote_images:
        h = re.sub(
            r'(?i)(<img\b[^>]*?\bsrc\s*=\s*["\'])https?://[^"\']+(["\'])',
            r'\1data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7\2 data-Remote-Blocked="1"',
            h,
        )
    return h


def is_auth_error(err: Exception | str) -> bool:
    msg = str(err).lower()
    auth_markers = (
        "authenticationfailed",
        "invalid credentials",
        "login failed",
        "auth failed",
        "authentication failed",
        "username and password not accepted",
        "badcredentials",
        "535 ",
        "535-",
        "534 ",
        "[auth]",
        "unauthorized",
    )
    return any(m in msg for m in auth_markers)


class SatzMailManager:
    """
    Section 4 (M11-M14): Per-profile mail storage (`profiles/<id>/mail.sqlite`),
    account management with vault credentials, IMAP & POP3 sync, and lane queries.
    """

    def __init__(
        self,
        runtime: Any,
        imap_factory: Callable[..., Any] | None = None,
        pop3_factory: Callable[..., Any] | None = None,
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.runtime = runtime
        self.passwords = runtime.passwords
        self.db_lock = threading.RLock()
        self.imap_factory = imap_factory
        self.pop3_factory = pop3_factory
        self.smtp_factory = smtp_factory

        self._active_db_path: Path | None = None
        self._conn: sqlite3.Connection | None = None

        # Per-account background sync threads & state
        self._account_threads: dict[str, threading.Thread] = {}
        self._account_stop_events: dict[str, threading.Event] = {}
        self._account_wake_events: dict[str, threading.Event] = {}
        self._account_backoff: dict[str, dict[str, float]] = {}
        self._auth_stopped_accounts: set[str] = set()
        self.sync_poll_interval_secs = 120.0

        # Pipeline reference (attached in M12)
        self.pipeline: Any = None

        # Pending SMTP send confirmations & outbox timer (M13)
        self._confirm_tokens: dict[str, dict[str, Any]] = {}
        self._send_timers: dict[str, threading.Timer] = {}

        self._ensure_connection()

    # ── SQLite Connection & Schema (Section 4.3) ─────────────────────────
    def _current_mail_db_path(self) -> Path:
        return self.passwords.get_profile_mail_db_path()

    def _current_mail_html_dir(self) -> Path:
        db_path = self._current_mail_db_path()
        d = db_path.parent / "mail_html"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ensure_connection(self) -> sqlite3.Connection:
        with self.db_lock:
            target_path = self._current_mail_db_path()
            if self._conn is not None and self._active_db_path == target_path:
                return self._conn
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            target_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(target_path), check_same_thread=False, timeout=15.0)
            conn.row_factory = sqlite3.Row
            self._init_schema(conn)
            self._conn = conn
            self._active_db_path = target_path
            return conn

    def rebind_profile(self) -> None:
        with self.db_lock:
            self.stop_all_sync_threads()
            self._auth_stopped_accounts.clear()
            self._ensure_connection()
            if self.passwords.unlocked:
                self.start_sync_threads_for_unlocked_profile()

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS mail_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                email TEXT NOT NULL,
                protocol TEXT NOT NULL DEFAULT 'imap',
                in_host TEXT NOT NULL,
                in_port INTEGER NOT NULL DEFAULT 993,
                in_security TEXT NOT NULL DEFAULT 'ssl',
                smtp_host TEXT NOT NULL,
                smtp_port INTEGER NOT NULL DEFAULT 587,
                smtp_security TEXT NOT NULL DEFAULT 'starttls',
                vault_prefix TEXT NOT NULL,
                sync_days INTEGER NOT NULL DEFAULT 30,
                last_sync_at REAL NOT NULL DEFAULT 0.0,
                last_error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS folders (
                account_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'other',
                uidvalidity INTEGER NOT NULL DEFAULT 0,
                last_uid INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_id, name),
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                folder TEXT NOT NULL,
                uid INTEGER NOT NULL DEFAULT 0,
                pop_uidl TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL DEFAULT '',
                thread_id TEXT NOT NULL DEFAULT '',
                in_reply_to TEXT NOT NULL DEFAULT '',
                "references" TEXT NOT NULL DEFAULT '',
                from_addr TEXT NOT NULL DEFAULT '',
                from_name TEXT NOT NULL DEFAULT '',
                to_json TEXT NOT NULL DEFAULT '[]',
                cc_json TEXT NOT NULL DEFAULT '[]',
                subject TEXT NOT NULL DEFAULT '',
                date REAL NOT NULL DEFAULT 0.0,
                snippet TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                has_html INTEGER NOT NULL DEFAULT 0,
                has_attachments INTEGER NOT NULL DEFAULT 0,
                list_unsubscribe TEXT NOT NULL DEFAULT '',
                seen INTEGER NOT NULL DEFAULT 0,
                answered INTEGER NOT NULL DEFAULT 0,
                flagged INTEGER NOT NULL DEFAULT 0,
                hidden INTEGER NOT NULL DEFAULT 0,
                fetched_at REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_account_folder_uid
                ON messages(account_id, folder, uid);
            CREATE INDEX IF NOT EXISTS idx_messages_date
                ON messages(date DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_thread
                ON messages(thread_id, date ASC);

            CREATE TABLE IF NOT EXISTS parts (
                message_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (message_id, kind),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS labels (
                message_id TEXT PRIMARY KEY,
                label TEXT NOT NULL DEFAULT 'email',
                confidence REAL NOT NULL DEFAULT 0.0,
                source TEXT NOT NULL DEFAULT 'rule',
                model_version TEXT NOT NULL DEFAULT 'cold',
                at REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS extracts (
                message_id TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'rule',
                confidence REAL NOT NULL DEFAULT 1.0,
                PRIMARY KEY (message_id, field),
                FOREIGN KEY (message_id) REFERENCES accounts_or_messages_noop(id) ON DELETE CASCADE
            );
            """
        )
        # Fix foreign key on extracts cleanly (referencing messages(id))
        conn.executescript(
            """
            DROP TABLE IF EXISTS extracts;
            CREATE TABLE IF NOT EXISTS extracts (
                message_id TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'rule',
                confidence REAL NOT NULL DEFAULT 1.0,
                PRIMARY KEY (message_id, field),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS actions (
                message_id TEXT PRIMARY KEY,
                needs_reply INTEGER NOT NULL DEFAULT 0,
                due_date TEXT NULL,
                ask TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                old_label TEXT NOT NULL,
                new_label TEXT NOT NULL,
                at REAL NOT NULL DEFAULT 0.0,
                used_in_training INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS eval_labels (
                message_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                extract_ok INTEGER NULL,
                at REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                to_json TEXT NOT NULL DEFAULT '[]',
                cc_json TEXT NOT NULL DEFAULT '[]',
                bcc_json TEXT NOT NULL DEFAULT '[]',
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                in_reply_to TEXT NOT NULL DEFAULT '',
                "references" TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                error TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0.0,
                send_after REAL NOT NULL DEFAULT 0.0,
                sent_at REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS attachments (
                message_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime TEXT NOT NULL DEFAULT 'application/octet-stream',
                size INTEGER NOT NULL DEFAULT 0,
                part_id TEXT NOT NULL,
                saved_path TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (message_id, part_id),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                message_id UNINDEXED,
                subject,
                from_name,
                from_addr,
                new_text
            );
            """
        )
        conn.commit()

    # ── Settings Helpers ─────────────────────────────────────────────────
    def get_mail_settings(self) -> dict[str, Any]:
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute("SELECT key, value FROM mail_settings").fetchall()
            kv = {r["key"]: r["value"] for r in rows}
            remote_senders: list[str] = []
            try:
                remote_senders = json.loads(kv.get("remote_images_senders_json", "[]"))
            except Exception:
                remote_senders = []
            return {
                "mark_read_on_server": kv.get("mark_read_on_server", "1") == "1",
                "sends_per_hour_limit": int(kv.get("sends_per_hour_limit", "20") or 20),
                "remote_images_senders": remote_senders,
                "last_visit_at": float(kv.get("last_visit_at", "0.0") or 0.0),
            }

    def update_mail_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.db_lock:
            conn = self._ensure_connection()
            if "mark_read_on_server" in payload:
                val = "1" if bool(payload["mark_read_on_server"]) else "0"
                conn.execute(
                    "INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('mark_read_on_server', ?)",
                    (val,),
                )
            if "sends_per_hour_limit" in payload:
                val = str(max(1, int(payload["sends_per_hour_limit"])))
                conn.execute(
                    "INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('sends_per_hour_limit', ?)",
                    (val,),
                )
            if "remote_images_senders" in payload and isinstance(payload["remote_images_senders"], list):
                senders = sorted({str(s).strip().lower() for s in payload["remote_images_senders"] if str(s).strip()})
                conn.execute(
                    "INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('remote_images_senders_json', ?)",
                    (json.dumps(senders),),
                )
            if "allow_remote_images_sender" in payload:
                sender = str(payload["allow_remote_images_sender"] or "").strip().lower()
                cur = self.get_mail_settings()["remote_images_senders"]
                if sender and sender not in cur:
                    cur.append(sender)
                conn.execute(
                    "INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('remote_images_senders_json', ?)",
                    (json.dumps(cur),),
                )
            conn.commit()
            return self.get_mail_settings()

    # ── Account Management & Presets (Section 4.2) ───────────────────────
    def _resolve_credentials_for_prefix(self, vault_prefix: str) -> tuple[str, str]:
        env_map = self.passwords.get_unlocked_credentials_map()
        pfx = (vault_prefix or "").strip().upper()
        username = (
            env_map.get(f"{pfx}_USERNAME")
            or env_map.get(f"{pfx}_USER")
            or env_map.get(f"{pfx}_EMAIL")
            or ""
        )
        password = (
            env_map.get(f"{pfx}_PASSWORD")
            or env_map.get(f"{pfx}_PASS")
            or env_map.get(f"{pfx}_SECRET")
            or ""
        )
        return username, password

    def list_accounts(self) -> dict[str, Any]:
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            self.stop_all_sync_threads()
            return {
                "unlocked": False,
                "accounts": [],
                "presets": list(MAIL_PRESETS.values()),
                "settings": self.get_mail_settings(),
            }
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute(
                """
                SELECT id, label, email, protocol, in_host, in_port, in_security,
                       smtp_host, smtp_port, smtp_security, vault_prefix, sync_days,
                       last_sync_at, last_error
                FROM accounts
                ORDER BY rowid ASC
                """
            ).fetchall()
            accounts: list[dict[str, Any]] = []
            for r in rows:
                aid = r["id"]
                msg_cnt_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM messages WHERE account_id = ? AND hidden = 0",
                    (aid,),
                ).fetchone()
                accounts.append(
                    {
                        "id": aid,
                        "label": r["label"],
                        "email": r["email"],
                        "protocol": r["protocol"],
                        "in_host": r["in_host"],
                        "in_port": int(r["in_port"]),
                        "in_security": r["in_security"],
                        "smtp_host": r["smtp_host"],
                        "smtp_port": int(r["smtp_port"]),
                        "smtp_security": r["smtp_security"],
                        "vault_prefix": r["vault_prefix"],
                        "sync_days": int(r["sync_days"] or 30),
                        "last_sync_at": float(r["last_sync_at"] or 0.0),
                        "last_error": r["last_error"] or "",
                        "auth_failed": aid in self._auth_stopped_accounts or (r["last_error"] or "").startswith("[auth failed]"),
                        "message_count": int(msg_cnt_row["c"] if msg_cnt_row else 0),
                    }
                )
            return {
                "unlocked": True,
                "accounts": accounts,
                "presets": list(MAIL_PRESETS.values()),
                "settings": self.get_mail_settings(),
            }

    def _open_imap_client(self, host: str, port: int, security: str):
        if self.imap_factory is not None:
            return self.imap_factory(host, port, security)
        sec = (security or "ssl").lower()
        ctx = ssl.create_default_context()
        if sec == "ssl":
            return imaplib.IMAP4_SSL(host, int(port or 993), ssl_context=ctx, timeout=15.0)
        client = imaplib.IMAP4(host, int(port or 143), timeout=15.0)
        if sec == "starttls":
            client.starttls(ssl_context=ctx)
        return client

    def _open_pop3_client(self, host: str, port: int, security: str):
        if self.pop3_factory is not None:
            return self.pop3_factory(host, port, security)
        sec = (security or "ssl").lower()
        ctx = ssl.create_default_context()
        if sec == "ssl":
            return poplib.POP3_SSL(host, int(port or 995), context=ctx, timeout=15.0)
        client = poplib.POP3(host, int(port or 110), timeout=15.0)
        if sec == "starttls" and hasattr(client, "stls"):
            client.stls(context=ctx)
        return client

    def _open_smtp_client(self, host: str, port: int, security: str):
        if self.smtp_factory is not None:
            return self.smtp_factory(host, port, security)
        sec = (security or "starttls").lower()
        ctx = ssl.create_default_context()
        if sec == "ssl" or int(port or 587) == 465:
            smtp = smtplib.SMTP_SSL(host, int(port or 465), context=ctx, timeout=15.0)
            smtp.ehlo()
            return smtp
        smtp = smtplib.SMTP(host, int(port or 587), timeout=15.0)
        smtp.ehlo()
        if sec == "starttls":
            smtp.starttls(context=ctx)
            smtp.ehlo()
        return smtp

    def test_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Section 4.2 (M11): `[test]` logs in to both incoming (IMAP/POP3) and outgoing
        (SMTP EHLO + AUTH, no message sent) and shows the exact server error on failure.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile vault is locked."}

        account_id = str(payload.get("account_id") or "").strip()
        if account_id:
            with self.db_lock:
                conn = self._ensure_connection()
                row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
                if not row:
                    return {"ok": False, "error": f"Account {account_id} not found."}
                protocol = str(row["protocol"] or "imap").lower()
                in_host = str(row["in_host"] or "")
                in_port = int(row["in_port"] or 993)
                in_security = str(row["in_security"] or "ssl").lower()
                smtp_host = str(row["smtp_host"] or "")
                smtp_port = int(row["smtp_port"] or 587)
                smtp_security = str(row["smtp_security"] or "starttls").lower()
                username, password = self._resolve_credentials_for_prefix(row["vault_prefix"])
                if not username:
                    username = str(row["email"] or "")
        else:
            preset_id = str(payload.get("preset") or "").strip().lower()
            preset = MAIL_PRESETS.get(preset_id, {})
            protocol = str(payload.get("protocol") or preset.get("protocol") or "imap").lower()
            in_host = str(payload.get("in_host") or preset.get("in_host") or "").strip()
            in_port = int(payload.get("in_port") or preset.get("in_port") or (995 if protocol == "pop3" else 993))
            in_security = str(payload.get("in_security") or preset.get("in_security") or "ssl").lower()
            smtp_host = str(payload.get("smtp_host") or preset.get("smtp_host") or "").strip()
            smtp_port = int(payload.get("smtp_port") or preset.get("smtp_port") or 587)
            smtp_security = str(payload.get("smtp_security") or preset.get("smtp_security") or "starttls").lower()
            username = str(payload.get("username") or payload.get("email") or "").strip()
            password = str(payload.get("password") or "").strip()
            vault_prefix = str(payload.get("vault_prefix") or "").strip()
            if (not username or not password) and vault_prefix:
                v_user, v_pass = self._resolve_credentials_for_prefix(vault_prefix)
                username = username or v_user
                password = password or v_pass

        if not in_host or not smtp_host or not username or not password:
            return {
                "ok": False,
                "error": "Incoming host, outgoing SMTP host, username/email, and app password are required.",
            }

        # 1. Incoming check (IMAP or POP3)
        try:
            if protocol == "pop3":
                pop = self._open_pop3_client(in_host, in_port, in_security)
                try:
                    pop.user(username)
                    pop.pass_(password)
                    pop.stat()
                finally:
                    try:
                        pop.quit()
                    except Exception:
                        pass
            else:
                imap = self._open_imap_client(in_host, in_port, in_security)
                try:
                    imap.login(username, password)
                    st, _ = imap.select("INBOX", readonly=True)
                    if st != "OK":
                        return {"ok": False, "stage": "incoming", "error": f"IMAP SELECT INBOX failed: {st}"}
                finally:
                    try:
                        imap.logout()
                    except Exception:
                        pass
        except Exception as exc:
            return {"ok": False, "stage": "incoming", "error": f"{ protocol.upper() } error ({in_host}:{in_port}): {exc}"}

        # 2. Outgoing check (SMTP EHLO + AUTH, no message sent)
        try:
            smtp = self._open_smtp_client(smtp_host, smtp_port, smtp_security)
            try:
                smtp.login(username, password)
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass
        except Exception as exc:
            return {"ok": False, "stage": "outgoing", "error": f"SMTP error ({smtp_host}:{smtp_port}): {exc}"}

        return {
            "ok": True,
            "incoming_ok": True,
            "outgoing_ok": True,
            "protocol": protocol,
            "in_host": in_host,
            "smtp_host": smtp_host,
        }

    def add_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Section 4.2 (M11): Stores credentials in `vault.enc` under `<PREFIX>_USERNAME`,
        `<PREFIX>_PASSWORD`, `<PREFIX>_IMAP_HOST`, `<PREFIX>_SMTP_HOST` and creates the
        account row in `mail.sqlite` (storing `vault_prefix`, NEVER the password).
        """
        if not self.passwords.unlocked:
            raise PermissionError("Unlock the active profile vault before adding a mail account.")

        preset_id = str(payload.get("preset") or "").strip().lower()
        preset = MAIL_PRESETS.get(preset_id, {})
        email_addr = str(payload.get("email") or payload.get("username") or "").strip()
        password = str(payload.get("password") or "").strip()
        label = str(payload.get("label") or preset.get("label") or email_addr).strip()
        protocol = str(payload.get("protocol") or preset.get("protocol") or "imap").strip().lower()
        in_host = str(payload.get("in_host") or preset.get("in_host") or "").strip()
        in_port = int(payload.get("in_port") or preset.get("in_port") or (995 if protocol == "pop3" else 993))
        in_security = str(payload.get("in_security") or preset.get("in_security") or "ssl").strip().lower()
        smtp_host = str(payload.get("smtp_host") or preset.get("smtp_host") or "").strip()
        smtp_port = int(payload.get("smtp_port") or preset.get("smtp_port") or 587)
        smtp_security = str(payload.get("smtp_security") or preset.get("smtp_security") or "starttls").strip().lower()
        sync_days = max(1, int(payload.get("sync_days") or 30))

        raw_prefix = str(payload.get("vault_prefix") or "").strip().upper()
        if not raw_prefix:
            clean_part = re.sub(r"[^A-Z0-9]+", "_", (preset_id or label or email_addr).upper()).strip("_")
            raw_prefix = f"MAIL_{clean_part}" if not clean_part.startswith("MAIL_") else clean_part

        # Check if credentials already exist in vault under raw_prefix
        if not password:
            existing_user, existing_pass = self._resolve_credentials_for_prefix(raw_prefix)
            if not email_addr and existing_user:
                email_addr = existing_user
            password = existing_pass

        if not email_addr or not password or not in_host or not smtp_host:
            raise ValueError("Email, app password, incoming host, and SMTP host are required.")

        # Save credentials in vault.enc under `<PREFIX>_*`
        self.passwords.upsert_service_credential(
            service=raw_prefix,
            username=email_addr,
            password=password,
            imap_host=in_host,
            extra={f"{raw_prefix}_SMTP_HOST": smtp_host},
        )

        account_id = str(payload.get("id") or f"acct-{uuid.uuid4().hex[:10]}")
        with self.db_lock:
            conn = self._ensure_connection()
            conn.execute(
                """
                INSERT OR REPLACE INTO accounts (
                    id, label, email, protocol, in_host, in_port, in_security,
                    smtp_host, smtp_port, smtp_security, vault_prefix, sync_days,
                    last_sync_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '')
                """,
                (
                    account_id,
                    label,
                    email_addr,
                    protocol,
                    in_host,
                    in_port,
                    in_security,
                    smtp_host,
                    smtp_port,
                    smtp_security,
                    raw_prefix,
                    sync_days,
                ),
            )
            conn.commit()

        self._auth_stopped_accounts.discard(account_id)
        if bool(payload.get("start_sync", True)):
            self._start_account_sync_thread(account_id)

        return {
            "ok": True,
            "account_id": account_id,
            "vault_prefix": raw_prefix,
            "accounts": self.list_accounts()["accounts"],
        }

    def remove_account(self, account_id: str) -> dict[str, Any]:
        """
        Section 4.5.5 (M11/M12): Removing an account stops its sync thread, deletes its
        `mail.sqlite` rows and its knowledge store passages (`mail` conversation). Brain entities stay.
        """
        aid = (account_id or "").strip()
        if not aid:
            raise ValueError("account_id is required")

        self._stop_account_sync_thread(aid)
        msg_ids: list[str] = []
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute("SELECT id FROM messages WHERE account_id = ?", (aid,)).fetchall()
            msg_ids = [r["id"] for r in rows]
            for mid in msg_ids:
                conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (mid,))
                html_file = self._current_mail_html_dir() / f"{mid}.html"
                if html_file.exists():
                    try:
                        html_file.unlink()
                    except Exception:
                        pass
            conn.execute("DELETE FROM outbox WHERE account_id = ?", (aid,))
            conn.execute("DELETE FROM folders WHERE account_id = ?", (aid,))
            conn.execute("DELETE FROM messages WHERE account_id = ?", (aid,))
            conn.execute("DELETE FROM accounts WHERE id = ?", (aid,))
            conn.commit()

        # Remove knowledge store passages for deleted messages
        if msg_ids and hasattr(self.runtime, "store"):
            with self.runtime.store_lock:
                for mid in msg_ids:
                    src_id = f"mail:{mid}"
                    self.runtime.store.db.execute("DELETE FROM satz_sources WHERE source_id = ?", (src_id,))
                    self.runtime.store.db.execute("DELETE FROM local_passages WHERE url = ?", (f"satzmail://message/{mid}",))
                self.runtime.store.db.commit()

        return {
            "ok": True,
            "removed_account_id": aid,
            "removed_messages": len(msg_ids),
            "accounts": self.list_accounts()["accounts"],
        }

    # ── Background Sync Threads (Section 4.4) ────────────────────────────
    def start_sync_threads_for_unlocked_profile(self) -> None:
        if not self.passwords.unlocked:
            return
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute("SELECT id FROM accounts").fetchall()
            acct_ids = [r["id"] for r in rows]
        for aid in acct_ids:
            if aid not in self._auth_stopped_accounts:
                self._start_account_sync_thread(aid)

    def stop_all_sync_threads(self) -> None:
        for aid, ev in list(self._account_stop_events.items()):
            ev.set()
            wake = self._account_wake_events.get(aid)
            if wake:
                wake.set()
        self._account_threads.clear()
        self._account_stop_events.clear()
        self._account_wake_events.clear()

    def _stop_account_sync_thread(self, account_id: str) -> None:
        ev = self._account_stop_events.pop(account_id, None)
        if ev:
            ev.set()
        wake = self._account_wake_events.pop(account_id, None)
        if wake:
            wake.set()
        self._account_threads.pop(account_id, None)

    def _start_account_sync_thread(self, account_id: str) -> None:
        existing = self._account_threads.get(account_id)
        if existing and existing.is_alive():
            wake = self._account_wake_events.get(account_id)
            if wake:
                wake.set()
            return
        stop_ev = threading.Event()
        wake_ev = threading.Event()
        self._account_stop_events[account_id] = stop_ev
        self._account_wake_events[account_id] = wake_ev
        t = threading.Thread(
            target=self._account_sync_loop,
            args=(account_id, stop_ev, wake_ev),
            daemon=True,
            name=f"satz-mail-sync-{account_id}",
        )
        self._account_threads[account_id] = t
        t.start()

    def _account_sync_loop(
        self,
        account_id: str,
        stop_ev: threading.Event,
        wake_ev: threading.Event,
    ) -> None:
        while not stop_ev.is_set():
            if not self.passwords.unlocked or account_id in self._auth_stopped_accounts:
                break
            bstate = self._account_backoff.get(account_id, {"errors": 0.0, "backoff_until": 0.0})
            now = time.time()
            if now < bstate.get("backoff_until", 0.0):
                wait_s = min(self.sync_poll_interval_secs, max(1.0, bstate["backoff_until"] - now))
                wake_ev.wait(timeout=wait_s)
                wake_ev.clear()
                continue
            try:
                self.sync_account_once(account_id)
            except Exception as exc:
                self.runtime.record_error("mail_sync", f"{account_id}: {exc}")
            wake_ev.wait(timeout=self.sync_poll_interval_secs)
            wake_ev.clear()

    def sync_all_accounts_once(self) -> dict[str, Any]:
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute("SELECT id FROM accounts").fetchall()
            acct_ids = [r["id"] for r in rows]
        results = {}
        for aid in acct_ids:
            results[aid] = self.sync_account_once(aid)
        return {"ok": True, "results": results}

    def sync_account_once(self, account_id: str) -> dict[str, Any]:
        """
        Section 4.4 (M11): Runs one sync pass for `account_id`:
        - IMAP: INBOX + Sent folder, last `sync_days` (default 30 days), max 2,000, newest first,
          using `BODY.PEEK` everywhere (`readonly=True`) so syncing never marks mail as read (`\\Seen`).
          Incremental sync uses `UID > last_uid` with `UIDVALIDITY` check.
        - POP3: `UIDL` for dedupe, never `DELE` ("leave on server" forced).
        - Auth errors stop sync and set `[auth failed]`; network errors back off (doubling, max 30 min = 1800s).
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        with self.db_lock:
            conn = self._ensure_connection()
            acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not acct:
                return {"ok": False, "error": f"Account {account_id} not found."}
            acct_dict = dict(acct)

        username, password = self._resolve_credentials_for_prefix(acct_dict["vault_prefix"])
        if not username:
            username = acct_dict["email"]
        if not username or not password:
            err_str = "[auth failed] Missing credentials in vault"
            self._auth_stopped_accounts.add(account_id)
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute("UPDATE accounts SET last_error = ? WHERE id = ?", (err_str, account_id))
                conn.commit()
            return {"ok": False, "error": err_str}

        try:
            protocol = str(acct_dict.get("protocol") or "imap").lower()
            if protocol == "pop3":
                synced_ids = self._sync_pop3_account(acct_dict, username, password)
            else:
                synced_ids = self._sync_imap_account(acct_dict, username, password)

            now = time.time()
            self._account_backoff[account_id] = {"errors": 0.0, "backoff_until": 0.0}
            self._auth_stopped_accounts.discard(account_id)
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute(
                    "UPDATE accounts SET last_sync_at = ?, last_error = '' WHERE id = ?",
                    (now, account_id),
                )
                conn.commit()

            # Enqueue newly synced messages into the processing pipeline (M12)
            if synced_ids and self.pipeline is not None:
                self.pipeline.enqueue_messages(synced_ids)

            return {"ok": True, "synced_count": len(synced_ids), "message_ids": synced_ids}

        except Exception as exc:
            now = time.time()
            if is_auth_error(exc):
                err_msg = f"[auth failed] {exc}"
                self._auth_stopped_accounts.add(account_id)
                self.runtime.record_error("mail_auth", f"{account_id}: {exc}")
            else:
                prev = int(self._account_backoff.get(account_id, {}).get("errors", 0.0))
                nxt = prev + 1
                backoff_secs = min(1800.0, 60.0 * (2 ** (nxt - 1)))
                self._account_backoff[account_id] = {
                    "errors": float(nxt),
                    "backoff_until": now + backoff_secs,
                }
                err_msg = f"sync error (backoff {int(backoff_secs)}s): {exc}"
                self.runtime.record_error("mail_sync", f"{account_id}: {exc}")

            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute("UPDATE accounts SET last_error = ? WHERE id = ?", (err_msg, account_id))
                conn.commit()
            return {"ok": False, "error": err_msg}

    def _discover_imap_folders(self, imap: Any) -> list[tuple[str, str]]:
        """
        Returns `[("INBOX", "inbox"), (<sent_folder>, "sent")]`.
        Detects Sent folder via `\\Sent` special-use flag in `LIST` or standard Sent folder names.
        """
        folders: list[tuple[str, str]] = [("INBOX", "inbox")]
        sent_folder: str | None = None
        try:
            st, lines = imap.list()
            if st == "OK" and lines:
                candidates: list[str] = []
                for raw_line in lines:
                    if not raw_line:
                        continue
                    line_str = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
                    # Parse `(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"`
                    m = re.match(r'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL|\S+)\s+(?P<name>.+)$', line_str.strip())
                    if not m:
                        continue
                    flags = m.group("flags").lower()
                    name = m.group("name").strip().strip('"')
                    if "\\sent" in flags:
                        sent_folder = name
                        break
                    candidates.append(name)
                if not sent_folder:
                    for cand in candidates:
                        cl = cand.lower()
                        if cl in ("sent", "sent items", "sent messages", "[gmail]/sent mail", "gesendet", "inbox.sent"):
                            sent_folder = cand
                            break
        except Exception:
            pass
        if sent_folder and sent_folder.upper() != "INBOX":
            folders.append((sent_folder, "sent"))
        return folders

    def _sync_imap_account(self, acct: dict[str, Any], username: str, password: str) -> list[str]:
        account_id = acct["id"]
        in_host = acct["in_host"]
        in_port = int(acct["in_port"] or 993)
        in_security = acct["in_security"] or "ssl"
        sync_days = max(1, int(acct.get("sync_days") or 30))

        new_msg_ids: list[str] = []
        imap = self._open_imap_client(in_host, in_port, in_security)
        try:
            imap.login(username, password)
            target_folders = self._discover_imap_folders(imap)

            for folder_name, role in target_folders:
                # Always SELECT readonly=True during sync so syncing NEVER marks mail as \Seen
                st, _ = imap.select(f'"{folder_name}"' if " " in folder_name else folder_name, readonly=True)
                if st != "OK":
                    continue

                # Check UIDVALIDITY
                uidvalidity = 0
                try:
                    uv_resp = imap.response("UIDVALIDITY")
                    if uv_resp and uv_resp[1] and uv_resp[1][0]:
                        uv_val = uv_resp[1][0]
                        uidvalidity = int(uv_val.decode() if isinstance(uv_val, bytes) else uv_val)
                except Exception:
                    uidvalidity = 0

                with self.db_lock:
                    conn = self._ensure_connection()
                    frow = conn.execute(
                        "SELECT uidvalidity, last_uid FROM folders WHERE account_id = ? AND name = ?",
                        (account_id, folder_name),
                    ).fetchone()
                    stored_uv = int(frow["uidvalidity"] or 0) if frow else 0
                    last_uid = int(frow["last_uid"] or 0) if frow else 0

                    # If UIDVALIDITY changed on the server, reset folder state & resync
                    if stored_uv > 0 and uidvalidity > 0 and stored_uv != uidvalidity:
                        old_rows = conn.execute(
                            "SELECT id FROM messages WHERE account_id = ? AND folder = ?",
                            (account_id, folder_name),
                        ).fetchall()
                        for orow in old_rows:
                            conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (orow["id"],))
                        conn.execute(
                            "DELETE FROM messages WHERE account_id = ? AND folder = ?",
                            (account_id, folder_name),
                        )
                        conn.commit()
                        last_uid = 0

                if last_uid > 0:
                    search_crit = f"UID {last_uid + 1}:*"
                    st_s, s_data = imap.uid("SEARCH", None, search_crit)
                else:
                    since_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=sync_days)
                    since_str = since_dt.strftime("%d-%b-%Y")
                    st_s, s_data = imap.uid("SEARCH", None, f"(SINCE {since_str})")

                if st_s != "OK" or not s_data or not s_data[0]:
                    with self.db_lock:
                        conn = self._ensure_connection()
                        conn.execute(
                            """
                            INSERT INTO folders (account_id, name, role, uidvalidity, last_uid)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(account_id, name) DO UPDATE SET
                                role = excluded.role,
                                uidvalidity = CASE WHEN excluded.uidvalidity > 0 THEN excluded.uidvalidity ELSE folders.uidvalidity END
                            """,
                            (account_id, folder_name, role, uidvalidity, last_uid),
                        )
                        conn.commit()
                    continue

                raw_uids = s_data[0].split() if isinstance(s_data[0], (bytes, str)) else []
                uids: list[int] = []
                for u in raw_uids:
                    try:
                        u_int = int(u.decode() if isinstance(u, bytes) else u)
                        if u_int > last_uid:
                            uids.append(u_int)
                    except Exception:
                        pass

                uids.sort()
                # Cap at 2,000 messages, newest first (Section 4.4)
                if len(uids) > 2000:
                    uids = uids[-2000:]
                uids_newest_first = list(reversed(uids))
                max_seen_uid = max(uids) if uids else last_uid

                for uid_val in uids_newest_first:
                    # Section 4.4: Use BODY.PEEK everywhere so syncing never marks mail as read
                    st_f, f_data = imap.uid(
                        "FETCH",
                        str(uid_val),
                        "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.20000>)",
                    )
                    if st_f != "OK" or not f_data:
                        continue
                    saved_id = self._ingest_imap_fetched_item(
                        account_id=account_id,
                        folder_name=folder_name,
                        role=role,
                        uid=uid_val,
                        fetch_data=f_data,
                    )
                    if saved_id:
                        new_msg_ids.append(saved_id)

                with self.db_lock:
                    conn = self._ensure_connection()
                    conn.execute(
                        """
                        INSERT INTO folders (account_id, name, role, uidvalidity, last_uid)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(account_id, name) DO UPDATE SET
                            role = excluded.role,
                            uidvalidity = CASE WHEN excluded.uidvalidity > 0 THEN excluded.uidvalidity ELSE folders.uidvalidity END,
                            last_uid = MAX(folders.last_uid, excluded.last_uid)
                        """,
                        (account_id, folder_name, role, uidvalidity, max_seen_uid),
                    )
                    conn.commit()
        finally:
            try:
                imap.logout()
            except Exception:
                pass

        return new_msg_ids

    def _ingest_imap_fetched_item(
        self,
        account_id: str,
        folder_name: str,
        role: str,
        uid: int,
        fetch_data: list[Any],
    ) -> str | None:
        flags_str = ""
        header_bytes = b""
        body_bytes = b""
        full_rfc822_bytes = b""

        for item in fetch_data:
            if isinstance(item, tuple) and len(item) >= 2:
                meta = item[0].decode("utf-8", errors="replace") if isinstance(item[0], bytes) else str(item[0])
                payload = item[1] if isinstance(item[1], bytes) else str(item[1]).encode("utf-8")
                if "FLAGS" in meta.upper():
                    flags_str += " " + meta
                meta_up = meta.upper()
                if "HEADER" in meta_up:
                    header_bytes = payload
                elif "TEXT" in meta_up:
                    body_bytes = payload
                else:
                    full_rfc822_bytes = payload
            elif isinstance(item, bytes):
                flags_str += " " + item.decode("utf-8", errors="replace")

        raw_combined = full_rfc822_bytes if full_rfc822_bytes else (header_bytes + b"\r\n\r\n" + body_bytes)
        if not raw_combined.strip():
            return None

        flags_up = flags_str.upper()
        seen = 1 if ("\\SEEN" in flags_up or role == "sent") else 0
        answered = 1 if "\\ANSWERED" in flags_up else 0
        flagged = 1 if "\\FLAGGED" in flags_up else 0

        return self._store_parsed_raw_email(
            account_id=account_id,
            folder_name=folder_name,
            role=role,
            uid=uid,
            pop_uidl="",
            raw_bytes=raw_combined,
            seen=seen,
            answered=answered,
            flagged=flagged,
        )

    def _sync_pop3_account(self, acct: dict[str, Any], username: str, password: str) -> list[str]:
        """
        Section 4.4 (M11): POP3 sync using `poplib.POP3_SSL`, `UIDL` for dedupe,
        NEVER calling `DELE` ("leave on server" forced).
        """
        account_id = acct["id"]
        in_host = acct["in_host"]
        in_port = int(acct["in_port"] or 995)
        in_security = acct["in_security"] or "ssl"

        with self.db_lock:
            conn = self._ensure_connection()
            existing_rows = conn.execute(
                "SELECT pop_uidl FROM messages WHERE account_id = ? AND pop_uidl != ''",
                (account_id,),
            ).fetchall()
            known_uidls = {r["pop_uidl"] for r in existing_rows}

        new_msg_ids: list[str] = []
        pop = self._open_pop3_client(in_host, in_port, in_security)
        try:
            pop.user(username)
            pop.pass_(password)
            resp, uidl_lines, _ = pop.uidl()
            entries: list[tuple[int, str]] = []
            for raw_ln in uidl_lines or []:
                ln = raw_ln.decode("utf-8", errors="replace").strip() if isinstance(raw_ln, bytes) else str(raw_ln).strip()
                parts = ln.split(None, 1)
                if len(parts) == 2:
                    try:
                        msg_num = int(parts[0])
                        uidl_val = parts[1].strip()
                        if uidl_val not in known_uidls:
                            entries.append((msg_num, uidl_val))
                    except Exception:
                        pass

            # Newest first, max 2,000, NEVER calling pop.dele()
            entries = entries[-2000:][::-1]
            for msg_num, uidl_val in entries:
                _, msg_lines, _ = pop.retr(msg_num)
                raw_bytes = b"\r\n".join(
                    ln if isinstance(ln, bytes) else str(ln).encode("utf-8")
                    for ln in (msg_lines or [])
                )
                saved_id = self._store_parsed_raw_email(
                    account_id=account_id,
                    folder_name="INBOX",
                    role="inbox",
                    uid=msg_num,
                    pop_uidl=uidl_val,
                    raw_bytes=raw_bytes,
                    seen=0,
                    answered=0,
                    flagged=0,
                )
                if saved_id:
                    new_msg_ids.append(saved_id)
        finally:
            try:
                pop.quit()
            except Exception:
                pass

        return new_msg_ids

    def _store_parsed_raw_email(
        self,
        account_id: str,
        folder_name: str,
        role: str,
        uid: int,
        pop_uidl: str,
        raw_bytes: bytes,
        seen: int,
        answered: int,
        flagged: int,
    ) -> str | None:
        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
        raw_msg_id = str(msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
        in_reply_to = str(msg.get("In-Reply-To") or "").strip()
        references = str(msg.get("References") or "").strip()
        subject = decode_mime_header(msg.get("Subject")) or "(no subject)"
        list_unsub = str(msg.get("List-Unsubscribe") or "").strip()
        precedence = str(msg.get("Precedence") or "").strip()
        if precedence and not list_unsub and precedence.lower() in ("bulk", "list", "junk"):
            list_unsub = f"Precedence: {precedence}"

        from_list = parse_address_list(msg.get("From"))
        from_name = from_list[0]["name"] if from_list else ""
        from_addr = from_list[0]["email"] if from_list else decode_mime_header(msg.get("From")).lower()
        to_list = parse_address_list(msg.get_all("To", []))
        cc_list = parse_address_list(msg.get_all("Cc", []))

        date_hdr = msg.get("Date")
        msg_ts = time.time()
        if date_hdr:
            try:
                dt = email.utils.parsedate_to_datetime(str(date_hdr))
                if dt is not None:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    msg_ts = dt.timestamp()
            except Exception:
                msg_ts = time.time()

        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachment_rows: list[dict[str, Any]] = []

        if msg.is_multipart():
            part_idx = 0
            for part in msg.walk():
                if part.is_multipart():
                    continue
                part_idx += 1
                ctype = (part.get_content_type() or "text/plain").lower()
                disp = str(part.get_content_disposition() or "").lower()
                fname = decode_mime_header(part.get_filename())
                if disp == "attachment" or fname:
                    payload_bytes = part.get_payload(decode=True) or b""
                    attachment_rows.append(
                        {
                            "part_id": str(part_idx),
                            "filename": fname or f"attachment-{part_idx}",
                            "mime": ctype,
                            "size": len(payload_bytes),
                            "bytes": payload_bytes,
                        }
                    )
                    continue
                if ctype == "text/plain":
                    try:
                        plain_parts.append(str(part.get_content()))
                    except Exception:
                        raw_p = part.get_payload(decode=True) or b""
                        plain_parts.append(raw_p.decode(part.get_content_charset() or "utf-8", errors="replace"))
                elif ctype == "text/html":
                    try:
                        html_parts.append(str(part.get_content()))
                    except Exception:
                        raw_p = part.get_payload(decode=True) or b""
                        html_parts.append(raw_p.decode(part.get_content_charset() or "utf-8", errors="replace"))
        else:
            ctype = (msg.get_content_type() or "text/plain").lower()
            try:
                content_str = str(msg.get_content())
            except Exception:
                raw_p = msg.get_payload(decode=True) or b""
                content_str = raw_p.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if ctype == "text/html":
                html_parts.append(content_str)
            else:
                plain_parts.append(content_str)

        full_html = "\n".join(h for h in html_parts if h).strip()
        body_text = "\n\n".join(p.strip() for p in plain_parts if p and p.strip())
        if not body_text and full_html:
            # Prefer SGS extract_main_text, falling back to tag stripping (Section 4.5.1)
            try:
                from src.planck3.web import extract_main_text

                body_text = extract_main_text(full_html, "https://mail.local") or ""
            except Exception:
                body_text = ""
            if not body_text:
                body_text = strip_html_tags(full_html)

        snippet = re.sub(r"\s+", " ", (body_text or "").strip())[:220]
        thread_id = compute_thread_id(raw_msg_id, in_reply_to, references, subject, from_addr, to_list)

        # Deterministic message key
        unique_seed = f"{account_id}|{folder_name}|{uid}|{pop_uidl}|{raw_msg_id}"
        local_id = "msg-" + hashlib.sha1(unique_seed.encode("utf-8")).hexdigest()[:16]

        has_html = 1 if full_html else 0
        has_attachments = 1 if attachment_rows else 0
        now_ts = time.time()

        if full_html:
            try:
                html_path = self._current_mail_html_dir() / f"{local_id}.html"
                html_path.write_text(full_html, encoding="utf-8")
            except Exception:
                pass

        with self.db_lock:
            conn = self._ensure_connection()
            existing = conn.execute("SELECT id, seen FROM messages WHERE id = ?", (local_id,)).fetchone()
            effective_seen = max(seen, int(existing["seen"])) if existing else seen

            conn.execute(
                """
                INSERT OR REPLACE INTO messages (
                    id, account_id, folder, uid, pop_uidl, message_id, thread_id,
                    in_reply_to, "references", from_addr, from_name, to_json, cc_json,
                    subject, date, snippet, body_text, has_html, has_attachments,
                    list_unsubscribe, seen, answered, flagged, hidden, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT hidden FROM messages WHERE id = ?), 0), ?)
                """,
                (
                    local_id,
                    account_id,
                    folder_name,
                    uid,
                    pop_uidl,
                    raw_msg_id,
                    thread_id,
                    in_reply_to,
                    references,
                    from_addr,
                    from_name,
                    json.dumps(to_list, ensure_ascii=False),
                    json.dumps(cc_list, ensure_ascii=False),
                    subject,
                    msg_ts,
                    snippet,
                    body_text,
                    has_html,
                    has_attachments,
                    list_unsub,
                    effective_seen,
                    answered,
                    flagged,
                    local_id,
                    now_ts,
                ),
            )

            # Seed initial `new` part and FTS row before M12 pipeline refines it
            has_part = conn.execute(
                "SELECT 1 FROM parts WHERE message_id = ? AND kind = 'new'",
                (local_id,),
            ).fetchone()
            if not has_part:
                conn.execute(
                    "INSERT OR REPLACE INTO parts (message_id, kind, text) VALUES (?, 'new', ?)",
                    (local_id, body_text),
                )
                conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (local_id,))
                conn.execute(
                    "INSERT INTO messages_fts (message_id, subject, from_name, from_addr, new_text) VALUES (?, ?, ?, ?, ?)",
                    (local_id, subject, from_name, from_addr, body_text),
                )

            for att in attachment_rows:
                att_dir = self._current_mail_db_path().parent / "mail_attachments" / local_id
                att_dir.mkdir(parents=True, exist_ok=True)
                safe_fname = re.sub(r"[^A-Za-z0-9._-]+", "_", att["filename"]) or f"part-{att['part_id']}"
                saved_p = att_dir / safe_fname
                try:
                    if att.get("bytes"):
                        saved_p.write_bytes(att["bytes"])
                except Exception:
                    pass
                conn.execute(
                    """
                    INSERT OR REPLACE INTO attachments (message_id, filename, mime, size, part_id, saved_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (local_id, att["filename"], att["mime"], att["size"], att["part_id"], str(saved_p)),
                )

            conn.commit()

        return local_id

    # ── Lane Queries & Status (M11-M14) ──────────────────────────────────
    def get_inbox_unread_count(self) -> int:
        if not self.passwords.unlocked:
            return 0
        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM messages m
                LEFT JOIN labels l ON l.message_id = m.id
                WHERE m.hidden = 0
                  AND UPPER(m.folder) = 'INBOX'
                  AND m.seen = 0
                  AND COALESCE(l.label, 'email') = 'email'
                """
            ).fetchone()
            return int(row["c"] if row else 0)

    def get_lane(self, name: str = "inbox", cursor: int = 0, limit: int = 50) -> dict[str, Any]:
        """
        Section 4.1 & 4.8: Returns lane rows (50 per page) for `inbox`, `pings`, `orders`, `promos`.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {
                "unlocked": False,
                "lane": name,
                "rows": [],
                "groups": [],
                "counts": {"inbox_unread": 0, "pings": 0, "orders": 0, "promos": 0},
            }

        lane = (name or "inbox").strip().lower()
        offset = max(0, int(cursor or 0))
        page_limit = max(1, min(200, int(limit or 50)))

        with self.db_lock:
            conn = self._ensure_connection()
            counts = self._compute_lane_counts(conn)

            if lane == "inbox":
                rows = conn.execute(
                    """
                    SELECT m.id, m.account_id, m.thread_id, m.from_name, m.from_addr, m.subject,
                           m.snippet, m.date, m.seen, m.answered, m.flagged, m.has_attachments,
                           COALESCE(l.label, 'email') AS label,
                           COALESCE(l.confidence, 0.0) AS confidence,
                           COALESCE(a.needs_reply, 0) AS needs_reply,
                           a.due_date AS due_date,
                           COALESCE(a.ask, '') AS ask
                    FROM messages m
                    LEFT JOIN labels l ON l.message_id = m.id
                    LEFT JOIN actions a ON a.message_id = m.id
                    WHERE m.hidden = 0
                      AND UPPER(m.folder) = 'INBOX'
                      AND COALESCE(l.label, 'email') = 'email'
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (page_limit, offset),
                ).fetchall()
                return {
                    "unlocked": True,
                    "lane": "inbox",
                    "rows": [dict(r) for r in rows],
                    "next_cursor": offset + len(rows) if len(rows) == page_limit else None,
                    "counts": counts,
                }

            if lane == "pings":
                rows = conn.execute(
                    """
                    SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen,
                           COALESCE(e.value, '') AS platform
                    FROM messages m
                    JOIN labels l ON l.message_id = m.id AND l.label = 'ping'
                    LEFT JOIN extracts e ON e.message_id = m.id AND e.field = 'platform'
                    WHERE m.hidden = 0
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (page_limit, offset),
                ).fetchall()
                items = [dict(r) for r in rows]
                groups_map: dict[str, dict[str, Any]] = {}
                for it in items:
                    plat = it.get("platform") or "Other"
                    author = it.get("from_name") or it.get("from_addr") or "unknown"
                    g = groups_map.setdefault(plat, {"platform": plat, "count": 0, "authors": {}, "items": []})
                    g["count"] += 1
                    g["authors"][author] = g["authors"].get(author, 0) + 1
                    g["items"].append(it)
                return {
                    "unlocked": True,
                    "lane": "pings",
                    "rows": items,
                    "groups": list(groups_map.values()),
                    "counts": counts,
                }

            if lane == "orders":
                rows = conn.execute(
                    """
                    SELECT m.id, m.thread_id, m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen
                    FROM messages m
                    JOIN labels l ON l.message_id = m.id AND l.label = 'information'
                    WHERE m.hidden = 0
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (page_limit, offset),
                ).fetchall()
                orders_by_key: dict[str, dict[str, Any]] = {}
                for r in rows:
                    mid = r["id"]
                    ext_rows = conn.execute(
                        "SELECT field, value FROM extracts WHERE message_id = ?",
                        (mid,),
                    ).fetchall()
                    ext = {er["field"]: er["value"] for er in ext_rows}
                    order_no = ext.get("order_number") or ""
                    merchant = ext.get("merchant") or r["from_name"] or r["from_addr"]
                    key = f"{merchant.lower()}::{order_no}" if order_no else f"thr::{r['thread_id'] or mid}"
                    card = orders_by_key.get(key)
                    email_entry = {
                        "id": mid,
                        "subject": r["subject"],
                        "date": r["date"],
                        "snippet": r["snippet"],
                        "status": ext.get("status") or "",
                    }
                    if not card:
                        orders_by_key[key] = {
                            "key": key,
                            "merchant": merchant,
                            "order_number": order_no,
                            "status": ext.get("status") or "ordered",
                            "tracking_number": ext.get("tracking_number") or "",
                            "tracking_url": ext.get("tracking_url") or "",
                            "total": ext.get("total") or "",
                            "last_update": r["date"],
                            "latest_message_id": mid,
                            "emails": [email_entry],
                        }
                    else:
                        card["emails"].append(email_entry)
                        if not card["order_number"] and order_no:
                            card["order_number"] = order_no
                        if not card["tracking_number"] and ext.get("tracking_number"):
                            card["tracking_number"] = ext["tracking_number"]
                        if not card["tracking_url"] and ext.get("tracking_url"):
                            card["tracking_url"] = ext["tracking_url"]
                        if not card["total"] and ext.get("total"):
                            card["total"] = ext["total"]
                return {
                    "unlocked": True,
                    "lane": "orders",
                    "rows": list(orders_by_key.values()),
                    "counts": counts,
                }

            if lane == "promos":
                rows = conn.execute(
                    """
                    SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen
                    FROM messages m
                    JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
                    WHERE m.hidden = 0
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (page_limit, offset),
                ).fetchall()
                companies: dict[str, dict[str, Any]] = {}
                today_iso = datetime.date.today().isoformat()
                for r in rows:
                    mid = r["id"]
                    ext_rows = conn.execute(
                        "SELECT field, value FROM extracts WHERE message_id = ?",
                        (mid,),
                    ).fetchall()
                    ext = {er["field"]: er["value"] for er in ext_rows}
                    dom = (r["from_addr"].split("@")[-1] if "@" in r["from_addr"] else r["from_addr"]).lower()
                    company = ext.get("company") or r["from_name"] or dom
                    comp_key = dom or company.lower()
                    grp = companies.setdefault(
                        comp_key,
                        {
                            "company": company,
                            "domain": dom,
                            "active_codes": [],
                            "expired_codes": [],
                            "emails": [],
                        },
                    )
                    if len(grp["emails"]) < 5:
                        grp["emails"].append(
                            {
                                "id": mid,
                                "subject": r["subject"],
                                "date": r["date"],
                                "snippet": r["snippet"],
                            }
                        )
                    code = ext.get("voucher_code") or ""
                    if code:
                        expiry = ext.get("expiry") or ""
                        is_expired = bool(expiry and re.match(r"^\d{4}-\d{2}-\d{2}$", expiry) and expiry < today_iso)
                        code_item = {
                            "code": code,
                            "discount_value": ext.get("discount_value") or "",
                            "expiry": expiry,
                            "message_id": mid,
                            "expired": is_expired,
                        }
                        target_list = grp["expired_codes"] if is_expired else grp["active_codes"]
                        if not any(c["code"] == code for c in target_list):
                            target_list.append(code_item)
                return {
                    "unlocked": True,
                    "lane": "promos",
                    "rows": list(companies.values()),
                    "counts": counts,
                }

            return {"unlocked": True, "lane": lane, "rows": [], "counts": counts}

    def _compute_lane_counts(self, conn: sqlite3.Connection) -> dict[str, int]:
        inbox_unread = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM messages m
            LEFT JOIN labels l ON l.message_id = m.id
            WHERE m.hidden = 0 AND UPPER(m.folder) = 'INBOX' AND m.seen = 0
              AND COALESCE(l.label, 'email') = 'email'
            """
        ).fetchone()
        pings_c = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'ping'
            WHERE m.hidden = 0 AND m.seen = 0
            """
        ).fetchone()
        orders_c = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'information'
            WHERE m.hidden = 0
            """
        ).fetchone()
        promos_c = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
            WHERE m.hidden = 0
            """
        ).fetchone()
        return {
            "inbox_unread": int(inbox_unread["c"] if inbox_unread else 0),
            "pings": int(pings_c["c"] if pings_c else 0),
            "orders": int(orders_c["c"] if orders_c else 0),
            "promos": int(promos_c["c"] if promos_c else 0),
        }

    def get_status(self) -> dict[str, Any]:
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {
                "unlocked": False,
                "accounts_count": 0,
                "inbox_unread": 0,
                "processing_done": 0,
                "processing_total": 0,
                "model_version": "cold",
                "labelled_count": 0,
            }
        with self.db_lock:
            conn = self._ensure_connection()
            acct_cnt = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
            labelled_cnt = conn.execute("SELECT COUNT(*) AS c FROM labels").fetchone()["c"]
            counts = self._compute_lane_counts(conn)
        pipe_status = self.pipeline.get_status() if self.pipeline is not None else {
            "processing_done": int(labelled_cnt),
            "processing_total": int(labelled_cnt),
            "is_processing": False,
            "model_version": "cold",
            "last_retrain_at": 0.0,
        }
        return {
            "unlocked": True,
            "accounts_count": int(acct_cnt),
            "inbox_unread": counts["inbox_unread"],
            "counts": counts,
            **pipe_status,
        }

#!/usr/bin/env python3
"""
Unified Cloud Drives Surface for Satz Browser (`conv-drives`).

Supports single-account Google Drive (`hellofresh.com`, extending `satz_google_auth.py`)
and single-account Microsoft OneDrive (`ONEDRIVE_OAUTH_*` in `vault.enc`).

Core security & privacy invariants:
1. Zero cloud credential or profile storage: all OAuth tokens, metadata (`drives.sqlite`),
   Brain entities (`Entities/Documents/`), and semantic passages (`planck_store.sqlite`)
   live strictly inside the local unlocked profile directory (`data/profiles/<id>/`).
2. Zero local file downloads: background 90-day core indexing streams document exports/bytes
   exclusively into bounded `io.BytesIO` buffers in RAM, writes distilled summaries and
   6-8 semantic passages into `SatzBrain` + `planck_store.sqlite`, and discards raw bytes.
3. Pure local retrieval in Chat: chat queries combine `drives.sqlite` metadata/FTS5 with
   `SatzBrain` / `planck_store.sqlite` semantic passages with zero mid-chat cloud downloads.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from satz_google_auth import GOOGLE_DRIVE_READONLY_SCOPE, _mask_client_id, _render_callback_html


ONEDRIVE_VAULT_PREFIX = "ONEDRIVE_OAUTH"
DEFAULT_ONEDRIVE_TENANT = "common"
DEFAULT_ONEDRIVE_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Files.Read.All",
]

GDRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GDRIVE_CHANGES_URL = "https://www.googleapis.com/drive/v3/changes"
GDRIVE_START_TOKEN_URL = "https://www.googleapis.com/drive/v3/changes/startPageToken"
GDRIVE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress),storageQuota"

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

CORE_INDEX_WINDOW_SECS = 90 * 86_400
MAX_EXTRACT_BYTES = 15 * 1024 * 1024
MAX_INDEX_DOCS_PER_PASS = 40

GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _parse_iso_ts(raw: str | float | int | None) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    try:
        norm = s.replace("Z", "+00:00")
        return datetime.fromisoformat(norm).timestamp()
    except Exception:
        return 0.0


def _ts_to_iso(ts: float) -> str:
    if not ts or ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_file_category(mime_type: str, name: str, is_folder: bool = False) -> str:
    if is_folder or mime_type == GOOGLE_FOLDER_MIME:
        return "folder"
    m = (mime_type or "").strip().lower()
    ext = Path(name or "").suffix.lower()
    if m in (GOOGLE_DOC_MIME, DOCX_MIME, "application/msword", "application/rtf") or ext in (
        ".doc",
        ".docx",
        ".odt",
        ".rtf",
        ".md",
        ".txt",
    ):
        return "doc"
    if m in (GOOGLE_SHEET_MIME, XLSX_MIME, "application/vnd.ms-excel", "text/csv", "text/tab-separated-values") or ext in (
        ".xls",
        ".xlsx",
        ".ods",
        ".csv",
        ".tsv",
    ):
        return "sheet"
    if m in (GOOGLE_SLIDE_MIME, PPTX_MIME, "application/vnd.ms-powerpoint") or ext in (
        ".ppt",
        ".pptx",
        ".odp",
    ):
        return "slide"
    if m == "application/pdf" or ext == ".pdf":
        return "pdf"
    if m.startswith("image/") or ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic"):
        return "image"
    if m.startswith("text/"):
        return "doc"
    return "other"


def is_core_indexable(file_category: str, mime_type: str, name: str, size_bytes: int) -> bool:
    if file_category == "folder" or file_category == "image":
        return False
    if size_bytes and size_bytes > MAX_EXTRACT_BYTES:
        return False
    m = (mime_type or "").strip().lower()
    ext = Path(name or "").suffix.lower()
    if m in (GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME, GOOGLE_SLIDE_MIME, DOCX_MIME, XLSX_MIME, PPTX_MIME, "application/pdf"):
        return True
    if m.startswith("text/") or ext in (".md", ".txt", ".csv", ".tsv", ".json", ".docx", ".xlsx", ".pptx", ".pdf"):
        return True
    return False


def append_google_authuser(url: str, email: str) -> str:
    u = (url or "").strip()
    em = (email or "").strip()
    if not u or not em:
        return u
    try:
        sp = urllib.parse.urlsplit(u)
        host = (sp.hostname or "").lower()
        if not (host.endswith(".google.com") or host == "google.com"):
            return u
        q_pairs = urllib.parse.parse_qsl(sp.query, keep_blank_values=True)
        if any(k == "authuser" for k, _ in q_pairs):
            return u
        q_pairs.append(("authuser", em))
        new_query = urllib.parse.urlencode(q_pairs)
        return urllib.parse.urlunsplit((sp.scheme, sp.netloc, sp.path, new_query, sp.fragment))
    except Exception:
        return u


# ── In-Memory Document Text Extractors (Zero Disk Writes) ────────────────


def extract_docx_text_in_memory(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        if "word/document.xml" not in zf.namelist():
            return ""
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "p":
            runs: list[str] = []
            for child in elem.iter():
                ctag = child.tag.rsplit("}", 1)[-1]
                if ctag == "t" and child.text:
                    runs.append(child.text)
                elif ctag in ("tab", "br"):
                    runs.append(" ")
            line = re.sub(r"\s+", " ", "".join(runs)).strip()
            if line:
                paragraphs.append(line)
    return "\n".join(paragraphs)


def extract_xlsx_text_in_memory(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = set(zf.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.iter():
                if si.tag.rsplit("}", 1)[-1] == "si":
                    parts = [
                        t.text
                        for t in si.iter()
                        if t.tag.rsplit("}", 1)[-1] == "t" and t.text
                    ]
                    shared_strings.append("".join(parts).strip())

        sheet_files = sorted(
            n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )[:6]
        out_lines: list[str] = []
        for idx, sf in enumerate(sheet_files, start=1):
            sh_root = ET.fromstring(zf.read(sf))
            sheet_rows: list[str] = []
            for row_el in sh_root.iter():
                if row_el.tag.rsplit("}", 1)[-1] != "row":
                    continue
                vals: list[str] = []
                for cell in row_el:
                    if cell.tag.rsplit("}", 1)[-1] != "c":
                        continue
                    c_type = cell.attrib.get("t", "")
                    val_txt = ""
                    for sub in cell.iter():
                        stag = sub.tag.rsplit("}", 1)[-1]
                        if stag == "v" and sub.text is not None:
                            if c_type == "s":
                                try:
                                    s_idx = int(sub.text)
                                    if 0 <= s_idx < len(shared_strings):
                                        val_txt = shared_strings[s_idx]
                                except ValueError:
                                    val_txt = sub.text
                            else:
                                val_txt = sub.text
                            break
                        if c_type == "inlineStr" and stag == "t" and sub.text:
                            val_txt += sub.text
                    val_clean = re.sub(r"\s+", " ", val_txt).strip()
                    if val_clean:
                        vals.append(val_clean)
                if vals:
                    sheet_rows.append(" | ".join(vals[:16]))
                if len(sheet_rows) >= 120:
                    break
            if sheet_rows:
                out_lines.append(f"Sheet {idx}:")
                out_lines.extend(sheet_rows)
    return "\n".join(out_lines)


def extract_pptx_text_in_memory(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        slide_names = [
            n for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n)
        ]
        slide_names.sort(key=lambda s: int(re.search(r"(\d+)", s).group(1)))  # type: ignore[union-attr]
        slides_out: list[str] = []
        for idx, sname in enumerate(slide_names[:60], start=1):
            s_root = ET.fromstring(zf.read(sname))
            paras: list[str] = []
            for elem in s_root.iter():
                if elem.tag.rsplit("}", 1)[-1] == "p":
                    runs = [
                        t.text
                        for t in elem.iter()
                        if t.tag.rsplit("}", 1)[-1] == "t" and t.text
                    ]
                    line = re.sub(r"\s+", " ", "".join(runs)).strip()
                    if line:
                        paras.append(line)
            if paras:
                slides_out.append(f"Slide {idx}: " + " ".join(paras))
    return "\n".join(slides_out)


def _decode_pdf_literal_string(raw: bytes) -> str:
    out = bytearray()
    i = 0
    n = len(raw)
    esc_map = {
        ord("n"): ord("\n"),
        ord("r"): ord("\r"),
        ord("t"): ord("\t"),
        ord("b"): 8,
        ord("f"): 12,
        ord("("): ord("("),
        ord(")"): ord(")"),
        ord("\\"): ord("\\"),
    }
    while i < n:
        b = raw[i]
        if b == ord("\\") and i + 1 < n:
            nxt = raw[i + 1]
            if nxt in esc_map:
                out.append(esc_map[nxt])
                i += 2
                continue
            if ord("0") <= nxt <= ord("7"):
                oct_digits = bytes([nxt])
                j = i + 2
                while j < n and len(oct_digits) < 3 and ord("0") <= raw[j] <= ord("7"):
                    oct_digits += bytes([raw[j]])
                    j += 1
                out.append(int(oct_digits, 8) & 0xFF)
                i = j
                continue
            if nxt in (ord("\r"), ord("\n")):
                i += 2
                if i < n and raw[i - 1] == ord("\r") and raw[i] == ord("\n"):
                    i += 1
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(b)
        i += 1
    if out.startswith(b"\xfe\xff"):
        return bytes(out[2:]).decode("utf-16-be", errors="ignore")
    return bytes(out).decode("latin-1", errors="ignore")


def _decode_pdf_hex_string(hex_bytes: bytes) -> str:
    clean = re.sub(rb"[^0-9A-Fa-f]", b"", hex_bytes)
    if not clean:
        return ""
    if len(clean) % 2 == 1:
        clean += b"0"
    raw = bytes.fromhex(clean.decode("ascii"))
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="ignore")
    if len(raw) >= 4 and len(raw) % 2 == 0 and raw[0] == 0:
        return raw.decode("utf-16-be", errors="ignore")
    return raw.decode("latin-1", errors="ignore")


def extract_pdf_text_in_memory(raw_bytes: bytes) -> str:
    if not raw_bytes:
        return ""
    # Prefer pypdf / PyPDF2 if installed in the Python environment
    for mod_name in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(mod_name)
            reader = mod.PdfReader(io.BytesIO(raw_bytes))
            pages_txt = []
            for p in reader.pages[:60]:
                pt = (p.extract_text() or "").strip()
                if pt:
                    pages_txt.append(pt)
            if pages_txt:
                return "\n\n".join(pages_txt)
        except ImportError:
            pass
        except Exception:
            pass

    # Pure-stdlib in-memory PDF content-stream extractor (FlateDecode + uncompressed BT..ET)
    chunks: list[str] = []
    stream_re = re.compile(rb"stream(?:\r\n|\n)(.*?)(?:\r\n|\n)?endstream", re.DOTALL)
    bt_re = re.compile(rb"BT\b(.*?)\bET", re.DOTALL)
    tok_re = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]{2,}>")

    candidate_streams: list[bytes] = []
    for m in stream_re.finditer(raw_bytes):
        s_data = m.group(1)
        decomp = None
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                decomp = zlib.decompress(s_data, wbits)
                break
            except Exception:
                continue
        candidate_streams.append(decomp if decomp is not None else s_data)
        if len(candidate_streams) >= 160:
            break
    if not candidate_streams:
        candidate_streams.append(raw_bytes)

    for c_bytes in candidate_streams:
        if b"BT" not in c_bytes:
            continue
        for bt_m in bt_re.finditer(c_bytes):
            block = bt_m.group(1)
            pieces: list[str] = []
            for tm in tok_re.finditer(block):
                tok = tm.group(0)
                if tok.startswith(b"(") and tok.endswith(b")"):
                    txt = _decode_pdf_literal_string(tok[1:-1])
                elif tok.startswith(b"<") and tok.endswith(b">"):
                    txt = _decode_pdf_hex_string(tok[1:-1])
                else:
                    txt = ""
                if txt:
                    pieces.append(txt)
            joined = re.sub(r"\s+", " ", "".join(pieces)).strip()
            if joined and any(ch.isalnum() for ch in joined):
                chunks.append(joined)
    return "\n".join(chunks)


def extract_csv_text_in_memory(raw_bytes: bytes) -> str:
    txt = raw_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(txt))
    lines: list[str] = []
    for idx, row in enumerate(reader):
        if idx >= 150:
            break
        cells = [re.sub(r"\s+", " ", c).strip() for c in row[:16] if c and c.strip()]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def extract_document_text_from_bytes(raw_bytes: bytes, mime_type: str, name: str) -> str:
    if not raw_bytes:
        return ""
    m = (mime_type or "").strip().lower()
    ext = Path(name or "").suffix.lower()
    try:
        if m == DOCX_MIME or ext == ".docx":
            return extract_docx_text_in_memory(raw_bytes)
        if m == XLSX_MIME or ext == ".xlsx":
            return extract_xlsx_text_in_memory(raw_bytes)
        if m == PPTX_MIME or ext == ".pptx":
            return extract_pptx_text_in_memory(raw_bytes)
        if m == "application/pdf" or ext == ".pdf" or raw_bytes.startswith(b"%PDF-"):
            return extract_pdf_text_in_memory(raw_bytes)
        if m in ("text/csv", "text/tab-separated-values") or ext in (".csv", ".tsv"):
            return extract_csv_text_in_memory(raw_bytes)
        if m.startswith("text/") or ext in (".md", ".txt", ".json"):
            return raw_bytes.decode("utf-8-sig", errors="replace")
    except Exception:
        return ""
    return ""


# ── Single-Account Microsoft OneDrive OAuth 2.0 + PKCE Manager ───────────


class OneDriveOAuthManager:
    """Manages profile-scoped Microsoft OneDrive OAuth 2.0 + PKCE inside `vault.enc`."""

    def __init__(
        self,
        runtime: Any,
        token_requester: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
        userinfo_requester: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.runtime = runtime
        self.passwords = runtime.passwords
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._servers: dict[str, ThreadingHTTPServer] = {}
        self._token_requester = token_requester
        self._userinfo_requester = userinfo_requester

    def _require_unlocked(self) -> str:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            raise PermissionError("Unlock a profile with its 6-digit PIN first.")
        return str(self.passwords.active_profile_id)

    @staticmethod
    def _auth_url(tenant: str) -> str:
        t = (tenant or DEFAULT_ONEDRIVE_TENANT).strip() or DEFAULT_ONEDRIVE_TENANT
        return f"https://login.microsoftonline.com/{urllib.parse.quote(t)}/oauth2/v2.0/authorize"

    @staticmethod
    def _token_url(tenant: str) -> str:
        t = (tenant or DEFAULT_ONEDRIVE_TENANT).strip() or DEFAULT_ONEDRIVE_TENANT
        return f"https://login.microsoftonline.com/{urllib.parse.quote(t)}/oauth2/v2.0/token"

    def _http_post_form(self, url: str, form_data: dict[str, str]) -> dict[str, Any]:
        if self._token_requester is not None:
            return self._token_requester(url, form_data)
        encoded = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as he:
            detail = ""
            try:
                detail = he.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            raise RuntimeError(f"Microsoft OAuth endpoint returned HTTP {he.code}: {detail or he}") from he

    def _http_get_me(self, access_token: str) -> dict[str, Any]:
        if self._userinfo_requester is not None:
            return self._userinfo_requester(access_token)
        req = urllib.request.Request(
            f"{GRAPH_BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def save_client_config(
        self,
        *,
        client_id: str = "",
        tenant_id: str = "",
        client_secret: str = "",
        redirect_port: int | None = None,
    ) -> dict[str, Any]:
        self._require_unlocked()
        env_now = self.passwords.get_unlocked_credentials_map()
        cid = (
            (client_id or "").strip()
            or env_now.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID", "").strip()
            or (os.environ.get("ONEDRIVE_CLIENT_ID") or "").strip()
        )
        if not cid:
            raise ValueError("Microsoft Application (client) ID is required for OneDrive sign-in.")
        tid = (
            (tenant_id or "").strip()
            or env_now.get(f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID", "").strip()
            or DEFAULT_ONEDRIVE_TENANT
        )
        csec = (client_secret or "").strip()
        updates: dict[str, str] = {
            f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID": cid,
            f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID": tid,
        }
        if csec:
            updates[f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_SECRET"] = csec
        if redirect_port is not None and int(redirect_port) > 0:
            updates[f"{ONEDRIVE_VAULT_PREFIX}_REDIRECT_PORT"] = str(int(redirect_port))
        self.passwords.update_vault_entries(updates)
        return self.get_status()

    def get_status(self, session_id: str = "") -> dict[str, Any]:
        unlocked = bool(self.passwords.unlocked and self.passwords.active_profile_id)
        if not unlocked:
            return {
                "ok": True,
                "unlocked": False,
                "configured": False,
                "signed_in": False,
                "has_client_id": False,
                "masked_client_id": "",
                "tenant_id": DEFAULT_ONEDRIVE_TENANT,
                "email": "",
                "name": "",
                "scopes": list(DEFAULT_ONEDRIVE_SCOPES),
                "expires_at": 0.0,
                "session": None,
            }

        env_map = self.passwords.get_unlocked_credentials_map()
        cid = (
            env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID", "").strip()
            or (os.environ.get("ONEDRIVE_CLIENT_ID") or "").strip()
        )
        tid = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID", "").strip() or DEFAULT_ONEDRIVE_TENANT
        access_tok = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_ACCESS_TOKEN", "").strip()
        refresh_tok = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN", "").strip()
        email = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_EMAIL", "").strip()
        name = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_NAME", "").strip()
        scopes_str = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_SCOPES", "").strip()
        scopes = [s for s in scopes_str.split() if s] if scopes_str else list(DEFAULT_ONEDRIVE_SCOPES)
        try:
            expires_at = float(env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_EXPIRY", "0") or 0.0)
        except ValueError:
            expires_at = 0.0

        sess_out = None
        if session_id:
            with self._lock:
                s = self._sessions.get(session_id)
                if s and s.get("profile_id") == self.passwords.active_profile_id:
                    sess_out = {
                        "session_id": s["session_id"],
                        "status": s["status"],
                        "email": s.get("email") or "",
                        "error": s.get("error") or "",
                        "redirect_uri": s.get("redirect_uri") or "",
                    }

        return {
            "ok": True,
            "unlocked": True,
            "configured": bool(cid),
            "signed_in": bool((access_tok or refresh_tok) and email),
            "has_client_id": bool(cid),
            "masked_client_id": _mask_client_id(cid),
            "tenant_id": tid,
            "email": email,
            "name": name,
            "scopes": scopes,
            "expires_at": expires_at,
            "token_valid": bool(access_tok and expires_at > time.time() + 30.0),
            "session": sess_out,
        }

    def start_login(
        self,
        *,
        client_id: str = "",
        tenant_id: str = "",
        client_secret: str = "",
        login_hint: str = "",
        redirect_port: int | None = None,
        redirect_host: str = "localhost",
        callback_path: str = "/oauth/onedrive/callback",
    ) -> dict[str, Any]:
        profile_id = self._require_unlocked()
        if client_id or tenant_id or client_secret or redirect_port is not None:
            self.save_client_config(
                client_id=client_id,
                tenant_id=tenant_id,
                client_secret=client_secret,
                redirect_port=redirect_port,
            )

        env_map = self.passwords.get_unlocked_credentials_map()
        cid = (
            env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID", "").strip()
            or (os.environ.get("ONEDRIVE_CLIENT_ID") or "").strip()
        )
        if not cid:
            raise ValueError(
                "Enter your Microsoft Application (client) ID first to authorize OneDrive via PKCE."
            )
        tid = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID", "").strip() or DEFAULT_ONEDRIVE_TENANT
        try:
            saved_port = int(env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_REDIRECT_PORT", "0") or 0)
        except ValueError:
            saved_port = 0
        bind_port = int(redirect_port if redirect_port is not None else saved_port or 0)
        host_norm = "127.0.0.1" if redirect_host == "127.0.0.1" else "localhost"
        path_norm = callback_path if callback_path.startswith("/") else f"/{callback_path}"

        code_verifier = secrets.token_urlsafe(64)[:96]
        challenge_digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_digest).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(24)
        session_id = f"odoauth-{secrets.token_hex(8)}"

        self.stop_pending_servers()
        mgr = self

        class _CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path != path_norm:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                code = (qs.get("code") or [""])[0]
                cb_state = (qs.get("state") or [""])[0]
                err = (qs.get("error") or [""])[0]
                err_desc = (qs.get("error_description") or [""])[0]

                res = mgr.complete_callback(
                    session_id=session_id,
                    state=cb_state,
                    code=code,
                    error=err_desc or err,
                )
                ok = bool(res.get("ok"))
                email = str(res.get("email") or "")
                headline = f"OneDrive connected as {email}" if ok else "OneDrive sign-in failed"
                detail = (
                    "Authorization complete. Satz stored encrypted OneDrive tokens locally in your profile vault."
                    if ok
                    else str(res.get("error") or "OAuth exchange did not succeed.")
                )
                body = _render_callback_html(
                    ok,
                    headline,
                    detail,
                    page_title="OneDrive Auth · Satz",
                )
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

                def _shutdown_later() -> None:
                    time.sleep(0.35)
                    mgr._close_server(session_id)

                threading.Thread(target=_shutdown_later, daemon=True).start()

        server = ThreadingHTTPServer(("127.0.0.1", bind_port), _CallbackHandler)
        actual_port = server.server_address[1]
        redirect_uri = f"http://{host_norm}:{actual_port}{path_norm}"

        with self._lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "profile_id": profile_id,
                "status": "pending",
                "state": state,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "tenant_id": tid,
                "scopes": list(DEFAULT_ONEDRIVE_SCOPES),
                "email": "",
                "error": "",
                "created_at": time.time(),
            }
            self._servers[session_id] = server

        threading.Thread(target=server.serve_forever, daemon=True, name=f"satz-odoauth-{session_id}").start()

        def _auto_expire() -> None:
            time.sleep(600.0)
            with self._lock:
                s = self._sessions.get(session_id)
                if s and s.get("status") == "pending":
                    s["status"] = "expired"
                    s["error"] = "OneDrive OAuth session timed out after 10 minutes."
            self._close_server(session_id)

        threading.Thread(target=_auto_expire, daemon=True).start()

        params = {
            "client_id": cid,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(DEFAULT_ONEDRIVE_SCOPES),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "select_account",
        }
        hint = (login_hint or env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_EMAIL") or "").strip()
        if hint:
            params["login_hint"] = hint
        auth_url = f"{self._auth_url(tid)}?{urllib.parse.urlencode(params)}"
        return {
            "ok": True,
            "session_id": session_id,
            "auth_url": auth_url,
            "redirect_uri": redirect_uri,
            "scopes": list(DEFAULT_ONEDRIVE_SCOPES),
        }

    def complete_callback(
        self,
        *,
        session_id: str,
        state: str,
        code: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return {"ok": False, "error": "OneDrive OAuth session not found or expired."}
            if sess.get("profile_id") != self.passwords.active_profile_id or not self.passwords.unlocked:
                sess["status"] = "error"
                sess["error"] = "Profile was locked or switched during OneDrive sign-in."
                return {"ok": False, "error": sess["error"]}
            expected_state = str(sess.get("state") or "")
            if not state or not hmac.compare_digest(state.encode("utf-8"), expected_state.encode("utf-8")):
                sess["status"] = "error"
                sess["error"] = "Invalid OAuth CSRF state parameter."
                return {"ok": False, "error": sess["error"]}
            if error:
                sess["status"] = "error"
                sess["error"] = error
                return {"ok": False, "error": error}
            if not code:
                sess["status"] = "error"
                sess["error"] = "Missing authorization code from Microsoft redirect."
                return {"ok": False, "error": sess["error"]}

            env_map = self.passwords.get_unlocked_credentials_map()
            cid = (
                env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID", "").strip()
                or (os.environ.get("ONEDRIVE_CLIENT_ID") or "").strip()
            )
            csec = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_SECRET", "").strip()
            tid = str(sess.get("tenant_id") or DEFAULT_ONEDRIVE_TENANT)
            redirect_uri = str(sess["redirect_uri"])
            code_verifier = str(sess["code_verifier"])

        try:
            form: dict[str, str] = {
                "client_id": cid,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "scope": " ".join(DEFAULT_ONEDRIVE_SCOPES),
            }
            if csec:
                form["client_secret"] = csec
            tok_resp = self._http_post_form(self._token_url(tid), form)
            access_tok = str(tok_resp.get("access_token") or "").strip()
            if not access_tok:
                raise RuntimeError(f"Token response missing access_token: {tok_resp}")
            refresh_tok = str(
                tok_resp.get("refresh_token") or env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN") or ""
            ).strip()
            expires_in = float(tok_resp.get("expires_in") or 3600.0)
            expiry_ts = time.time() + max(60.0, expires_in)
            granted_scope = str(tok_resp.get("scope") or " ".join(DEFAULT_ONEDRIVE_SCOPES)).strip()

            me = self._http_get_me(access_tok)
            email = str(
                me.get("mail")
                or me.get("userPrincipalName")
                or env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_EMAIL")
                or "onedrive-user"
            ).strip()
            name = str(me.get("displayName") or env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_NAME") or email).strip()

            updates: dict[str, str] = {
                f"{ONEDRIVE_VAULT_PREFIX}_ACCESS_TOKEN": access_tok,
                f"{ONEDRIVE_VAULT_PREFIX}_EXPIRY": str(round(expiry_ts, 3)),
                f"{ONEDRIVE_VAULT_PREFIX}_SCOPES": granted_scope,
                f"{ONEDRIVE_VAULT_PREFIX}_EMAIL": email,
                f"{ONEDRIVE_VAULT_PREFIX}_NAME": name,
            }
            if cid and not env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID"):
                updates[f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID"] = cid
            if refresh_tok:
                updates[f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN"] = refresh_tok
            self.passwords.update_vault_entries(updates)

            if getattr(self.runtime, "drives", None) is not None:
                try:
                    self.runtime.drives.on_onedrive_connected(email=email, name=name)
                except Exception as de:
                    self.runtime.record_error("onedrive_oauth_link", de)

            with self._lock:
                sess["status"] = "authorized"
                sess["email"] = email
                sess["error"] = ""

            return {"ok": True, "status": "authorized", "email": email, "name": name}
        except Exception as exc:
            with self._lock:
                sess["status"] = "error"
                sess["error"] = str(exc)
            return {"ok": False, "error": str(exc)}

    def get_valid_access_token(self, force_refresh: bool = False) -> str:
        self._require_unlocked()
        env_map = self.passwords.get_unlocked_credentials_map()
        access_tok = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_ACCESS_TOKEN", "").strip()
        refresh_tok = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN", "").strip()
        cid = (
            env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID", "").strip()
            or (os.environ.get("ONEDRIVE_CLIENT_ID") or "").strip()
        )
        csec = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_SECRET", "").strip()
        tid = env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID", "").strip() or DEFAULT_ONEDRIVE_TENANT
        try:
            expiry_ts = float(env_map.get(f"{ONEDRIVE_VAULT_PREFIX}_EXPIRY", "0") or 0.0)
        except ValueError:
            expiry_ts = 0.0

        if not force_refresh and access_tok and expiry_ts > (time.time() + 60.0):
            return access_tok
        if not refresh_tok or not cid:
            if access_tok and not force_refresh:
                return access_tok
            raise PermissionError("OneDrive refresh token missing. Sign in to OneDrive again.")

        form: dict[str, str] = {
            "client_id": cid,
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "scope": " ".join(DEFAULT_ONEDRIVE_SCOPES),
        }
        if csec:
            form["client_secret"] = csec
        tok_resp = self._http_post_form(self._token_url(tid), form)
        new_access = str(tok_resp.get("access_token") or "").strip()
        if not new_access:
            raise RuntimeError(f"Failed refreshing OneDrive token: {tok_resp}")
        expires_in = float(tok_resp.get("expires_in") or 3600.0)
        updates = {
            f"{ONEDRIVE_VAULT_PREFIX}_ACCESS_TOKEN": new_access,
            f"{ONEDRIVE_VAULT_PREFIX}_EXPIRY": str(round(time.time() + max(60.0, expires_in), 3)),
        }
        if tok_resp.get("refresh_token"):
            updates[f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN"] = str(tok_resp["refresh_token"]).strip()
        self.passwords.update_vault_entries(updates)
        return new_access

    def disconnect(self, clear_client_config: bool = False) -> dict[str, Any]:
        self._require_unlocked()
        self.stop_pending_servers()
        keys = [
            f"{ONEDRIVE_VAULT_PREFIX}_ACCESS_TOKEN",
            f"{ONEDRIVE_VAULT_PREFIX}_REFRESH_TOKEN",
            f"{ONEDRIVE_VAULT_PREFIX}_EXPIRY",
            f"{ONEDRIVE_VAULT_PREFIX}_EMAIL",
            f"{ONEDRIVE_VAULT_PREFIX}_NAME",
            f"{ONEDRIVE_VAULT_PREFIX}_SCOPES",
        ]
        if clear_client_config:
            keys.extend(
                [
                    f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_ID",
                    f"{ONEDRIVE_VAULT_PREFIX}_CLIENT_SECRET",
                    f"{ONEDRIVE_VAULT_PREFIX}_TENANT_ID",
                    f"{ONEDRIVE_VAULT_PREFIX}_REDIRECT_PORT",
                ]
            )
        self.passwords.delete_vault_keys(keys)
        return self.get_status()

    def _close_server(self, session_id: str) -> None:
        with self._lock:
            srv = self._servers.pop(session_id, None)
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass

    def stop_pending_servers(self) -> None:
        with self._lock:
            sids = list(self._servers.keys())
        for sid in sids:
            self._close_server(sid)


# ── Unified Cloud Drives Catalog, Sync & Zero-Disk Brain Indexer ─────────


class SatzDrivesManager:
    """
    Manages the profile-scoped `drives.sqlite` unified catalog across Google Drive
    (`hellofresh.com`) and Microsoft OneDrive, single-level folder browsing with
    breadcrumbs, filters, global FTS5 search, zero-disk 90-day Brain indexing,
    and local Chat source retrieval.
    """

    def __init__(
        self,
        runtime: Any,
        http_json_getter: Callable[[str, str], dict[str, Any]] | None = None,
        http_bytes_getter: Callable[[str, str, int], bytes] | None = None,
    ) -> None:
        self.runtime = runtime
        self.passwords = runtime.passwords
        self.onedrive_auth = OneDriveOAuthManager(runtime)
        self._db_lock = threading.RLock()
        self._sync_lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._bound_profile_id: str | None = "__UNBOUND__"
        self._syncing_providers: set[str] = set()
        self._indexing_active: bool = False
        self._http_json_getter = http_json_getter
        self._http_bytes_getter = http_bytes_getter
        self.rebind_profile(defer_sync_start=True)

    # ── Profile & SQLite Lifecycle ───────────────────────────────────────

    def rebind_profile(self, defer_sync_start: bool = False) -> None:
        is_unlocked = bool(self.passwords.unlocked and self.passwords.active_profile_id)
        pid = str(self.passwords.active_profile_id) if is_unlocked else None
        with self._db_lock:
            if self._bound_profile_id == pid and self._conn is not None:
                return
            self._close_conn_locked()
            db_path = self.passwords.get_profile_drives_db_path(pid)
            db_target = ":memory:" if str(db_path) == ":memory:" else str(db_path)
            if db_target != ":memory:":
                Path(db_target).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_target, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._init_tables(conn)
            self._conn = conn
            self._bound_profile_id = pid

        if not is_unlocked:
            self.onedrive_auth.stop_pending_servers()
        elif not defer_sync_start:
            st = self.get_status()
            if st["google"]["connected"] or st["onedrive"]["connected"]:
                self.trigger_background_sync()

    def _close_conn_locked(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def close(self) -> None:
        self.onedrive_auth.stop_pending_servers()
        with self._db_lock:
            self._close_conn_locked()

    def _get_conn(self) -> sqlite3.Connection:
        self.rebind_profile(defer_sync_start=True)
        assert self._conn is not None
        return self._conn

    @staticmethod
    def _init_tables(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS drive_sync_state (
                provider TEXT PRIMARY KEY,
                account_email TEXT NOT NULL DEFAULT '',
                account_name TEXT NOT NULL DEFAULT '',
                root_remote_id TEXT NOT NULL DEFAULT '',
                delta_token TEXT NOT NULL DEFAULT '',
                last_synced_at REAL NOT NULL DEFAULT 0.0,
                total_files INTEGER NOT NULL DEFAULT 0,
                indexed_docs INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'idle',
                last_error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS drive_items (
                item_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                remote_id TEXT NOT NULL,
                name TEXT NOT NULL,
                is_folder INTEGER NOT NULL DEFAULT 0,
                is_shortcut INTEGER NOT NULL DEFAULT 0,
                target_id TEXT NOT NULL DEFAULT '',
                target_mime TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                file_category TEXT NOT NULL DEFAULT 'other',
                parent_id TEXT NOT NULL DEFAULT '',
                is_root INTEGER NOT NULL DEFAULT 0,
                shared_orphan INTEGER NOT NULL DEFAULT 0,
                resolved_path TEXT NOT NULL DEFAULT '',
                path_crumbs_json TEXT NOT NULL DEFAULT '[]',
                owner_name TEXT NOT NULL DEFAULT '',
                owner_email TEXT NOT NULL DEFAULT '',
                is_me INTEGER NOT NULL DEFAULT 0,
                modified_at REAL NOT NULL DEFAULT 0.0,
                viewed_at REAL NOT NULL DEFAULT 0.0,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                web_url TEXT NOT NULL DEFAULT '',
                download_url TEXT NOT NULL DEFAULT '',
                revision_id TEXT NOT NULL DEFAULT '',
                trashed INTEGER NOT NULL DEFAULT 0,
                core_summary TEXT NOT NULL DEFAULT '',
                brain_slug TEXT NOT NULL DEFAULT '',
                indexed_revision TEXT NOT NULL DEFAULT '',
                indexed_at REAL NOT NULL DEFAULT 0.0
            );

            CREATE INDEX IF NOT EXISTS idx_drive_items_parent
                ON drive_items(provider, parent_id, trashed);
            CREATE INDEX IF NOT EXISTS idx_drive_items_root
                ON drive_items(is_root, shared_orphan, trashed);
            CREATE INDEX IF NOT EXISTS idx_drive_items_modified
                ON drive_items(trashed, is_folder DESC, modified_at DESC);
            CREATE INDEX IF NOT EXISTS idx_drive_items_category
                ON drive_items(file_category, trashed);
            CREATE INDEX IF NOT EXISTS idx_drive_items_owner
                ON drive_items(owner_email, is_me, trashed);

            CREATE VIRTUAL TABLE IF NOT EXISTS drive_items_fts USING fts5(
                item_key UNINDEXED,
                name,
                resolved_path,
                owner_name,
                owner_email,
                core_summary
            );
            """
        )
        conn.commit()

    # ── HTTP Helpers (RAM Only) ──────────────────────────────────────────

    def _http_get_json(self, url: str, access_token: str) -> dict[str, Any]:
        if self._http_json_getter is not None:
            return self._http_json_getter(url, access_token)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as he:
            detail = ""
            try:
                detail = he.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            raise RuntimeError(f"Drive API HTTP {he.code}: {detail or he}") from he

    def _http_get_bytes_in_memory(
        self,
        url: str,
        access_token: str,
        max_bytes: int = MAX_EXTRACT_BYTES,
    ) -> bytes:
        """Streams response strictly into a bounded `io.BytesIO` buffer in RAM; never touches disk."""
        if self._http_bytes_getter is not None:
            raw = self._http_bytes_getter(url, access_token, max_bytes)
            return raw[:max_bytes]
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        buf = io.BytesIO()
        try:
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                total = 0
                while True:
                    chunk = resp.read(65_536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        buf.write(chunk[: max(0, max_bytes - (total - len(chunk)))])
                        break
                    buf.write(chunk)
            return buf.getvalue()
        finally:
            buf.close()

    # ── Onboarding & Status ──────────────────────────────────────────────

    def start_google_drive_connect(
        self,
        *,
        client_id: str = "",
        client_secret: str = "",
        client_secret_json: str = "",
        login_hint: str = "",
        hd: str = "hellofresh.com",
        redirect_port: int | None = None,
    ) -> dict[str, Any]:
        g_status = self.runtime.google_auth.get_status()
        existing_scopes = g_status.get("scopes") or []
        keep_gmail = "https://mail.google.com/" in existing_scopes and bool(g_status.get("signed_in"))
        return self.runtime.google_auth.start_login(
            client_id=client_id,
            client_secret=client_secret,
            client_secret_json=client_secret_json,
            connect_gmail=keep_gmail,
            connect_drive=True,
            login_hint=login_hint,
            hd=hd,
            redirect_port=redirect_port,
        )

    def on_google_connected(self, email: str, name: str = "") -> None:
        with self._db_lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO drive_sync_state (provider, account_email, account_name, status)
                VALUES ('gdrive', ?, ?, 'idle')
                ON CONFLICT(provider) DO UPDATE SET
                    account_email = excluded.account_email,
                    account_name = excluded.account_name
                """,
                (email, name or email),
            )
            conn.commit()
        if not getattr(self.runtime.brain, "locked", True):
            try:
                self.runtime.brain.upsert_entity(
                    entity_type="account",
                    name="Google Drive",
                    summary=f"Connected Google Drive account ({email}).",
                    attributes={"provider": "Google Drive", "email": email},
                    actor="drives/oauth_connect",
                )
            except Exception:
                pass
        self.trigger_background_sync(providers=["gdrive"])

    def on_onedrive_connected(self, email: str, name: str = "") -> None:
        with self._db_lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO drive_sync_state (provider, account_email, account_name, status)
                VALUES ('onedrive', ?, ?, 'idle')
                ON CONFLICT(provider) DO UPDATE SET
                    account_email = excluded.account_email,
                    account_name = excluded.account_name
                """,
                (email, name or email),
            )
            conn.commit()
        if not getattr(self.runtime.brain, "locked", True):
            try:
                self.runtime.brain.upsert_entity(
                    entity_type="account",
                    name="Microsoft OneDrive",
                    summary=f"Connected Microsoft OneDrive account ({email}).",
                    attributes={"provider": "OneDrive", "email": email},
                    actor="drives/oauth_connect",
                )
            except Exception:
                pass
        self.trigger_background_sync(providers=["onedrive"])

    def disconnect_provider(
        self,
        provider: str,
        *,
        purge_index: bool = True,
        clear_client_config: bool = False,
    ) -> dict[str, Any]:
        prov = (provider or "").strip().lower()
        if prov in ("gdrive", "google"):
            g_st = self.runtime.google_auth.get_status()
            scopes = [
                s
                for s in (g_st.get("scopes") or [])
                if s not in (GOOGLE_DRIVE_READONLY_SCOPE, "https://www.googleapis.com/auth/drive")
            ]
            if "https://mail.google.com/" in scopes and not clear_client_config:
                # Preserve Gmail OAuth session if Gmail is also using this profile vault
                self.passwords.update_vault_entries({"GOOGLE_OAUTH_SCOPES": " ".join(scopes)})
            else:
                self.runtime.google_auth.disconnect(clear_client_config=clear_client_config)
            prov = "gdrive"
        elif prov == "onedrive":
            self.onedrive_auth.disconnect(clear_client_config=clear_client_config)
        else:
            raise ValueError(f"Unsupported drive provider: {provider}")

        if purge_index:
            self._purge_provider_data(prov)
        return self.get_status()

    def _purge_provider_data(self, provider: str) -> None:
        slugs_to_remove: list[str] = []
        urls_to_remove: list[str] = []
        with self._db_lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT item_key, brain_slug, web_url FROM drive_items WHERE provider = ?",
                (provider,),
            ).fetchall()
            for r in rows:
                if r["brain_slug"]:
                    slugs_to_remove.append(str(r["brain_slug"]))
                if r["web_url"]:
                    urls_to_remove.append(str(r["web_url"]))
            conn.execute("DELETE FROM drive_items WHERE provider = ?", (provider,))
            conn.execute("DELETE FROM drive_sync_state WHERE provider = ?", (provider,))
            self._rebuild_fts_locked(conn)
            conn.commit()

        if slugs_to_remove and not getattr(self.runtime.brain, "locked", True):
            for slug in slugs_to_remove:
                try:
                    self.runtime.brain.delete_entity(slug)
                except Exception:
                    pass
        if urls_to_remove and hasattr(self.runtime, "store") and self.runtime.store is not None:
            with self.runtime.store_lock:
                for u in urls_to_remove:
                    self.runtime.store.db.execute(
                        "DELETE FROM passages WHERE url = ? AND question LIKE '[conv:drives]%'",
                        (u,),
                    )
                    self.runtime.store.db.execute(
                        "DELETE FROM satz_conv_passages WHERE conversation_id = 'drives' AND url = ?",
                        (u,),
                    )
                self.runtime.store.db.commit()

    def get_status(
        self,
        *,
        google_session_id: str = "",
        onedrive_session_id: str = "",
    ) -> dict[str, Any]:
        unlocked = bool(self.passwords.unlocked and self.passwords.active_profile_id)
        g_auth = self.runtime.google_auth.get_status(session_id=google_session_id)
        od_auth = self.onedrive_auth.get_status(session_id=onedrive_session_id)

        if not unlocked:
            return {
                "ok": True,
                "unlocked": False,
                "syncing": False,
                "indexing": False,
                "total_files": 0,
                "indexed_docs": 0,
                "last_synced_at": 0.0,
                "google": {
                    "provider": "gdrive",
                    "connected": False,
                    "configured": False,
                    "signed_in_gmail_only": False,
                    "email": "",
                    "name": "",
                    "total_files": 0,
                    "indexed_docs": 0,
                    "last_synced_at": 0.0,
                    "status": "locked",
                    "last_error": "",
                    "session": None,
                },
                "onedrive": {
                    "provider": "onedrive",
                    "connected": False,
                    "configured": False,
                    "email": "",
                    "name": "",
                    "tenant_id": DEFAULT_ONEDRIVE_TENANT,
                    "total_files": 0,
                    "indexed_docs": 0,
                    "last_synced_at": 0.0,
                    "status": "locked",
                    "last_error": "",
                    "session": None,
                },
            }

        with self._db_lock:
            conn = self._get_conn()
            sync_rows = {
                str(r["provider"]): dict(r)
                for r in conn.execute("SELECT * FROM drive_sync_state").fetchall()
            }
            counts = {
                str(r["provider"]): (int(r["cnt"]), int(r["icnt"]))
                for r in conn.execute(
                    """
                    SELECT provider,
                           COUNT(*) AS cnt,
                           SUM(CASE WHEN indexed_at > 0 THEN 1 ELSE 0 END) AS icnt
                    FROM drive_items
                    WHERE trashed = 0
                    GROUP BY provider
                    """
                ).fetchall()
            }

        g_sync = sync_rows.get("gdrive") or {}
        od_sync = sync_rows.get("onedrive") or {}
        g_cnt, g_icnt = counts.get("gdrive", (0, 0))
        od_cnt, od_icnt = counts.get("onedrive", (0, 0))

        g_connected = bool(g_auth.get("drive_authorized"))
        od_connected = bool(od_auth.get("signed_in"))

        last_sync = max(
            float(g_sync.get("last_synced_at") or 0.0),
            float(od_sync.get("last_synced_at") or 0.0),
        )

        return {
            "ok": True,
            "unlocked": True,
            "syncing": bool(self._syncing_providers),
            "indexing": bool(self._indexing_active),
            "total_files": g_cnt + od_cnt,
            "indexed_docs": g_icnt + od_icnt,
            "last_synced_at": last_sync,
            "google": {
                "provider": "gdrive",
                "connected": g_connected,
                "configured": bool(g_auth.get("configured")),
                "signed_in_gmail_only": bool(g_auth.get("signed_in") and not g_connected),
                "masked_client_id": str(g_auth.get("masked_client_id") or ""),
                "email": str(g_auth.get("email") or g_sync.get("account_email") or ""),
                "name": str(g_auth.get("name") or g_sync.get("account_name") or ""),
                "total_files": g_cnt,
                "indexed_docs": g_icnt,
                "last_synced_at": float(g_sync.get("last_synced_at") or 0.0),
                "status": "syncing" if "gdrive" in self._syncing_providers else str(g_sync.get("status") or "idle"),
                "last_error": str(g_sync.get("last_error") or ""),
                "session": g_auth.get("session"),
            },
            "onedrive": {
                "provider": "onedrive",
                "connected": od_connected,
                "configured": bool(od_auth.get("configured")),
                "masked_client_id": str(od_auth.get("masked_client_id") or ""),
                "tenant_id": str(od_auth.get("tenant_id") or DEFAULT_ONEDRIVE_TENANT),
                "email": str(od_auth.get("email") or od_sync.get("account_email") or ""),
                "name": str(od_auth.get("name") or od_sync.get("account_name") or ""),
                "total_files": od_cnt,
                "indexed_docs": od_icnt,
                "last_synced_at": float(od_sync.get("last_synced_at") or 0.0),
                "status": "syncing" if "onedrive" in self._syncing_providers else str(od_sync.get("status") or "idle"),
                "last_error": str(od_sync.get("last_error") or ""),
                "session": od_auth.get("session"),
            },
        }

    # ── Sync Engine (Google Drive & Microsoft OneDrive) ──────────────────

    def trigger_background_sync(
        self,
        providers: list[str] | None = None,
        full_resync: bool = False,
    ) -> dict[str, Any]:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return {"ok": False, "error": "Profile is locked."}
        pid = str(self.passwords.active_profile_id)

        def _worker() -> None:
            self.sync_now(providers=providers, full_resync=full_resync, expected_profile_id=pid)

        threading.Thread(target=_worker, daemon=True, name="satz-drives-sync").start()
        return {"ok": True, "queued": True}

    def sync_now(
        self,
        *,
        providers: list[str] | None = None,
        full_resync: bool = False,
        run_core_indexer: bool = True,
        expected_profile_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return {"ok": False, "error": "Unlock a profile first."}
        active_pid = str(self.passwords.active_profile_id)
        if expected_profile_id and expected_profile_id != active_pid:
            return {"ok": False, "error": "Profile changed."}

        st = self.get_status()
        wanted = [p.lower() for p in providers] if providers else ["gdrive", "onedrive"]
        synced: dict[str, Any] = {}

        with self._sync_lock:
            if "gdrive" in wanted and st["google"]["connected"]:
                self._syncing_providers.add("gdrive")
                try:
                    synced["gdrive"] = self._sync_google_drive(active_pid, full_resync=full_resync)
                except Exception as exc:
                    self._record_sync_error("gdrive", str(exc))
                    synced["gdrive"] = {"ok": False, "error": str(exc)}
                finally:
                    self._syncing_providers.discard("gdrive")

            if "onedrive" in wanted and st["onedrive"]["connected"]:
                self._syncing_providers.add("onedrive")
                try:
                    synced["onedrive"] = self._sync_onedrive(active_pid, full_resync=full_resync)
                except Exception as exc:
                    self._record_sync_error("onedrive", str(exc))
                    synced["onedrive"] = {"ok": False, "error": str(exc)}
                finally:
                    self._syncing_providers.discard("onedrive")

            indexed_count = 0
            if run_core_indexer and not getattr(self.runtime, "pause_learning", False):
                self._indexing_active = True
                try:
                    indexed_count = self.run_core_content_index_pass(expected_profile_id=active_pid)
                finally:
                    self._indexing_active = False

        return {
            "ok": True,
            "synced": synced,
            "indexed_this_pass": indexed_count,
            "status": self.get_status(),
        }

    def _record_sync_error(self, provider: str, err_msg: str) -> None:
        with self._db_lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO drive_sync_state (provider, status, last_error)
                VALUES (?, 'error', ?)
                ON CONFLICT(provider) DO UPDATE SET
                    status = 'error',
                    last_error = excluded.last_error
                """,
                (provider, err_msg[:400]),
            )
            conn.commit()

    def _sync_google_drive(self, profile_id: str, *, full_resync: bool = False) -> dict[str, Any]:
        token = self.runtime.google_auth.get_valid_access_token()
        g_status = self.runtime.google_auth.get_status()
        account_email = str(g_status.get("email") or "").strip()
        account_name = str(g_status.get("name") or account_email).strip()

        # Resolve canonical My Drive root ID so direct children of My Drive are tagged `is_root=1`
        root_info = self._http_get_json(f"{GDRIVE_FILES_URL}/root?fields=id,name", token)
        root_id = str(root_info.get("id") or "root").strip()

        with self._db_lock:
            conn = self._get_conn()
            state_row = conn.execute(
                "SELECT delta_token FROM drive_sync_state WHERE provider = 'gdrive'"
            ).fetchone()
            delta_token = "" if full_resync else str((state_row["delta_token"] if state_row else "") or "")

        upserted = 0
        fields_spec = (
            "id,name,mimeType,parents,trashed,modifiedTime,viewedByMeTime,size,"
            "webViewLink,owners(displayName,emailAddress,me),headRevisionId,md5Checksum,"
            "shortcutDetails(targetId,targetMimeType)"
        )

        if not delta_token:
            # Progressive pass 1: root items + top-200 recent files for immediate UI responsiveness
            fast_q = urllib.parse.urlencode(
                {
                    "q": "trashed = false",
                    "pageSize": "200",
                    "orderBy": "modifiedTime desc",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                    "fields": f"nextPageToken,files({fields_spec})",
                }
            )
            first_page = self._http_get_json(f"{GDRIVE_FILES_URL}?{fast_q}", token)
            first_files = list(first_page.get("files") or [])
            if first_files:
                upserted += self._ingest_gdrive_records(first_files, root_id=root_id, account_email=account_email)

            # Full catalog pagination
            page_token = str(first_page.get("nextPageToken") or "")
            pages_fetched = 1
            while page_token and pages_fetched < 50:
                if self.passwords.active_profile_id != profile_id or not self.passwords.unlocked:
                    break
                pq = urllib.parse.urlencode(
                    {
                        "q": "trashed = false",
                        "pageSize": "500",
                        "pageToken": page_token,
                        "orderBy": "modifiedTime desc",
                        "supportsAllDrives": "true",
                        "includeItemsFromAllDrives": "true",
                        "fields": f"nextPageToken,files({fields_spec})",
                    }
                )
                resp = self._http_get_json(f"{GDRIVE_FILES_URL}?{pq}", token)
                batch = list(resp.get("files") or [])
                if batch:
                    upserted += self._ingest_gdrive_records(batch, root_id=root_id, account_email=account_email)
                page_token = str(resp.get("nextPageToken") or "")
                pages_fetched += 1

            tok_resp = self._http_get_json(
                f"{GDRIVE_START_TOKEN_URL}?supportsAllDrives=true",
                token,
            )
            new_delta_token = str(tok_resp.get("startPageToken") or "")
        else:
            page_token = delta_token
            new_delta_token = delta_token
            pages_fetched = 0
            while page_token and pages_fetched < 50:
                cq = urllib.parse.urlencode(
                    {
                        "pageToken": page_token,
                        "pageSize": "500",
                        "supportsAllDrives": "true",
                        "includeItemsFromAllDrives": "true",
                        "fields": f"nextPageToken,newStartPageToken,changes(fileId,removed,file({fields_spec}))",
                    }
                )
                c_resp = self._http_get_json(f"{GDRIVE_CHANGES_URL}?{cq}", token)
                to_upsert: list[dict[str, Any]] = []
                removed_ids: list[str] = []
                for ch in c_resp.get("changes") or []:
                    fid = str(ch.get("fileId") or "").strip()
                    fobj = ch.get("file")
                    if ch.get("removed") or (isinstance(fobj, dict) and fobj.get("trashed")):
                        if fid:
                            removed_ids.append(fid)
                    elif isinstance(fobj, dict):
                        to_upsert.append(fobj)
                if removed_ids:
                    with self._db_lock:
                        conn = self._get_conn()
                        for rid in removed_ids:
                            conn.execute(
                                "UPDATE drive_items SET trashed = 1 WHERE item_key = ?",
                                (f"gdrive:{rid}",),
                            )
                        conn.commit()
                if to_upsert:
                    upserted += self._ingest_gdrive_records(to_upsert, root_id=root_id, account_email=account_email)
                if c_resp.get("newStartPageToken"):
                    new_delta_token = str(c_resp["newStartPageToken"])
                    break
                page_token = str(c_resp.get("nextPageToken") or "")
                pages_fetched += 1

        self._finalize_provider_sync(
            provider="gdrive",
            account_email=account_email,
            account_name=account_name,
            root_remote_id=root_id,
            delta_token=new_delta_token,
        )
        return {"ok": True, "upserted": upserted}

    def _ingest_gdrive_records(
        self,
        files: list[dict[str, Any]],
        *,
        root_id: str,
        account_email: str,
    ) -> int:
        rows_data: list[tuple[Any, ...]] = []
        acct_low = account_email.lower()
        for f in files:
            fid = str(f.get("id") or "").strip()
            if not fid or fid == root_id:
                continue
            name = str(f.get("name") or "Untitled").strip()
            mime = str(f.get("mimeType") or "").strip()
            trashed = 1 if f.get("trashed") else 0

            is_shortcut = 1 if mime == GOOGLE_SHORTCUT_MIME else 0
            sc_details = f.get("shortcutDetails") if isinstance(f.get("shortcutDetails"), dict) else {}
            target_id = str(sc_details.get("targetId") or "").strip() if is_shortcut else ""
            target_mime = str(sc_details.get("targetMimeType") or "").strip() if is_shortcut else ""

            effective_mime = target_mime if (is_shortcut and target_mime) else mime
            is_folder = 1 if effective_mime == GOOGLE_FOLDER_MIME else 0
            category = classify_file_category(effective_mime, name, is_folder=bool(is_folder))

            parents = [str(p).strip() for p in (f.get("parents") or []) if str(p).strip()]
            parent_id = parents[0] if parents else ""
            is_root = 1 if (parent_id and parent_id in (root_id, "root")) else 0

            owners = f.get("owners") if isinstance(f.get("owners"), list) else []
            primary_owner = owners[0] if owners and isinstance(owners[0], dict) else {}
            owner_email = str(primary_owner.get("emailAddress") or "").strip()
            owner_name = str(primary_owner.get("displayName") or owner_email or "").strip()
            is_me = 1 if (primary_owner.get("me") or (acct_low and owner_email.lower() == acct_low)) else 0

            mod_ts = _parse_iso_ts(f.get("modifiedTime"))
            view_ts = _parse_iso_ts(f.get("viewedByMeTime"))
            try:
                size_bytes = int(f.get("size") or 0)
            except (ValueError, TypeError):
                size_bytes = 0

            raw_web_url = str(f.get("webViewLink") or "").strip()
            if not raw_web_url:
                open_id = target_id if (is_shortcut and target_id) else fid
                if is_folder:
                    raw_web_url = f"https://drive.google.com/drive/folders/{open_id}"
                else:
                    raw_web_url = f"https://drive.google.com/file/d/{open_id}/view"
            web_url = append_google_authuser(raw_web_url, account_email)

            rev_id = str(
                f.get("headRevisionId")
                or f.get("md5Checksum")
                or f.get("modifiedTime")
                or ""
            ).strip()

            rows_data.append(
                (
                    f"gdrive:{fid}",
                    "gdrive",
                    fid,
                    name,
                    is_folder,
                    is_shortcut,
                    target_id,
                    target_mime,
                    effective_mime,
                    category,
                    "" if is_root else parent_id,
                    is_root,
                    owner_name,
                    owner_email,
                    is_me,
                    mod_ts,
                    view_ts,
                    size_bytes,
                    web_url,
                    "",
                    rev_id,
                    trashed,
                )
            )

        if not rows_data:
            return 0

        with self._db_lock:
            conn = self._get_conn()
            conn.executemany(
                """
                INSERT INTO drive_items (
                    item_key, provider, remote_id, name, is_folder, is_shortcut,
                    target_id, target_mime, mime_type, file_category, parent_id, is_root,
                    owner_name, owner_email, is_me, modified_at, viewed_at,
                    size_bytes, web_url, download_url, revision_id, trashed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_key) DO UPDATE SET
                    name = excluded.name,
                    is_folder = excluded.is_folder,
                    is_shortcut = excluded.is_shortcut,
                    target_id = excluded.target_id,
                    target_mime = excluded.target_mime,
                    mime_type = excluded.mime_type,
                    file_category = excluded.file_category,
                    parent_id = excluded.parent_id,
                    is_root = excluded.is_root,
                    owner_name = excluded.owner_name,
                    owner_email = excluded.owner_email,
                    is_me = excluded.is_me,
                    modified_at = excluded.modified_at,
                    viewed_at = CASE WHEN excluded.viewed_at > 0 THEN excluded.viewed_at ELSE drive_items.viewed_at END,
                    size_bytes = excluded.size_bytes,
                    web_url = excluded.web_url,
                    revision_id = excluded.revision_id,
                    trashed = excluded.trashed
                """,
                rows_data,
            )
            self._recompute_paths_locked(conn, "gdrive", root_id)
            self._rebuild_fts_locked(conn)
            conn.commit()
        return len(rows_data)

    def _sync_onedrive(self, profile_id: str, *, full_resync: bool = False) -> dict[str, Any]:
        token = self.onedrive_auth.get_valid_access_token()
        od_status = self.onedrive_auth.get_status()
        account_email = str(od_status.get("email") or "").strip()
        account_name = str(od_status.get("name") or account_email).strip()

        root_resp = self._http_get_json(f"{GRAPH_BASE_URL}/me/drive/root?$select=id,name,webUrl", token)
        root_id = str(root_resp.get("id") or "root").strip()

        with self._db_lock:
            conn = self._get_conn()
            state_row = conn.execute(
                "SELECT delta_token FROM drive_sync_state WHERE provider = 'onedrive'"
            ).fetchone()
            delta_link = "" if full_resync else str((state_row["delta_token"] if state_row else "") or "")

        next_url = delta_link or f"{GRAPH_BASE_URL}/me/drive/root/delta?$top=200"
        new_delta_link = delta_link
        upserted = 0
        pages = 0

        while next_url and pages < 50:
            if self.passwords.active_profile_id != profile_id or not self.passwords.unlocked:
                break
            resp = self._http_get_json(next_url, token)
            items = list(resp.get("value") or [])
            if items:
                upserted += self._ingest_onedrive_records(
                    items,
                    root_id=root_id,
                    account_email=account_email,
                )
            if resp.get("@odata.deltaLink"):
                new_delta_link = str(resp["@odata.deltaLink"])
                break
            next_url = str(resp.get("@odata.nextLink") or "")
            pages += 1

        # Also sync OneDrive "Shared with me" items so shared workbooks/docs appear in unified Drives
        try:
            shared_resp = self._http_get_json(f"{GRAPH_BASE_URL}/me/drive/sharedWithMe?$top=100", token)
            shared_items = list(shared_resp.get("value") or [])
            if shared_items:
                upserted += self._ingest_onedrive_records(
                    shared_items,
                    root_id=root_id,
                    account_email=account_email,
                    force_shared_orphan=True,
                )
        except Exception:
            pass

        self._finalize_provider_sync(
            provider="onedrive",
            account_email=account_email,
            account_name=account_name,
            root_remote_id=root_id,
            delta_token=new_delta_link,
        )
        return {"ok": True, "upserted": upserted}

    def _ingest_onedrive_records(
        self,
        items: list[dict[str, Any]],
        *,
        root_id: str,
        account_email: str,
        force_shared_orphan: bool = False,
    ) -> int:
        rows_data: list[tuple[Any, ...]] = []
        removed_keys: list[str] = []
        acct_low = account_email.lower()

        for it in items:
            iid = str(it.get("id") or "").strip()
            if not iid or iid == root_id or "root" in it:
                continue
            if "deleted" in it:
                removed_keys.append(f"onedrive:{iid}")
                continue

            remote_item = it.get("remoteItem") if isinstance(it.get("remoteItem"), dict) else {}
            source_obj = remote_item or it
            name = str(it.get("name") or source_obj.get("name") or "Untitled").strip()

            is_shortcut = 1 if remote_item else 0
            target_id = str(remote_item.get("id") or "").strip() if is_shortcut else ""
            is_folder = 1 if ("folder" in source_obj or "folder" in it) else 0

            file_info = source_obj.get("file") if isinstance(source_obj.get("file"), dict) else {}
            mime = str(file_info.get("mimeType") or (GOOGLE_FOLDER_MIME if is_folder else "")).strip()
            category = classify_file_category(mime, name, is_folder=bool(is_folder))

            parent_ref = it.get("parentReference") if isinstance(it.get("parentReference"), dict) else {}
            parent_id = str(parent_ref.get("id") or "").strip()
            parent_path = str(parent_ref.get("path") or "").strip()
            is_root = 0 if force_shared_orphan else (
                1 if (parent_id == root_id or parent_path.endswith("/drive/root:")) else 0
            )

            created_by = (source_obj.get("createdBy") or it.get("createdBy") or {})
            user_block = created_by.get("user") if isinstance(created_by, dict) else {}
            if not isinstance(user_block, dict):
                user_block = {}
            owner_email = str(user_block.get("email") or "").strip()
            owner_name = str(user_block.get("displayName") or owner_email or account_name_fallback(account_email)).strip()
            is_me = 1 if (not force_shared_orphan and (not owner_email or owner_email.lower() == acct_low)) else (
                1 if (acct_low and owner_email.lower() == acct_low) else 0
            )

            fs_info = source_obj.get("fileSystemInfo") if isinstance(source_obj.get("fileSystemInfo"), dict) else {}
            mod_ts = _parse_iso_ts(
                source_obj.get("lastModifiedDateTime")
                or it.get("lastModifiedDateTime")
                or fs_info.get("lastModifiedDateTime")
            )
            try:
                size_bytes = int(source_obj.get("size") or it.get("size") or 0)
            except (ValueError, TypeError):
                size_bytes = 0

            web_url = str(source_obj.get("webUrl") or it.get("webUrl") or "https://onedrive.live.com").strip()
            rev_id = str(it.get("cTag") or it.get("eTag") or source_obj.get("eTag") or mod_ts).strip()

            rows_data.append(
                (
                    f"onedrive:{iid}",
                    "onedrive",
                    iid,
                    name,
                    is_folder,
                    is_shortcut,
                    target_id,
                    mime if is_shortcut else "",
                    mime,
                    category,
                    "" if (is_root or force_shared_orphan) else parent_id,
                    is_root,
                    1 if force_shared_orphan else 0,
                    owner_name,
                    owner_email,
                    is_me,
                    mod_ts,
                    size_bytes,
                    web_url,
                    rev_id,
                    0,
                )
            )

        with self._db_lock:
            conn = self._get_conn()
            for rkey in removed_keys:
                conn.execute("UPDATE drive_items SET trashed = 1 WHERE item_key = ?", (rkey,))
            if rows_data:
                conn.executemany(
                    """
                    INSERT INTO drive_items (
                        item_key, provider, remote_id, name, is_folder, is_shortcut,
                        target_id, target_mime, mime_type, file_category, parent_id, is_root,
                        shared_orphan, owner_name, owner_email, is_me, modified_at,
                        size_bytes, web_url, revision_id, trashed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_key) DO UPDATE SET
                        name = excluded.name,
                        is_folder = excluded.is_folder,
                        is_shortcut = excluded.is_shortcut,
                        target_id = excluded.target_id,
                        target_mime = excluded.target_mime,
                        mime_type = excluded.mime_type,
                        file_category = excluded.file_category,
                        parent_id = excluded.parent_id,
                        is_root = excluded.is_root,
                        shared_orphan = CASE WHEN excluded.shared_orphan = 1 THEN 1 ELSE drive_items.shared_orphan END,
                        owner_name = excluded.owner_name,
                        owner_email = excluded.owner_email,
                        is_me = excluded.is_me,
                        modified_at = excluded.modified_at,
                        size_bytes = excluded.size_bytes,
                        web_url = excluded.web_url,
                        revision_id = excluded.revision_id,
                        trashed = excluded.trashed
                    """,
                    rows_data,
                )
            self._recompute_paths_locked(conn, "onedrive", root_id)
            self._rebuild_fts_locked(conn)
            conn.commit()
        return len(rows_data)

    def _recompute_paths_locked(self, conn: sqlite3.Connection, provider: str, root_id: str) -> None:
        rows = conn.execute(
            """
            SELECT item_key, remote_id, name, is_folder, parent_id, is_root, shared_orphan
            FROM drive_items
            WHERE provider = ? AND trashed = 0
            """,
            (provider,),
        ).fetchall()
        by_remote: dict[str, sqlite3.Row] = {str(r["remote_id"]): r for r in rows}

        updates: list[tuple[int, str, str, str]] = []
        for r in rows:
            chain: list[dict[str, str]] = []
            seen: set[str] = {str(r["remote_id"])}
            cur_parent = str(r["parent_id"] or "")
            reached_root = bool(r["is_root"])
            depth = 0
            while cur_parent and cur_parent != root_id and depth < 32:
                if cur_parent in seen:
                    break
                seen.add(cur_parent)
                p_row = by_remote.get(cur_parent)
                if p_row is None:
                    break
                chain.append(
                    {
                        "key": f"{provider}:{p_row['remote_id']}",
                        "name": str(p_row["name"]),
                        "provider": provider,
                    }
                )
                if p_row["is_root"]:
                    reached_root = True
                    break
                cur_parent = str(p_row["parent_id"] or "")
                depth += 1

            chain.reverse()
            is_orphan = 1 if (not reached_root and not r["is_root"] and not chain) else 0
            if not reached_root and not r["is_root"]:
                crumbs = [{"key": "__shared__", "name": "Shared with me", "provider": "shared"}, *chain]
            else:
                crumbs = chain
            resolved_path = " / ".join(c["name"] for c in crumbs) if crumbs else "Drives"
            updates.append(
                (
                    is_orphan,
                    resolved_path,
                    json.dumps(crumbs, ensure_ascii=False),
                    str(r["item_key"]),
                )
            )

        if updates:
            conn.executemany(
                """
                UPDATE drive_items
                SET shared_orphan = ?, resolved_path = ?, path_crumbs_json = ?
                WHERE item_key = ?
                """,
                updates,
            )

    @staticmethod
    def _rebuild_fts_locked(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM drive_items_fts")
        conn.execute(
            """
            INSERT INTO drive_items_fts (item_key, name, resolved_path, owner_name, owner_email, core_summary)
            SELECT item_key, name, resolved_path, owner_name, owner_email, core_summary
            FROM drive_items
            WHERE trashed = 0
            """
        )

    def _finalize_provider_sync(
        self,
        *,
        provider: str,
        account_email: str,
        account_name: str,
        root_remote_id: str,
        delta_token: str,
    ) -> None:
        now = time.time()
        with self._db_lock:
            conn = self._get_conn()
            cnt_row = conn.execute(
                """
                SELECT COUNT(*) AS cnt,
                       SUM(CASE WHEN indexed_at > 0 THEN 1 ELSE 0 END) AS icnt
                FROM drive_items
                WHERE provider = ? AND trashed = 0
                """,
                (provider,),
            ).fetchone()
            total = int(cnt_row["cnt"] or 0) if cnt_row else 0
            indexed = int(cnt_row["icnt"] or 0) if cnt_row else 0
            conn.execute(
                """
                INSERT INTO drive_sync_state (
                    provider, account_email, account_name, root_remote_id, delta_token,
                    last_synced_at, total_files, indexed_docs, status, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idle', '')
                ON CONFLICT(provider) DO UPDATE SET
                    account_email = excluded.account_email,
                    account_name = excluded.account_name,
                    root_remote_id = excluded.root_remote_id,
                    delta_token = CASE WHEN excluded.delta_token != '' THEN excluded.delta_token ELSE drive_sync_state.delta_token END,
                    last_synced_at = excluded.last_synced_at,
                    total_files = excluded.total_files,
                    indexed_docs = excluded.indexed_docs,
                    status = 'idle',
                    last_error = ''
                """,
                (provider, account_email, account_name, root_remote_id, delta_token, now, total, indexed),
            )
            conn.commit()

    # ── Zero-Disk 90-Day Core Content Indexer -> SatzBrain ───────────────

    def run_core_content_index_pass(
        self,
        *,
        limit: int = MAX_INDEX_DOCS_PER_PASS,
        expected_profile_id: str | None = None,
    ) -> int:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return 0
        if getattr(self.runtime, "pause_learning", False) or getattr(self.runtime.brain, "locked", True):
            return 0
        active_pid = str(self.passwords.active_profile_id)
        if expected_profile_id and expected_profile_id != active_pid:
            return 0

        cutoff_ts = time.time() - CORE_INDEX_WINDOW_SECS
        with self._db_lock:
            conn = self._get_conn()
            candidates = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT *
                    FROM drive_items
                    WHERE trashed = 0
                      AND is_folder = 0
                      AND (modified_at >= ? OR viewed_at >= ?)
                      AND (indexed_at = 0 OR indexed_revision != revision_id)
                    ORDER BY modified_at DESC
                    LIMIT ?
                    """,
                    (cutoff_ts, cutoff_ts, max(1, int(limit) * 2)),
                ).fetchall()
            ]

        indexed_ok = 0
        for row in candidates:
            if indexed_ok >= limit:
                break
            if self.passwords.active_profile_id != active_pid or not self.passwords.unlocked:
                break
            if getattr(self.runtime, "pause_learning", False):
                break
            if not is_core_indexable(
                str(row["file_category"]),
                str(row["mime_type"]),
                str(row["name"]),
                int(row["size_bytes"] or 0),
            ):
                continue
            try:
                raw_text = self._fetch_and_extract_item_in_memory(row)
                if not raw_text or not raw_text.strip():
                    # Mark revision checked so empty/unreadable docs do not spin every cycle
                    self._mark_item_indexed(
                        str(row["item_key"]),
                        revision_id=str(row["revision_id"]),
                        core_summary=str(row["core_summary"] or ""),
                        brain_slug=str(row["brain_slug"] or ""),
                    )
                    continue
                self._store_extracted_doc_in_brain(row, raw_text)
                indexed_ok += 1
            except Exception as exc:
                self.runtime.record_error("drives_core_index", f"{row.get('name')}: {exc}")

        if indexed_ok > 0:
            with self._db_lock:
                conn = self._get_conn()
                self._rebuild_fts_locked(conn)
                for prov in ("gdrive", "onedrive"):
                    icnt = conn.execute(
                        "SELECT COUNT(*) FROM drive_items WHERE provider = ? AND trashed = 0 AND indexed_at > 0",
                        (prov,),
                    ).fetchone()[0]
                    conn.execute(
                        "UPDATE drive_sync_state SET indexed_docs = ? WHERE provider = ?",
                        (int(icnt), prov),
                    )
                conn.commit()
        return indexed_ok

    def _fetch_and_extract_item_in_memory(self, row: dict[str, Any]) -> str:
        provider = str(row["provider"])
        remote_id = str(row["target_id"] or row["remote_id"])
        mime = str(row["mime_type"] or "").strip().lower()
        name = str(row["name"] or "")

        if provider == "gdrive":
            token = self.runtime.google_auth.get_valid_access_token()
            fid_q = urllib.parse.quote(remote_id, safe="")
            if mime == GOOGLE_DOC_MIME:
                url = f"{GDRIVE_FILES_URL}/{fid_q}/export?mimeType=text/plain"
                raw = self._http_get_bytes_in_memory(url, token)
                return raw.decode("utf-8-sig", errors="replace")
            if mime == GOOGLE_SHEET_MIME:
                url = f"{GDRIVE_FILES_URL}/{fid_q}/export?mimeType=text/csv"
                raw = self._http_get_bytes_in_memory(url, token)
                return extract_csv_text_in_memory(raw)
            if mime == GOOGLE_SLIDE_MIME:
                url = f"{GDRIVE_FILES_URL}/{fid_q}/export?mimeType=text/plain"
                raw = self._http_get_bytes_in_memory(url, token)
                return raw.decode("utf-8-sig", errors="replace")
            url = f"{GDRIVE_FILES_URL}/{fid_q}?alt=media&supportsAllDrives=true"
            raw = self._http_get_bytes_in_memory(url, token)
            return extract_document_text_from_bytes(raw, mime, name)

        if provider == "onedrive":
            token = self.onedrive_auth.get_valid_access_token()
            iid_q = urllib.parse.quote(remote_id, safe="")
            url = f"{GRAPH_BASE_URL}/me/drive/items/{iid_q}/content"
            raw = self._http_get_bytes_in_memory(url, token)
            return extract_document_text_from_bytes(raw, mime, name)

        return ""

    def _store_extracted_doc_in_brain(self, row: dict[str, Any], raw_text: str) -> None:
        from satz_brain import neutralize_brain_directives_in_source
        from src.planck3.candidates import rank_passages, split_sentences
        from src.planck3.util import norm_text
        from src.planck3.web import domain_of

        safe_text = neutralize_brain_directives_in_source(raw_text)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in safe_text.splitlines()]
        non_empty = [ln for ln in lines if ln]
        clean_text = "\n".join(non_empty)[:80_000]
        if not clean_text:
            return

        item_key = str(row["item_key"])
        name = str(row["name"] or "Untitled Document").strip()
        provider = str(row["provider"])
        prov_label = "Google Drive" if provider == "gdrive" else "OneDrive"
        category = str(row["file_category"] or "doc")
        resolved_path = str(row["resolved_path"] or "Drives")
        owner_name = str(row["owner_name"] or "").strip()
        owner_email = str(row["owner_email"] or "").strip()
        owner_disp = (
            f"{owner_name} <{owner_email}>"
            if (owner_name and owner_email and owner_name.lower() != owner_email.lower())
            else (owner_email or owner_name or "Me")
        )
        web_url = str(row["web_url"] or "").strip()
        mod_iso = _ts_to_iso(float(row["modified_at"] or 0.0))
        domain = domain_of(web_url) if web_url else ("drive.google.com" if provider == "gdrive" else "onedrive.live.com")

        lead_snippet = re.sub(r"\s+", " ", " ".join(non_empty[:4])).strip()[:220]
        core_summary = lead_snippet or f"{prov_label} {category} in {resolved_path}"

        query_seed = f"{name} {resolved_path} {owner_name}".strip()
        doc_obj = {
            "url": web_url,
            "domain": domain,
            "title": name,
            "trust": 0.85,
            "text": clean_text,
        }
        passages = rank_passages(query_seed, [doc_obj], k=8, per_source=8, min_score=0.05)
        if not passages:
            sents = [s for s in split_sentences(clean_text) if len(s) >= 20][:8]
            if not sents:
                sents = [ln[:400] for ln in non_empty[:8]]
            passages = [
                {
                    "text": s[:420],
                    "url": web_url,
                    "domain": domain,
                    "title": name,
                    "trust": 0.85,
                    "score": 0.6,
                }
                for s in sents
                if s.strip()
            ]

        distilled_lines = [f"- {p['text']}" for p in passages[:8]]
        distilled_content = "\n".join(distilled_lines)[:2800]

        rels: dict[str, list[str]] = {}
        owner_link_target = owner_name or owner_email
        if owner_link_target:
            rels["owned_by"] = [f"[[{owner_link_target}]]"]

        upserted_ent = self.runtime.brain.upsert_entity(
            entity_type="document",
            name=name,
            summary=core_summary,
            attributes={
                "provider": prov_label,
                "file_type": category,
                "path": resolved_path,
                "owner": owner_disp,
                "modified_at": mod_iso,
                "$item_key": item_key,
            },
            content=distilled_content,
            relationships=rels or None,
            source_url=web_url,
            actor="drives/background_sync",
        )
        brain_slug = str(upserted_ent.get("slug") or "")

        if passages and hasattr(self.runtime, "store") and self.runtime.store is not None:
            with self.runtime.store_lock:
                if web_url:
                    self.runtime.store.db.execute(
                        "DELETE FROM passages WHERE url = ? AND question LIKE '[conv:drives]%'",
                        (web_url,),
                    )
                    self.runtime.store.db.execute(
                        "DELETE FROM satz_conv_passages WHERE conversation_id = 'drives' AND url = ?",
                        (web_url,),
                    )
                q_tag = f"[conv:drives] [{prov_label}] {name}"
                self.runtime.store.add_passages(passages, name[:80], q_tag)
                for p in passages:
                    self.runtime.store.db.execute(
                        "INSERT OR IGNORE INTO satz_conv_passages (conversation_id, text_norm, url) VALUES ('drives', ?, ?)",
                        (norm_text(p["text"]), web_url),
                    )
                self.runtime.store.db.commit()

        self._mark_item_indexed(
            item_key,
            revision_id=str(row["revision_id"]),
            core_summary=core_summary,
            brain_slug=brain_slug,
        )

    def _mark_item_indexed(
        self,
        item_key: str,
        *,
        revision_id: str,
        core_summary: str,
        brain_slug: str,
    ) -> None:
        now = time.time()
        with self._db_lock:
            conn = self._get_conn()
            conn.execute(
                """
                UPDATE drive_items
                SET core_summary = ?,
                    brain_slug = ?,
                    indexed_revision = ?,
                    indexed_at = ?
                WHERE item_key = ?
                """,
                (core_summary, brain_slug, revision_id, now, item_key),
            )
            conn.commit()

    # ── Explorer Listing, Breadcrumbs, Filters, Search & Create Menu ─────

    def list_items(
        self,
        *,
        folder_key: str = "",
        provider: str = "all",
        file_type: str = "all",
        owner: str = "all",
        query: str = "",
        limit: int = 300,
    ) -> dict[str, Any]:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return {
                "ok": True,
                "unlocked": False,
                "folder_key": "",
                "parent_key": None,
                "breadcrumbs": [{"key": "", "name": "Drives"}],
                "items": [],
                "facets": {"providers": [], "file_types": {}, "owners": []},
                "scope": "locked",
            }

        fk = (folder_key or "").strip()
        prov = (provider or "all").strip().lower()
        ftype = (file_type or "all").strip().lower()
        own = (owner or "all").strip()
        q = (query or "").strip()
        lim = max(1, min(1000, int(limit or 300)))

        with self._db_lock:
            conn = self._get_conn()
            breadcrumbs, parent_key, resolved_fk = self._resolve_breadcrumbs_locked(conn, fk)
            facets = self._compute_facets_locked(conn)

            where_clauses = ["d.trashed = 0"]
            params: list[Any] = []

            if prov in ("gdrive", "onedrive"):
                where_clauses.append("d.provider = ?")
                params.append(prov)

            if ftype and ftype != "all":
                where_clauses.append("d.file_category = ?")
                params.append(ftype)

            if own and own.lower() != "all":
                if own.lower() == "me":
                    where_clauses.append("d.is_me = 1")
                else:
                    where_clauses.append("(LOWER(d.owner_email) = LOWER(?) OR LOWER(d.owner_name) = LOWER(?))")
                    params.extend([own, own])

            has_deep_filter = bool((ftype and ftype not in ("all", "folder")) or (own and own.lower() != "all"))
            scope = "folder"
            items_out: list[dict[str, Any]] = []

            if q:
                scope = "search"
                matched_keys = self._search_item_keys_locked(conn, q, limit=lim)
                if matched_keys:
                    placeholders = ",".join("?" for _ in matched_keys)
                    sql = f"""
                        SELECT d.*
                        FROM drive_items d
                        WHERE {" AND ".join(where_clauses)}
                          AND d.item_key IN ({placeholders})
                        LIMIT ?
                    """
                    rows = conn.execute(sql, [*params, *matched_keys, lim]).fetchall()
                    rank_map = {k: i for i, k in enumerate(matched_keys)}
                    sorted_rows = sorted(rows, key=lambda r: rank_map.get(str(r["item_key"]), 999999))
                    items_out = [self._serialize_item_row(r) for r in sorted_rows]
            elif resolved_fk == "__shared__":
                where_clauses.append("d.shared_orphan = 1")
                sql = f"""
                    SELECT d.*
                    FROM drive_items d
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY d.is_folder DESC, d.modified_at DESC, d.name COLLATE NOCASE ASC
                    LIMIT ?
                """
                rows = conn.execute(sql, [*params, lim]).fetchall()
                items_out = [self._serialize_item_row(r) for r in rows]
            elif resolved_fk and ":" in resolved_fk:
                f_prov, f_rem_id = resolved_fk.split(":", 1)
                if has_deep_filter:
                    scope = "filtered"
                    # Match items anywhere inside this folder subtree
                    subtree_ids = self._collect_descendant_folder_ids_locked(conn, f_prov, f_rem_id)
                    placeholders = ",".join("?" for _ in subtree_ids)
                    where_clauses.append("d.provider = ?")
                    params.append(f_prov)
                    where_clauses.append(f"d.parent_id IN ({placeholders})")
                    params.extend(subtree_ids)
                else:
                    where_clauses.append("d.provider = ? AND d.parent_id = ?")
                    params.extend([f_prov, f_rem_id])
                sql = f"""
                    SELECT d.*
                    FROM drive_items d
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY d.is_folder DESC, d.modified_at DESC, d.name COLLATE NOCASE ASC
                    LIMIT ?
                """
                rows = conn.execute(sql, [*params, lim]).fetchall()
                items_out = [self._serialize_item_row(r) for r in rows]
            else:
                # Root `Drives` view
                if has_deep_filter:
                    scope = "filtered"
                    sql = f"""
                        SELECT d.*
                        FROM drive_items d
                        WHERE {" AND ".join(where_clauses)}
                        ORDER BY d.is_folder DESC, d.modified_at DESC, d.name COLLATE NOCASE ASC
                        LIMIT ?
                    """
                    rows = conn.execute(sql, [*params, lim]).fetchall()
                    items_out = [self._serialize_item_row(r) for r in rows]
                else:
                    where_clauses.append("d.is_root = 1")
                    sql = f"""
                        SELECT d.*
                        FROM drive_items d
                        WHERE {" AND ".join(where_clauses)}
                        ORDER BY d.is_folder DESC, d.modified_at DESC, d.name COLLATE NOCASE ASC
                        LIMIT ?
                    """
                    rows = conn.execute(sql, [*params, lim]).fetchall()
                    items_out = [self._serialize_item_row(r) for r in rows]

                    # Prepend virtual "Shared with me" folder when orphan shared items exist
                    if ftype in ("all", "folder"):
                        sh_where = "trashed = 0 AND shared_orphan = 1"
                        sh_params: list[Any] = []
                        if prov in ("gdrive", "onedrive"):
                            sh_where += " AND provider = ?"
                            sh_params.append(prov)
                        sh_cnt = conn.execute(
                            f"SELECT COUNT(*) FROM drive_items WHERE {sh_where}",
                            sh_params,
                        ).fetchone()[0]
                        if int(sh_cnt or 0) > 0:
                            items_out.insert(
                                0,
                                {
                                    "item_key": "__shared__",
                                    "navigate_key": "__shared__",
                                    "provider": prov if prov in ("gdrive", "onedrive") else "shared",
                                    "name": "Shared with me",
                                    "is_folder": True,
                                    "is_shortcut": False,
                                    "mime_type": GOOGLE_FOLDER_MIME,
                                    "file_category": "folder",
                                    "resolved_path": "Drives",
                                    "path_crumbs": [],
                                    "owner_name": "Shared",
                                    "owner_email": "",
                                    "is_me": False,
                                    "modified_at": 0.0,
                                    "size_bytes": 0,
                                    "web_url": "",
                                    "core_summary": f"{int(sh_cnt)} shared items",
                                    "brain_slug": "",
                                    "indexed": False,
                                },
                            )

        return {
            "ok": True,
            "unlocked": True,
            "folder_key": resolved_fk,
            "parent_key": parent_key,
            "breadcrumbs": breadcrumbs,
            "items": items_out,
            "facets": facets,
            "scope": scope,
        }

    def _resolve_breadcrumbs_locked(
        self,
        conn: sqlite3.Connection,
        folder_key: str,
    ) -> tuple[list[dict[str, str]], str | None, str]:
        root_crumb = {"key": "", "name": "Drives", "provider": "all"}
        if not folder_key:
            return [root_crumb], None, ""
        if folder_key == "__shared__":
            return [root_crumb, {"key": "__shared__", "name": "Shared with me", "provider": "shared"}], "", "__shared__"

        row = conn.execute(
            "SELECT * FROM drive_items WHERE item_key = ? AND trashed = 0",
            (folder_key,),
        ).fetchone()
        if row is None:
            return [root_crumb], None, ""

        # Resolve folder shortcut transparently to target folder if cached
        if row["is_shortcut"] and row["target_id"]:
            target_key = f"{row['provider']}:{row['target_id']}"
            t_row = conn.execute(
                "SELECT * FROM drive_items WHERE item_key = ? AND trashed = 0",
                (target_key,),
            ).fetchone()
            if t_row is not None and t_row["is_folder"]:
                row = t_row
                folder_key = target_key

        try:
            anc_crumbs = json.loads(row["path_crumbs_json"] or "[]")
            if not isinstance(anc_crumbs, list):
                anc_crumbs = []
        except Exception:
            anc_crumbs = []

        self_crumb = {
            "key": str(row["item_key"]),
            "name": str(row["name"]),
            "provider": str(row["provider"]),
        }
        full_crumbs = [root_crumb, *anc_crumbs, self_crumb]
        parent_key = str(full_crumbs[-2]["key"]) if len(full_crumbs) >= 2 else ""
        return full_crumbs, parent_key, str(row["item_key"])

    @staticmethod
    def _collect_descendant_folder_ids_locked(
        conn: sqlite3.Connection,
        provider: str,
        start_remote_id: str,
    ) -> list[str]:
        folder_rows = conn.execute(
            "SELECT remote_id, parent_id FROM drive_items WHERE provider = ? AND is_folder = 1 AND trashed = 0",
            (provider,),
        ).fetchall()
        children_by_parent: dict[str, list[str]] = {}
        for fr in folder_rows:
            children_by_parent.setdefault(str(fr["parent_id"] or ""), []).append(str(fr["remote_id"]))

        collected: list[str] = [start_remote_id]
        seen = {start_remote_id}
        idx = 0
        while idx < len(collected) and len(collected) < 500:
            cur = collected[idx]
            idx += 1
            for ch in children_by_parent.get(cur, []):
                if ch not in seen:
                    seen.add(ch)
                    collected.append(ch)
        return collected

    def _compute_facets_locked(self, conn: sqlite3.Connection) -> dict[str, Any]:
        type_rows = conn.execute(
            """
            SELECT file_category, COUNT(*) AS cnt
            FROM drive_items
            WHERE trashed = 0
            GROUP BY file_category
            """
        ).fetchall()
        file_types = {str(r["file_category"]): int(r["cnt"]) for r in type_rows}

        owner_rows = conn.execute(
            """
            SELECT owner_email, owner_name, is_me, COUNT(*) AS cnt
            FROM drive_items
            WHERE trashed = 0 AND (owner_email != '' OR owner_name != '')
            GROUP BY LOWER(COALESCE(NULLIF(owner_email, ''), owner_name))
            ORDER BY is_me DESC, cnt DESC
            LIMIT 60
            """
        ).fetchall()
        owners: list[dict[str, Any]] = []
        for r in owner_rows:
            em = str(r["owner_email"] or "").strip()
            nm = str(r["owner_name"] or em).strip()
            val = em or nm
            if not val:
                continue
            owners.append(
                {
                    "value": val,
                    "label": f"{nm} ({em})" if (em and nm and nm.lower() != em.lower()) else val,
                    "email": em,
                    "name": nm,
                    "is_me": bool(r["is_me"]),
                    "count": int(r["cnt"]),
                }
            )

        prov_rows = conn.execute(
            """
            SELECT provider, COUNT(*) AS cnt
            FROM drive_items
            WHERE trashed = 0
            GROUP BY provider
            """
        ).fetchall()
        providers = [{"id": str(r["provider"]), "count": int(r["cnt"])} for r in prov_rows]

        return {
            "providers": providers,
            "file_types": file_types,
            "owners": owners,
        }

    def _search_item_keys_locked(
        self,
        conn: sqlite3.Connection,
        query: str,
        *,
        limit: int = 100,
    ) -> list[str]:
        tokens = [t for t in re.findall(r"[A-Za-z0-9äöüÄÖÜß_.\-@]+", query) if len(t) >= 2]
        ordered_keys: list[str] = []
        seen: set[str] = set()

        def _add(k: str) -> None:
            if k and k not in seen:
                seen.add(k)
                ordered_keys.append(k)

        # 1. Exact / prefix FTS5 search over name, path, owner, core_summary
        if tokens:
            fts_terms = [re.sub(r"[^A-Za-z0-9äöüÄÖÜß]", "", t) for t in tokens]
            fts_terms = [ft for ft in fts_terms if len(ft) >= 2][:6]
            if fts_terms:
                fts_expr = " AND ".join(f'"{ft}"*' for ft in fts_terms)
                try:
                    for r in conn.execute(
                        "SELECT item_key FROM drive_items_fts WHERE drive_items_fts MATCH ? ORDER BY bm25(drive_items_fts) LIMIT ?",
                        (fts_expr, limit),
                    ).fetchall():
                        _add(str(r["item_key"]))
                except Exception:
                    pass
                if len(ordered_keys) < 5 and len(fts_terms) > 1:
                    or_expr = " OR ".join(f'"{ft}"*' for ft in fts_terms)
                    try:
                        for r in conn.execute(
                            "SELECT item_key FROM drive_items_fts WHERE drive_items_fts MATCH ? ORDER BY bm25(drive_items_fts) LIMIT ?",
                            (or_expr, limit),
                        ).fetchall():
                            _add(str(r["item_key"]))
                    except Exception:
                        pass

        # 2. Substring LIKE fallback for partial filenames or emails
        like_pat = f"%{query.strip()}%"
        for r in conn.execute(
            """
            SELECT item_key
            FROM drive_items
            WHERE trashed = 0
              AND (name LIKE ? OR resolved_path LIKE ? OR owner_email LIKE ? OR owner_name LIKE ? OR core_summary LIKE ?)
            ORDER BY is_folder DESC, modified_at DESC
            LIMIT ?
            """,
            (like_pat, like_pat, like_pat, like_pat, like_pat, limit),
        ).fetchall():
            _add(str(r["item_key"]))

        # 3. Semantic Brain search (`SatzBrain`) for document entities matching conceptual queries
        if not getattr(self.runtime.brain, "locked", True):
            try:
                b_hits = self.runtime.brain.search(query, limit=12)
                slugs = [
                    str(ent.get("slug") or "")
                    for ent in (b_hits.get("entities") or [])
                    if str(ent.get("type") or "") == "document" and ent.get("slug")
                ]
                if slugs:
                    placeholders = ",".join("?" for _ in slugs)
                    for r in conn.execute(
                        f"SELECT item_key FROM drive_items WHERE trashed = 0 AND brain_slug IN ({placeholders})",
                        slugs,
                    ).fetchall():
                        _add(str(r["item_key"]))
            except Exception:
                pass

        return ordered_keys[:limit]

    @staticmethod
    def _serialize_item_row(r: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        try:
            crumbs = json.loads(r["path_crumbs_json"] or "[]")
            if not isinstance(crumbs, list):
                crumbs = []
        except Exception:
            crumbs = []
        is_folder = bool(r["is_folder"])
        is_shortcut = bool(r["is_shortcut"])
        provider = str(r["provider"])
        nav_key = ""
        if is_folder:
            if is_shortcut and r["target_id"]:
                nav_key = f"{provider}:{r['target_id']}"
            else:
                nav_key = str(r["item_key"])
        return {
            "item_key": str(r["item_key"]),
            "navigate_key": nav_key,
            "provider": provider,
            "remote_id": str(r["remote_id"]),
            "name": str(r["name"]),
            "is_folder": is_folder,
            "is_shortcut": is_shortcut,
            "mime_type": str(r["mime_type"]),
            "file_category": str(r["file_category"]),
            "resolved_path": str(r["resolved_path"] or "Drives"),
            "path_crumbs": crumbs,
            "owner_name": str(r["owner_name"] or ""),
            "owner_email": str(r["owner_email"] or ""),
            "is_me": bool(r["is_me"]),
            "modified_at": float(r["modified_at"] or 0.0),
            "size_bytes": int(r["size_bytes"] or 0),
            "web_url": str(r["web_url"] or ""),
            "core_summary": str(r["core_summary"] or ""),
            "brain_slug": str(r["brain_slug"] or ""),
            "indexed": bool((r["indexed_at"] or 0.0) > 0 and r["brain_slug"]),
        }

    def get_create_targets(self) -> dict[str, Any]:
        st = self.get_status()
        targets: list[dict[str, str]] = []
        if st["google"]["connected"]:
            g_email = str(st["google"].get("email") or "")
            targets.extend(
                [
                    {
                        "id": "gdrive:doc",
                        "provider": "gdrive",
                        "provider_label": "Google Drive",
                        "label": "Google Doc",
                        "url": append_google_authuser("https://docs.google.com/document/create", g_email),
                    },
                    {
                        "id": "gdrive:sheet",
                        "provider": "gdrive",
                        "provider_label": "Google Drive",
                        "label": "Google Sheet",
                        "url": append_google_authuser("https://docs.google.com/spreadsheets/create", g_email),
                    },
                    {
                        "id": "gdrive:slide",
                        "provider": "gdrive",
                        "provider_label": "Google Drive",
                        "label": "Google Slides",
                        "url": append_google_authuser("https://docs.google.com/presentation/create", g_email),
                    },
                ]
            )
        if st["onedrive"]["connected"]:
            targets.extend(
                [
                    {
                        "id": "onedrive:word",
                        "provider": "onedrive",
                        "provider_label": "OneDrive",
                        "label": "Word document",
                        "url": "https://word.cloud.microsoft/",
                    },
                    {
                        "id": "onedrive:excel",
                        "provider": "onedrive",
                        "provider_label": "OneDrive",
                        "label": "Excel workbook",
                        "url": "https://excel.cloud.microsoft/",
                    },
                    {
                        "id": "onedrive:powerpoint",
                        "provider": "onedrive",
                        "provider_label": "OneDrive",
                        "label": "PowerPoint presentation",
                        "url": "https://powerpoint.cloud.microsoft/",
                    },
                ]
            )
        return {"ok": True, "targets": targets}

    # ── Pure Local Chat Retrieval (`drives.sqlite` + `SatzBrain`) ────────

    def build_chat_sources(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return []
        st = self.get_status()
        if st["total_files"] <= 0:
            return []

        from src.planck3.web import domain_of

        q = (query or "").strip()
        sources_out: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        with self._db_lock:
            conn = self._get_conn()
            candidate_rows: list[sqlite3.Row] = []

            if q:
                keys = self._search_item_keys_locked(conn, q, limit=limit * 2)
                # Also strip common chat stopwords if full query was conversational
                if len(keys) < limit:
                    stop = {
                        "what", "which", "where", "when", "who", "does", "show", "find",
                        "list", "files", "file", "documents", "document", "docs", "drive",
                        "drives", "google", "onedrive", "shared", "with", "from", "about",
                        "recent", "latest", "have", "open", "folder", "folders", "summarize",
                    }
                    kw = [
                        w
                        for w in re.findall(r"[A-Za-z0-9äöüÄÖÜß.@\-]{3,}", q)
                        if w.lower() not in stop
                    ]
                    for w in kw[:4]:
                        for k in self._search_item_keys_locked(conn, w, limit=limit):
                            if k not in keys:
                                keys.append(k)

                if keys:
                    placeholders = ",".join("?" for _ in keys[: limit * 2])
                    fetched = {
                        str(r["item_key"]): r
                        for r in conn.execute(
                            f"SELECT * FROM drive_items WHERE trashed = 0 AND item_key IN ({placeholders})",
                            keys[: limit * 2],
                        ).fetchall()
                    }
                    for k in keys:
                        if k in fetched:
                            candidate_rows.append(fetched[k])

            # Fallback for broad overview prompts ("what recent docs do I have?", "summarize my drive")
            if not candidate_rows:
                candidate_rows = conn.execute(
                    """
                    SELECT *
                    FROM drive_items
                    WHERE trashed = 0 AND is_folder = 0
                    ORDER BY indexed_at DESC, modified_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        # Prepend a lightweight synthetic catalog overview source so count/owner/provider questions are exact
        sources_out.append(
            {
                "id": "drive:__overview__",
                "url": (
                    append_google_authuser("https://drive.google.com/drive/my-drive#overview", str(st["google"].get("email") or ""))
                    if st["google"]["connected"]
                    else "https://onedrive.live.com/#overview"
                ),
                "title": "Unified Cloud Drives Catalog Overview",
                "domain": "drives",
                "is_open_tab": True,
            }
        )

        for r in candidate_rows:
            ikey = str(r["item_key"])
            if ikey in seen_keys or len(sources_out) >= (limit + 1):
                continue
            seen_keys.add(ikey)
            prov_badge = "GDrive" if str(r["provider"]) == "gdrive" else "OneDrive"
            web_url = str(r["web_url"] or "").strip() or (
                "https://drive.google.com" if str(r["provider"]) == "gdrive" else "https://onedrive.live.com"
            )
            sources_out.append(
                {
                    "id": f"drive:{ikey}",
                    "url": web_url,
                    "title": f"[{prov_badge}] {r['name']}",
                    "domain": domain_of(web_url) or prov_badge.lower(),
                    "is_open_tab": True,
                }
            )
        return sources_out

    def get_source_text_for_chat(self, drive_source_id: str) -> str:
        if not self.passwords.unlocked or not self.passwords.active_profile_id:
            return ""
        raw_key = drive_source_id.split("drive:", 1)[1].strip() if drive_source_id.startswith("drive:") else drive_source_id
        if raw_key == "__overview__":
            return self._build_catalog_overview_text()

        with self._db_lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM drive_items WHERE item_key = ? AND trashed = 0",
                (raw_key,),
            ).fetchone()
        if row is None:
            return ""

        prov_label = "Google Drive" if str(row["provider"]) == "gdrive" else "OneDrive"
        mod_iso = _ts_to_iso(float(row["modified_at"] or 0.0)) or "unknown"
        owner_str = str(row["owner_email"] or row["owner_name"] or ("Me" if row["is_me"] else "Unknown"))
        lines = [
            f"Document: {row['name']}",
            f"Cloud Provider: {prov_label}",
            f"Type: {row['file_category']} ({row['mime_type']})",
            f"Folder Path: {row['resolved_path'] or 'Drives'}",
            f"Owner: {owner_str}",
            f"Last Modified: {mod_iso}",
            f"Web URL: {row['web_url']}",
        ]
        if row["core_summary"]:
            lines.append(f"Summary: {row['core_summary']}")

        # Pull semantic passages stored locally in `planck_store.sqlite`
        web_url = str(row["web_url"] or "").strip()
        if web_url and hasattr(self.runtime, "store") and self.runtime.store is not None:
            with self.runtime.store_lock:
                p_rows = self.runtime.store.db.execute(
                    """
                    SELECT text
                    FROM passages
                    WHERE url = ? AND question LIKE '[conv:drives]%'
                    ORDER BY ts DESC
                    LIMIT 8
                    """,
                    (web_url,),
                ).fetchall()
            if p_rows:
                lines.append("\nIndexed Passages (from Satz Brain):")
                for pr in p_rows:
                    lines.append(f"- {pr['text']}")

        return "\n".join(lines)

    def _build_catalog_overview_text(self) -> str:
        st = self.get_status()
        with self._db_lock:
            conn = self._get_conn()
            facets = self._compute_facets_locked(conn)
            recent_rows = conn.execute(
                """
                SELECT provider, name, file_category, resolved_path, owner_email, owner_name, modified_at
                FROM drive_items
                WHERE trashed = 0
                ORDER BY modified_at DESC
                LIMIT 15
                """
            ).fetchall()

        parts = [
            "Connected Cloud Drives Summary (local metadata index):",
            f"- Total indexed items (metadata): {st['total_files']} ({st['indexed_docs']} active documents indexed into Satz Brain)",
        ]
        if st["google"]["connected"]:
            parts.append(
                f"- Google Drive ({st['google']['email']}): {st['google']['total_files']} items, {st['google']['indexed_docs']} docs in Brain"
            )
        if st["onedrive"]["connected"]:
            parts.append(
                f"- Microsoft OneDrive ({st['onedrive']['email']}): {st['onedrive']['total_files']} items, {st['onedrive']['indexed_docs']} docs in Brain"
            )
        if facets["file_types"]:
            ft_summary = ", ".join(f"{k}: {v}" for k, v in sorted(facets["file_types"].items()))
            parts.append(f"- Breakdown by type: {ft_summary}")
        if facets["owners"]:
            top_owners = ", ".join(f"{o['label']} ({o['count']})" for o in facets["owners"][:8])
            parts.append(f"- Top file owners: {top_owners}")
        if recent_rows:
            parts.append("\nMost recently modified items:")
            for r in recent_rows:
                p_tag = "GDrive" if str(r["provider"]) == "gdrive" else "OneDrive"
                own = str(r["owner_email"] or r["owner_name"] or "Me")
                parts.append(
                    f"- [{p_tag}] {r['name']} ({r['file_category']}, path: {r['resolved_path']}, owner: {own}, modified: {_ts_to_iso(float(r['modified_at'] or 0.0))})"
                )
        return "\n".join(parts)


def account_name_fallback(email: str) -> str:
    if not email:
        return ""
    return email.split("@", 1)[0]

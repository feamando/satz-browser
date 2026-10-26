#!/usr/bin/env python3
"""
Satz Profile & .env Password Management System

1. Manages user profiles with a Name and a 6-digit PIN (hashed with SHA-256 + salt).
2. Stores each profile's credentials in an isolated `.env` file at:
   `%APPDATA%/com.satz.browser/profiles/<profile_id>/.env`
   and isolates each profile's Brain directory at:
   `%APPDATA%/com.satz.browser/profiles/<profile_id>/brain`
3. Strict profile boundary: `.env` credentials are only accessible when that specific
   profile is unlocked with its 6-digit PIN.
4. Provides authenticated data extraction for the Agent and the Background Bookmark
   Indexer (supporting HTTP Cookie/Token/Basic/Form login + IMAP email extraction).
"""

from __future__ import annotations

import base64
import email
import hashlib
import http.cookiejar
import imaplib
import json
import os
import re
import secrets
import ssl
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import Any


PIN_REGEX = re.compile(r"^\d{6}$")
ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")

KNOWN_SERVICE_ALIASES: dict[str, list[str]] = {
    "GMAIL": ["mail.google.com", "gmail.com", "google.com"],
    "GOOGLE": ["mail.google.com", "google.com", "accounts.google.com"],
    "OUTLOOK": ["outlook.live.com", "outlook.office.com", "hotmail.com"],
    "GITHUB": ["github.com", "api.github.com"],
    "ZALANDO": ["zalando.de", "en.zalando.de", "zalando.com"],
    "AMAZON": ["amazon.com", "amazon.de", "amazon.co.uk"],
    "NOTION": ["notion.so"],
    "SLACK": ["slack.com", "app.slack.com"],
    "CONFLUENCE": ["atlassian.net"],
    "JIRA": ["atlassian.net"],
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify_profile(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s[:40] or "user"


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


def _normalize_service_prefix(service_or_domain: str) -> str:
    s = (service_or_domain or "").strip().lower()
    s = re.sub(r"^https?://", "", s).split("/")[0]
    for prefix in ("www.", "en.", "de.", "mail.", "app.", "my.", "accounts."):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    parts = s.split(".")
    base = parts[0] if parts else s
    clean = re.sub(r"[^a-z0-9]+", "_", base).strip("_").upper()
    return clean or "SERVICE"


def _decode_mime_words(raw: str) -> str:
    if not raw:
        return ""
    out = []
    for part, enc in decode_header(raw):
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return "".join(out)


class ProfilePasswordManager:
    """
    Manages user profiles (Name + 6-digit PIN) and profile-scoped `.env` password files.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.profiles_dir = self.base_dir / "profiles"
        self.registry_file = self.profiles_dir / "profiles.json"
        self.lock = threading.RLock()

        self.active_profile_id: str | None = None
        self.unlocked: bool = False
        self._unlocked_env_cache: dict[str, str] = {}

        self._ensure_layout()

    def _ensure_layout(self) -> None:
        with self.lock:
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            if not self.registry_file.exists():
                self._save_registry({"profiles": [], "last_profile_id": None})

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_file.exists():
            return {"profiles": [], "last_profile_id": None}
        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"profiles": [], "last_profile_id": None}
            if "profiles" not in data or not isinstance(data["profiles"], list):
                data["profiles"] = []
            return data
        except Exception:
            return {"profiles": [], "last_profile_id": None}

    def _save_registry(self, data: dict[str, Any]) -> None:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_profile_dir(self, profile_id: str) -> Path:
        p = self.profiles_dir / profile_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_profile_brain_dir(self, profile_id: str | None = None) -> Path:
        pid = profile_id or self.active_profile_id
        if not pid:
            return self.base_dir / "brain"
        d = self.get_profile_dir(pid) / "brain"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_profile_env_path(self, profile_id: str | None = None) -> Path | None:
        pid = profile_id or self.active_profile_id
        if not pid:
            return None
        return self.get_profile_dir(pid) / ".env"

    def list_profiles(self) -> dict[str, Any]:
        with self.lock:
            reg = self._load_registry()
            profiles_public = []
            active_profile = None
            for p in reg.get("profiles", []):
                pid = p.get("id")
                env_file = self.profiles_dir / str(pid) / ".env"
                cred_count = 0
                if env_file.exists():
                    parsed = self._parse_env_text(env_file.read_text(encoding="utf-8", errors="ignore"))
                    cred_count = len(self._group_credentials(parsed))
                item = {
                    "id": pid,
                    "name": p.get("name"),
                    "created_at": p.get("created_at"),
                    "last_active_at": p.get("last_active_at"),
                    "credential_services_count": cred_count,
                    "is_active": pid == self.active_profile_id and self.unlocked,
                }
                profiles_public.append(item)
                if pid == self.active_profile_id and self.unlocked:
                    active_profile = item

            return {
                "profiles": profiles_public,
                "active_profile_id": self.active_profile_id if self.unlocked else None,
                "unlocked": self.unlocked,
                "active_profile": active_profile,
            }

    def create_profile(self, name: str, pin: str) -> dict[str, Any]:
        clean_name = (name or "").strip()
        clean_pin = (pin or "").strip()
        if not clean_name:
            raise ValueError("Profile name is required.")
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits (000000-999999).")

        with self.lock:
            reg = self._load_registry()
            base_slug = _slugify_profile(clean_name)
            existing_ids = {p.get("id") for p in reg.get("profiles", [])}
            pid = base_slug
            counter = 2
            while pid in existing_ids:
                pid = f"{base_slug}-{counter}"
                counter += 1

            salt = secrets.token_hex(8)
            now = _utc_iso()
            profile_entry = {
                "id": pid,
                "name": clean_name,
                "salt": salt,
                "pin_hash": _hash_pin(clean_pin, salt),
                "created_at": now,
                "last_active_at": now,
            }
            reg["profiles"].append(profile_entry)
            reg["last_profile_id"] = pid
            self._save_registry(reg)

            # Initialize profile directory and starter .env file
            pdir = self.get_profile_dir(pid)
            (pdir / "brain").mkdir(parents=True, exist_ok=True)
            env_path = pdir / ".env"
            if not env_path.exists():
                env_path.write_text(
                    f"# Satz Profile .env Password Vault - Profile: {clean_name} ({pid})\n"
                    f"# Created: {now}\n"
                    "# Format: SERVICE_USERNAME=..., SERVICE_PASSWORD=..., SERVICE_URL=...\n"
                    "# Only accessible when this profile is unlocked with its 6-digit PIN.\n\n",
                    encoding="utf-8",
                )

            # Automatically unlock newly created profile
            self.active_profile_id = pid
            self.unlocked = True
            self._reload_active_env()

            return self.list_profiles()

    def unlock_profile(self, profile_id: str, pin: str) -> dict[str, Any]:
        clean_pin = (pin or "").strip()
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits.")

        with self.lock:
            reg = self._load_registry()
            target = None
            for p in reg.get("profiles", []):
                if p.get("id") == profile_id:
                    target = p
                    break
            if not target:
                raise ValueError(f"Profile '{profile_id}' not found.")

            expected_hash = target.get("pin_hash")
            salt = target.get("salt", "")
            if _hash_pin(clean_pin, salt) != expected_hash:
                raise ValueError("Invalid 6-digit PIN for this profile.")

            target["last_active_at"] = _utc_iso()
            reg["last_profile_id"] = profile_id
            self._save_registry(reg)

            self.active_profile_id = profile_id
            self.unlocked = True
            self._reload_active_env()

            return self.list_profiles()

    def lock_profile(self) -> dict[str, Any]:
        with self.lock:
            self.unlocked = False
            self.active_profile_id = None
            self._unlocked_env_cache.clear()
            return self.list_profiles()

    def delete_profile(self, profile_id: str, pin: str) -> dict[str, Any]:
        clean_pin = (pin or "").strip()
        with self.lock:
            reg = self._load_registry()
            target = next((p for p in reg.get("profiles", []) if p.get("id") == profile_id), None)
            if not target:
                raise ValueError("Profile not found.")
            if _hash_pin(clean_pin, target.get("salt", "")) != target.get("pin_hash"):
                raise ValueError("Invalid 6-digit PIN.")

            reg["profiles"] = [p for p in reg.get("profiles", []) if p.get("id") != profile_id]
            if self.active_profile_id == profile_id:
                self.active_profile_id = None
                self.unlocked = False
                self._unlocked_env_cache.clear()
            self._save_registry(reg)
            return self.list_profiles()

    # ── .env Password File Parsing & Management ──────────────────────────
    def _parse_env_text(self, raw_text: str) -> dict[str, str]:
        env_map: dict[str, str] = {}
        for line in (raw_text or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[7:].strip()
            m = ENV_LINE_RE.match(stripped)
            if m:
                k = m.group(1).strip()
                v = m.group(2).strip()
                if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                    v = v[1:-1]
                env_map[k] = v
        return env_map

    def _reload_active_env(self) -> dict[str, str]:
        with self.lock:
            self._unlocked_env_cache.clear()
            if not self.unlocked or not self.active_profile_id:
                return {}
            env_path = self.get_profile_env_path(self.active_profile_id)
            if env_path and env_path.exists():
                raw = env_path.read_text(encoding="utf-8", errors="ignore")
                self._unlocked_env_cache = self._parse_env_text(raw)
            return dict(self._unlocked_env_cache)

    def _group_credentials(self, env_map: dict[str, str]) -> list[dict[str, Any]]:
        """
        Groups flat .env keys (e.g. ZALANDO_USERNAME, ZALANDO_PASSWORD, ZALANDO_URL)
        into structured service entries.
        """
        groups: dict[str, dict[str, Any]] = {}
        suffixes = (
            "_USERNAME",
            "_USER",
            "_EMAIL",
            "_LOGIN",
            "_PASSWORD",
            "_PASS",
            "_SECRET",
            "_TOKEN",
            "_API_KEY",
            "_COOKIE",
            "_URL",
            "_DOMAIN",
            "_IMAP_HOST",
        )
        for k, v in env_map.items():
            k_up = k.upper()
            matched_prefix = None
            matched_field = None
            for sfx in suffixes:
                if k_up.endswith(sfx) and len(k_up) > len(sfx):
                    matched_prefix = k_up[: -len(sfx)]
                    matched_field = sfx.lstrip("_").lower()
                    break
            if not matched_prefix:
                matched_prefix = k_up
                matched_field = "value"

            g = groups.setdefault(
                matched_prefix,
                {
                    "service": matched_prefix,
                    "domain": "",
                    "username": "",
                    "has_password": False,
                    "has_token": False,
                    "has_cookie": False,
                    "keys": [],
                },
            )
            g["keys"].append(k)
            if matched_field in ("username", "user", "email", "login"):
                g["username"] = v
            elif matched_field in ("password", "pass", "secret"):
                g["has_password"] = bool(v)
            elif matched_field in ("token", "api_key"):
                g["has_token"] = bool(v)
            elif matched_field == "cookie":
                g["has_cookie"] = bool(v)
            elif matched_field in ("url", "domain"):
                g["domain"] = v

            if not g["domain"] and matched_prefix in KNOWN_SERVICE_ALIASES:
                g["domain"] = KNOWN_SERVICE_ALIASES[matched_prefix][0]

        return sorted(groups.values(), key=lambda x: x["service"])

    def get_active_vault_summary(self, include_raw_env: bool = False) -> dict[str, Any]:
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                return {
                    "unlocked": False,
                    "profile_id": None,
                    "env_path": None,
                    "services": [],
                    "raw_env": "",
                }
            env_map = self._reload_active_env()
            env_path = self.get_profile_env_path(self.active_profile_id)
            raw_text = (
                env_path.read_text(encoding="utf-8", errors="ignore")
                if (include_raw_env and env_path and env_path.exists())
                else ""
            )
            return {
                "unlocked": True,
                "profile_id": self.active_profile_id,
                "env_path": str(env_path) if env_path else "",
                "services": self._group_credentials(env_map),
                "raw_env": raw_text,
            }

    def upsert_service_credential(
        self,
        service_or_domain: str,
        username: str,
        password: str = "",
        token: str = "",
        cookie: str = "",
        url: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before storing passwords.")

            prefix = _normalize_service_prefix(service_or_domain)
            env_path = self.get_profile_env_path(self.active_profile_id)
            assert env_path is not None

            existing_text = env_path.read_text(encoding="utf-8", errors="ignore") if env_path.exists() else ""
            env_map = self._parse_env_text(existing_text)

            if username.strip():
                env_map[f"{prefix}_USERNAME"] = username.strip()
            if password.strip():
                env_map[f"{prefix}_PASSWORD"] = password.strip()
            if token.strip():
                env_map[f"{prefix}_TOKEN"] = token.strip()
            if cookie.strip():
                env_map[f"{prefix}_COOKIE"] = cookie.strip()
            effective_url = (url or service_or_domain or "").strip()
            if effective_url:
                env_map[f"{prefix}_URL"] = effective_url

            self._write_env_map(env_path, env_map)
            self._reload_active_env()
            return self.get_active_vault_summary(include_raw_env=True)

    def save_raw_env(self, raw_env_text: str) -> dict[str, Any]:
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before editing its .env file.")
            env_path = self.get_profile_env_path(self.active_profile_id)
            assert env_path is not None
            env_path.write_text(raw_env_text.strip() + "\n", encoding="utf-8")
            self._reload_active_env()
            return self.get_active_vault_summary(include_raw_env=True)

    def import_env_file(self, external_path: str) -> dict[str, Any]:
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before importing a .env file.")
            src_path = Path(external_path.strip().strip('"').strip("'"))
            if not src_path.exists() or not src_path.is_file():
                raise FileNotFoundError(f".env file not found at: {src_path}")

            imported_raw = src_path.read_text(encoding="utf-8", errors="ignore")
            imported_map = self._parse_env_text(imported_raw)

            env_path = self.get_profile_env_path(self.active_profile_id)
            assert env_path is not None
            current_map = (
                self._parse_env_text(env_path.read_text(encoding="utf-8", errors="ignore"))
                if env_path.exists()
                else {}
            )
            current_map.update(imported_map)
            self._write_env_map(env_path, current_map)
            self._reload_active_env()
            return self.get_active_vault_summary(include_raw_env=True)

    def delete_service_credential(self, service_prefix: str) -> dict[str, Any]:
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Profile is locked.")
            prefix = service_prefix.strip().upper()
            env_path = self.get_profile_env_path(self.active_profile_id)
            assert env_path is not None
            if env_path.exists():
                env_map = self._parse_env_text(env_path.read_text(encoding="utf-8", errors="ignore"))
                to_remove = [k for k in env_map if k.upper() == prefix or k.upper().startswith(f"{prefix}_")]
                for k in to_remove:
                    env_map.pop(k, None)
                self._write_env_map(env_path, env_map)
            self._reload_active_env()
            return self.get_active_vault_summary(include_raw_env=True)

    def _write_env_map(self, env_path: Path, env_map: dict[str, str]) -> None:
        lines = [
            f"# Satz Profile .env Password Vault ({self.active_profile_id})",
            f"# Updated: {_utc_iso()}",
            "# Only accessible within this unlocked profile.",
            "",
        ]
        for k, v in sorted(env_map.items()):
            safe_val = v.replace("\n", " ").strip()
            if " " in safe_val or "#" in safe_val or '"' in safe_val:
                safe_val = '"' + safe_val.replace('"', '\\"') + '"'
            lines.append(f"{k}={safe_val}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Credential Resolution & Authenticated Extraction for Agent/Bookmarks ─
    def find_credentials_for_target(self, url_or_query: str) -> dict[str, str] | None:
        """
        Finds matching credentials from the active unlocked profile's `.env`
        for a given URL, domain, or user query (e.g. 'gmail', 'zalando', 'github').
        Returns None if profile is locked or no matching credentials exist.
        """
        with self.lock:
            if not self.unlocked or not self.active_profile_id:
                return None
            env_map = self._reload_active_env()
            if not env_map:
                return None

            target_l = (url_or_query or "").lower()
            prefix_cand = _normalize_service_prefix(url_or_query)

            # Group keys by prefix
            prefixes: set[str] = set()
            for k in env_map:
                k_up = k.upper()
                for sfx in ("_USERNAME", "_USER", "_EMAIL", "_PASSWORD", "_PASS", "_TOKEN", "_API_KEY", "_COOKIE", "_URL"):
                    if k_up.endswith(sfx) and len(k_up) > len(sfx):
                        prefixes.add(k_up[: -len(sfx)])

            matched_prefix: str | None = None
            for pfx in prefixes:
                if pfx == prefix_cand or pfx.lower() in target_l:
                    matched_prefix = pfx
                    break
                custom_url = env_map.get(f"{pfx}_URL", "").lower()
                if custom_url and (custom_url in target_l or target_l in custom_url):
                    matched_prefix = pfx
                    break
                for alias_dom in KNOWN_SERVICE_ALIASES.get(pfx, []):
                    if alias_dom in target_l:
                        matched_prefix = pfx
                        break
                if matched_prefix:
                    break

            if not matched_prefix:
                return None

            username = (
                env_map.get(f"{matched_prefix}_USERNAME")
                or env_map.get(f"{matched_prefix}_USER")
                or env_map.get(f"{matched_prefix}_EMAIL")
                or env_map.get(f"{matched_prefix}_LOGIN")
                or ""
            )
            password = (
                env_map.get(f"{matched_prefix}_PASSWORD")
                or env_map.get(f"{matched_prefix}_PASS")
                or env_map.get(f"{matched_prefix}_SECRET")
                or ""
            )
            token = (
                env_map.get(f"{matched_prefix}_TOKEN")
                or env_map.get(f"{matched_prefix}_API_KEY")
                or ""
            )
            cookie = env_map.get(f"{matched_prefix}_COOKIE") or ""
            imap_host = env_map.get(f"{matched_prefix}_IMAP_HOST") or ""
            service_url = env_map.get(f"{matched_prefix}_URL") or ""

            return {
                "service": matched_prefix,
                "username": username,
                "password": password,
                "token": token,
                "cookie": cookie,
                "imap_host": imap_host,
                "url": service_url,
            }

    def extract_with_profile_credentials(self, url_or_service: str) -> dict[str, Any] | None:
        """
        Uses the active profile's `.env` credentials to authenticate and extract data
        in the background (for bookmarks or agent requests).
        Supports:
        1. IMAP email extraction (for Gmail / Outlook / IMAP services when username + password are stored)
        2. Authenticated HTTP fetch (Bearer token, Cookie header, or Basic Auth / login session)
        """
        creds = self.find_credentials_for_target(url_or_service)
        if not creds:
            return None

        service = creds["service"]
        username = creds["username"]
        password = creds["password"]
        token = creds["token"]
        cookie = creds["cookie"]
        imap_host = creds["imap_host"]

        # 1. Check if this is an email / IMAP service
        if not imap_host:
            if service in ("GMAIL", "GOOGLE") or "mail.google.com" in url_or_service.lower():
                imap_host = "imap.gmail.com"
            elif service == "OUTLOOK" or "outlook." in url_or_service.lower():
                imap_host = "outlook.office365.com"

        if imap_host and username and password:
            imap_text = self._fetch_imap_recent_emails(imap_host, username, password, limit=8)
            if imap_text:
                return {
                    "service": service,
                    "username": username,
                    "mode": "imap",
                    "text": imap_text,
                }

        # 2. Authenticated HTTP fetch if URL is provided
        target_url = url_or_service if url_or_service.startswith(("http://", "https://")) else creds.get("url", "")
        if target_url and target_url.startswith(("http://", "https://")):
            html_out = self._fetch_authenticated_http(target_url, username, password, token, cookie)
            if html_out:
                return {
                    "service": service,
                    "username": username,
                    "mode": "http_auth",
                    "html": html_out,
                }

        return {
            "service": service,
            "username": username,
            "mode": "credentials_ready",
            "text": f"[Profile '{self.active_profile_id}' has stored credentials for {service} (username: {username})]",
        }

    def _fetch_imap_recent_emails(self, host: str, username: str, password: str, limit: int = 8) -> str:
        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(host, 993, ssl_context=ctx) as mail:
                mail.login(username, password)
                mail.select("INBOX", readonly=True)
                status, data = mail.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    return ""
                msg_ids = data[0].split()
                latest_ids = list(reversed(msg_ids[-limit:]))
                extracted_blocks: list[str] = [
                    f"[AUTHENTICATED IMAP INBOX ({username} on {host}) - LATEST {len(latest_ids)} EMAILS]"
                ]
                for idx, mid in enumerate(latest_ids, 1):
                    st, msg_data = mail.fetch(mid, "(RFC822.HEADER BODY.PEEK[TEXT]<0.2500>)")
                    if st != "OK" or not msg_data:
                        continue
                    header_bytes = b""
                    body_bytes = b""
                    for part in msg_data:
                        if isinstance(part, tuple):
                            if b"HEADER" in part[0]:
                                header_bytes = part[1]
                            else:
                                body_bytes = part[1]
                    msg = email.message_from_bytes(header_bytes)
                    subj = _decode_mime_words(msg.get("Subject", "(no subject)"))
                    sender = _decode_mime_words(msg.get("From", ""))
                    date_str = msg.get("Date", "")
                    body_snip = body_bytes.decode("utf-8", errors="ignore").strip()
                    body_snip = re.sub(r"<[^>]+>", " ", body_snip)
                    body_snip = re.sub(r"\s+", " ", body_snip)[:500]
                    extracted_blocks.append(
                        f"[{idx}] From: {sender} | Subject: {subj} | Date: {date_str}\n    Snippet: {body_snip}"
                    )
                return "\n".join(extracted_blocks)
        except Exception as e:
            print(f"[satz-passwords] IMAP fetch note for {host}: {e}", flush=True)
            return ""

    def _fetch_authenticated_http(
        self,
        url: str,
        username: str,
        password: str,
        token: str,
        cookie: str,
    ) -> str:
        try:
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}" if not token.lower().startswith(("bearer ", "basic ", "token ")) else token
            elif username and password and not cookie:
                b64 = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                headers["Authorization"] = f"Basic {b64}"
            if cookie:
                headers["Cookie"] = cookie

            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=8) as resp:
                raw = resp.read(1_500_000)
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

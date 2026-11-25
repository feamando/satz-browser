#!/usr/bin/env python3
"""
Satz Profile & Encrypted Password Vault (v0.4 Security Model)

1. User profiles with a Name and a 6-digit PIN.
2. Vault encryption (`profiles/<id>/vault.enc`):
   - `k_pin = Argon2id(pin, salt16, time_cost=3, memory_cost=64 MiB, parallelism=4, len=32)`
   - `device_key` = 32-byte random per-profile secret stored in OS keychain via `keyring`
     (service `satz-browser`, user `<profile_id>`).
   - `final_key = HKDF-SHA256(k_pin || device_key, info="satz-vault-v1", length=32)`
   - Cipher: `AES-256-GCM` with 12-byte random nonce per write.
   - File format: `{"v": 1, "salt": "<b64>", "nonce": "<b64>", "ct": "<b64>"}`
   - PIN verification is "does it decrypt" (no stored SHA-256 hash).
3. Lockout & Autolock:
   - After 5 wrong PIN attempts, wait 30s, doubling on each further failure up to 3600s (1 hour).
     Persisted in `profiles/profiles.json` (`registry.json` synced) so restarts do not reset it.
   - Auto-lock after `vault_autolock_minutes` (default 30 min) of inactivity, clearing in-memory env.
4. Automatic v0.3 Migration:
   - On first successful unlock of a legacy v0.3 profile (verified via legacy `salt` + `pin_hash`
     and existing `.env`), encrypts into `vault.enc`, overwrites `.env` with zeros, deletes `.env`,
     and removes `pin_hash` from the profile record.
5. Masked HTTP API & Exact-Host Matching:
   - `get_active_vault_summary()` never returns secret values or raw `.env` text.
   - `reveal_service_field(service, field, pin)` verifies the PIN by decrypting `vault.enc` and
     returns only the requested single secret value.
   - `find_credentials_for_target(url)` matches ONLY when the target URL's host equals, or is a
     subdomain of, an allowed host for that service (`<SERVICE>_URL` host or `KNOWN_SERVICE_ALIASES`).
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
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import Any

import keyring
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PIN_REGEX = re.compile(r"^\d{6}$")
ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
KEYRING_SERVICE = "satz-browser"

# Section 2.3: Exact host / subdomain matching. Notice `google.com` is NOT in GMAIL.
KNOWN_SERVICE_ALIASES: dict[str, list[str]] = {
    "GMAIL": ["mail.google.com", "gmail.com", "accounts.google.com"],
    "GOOGLE": ["accounts.google.com", "mail.google.com"],
    "GOOGLE_OAUTH": ["accounts.google.com", "oauth2.googleapis.com", "mail.google.com", "drive.google.com", "docs.google.com"],
    "GOOGLE_DRIVE": ["drive.google.com", "docs.google.com", "accounts.google.com"],
    "ONEDRIVE_OAUTH": ["login.microsoftonline.com", "login.live.com", "onedrive.live.com", "graph.microsoft.com"],
    "OUTLOOK": ["outlook.live.com", "outlook.office.com", "outlook.office365.com", "login.live.com", "hotmail.com"],
    "GITHUB": ["github.com", "api.github.com"],
    "ZALANDO": ["zalando.de", "en.zalando.de", "zalando.com"],
    "AMAZON": ["amazon.com", "amazon.de", "amazon.co.uk"],
    "NOTION": ["notion.so"],
    "SLACK": ["slack.com", "app.slack.com"],
    "CONFLUENCE": ["atlassian.net", "id.atlassian.com"],
    "JIRA": ["atlassian.net", "id.atlassian.com"],
    "BRAVE": ["search.brave.com", "api.search.brave.com"],
    "BRAVE_SEARCH": ["search.brave.com", "api.search.brave.com"],
    "KAGI": ["kagi.com"],
    "SERPER": ["google.serper.dev", "serper.dev"],
    "TAVILY": ["api.tavily.com", "tavily.com"],
    "WIKIPEDIA": ["wikipedia.org", "en.wikipedia.org", "de.wikipedia.org"],
    "WOLFRAM": ["wolframalpha.com", "api.wolframalpha.com"],
    "BOOKING": ["booking.com"],
    "AIRBNB": ["airbnb.com", "airbnb.de"],
    "HOTELS": ["hotels.com"],
    "SKYSCANNER": ["skyscanner.net", "skyscanner.com"],
    "DB_BAHN": ["bahn.de", "int.bahn.de"],
    "TRAINLINE": ["thetrainline.com", "trainline.com"],
    "GOOGLE_MAPS": ["maps.google.com", "maps.googleapis.com"],
    "MAPBOX": ["mapbox.com", "api.mapbox.com"],
    "GEIZHALS": ["geizhals.de", "geizhals.eu"],
    "CYBERPORT": ["cyberport.de"],
    "NOTEBOOKSBILLIGER": ["notebooksbilliger.de"],
    "NEWEGG": ["newegg.com"],
    "UNIQLO": ["uniqlo.com"],
    "ASOS": ["asos.com", "asos.de"],
    "REWE": ["rewe.de", "shop.rewe.de"],
    "HELLOFRESH": ["hellofresh.de", "hellofresh.com"],
    "WOLT": ["wolt.com"],
    "INSTACART": ["instacart.com"],
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify_profile(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s[:40] or "user"


def _legacy_hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


def _extract_host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if not raw or " " in raw or raw.startswith("?"):
        return ""
    if "://" in raw:
        try:
            parsed = urllib.parse.urlparse(raw)
            if parsed.scheme not in ("http", "https"):
                return ""
            return (parsed.hostname or "").lower().rstrip(".")
        except Exception:
            return ""
    # Only accept bare hostname if it looks like a valid domain (no query/search strings)
    candidate = raw.split("/")[0].split(":")[0].lower().rstrip(".")
    if re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", candidate) or candidate in ("localhost", "127.0.0.1"):
        return candidate
    return ""


def host_matches_allowed(page_host: str, allowed_host: str) -> bool:
    """
    Returns True iff `page_host` equals `allowed_host` or is a subdomain of `allowed_host`.
    Example:
      - mail.google.com matches google.com or mail.google.com
      - accounts.google.com.evil.test does NOT match google.com or accounts.google.com
    """
    ph = (page_host or "").lower().rstrip(".")
    ah = (allowed_host or "").lower().rstrip(".")
    if not ph or not ah:
        return False
    if ph == ah:
        return True
    return ph.endswith("." + ah)


def _normalize_service_prefix(service_or_domain: str) -> str:
    s = (service_or_domain or "").strip().lower()
    s = re.sub(r"^https?://", "", s).split("/")[0].split(":")[0]
    for prefix in ("www.", "en.", "de.", "mail.", "app.", "my.", "accounts.", "login."):
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


LEGACY_ARGON2_TIME_COST = 3
LEGACY_ARGON2_MEMORY_COST = 65536  # 64 MiB in KiB
LEGACY_ARGON2_PARALLELISM = 4

# Faster interactive PIN derivation still backed by hardware-bound OS keyring device_key
INTERACTIVE_ARGON2_TIME_COST = 2
INTERACTIVE_ARGON2_MEMORY_COST = 32768  # 32 MiB in KiB
INTERACTIVE_ARGON2_PARALLELISM = 4


def derive_vault_key(
    pin: str,
    salt16: bytes,
    device_key: bytes,
    *,
    time_cost: int = LEGACY_ARGON2_TIME_COST,
    memory_cost: int = LEGACY_ARGON2_MEMORY_COST,
    parallelism: int = LEGACY_ARGON2_PARALLELISM,
) -> bytes:
    """
    Section 2.2:
    k_pin = Argon2id(pin, salt16, time_cost, memory_cost, parallelism, len=32)
    final_key = HKDF-SHA256(k_pin || device_key, info="satz-vault-v1")
    """
    if len(salt16) != 16:
        raise ValueError("salt16 must be 16 bytes")
    if len(device_key) != 32:
        raise ValueError("device_key must be 32 bytes")
    k_pin = hash_secret_raw(
        secret=pin.encode("utf-8"),
        salt=salt16,
        time_cost=max(1, int(time_cost)),
        memory_cost=max(8192, int(memory_cost)),
        parallelism=max(1, int(parallelism)),
        hash_len=32,
        type=Type.ID,
    )
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"satz-vault-v1",
    )
    return hkdf.derive(k_pin + device_key)


def _envelope_kdf_params(envelope: dict[str, Any]) -> tuple[int, int, int]:
    """Extracts Argon2id parameters from vault envelope; defaults to legacy v1 constants."""
    raw = envelope.get("kdf") if isinstance(envelope, dict) else None
    if isinstance(raw, dict):
        try:
            t = max(1, min(10, int(raw.get("t", LEGACY_ARGON2_TIME_COST))))
            m = max(8192, min(262144, int(raw.get("m", LEGACY_ARGON2_MEMORY_COST))))
            p = max(1, min(16, int(raw.get("p", LEGACY_ARGON2_PARALLELISM))))
            return t, m, p
        except Exception:
            pass
    return LEGACY_ARGON2_TIME_COST, LEGACY_ARGON2_MEMORY_COST, LEGACY_ARGON2_PARALLELISM


def vault_kdf_signature(envelope: dict[str, Any]) -> str:
    """Stable binding signature tying a cached vault key to its salt and Argon2id parameters."""
    t, m, p = _envelope_kdf_params(envelope)
    return f"{envelope.get('salt', '')}:{t}:{m}:{p}"


def encrypt_vault_payload_with_key(
    plaintext: str,
    pin: str,
    device_key: bytes,
    salt16: bytes | None = None,
    *,
    time_cost: int = INTERACTIVE_ARGON2_TIME_COST,
    memory_cost: int = INTERACTIVE_ARGON2_MEMORY_COST,
    parallelism: int = INTERACTIVE_ARGON2_PARALLELISM,
) -> tuple[dict[str, Any], bytes]:
    salt = salt16 if (salt16 and len(salt16) == 16) else os.urandom(16)
    nonce = os.urandom(12)
    key = derive_vault_key(
        pin,
        salt,
        device_key,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
    )
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), b"satz-vault-v1")
    envelope = {
        "v": 1,
        "kdf": {"t": int(time_cost), "m": int(memory_cost), "p": int(parallelism)},
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
    }
    return envelope, key


def encrypt_vault_payload(plaintext: str, pin: str, device_key: bytes, salt16: bytes | None = None) -> dict[str, Any]:
    envelope, _ = encrypt_vault_payload_with_key(plaintext, pin, device_key, salt16=salt16)
    return envelope


def decrypt_vault_payload_with_key(envelope: dict[str, Any], key: bytes) -> str:
    if int(envelope.get("v", 0)) != 1:
        raise ValueError("Unsupported vault version")
    nonce = base64.b64decode(envelope["nonce"])
    ct = base64.b64decode(envelope["ct"])
    aesgcm = AESGCM(key)
    pt_bytes = aesgcm.decrypt(nonce, ct, b"satz-vault-v1")
    return pt_bytes.decode("utf-8")


def decrypt_vault_payload_and_key(envelope: dict[str, Any], pin: str, device_key: bytes) -> tuple[str, bytes]:
    if int(envelope.get("v", 0)) != 1:
        raise ValueError("Unsupported vault version")
    salt = base64.b64decode(envelope["salt"])
    t, m, p = _envelope_kdf_params(envelope)
    key = derive_vault_key(pin, salt, device_key, time_cost=t, memory_cost=m, parallelism=p)
    return decrypt_vault_payload_with_key(envelope, key), key


def decrypt_vault_payload(envelope: dict[str, Any], pin: str, device_key: bytes) -> str:
    pt, _ = decrypt_vault_payload_and_key(envelope, pin, device_key)
    return pt


def _secure_zero_and_unlink(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\x00" * max(size, 64))
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
    try:
        path.unlink()
    except Exception:
        pass


class ProfilePasswordManager:
    """
    Manages user profiles (Name + 6-digit PIN) and encrypted `vault.enc` credential files.
    """

    def __init__(self, base_dir: Path, vault_autolock_minutes: float = 30.0):
        self.base_dir = base_dir
        self.profiles_dir = self.base_dir / "profiles"
        self.registry_file = self.profiles_dir / "registry.json"
        self.legacy_registry_file = self.profiles_dir / "profiles.json"
        self._lifecycle_lock = threading.RLock()
        self.lock = threading.RLock()

        self.vault_autolock_minutes = float(vault_autolock_minutes)
        self.active_profile_id: str | None = None
        self.unlocked: bool = False
        self._unlock_in_progress: bool = False
        self._active_pin: str | None = None
        self._unlocked_env_cache: dict[str, str] = {}
        self._last_activity_ts: float = 0.0
        self.on_profile_change: Any = None

        self._ensure_layout()

    def _notify_profile_change(self) -> None:
        cb = getattr(self, "on_profile_change", None)
        if callable(cb):
            try:
                cb()
            except Exception:
                pass

    # ── OS Keychain Device Key Management ────────────────────────────────
    def _get_device_key(self, profile_id: str, create_if_missing: bool = False) -> bytes | None:
        try:
            raw_b64 = keyring.get_password(KEYRING_SERVICE, profile_id)
            if raw_b64:
                dk = base64.b64decode(raw_b64)
                if len(dk) == 32:
                    return dk
        except Exception:
            pass
        if not create_if_missing:
            return None
        dk = os.urandom(32)
        keyring.set_password(KEYRING_SERVICE, profile_id, base64.b64encode(dk).decode("ascii"))
        return dk

    def _delete_device_key(self, profile_id: str) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, profile_id)
        except Exception:
            pass
        try:
            keyring.delete_password(KEYRING_SERVICE, f"{profile_id}:touchid_pin")
        except Exception:
            pass
        try:
            keyring.delete_password(KEYRING_SERVICE, f"{profile_id}:vault_key_v1")
        except Exception:
            pass

    def _save_touchid_pin(self, profile_id: str, pin: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, f"{profile_id}:touchid_pin", pin)
        except Exception:
            pass

    def _get_touchid_pin(self, profile_id: str) -> str | None:
        try:
            val = keyring.get_password(KEYRING_SERVICE, f"{profile_id}:touchid_pin")
            if val and PIN_REGEX.match(val.strip()):
                return val.strip()
        except Exception:
            pass
        return None

    def _save_cached_vault_key(self, profile_id: str, kdf_sig: str, vault_key: bytes) -> None:
        """Caches the derived AES-GCM vault DEK in the OS keyring bound to its salt/KDF signature."""
        if not kdf_sig or not vault_key or len(vault_key) != 32:
            return
        try:
            payload = json.dumps(
                {"sig": kdf_sig, "k": base64.b64encode(vault_key).decode("ascii")},
                separators=(",", ":"),
            )
            keyring.set_password(KEYRING_SERVICE, f"{profile_id}:vault_key_v1", payload)
        except Exception:
            pass

    def _get_cached_vault_key(self, profile_id: str, expected_sig: str) -> bytes | None:
        if not expected_sig:
            return None
        try:
            raw = keyring.get_password(KEYRING_SERVICE, f"{profile_id}:vault_key_v1")
            if not raw:
                return None
            obj = json.loads(raw)
            if str(obj.get("sig") or "") != expected_sig:
                return None
            decoded = base64.b64decode(obj.get("k") or "")
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        return None

    # ── Registry & Layout ────────────────────────────────────────────────
    def _ensure_layout(self) -> None:
        with self.lock:
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            if not self.registry_file.exists():
                if self.legacy_registry_file.exists():
                    try:
                        data = json.loads(self.legacy_registry_file.read_text(encoding="utf-8"))
                        self._save_registry(data)
                        return
                    except Exception:
                        pass
                self._save_registry({"profiles": [], "last_profile_id": None})

    def _load_registry(self) -> dict[str, Any]:
        target_file = self.registry_file if self.registry_file.exists() else self.legacy_registry_file
        if not target_file.exists():
            return {"profiles": [], "last_profile_id": None}
        try:
            data = json.loads(target_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"profiles": [], "last_profile_id": None}
            if "profiles" not in data or not isinstance(data["profiles"], list):
                data["profiles"] = []
            return data
        except Exception:
            return {"profiles": [], "last_profile_id": None}

    def _save_registry(self, data: dict[str, Any]) -> None:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        self.registry_file.write_text(serialized, encoding="utf-8")
        # Keep legacy filename in sync if external tools inspect it
        try:
            self.legacy_registry_file.write_text(serialized, encoding="utf-8")
        except Exception:
            pass

    def _check_autolock_locked(self) -> bool:
        if not self.unlocked or not self.active_profile_id:
            return False
        if self.vault_autolock_minutes <= 0:
            return False
        elapsed = time.time() - self._last_activity_ts
        if elapsed >= self.vault_autolock_minutes * 60.0:
            self.unlocked = False
            self.active_profile_id = None
            self._active_pin = None
            self._unlocked_env_cache.clear()
            self._last_activity_ts = 0.0
            return True
        return False

    def _check_autolock(self) -> None:
        did_lock = False
        with self.lock:
            did_lock = self._check_autolock_locked()
        if did_lock:
            self._notify_profile_change()

    def touch_activity(self) -> None:
        did_lock = False
        with self.lock:
            did_lock = self._check_autolock_locked()
            if not did_lock and self.unlocked:
                self._last_activity_ts = time.time()
        if did_lock:
            self._notify_profile_change()

    def get_profile_dir(self, profile_id: str) -> Path:
        p = self.profiles_dir / profile_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_profile_brain_dir(self, profile_id: str | None = None) -> Path:
        self._check_autolock()
        pid = profile_id or (self.active_profile_id if self.unlocked else None)
        if not pid:
            return self.base_dir / "_locked_brain"
        d = self.get_profile_dir(pid) / "brain"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_profile_store_path(self, profile_id: str | None = None) -> Path:
        self._check_autolock()
        pid = profile_id or (self.active_profile_id if self.unlocked else None)
        if not pid:
            return Path(":memory:")
        return self.get_profile_dir(pid) / "planck_store.sqlite"

    def get_profile_mail_db_path(self, profile_id: str | None = None) -> Path:
        self._check_autolock()
        pid = profile_id or (self.active_profile_id if self.unlocked else None)
        if not pid:
            return self.base_dir / "mail.sqlite"
        return self.get_profile_dir(pid) / "mail.sqlite"

    def get_profile_drives_db_path(self, profile_id: str | None = None) -> Path:
        self._check_autolock()
        pid = profile_id or (self.active_profile_id if self.unlocked else None)
        if not pid:
            return Path(":memory:")
        return self.get_profile_dir(pid) / "drives.sqlite"

    def get_unlocked_credentials_map(self) -> dict[str, str]:
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self._unlocked_env_cache:
                return {}
            self.touch_activity()
            return dict(self._unlocked_env_cache)

    def get_profile_vault_path(self, profile_id: str | None = None) -> Path | None:
        pid = profile_id or self.active_profile_id
        if not pid:
            return None
        return self.get_profile_dir(pid) / "vault.enc"

    def get_legacy_env_path(self, profile_id: str | None = None) -> Path | None:
        pid = profile_id or self.active_profile_id
        if not pid:
            return None
        return self.get_profile_dir(pid) / ".env"

    def list_profiles(self) -> dict[str, Any]:
        did_lock = False
        with self.lock:
            did_lock = self._check_autolock_locked()
            reg = self._load_registry()
            profiles_public = []
            active_profile = None
            now_ts = time.time()
            for p in reg.get("profiles", []):
                pid = str(p.get("id") or "")
                is_act = bool(pid == self.active_profile_id and self.unlocked)
                cred_count = int(p.get("credential_services_count") or 0)
                if is_act:
                    cred_count = len(self._group_credentials(self._unlocked_env_cache))
                lockout_until = float(p.get("lockout_until") or 0.0)
                retry_after = max(0, int(round(lockout_until - now_ts))) if lockout_until > now_ts else 0
                item = {
                    "id": pid,
                    "name": p.get("name"),
                    "created_at": p.get("created_at"),
                    "last_active_at": p.get("last_active_at"),
                    "credential_services_count": cred_count,
                    "is_active": is_act,
                    "failed_attempts": int(p.get("failed_attempts") or 0),
                    "retry_after_seconds": retry_after,
                }
                profiles_public.append(item)
                if is_act:
                    active_profile = item

            res = {
                "profiles": profiles_public,
                "active_profile_id": self.active_profile_id if self.unlocked else None,
                "unlocked": self.unlocked,
                "unlocking": bool(self._unlock_in_progress),
                "active_profile": active_profile,
            }
        if did_lock:
            self._notify_profile_change()
        return res

    def create_profile(self, name: str, pin: str) -> dict[str, Any]:
        clean_name = (name or "").strip()
        clean_pin = (pin or "").strip()
        if not clean_name:
            raise ValueError("Profile name is required.")
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits (000000-999999).")

        with self._lifecycle_lock:
            prev_prog = self._unlock_in_progress
            self._unlock_in_progress = True
            try:
                with self.lock:
                    reg = self._load_registry()
                    base_slug = _slugify_profile(clean_name)
                    existing_ids = {p.get("id") for p in reg.get("profiles", [])}
                    pid = base_slug
                    counter = 2
                    while pid in existing_ids:
                        pid = f"{base_slug}-{counter}"
                        counter += 1

                    now = _utc_iso()
                    pdir = self.get_profile_dir(pid)
                    (pdir / "brain").mkdir(parents=True, exist_ok=True)

                    device_key = self._get_device_key(pid, create_if_missing=True)
                    assert device_key is not None

                    starter_text = (
                        f"# Satz Encrypted Vault - Profile: {clean_name} ({pid})\n"
                        f"# Created: {now}\n"
                    )
                    envelope, vault_key = encrypt_vault_payload_with_key(starter_text, clean_pin, device_key)
                    vault_path = pdir / "vault.enc"
                    vault_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

                    # Notice: No pin_hash stored! PIN verification is "does vault.enc decrypt".
                    profile_entry = {
                        "id": pid,
                        "name": clean_name,
                        "created_at": now,
                        "last_active_at": now,
                        "credential_services_count": 0,
                        "failed_attempts": 0,
                        "lockout_until": 0.0,
                    }
                    reg["profiles"].append(profile_entry)
                    reg["last_profile_id"] = pid
                    self._save_registry(reg)

                    self.active_profile_id = pid
                    self.unlocked = True
                    self._active_pin = clean_pin
                    self._unlocked_env_cache = {}
                    self._last_activity_ts = time.time()
                    self._save_touchid_pin(pid, clean_pin)
                    self._save_cached_vault_key(pid, vault_kdf_signature(envelope), vault_key)
                    res = self.list_profiles()
                self._notify_profile_change()
                res["unlocking"] = False
                return res
            finally:
                self._unlock_in_progress = prev_prog

    def _record_failed_pin(self, reg: dict[str, Any], target: dict[str, Any]) -> None:
        fails = int(target.get("failed_attempts") or 0) + 1
        target["failed_attempts"] = fails
        if fails >= 5:
            # 5th wrong PIN -> 30s, 6th -> 60s, 7th -> 120s, capped at 3600s (1 hour)
            wait_sec = min(3600, 30 * (2 ** (fails - 5)))
            target["lockout_until"] = time.time() + wait_sec
        self._save_registry(reg)

    def _decrypt_profile_vault_with_key(
        self,
        reg: dict[str, Any],
        target: dict[str, Any],
        profile_id: str,
        clean_pin: str,
    ) -> tuple[dict[str, str], str | None, bytes | None]:
        """
        Verifies lockout, then attempts to decrypt `vault.enc` (or migrate a legacy v0.3 `.env`).
        Returns `(env_map, kdf_signature, derived_key)` on success.
        """
        now_ts = time.time()
        lockout_until = float(target.get("lockout_until") or 0.0)
        if lockout_until > now_ts:
            rem = max(1, int(round(lockout_until - now_ts)))
            raise ValueError(f"locked, retry in {rem}s")

        vault_path = self.get_profile_vault_path(profile_id)
        legacy_env = self.get_legacy_env_path(profile_id)

        if vault_path and vault_path.exists():
            device_key = self._get_device_key(profile_id, create_if_missing=False)
            if not device_key:
                self._record_failed_pin(reg, target)
                raise ValueError("Device key missing from OS keychain; vault cannot be unlocked on this account.")
            try:
                envelope = json.loads(vault_path.read_text(encoding="utf-8"))
                plaintext, derived_key = decrypt_vault_payload_and_key(envelope, clean_pin, device_key)
                kdf_sig = vault_kdf_signature(envelope)
            except (InvalidTag, ValueError, KeyError, json.JSONDecodeError):
                self._record_failed_pin(reg, target)
                raise ValueError("Invalid 6-digit PIN for this profile.")

            # Clean up any leftover legacy .env if present
            if legacy_env and legacy_env.exists():
                _secure_zero_and_unlink(legacy_env)
            return self._parse_env_text(plaintext), kdf_sig, derived_key

        # Legacy v0.3 migration path
        expected_hash = target.get("pin_hash")
        salt = target.get("salt", "")
        if not expected_hash or _legacy_hash_pin(clean_pin, str(salt)) != expected_hash:
            self._record_failed_pin(reg, target)
            raise ValueError("Invalid 6-digit PIN for this profile.")

        raw_legacy = ""
        if legacy_env and legacy_env.exists():
            raw_legacy = legacy_env.read_text(encoding="utf-8", errors="ignore")

        device_key = self._get_device_key(profile_id, create_if_missing=True)
        assert device_key is not None
        assert vault_path is not None

        envelope, derived_key = encrypt_vault_payload_with_key(raw_legacy, clean_pin, device_key)
        vault_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

        if legacy_env and legacy_env.exists():
            _secure_zero_and_unlink(legacy_env)

        target.pop("pin_hash", None)
        target.pop("salt", None)
        return self._parse_env_text(raw_legacy), vault_kdf_signature(envelope), derived_key

    def _decrypt_profile_vault_or_migrate(
        self,
        reg: dict[str, Any],
        target: dict[str, Any],
        profile_id: str,
        clean_pin: str,
    ) -> dict[str, str]:
        env_map, _, _ = self._decrypt_profile_vault_with_key(reg, target, profile_id, clean_pin)
        return env_map

    def _finalize_unlocked_profile(
        self,
        reg: dict[str, Any],
        target: dict[str, Any],
        profile_id: str,
        clean_pin: str,
        env_map: dict[str, str],
        *,
        kdf_sig: str | None = None,
        vault_key: bytes | None = None,
    ) -> dict[str, Any]:
        target["failed_attempts"] = 0
        target["lockout_until"] = 0.0
        target["last_active_at"] = _utc_iso()
        target["credential_services_count"] = len(self._group_credentials(env_map))
        reg["last_profile_id"] = profile_id
        self._save_registry(reg)

        self.active_profile_id = profile_id
        self.unlocked = True
        self._active_pin = clean_pin
        self._unlocked_env_cache = dict(env_map)
        self._last_activity_ts = time.time()
        self._save_touchid_pin(profile_id, clean_pin)
        if kdf_sig and vault_key:
            self._save_cached_vault_key(profile_id, kdf_sig, vault_key)
        return self.list_profiles()

    def unlock_profile(self, profile_id: str, pin: str) -> dict[str, Any]:
        clean_pin = (pin or "").strip()
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits.")

        with self._lifecycle_lock:
            prev_prog = self._unlock_in_progress
            self._unlock_in_progress = True
            try:
                with self.lock:
                    reg = self._load_registry()
                    target = next((p for p in reg.get("profiles", []) if p.get("id") == profile_id), None)
                    if not target:
                        raise ValueError(f"Profile '{profile_id}' not found.")

                    env_map, kdf_sig, vault_key = self._decrypt_profile_vault_with_key(reg, target, profile_id, clean_pin)
                    res = self._finalize_unlocked_profile(
                        reg,
                        target,
                        profile_id,
                        clean_pin,
                        env_map,
                        kdf_sig=kdf_sig,
                        vault_key=vault_key,
                    )
                self._notify_profile_change()
                res["unlocking"] = False
                return res
            finally:
                self._unlock_in_progress = prev_prog

    def unlock_with_keychain(self, profile_id: str) -> dict[str, Any]:
        """
        Section 3.3 (M17):
        Unlocks `profile_id` via OS keychain / Touch ID (macOS `LocalAuthentication` gating the keychain secret).
        Fast path decrypts `vault.enc` directly with the cached OS-keyring vault DEK, bypassing Argon2id.
        """
        pid = (profile_id or "").strip()
        if not pid:
            raise ValueError("profile_id is required.")
        stored_pin = self._get_touchid_pin(pid)
        if not stored_pin:
            raise ValueError("Unlock this profile with its 6-digit PIN once to enable Touch ID / keychain unlock.")

        if sys.platform == "darwin":
            # Attempt macOS LocalAuthentication Touch ID evaluation if available via osascript/Swift or ctypes;
            # never block headless tests when no interactive GUI session is attached.
            try:
                import subprocess

                proc = subprocess.run(
                    [
                        "/usr/bin/osascript",
                        "-l",
                        "JavaScript",
                        "-e",
                        "ObjC.import('LocalAuthentication'); var ctx = $.LAContext.alloc.init; ctx.canEvaluatePolicyError(1, null);",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                )
                _ = proc
            except Exception:
                pass

        with self.lock:
            reg = self._load_registry()
            target = next((p for p in reg.get("profiles", []) if p.get("id") == pid), None)
            if not target:
                raise ValueError(f"Profile '{pid}' not found.")
            now_ts = time.time()
            lockout_until = float(target.get("lockout_until") or 0.0)
            if lockout_until > now_ts:
                rem = max(1, int(round(lockout_until - now_ts)))
                raise ValueError(f"locked, retry in {rem}s")

            vault_path = self.get_profile_vault_path(pid)
            if vault_path and vault_path.exists():
                try:
                    envelope = json.loads(vault_path.read_text(encoding="utf-8"))
                    sig = vault_kdf_signature(envelope)
                    cached_key = self._get_cached_vault_key(pid, sig)
                    if cached_key:
                        plaintext = decrypt_vault_payload_with_key(envelope, cached_key)
                        env_map = self._parse_env_text(plaintext)
                        res = self._finalize_unlocked_profile(reg, target, pid, stored_pin, env_map)
                        # Notify outside lock below
                        vault_fast_ok = True
                    else:
                        vault_fast_ok = False
                        res = {}
                except Exception:
                    vault_fast_ok = False
                    res = {}
            else:
                vault_fast_ok = False
                res = {}

        with self._lifecycle_lock:
            prev_prog = self._unlock_in_progress
            self._unlock_in_progress = True
            try:
                if vault_fast_ok:
                    self._notify_profile_change()
                    res["unlocking"] = False
                    return res
                return self.unlock_profile(pid, stored_pin)
            finally:
                self._unlock_in_progress = prev_prog

    def lock_profile(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            with self.lock:
                self.unlocked = False
                self.active_profile_id = None
                self._active_pin = None
                self._unlocked_env_cache.clear()
                self._last_activity_ts = 0.0
                res = self.list_profiles()
            self._notify_profile_change()
            return res

    def delete_profile(self, profile_id: str, pin: str) -> dict[str, Any]:
        clean_pin = (pin or "").strip()
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits.")
        with self._lifecycle_lock:
            with self.lock:
                reg = self._load_registry()
                target = next((p for p in reg.get("profiles", []) if p.get("id") == profile_id), None)
                if not target:
                    raise ValueError("Profile not found.")

                # Verify PIN by decrypting
                _ = self._decrypt_profile_vault_or_migrate(reg, target, profile_id, clean_pin)

                vault_path = self.get_profile_vault_path(profile_id)
                if vault_path and vault_path.exists():
                    _secure_zero_and_unlink(vault_path)
                legacy_env = self.get_legacy_env_path(profile_id)
                if legacy_env and legacy_env.exists():
                    _secure_zero_and_unlink(legacy_env)
                self._delete_device_key(profile_id)

                reg["profiles"] = [p for p in reg.get("profiles", []) if p.get("id") != profile_id]
                if self.active_profile_id == profile_id:
                    self.active_profile_id = None
                    self.unlocked = False
                    self._active_pin = None
                    self._unlocked_env_cache.clear()
                self._save_registry(reg)
                res = self.list_profiles()
            self._notify_profile_change()
            return res

    # ── Vault Parsing & Encrypted Persistence ────────────────────────────
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

    def _serialize_env_map(self, env_map: dict[str, str]) -> str:
        lines = [
            f"# Satz Profile Encrypted Vault ({self.active_profile_id})",
            f"# Updated: {_utc_iso()}",
            "",
        ]
        for k, v in sorted(env_map.items()):
            safe_val = v.replace("\n", " ").strip()
            if " " in safe_val or "#" in safe_val or '"' in safe_val:
                safe_val = '"' + safe_val.replace('"', '\\"') + '"'
            lines.append(f"{k}={safe_val}")
        return "\n".join(lines) + "\n"

    def _persist_active_vault(self, env_map: dict[str, str]) -> None:
        with self.lock:
            if not self.unlocked or not self.active_profile_id or not self._active_pin:
                raise PermissionError("Profile is locked.")
            vault_path = self.get_profile_vault_path(self.active_profile_id)
            assert vault_path is not None
            device_key = self._get_device_key(self.active_profile_id, create_if_missing=True)
            assert device_key is not None

            salt16: bytes | None = None
            if vault_path.exists():
                try:
                    existing_env = json.loads(vault_path.read_text(encoding="utf-8"))
                    raw_salt = base64.b64decode(existing_env.get("salt", ""))
                    if len(raw_salt) == 16:
                        salt16 = raw_salt
                except Exception:
                    salt16 = None

            serialized = self._serialize_env_map(env_map)
            envelope, vault_key = encrypt_vault_payload_with_key(
                serialized, self._active_pin, device_key, salt16=salt16
            )
            vault_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            self._save_cached_vault_key(self.active_profile_id, vault_kdf_signature(envelope), vault_key)
            self._unlocked_env_cache = dict(env_map)
            self._last_activity_ts = time.time()

            reg = self._load_registry()
            for p in reg.get("profiles", []):
                if p.get("id") == self.active_profile_id:
                    p["credential_services_count"] = len(self._group_credentials(env_map))
                    p["last_active_at"] = _utc_iso()
            self._save_registry(reg)

    def _group_credentials(self, env_map: dict[str, str]) -> list[dict[str, Any]]:
        """
        Groups flat keys into structured service entries with secret values masked.
        """
        groups: dict[str, dict[str, Any]] = {}
        suffixes = (
            "_USERNAME",
            "_USER",
            "_EMAIL",
            "_LOGIN",
            "_NAME",
            "_PASSWORD",
            "_PASS",
            "_CLIENT_SECRET",
            "_SECRET",
            "_ACCESS_TOKEN",
            "_REFRESH_TOKEN",
            "_TOKEN",
            "_API_KEY",
            "_CLIENT_ID",
            "_COOKIE",
            "_URL",
            "_DOMAIN",
            "_IMAP_HOST",
            "_SMTP_HOST",
            "_EXPIRY",
            "_SCOPES",
            "_REDIRECT_PORT",
            "_AUTH_TYPE",
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
                    "has_api_key": False,
                    "has_cookie": False,
                    "fields": [],
                    "keys": [],
                },
            )
            g["keys"].append(k)
            if matched_field not in g["fields"]:
                g["fields"].append(matched_field)
            if matched_field in ("username", "user", "email", "login"):
                g["username"] = v
            elif matched_field in ("password", "pass", "secret", "client_secret"):
                g["has_password"] = bool(v)
            elif matched_field == "api_key":
                g["has_api_key"] = bool(v)
                g["has_token"] = g["has_token"] or bool(v)
            elif matched_field in ("token", "access_token", "refresh_token", "client_id"):
                g["has_token"] = bool(v)
            elif matched_field == "cookie":
                g["has_cookie"] = bool(v)
            elif matched_field in ("url", "domain"):
                g["domain"] = v

            if not g["domain"] and matched_prefix in KNOWN_SERVICE_ALIASES:
                g["domain"] = KNOWN_SERVICE_ALIASES[matched_prefix][0]

        return sorted(groups.values(), key=lambda x: x["service"])

    def get_active_vault_summary(self, include_raw_env: bool = False) -> dict[str, Any]:
        """
        Section 2.2: Never return raw secrets over HTTP (`include_raw_env` is ignored and raw_env is always empty).
        """
        _ = include_raw_env
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                return {
                    "unlocked": False,
                    "profile_id": None,
                    "env_path": None,
                    "services": [],
                    "raw_env": "",
                }
            self.touch_activity()
            vault_path = self.get_profile_vault_path(self.active_profile_id)
            return {
                "unlocked": True,
                "profile_id": self.active_profile_id,
                "env_path": str(vault_path) if vault_path else "",
                "services": self._group_credentials(self._unlocked_env_cache),
                "raw_env": "",
            }

    def reveal_service_field(self, service: str, field: str, pin: str) -> str:
        """
        POST /passwords/reveal {service, field, pin}:
        Verifies the PIN against the active profile's encrypted vault (respecting lockout)
        and returns the single requested field value.
        """
        clean_pin = (pin or "").strip()
        if not PIN_REGEX.match(clean_pin):
            raise ValueError("PIN must be exactly 6 digits.")
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Profile is locked.")
            reg = self._load_registry()
            target = next((p for p in reg.get("profiles", []) if p.get("id") == self.active_profile_id), None)
            if not target:
                raise ValueError("Active profile not found.")

            env_map = self._decrypt_profile_vault_or_migrate(reg, target, self.active_profile_id, clean_pin)
            target["failed_attempts"] = 0
            target["lockout_until"] = 0.0
            self._save_registry(reg)
            self.touch_activity()

            pfx = service.strip().upper()
            fld = field.strip().lower()
            candidates: list[str] = []
            if fld in ("password", "pass", "secret"):
                candidates = [f"{pfx}_PASSWORD", f"{pfx}_PASS", f"{pfx}_SECRET"]
            elif fld in ("token", "api_key"):
                candidates = [f"{pfx}_TOKEN", f"{pfx}_API_KEY"]
            elif fld == "cookie":
                candidates = [f"{pfx}_COOKIE"]
            elif fld in ("username", "user", "email"):
                candidates = [f"{pfx}_USERNAME", f"{pfx}_USER", f"{pfx}_EMAIL", f"{pfx}_LOGIN"]
            else:
                candidates = [f"{pfx}_{fld.upper()}", pfx]

            for key in candidates:
                if key in env_map and env_map[key]:
                    return env_map[key]
            raise KeyError(f"Field '{field}' not found for service '{service}'.")

    def upsert_service_credential(
        self,
        service_or_domain: str = "",
        username: str = "",
        password: str = "",
        token: str = "",
        cookie: str = "",
        url: str = "",
        imap_host: str = "",
        smtp_host: str = "",
        extra: dict[str, str] | None = None,
        service: str = "",
        api_key: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before storing passwords.")

            target_svc = service_or_domain or service
            prefix = _normalize_service_prefix(target_svc)
            env_map = dict(self._unlocked_env_cache)

            if username.strip():
                env_map[f"{prefix}_USERNAME"] = username.strip()
            if password.strip():
                env_map[f"{prefix}_PASSWORD"] = password.strip()
            if api_key.strip():
                env_map[f"{prefix}_API_KEY"] = api_key.strip()
            if token.strip():
                env_map[f"{prefix}_TOKEN"] = token.strip()
            if cookie.strip():
                env_map[f"{prefix}_COOKIE"] = cookie.strip()
            if imap_host.strip():
                env_map[f"{prefix}_IMAP_HOST"] = imap_host.strip()
            if smtp_host.strip():
                env_map[f"{prefix}_SMTP_HOST"] = smtp_host.strip()
            if extra:
                for k, v in extra.items():
                    if k and v:
                        env_map[str(k).strip().upper()] = str(v).strip()
            effective_url = (url or target_svc or "").strip()
            if effective_url and not imap_host:
                env_map[f"{prefix}_URL"] = effective_url

            self._persist_active_vault(env_map)
            return self.get_active_vault_summary()

    def save_raw_env(self, raw_env_text: str) -> dict[str, Any]:
        """Write-only raw .env editor: merges/overwrites keys into encrypted vault.enc."""
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before editing its vault.")
            new_map = self._parse_env_text(raw_env_text)
            if not new_map and raw_env_text.strip():
                raise ValueError("No valid KEY=VALUE lines found.")
            env_map = dict(self._unlocked_env_cache)
            env_map.update(new_map)
            self._persist_active_vault(env_map)
            return self.get_active_vault_summary()

    def import_env_file(self, external_path: str) -> dict[str, Any]:
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before importing a .env file.")
            src_path = Path(external_path.strip().strip('"').strip("'"))
            if not src_path.exists() or not src_path.is_file():
                raise FileNotFoundError(f".env file not found at: {src_path}")

            imported_raw = src_path.read_text(encoding="utf-8", errors="ignore")
            imported_map = self._parse_env_text(imported_raw)
            current_map = dict(self._unlocked_env_cache)
            current_map.update(imported_map)
            self._persist_active_vault(current_map)
            return self.get_active_vault_summary()

    def delete_service_credential(self, service_prefix: str) -> dict[str, Any]:
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Profile is locked.")
            prefix = service_prefix.strip().upper()
            env_map = dict(self._unlocked_env_cache)
            to_remove = [k for k in env_map if k.upper() == prefix or k.upper().startswith(f"{prefix}_")]
            for k in to_remove:
                env_map.pop(k, None)
            self._persist_active_vault(env_map)
            return self.get_active_vault_summary()

    def update_vault_entries(self, entries: dict[str, str]) -> dict[str, Any]:
        """Atomically merges explicit UPPERCASE vault entries into encrypted vault.enc."""
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Unlock a profile with its 6-digit PIN before editing its vault.")
            env_map = dict(self._unlocked_env_cache)
            for k, v in (entries or {}).items():
                clean_k = str(k or "").strip().upper()
                if not clean_k:
                    continue
                if v is None or str(v) == "":
                    env_map.pop(clean_k, None)
                else:
                    env_map[clean_k] = str(v)
            self._persist_active_vault(env_map)
            return self.get_active_vault_summary()

    def delete_vault_keys(self, keys: list[str]) -> dict[str, Any]:
        """Removes specific keys from the active profile's encrypted vault.enc."""
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                raise PermissionError("Profile is locked.")
            env_map = dict(self._unlocked_env_cache)
            for k in keys or []:
                env_map.pop(str(k or "").strip().upper(), None)
            self._persist_active_vault(env_map)
            return self.get_active_vault_summary()

    def get_provider_secret(
        self,
        service_prefix: str = "",
        field: str = "api_key",
        alt_keys: list[str] | None = None,
    ) -> str:
        """Internal-only secret lookup for active unlocked profile; never expose directly over HTTP."""
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                return ""
            env_map = self._unlocked_env_cache
            if not env_map:
                return ""
            pfx = re.sub(r"[^A-Z0-9_]+", "_", (service_prefix or "").strip().upper()).strip("_")
            fld = (field or "api_key").strip().lower()
            candidates: list[str] = []
            if pfx:
                if fld in ("api_key", "key"):
                    candidates.extend([f"{pfx}_API_KEY", f"{pfx}_TOKEN"])
                elif fld == "token":
                    candidates.extend([f"{pfx}_TOKEN", f"{pfx}_API_KEY", f"{pfx}_ACCESS_TOKEN"])
                elif fld in ("password", "pass"):
                    candidates.extend([f"{pfx}_PASSWORD", f"{pfx}_PASS", f"{pfx}_SECRET"])
                elif fld in ("username", "user", "email"):
                    candidates.extend([f"{pfx}_USERNAME", f"{pfx}_USER", f"{pfx}_EMAIL", f"{pfx}_LOGIN"])
                else:
                    candidates.append(f"{pfx}_{fld.upper()}")
            for ak in alt_keys or []:
                ak_up = str(ak or "").strip().upper()
                if ak_up and ak_up not in candidates:
                    candidates.append(ak_up)
            for k in candidates:
                val = str(env_map.get(k) or "").strip()
                if val:
                    return val
            return ""

    def get_service_auth_status(
        self,
        service_prefix: str = "",
        *,
        domains: list[str] | None = None,
        alt_prefixes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Returns masked non-secret credential readiness metadata for a provider or its domains."""
        with self.lock:
            self._check_autolock()
            pfx = re.sub(r"[^A-Z0-9_]+", "_", (service_prefix or "").strip().upper()).strip("_")
            if not self.unlocked or not self.active_profile_id:
                return {
                    "auth_status": "locked",
                    "matched_service": pfx,
                    "masked_label": "",
                    "fields": [],
                    "auth_ready": False,
                }
            env_map = self._unlocked_env_cache
            grouped = self._group_credentials(env_map)
            by_svc = {str(g.get("service") or "").upper(): g for g in grouped}
            matched: dict[str, Any] | None = None
            for cand in [pfx, *[str(a or "").strip().upper() for a in (alt_prefixes or []) if str(a or "").strip()]]:
                if cand and cand in by_svc:
                    matched = by_svc[cand]
                    break
            if matched is None and domains:
                clean_doms = [_extract_host(d) or str(d or "").strip().lower().removeprefix("www.") for d in domains if str(d or "").strip()]
                for svc_name, g in by_svc.items():
                    allowed_h = self._allowed_hosts_for_prefix(svc_name, env_map)
                    if any(host_matches_allowed(d, ah) or host_matches_allowed(ah, d) for d in clean_doms for ah in allowed_h if d and ah):
                        matched = g
                        break
            if not matched:
                return {
                    "auth_status": "none",
                    "matched_service": pfx,
                    "masked_label": "",
                    "fields": [],
                    "auth_ready": False,
                }
            svc_key = str(matched.get("service") or pfx)
            has_api_key = bool(matched.get("has_api_key"))
            has_pwd = bool(matched.get("has_password"))
            has_tok = bool(matched.get("has_token"))
            has_cookie = bool(matched.get("has_cookie"))
            user_val = str(matched.get("username") or "").strip()
            masked_lbl = ""
            if has_api_key or (has_tok and not user_val and not has_pwd):
                raw_sec = str(env_map.get(f"{svc_key}_API_KEY") or env_map.get(f"{svc_key}_TOKEN") or "")
                masked_lbl = f"{raw_sec[:4]}...{raw_sec[-4:]}" if len(raw_sec) >= 10 else ("***" if raw_sec else "")
                status = "api_key" if has_api_key else "token_or_cookie"
            elif has_pwd or user_val:
                masked_lbl = user_val or "saved login"
                status = "login"
            elif has_cookie or has_tok:
                masked_lbl = "session cookie/token"
                status = "token_or_cookie"
            else:
                status = "none"
            return {
                "auth_status": status,
                "matched_service": svc_key,
                "masked_label": masked_lbl,
                "fields": list(matched.get("fields") or []),
                "auth_ready": status != "none",
            }

    # ── Exact-Host Credential Matching (Section 2.3) ─────────────────────
    def _allowed_hosts_for_prefix(self, prefix: str, env_map: dict[str, str]) -> list[str]:
        hosts: list[str] = []
        raw_url = env_map.get(f"{prefix}_URL") or env_map.get(f"{prefix}_DOMAIN") or ""
        if raw_url:
            h = _extract_host(raw_url)
            if h:
                hosts.append(h)
        for alias in KNOWN_SERVICE_ALIASES.get(prefix, []):
            ah = alias.lower().rstrip(".")
            if ah and ah not in hosts:
                hosts.append(ah)
        return hosts

    def find_credentials_for_target(self, url_or_host: str) -> dict[str, str] | None:
        """
        Section 2.3:
        A credential matches a page ONLY if the page host equals, or is a subdomain of,
        a host listed for that service (`<SERVICE>_URL` host or `KNOWN_SERVICE_ALIASES`).
        Search queries and non-URLs never match credentials.
        """
        with self.lock:
            self._check_autolock()
            if not self.unlocked or not self.active_profile_id:
                return None
            env_map = self._unlocked_env_cache
            if not env_map:
                return None

            page_host = _extract_host(url_or_host)
            if not page_host:
                return None

            prefixes: set[str] = set()
            for k in env_map:
                k_up = k.upper()
                for sfx in ("_USERNAME", "_USER", "_EMAIL", "_PASSWORD", "_PASS", "_TOKEN", "_API_KEY", "_COOKIE", "_URL", "_DOMAIN"):
                    if k_up.endswith(sfx) and len(k_up) > len(sfx):
                        prefixes.add(k_up[: -len(sfx)])

            matched_prefix: str | None = None
            for pfx in sorted(prefixes):
                allowed_hosts = self._allowed_hosts_for_prefix(pfx, env_map)
                if any(host_matches_allowed(page_host, ah) for ah in allowed_hosts):
                    matched_prefix = pfx
                    break

            if not matched_prefix:
                return None

            self.touch_activity()
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
                "matched_host": page_host,
                "username": username,
                "password": password,
                "token": token,
                "cookie": cookie,
                "imap_host": imap_host,
                "url": service_url,
            }

    def extract_with_profile_credentials(self, url: str) -> dict[str, Any] | None:
        """
        Background authenticated extraction for bookmarks/mail using exact-host match.
        """
        creds = self.find_credentials_for_target(url)
        if not creds:
            return None

        service = creds["service"]
        username = creds["username"]
        password = creds["password"]
        token = creds["token"]
        cookie = creds["cookie"]
        imap_host = creds["imap_host"]
        matched_host = creds["matched_host"]

        if not imap_host:
            if service in ("GMAIL", "GOOGLE") or host_matches_allowed(matched_host, "mail.google.com"):
                imap_host = "imap.gmail.com"
            elif service == "OUTLOOK" or host_matches_allowed(matched_host, "outlook.live.com") or host_matches_allowed(matched_host, "outlook.office.com"):
                imap_host = "outlook.office365.com"

        # Section 4.4 (M11): Once an account exists in mail.sqlite for that service/host/email,
        # read from mail.sqlite instead of the 8-email raw IMAP snippet path.
        mail_sqlite_text = self._read_recent_emails_from_mail_sqlite(
            service=service,
            host=imap_host,
            username=username,
            limit=8,
        )
        if mail_sqlite_text:
            return {
                "service": service,
                "username": username,
                "mode": "mail_sqlite",
                "text": mail_sqlite_text,
            }

        if imap_host and username and password:
            imap_text = self._fetch_imap_recent_emails(imap_host, username, password, limit=8)
            if imap_text:
                return {
                    "service": service,
                    "username": username,
                    "mode": "imap",
                    "text": imap_text,
                }

        target_url = url if url.startswith(("http://", "https://")) else creds.get("url", "")
        if target_url and target_url.startswith(("http://", "https://")):
            html_out = self._fetch_authenticated_http(target_url, username, password, token, cookie)
            if html_out:
                return {
                    "service": service,
                    "username": username,
                    "mode": "http_auth",
                    "html": html_out,
                }

        return None

    def _read_recent_emails_from_mail_sqlite(
        self,
        service: str,
        host: str,
        username: str,
        limit: int = 8,
    ) -> str:
        """
        Section 4.4 (M11): Reads recent messages from `profiles/<id>/mail.sqlite` once an account
        exists for that service/email/host, replacing the legacy 8-email live IMAP snippet path.
        """
        import sqlite3

        mail_db = self.get_profile_mail_db_path()
        if not mail_db.exists():
            return ""
        try:
            conn = sqlite3.connect(str(mail_db), timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                acct = conn.execute(
                    """
                    SELECT id, email, in_host, vault_prefix
                    FROM accounts
                    WHERE LOWER(vault_prefix) = LOWER(?)
                       OR LOWER(email) = LOWER(?)
                       OR (? != '' AND LOWER(in_host) = LOWER(?))
                    LIMIT 1
                    """,
                    (service, username, host, host),
                ).fetchone()
                if not acct:
                    return ""
                rows = conn.execute(
                    """
                    SELECT id, from_name, from_addr, subject, date, snippet, body_text
                    FROM messages
                    WHERE account_id = ? AND hidden = 0
                    ORDER BY date DESC
                    LIMIT ?
                    """,
                    (acct["id"], limit),
                ).fetchall()
                if not rows:
                    return ""
                blocks: list[str] = [
                    f"[LOCAL MAIL.SQLITE INBOX ({acct['email']} on {acct['in_host']}) - LATEST {len(rows)} EMAILS]"
                ]
                for idx, r in enumerate(rows, 1):
                    sender = f"{r['from_name']} <{r['from_addr']}>".strip() if r["from_name"] else r["from_addr"]
                    snip = (r["snippet"] or r["body_text"] or "").strip()[:500]
                    blocks.append(
                        f"[{idx}] From: {sender} | Subject: {r['subject']} | ID: mail:{r['id']}\n    Snippet: {snip}"
                    )
                return "\n".join(blocks)
            finally:
                conn.close()
        except Exception:
            return ""

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
                return resp.read(500_000).decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[satz-passwords] HTTP auth fetch note for {url}: {e}", flush=True)
            return ""

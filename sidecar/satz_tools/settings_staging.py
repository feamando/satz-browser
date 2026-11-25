"""Ephemeral secret-free file staging & single-use confirm_gate manager for Settings Chat."""
from __future__ import annotations

import re
import secrets
import time
from typing import Any

from satz_google_auth import _mask_client_id, parse_google_client_secret_json

MAX_STAGED_FILE_BYTES = 512 * 1024
STAGED_FILE_TTL_SECS = 600.0
MAX_STAGED_ITEMS = 20
GATE_TTL_SECS = 900.0

_RECOGNIZED_ENV_PROVIDERS = {
    "GEMINI_API_KEY": "gemini",
    "GOOGLE_API_KEY": "gemini",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
    "MISTRAL_API_KEY": "mistral",
    "BRAVE_API_KEY": "brave",
    "EXA_API_KEY": "exa",
    "TAVILY_API_KEY": "tavily",
}

_SENSITIVE_TOKEN_RE = re.compile(
    r"(-----BEGIN|AIza[0-9A-Za-z\-_]{15,}|sk-[0-9A-Za-z\-_]{15,}|GOCSPX-[0-9A-Za-z\-_]{10,}|"
    r"(?:password|passwd|secret|token|api_key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_\-]{6,})",
    re.IGNORECASE,
)


def _mask_secret_prefix(val: str) -> str:
    v = (val or "").strip()
    if len(v) >= 10:
        return f"{v[:4]}...{v[-4:]}"
    if len(v) >= 4:
        return f"{v[:2]}***"
    return "***" if v else ""


def _ensure_staging_store(runtime: Any) -> dict[str, dict[str, Any]]:
    store = getattr(runtime, "_staged_files", None)
    if not isinstance(store, dict):
        store = {}
        runtime._staged_files = store
    now = time.time()
    expired = [k for k, v in store.items() if float(v.get("expires_at") or 0.0) <= now]
    for k in expired:
        store.pop(k, None)
    while len(store) > MAX_STAGED_ITEMS:
        oldest = min(store.items(), key=lambda kv: float(kv[1].get("created_at") or 0.0))[0]
        store.pop(oldest, None)
    return store


def _ensure_gate_store(runtime: Any) -> dict[str, dict[str, Any]]:
    store = getattr(runtime, "_pending_settings_gates", None)
    if not isinstance(store, dict):
        store = {}
        runtime._pending_settings_gates = store
    now = time.time()
    expired = [k for k, v in store.items() if float(v.get("expires_at") or 0.0) <= now]
    for k in expired:
        store.pop(k, None)
    return store


def clear_ephemeral_settings_state(runtime: Any) -> None:
    """Wipes staged secret files and pending confirm gates on profile lock/switch."""
    for attr in ("_staged_files", "_pending_settings_gates"):
        d = getattr(runtime, attr, None)
        if isinstance(d, dict):
            d.clear()


def _parse_env_pairs(raw_text: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k_clean = k.strip()
        if k_clean.lower().startswith("export "):
            k_clean = k_clean[7:].strip()
        v_clean = v.strip().strip('"').strip("'")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k_clean):
            pairs[k_clean] = v_clean
    return pairs


def stage_settings_file(
    runtime: Any,
    *,
    filename: str,
    mime: str = "text/plain",
    content_text: str = "",
) -> dict[str, Any]:
    """
    Stages a config/secret file in RAM only, classifies it deterministically, and returns
    strictly sanitized metadata (`staging_id`, `detected_kind`, `summary`, `safe_fields`).
    """
    fname = (filename or "uploaded.txt").strip() or "uploaded.txt"
    raw = str(content_text or "")
    raw_bytes = raw.encode("utf-8", errors="replace")
    if not raw.strip():
        return {"ok": False, "error": f"{fname} is empty."}
    if len(raw_bytes) > MAX_STAGED_FILE_BYTES:
        return {"ok": False, "error": f"{fname} exceeds 512 KB staging limit."}

    detected_kind = "unknown_text"
    summary = f"{len(raw.splitlines())} line(s), {len(raw_bytes)} bytes"
    safe_fields: dict[str, Any] = {
        "line_count": len(raw.splitlines()),
        "byte_count": len(raw_bytes),
    }

    # 1. Google OAuth client_secret JSON check
    is_google_json = False
    try:
        cid, csec, ruris = parse_google_client_secret_json(raw)
        is_google_json = bool(cid)
        if is_google_json:
            import json

            parsed = json.loads(raw)
            client_type = "installed" if isinstance(parsed.get("installed"), dict) else (
                "web" if isinstance(parsed.get("web"), dict) else "raw"
            )
            block = parsed.get(client_type) if client_type in ("installed", "web") else parsed
            project_id = str((block or {}).get("project_id") or "")
            masked_cid = _mask_client_id(cid)
            detected_kind = "google_client_secret"
            summary = f"Google OAuth ({masked_cid})"
            safe_fields = {
                "masked_client_id": masked_cid,
                "project_id": project_id,
                "client_type": client_type,
                "has_client_secret": bool(csec),
                "redirect_uris": list(ruris)[:4],
            }
    except Exception:
        is_google_json = False

    # 2. .env / KEY=VALUE secrets check
    if not is_google_json:
        env_pairs = _parse_env_pairs(raw)
        if env_pairs:
            detected_kind = "env_secrets"
            recognized_provs = sorted(
                {
                    _RECOGNIZED_ENV_PROVIDERS[k]
                    for k in env_pairs
                    if k in _RECOGNIZED_ENV_PROVIDERS
                }
            )
            masked_previews = {k: _mask_secret_prefix(v) for k, v in list(env_pairs.items())[:25]}
            summary = f"{len(env_pairs)} env key(s)"
            if recognized_provs:
                summary += f" ({', '.join(recognized_provs)})"
            safe_fields = {
                "keys": list(env_pairs.keys())[:25],
                "masked_previews": masked_previews,
                "recognized_providers": recognized_provs,
            }
        else:
            has_sensitive = bool(_SENSITIVE_TOKEN_RE.search(raw))
            safe_fields["contains_sensitive_tokens"] = has_sensitive
            if has_sensitive:
                summary = "redacted secret text"

    staging_id = f"stg_{secrets.token_hex(4)}"
    now = time.time()
    profile_id = (
        runtime.passwords.active_profile_id
        if getattr(runtime, "passwords", None) and runtime.passwords.unlocked
        else None
    )
    store = _ensure_staging_store(runtime)
    store[staging_id] = {
        "staging_id": staging_id,
        "filename": fname,
        "mime": str(mime or "text/plain"),
        "detected_kind": detected_kind,
        "summary": summary,
        "safe_fields": safe_fields,
        "raw_text": raw,
        "profile_id": profile_id,
        "created_at": now,
        "expires_at": now + STAGED_FILE_TTL_SECS,
    }
    return {
        "ok": True,
        "staged": {
            "staging_id": staging_id,
            "filename": fname,
            "detected_kind": detected_kind,
            "summary": summary,
            "safe_fields": safe_fields,
        },
    }


def get_staged_file_entry(runtime: Any, staging_id: str, *, include_raw: bool = False) -> dict[str, Any] | None:
    store = _ensure_staging_store(runtime)
    item = store.get((staging_id or "").strip())
    if not item:
        return None
    out = {
        "staging_id": item["staging_id"],
        "filename": item["filename"],
        "detected_kind": item["detected_kind"],
        "summary": item["summary"],
        "safe_fields": dict(item.get("safe_fields") or {}),
    }
    if include_raw:
        out["raw_text"] = item.get("raw_text") or ""
    return out


def create_confirm_gate(
    runtime: Any,
    *,
    action_type: str,
    summary: str,
    params: dict[str, Any],
) -> str:
    token = f"cfg_{secrets.token_hex(8)}"
    now = time.time()
    store = _ensure_gate_store(runtime)
    store[token] = {
        "confirm_token": token,
        "action_type": action_type,
        "summary": summary,
        "params": dict(params),
        "created_at": now,
        "expires_at": now + GATE_TTL_SECS,
    }
    return token


def execute_confirm_gate(
    runtime: Any,
    *,
    confirm_token: str,
    action_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = _ensure_gate_store(runtime)
    tok = (confirm_token or "").strip()
    gate = store.pop(tok, None)
    if not gate:
        return {"ok": False, "error": "Confirmation token expired or already used."}

    act = str(gate.get("action_type") or "")
    params = dict(gate.get("params") or {})
    extra = dict(action_payload or {})

    if act == "google_disconnect":
        clear_cfg = bool(params.get("clear_client_config", False))
        st = runtime.google_auth.disconnect(clear_client_config=clear_cfg)
        return {
            "ok": True,
            "message": "Disconnected Google OAuth session tokens.",
            "refresh_hints": ["google_oauth", "mail"],
            "google_oauth": st,
        }

    if act == "import_staged_env":
        if not runtime.passwords.unlocked:
            return {"ok": False, "error": "Unlock an active profile before importing secrets into vault.enc."}
        staging_id = str(params.get("staging_id") or "")
        entry = get_staged_file_entry(runtime, staging_id, include_raw=True)
        if not entry or entry.get("detected_kind") != "env_secrets":
            return {"ok": False, "error": "Staged .env file expired or unavailable. Attach it again."}
        pairs = _parse_env_pairs(entry.get("raw_text") or "")
        selected_keys = params.get("keys") or list(pairs.keys())
        filtered_lines = [f"{k}={pairs[k]}" for k in selected_keys if k in pairs]
        if not filtered_lines:
            return {"ok": False, "error": "No valid KEY=VALUE pairs left to import."}
        runtime.passwords.save_raw_env("\n".join(filtered_lines))
        # Also refresh model discovery if API keys were imported
        for prov_key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MISTRAL_API_KEY"):
            if prov_key in pairs:
                prov_id = _RECOGNIZED_ENV_PROVIDERS.get(prov_key)
                if prov_id:
                    runtime.get_model_management_config(refresh_provider=prov_id)
        st_store = _ensure_staging_store(runtime)
        st_store.pop(staging_id, None)
        return {
            "ok": True,
            "message": f"Imported {len(filtered_lines)} key(s) into active profile vault.enc.",
            "refresh_hints": ["vault", "models", "providers"],
        }

    if act == "switch_or_unlock_profile":
        pid = str(params.get("profile_id") or "")
        if not pid:
            return {"ok": False, "error": "Missing profile_id."}
        use_keychain = bool(params.get("use_keychain", False))
        if use_keychain:
            with runtime._fast_http_unlock_context():
                res = runtime.passwords.unlock_with_keychain(pid)
                if getattr(runtime.passwords, "on_profile_change", None) is None:
                    runtime._refresh_active_profile_brain(defer_heavy=True)
            return {
                "ok": True,
                "message": f"Unlocked profile '{pid}' via keychain.",
                "refresh_hints": ["profile", "mail", "brain", "models", "google_oauth"],
                "profile": res,
            }
        pin = str(extra.get("pin") or "").strip()
        if not pin:
            return {"ok": False, "error": "Enter your 6-digit PIN to unlock this profile."}
        with runtime._fast_http_unlock_context():
            res = runtime.passwords.unlock_profile(pid, pin)
            if getattr(runtime.passwords, "on_profile_change", None) is None:
                runtime._refresh_active_profile_brain(defer_heavy=True)
        return {
            "ok": True,
            "message": f"Unlocked profile '{pid}'.",
            "refresh_hints": ["profile", "mail", "brain", "models", "google_oauth"],
            "profile": res,
        }

    if act == "remove_mail_account":
        aid = str(params.get("account_id") or "")
        res = runtime.mail.remove_account(aid)
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "Failed to remove mail account.")}
        return {
            "ok": True,
            "message": f"Removed mail account {aid}.",
            "refresh_hints": ["mail"],
        }

    if act == "delete_provider":
        prov_id = str(params.get("provider_id") or "")
        res = runtime.providers.delete_provider(prov_id, delete_credentials=bool(params.get("delete_credentials", False)))
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "Failed to remove provider.")}
        return {
            "ok": True,
            "message": f"Removed provider {prov_id}.",
            "refresh_hints": ["providers"],
        }

    if act == "delete_profile":
        pid = str(params.get("profile_id") or "")
        pin = str(extra.get("pin") or "").strip()
        if not pin:
            return {"ok": False, "error": "Enter the profile's 6-digit PIN inside the card to confirm deletion."}
        res = runtime.passwords.delete_profile(pid, pin)
        return {
            "ok": True,
            "message": f"Deleted profile {pid}.",
            "refresh_hints": ["profile"],
            "profile": res,
        }

    if act == "delete_news_feed":
        fid = str(params.get("feed_id") or "")
        lbl = str(params.get("label") or fid)
        res = runtime.news.add_or_toggle_feed({"action": "delete", "feed_id": fid})
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "Failed to remove feed.")}
        return {
            "ok": True,
            "message": f"Removed news feed {lbl}.",
            "refresh_hints": ["news_sources", "news_stories"],
        }

    if act == "delete_news_topic":
        tid = str(params.get("topic_id") or "")
        tname = str(params.get("name") or tid)
        res = runtime.news.manage_topic({"action": "delete", "topic_id": tid})
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "Failed to remove topic.")}
        return {
            "ok": True,
            "message": f"Removed tracked topic '{tname}'.",
            "refresh_hints": ["news_topics", "news_stories"],
        }

    return {"ok": False, "error": f"Unsupported gate action: {act}"}


def _find_inline_google_client_json_spans(raw_text: str) -> list[tuple[int, int, str]]:
    """Find balanced {...} JSON substrings containing a Google OAuth client_id + client_secret."""
    import json as _json

    spans: list[tuple[int, int, str]] = []
    n = len(raw_text or "")
    i = 0
    while i < n:
        if raw_text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        found_end = -1
        while j < n:
            ch = raw_text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        found_end = j + 1
                        break
            j += 1
        if found_end > i:
            blob = raw_text[i:found_end]
            try:
                parsed = _json.loads(blob)
                if isinstance(parsed, dict):
                    inner = (
                        parsed.get("installed")
                        if isinstance(parsed.get("installed"), dict)
                        else parsed.get("web")
                        if isinstance(parsed.get("web"), dict)
                        else parsed
                    )
                    if isinstance(inner, dict) and inner.get("client_id") and inner.get("client_secret"):
                        spans.append((i, found_end, blob))
                        i = found_end
                        continue
            except Exception:
                pass
        i += 1
    return spans


_INLINE_ENV_SECRET_LINE_RE = re.compile(
    r"^(?:\s*export\s+)?(GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|MISTRAL_API_KEY|BRAVE_API_KEY|EXA_API_KEY|TAVILY_API_KEY)\s*=\s*(.+?)\s*$",
    re.MULTILINE,
)


def redact_inline_secrets_text(raw_text: str) -> str:
    """Redact inline Google client_secret JSON blobs and known API_KEY= lines from text."""
    out = str(raw_text or "")
    if not out:
        return out
    for s, e, _blob in reversed(_find_inline_google_client_json_spans(out)):
        out = f"{out[:s]}[client_secret JSON redacted locally]{out[e:]}"
    out = _INLINE_ENV_SECRET_LINE_RE.sub(lambda m: f"{m.group(1)}=[redacted locally]", out)
    return out


def extract_and_stage_inline_secrets(
    runtime: Any,
    raw_text: str,
    staged_files: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Detect inline Google OAuth client_secret JSON or .env API key lines pasted directly
    into Settings Chat text, stage them into RAM via `stage_settings_file`, and return
    `(sanitized_text, updated_staged_files)`.
    """
    out = str(raw_text or "")
    out_staged = [dict(x) for x in (staged_files or []) if isinstance(x, dict)]
    existing_ids = {str(x.get("staging_id") or "") for x in out_staged}

    spans = _find_inline_google_client_json_spans(out)
    for s, e, blob in reversed(spans):
        staged_res = stage_settings_file(
            runtime,
            filename="client_secret_pasted.json",
            mime="application/json",
            content_text=blob,
        )
        repl = "[client_secret JSON redacted locally]"
        if staged_res.get("ok") and isinstance(staged_res.get("staged"), dict):
            sf = staged_res["staged"]
            sid = str(sf.get("staging_id") or "")
            if sid and sid not in existing_ids:
                existing_ids.add(sid)
                out_staged.append(sf)
            repl = f"[staged client_secret_pasted.json ({sf.get('summary') or sid})]"
        out = f"{out[:s]}{repl}{out[e:]}"

    env_matches = list(_INLINE_ENV_SECRET_LINE_RE.finditer(out))
    if env_matches:
        env_lines = [
            f"{m.group(1)}={m.group(2).strip().strip(chr(34)).strip(chr(39))}"
            for m in env_matches
        ]
        staged_res = stage_settings_file(
            runtime,
            filename="pasted.env",
            mime="text/plain",
            content_text="\n".join(env_lines),
        )
        tag = "[redacted locally]"
        if staged_res.get("ok") and isinstance(staged_res.get("staged"), dict):
            sf = staged_res["staged"]
            sid = str(sf.get("staging_id") or "")
            if sid and sid not in existing_ids:
                existing_ids.add(sid)
                out_staged.append(sf)
            tag = f"[staged pasted.env ({sf.get('summary') or sid})]"
        out = _INLINE_ENV_SECRET_LINE_RE.sub(lambda m: f"{m.group(1)}={tag}", out)

    return out, out_staged

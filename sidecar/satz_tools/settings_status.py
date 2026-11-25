"""Read-only Settings inspection tools (safe masked views only, zero raw secrets)."""
from __future__ import annotations

from typing import Any

from satz_tools.registry import satz_tool
from satz_tools.settings_staging import get_staged_file_entry


@satz_tool(
    name="settings_get_summary",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Read the current Satz browser Settings summary across profiles, models/API keys, "
        "Google OAuth status, Cloud Drives (Google Drive & OneDrive), Mail accounts, and Action Providers. "
        "Never returns raw secrets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "enum": ["all", "profiles", "models", "oauth", "drives", "mail", "providers"],
                "description": "Settings section to inspect (defaults to all).",
            }
        },
        "required": [],
    },
)
def settings_get_summary(runtime: Any, session: Any = None, section: str = "all") -> dict[str, Any]:
    sec = (section or "all").strip().lower()
    if sec not in {"all", "profiles", "models", "oauth", "drives", "mail", "providers"}:
        sec = "all"

    out: dict[str, Any] = {"ok": True, "section": sec}

    if sec in ("all", "profiles"):
        out["profiles"] = runtime.passwords.list_profiles()

    if sec in ("all", "models"):
        mcfg = runtime.get_model_management_config()
        safe_providers = [
            {
                "id": p.get("id"),
                "label": p.get("label"),
                "configured": bool(p.get("configured")),
                "key_source": p.get("key_source") or "none",
                "masked_key": p.get("masked_key") or "",
                "model_count": len(p.get("models") or []),
                "models": [m.get("id") for m in (p.get("models") or [])[:8]],
            }
            for p in (mcfg.get("cloud_providers") or [])
        ]
        out["models"] = {
            "roles": mcfg.get("roles") or {},
            "cloud_providers": safe_providers,
        }

    if sec in ("all", "oauth"):
        g_st = dict(runtime.google_auth.get_status() or {})
        g_scopes = [str(s) for s in (g_st.get("scopes") or [])]
        g_st["drive_scope_authorized"] = any("drive" in s.lower() for s in g_scopes)
        out["google_oauth"] = g_st

    if sec in ("all", "drives"):
        drives_mgr = getattr(runtime, "drives", None)
        if drives_mgr is not None:
            try:
                d_st = dict(drives_mgr.get_status() or {})
            except Exception as exc:
                d_st = {"unlocked": bool(getattr(runtime.passwords, "unlocked", False)), "error": str(exc)}
        else:
            d_st = {"unlocked": bool(getattr(runtime.passwords, "unlocked", False))}
        g_drv = dict(d_st.get("google") or {})
        od_drv = dict(d_st.get("onedrive") or {})
        out["drives"] = {
            "unlocked": bool(d_st.get("unlocked")),
            "google_configured": bool(g_drv.get("configured")),
            "google_drive_ready": bool(g_drv.get("connected")),
            "signed_in_gmail_only": bool(g_drv.get("signed_in_gmail_only")),
            "needs_drive_scope": bool(g_drv.get("signed_in_gmail_only") and not g_drv.get("connected")),
            "google_email": g_drv.get("email") or "",
            "onedrive_configured": bool(od_drv.get("configured")),
            "onedrive_signed_in": bool(od_drv.get("connected")),
            "onedrive_email": od_drv.get("email") or "",
            "total_files": int(d_st.get("total_files") or 0),
            "indexed_count": int(d_st.get("indexed_docs") or 0),
            "syncing": bool(d_st.get("syncing")),
            "pinned_tab_hint": "Look for 'Drives' in the left sidebar Pinned section.",
        }

    if sec in ("all", "mail"):
        ml = runtime.mail.list_accounts()
        out["mail"] = {
            "unlocked": bool(ml.get("unlocked")),
            "accounts": [
                {
                    "id": a.get("id"),
                    "label": a.get("label"),
                    "email": a.get("email"),
                    "protocol": a.get("protocol"),
                    "inbox_unread": a.get("inbox_unread", 0),
                }
                for a in (ml.get("accounts") or [])
            ],
        }

    if sec in ("all", "providers"):
        reg = runtime.providers.list_registry() if hasattr(runtime, "providers") else {}
        by_cat = reg.get("providers_by_category") or {}
        out["providers"] = {
            "unlocked": bool(reg.get("unlocked")),
            "categories": [
                {
                    "id": c.get("id"),
                    "label": c.get("label"),
                    "providers": [
                        {
                            "id": p.get("id"),
                            "display_name": p.get("display_name"),
                            "auth_ready": bool(p.get("auth_ready")),
                            "priority": p.get("priority"),
                        }
                        for p in (by_cat.get(c.get("id") or "", []) or [])
                    ],
                }
                for c in (reg.get("categories") or [])
            ],
        }

    return {"model_payload": out}


@satz_tool(
    name="settings_inspect_staged_file",
    domain="settings",
    mode="read",
    mcp_safe=True,
    description=(
        "Inspect a staged configuration file using its staging_id handle. "
        "Returns safe metadata (detected_kind, project_id, masked key prefixes) without exposing raw secrets."
    ),
    parameters={
        "type": "object",
        "properties": {
            "staging_id": {
                "type": "string",
                "description": "Handle of the staged file (e.g. stg_a1b2c3d4).",
            }
        },
        "required": ["staging_id"],
    },
)
def settings_inspect_staged_file(
    runtime: Any,
    session: Any = None,
    staging_id: str = "",
) -> dict[str, Any]:
    entry = get_staged_file_entry(runtime, staging_id, include_raw=False)
    if not entry:
        return {
            "model_payload": {
                "ok": False,
                "error": f"Staged file '{staging_id}' was not found or expired. Ask the user to attach or drop it again.",
            }
        }
    return {"model_payload": {"ok": True, "staged": entry}}

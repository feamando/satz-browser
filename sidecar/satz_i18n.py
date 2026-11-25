"""
App-wide UI Localization Manager (`satz_i18n.py`):
- Persists user language preference & custom translated UI packs app-wide under
  `<app_data_dir>/i18n/` (`config.json` + `<lang>.json`) so language applies across all profiles.
- Translates canonical UI keys using the user's selected default chat model
  (`roles.chat`, supporting both local `gemma-4-e4b` and cloud providers).
- Supports domain-priority batching, strict `{var}` placeholder verification + 1-shot retry,
  incremental `source_hash` diffing for silent background sync, `custom: true` override preservation,
  RTL direction detection, cancellation, and portable JSON export/import.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.parse
from typing import Any, Callable

from satz_translate import LANGUAGE_CATALOG, _LANG_ALIASES, _LANG_BY_CODE


_RTL_LANGS = {"ar", "he", "fa", "ur", "yi", "ps", "sd", "ckb"}

_DOMAIN_PRIORITY: list[str] = [
    "common",
    "time",
    "rail",
    "top",
    "status",
    "start",
    "profile",
    "settings",
    "prov",
    "mail",
    "chat",
    "news",
    "sources",
    "brain",
    "cmd",
    "privacy",
    "err",
    "main",
    "settings_card",
]
_DOMAIN_RANK = {dom: idx for idx, dom in enumerate(_DOMAIN_PRIORITY)}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]+",
    flags=re.UNICODE,
)
_NON_GENERATIVE_MODELS = {"planck3 (web)", "hertz (reader)", "planck (reader)"}

_PROVIDER_HOST_MAP = {
    "gemini": "generativelanguage.googleapis.com",
    "anthropic": "api.anthropic.com",
    "openai": "api.openai.com",
    "mistral": "api.mistral.ai",
}

_EXTRA_LANG_LABELS: dict[str, tuple[str, str]] = {
    "ur": ("Urdu", "اردو"),
    "yi": ("Yiddish", "ייִדיש"),
    "ps": ("Pashto", "پښتو"),
}


def compute_source_hash(entry: dict[str, Any]) -> str:
    """Compute stable hash over canonical English entry text/one so key edits invalidate only changed keys."""
    payload = json.dumps(
        {
            "text": str(entry.get("text") or ""),
            "one": str(entry.get("one") or ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def extract_placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(str(text or "")))


def _sanitize_ui_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-")
    cleaned = _EMOJI_RE.sub("", cleaned)
    return cleaned.strip()


def normalize_lang_spec(raw_lang: str) -> dict[str, str]:
    """
    Normalize a language name, alias, or BCP-47 tag into a safe local pack identifier,
    human label, and `ltr`/`rtl` writing direction.
    """
    raw = str(raw_lang or "").strip()
    if not raw:
        return {"lang": "en", "label": "English", "dir": "ltr"}

    low = raw.lower().strip()
    # Direct alias or catalog match (e.g. "German", "Deutsch", "fr", "pt-BR")
    base = re.split(r"[-_]", low)[0]
    mapped = _LANG_ALIASES.get(low) or _LANG_ALIASES.get(base)
    if mapped:
        if mapped == "en" and low in ("en", "eng", "english"):
            return {"lang": "en", "label": "English", "dir": "ltr"}
        if "-" in low or "_" in low:
            parts = [p for p in re.split(r"[-_]", low) if p]
            if len(parts) >= 2 and len(parts[0]) <= 3 and all(p.isalnum() for p in parts):
                norm_tag = f"{mapped}-{'-'.join(parts[1:])}"
                info = _LANG_BY_CODE.get(mapped)
                label = f"{info['native']} ({parts[1].upper()})" if info else raw
                direction = "rtl" if mapped in _RTL_LANGS else "ltr"
                return {"lang": norm_tag, "label": label, "dir": direction}
        info = _LANG_BY_CODE.get(mapped)
        label = str(info.get("native") or info.get("name") or raw) if info else raw
        direction = "rtl" if (mapped in _RTL_LANGS or bool(info and info.get("rtl"))) else "ltr"
        return {"lang": mapped, "label": label, "dir": direction}

    if low in _EXTRA_LANG_LABELS:
        _name, native = _EXTRA_LANG_LABELS[low]
        return {
            "lang": low,
            "label": native,
            "dir": "rtl" if low in _RTL_LANG_S_OR_CHECK(low) else "ltr",
        }

    # Custom/regional non-catalog tag or dialect label (e.g. "bavarian", "tlh", "es-419")
    slug = re.sub(r"[^a-z0-9-]+", "-", low).strip("-")
    if not slug:
        slug = "custom-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    if slug.startswith(("ar", "he", "fa", "ur", "yi", "ps", "sd", "ckb")):
        direction = "rtl"
    else:
        direction = "ltr"
    label = raw if any(ord(c) > 127 or c.isupper() for c in raw) else raw.title()
    return {"lang": slug[:32], "label": label, "dir": direction}


def _RTL_LANG_S_OR_CHECK(code: str) -> set[str]:
    return _RTL_LANGS


def parse_ts_catalog_file(ts_path: Path) -> dict[str, dict[str, str]]:
    """
    Extract canonical `EN_CATALOG` entries from `src/i18n/catalog.ts` without needing Node.
    """
    if not ts_path.exists():
        return {}
    raw = ts_path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, dict[str, str]] = {}
    # Each entry line has the shape: `"key": { text: "...", one: "...", hint: "..." },`
    line_re = re.compile(
        r'^\s*"([a-zA-Z0-9_.-]+)"\s*:\s*\{(.+)\}\s*,?\s*$',
        flags=re.MULTILINE,
    )
    field_re = re.compile(r'\b(text|one|hint)\s*:\s*"((?:\\.|[^"\\])*)"')
    for m in line_re.finditer(raw):
        key = m.group(1).strip()
        body = m.group(2)
        entry: dict[str, str] = {}
        for fm in field_re.finditer(body):
            fname = fm.group(1)
            fval_raw = fm.group(2)
            try:
                fval = json.loads(f'"{fval_raw}"')
            except Exception:
                fval = fval_raw.replace('\\"', '"').replace("\\\\", "\\")
            entry[fname] = fval
        if "text" in entry:
            out[key] = entry
    return out


def _extract_json_object(raw: str) -> dict[str, Any]:
    txt = str(raw or "").strip()
    if not txt:
        return {}
    # Strip fenced markdown code blocks if present
    txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s*```$", "", txt)
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    first = txt.find("{")
    last = txt.rfind("}")
    if first >= 0 and last > first:
        try:
            parsed = json.loads(txt[first : last + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


class SatzI18nManager:
    """App-wide UI localization store and LLM translation orchestrator."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        base_dir = Path(runtime.legacy_store_path).parent
        self.i18n_dir = base_dir / "i18n"
        self.i18n_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.i18n_dir / "config.json"
        self.manifest_cache_path = self.i18n_dir / "en_manifest.json"
        self._ts_catalog_path = Path(__file__).resolve().parent.parent / "src" / "i18n" / "catalog.ts"
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._job_state: dict[str, Any] = {
            "running": False,
            "lang": "",
            "label": "",
            "model": "",
            "completed": 0,
            "total": 0,
            "current_batch": 0,
            "total_batches": 0,
            "error": "",
            "updated_at": 0.0,
        }
        self._bg_thread: threading.Thread | None = None

    def _safe_bundle_path(self, lang: str) -> Path:
        spec = normalize_lang_spec(lang)
        slug = spec["lang"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", slug):
            slug = "custom-" + hashlib.sha256(lang.encode("utf-8")).hexdigest()[:8]
        return self.i18n_dir / f"{slug}.json"

    def _read_config_unlocked(self) -> dict[str, Any]:
        default_cfg = {
            "version": 1,
            "active_locale": "en",
            "active_label": "English",
            "active_dir": "ltr",
            "updated_at": int(time.time()),
        }
        if not self.config_path.exists():
            return default_cfg
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                spec = normalize_lang_spec(str(raw.get("active_locale") or "en"))
                return {
                    "version": 1,
                    "active_locale": spec["lang"],
                    "active_label": str(raw.get("active_label") or spec["label"]),
                    "active_dir": str(raw.get("active_dir") or spec["dir"]),
                    "updated_at": int(raw.get("updated_at") or time.time()),
                }
        except Exception:
            pass
        return default_cfg

    def _write_config_unlocked(self, cfg: dict[str, Any]) -> None:
        tmp = self.config_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.config_path)

    def _read_bundle_unlocked(self, lang: str) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        path = self._safe_bundle_path(spec["lang"])
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    entries = raw.get("entries")
                    return {
                        "version": 1,
                        "lang": spec["lang"],
                        "label": str(raw.get("label") or spec["label"]),
                        "dir": str(raw.get("dir") or spec["dir"]),
                        "model": str(raw.get("model") or ""),
                        "updated_at": int(raw.get("updated_at") or 0),
                        "entries": dict(entries) if isinstance(entries, dict) else {},
                    }
            except Exception:
                pass
        return {
            "version": 1,
            "lang": spec["lang"],
            "label": spec["label"],
            "dir": spec["dir"],
            "model": "",
            "updated_at": 0,
            "entries": {},
        }

    def _write_bundle_unlocked(self, bundle: dict[str, Any]) -> None:
        path = self._safe_bundle_path(str(bundle.get("lang") or "custom"))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def resolve_catalog(self, provided_catalog: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
        """
        Return the canonical English UI catalog from:
        1) explicitly supplied manifest (and update cached manifest if non-empty),
        2) `src/i18n/catalog.ts`, or
        3) cached `en_manifest.json`.
        """
        if isinstance(provided_catalog, dict) and len(provided_catalog) > 0:
            normalized: dict[str, dict[str, str]] = {}
            for k, v in provided_catalog.items():
                if not isinstance(v, dict) or "text" not in v:
                    continue
                item: dict[str, str] = {"text": str(v.get("text") or "")}
                if v.get("one") is not None:
                    item["one"] = str(v.get("one"))
                if v.get("hint") is not None:
                    item["hint"] = str(v.get("hint"))
                normalized[str(k)] = item
            if normalized:
                with self._lock:
                    try:
                        tmp = self.manifest_cache_path.with_suffix(".json.tmp")
                        tmp.write_text(json.dumps(normalized, ensure_ascii=False), encoding="utf-8")
                        os.replace(tmp, self.manifest_cache_path)
                    except Exception:
                        pass
                return normalized

        parsed = parse_ts_catalog_file(self._ts_catalog_path)
        if parsed:
            return parsed

        with self._lock:
            if self.manifest_cache_path.exists():
                try:
                    cached = json.loads(self.manifest_cache_path.read_text(encoding="utf-8"))
                    if isinstance(cached, dict):
                        return cached
                except Exception:
                    pass
        return {}

    def resolve_translation_model(self, model_override: str | None = None) -> dict[str, Any]:
        """Resolve which model translates UI strings (default: configured `roles.chat`)."""
        chosen = str(model_override or "").strip()
        if not chosen:
            try:
                cfg = self.runtime.get_model_management_config()
                chosen = str((cfg.get("roles") or {}).get("chat") or "gemma-4-e4b").strip()
            except Exception:
                chosen = "gemma-4-e4b"

        if chosen in _NON_GENERATIVE_MODELS:
            chosen = "gemma-4-e4b"

        parsed_cloud = self.runtime._parse_cloud_model_id(chosen)
        if parsed_cloud is None:
            return {
                "model_id": chosen,
                "local_only": True,
                "provider_id": "local",
                "host": "localhost",
                "disclosure": f"Local only ({chosen} on device; UI strings never leave your machine).",
            }

        prov_id, _slug = parsed_cloud
        host = _PROVIDER_HOST_MAP.get(prov_id, prov_id)
        return {
            "model_id": chosen,
            "local_only": False,
            "provider_id": prov_id,
            "host": host,
            "disclosure": (
                f"Uses default chat model {chosen} via {host} over HTTPS; "
                "sends only static UI strings and slot hints (never vault secrets, mail, or browsing data)."
            ),
        }

    def set_active_locale(self, lang: str, label: str | None = None) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        with self._lock:
            cfg = self._read_config_unlocked()
            cfg["active_locale"] = spec["lang"]
            if spec["lang"] == "en":
                cfg["active_label"] = "English"
                cfg["active_dir"] = "ltr"
            else:
                existing_bundle = self._read_bundle_unlocked(spec["lang"])
                cfg["active_label"] = str(label or existing_bundle.get("label") or spec["label"])
                cfg["active_dir"] = str(existing_bundle.get("dir") or spec["dir"])
            cfg["updated_at"] = int(time.time())
            self._write_config_unlocked(cfg)
            return dict(cfg)

    def get_bundle(self, lang: str) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        if spec["lang"] == "en":
            return {
                "ok": True,
                "lang": "en",
                "label": "English",
                "dir": "ltr",
                "model": "canonical",
                "updated_at": 0,
                "entries": {},
            }
        with self._lock:
            bundle = self._read_bundle_unlocked(spec["lang"])
            return {"ok": True, **bundle}

    def _compute_bundle_stats(
        self,
        bundle: dict[str, Any],
        catalog: dict[str, dict[str, str]],
    ) -> dict[str, int]:
        entries = bundle.get("entries") or {}
        total = len(catalog)
        if not total:
            translated = len(entries)
            custom_ct = sum(1 for v in entries.values() if isinstance(v, dict) and v.get("custom"))
            return {
                "total": translated,
                "translated": translated,
                "missing": 0,
                "stale": 0,
                "custom_count": custom_ct,
            }
        translated = 0
        missing = 0
        stale = 0
        custom_ct = 0
        for key, src_entry in catalog.items():
            cur = entries.get(key)
            if not isinstance(cur, dict) or not str(cur.get("text") or "").strip():
                missing += 1
                continue
            translated += 1
            if cur.get("custom"):
                custom_ct += 1
                continue
            expected_hash = compute_source_hash(src_entry)
            if cur.get("source_hash") != expected_hash:
                stale += 1
        return {
            "total": total,
            "translated": translated,
            "missing": missing,
            "stale": stale,
            "custom_count": custom_ct,
        }

    def get_status(
        self,
        lang: str | None = None,
        catalog: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cat = self.resolve_catalog(catalog)
        model_info = self.resolve_translation_model()
        with self._lock:
            cfg = self._read_config_unlocked()
            locales_out: list[dict[str, Any]] = [
                {
                    "lang": "en",
                    "label": "English",
                    "dir": "ltr",
                    "model": "canonical",
                    "total": len(cat),
                    "translated": len(cat),
                    "missing": 0,
                    "stale": 0,
                    "custom_count": 0,
                    "updated_at": 0,
                }
            ]
            seen_langs = {"en"}
            for path in sorted(self.i18n_dir.glob("*.json")):
                if path.name in ("config.json", "en_manifest.json"):
                    continue
                code = path.stem
                if code in seen_langs:
                    continue
                seen_langs.add(code)
                bundle = self._read_bundle_unlocked(code)
                stats = self._compute_bundle_stats(bundle, cat)
                locales_out.append(
                    {
                        "lang": bundle["lang"],
                        "label": bundle["label"],
                        "dir": bundle["dir"],
                        "model": bundle.get("model") or "",
                        "updated_at": bundle.get("updated_at") or 0,
                        **stats,
                    }
                )

            target_lang = normalize_lang_spec(lang)["lang"] if lang else cfg["active_locale"]
            if target_lang != "en" and target_lang not in seen_langs:
                spec = normalize_lang_spec(target_lang)
                locales_out.append(
                    {
                        "lang": spec["lang"],
                        "label": spec["label"],
                        "dir": spec["dir"],
                        "model": "",
                        "updated_at": 0,
                        "total": len(cat),
                        "translated": 0,
                        "missing": len(cat),
                        "stale": 0,
                        "custom_count": 0,
                    }
                )

            target_stats = next(
                (x for x in locales_out if x["lang"] == target_lang),
                locales_out[0],
            )
            return {
                "ok": True,
                "active_locale": cfg["active_locale"],
                "active_label": cfg["active_label"],
                "active_dir": cfg["active_dir"],
                "default_model": model_info["model_id"],
                "model_info": model_info,
                "target": target_stats,
                "locales": locales_out,
                "job": dict(self._job_state),
                "suggested_languages": LANGUAGE_CATALOG,
            }

    def cancel_translation(self, lang: str | None = None) -> dict[str, Any]:
        with self._lock:
            cancelled: list[str] = []
            if lang:
                slug = normalize_lang_spec(lang)["lang"]
                ev = self._cancel_events.get(slug)
                if ev:
                    ev.set()
                    cancelled.append(slug)
            else:
                for slug, ev in list(self._cancel_events.items()):
                    ev.set()
                    cancelled.append(slug)
            return {"ok": True, "cancelled": cancelled}

    def _keys_needing_translation(
        self,
        catalog: dict[str, dict[str, str]],
        bundle: dict[str, Any],
        *,
        only_missing: bool = True,
        force: bool = False,
    ) -> list[str]:
        existing = bundle.get("entries") or {}
        pending: list[str] = []
        for key, src_entry in catalog.items():
            cur = existing.get(key)
            is_custom = isinstance(cur, dict) and bool(cur.get("custom"))
            if is_custom and not force:
                continue
            cur_text = str(cur.get("text") or "").strip() if isinstance(cur, dict) else ""
            src_hash = compute_source_hash(src_entry)
            if force:
                pending.append(key)
            elif not cur_text:
                pending.append(key)
            elif only_missing:
                if not isinstance(cur, dict) or cur.get("source_hash") != src_hash:
                    pending.append(key)
            else:
                if not is_custom:
                    pending.append(key)

        def _sort_key(k: str) -> tuple[int, str]:
            prefix = k.split(".", 1)[0]
            return (_DOMAIN_RANK.get(prefix, 999), k)

        pending.sort(key=_sort_key)
        return pending

    def _validate_translated_entry(
        self,
        src_entry: dict[str, str],
        raw_val: Any,
    ) -> tuple[dict[str, str] | None, str]:
        if isinstance(raw_val, str):
            cand_text = raw_val
            cand_one = None
        elif isinstance(raw_val, dict):
            cand_text = str(raw_val.get("text") or "")
            cand_one = str(raw_val.get("one")) if raw_val.get("one") is not None else None
        else:
            return None, "expected object or string"

        cleaned_text = _sanitize_ui_text(cand_text)
        if not cleaned_text:
            return None, "empty translation"

        expected_vars = extract_placeholders(src_entry.get("text") or "")
        got_vars = extract_placeholders(cleaned_text)
        if expected_vars != got_vars:
            return (
                None,
                f"placeholder mismatch for text: expected {sorted(expected_vars)}, got {sorted(got_vars)}",
            )

        out: dict[str, str] = {"text": cleaned_text}
        if src_entry.get("one") is not None:
            if not cand_one:
                cand_one = cleaned_text
            cleaned_one = _sanitize_ui_text(cand_one)
            if not cleaned_one:
                return None, "empty singular form"
            expected_one_vars = extract_placeholders(src_entry.get("one") or "")
            got_one_vars = extract_placeholders(cleaned_one)
            if expected_one_vars != got_one_vars:
                return (
                    None,
                    f"placeholder mismatch for singular 'one': expected {sorted(expected_one_vars)}, got {sorted(got_one_vars)}",
                )
            out["one"] = cleaned_one
        return out, ""

    def _call_model_translate_batch(
        self,
        model_id: str,
        target_label: str,
        target_lang: str,
        batch_keys: list[str],
        catalog: dict[str, dict[str, str]],
        retry_notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload_items: dict[str, Any] = {}
        for k in batch_keys:
            src = catalog[k]
            item: dict[str, Any] = {"text": src["text"]}
            if src.get("one") is not None:
                item["one"] = src["one"]
            if src.get("hint"):
                item["hint"] = src["hint"]
            if retry_notes and k in retry_notes:
                item["fix_note"] = retry_notes[k]
            payload_items[k] = item

        sys_prompt = (
            "You are a UI localization translator for Satz Browser. "
            f"Translate all provided English UI strings accurately into {target_label} (locale code: {target_lang}).\n"
            "STRICT RULES:\n"
            "1. Return ONLY a single valid JSON object mapping each input key to "
            '{"text": "<translated>"} (or {"text": "<plural>", "one": "<singular>"} ONLY when the input includes "one").\n'
            "2. Preserve EVERY {placeholder} variable spelling verbatim (for example {count}, {name}, {mod}, {domain}, {error}). Never translate or remove {variables}.\n"
            "3. Keep translations concise and natural for the UI hint (button, tab, tooltip, placeholder).\n"
            "4. Never output em dashes (\\u2014), en dashes (\\u2013), or emojis; use ASCII '-' or '·' instead.\n"
            "5. Output raw JSON only, no commentary or markdown outside the JSON object."
        )
        user_prompt = (
            f"Target language: {target_label} ({target_lang})\n"
            "Translate the values below:\n"
            + json.dumps(payload_items, ensure_ascii=False, indent=2)
        )
        raw = self.runtime._complete_role_prompt(
            model_id,
            sys_prompt,
            user_prompt,
            temperature=0.1,
            max_tokens=2400,
        )
        return _extract_json_object(raw)

    def translate_sync(
        self,
        lang: str,
        *,
        catalog: dict[str, Any] | None = None,
        model: str | None = None,
        only_missing: bool = True,
        force: bool = False,
        activate: bool = True,
        batch_size: int = 25,
        on_batch_done: Callable[[dict[str, Any], int, int, int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        if spec["lang"] == "en":
            if activate:
                self.set_active_locale("en", "English")
            return {
                "ok": True,
                "lang": "en",
                "label": "English",
                "dir": "ltr",
                "model": "canonical",
                "translated_now": 0,
                "skipped_or_failed": 0,
                "total_needed": 0,
                "cancelled": False,
                "entries": {},
            }

        cat = self.resolve_catalog(catalog)
        model_info = self.resolve_translation_model(model)
        eff_model = model_info["model_id"]

        with self._lock:
            bundle = self._read_bundle_unlocked(spec["lang"])
            if not bundle.get("label"):
                bundle["label"] = spec["label"]
            bundle["dir"] = spec["dir"]
            if activate:
                cfg = self._read_config_unlocked()
                cfg["active_locale"] = spec["lang"]
                cfg["active_label"] = bundle["label"]
                cfg["active_dir"] = bundle["dir"]
                cfg["updated_at"] = int(time.time())
                self._write_config_unlocked(cfg)
            self._write_bundle_unlocked(bundle)

        keys_todo = self._keys_needing_translation(
            cat, bundle, only_missing=only_missing, force=force
        )
        if not keys_todo:
            with self._lock:
                self._job_state.update(
                    {
                        "running": False,
                        "lang": spec["lang"],
                        "label": bundle["label"],
                        "model": eff_model,
                        "completed": 0,
                        "total": 0,
                        "current_batch": 0,
                        "total_batches": 0,
                        "error": "",
                        "updated_at": time.time(),
                    }
                )
            return {
                "ok": True,
                "lang": spec["lang"],
                "label": bundle["label"],
                "dir": bundle["dir"],
                "model": eff_model,
                "translated_now": 0,
                "skipped_or_failed": 0,
                "total_needed": 0,
                "cancelled": False,
                "entries": bundle.get("entries") or {},
            }

        ev = cancel_event
        if ev is None:
            with self._lock:
                ev = threading.Event()
                self._cancel_events[spec["lang"]] = ev

        batches = [
            keys_todo[i : i + max(5, batch_size)]
            for i in range(0, len(keys_todo), max(5, batch_size))
        ]
        total_keys = len(keys_todo)
        total_batches = len(batches)
        translated_now = 0
        failed_keys = 0
        was_cancelled = False

        with self._lock:
            self._job_state.update(
                {
                    "running": True,
                    "lang": spec["lang"],
                    "label": bundle["label"],
                    "model": eff_model,
                    "completed": 0,
                    "total": total_keys,
                    "current_batch": 0,
                    "total_batches": total_batches,
                    "error": "",
                    "updated_at": time.time(),
                }
            )

        try:
            for b_idx, batch_keys in enumerate(batches, start=1):
                if ev.is_set():
                    was_cancelled = True
                    break

                raw_map = self._call_model_translate_batch(
                    eff_model,
                    str(bundle["label"]),
                    spec["lang"],
                    batch_keys,
                    cat,
                )
                delta_entries: dict[str, Any] = {}
                retry_keys: list[str] = []
                retry_reasons: dict[str, str] = {}
                now_ts = int(time.time())

                for k in batch_keys:
                    valid, err_reason = self._validate_translated_entry(cat[k], raw_map.get(k))
                    if valid:
                        delta_entries[k] = {
                            **valid,
                            "source_hash": compute_source_hash(cat[k]),
                            "model": eff_model,
                            "updated_at": now_ts,
                            "custom": False,
                        }
                    else:
                        retry_keys.append(k)
                        retry_reasons[k] = err_reason or "missing key in JSON output"

                # One targeted retry for missing or placeholder-mismatched keys
                if retry_keys and not ev.is_set():
                    retry_map = self._call_model_translate_batch(
                        eff_model,
                        str(bundle["label"]),
                        spec["lang"],
                        retry_keys,
                        cat,
                        retry_notes=retry_reasons,
                    )
                    for k in retry_keys:
                        valid, _err = self._validate_translated_entry(cat[k], retry_map.get(k))
                        if valid:
                            delta_entries[k] = {
                                **valid,
                                "source_hash": compute_source_hash(cat[k]),
                                "model": eff_model,
                                "updated_at": now_ts,
                                "custom": False,
                            }
                        else:
                            failed_keys += 1

                if delta_entries:
                    with self._lock:
                        cur_bundle = self._read_bundle_unlocked(spec["lang"])
                        existing = cur_bundle.setdefault("entries", {})
                        for k, new_ent in delta_entries.items():
                            prev = existing.get(k)
                            if isinstance(prev, dict) and prev.get("custom") and not force:
                                continue
                            existing[k] = new_ent
                        cur_bundle["model"] = eff_model
                        cur_bundle["dir"] = spec["dir"]
                        cur_bundle["updated_at"] = now_ts
                        self._write_bundle_unlocked(cur_bundle)
                        bundle = cur_bundle

                translated_now += len(delta_entries)
                with self._lock:
                    self._job_state.update(
                        {
                            "completed": translated_now,
                            "current_batch": b_idx,
                            "total_batches": total_batches,
                            "updated_at": time.time(),
                        }
                    )

                if on_batch_done is not None:
                    on_batch_done(delta_entries, b_idx, total_batches, translated_now, total_keys)

            with self._lock:
                self._job_state.update(
                    {
                        "running": False,
                        "completed": translated_now,
                        "updated_at": time.time(),
                    }
                )
                final_bundle = self._read_bundle_unlocked(spec["lang"])
            return {
                "ok": True,
                "lang": spec["lang"],
                "label": final_bundle["label"],
                "dir": final_bundle["dir"],
                "model": eff_model,
                "translated_now": translated_now,
                "skipped_or_failed": failed_keys,
                "total_needed": total_keys,
                "cancelled": was_cancelled,
                "entries": final_bundle.get("entries") or {},
            }
        except Exception as exc:
            with self._lock:
                self._job_state.update(
                    {
                        "running": False,
                        "error": str(exc),
                        "updated_at": time.time(),
                    }
                )
            return {
                "ok": False,
                "lang": spec["lang"],
                "label": bundle["label"],
                "dir": spec["dir"],
                "model": eff_model,
                "translated_now": translated_now,
                "skipped_or_failed": failed_keys,
                "total_needed": total_keys,
                "cancelled": was_cancelled,
                "error": str(exc),
                "entries": bundle.get("entries") or {},
            }

    def start_background_translation(
        self,
        lang: str,
        *,
        catalog: dict[str, Any] | None = None,
        model: str | None = None,
        only_missing: bool = True,
        force: bool = False,
        activate: bool = True,
    ) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        if spec["lang"] == "en":
            if activate:
                self.set_active_locale("en", "English")
            return {"ok": True, "started": False, "lang": "en", "already_running": False}

        resolved = self.resolve_translation_model(model)
        eff_model = resolved["model_id"]
        with self._lock:
            if (
                self._job_state.get("running")
                and self._job_state.get("lang") == spec["lang"]
                and self._job_state.get("model") == eff_model
                and self._bg_thread is not None
                and self._bg_thread.is_alive()
            ):
                return {
                    "ok": True,
                    "started": False,
                    "already_running": True,
                    "lang": spec["lang"],
                    "model": eff_model,
                }
            ev = threading.Event()
            self._cancel_events[spec["lang"]] = ev
            cat = self.resolve_catalog(catalog)
            self._job_state.update(
                {
                    "running": True,
                    "lang": spec["lang"],
                    "label": spec["label"],
                    "model": eff_model,
                    "completed": 0,
                    "total": 0,
                    "current_batch": 0,
                    "total_batches": 0,
                    "error": "",
                    "updated_at": time.time(),
                }
            )

            def _worker() -> None:
                from contextlib import nullcontext

                bg_fn = getattr(self.runtime, "background_cloud_scope", None)
                ctx = bg_fn() if callable(bg_fn) else nullcontext()
                try:
                    with ctx:
                        self.translate_sync(
                            spec["lang"],
                            catalog=cat,
                            model=eff_model,
                            only_missing=only_missing,
                            force=force,
                            activate=activate,
                            cancel_event=ev,
                        )
                except Exception as exc:
                    with self._lock:
                        self._job_state.update(
                            {"running": False, "error": str(exc), "updated_at": time.time()}
                        )

            th = threading.Thread(
                target=_worker,
                name=f"satz-i18n-{spec['lang']}",
                daemon=True,
            )
            self._bg_thread = th
            th.start()
            return {
                "ok": True,
                "started": True,
                "already_running": False,
                "lang": spec["lang"],
                "label": spec["label"],
                "dir": spec["dir"],
                "model": eff_model,
            }

    def override_entry(
        self,
        lang: str,
        key: str,
        text: str | None,
        one: str | None = None,
        *,
        reset: bool = False,
        catalog: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        if spec["lang"] == "en":
            return {"ok": False, "error": "English canonical entries cannot be overwritten."}
        key_s = str(key or "").strip()
        if not key_s:
            return {"ok": False, "error": "Missing key."}

        cat = self.resolve_catalog(catalog)
        src = cat.get(key_s)

        if reset:
            with self._lock:
                bundle = self._read_bundle_unlocked(spec["lang"])
                entries = bundle.setdefault("entries", {})
                removed = entries.pop(key_s, None)
                bundle["updated_at"] = int(time.time())
                self._write_bundle_unlocked(bundle)
            return {
                "ok": True,
                "lang": spec["lang"],
                "key": key_s,
                "reset": True,
                "had_entry": removed is not None,
            }

        cleaned = _sanitize_ui_text(str(text or ""))
        if not cleaned:
            return {"ok": False, "error": "Translated text cannot be empty."}
        if src:
            expected_vars = extract_placeholders(src.get("text") or "")
            got_vars = extract_placeholders(cleaned)
            if expected_vars != got_vars:
                return {
                    "ok": False,
                    "error": f"Placeholder mismatch: expected {sorted(expected_vars)}, got {sorted(got_vars)}",
                }
        entry_obj: dict[str, Any] = {
            "text": cleaned,
            "source_hash": compute_source_hash(src) if src else "",
            "model": "manual",
            "updated_at": int(time.time()),
            "custom": True,
        }
        if one is not None:
            cleaned_one = _sanitize_ui_text(one)
            if src and src.get("one") is not None:
                exp_one = extract_placeholders(src["one"])
                got_one = extract_placeholders(cleaned_one or cleaned)
                if exp_one != got_one:
                    return {
                        "ok": False,
                        "error": f"Singular placeholder mismatch: expected {sorted(exp_one)}, got {sorted(got_one)}",
                    }
            entry_obj["one"] = cleaned_one or cleaned

        with self._lock:
            bundle = self._read_bundle_unlocked(spec["lang"])
            entries = bundle.setdefault("entries", {})
            entries[key_s] = entry_obj
            bundle["updated_at"] = int(time.time())
            self._write_bundle_unlocked(bundle)
        return {"ok": True, "lang": spec["lang"], "key": key_s, "entry": entry_obj}

    def export_pack(self, lang: str) -> dict[str, Any]:
        spec = normalize_lang_spec(lang)
        if spec["lang"] == "en":
            cat = self.resolve_catalog()
            return {
                "ok": True,
                "pack": {
                    "version": 1,
                    "lang": "en",
                    "label": "English",
                    "dir": "ltr",
                    "model": "canonical",
                    "updated_at": int(time.time()),
                    "entries": {k: {"text": v["text"], **({"one": v["one"]} if "one" in v else {})} for k, v in cat.items()},
                },
            }
        with self._lock:
            bundle = self._read_bundle_unlocked(spec["lang"])
            return {"ok": True, "pack": bundle}

    def import_pack(self, pack: dict[str, Any], *, activate: bool = True) -> dict[str, Any]:
        if not isinstance(pack, dict):
            return {"ok": False, "error": "Expected JSON object pack."}
        raw_lang = str(pack.get("lang") or pack.get("locale") or "").strip()
        if not raw_lang:
            return {"ok": False, "error": "Missing 'lang' field in imported pack."}
        spec = normalize_lang_spec(raw_lang)
        if spec["lang"] == "en":
            return {"ok": False, "error": "Cannot overwrite canonical 'en' pack."}

        cat = self.resolve_catalog()
        raw_entries = pack.get("entries")
        if not isinstance(raw_entries, dict):
            return {"ok": False, "error": "Missing 'entries' object in imported pack."}

        accepted: dict[str, Any] = {}
        rejected: list[dict[str, str]] = []
        now_ts = int(time.time())
        for k, raw_v in raw_entries.items():
            key_s = str(k)
            src = cat.get(key_s)
            if src:
                valid, err = self._validate_translated_entry(src, raw_v)
                if not valid:
                    rejected.append({"key": key_s, "reason": err})
                    continue
                is_custom = bool(isinstance(raw_v, dict) and raw_v.get("custom"))
                src_hash = (
                    str(raw_v.get("source_hash") or compute_source_hash(src))
                    if isinstance(raw_v, dict)
                    else compute_source_hash(src)
                )
                model_tag = (
                    str(raw_v.get("model") or "imported")
                    if isinstance(raw_v, dict)
                    else "imported"
                )
                accepted[key_s] = {
                    **valid,
                    "source_hash": src_hash,
                    "model": model_tag,
                    "updated_at": now_ts,
                    "custom": is_custom,
                }
            elif isinstance(raw_v, dict) and str(raw_v.get("text") or "").strip():
                accepted[key_s] = {
                    "text": _sanitize_ui_text(str(raw_v["text"])),
                    **({"one": _sanitize_ui_text(str(raw_v["one"]))} if raw_v.get("one") is not None else {}),
                    "source_hash": str(raw_v.get("source_hash") or ""),
                    "model": str(raw_v.get("model") or "imported"),
                    "updated_at": now_ts,
                    "custom": bool(raw_v.get("custom")),
                }

        with self._lock:
            bundle = self._read_bundle_unlocked(spec["lang"])
            bundle["label"] = str(pack.get("label") or bundle.get("label") or spec["label"])
            bundle["dir"] = str(pack.get("dir") or spec["dir"])
            if bundle["dir"] not in ("ltr", "rtl"):
                bundle["dir"] = spec["dir"]
            bundle["model"] = str(pack.get("model") or bundle.get("model") or "imported")
            bundle["updated_at"] = now_ts
            merged = bundle.setdefault("entries", {})
            merged.update(accepted)
            self._write_bundle_unlocked(bundle)
            if activate:
                cfg = self._read_config_unlocked()
                cfg["active_locale"] = spec["lang"]
                cfg["active_label"] = bundle["label"]
                cfg["active_dir"] = bundle["dir"]
                cfg["updated_at"] = now_ts
                self._write_config_unlocked(cfg)

        return {
            "ok": True,
            "lang": spec["lang"],
            "label": bundle["label"],
            "dir": bundle["dir"],
            "imported": len(accepted),
            "rejected": rejected,
            "entries": bundle["entries"],
        }

    def format_oauth_callback_copy(self, ok: bool, headline: str, detail: str) -> dict[str, str]:
        """Provide localized UI chrome labels for the loopback Google OAuth HTML callback page."""
        with self._lock:
            cfg = self._read_config_unlocked()
            active = cfg.get("active_locale") or "en"
            lang_dir = cfg.get("active_dir") or "ltr"
            if active == "en":
                return {
                    "lang": "en",
                    "dir": "ltr",
                    "title": "Google Auth · Satz",
                    "badge": "Connected" if ok else "Authorization Failed",
                    "headline": headline,
                    "detail": detail,
                    "hint": "Tokens are saved inside your encrypted Satz profile vault. You can close this tab now (Ctrl+W / Cmd+W).",
                }
            bundle = self._read_bundle_unlocked(active)
            entries = bundle.get("entries") or {}

            def _lookup(key: str, default: str) -> str:
                ent = entries.get(key)
                if isinstance(ent, dict) and str(ent.get("text") or "").strip():
                    return str(ent["text"])
                return default

            return {
                "lang": active,
                "dir": lang_dir,
                "title": _lookup("oauth.cb_title", "Google Auth · Satz"),
                "badge": _lookup("oauth.cb_connected", "Connected") if ok else _lookup("oauth.cb_failed", "Authorization Failed"),
                "headline": headline,
                "detail": detail,
                "hint": _lookup(
                    "oauth.cb_hint",
                    "Tokens are saved inside your encrypted Satz profile vault. You can close this tab now (Ctrl+W / Cmd+W).",
                ),
            }

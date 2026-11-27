"""
Local model packaging, Hugging Face downloader, custom path manager,
and shipped Planck runtime discovery for Satz.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SIDE_ROOT = Path(__file__).resolve().parent
VENDOR_PLANCK_ROOT = SIDE_ROOT / "planck_vendor"
SHIPPED_PLANCK_DIR = SIDE_ROOT / "models" / "planck"
SHIPPED_PLANCK_READER = SHIPPED_PLANCK_DIR / "xreader_planck" / "manifest.json"
SHIPPED_PLANCK_ENCODER = SHIPPED_PLANCK_DIR / "planck13" / "manifest.json"
SHIPPED_PLANCK_TOKENIZER = SHIPPED_PLANCK_DIR / "tokenizer.model"

HF_CURATED_CATALOG: list[dict[str, Any]] = [
    {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "label": "Qwen 2.5 1.5B Instruct",
        "approx_size": "~3.1 GB",
        "gated": False,
        "notes": "Fast, ungated local chat & tool-use starter model for Mac Apple Silicon / CPU.",
    },
    {
        "repo_id": "Qwen/Qwen2.5-3B-Instruct",
        "label": "Qwen 2.5 3B Instruct",
        "approx_size": "~6.2 GB",
        "gated": False,
        "notes": "Balanced quality/speed local model with strong structured instruction following.",
    },
    {
        "repo_id": "Qwen/Qwen3-4B",
        "label": "Qwen 3 4B",
        "approx_size": "~8.0 GB",
        "gated": False,
        "notes": "Strong local reasoning & multilingual chat without gated license.",
    },
    {
        "repo_id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "label": "SmolLM2 1.7B Instruct",
        "approx_size": "~3.4 GB",
        "gated": False,
        "notes": "Compact Apache-2.0 chat model for low-RAM laptops.",
    },
    {
        "repo_id": "google/gemma-3-4b-it",
        "label": "Gemma 3 4B IT",
        "approx_size": "~8.0 GB",
        "gated": True,
        "notes": "Google Gemma 3 (requires accepting license on huggingface.co + HF token).",
    },
    {
        "repo_id": "google/gemma-4-E4B-it",
        "label": "Gemma 4 E4B IT",
        "approx_size": "~15.3 GB",
        "gated": True,
        "notes": "Reference local multimodal Satz model (requires HF token + 16 GB+ GPU/unified RAM).",
    },
]

_HF_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_SKIP_EXTS = (".msgpack", ".h5", ".ot", ".onnx", ".tflite", ".pb")
_SKIP_PREFIXES = ("original/", "flax_model", "tf_model", "rust_model", ".git/")
_WEIGHT_EXTS = (".safetensors", ".bin", ".pt", ".pth", ".npz")
_HF_ALLOWED_HOST = "huggingface.co"


def _mask_secret(tok: str) -> str:
    t = (tok or "").strip()
    if not t:
        return ""
    if len(t) >= 10:
        return f"{t[:5]}...{t[-4:]}"
    return "***"


def _dir_size_bytes(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _is_hf_llm_dir_valid(path: Path) -> tuple[bool, str]:
    if path.is_file():
        path = path.parent
    if not path.is_dir():
        return False, f"Directory does not exist: {path}"
    if not (path / "config.json").is_file():
        return False, f"Missing config.json in model folder: {path}"
    has_weights = any(
        (
            f.is_file()
            and (
                f.name.endswith(_WEIGHT_EXTS)
                or f.name in ("model.safetensors.index.json", "pytorch_model.bin.index.json")
            )
        )
        for f in path.iterdir()
    )
    if not has_weights:
        return False, f"No model weight files (.safetensors / .bin / .pt) found in {path}"
    return True, ""


def _resolve_checkpoint_target(raw_path: str | Path) -> Path | None:
    p = Path(str(raw_path or "").strip()).expanduser()
    if not str(p):
        return None
    if p.is_file():
        return p
    if p.is_dir():
        for cand_name in ("manifest.json", "reader.pt", "best.pt", "final.pt", "model.pt"):
            cand = p / cand_name
            if cand.is_file():
                return cand
        for pt in sorted(p.glob("*.pt")):
            if pt.is_file():
                return pt
        return None
    if Path(f"{p}.part000").is_file():
        return p
    return None


def _pick_hf_repo_files(siblings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = [str(s.get("rfilename") or s.get("path") or "") for s in siblings]
    has_safetensors = any(n.endswith(".safetensors") and "/" not in n for n in names) or any(
        n.endswith(".safetensors") and not n.startswith(_SKIP_PREFIXES) for n in names
    )
    chosen: list[dict[str, Any]] = []
    for s in siblings:
        fn = str(s.get("rfilename") or s.get("path") or "").strip()
        if not fn or fn.startswith("."):
            if fn != ".gitattributes":
                continue
            continue
        low = fn.lower()
        if low.startswith(_SKIP_PREFIXES) or low.endswith(_SKIP_EXTS):
            continue
        if has_safetensors and low.endswith(".bin") and "pytorch_model" in low:
            continue
        if low in ("readme.md", "license", "license.txt", "notice"):
            continue
        sz = s.get("size")
        if sz is None and isinstance(s.get("lfs"), dict):
            sz = s["lfs"].get("size")
        chosen.append({"path": fn, "size": int(sz or 0)})
    return chosen


def open_native_file_dialog(mode: str = "directory", title: str = "Select model") -> tuple[str, bool, str]:
    """Opens a native OS folder/file chooser cleanly on Windows, macOS, and Linux."""
    norm_mode = (mode or "directory").strip().lower()
    safe_title = re.sub(r'["`$\\]', "", title or "Select model")[:80]

    if sys.platform == "darwin":
        if norm_mode == "directory":
            script = f'POSIX path of (choose folder with prompt "{safe_title}")'
        else:
            script = f'POSIX path of (choose file with prompt "{safe_title}")'
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            if "-128" in err or "User canceled" in err or "cancelled" in err.lower():
                return "", True, ""
            return "", False, err or "macOS file picker failed"
        return (proc.stdout or "").strip(), False, ""

    if sys.platform == "win32":
        if norm_mode == "directory":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$d.Description = '{safe_title}'; "
                "$d.ShowNewFolderButton = $true; "
                "$res = $d.ShowDialog(); "
                "if ($res -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }"
            )
        else:
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                f"$d.Title = '{safe_title}'; "
                "$d.Filter = 'Model files (*.pt;manifest.json;*.safetensors;config.json)|*.pt;*.json;*.safetensors|All files (*.*)|*.*'; "
                "$res = $d.ShowDialog(); "
                "if ($res -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.FileName }"
            )
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=flags,
        )
        if proc.returncode != 0:
            return "", False, (proc.stderr or "").strip() or "Windows file picker failed"
        selected = (proc.stdout or "").strip()
        if not selected:
            return "", True, ""
        return selected, False, ""

    # Linux fallback
    for tool in ("zenity", "kdialog"):
        if shutil.which(tool):
            if tool == "zenity":
                args = ["zenity", "--file-selection", f"--title={safe_title}"]
                if norm_mode == "directory":
                    args.append("--directory")
            else:
                args = ["kdialog", "--title", safe_title]
                args.append("--getexistingdirectory" if norm_mode == "directory" else "--getopenfilename")
            proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0:
                return "", True, ""
            return (proc.stdout or "").strip(), False, ""
    return "", False, "No native file picker utility found on this system; paste the path directly."


class LocalModelManager:
    """Manages local model paths, shipped Planck discovery, and HF downloads."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.lock = threading.RLock()
        self.app_data_dir = runtime.legacy_store_path.parent
        self.models_dir = self.app_data_dir / "models"
        self.config_path = self.app_data_dir / "local_models.json"
        self._session_hf_token: str = ""
        self._downloads: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._data: dict[str, Any] = self._load_config()

    def _default_data(self) -> dict[str, Any]:
        return {
            "version": 1,
            "custom_llms": [],
            "overrides": {
                "chat_llm_path": "",
                "hertz_reader_path": "",
                "planck_reader_path": "",
                "planck13_encoder_path": "",
                "planck_tokenizer_path": "",
            },
        }

    def _load_config(self) -> dict[str, Any]:
        base = self._default_data()
        if self.config_path.is_file():
            try:
                parsed = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("custom_llms"), list):
                        base["custom_llms"] = [
                            dict(x) for x in parsed["custom_llms"] if isinstance(x, dict) and x.get("path")
                        ]
                    if isinstance(parsed.get("overrides"), dict):
                        for k in base["overrides"]:
                            val = str(parsed["overrides"].get(k) or "").strip()
                            if val:
                                base["overrides"][k] = val
            except Exception:
                pass
        return base

    def _save_config(self) -> None:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.config_path)

    def resolve_hf_token(self, explicit_token: str = "") -> str:
        if (explicit_token or "").strip():
            return explicit_token.strip()
        if self._session_hf_token:
            return self._session_hf_token
        if getattr(self.runtime, "passwords", None) is not None and self.runtime.passwords.unlocked:
            env_map = self.runtime.passwords.get_unlocked_credentials_map()
            for env_name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
                val = str(env_map.get(env_name) or "").strip()
                if val:
                    return val
        if hasattr(self.runtime, "store") and self.runtime.store is not None:
            try:
                with self.runtime.store_lock:
                    row = self.runtime.store.db.execute(
                        "SELECT value FROM satz_meta WHERE key = 'hf_access_token'"
                    ).fetchone()
                    if row and row["value"]:
                        return str(row["value"]).strip()
            except Exception:
                pass
        for env_name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
            val = str(os.environ.get(env_name) or "").strip()
            if val:
                return val
        return ""

    def save_hf_token(self, token: str = "", clear: bool = False) -> dict[str, Any]:
        clean = (token or "").strip()
        with self.lock:
            if clear:
                self._session_hf_token = ""
                if getattr(self.runtime, "passwords", None) is not None and self.runtime.passwords.unlocked:
                    cur = self.runtime.passwords.get_unlocked_credentials_map()
                    for k in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
                        cur.pop(k, None)
                    self.runtime.passwords._unlocked_env_cache = cur
                    self.runtime.passwords._persist_active_vault(cur)
                with self.runtime.store_lock:
                    self.runtime.store.db.execute(
                        "DELETE FROM satz_meta WHERE key = 'hf_access_token'"
                    )
                    self.runtime.store.db.commit()
                return {"ok": True, "hf_token_configured": False, "hf_token_masked": ""}

            if not clean:
                return {"ok": False, "error": "Enter a Hugging Face token first."}
            self._session_hf_token = clean
            if getattr(self.runtime, "passwords", None) is not None and self.runtime.passwords.unlocked:
                self.runtime.passwords.save_raw_env(f"HF_TOKEN={clean}")
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    "INSERT OR REPLACE INTO satz_meta (key, value) VALUES (?, ?)",
                    ("hf_access_token", clean),
                )
                self.runtime.store.db.commit()
            return {
                "ok": True,
                "hf_token_configured": True,
                "hf_token_masked": _mask_secret(clean),
            }

    def list_custom_llms(self) -> list[dict[str, Any]]:
        with self.lock:
            out: list[dict[str, Any]] = []
            for entry in self._data.get("custom_llms") or []:
                p = Path(str(entry.get("path") or ""))
                ok, err = _is_hf_llm_dir_valid(p)
                out.append(
                    {
                        "id": str(entry.get("id") or ""),
                        "label": str(entry.get("label") or p.name),
                        "repo_id": str(entry.get("repo_id") or ""),
                        "path": str(p),
                        "source": str(entry.get("source") or "local_path"),
                        "ready": ok,
                        "error": err,
                        "size_bytes": int(entry.get("size_bytes") or (_dir_size_bytes(p) if p.exists() else 0)),
                        "added_at": float(entry.get("added_at") or 0.0),
                    }
                )
            return out

    def get_custom_llm_by_id(self, model_id: str) -> dict[str, Any] | None:
        mid = (model_id or "").strip()
        if not mid:
            return None
        for entry in self.list_custom_llms():
            if entry["id"] == mid:
                return entry
        return None

    def resolve_chat_llm_dir(self, model_id: str | None = None) -> Path:
        mid = (model_id or "").strip()
        if mid and mid != "gemma-4-e4b":
            if mid in ("planck3 (web)", "planck (reader)", "hertz (reader)", "template", "heuristic"):
                return self.models_dir / "__non_llm__"
            custom = self.get_custom_llm_by_id(mid)
            if custom and custom["path"]:
                return Path(custom["path"])
            cand_p = Path(mid).expanduser()
            if (os.sep in mid or "/" in mid or cand_p.is_absolute()) and cand_p.is_dir():
                return cand_p
            return self.models_dir / "__missing_custom_llm__"

        with self.lock:
            ov = str((self._data.get("overrides") or {}).get("chat_llm_path") or "").strip()
            if ov:
                p_ov = Path(ov).expanduser()
                if p_ov.exists():
                    return p_ov

        # Managed HF Gemma 4 E4B directory inside app data
        for slug in ("google--gemma-4-E4B-it", "google--gemma-4-e4b-it", "gemma-4-e4b-it"):
            cand = self.models_dir / slug
            if _is_hf_llm_dir_valid(cand)[0]:
                return cand

        # Registered Gemma 4 E4B custom entry
        for entry in self.list_custom_llms():
            if (
                entry["ready"]
                and (
                    "gemma-4-e4b" in entry["id"].lower()
                    or "gemma-4-e4b" in entry["repo_id"].lower()
                    or "gemma-4-e4b" in Path(entry["path"]).name.lower()
                )
            ):
                return Path(entry["path"])

        raw_rel = str(getattr(self.runtime, "gemma_rel_path", "models/gemma-4-e4b-it") or "models/gemma-4-e4b-it")
        p = Path(raw_rel).expanduser()
        if p.is_absolute():
            return p
        side_cand = SIDE_ROOT / p
        if side_cand.exists():
            return side_cand
        return self.runtime.sgs_root / p

    def has_ready_local_llm(self, model_id: str | None = None) -> bool:
        target = self.resolve_chat_llm_dir(model_id)
        if _is_hf_llm_dir_valid(target)[0]:
            return True
        if not model_id or model_id == "gemma-4-e4b":
            return False
        return False

    def first_ready_local_llm_id(self) -> str | None:
        if _is_hf_llm_dir_valid(self.resolve_chat_llm_dir("gemma-4-e4b"))[0]:
            return "gemma-4-e4b"
        for entry in self.list_custom_llms():
            if entry["ready"]:
                return entry["id"]
        return None

    def resolve_hertz_reader_ckpt(self) -> Path | None:
        with self.lock:
            ov = str((self._data.get("overrides") or {}).get("hertz_reader_path") or "").strip()
            if ov:
                t = _resolve_checkpoint_target(ov)
                if t is not None:
                    return t
        for rel in (
            "checkpoints/xreader_hertz_rc/reader.pt",
            "checkpoints/xreader_hertz/reader.pt",
            "checkpoints/xreader_hertz_r7/reader.pt",
        ):
            cand = self.runtime.sgs_root / rel
            if cand.exists():
                return cand
        return None

    def resolve_planck_reader_ckpt(self) -> tuple[Path | None, str]:
        with self.lock:
            ov = str((self._data.get("overrides") or {}).get("planck_reader_path") or "").strip()
            if ov:
                t = _resolve_checkpoint_target(ov)
                if t is not None:
                    return t, "custom"
        for rel in (
            "checkpoints/xreader_planck_rc/reader.pt",
            "checkpoints/xreader_planck_p15rc/reader.pt",
            "checkpoints/xreader_planck/reader.pt",
            "checkpoints/xreader_planck_r7/reader.pt",
        ):
            cand = self.runtime.sgs_root / rel
            if cand.exists():
                return cand, "local_sgs"
        if SHIPPED_PLANCK_READER.is_file():
            return SHIPPED_PLANCK_READER, "shipped"
        return None, "missing"

    def resolve_planck13_encoder(self) -> tuple[Path | None, Path | None, str]:
        with self.lock:
            ov_ckpt = str((self._data.get("overrides") or {}).get("planck13_encoder_path") or "").strip()
            ov_tok = str((self._data.get("overrides") or {}).get("planck_tokenizer_path") or "").strip()
        tok_override = Path(ov_tok).expanduser() if ov_tok else None
        if ov_ckpt:
            t = _resolve_checkpoint_target(ov_ckpt)
            if t is not None:
                tok = (
                    tok_override
                    if (tok_override and tok_override.is_file())
                    else (t.parent / "tokenizer.model" if (t.parent / "tokenizer.model").is_file() else None)
                )
                if tok is None:
                    sgs_tok = self.runtime.sgs_root / "data" / "wikipedia" / "tokenizer.model"
                    tok = sgs_tok if sgs_tok.is_file() else (SHIPPED_PLANCK_TOKENIZER if SHIPPED_PLANCK_TOKENIZER.is_file() else None)
                return t, tok, "custom"

        sgs_ckpt = self.runtime.sgs_root / "checkpoints" / "planck13" / "best.pt"
        sgs_tok = self.runtime.sgs_root / "data" / "wikipedia" / "tokenizer.model"
        if sgs_ckpt.is_file() and sgs_tok.is_file():
            return sgs_ckpt, sgs_tok, "local_sgs"

        if SHIPPED_PLANCK_ENCODER.is_file() and SHIPPED_PLANCK_TOKENIZER.is_file():
            return SHIPPED_PLANCK_ENCODER, SHIPPED_PLANCK_TOKENIZER, "shipped"

        return None, None, "missing"

    def point_local_model(
        self,
        *,
        role_slot: str,
        raw_path: str,
        label: str = "",
        set_active: bool = False,
    ) -> dict[str, Any]:
        slot = (role_slot or "chat_llm").strip().lower()
        clean_raw = (raw_path or "").strip()
        if not clean_raw:
            return {"ok": False, "error": "Provide a local model path."}
        p = Path(clean_raw).expanduser().resolve()

        if slot in ("chat_llm", "gemma_override", "local_llm"):
            if p.is_file():
                p = p.parent
            ok, err = _is_hf_llm_dir_valid(p)
            if not ok:
                return {"ok": False, "error": err}
            with self.lock:
                if slot == "gemma_override":
                    self._data["overrides"]["chat_llm_path"] = str(p)
                    model_id = "gemma-4-e4b"
                else:
                    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", p.name).strip("-") or "custom-llm"
                    model_id = f"local:{slug}"
                    existing = [e for e in self._data["custom_llms"] if e.get("path") == str(p) or e.get("id") == model_id]
                    if existing and existing[0].get("path") != str(p):
                        model_id = f"{model_id}-{abs(hash(str(p))) % 10000}"
                    self._data["custom_llms"] = [
                        e for e in self._data["custom_llms"] if e.get("id") != model_id and e.get("path") != str(p)
                    ]
                    self._data["custom_llms"].append(
                        {
                            "id": model_id,
                            "label": (label or "").strip() or p.name,
                            "repo_id": "",
                            "path": str(p),
                            "source": "local_path",
                            "size_bytes": _dir_size_bytes(p),
                            "added_at": time.time(),
                        }
                    )
                self._save_config()

            if set_active:
                self.runtime.update_model_management_config(
                    {
                        "role_chat": model_id,
                        "role_news_planner": model_id,
                        "role_news_capture": model_id,
                        "role_news_analyzer": model_id,
                    }
                )
            elif slot == "gemma_override":
                self.runtime.gemma_model = None
                self.runtime.gemma_tok = None
                self.runtime.gemma_processor = None
                self.runtime._loaded_local_llm_dir = None

            return {
                "ok": True,
                "model_id": model_id,
                "path": str(p),
                "message": f"Linked local model '{model_id}' at {p}",
            }

        if slot in ("reader_hertz", "reader_planck", "brain_encoder"):
            target = _resolve_checkpoint_target(p)
            if target is None:
                return {
                    "ok": False,
                    "error": f"No readable checkpoint (.pt or manifest.json) found at {p}",
                }
            ov_key = (
                "hertz_reader_path"
                if slot == "reader_hertz"
                else "planck_reader_path"
                if slot == "reader_planck"
                else "planck13_encoder_path"
            )
            with self.lock:
                self._data["overrides"][ov_key] = str(target)
                self._save_config()

            # Reset cached readers/encoder so the newly pointed checkpoint takes effect immediately
            with self.runtime.model_lock:
                if slot == "reader_hertz":
                    self.runtime.readers.pop("hertz (reader)", None)
                    self.runtime.answerer = None
                elif slot == "reader_planck":
                    self.runtime.readers.pop("planck (reader)", None)
                    self.runtime.answerer = None
                elif slot == "brain_encoder" and getattr(self.runtime, "brain", None) is not None:
                    self.runtime.brain._encoder = None
                    self.runtime.brain._encoder_ready = False

            return {
                "ok": True,
                "slot": slot,
                "path": str(target),
                "message": f"Linked {slot} checkpoint: {target}",
            }

        return {"ok": False, "error": f"Unknown local model slot: {role_slot}"}

    def remove_local_model(
        self,
        *,
        model_id: str = "",
        role_slot: str = "",
        delete_files: bool = False,
    ) -> dict[str, Any]:
        mid = (model_id or "").strip()
        slot = (role_slot or "").strip().lower()
        removed_path = ""
        with self.lock:
            if slot:
                ov_map = {
                    "chat_llm": "chat_llm_path",
                    "gemma_override": "chat_llm_path",
                    "reader_hertz": "hertz_reader_path",
                    "reader_planck": "planck_reader_path",
                    "brain_encoder": "planck13_encoder_path",
                    "planck_tokenizer": "planck_tokenizer_path",
                }
                ov_key = ov_map.get(slot)
                if not ov_key:
                    return {"ok": False, "error": f"Unknown slot: {role_slot}"}
                self._data["overrides"][ov_key] = ""
                self._save_config()
                with self.runtime.model_lock:
                    if slot in ("chat_llm", "gemma_override"):
                        self.runtime.gemma_model = None
                        self.runtime.gemma_tok = None
                        self.runtime.gemma_processor = None
                        self.runtime._loaded_local_llm_dir = None
                    elif slot == "reader_hertz":
                        self.runtime.readers.pop("hertz (reader)", None)
                        self.runtime.answerer = None
                    elif slot == "reader_planck":
                        self.runtime.readers.pop("planck (reader)", None)
                        self.runtime.answerer = None
                    elif slot == "brain_encoder" and getattr(self.runtime, "brain", None) is not None:
                        self.runtime.brain._encoder = None
                return {"ok": True, "message": f"Reset {slot} to default."}

            if not mid:
                return {"ok": False, "error": "Provide model_id or role_slot."}
            kept: list[dict[str, Any]] = []
            for entry in self._data.get("custom_llms") or []:
                if entry.get("id") == mid or entry.get("repo_id") == mid:
                    removed_path = str(entry.get("path") or "")
                    continue
                kept.append(entry)
            if not removed_path:
                return {"ok": False, "error": f"Local model not found: {mid}"}
            self._data["custom_llms"] = kept
            self._save_config()

        if delete_files and removed_path:
            try:
                rp = Path(removed_path).resolve()
                managed_root = self.models_dir.resolve()
                if managed_root in rp.parents and rp.exists():
                    shutil.rmtree(rp, ignore_errors=True)
            except Exception:
                pass

        # Unload if this model is currently resident in memory, and reset roles pointing at it back to default
        loaded_dir = getattr(self.runtime, "_loaded_local_llm_dir", None)
        if loaded_dir and removed_path and str(loaded_dir) == removed_path:
            with self.runtime.model_lock:
                self.runtime.gemma_model = None
                self.runtime.gemma_tok = None
                self.runtime.gemma_processor = None
                self.runtime._loaded_local_llm_dir = None
        with self.runtime.store_lock:
            self.runtime.store.db.execute(
                "DELETE FROM satz_meta WHERE key LIKE 'model_role_%' AND value = ?",
                (mid,),
            )
            self.runtime.store.db.commit()

        return {"ok": True, "removed": mid, "message": f"Removed local model {mid}."}

    def search_hf_models(self, query: str, token: str = "", limit: int = 8) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {"ok": True, "results": list(HF_CURATED_CATALOG)}
        tok = self.resolve_hf_token(token)
        params = urllib.parse.urlencode(
            {
                "search": q,
                "filter": "transformers",
                "sort": "downloads",
                "direction": "-1",
                "limit": str(max(1, min(20, int(limit)))),
            }
        )
        url = f"https://huggingface.co/api/models?{params}"
        headers = {"Accept": "application/json", "User-Agent": "satz-browser/0.5"}
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            return {"ok": False, "error": f"Hugging Face search failed: {exc}", "results": []}

        results: list[dict[str, Any]] = []
        for item in raw if isinstance(raw, list) else []:
            rid = str(item.get("id") or item.get("modelId") or "").strip()
            if not rid or "/" not in rid:
                continue
            ptag = str(item.get("pipeline_tag") or "").lower()
            if ptag and ptag not in ("text-generation", "image-text-to-text", "text2text-generation"):
                continue
            results.append(
                {
                    "repo_id": rid,
                    "label": rid.split("/", 1)[-1],
                    "downloads": int(item.get("downloads") or 0),
                    "likes": int(item.get("likes") or 0),
                    "gated": bool(item.get("gated")),
                    "private": bool(item.get("private")),
                    "pipeline_tag": ptag or "text-generation",
                }
            )
        return {"ok": True, "results": results}

    def inspect_hf_repo(self, repo_id: str, token: str = "") -> dict[str, Any]:
        rid = (repo_id or "").strip()
        if not _HF_REPO_RE.match(rid):
            return {"ok": False, "error": "Enter a valid Hugging Face repo id like 'owner/model-name'."}
        tok = self.resolve_hf_token(token)
        url = f"https://huggingface.co/api/models/{urllib.parse.quote(rid, safe='/')}?blobs=true"
        headers = {"Accept": "application/json", "User-Agent": "satz-browser/0.5"}
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                return {
                    "ok": False,
                    "error": f"Access denied ({he.code}) for {rid}. Accept the license on huggingface.co/{rid} and provide an HF token.",
                }
            if he.code == 404:
                return {"ok": False, "error": f"Repository not found on Hugging Face: {rid}"}
            return {"ok": False, "error": f"Hugging Face API error ({he.code}): {he.reason}"}
        except Exception as exc:
            return {"ok": False, "error": f"Failed to inspect {rid}: {exc}"}

        siblings = data.get("siblings") or []
        files = _pick_hf_repo_files(siblings)
        total_bytes = sum(f["size"] for f in files)
        return {
            "ok": True,
            "repo_id": rid,
            "gated": bool(data.get("gated")),
            "private": bool(data.get("private")),
            "pipeline_tag": str(data.get("pipeline_tag") or ""),
            "file_count": len(files),
            "total_bytes": total_bytes,
            "files": files,
        }

    def start_hf_download(
        self,
        *,
        repo_id: str,
        token: str = "",
        target_dir: str = "",
        use_as_chat: bool = True,
    ) -> dict[str, Any]:
        rid = (repo_id or "").strip()
        if not _HF_REPO_RE.match(rid):
            return {"ok": False, "error": "Enter a valid Hugging Face repo id like 'owner/model-name'."}

        with self.lock:
            for dl in self._downloads.values():
                if dl.get("repo_id") == rid and dl.get("state") in ("queued", "downloading"):
                    return {"ok": True, "download": dict(dl), "already_running": True}

        inspected = self.inspect_hf_repo(rid, token=token)
        if not inspected.get("ok"):
            return inspected
        files: list[dict[str, Any]] = inspected.get("files") or []
        if not files:
            return {"ok": False, "error": f"No downloadable model files found in {rid}."}
        if not any(f["path"] == "config.json" for f in files):
            return {"ok": False, "error": f"{rid} does not look like a Transformers model (missing config.json)."}

        eff_tok = self.resolve_hf_token(token)
        if token.strip():
            self.save_hf_token(token.strip())

        slug = rid.replace("/", "--")
        dest_dir = Path(target_dir).expanduser().resolve() if target_dir.strip() else (self.models_dir / slug)
        dl_id = f"hfdl-{int(time.time() * 1000)}-{abs(hash(rid)) % 10000}"
        total_bytes = int(inspected.get("total_bytes") or 0)
        cancel_ev = threading.Event()
        job: dict[str, Any] = {
            "download_id": dl_id,
            "repo_id": rid,
            "target_dir": str(dest_dir),
            "state": "queued",
            "files_total": len(files),
            "files_done": 0,
            "current_file": "",
            "downloaded_bytes": 0,
            "total_bytes": total_bytes,
            "pct": 0.0,
            "speed_bps": 0.0,
            "error": "",
            "started_at": time.time(),
            "finished_at": 0.0,
            "use_as_chat": bool(use_as_chat),
            "model_id": "",
        }
        with self.lock:
            self._downloads[dl_id] = job
            self._cancel_events[dl_id] = cancel_ev

        t = threading.Thread(
            target=self._run_hf_download_worker,
            args=(dl_id, rid, files, dest_dir, eff_tok, bool(use_as_chat), cancel_ev),
            daemon=True,
            name=f"hf-dl-{slug[:24]}",
        )
        t.start()
        return {"ok": True, "download": dict(job)}

    def _run_hf_download_worker(
        self,
        dl_id: str,
        repo_id: str,
        files: list[dict[str, Any]],
        dest_dir: Path,
        hf_token: str,
        use_as_chat: bool,
        cancel_ev: threading.Event,
    ) -> None:
        class _NoRedirectAuthHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
                if new_req is not None:
                    parsed_new = urllib.parse.urlsplit(new_req.full_url)
                    if parsed_new.netloc.lower() != _HF_ALLOWED_HOST:
                        new_req.headers.pop("Authorization", None)
                        new_req.unredirected_hdrs.pop("Authorization", None)
                return new_req

        opener = urllib.request.build_opener(_NoRedirectAuthHandler())
        t0 = time.time()
        completed_bytes_before = 0
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            with self.lock:
                self._downloads[dl_id]["state"] = "downloading"

            for idx, finfo in enumerate(files):
                if cancel_ev.is_set():
                    with self.lock:
                        self._downloads[dl_id]["state"] = "cancelled"
                        self._downloads[dl_id]["error"] = "Cancelled by user."
                        self._downloads[dl_id]["finished_at"] = time.time()
                    return

                rel_name = finfo["path"]
                expected_sz = int(finfo.get("size") or 0)
                out_file = (dest_dir / rel_name).resolve()
                if dest_dir.resolve() not in out_file.parents and out_file != dest_dir.resolve():
                    raise RuntimeError(f"Unsafe file path in repo: {rel_name}")
                out_file.parent.mkdir(parents=True, exist_ok=True)

                with self.lock:
                    self._downloads[dl_id]["current_file"] = rel_name

                if out_file.is_file() and expected_sz > 0 and out_file.stat().st_size == expected_sz:
                    completed_bytes_before += expected_sz
                    with self.lock:
                        self._downloads[dl_id]["files_done"] = idx + 1
                        self._downloads[dl_id]["downloaded_bytes"] = completed_bytes_before
                        tb = max(1, int(self._downloads[dl_id]["total_bytes"] or completed_bytes_before))
                        self._downloads[dl_id]["pct"] = min(100.0, round(100.0 * completed_bytes_before / tb, 1))
                    continue

                part_file = out_file.with_name(out_file.name + ".part")
                existing_part = part_file.stat().st_size if part_file.is_file() else 0
                url = f"https://huggingface.co/{urllib.parse.quote(repo_id, safe='/')}/resolve/main/{urllib.parse.quote(rel_name, safe='/')}"
                hdrs = {"User-Agent": "satz-browser/0.5"}
                if hf_token:
                    hdrs["Authorization"] = f"Bearer {hf_token}"
                if existing_part > 0:
                    hdrs["Range"] = f"bytes={existing_part}-"
                req = urllib.request.Request(url, headers=hdrs, method="GET")

                try:
                    resp = opener.open(req, timeout=30.0)
                except urllib.error.HTTPError as he:
                    if he.code in (401, 403):
                        raise RuntimeError(
                            f"Access denied ({he.code}) downloading {repo_id}. Accept its license on huggingface.co/{repo_id} and save a Hugging Face token in Settings."
                        ) from he
                    if he.code == 416 and part_file.is_file():
                        part_file.unlink(missing_ok=True)
                        existing_part = 0
                        hdrs.pop("Range", None)
                        resp = opener.open(urllib.request.Request(url, headers=hdrs, method="GET"), timeout=30.0)
                    else:
                        raise

                file_written = 0
                mode = "wb"
                if getattr(resp, "status", 200) == 206 and existing_part > 0:
                    mode = "ab"
                    file_written = existing_part

                with resp, open(part_file, mode) as fh:
                    while True:
                        if cancel_ev.is_set():
                            with self.lock:
                                self._downloads[dl_id]["state"] = "cancelled"
                                self._downloads[dl_id]["error"] = "Cancelled by user."
                                self._downloads[dl_id]["finished_at"] = time.time()
                            return
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        fh.write(chunk)
                        file_written += len(chunk)
                        total_done = completed_bytes_before + file_written
                        elapsed = max(0.2, time.time() - t0)
                        with self.lock:
                            tb = max(total_done, int(self._downloads[dl_id]["total_bytes"] or 0), 1)
                            self._downloads[dl_id]["downloaded_bytes"] = total_done
                            self._downloads[dl_id]["pct"] = min(99.9, round(100.0 * total_done / tb, 1))
                            self._downloads[dl_id]["speed_bps"] = round(total_done / elapsed, 1)

                part_file.replace(out_file)
                completed_bytes_before += file_written
                with self.lock:
                    self._downloads[dl_id]["files_done"] = idx + 1
                    self._downloads[dl_id]["downloaded_bytes"] = completed_bytes_before
                    tb = max(completed_bytes_before, int(self._downloads[dl_id]["total_bytes"] or 0), 1)
                    self._downloads[dl_id]["pct"] = min(100.0, round(100.0 * completed_bytes_before / tb, 1))

            ok, err = _is_hf_llm_dir_valid(dest_dir)
            if not ok:
                raise RuntimeError(err)

            is_gemma4 = "gemma-4-e4b" in repo_id.lower()
            model_id = "gemma-4-e4b" if is_gemma4 else f"local:{repo_id}"
            with self.lock:
                if is_gemma4:
                    self._data["overrides"]["chat_llm_path"] = str(dest_dir)
                self._data["custom_llms"] = [
                    e
                    for e in self._data.get("custom_llms", [])
                    if e.get("id") != model_id and e.get("path") != str(dest_dir)
                ]
                if not is_gemma4:
                    self._data["custom_llms"].append(
                        {
                            "id": model_id,
                            "label": repo_id.split("/", 1)[-1],
                            "repo_id": repo_id,
                            "path": str(dest_dir),
                            "source": "huggingface",
                            "size_bytes": _dir_size_bytes(dest_dir),
                            "added_at": time.time(),
                        }
                    )
                self._save_config()

            if is_gemma4:
                with self.runtime.model_lock:
                    self.runtime.gemma_model = None
                    self.runtime.gemma_tok = None
                    self.runtime.gemma_processor = None
                    self.runtime._loaded_local_llm_dir = None

            if use_as_chat:
                self.runtime.update_model_management_config(
                    {
                        "role_chat": model_id,
                        "role_news_planner": model_id,
                        "role_news_capture": model_id,
                        "role_news_analyzer": model_id,
                    }
                )

            with self.lock:
                self._downloads[dl_id]["state"] = "completed"
                self._downloads[dl_id]["pct"] = 100.0
                self._downloads[dl_id]["current_file"] = ""
                self._downloads[dl_id]["model_id"] = model_id
                self._downloads[dl_id]["finished_at"] = time.time()
        except Exception as exc:
            with self.lock:
                self._downloads[dl_id]["state"] = "error"
                self._downloads[dl_id]["error"] = str(exc)
                self._downloads[dl_id]["finished_at"] = time.time()

    def cancel_hf_download(self, download_id: str) -> dict[str, Any]:
        dl_id = (download_id or "").strip()
        with self.lock:
            ev = self._cancel_events.get(dl_id)
            if ev is None:
                return {"ok": False, "error": f"Download not found: {dl_id}"}
            ev.set()
            if dl_id in self._downloads and self._downloads[dl_id].get("state") in ("queued", "downloading"):
                self._downloads[dl_id]["state"] = "cancelled"
                self._downloads[dl_id]["error"] = "Cancelled by user."
        return {"ok": True, "download_id": dl_id}

    def list_hf_downloads(self) -> list[dict[str, Any]]:
        with self.lock:
            items = [dict(v) for v in self._downloads.values()]
        items.sort(key=lambda x: float(x.get("started_at") or 0.0), reverse=True)
        return items[:20]

    def get_snapshot(self) -> dict[str, Any]:
        tok = self.resolve_hf_token()
        with self.lock:
            overrides = dict(self._data.get("overrides") or {})
        gemma_dir = self.resolve_chat_llm_dir("gemma-4-e4b")
        gemma_ready = _is_hf_llm_dir_valid(gemma_dir)[0]
        planck_ckpt, planck_source = self.resolve_planck_reader_ckpt()
        enc_ckpt, _enc_tok, enc_source = self.resolve_planck13_encoder()
        hertz_ckpt = self.resolve_hertz_reader_ckpt()
        return {
            "models_dir": str(self.models_dir),
            "gemma_path": str(gemma_dir),
            "gemma_ready": gemma_ready,
            "local_llm_ready": self.first_ready_local_llm_id() is not None,
            "planck_reader_source": planck_source,
            "planck_reader_path": str(planck_ckpt or ""),
            "planck13_source": enc_source,
            "planck13_path": str(enc_ckpt or ""),
            "hertz_reader_path": str(hertz_ckpt or ""),
            "hertz_ready": bool(hertz_ckpt and hertz_ckpt.exists()),
            "custom_llms": self.list_custom_llms(),
            "overrides": overrides,
            "hf_catalog": list(HF_CURATED_CATALOG),
            "hf_token_configured": bool(tok),
            "hf_token_masked": _mask_secret(tok),
            "downloads": self.list_hf_downloads(),
        }

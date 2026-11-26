"""Shared helpers: UTF-8 safe I/O (Windows cp1252 consoles), text normalization."""

import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

STOPWORDS = frozenset("""
a an the of in on at to for from by with and or is are was were be been being
what which who whom whose when where why how does do did has have had it its
this that these those as into than then there their they he she his her you
your we our i me my not no yes can could would should will shall may might
about after before over under between during per via vs versus also only
""".split())


def utf8_console():
    """Windows consoles default to cp1252; non-ASCII page text would crash print()."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_env(path: str | Path | None = None) -> list[str]:
    """
    KEY=VALUE lines from the repo's .env (gitignored; template .env.example) into os.environ.
    A variable already set in the environment wins. Returns the names loaded (never the values).
    """
    import os
    p = Path(path) if path else REPO_ROOT / ".env"
    if not p.exists():
        return []
    loaded = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ts() -> float:
    return time.time()


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_text(s: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    s = strip_accents(str(s)).lower()
    s = re.sub(r"[^\w\s.]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)  # keep decimal points only
    return re.sub(r"\s+", " ", s).strip()


def content_words(s: str) -> list[str]:
    return [w for w in norm_text(s).split() if w not in STOPWORDS and len(w) > 1]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

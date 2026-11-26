from __future__ import annotations

import base64
from collections import Counter
import datetime
import difflib
import email
import email.header
import email.policy
import email.utils
import hashlib
import html as html_lib
from html.parser import HTMLParser
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
import urllib.error
import urllib.parse
import urllib.request
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
    normalizes dark-on-dark inline text colors for the #000000 terminal canvas, and blocks
    remote http(s) images unless allow_remote_images is enabled for that sender.
    """
    if not raw_html:
        return "<html><body><pre>(empty message)</pre></body></html>"
    h = re.sub(r"(?is)<(script|iframe|object|embed|applet|meta|base|link)\b[^>]*>.*?</\1>", "", raw_html)
    h = re.sub(r"(?is)<(script|iframe|object|embed|applet|meta|base|link)\b[^>]*/?>", "", h)
    h = re.sub(r'(?i)\s+on[a-z0-9_]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', "", h)
    h = re.sub(r'(?i)(href|src)\s*=\s*["\']\s*javascript:[^"\']*["\']', r'\1="#"', h)
    # Remove dark inline color attributes/styles (e.g. Apple Mail <font color="#000000" style="color: rgb(0, 0, 0)">)
    h = re.sub(r'(?i)\bcolor\s*=\s*["\']#[0-3][0-9a-f]{5}["\']', 'color="#e8e8e8"', h)
    h = re.sub(r'(?i)-webkit-text-stroke-color\s*:\s*[^;"]+;?', "", h)
    h = re.sub(
        r'(?i)(?<![a-z-])color\s*:\s*(?:#0{3,6}|#000001|#[0-2][0-9a-f]{5}|rgb\(\s*[0-4]?\d\s*,\s*[0-4]?\d\s*,\s*[0-4]?\d\s*\)|black)\b;?',
        "color: #e8e8e8;",
        h,
    )
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


_UNSUB_STRONG_RE = re.compile(
    r"\b(?:unsubscribe|abmelden|newsletter\s+abmelden|newsletter\s+abbestellen|abbestellen|"
    r"e-?mails?\s+abbestellen|austragen|opt[\s-]?out|remove\s+me|stop\s+receiving|"
    r"no\s+longer\s+(?:wish|want)\s+to\s+receive|keine\s+(?:weiteren\s+)?(?:e-?mails|newsletter))\b",
    re.I,
)
_UNSUB_PREF_RE = re.compile(
    r"\b(?:manage\s+(?:your\s+)?(?:email\s+)?preferences|email\s+preferences|"
    r"notification\s+(?:settings|preferences)|einstellungen\s+(?:verwalten|anpassen)|"
    r"benachrichtigungseinstellungen|newsletter[\s-]?einstellungen|präferenzen)\b",
    re.I,
)
_UNSUB_CONTEXT_RE = re.compile(
    r"(?:unsubscribe|abmelden|abbestellen|opt[\s-]?out|austragen|"
    r"receiving\s+this\s+e-?mail|erhalten\s+diese\s+e-?mail|no\s+longer\s+wish)",
    re.I,
)
_UNSUB_GENERIC_ANCHOR_RE = re.compile(
    r"^\s*(?:click\s+here|here|hier\s+klicken|hier|klicke\s+hier|link|this\s+link)\s*[.!]*\s*$",
    re.I,
)
_UNSUB_URL_HINT_RE = re.compile(
    r"(?:unsub|opt[\-_]?out|abmeld|abbestell|austrag|mailing[\-_]?list|email[\-_]?pref|remove[\-_]?sub)",
    re.I,
)
_UNSUB_NEGATIVE_RE = re.compile(
    r"(?:resubscribe|subscribe\s+again|wieder\s+anmelden|\bprivacy\b|\bdatenschutz\b|"
    r"\bimpressum\b|\bimprint\b|\bterms\b|\bagb\b|nutzungsbedingungen|view\s+in\s+browser|"
    r"im\s+browser\s+ansehen|facebook\.com|instagram\.com|twitter\.com|x\.com|linkedin\.com|"
    r"youtube\.com|tiktok\.com|apps\.apple\.com|play\.google\.com|"
    r"\.(?:png|jpe?g|gif|svg|webp|ico)(?:\?|$))",
    re.I,
)
_UNSUB_DONE_RE = re.compile(
    r"(?:you\s+have\s+been\s+unsubscribed|you\s+are\s+(?:now\s+)?unsubscribed|"
    r"successfully\s+unsubscribed|unsubscribed\s+successfully|"
    r"your\s+e-?mail(?:\s+address)?\s+has\s+been\s+removed|"
    r"opt[\s-]?out\s+confirmed|erfolgreich\s+abgemeldet|"
    r"sie\s+wurden(?:\s+erfolgreich)?\s+abgemeldet|"
    r"abmeldung(?:\s+war)?\s+erfolgreich|abmeldung\s+bestätigt|"
    r"vom\s+newsletter\s+abgemeldet|erfolgreich\s+ausgetragen|"
    r"sie\s+erhalten\s+(?:nun\s+)?keine\s+(?:weiteren\s+)?(?:e-?mails|newsletter)\s+mehr)",
    re.I,
)
_UNSUB_CAPTCHA_OR_LOGIN_RE = re.compile(
    r"(?:verify\s+you\s+are\s+human|complete\s+the\s+captcha|i\s+am\s+not\s+a\s+robot|"
    r"recaptcha|hcaptcha|cf-turnstile|please\s+sign\s+in|log\s+in\s+to\s+continue|"
    r"bitte\s+melde\s+dich\s+an)",
    re.I,
)


def classify_unsubscribe_page_text(text: str) -> str:
    """Classifies landing-page text cleanly without calling any LLM."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "unknown"
    if _UNSUB_CAPTCHA_OR_LOGIN_RE.search(t):
        return "captcha_or_login"
    if _UNSUB_DONE_RE.search(t):
        return "already_unsubscribed"
    if _UNSUB_STRONG_RE.search(t) or _UNSUB_PREF_RE.search(t):
        return "needs_confirmation"
    return "unknown"


def _parse_mailto_uri(raw_uri: str) -> dict[str, str] | None:
    uri = (raw_uri or "").strip()
    if not uri.lower().startswith("mailto:"):
        return None
    try:
        parsed = urllib.parse.urlsplit(uri)
        to_addr = urllib.parse.unquote(parsed.path or "").strip()
        qs = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        subj = (qs.get("subject") or [""])[0].strip() or "Unsubscribe"
        body = (qs.get("body") or [""])[0].strip() or "Unsubscribe"
        if not to_addr or "@" not in to_addr:
            return None
        return {
            "mailto": uri,
            "to": to_addr,
            "subject": subj[:240],
            "body": body[:2000],
        }
    except Exception:
        return None


def _parse_list_unsubscribe_header(header_val: str) -> dict[str, Any]:
    raw = (header_val or "").strip()
    http_urls: list[str] = []
    mailto_entries: list[dict[str, str]] = []
    if not raw or raw.lower().startswith("precedence:"):
        return {"http_urls": http_urls, "mailto_entries": mailto_entries}

    tokens = re.findall(r"<([^>]+)>", raw)
    if not tokens:
        tokens = [t.strip(" ,;") for t in re.split(r"[\s,]+", raw) if t.strip()]

    seen_http: set[str] = set()
    seen_mailto: set[str] = set()
    for tok in tokens:
        u = html_lib.unescape(tok).strip()
        low = u.lower()
        if low.startswith(("https://", "http://")):
            if u not in seen_http:
                seen_http.add(u)
                http_urls.append(u)
        elif low.startswith("mailto:"):
            parsed_m = _parse_mailto_uri(u)
            if parsed_m and parsed_m["to"].lower() not in seen_mailto:
                seen_mailto.add(parsed_m["to"].lower())
                mailto_entries.append(parsed_m)
    http_urls.sort(key=lambda x: (0 if x.lower().startswith("https://") else 1))
    return {"http_urls": http_urls, "mailto_entries": mailto_entries}


class _UnsubLinkHTMLParser(HTMLParser):
    """Lightweight stdlib HTML anchor extractor with nearby surrounding text context."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_a = False
        self._cur_href = ""
        self._cur_meta = ""
        self._cur_text: list[str] = []
        self._text_chunks: list[str] = []
        self._pre_ctx = ""
        self.anchors: list[dict[str, Any]] = []

    def _recent_text(self) -> str:
        joined = " ".join(self._text_chunks[-18:])
        return re.sub(r"\s+", " ", joined).strip()[-140:]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "head"):
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t == "a":
            attr_map = {k.lower(): (v or "") for k, v in attrs if k}
            href = html_lib.unescape(attr_map.get("href") or "").strip()
            if href and not href.lower().startswith(("javascript:", "data:", "#")):
                self._in_a = True
                self._cur_href = href
                self._cur_meta = " ".join(
                    x for x in (attr_map.get("title", ""), attr_map.get("aria-label", "")) if x
                ).strip()
                self._cur_text = []
                self._pre_ctx = self._recent_text()
        elif t == "img" and self._in_a:
            attr_map = {k.lower(): (v or "") for k, v in attrs if k}
            alt_v = (attr_map.get("alt") or attr_map.get("title") or "").strip()
            if alt_v:
                self._cur_text.append(alt_v)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "head") and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if t == "a" and self._in_a:
            txt = re.sub(r"\s+", " ", "".join(self._cur_text)).strip()
            if txt:
                self._text_chunks.append(txt)
            self.anchors.append(
                {
                    "href": self._cur_href,
                    "text": txt,
                    "meta": self._cur_meta,
                    "pre_context": self._pre_ctx,
                    "idx": len(self.anchors),
                }
            )
            self._in_a = False
            self._cur_href = ""
            self._cur_meta = ""
            self._cur_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        clean = re.sub(r"\s+", " ", data or "").strip()
        if not clean:
            return
        if self._in_a:
            self._cur_text.append(clean)
        else:
            self._text_chunks.append(clean)


def _score_unsubscribe_candidate(url: str, label: str, pre_context: str, pos_ratio: float) -> int:
    u_low = (url or "").lower()
    lbl_full = re.sub(r"\s+", " ", (label or "").strip())
    ctx_full = re.sub(r"\s+", " ", (pre_context or "").strip())
    if not u_low.startswith(("http://", "https://")):
        return -50
    if _UNSUB_NEGATIVE_RE.search(u_low) or _UNSUB_NEGATIVE_RE.search(lbl_full):
        return -25
    score = 0
    if _UNSUB_STRONG_RE.search(lbl_full):
        score += 14
    elif _UNSUB_PREF_RE.search(lbl_full):
        score += 7
    elif _UNSUB_GENERIC_ANCHOR_RE.match(lbl_full) and _UNSUB_CONTEXT_RE.search(ctx_full):
        score += 10
    elif _UNSUB_CONTEXT_RE.search(ctx_full):
        score += 4

    if _UNSUB_URL_HINT_RE.search(u_low):
        score += 5
    # Footer links at bottom of email deserve a small tiebreaker boost
    if score > 0 and pos_ratio >= 0.65:
        score += 2
    return score


STYLE_DISTILL_MIN_SAMPLES = 10
STYLE_DISTILL_STEP = 5
STYLE_BRAIN_ENTITY_NAME = "Email Writing Style Preferences"
STYLE_BRAIN_ENTITY_SLUG = "email-writing-style-preferences"

_DE_STYLE_WORDS = {
    "hallo",
    "guten",
    "danke",
    "vielen",
    "viele",
    "beste",
    "grüße",
    "gruesse",
    "grüsse",
    "liebe",
    "lieber",
    "freundlichen",
    "bitte",
    "gerne",
    "ich",
    "wir",
    "und",
    "nicht",
    "für",
    "fuer",
    "über",
    "ueber",
    "morgen",
    "heute",
    "termin",
    "können",
    "koennen",
    "würde",
    "wuerde",
    "passt",
    "schon",
    "noch",
    "auch",
    "lg",
    "vg",
    "mfg",
}

_EN_STYLE_WORDS = {
    "hi",
    "hello",
    "hey",
    "dear",
    "thanks",
    "thank",
    "best",
    "regards",
    "cheers",
    "please",
    "would",
    "could",
    "the",
    "and",
    "for",
    "you",
    "your",
    "we",
    "tomorrow",
    "today",
    "meeting",
    "sounds",
    "good",
    "let",
    "following",
    "shortly",
}

_CLICHE_FILLER_PHRASES = (
    "i hope this email finds you well",
    "hope this email finds you well",
    "hope you are doing well",
    "hope you're doing well",
    "thank you for reaching out",
    "thanks for reaching out",
    "please do not hesitate to reach out",
    "please let me know if you have any questions",
    "ich hoffe, es geht ihnen gut",
    "ich hoffe es geht dir gut",
    "vielen dank für ihre nachricht",
    "bei fragen stehe ich gerne zur verfügung",
)

_GREETING_RE = re.compile(
    r"^(hi|hey|hello|hallo|dear|guten\s+tag|guten\s+morgen|guten\s+abend|servus|moin|liebe[rs]?)(?:\s+([^,!\n]{1,36}))?\s*[,!]?\s*$",
    re.IGNORECASE,
)

_SIGNOFF_RE = re.compile(
    r"^(best\s+regards|kind\s+regards|warm\s+regards|best|thanks|thank\s+you|cheers|sincerely|regards|"
    r"viele\s+grüße|viele\s+gruesse|viele\s+grüsse|beste\s+grüße|beste\s+gruesse|beste\s+grüsse|"
    r"liebe\s+grüße|liebe\s+gruesse|mit\s+freundlichen\s+grüßen|mit\s+freundlichen\s+gruessen|"
    r"danke|vg|lg|mfg)\s*[,!]?\s*$",
    re.IGNORECASE,
)


def _strip_quoted_reply(body: str) -> str:
    """Removes quoted thread blocks (`On ... wrote:`, `> ...`, `--- Quoted Thread ---`) from a draft/sent email."""
    txt = str(body or "").replace("\r\n", "\n")
    for marker in (
        r"\n\s*On\s+.{4,120}\bwrote:\s*\n",
        r"\n\s*Am\s+.{4,120}\bschrieb\b.*:\s*\n",
        r"\n\s*---\s*Quoted Thread\s*---\s*\n",
        r"\n\s*-{3,}\s*Original Message\s*-{3,}\s*\n",
        r"\n\s*From:\s+.+\nSent:\s+",
    ):
        m = re.search(marker, txt, flags=re.IGNORECASE)
        if m:
            txt = txt[: m.start()]
    lines = txt.splitlines()
    while lines and (lines[-1].lstrip().startswith(">") or not lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).strip()


def _detect_language_de_en(text: str) -> str:
    """Lightweight deterministic German vs English detector (`de`, `en`, or `unknown`)."""
    clean = (text or "").strip()
    if not clean:
        return "unknown"
    try:
        from satz_translate import detect_language

        lang = detect_language(clean, hint_lang="unknown")
        if lang in ("de", "en"):
            return lang
    except Exception:
        pass
    low = clean.lower()
    de_score = 0
    en_score = 0
    if any(ch in low for ch in ("ä", "ö", "ü", "ß")):
        de_score += 2
    tokens = re.findall(r"[a-zäöüß]{2,}", low)
    for tok in tokens:
        if tok in _DE_STYLE_WORDS:
            de_score += 1
        if tok in _EN_STYLE_WORDS:
            en_score += 1
    if de_score > en_score and de_score >= 1:
        return "de"
    if en_score > de_score and en_score >= 1:
        return "en"
    if de_score == en_score and de_score > 0:
        return "de" if any(ch in low for ch in ("ä", "ö", "ü", "ß")) else "en"
    return "unknown"


def _extract_email_and_domain(raw_rcpt: str) -> tuple[str, str]:
    txt = (raw_rcpt or "").strip()
    m = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", txt)
    if not m:
        return "", ""
    addr = m.group(1).strip().lower()
    dom = addr.split("@", 1)[1] if "@" in addr else ""
    return addr, dom


def _extract_greeting_and_signoff(body_clean: str) -> tuple[str, str]:
    """Extracts normalized greeting (`Hi <Name>,` / `Hallo <Name>,` / `<none>`) and closing sign-off."""
    lines = [ln.strip() for ln in (body_clean or "").splitlines()]
    non_empty = [ln for ln in lines if ln]
    if not non_empty:
        return "<none>", "<none>"

    greeting = "<none>"
    first = non_empty[0]
    if len(first) <= 64:
        gm = _GREETING_RE.match(first)
        if gm:
            head_word = gm.group(1).strip()
            name_part = (gm.group(2) or "").strip()
            punct = "," if first.endswith(",") else ("!" if first.endswith("!") else "")
            if name_part:
                if name_part.lower() in ("all", "team", "everyone", "alle", "zusammen"):
                    greeting = f"{head_word} {name_part}{punct}"
                else:
                    greeting = f"{head_word} <Name>{punct}"
            else:
                greeting = f"{head_word}{punct}"

    signoff = "<none>"
    if len(non_empty) >= 2:
        last = non_empty[-1]
        prev = non_empty[-2]
        if _SIGNOFF_RE.match(last):
            signoff = last
        elif (
            len(last) <= 32
            and not any(ch in last for ch in (".", "?", "!"))
            and _SIGNOFF_RE.match(prev)
        ):
            signoff = f"{prev}\n{last}"
    elif _SIGNOFF_RE.match(non_empty[-1]):
        signoff = non_empty[-1]

    return greeting, signoff


def _analyze_outbox_edit_diff(
    draft_body: str,
    sent_body: str,
    to_list: list[str],
) -> dict[str, Any]:
    """Compares AI-drafted reply vs final sent outbox body to extract concrete style signals."""
    draft_clean = _strip_quoted_reply(draft_body)
    sent_clean = _strip_quoted_reply(sent_body)
    similarity = difflib.SequenceMatcher(None, draft_clean, sent_clean).ratio() if (draft_clean or sent_clean) else 1.0
    edit_ratio = round(max(0.0, min(1.0, 1.0 - similarity)), 4)

    draft_words = len(re.findall(r"\S+", draft_clean))
    sent_words = len(re.findall(r"\S+", sent_clean))
    compression_ratio = round(sent_words / max(1, draft_words), 3) if draft_words > 0 else 1.0

    draft_greeting, draft_signoff = _extract_greeting_and_signoff(draft_clean)
    sent_greeting, sent_signoff = _extract_greeting_and_signoff(sent_clean)
    draft_lang = _detect_language_de_en(draft_clean)
    sent_lang = _detect_language_de_en(sent_clean)

    draft_low = draft_clean.lower()
    sent_low = sent_clean.lower()
    removed_phrases = [
        phrase
        for phrase in _CLICHE_FILLER_PHRASES
        if phrase in draft_low and phrase not in sent_low
    ]

    recipient_addr, recipient_domain = ("", "")
    for r in to_list:
        addr, dom = _extract_email_and_domain(r)
        if addr:
            recipient_addr, recipient_domain = addr, dom
            break

    diff_preview = "\n".join(
        list(
            difflib.unified_diff(
                draft_clean.splitlines(),
                sent_clean.splitlines(),
                fromfile="ai_draft",
                tofile="sent_outbox",
                lineterm="",
                n=1,
            )
        )[:24]
    )

    return {
        "recipient_addr": recipient_addr,
        "recipient_domain": recipient_domain,
        "edit_ratio": edit_ratio,
        "draft_words": draft_words,
        "sent_words": sent_words,
        "compression_ratio": compression_ratio,
        "draft_greeting": draft_greeting,
        "sent_greeting": sent_greeting,
        "draft_signoff": draft_signoff,
        "sent_signoff": sent_signoff,
        "draft_lang": draft_lang,
        "sent_lang": sent_lang,
        "removed_phrases": removed_phrases,
        "diff_preview": diff_preview,
    }


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
        self._account_sync_locks: dict[str, threading.Lock] = {}
        self._sync_locks_guard = threading.Lock()
        self.sync_poll_interval_secs = 120.0

        # Pipeline reference (attached in M12)
        self.pipeline: Any = None

        # Pending SMTP send confirmations & outbox timer (M13)
        self._confirm_tokens: dict[str, dict[str, Any]] = {}
        self._send_timers: dict[str, threading.Timer] = {}
        self._brain_synced_accounts_sig: Any = None
        self.style_distiller_fn: Callable[[list[dict[str, Any]], dict[str, Any]], str] | None = None

        self._ensure_connection()
        from satz_mail_pipeline import SatzMailPipeline

        self.pipeline = SatzMailPipeline(self.runtime, self)

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

    def rebind_profile(self, *, defer_sync_start: bool = False) -> None:
        emit = getattr(self.runtime, "emit_unlock_progress", None)
        with self.db_lock:
            self.stop_all_sync_threads()
            self._auth_stopped_accounts.clear()
            self._brain_synced_accounts_sig = None
            if self.passwords.unlocked and callable(emit):
                emit("mail", "running", detail="opening_mail_db")
            self._ensure_connection()
            if self.pipeline is not None:
                self.pipeline._load_active_model_if_exists(load_weights=False)
            if self.passwords.unlocked:
                self.repair_calendar_pings_if_needed()
            if self.passwords.unlocked and not defer_sync_start:
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
                list_unsubscribe_post TEXT NOT NULL DEFAULT '',
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
                sent_at REAL NOT NULL DEFAULT 0.0,
                ai_draft_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS ai_drafts (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL DEFAULT '',
                reply_to_message_id TEXT NOT NULL DEFAULT '',
                to_addr TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                draft_body TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS writing_style_diffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                outbox_id TEXT NOT NULL UNIQUE,
                ai_draft_id TEXT NOT NULL DEFAULT '',
                recipient_key TEXT NOT NULL DEFAULT '',
                recipient_domain TEXT NOT NULL DEFAULT '',
                draft_body TEXT NOT NULL DEFAULT '',
                sent_body TEXT NOT NULL DEFAULT '',
                edit_ratio REAL NOT NULL DEFAULT 0.0,
                diff_summary_json TEXT NOT NULL DEFAULT '{}',
                at REAL NOT NULL DEFAULT 0.0,
                used_in_distill INTEGER NOT NULL DEFAULT 0
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

            CREATE TABLE IF NOT EXISTS message_translations (
                message_id TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                source_lang TEXT NOT NULL DEFAULT '',
                subject_tr TEXT NOT NULL DEFAULT '',
                snippet_tr TEXT NOT NULL DEFAULT '',
                new_text_tr TEXT NOT NULL DEFAULT '',
                html_tr TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (message_id, target_lang),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_msg_trans_lang
                ON message_translations(target_lang, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                message_id UNINDEXED,
                subject,
                from_name,
                from_addr,
                new_text
            );
            """
        )
        msg_cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "list_unsubscribe_post" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN list_unsubscribe_post TEXT NOT NULL DEFAULT ''")
        if "sender_header" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN sender_header TEXT NOT NULL DEFAULT ''")
        if "is_calendar" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN is_calendar INTEGER NOT NULL DEFAULT 0")
        outbox_cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(outbox)").fetchall()}
        if "ai_draft_id" not in outbox_cols:
            conn.execute("ALTER TABLE outbox ADD COLUMN ai_draft_id TEXT NOT NULL DEFAULT ''")
        acct_cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        if "updated_at" not in acct_cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN updated_at REAL NOT NULL DEFAULT 0.0")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mail_settings_ts (
                key TEXT PRIMARY KEY,
                updated_at REAL NOT NULL DEFAULT 0.0
            );
            CREATE TABLE IF NOT EXISTS mail_sync_tombstones (
                table_name TEXT NOT NULL,
                row_key TEXT NOT NULL,
                deleted_at REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (table_name, row_key)
            );
            INSERT OR IGNORE INTO mail_settings_ts (key, updated_at)
            SELECT key, 0.0 FROM mail_settings;

            CREATE TRIGGER IF NOT EXISTS trg_mail_settings_ai AFTER INSERT ON mail_settings
            BEGIN
                INSERT INTO mail_settings_ts (key, updated_at)
                VALUES (NEW.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at;
                DELETE FROM mail_sync_tombstones WHERE table_name = 'mail_settings' AND row_key = NEW.key;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_mail_settings_au AFTER UPDATE ON mail_settings
            BEGIN
                INSERT INTO mail_settings_ts (key, updated_at)
                VALUES (NEW.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(key) DO UPDATE SET updated_at = excluded.updated_at;
                DELETE FROM mail_sync_tombstones WHERE table_name = 'mail_settings' AND row_key = NEW.key;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_mail_settings_ad AFTER DELETE ON mail_settings
            BEGIN
                DELETE FROM mail_settings_ts WHERE key = OLD.key;
                INSERT INTO mail_sync_tombstones (table_name, row_key, deleted_at)
                VALUES ('mail_settings', OLD.key, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(table_name, row_key) DO UPDATE SET deleted_at = excluded.deleted_at;
            END;

            CREATE TRIGGER IF NOT EXISTS trg_mail_accounts_ai AFTER INSERT ON accounts
            BEGIN
                DELETE FROM mail_sync_tombstones WHERE table_name = 'accounts' AND row_key = NEW.id;
                UPDATE accounts SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE id = NEW.id AND COALESCE(updated_at, 0.0) <= 0.0;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_mail_accounts_au AFTER UPDATE OF label, email, protocol, in_host, in_port, in_security, smtp_host, smtp_port, smtp_security, vault_prefix, sync_days ON accounts
            WHEN COALESCE(NEW.updated_at, 0.0) <= COALESCE(OLD.updated_at, 0.0)
            BEGIN
                UPDATE accounts SET updated_at = (julianday('now') - 2440587.5) * 86400.0
                WHERE id = NEW.id;
            END;
            CREATE TRIGGER IF NOT EXISTS trg_mail_accounts_ad AFTER DELETE ON accounts
            BEGIN
                INSERT INTO mail_sync_tombstones (table_name, row_key, deleted_at)
                VALUES ('accounts', OLD.id, (julianday('now') - 2440587.5) * 86400.0)
                ON CONFLICT(table_name, row_key) DO UPDATE SET deleted_at = excluded.deleted_at;
            END;
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

    def _is_oauth_prefix(self, vault_prefix: str) -> bool:
        env_map = self.passwords.get_unlocked_credentials_map()
        pfx = (vault_prefix or "").strip().upper()
        return env_map.get(f"{pfx}_AUTH_TYPE", "").strip().lower() == "oauth2"

    def _resolve_auth_for_prefix(
        self,
        vault_prefix: str,
        acct_email: str = "",
        force_oauth_mode: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, str]:
        env_map = self.passwords.get_unlocked_credentials_map()
        pfx = (vault_prefix or "").strip().upper()
        username, password = self._resolve_credentials_for_prefix(pfx)
        username = username or (acct_email or "").strip()
        auth_type = env_map.get(f"{pfx}_AUTH_TYPE", "").strip().lower()
        if force_oauth_mode or auth_type == "oauth2":
            gauth = getattr(self.runtime, "google_auth", None)
            if gauth is None:
                raise PermissionError("Google OAuth manager is not initialized.")
            tok = gauth.get_valid_access_token(expected_email=username, force_refresh=force_refresh)
            oauth_email = env_map.get("GOOGLE_OAUTH_EMAIL", "").strip()
            eff_user = username or oauth_email
            return {"mode": "oauth2", "username": eff_user, "password": "", "access_token": tok}
        return {"mode": "password", "username": username, "password": password, "access_token": ""}

    def _xoauth2_bytes(self, username: str, access_token: str) -> bytes:
        return f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")

    def _imap_authenticate(
        self,
        imap: Any,
        auth_info: dict[str, str],
        vault_prefix: str = "",
        acct_email: str = "",
    ) -> None:
        if auth_info.get("mode") != "oauth2":
            imap.login(auth_info["username"], auth_info["password"])
            return
        tok = auth_info["access_token"]
        user = auth_info["username"]
        try:
            imap.authenticate("XOAUTH2", lambda _challenge: self._xoauth2_bytes(user, tok))
        except Exception:
            if vault_prefix:
                refreshed = self._resolve_auth_for_prefix(
                    vault_prefix, acct_email=acct_email, force_oauth_mode=True, force_refresh=True
                )
                tok2 = refreshed["access_token"]
                auth_info["access_token"] = tok2
                imap.authenticate("XOAUTH2", lambda _challenge: self._xoauth2_bytes(user, tok2))
                return
            raise

    def _smtp_authenticate(
        self,
        smtp: Any,
        auth_info: dict[str, str],
        vault_prefix: str = "",
        acct_email: str = "",
    ) -> None:
        if auth_info.get("mode") != "oauth2":
            smtp.login(auth_info["username"], auth_info["password"])
            return
        tok = auth_info["access_token"]
        user = auth_info["username"]
        try:
            smtp.auth("XOAUTH2", lambda _challenge=None: f"user={user}\x01auth=Bearer {tok}\x01\x01")
        except Exception:
            if vault_prefix:
                refreshed = self._resolve_auth_for_prefix(
                    vault_prefix, acct_email=acct_email, force_oauth_mode=True, force_refresh=True
                )
                tok2 = refreshed["access_token"]
                auth_info["access_token"] = tok2
                smtp.auth("XOAUTH2", lambda _challenge=None: f"user={user}\x01auth=Bearer {tok2}\x01\x01")
                return
            raise

    def _ensure_accounts_in_brain(self, accounts_list: list[dict[str, Any]]) -> None:
        brain = getattr(self.runtime, "brain", None)
        pm = getattr(self.runtime, "passwords", None)
        if brain is None or getattr(brain, "locked", False) or pm is None or not pm.unlocked:
            return
        user_prof = str(pm.active_profile_id or "default")
        sig = (
            user_prof,
            tuple(
                sorted(
                    (
                        str(a.get("id") or ""),
                        str(a.get("email") or "").strip().lower(),
                        str(a.get("label") or "").strip(),
                    )
                    for a in accounts_list
                )
            ),
        )
        if sig == self._brain_synced_accounts_sig:
            return
        try:
            for acct in accounts_list:
                email_addr = str(acct.get("email") or "").strip().lower()
                if not email_addr:
                    continue
                acct_label = str(acct.get("label") or email_addr).strip()
                proto = str(acct.get("protocol") or "imap").upper()
                in_host = str(acct.get("in_host") or "")
                brain.upsert_entity(
                    entity_type="account",
                    name=email_addr,
                    summary=f"Email profile {email_addr} ({acct_label} · {proto} {in_host}) in user profile {user_prof}.",
                    attributes={
                        "email": email_addr,
                        "email_profile": email_addr,
                        "account_label": acct_label,
                        "protocol": proto,
                        "in_host": in_host,
                        "user_profile": user_prof,
                        "$source": f"mail_account:{acct.get('id')}",
                    },
                    content=f"Note: Email account profile {email_addr} ({acct_label}) configured and indexed under user profile '{user_prof}'.",
                    aliases=[email_addr, acct_label] if acct_label.lower() != email_addr else [email_addr],
                    source_url=f"mail_account:{acct.get('id')}",
                    tier=1,
                    actor="mail/account",
                )
            self._brain_synced_accounts_sig = sig
        except Exception:
            pass

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
                acct_counts = self._compute_lane_counts(conn, account_id=aid)
                accounts.append(
                    {
                        "id": aid,
                        "label": r["label"] or r["email"],
                        "email": r["email"],
                        "protocol": r["protocol"],
                        "in_host": r["in_host"],
                        "in_port": int(r["in_port"]),
                        "in_security": r["in_security"],
                        "smtp_host": r["smtp_host"],
                        "smtp_port": int(r["smtp_port"]),
                        "smtp_security": r["smtp_security"],
                        "vault_prefix": r["vault_prefix"],
                        "auth_type": "oauth2" if self._is_oauth_prefix(r["vault_prefix"]) else "password",
                        "sync_days": int(r["sync_days"] or 30),
                        "last_sync_at": float(r["last_sync_at"] or 0.0),
                        "last_error": r["last_error"] or "",
                        "auth_failed": aid in self._auth_stopped_accounts or (r["last_error"] or "").startswith("[auth failed]"),
                        "message_count": int(msg_cnt_row["c"] if msg_cnt_row else 0),
                        "inbox_unread": acct_counts["inbox_unread"],
                        "counts": acct_counts,
                    }
                )
        if accounts:
            threading.Thread(
                target=self._ensure_accounts_in_brain,
                args=(accounts,),
                daemon=True,
                name="satz-mail-brain-accts",
            ).start()
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
        vault_prefix = ""
        auth_mode = str(payload.get("auth_type") or payload.get("auth_mode") or "").strip().lower()
        auth_info: dict[str, str] = {"mode": "password", "username": "", "password": "", "access_token": ""}

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
                vault_prefix = str(row["vault_prefix"] or "")
                acct_email = str(row["email"] or "")
                try:
                    auth_info = self._resolve_auth_for_prefix(vault_prefix, acct_email=acct_email)
                except Exception as ae:
                    return {"ok": False, "stage": "auth", "error": str(ae)}
                username = auth_info["username"] or acct_email
                password = auth_info["password"]
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
            if auth_mode == "oauth2":
                try:
                    auth_info = self._resolve_auth_for_prefix(vault_prefix, acct_email=username, force_oauth_mode=True)
                    username = username or auth_info["username"]
                except Exception as ae:
                    return {"ok": False, "stage": "auth", "error": str(ae)}
            else:
                if (not username or not password) and vault_prefix:
                    v_user, v_pass = self._resolve_credentials_for_prefix(vault_prefix)
                    username = username or v_user
                    password = password or v_pass
                auth_info = {"mode": "password", "username": username, "password": password, "access_token": ""}

        if not in_host or not smtp_host or not username or (
            auth_info.get("mode") != "oauth2" and not password
        ):
            return {
                "ok": False,
                "error": "Incoming host, outgoing SMTP host, username/email, and app password or Google OAuth are required.",
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
                    self._imap_authenticate(imap, auth_info, vault_prefix=vault_prefix, acct_email=username)
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
                self._smtp_authenticate(smtp, auth_info, vault_prefix=vault_prefix, acct_email=username)
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
            "auth_type": auth_info.get("mode", "password"),
            "in_host": in_host,
            "smtp_host": smtp_host,
        }

    def add_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Section 4.2 (M11): Stores credentials in `vault.enc` under `<PREFIX>_USERNAME`,
        `<PREFIX>_PASSWORD`, `<PREFIX>_IMAP_HOST`, `<PREFIX>_SMTP_HOST` (or `<PREFIX>_AUTH_TYPE=oauth2`
        backed by encrypted Google OAuth tokens) and creates the account row in `mail.sqlite`.
        """
        if not self.passwords.unlocked:
            raise PermissionError("Unlock the active profile vault before adding a mail account.")

        preset_id = str(payload.get("preset") or "").strip().lower()
        preset = MAIL_PRESETS.get(preset_id, {})
        auth_type = str(payload.get("auth_type") or payload.get("auth_mode") or "password").strip().lower()
        if auth_type not in ("password", "oauth2"):
            auth_type = "password"
        email_addr = str(payload.get("email") or payload.get("username") or "").strip()
        password = str(payload.get("password") or "").strip()
        raw_label = str(payload.get("label") or "").strip()
        generic_labels = {
            "",
            "gmail",
            "outlook",
            "outlook / hotmail",
            "icloud",
            "gmx",
            "web.de",
            "custom imap",
            "custom pop3",
        }
        label = email_addr if (raw_label.lower() in generic_labels and email_addr) else (raw_label or email_addr or str(preset.get("label") or "Mail"))
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
            clean_part = re.sub(r"[^A-Z0-9]+", "_", (email_addr or label or preset_id).upper()).strip("_")
            raw_prefix = f"MAIL_{clean_part}" if not clean_part.startswith("MAIL_") else clean_part

        if auth_type == "oauth2":
            gauth = getattr(self.runtime, "google_auth", None)
            if gauth is None:
                raise PermissionError("Google OAuth manager is not initialized.")
            st = gauth.get_status()
            if not st.get("signed_in"):
                raise PermissionError("Sign in with Google OAuth first.")
            if not email_addr:
                email_addr = str(st.get("email") or "").strip()
            gauth.get_valid_access_token(expected_email=email_addr)
            if not in_host:
                in_host = "imap.gmail.com"
            if not smtp_host:
                smtp_host = "smtp.gmail.com"
        else:
            # Check if credentials already exist in vault under raw_prefix
            if not password:
                existing_user, existing_pass = self._resolve_credentials_for_prefix(raw_prefix)
                if not email_addr and existing_user:
                    email_addr = existing_user
                password = existing_pass

        if not email_addr or not in_host or not smtp_host or (auth_type != "oauth2" and not password):
            raise ValueError("Email, app password (or Google OAuth), incoming host, and SMTP host are required.")

        # Save credentials / auth config in vault.enc under `<PREFIX>_*`
        self.passwords.upsert_service_credential(
            service=raw_prefix,
            username=email_addr,
            password="" if auth_type == "oauth2" else password,
            imap_host=in_host,
            extra={
                f"{raw_prefix}_SMTP_HOST": smtp_host,
                f"{raw_prefix}_AUTH_TYPE": auth_type,
            },
        )

        # Reuse existing account row for same email & host if linking OAuth
        existing_aid = ""
        with self.db_lock:
            conn = self._ensure_connection()
            prev = conn.execute(
                "SELECT id FROM accounts WHERE LOWER(email) = LOWER(?) AND LOWER(in_host) = LOWER(?) LIMIT 1",
                (email_addr, in_host),
            ).fetchone()
            if prev:
                existing_aid = str(prev["id"])
        account_id = str(payload.get("id") or existing_aid or f"acct-{uuid.uuid4().hex[:10]}")
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
            "auth_type": auth_type,
            "accounts": self.list_accounts()["accounts"],
        }

    def connect_google_oauth_account(
        self,
        *,
        email: str = "",
        label: str = "",
        sync_days: int = 30,
        start_sync: bool = True,
    ) -> dict[str, Any]:
        return self.add_account(
            {
                "preset": "gmail",
                "auth_type": "oauth2",
                "email": email,
                "label": label or email,
                "protocol": "imap",
                "in_host": "imap.gmail.com",
                "in_port": 993,
                "in_security": "ssl",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_security": "starttls",
                "sync_days": sync_days,
                "start_sync": start_sync,
            }
        )

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
    def repair_calendar_pings_if_needed(self) -> int:
        """
        One-time migration per profile: moves previously misclassified calendar invites/updates/RSVPs
        from `information` (Orders) or `email` into `ping` (with `platform` = Google/Microsoft/Calendar),
        and cleans stale order extracts, reply actions, Knowledge Store passages, and Brain `order` entities.
        Respects explicit user overrides (`labels.source = 'user'`).
        """
        if not self.passwords.unlocked:
            return 0
        from satz_mail_pipeline import MIN_TRAINING_SAMPLES, detect_calendar_notification

        repaired_ids: list[str] = []
        now = time.time()
        model_ver = getattr(self.pipeline, "model_version", "cold") if self.pipeline is not None else "cold"

        with self.db_lock:
            conn = self._ensure_connection()
            done = conn.execute(
                "SELECT value FROM mail_settings WHERE key = 'calendar_pings_repaired_v1'"
            ).fetchone()
            if done and str(done["value"]) == "1":
                return 0

            emit = getattr(self.runtime, "emit_unlock_progress", None)
            if callable(emit):
                emit("mail", "running", detail="repairing_calendar")

            rows = conn.execute(
                """
                SELECT m.id, m.from_addr, m.subject, m.sender_header, m.is_calendar,
                       COALESCE(l.label, '') AS label,
                       COALESCE(l.source, '') AS label_source,
                       SUBSTR(COALESCE(p.text, m.body_text, ''), 1, 3000) AS body_preview,
                       EXISTS(
                           SELECT 1 FROM attachments a
                           WHERE a.message_id = m.id
                             AND (LOWER(a.mime) IN ('text/calendar', 'application/ics') OR LOWER(a.filename) LIKE '%.ics')
                       ) AS has_cal_att
                FROM messages m
                LEFT JOIN labels l ON l.message_id = m.id
                LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
                """
            ).fetchall()

            for r in rows:
                lbl_source = str(r["label_source"] or "").lower()
                if lbl_source == "user":
                    continue
                is_cal_mime = bool(r["is_calendar"])
                has_cal_att = is_cal_mime or bool(r["has_cal_att"])
                cal_plat = detect_calendar_notification(
                    from_addr=str(r["from_addr"] or ""),
                    subject=str(r["subject"] or ""),
                    body_text=str(r["body_preview"] or ""),
                    sender_header=str(r["sender_header"] or ""),
                    has_calendar_part=has_cal_att,
                    is_calendar_mime=is_cal_mime,
                )
                if not cal_plat:
                    continue

                mid = str(r["id"])
                cur_lbl = str(r["label"] or "").lower()
                if cur_lbl == "ping":
                    plat_row = conn.execute(
                        "SELECT value FROM extracts WHERE message_id = ? AND field = 'platform'",
                        (mid,),
                    ).fetchone()
                    if plat_row and str(plat_row["value"] or "") == cal_plat:
                        continue
                else:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO labels (message_id, label, confidence, source, model_version, at)
                        VALUES (?, 'ping', 0.96, 'rule', ?, ?)
                        """,
                        (mid, model_ver, now),
                    )
                    repaired_ids.append(mid)

                conn.execute("DELETE FROM extracts WHERE message_id = ?", (mid,))
                conn.execute(
                    "INSERT INTO extracts (message_id, field, value, source, confidence) VALUES (?, 'platform', ?, 'rule', 1.0)",
                    (mid, cal_plat),
                )
                conn.execute("DELETE FROM actions WHERE message_id = ?", (mid,))

            conn.execute(
                "INSERT OR REPLACE INTO mail_settings (key, value) VALUES ('calendar_pings_repaired_v1', '1')"
            )
            conn.commit()

        if repaired_ids:
            rep_sources = {f"mail:{mid}" for mid in repaired_ids}
            if hasattr(self.runtime, "store") and self.runtime.store is not None:
                with self.runtime.store_lock:
                    try:
                        for mid in repaired_ids:
                            self.runtime.store.db.execute(
                                "DELETE FROM satz_sources WHERE source_id = ?",
                                (f"mail:{mid}",),
                            )
                            self.runtime.store.db.execute(
                                "DELETE FROM local_passages WHERE url = ?",
                                (f"satzmail://message/{mid}",),
                            )
                        self.runtime.store.db.commit()
                    except Exception:
                        pass

            brain = getattr(self.runtime, "brain", None)
            if brain is not None and not getattr(brain, "locked", True):
                try:
                    brain.delete_entities_by_source(rep_sources, entity_type="order")
                except Exception:
                    pass

            if (
                self.pipeline is not None
                and self.pipeline.model_version != "cold"
                and self.pipeline.trainer_fn is None
                and self.pipeline.model_predict_fn is None
            ):
                def _bg_retrain() -> None:
                    try:
                        with self.db_lock:
                            conn2 = self._ensure_connection()
                            samples = self.pipeline._get_training_samples(conn2)
                        if len(samples) >= MIN_TRAINING_SAMPLES:
                            self.pipeline.maybe_trigger_training(force_retrain=True)
                    except Exception:
                        pass

                threading.Thread(target=_bg_retrain, daemon=True, name="satz-mail-cal-retrain").start()

        return len(repaired_ids)

    def start_sync_threads_for_unlocked_profile(self) -> None:
        if not self.passwords.unlocked:
            return
        self.repair_calendar_pings_if_needed()
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

    def _get_account_sync_lock(self, account_id: str) -> threading.Lock:
        with self._sync_locks_guard:
            lock = self._account_sync_locks.get(account_id)
            if lock is None:
                lock = threading.Lock()
                self._account_sync_locks[account_id] = lock
            return lock

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
        with self._get_account_sync_lock(account_id):
            return self._sync_account_once_inner(account_id)

    def _sync_account_once_inner(self, account_id: str) -> dict[str, Any]:
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        with self.db_lock:
            conn = self._ensure_connection()
            acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if not acct:
                return {"ok": False, "error": f"Account {account_id} not found."}
            acct_dict = dict(acct)

        try:
            auth_info = self._resolve_auth_for_prefix(acct_dict["vault_prefix"], acct_email=acct_dict["email"])
        except Exception as ae:
            err_str = f"[auth failed] {ae}"
            self._auth_stopped_accounts.add(account_id)
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute("UPDATE accounts SET last_error = ? WHERE id = ?", (err_str, account_id))
                conn.commit()
            return {"ok": False, "error": err_str}

        username = auth_info["username"] or acct_dict["email"]
        password = auth_info["password"]
        if not username or (auth_info.get("mode") != "oauth2" and not password):
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
                synced_ids = self._sync_imap_account(acct_dict, username, password, auth_info=auth_info)

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

    def _sync_imap_account(
        self,
        acct: dict[str, Any],
        username: str,
        password: str = "",
        auth_info: dict[str, str] | None = None,
    ) -> list[str]:
        account_id = acct["id"]
        in_host = acct["in_host"]
        in_port = int(acct["in_port"] or 993)
        in_security = acct["in_security"] or "ssl"
        sync_days = max(1, int(acct.get("sync_days") or 30))

        eff_auth = auth_info or {"mode": "password", "username": username, "password": password, "access_token": ""}
        new_msg_ids: list[str] = []
        imap = self._open_imap_client(in_host, in_port, in_security)
        try:
            self._imap_authenticate(
                imap,
                eff_auth,
                vault_prefix=str(acct.get("vault_prefix") or ""),
                acct_email=str(acct.get("email") or username),
            )
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
                        "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.500000>)",
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
        list_unsub_post = str(msg.get("List-Unsubscribe-Post") or "").strip()
        precedence = str(msg.get("Precedence") or "").strip()
        if precedence and not list_unsub and precedence.lower() in ("bulk", "list", "junk"):
            list_unsub = f"Precedence: {precedence}"

        from_list = parse_address_list(msg.get("From"))
        from_name = from_list[0]["name"] if from_list else ""
        from_addr = from_list[0]["email"] if from_list else decode_mime_header(msg.get("From")).lower()
        sender_list = parse_address_list(msg.get("Sender"))
        sender_header = (
            sender_list[0]["email"] if sender_list and sender_list[0].get("email") else decode_mime_header(msg.get("Sender")).lower()
        )
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
        is_calendar_mime = 0
        if "calendar-notification@google.com" in sender_header or "calendar-notification@google.com" in from_addr:
            is_calendar_mime = 1

        if msg.is_multipart():
            part_idx = 0
            for part in msg.walk():
                if part.is_multipart():
                    continue
                part_idx += 1
                ctype = (part.get_content_type() or "text/plain").lower()
                disp = str(part.get_content_disposition() or "").lower()
                fname = decode_mime_header(part.get_filename())
                if not fname:
                    ct_name = part.get_param("name")
                    if ct_name:
                        fname = decode_mime_header(str(ct_name))
                cal_method = str(part.get_param("method") or "").strip().upper()
                is_cal_ctype = ctype in ("text/calendar", "application/ics")
                is_cal_name = (fname or "").strip().lower() in ("invite.ics", "meeting.ics", "event.ics", "calendar.ics")
                if (is_cal_ctype and cal_method in ("REQUEST", "REPLY", "CANCEL", "ADD", "COUNTER", "DECLINECOUNTER")) or is_cal_name:
                    is_calendar_mime = 1
                is_binary_part = ctype not in ("text/plain", "text/html") and (
                    ctype.startswith(("application/", "image/", "audio/", "video/"))
                    or disp in ("attachment", "inline")
                )
                if disp == "attachment" or fname or is_binary_part:
                    payload_bytes = part.get_payload(decode=True) or b""
                    if payload_bytes:
                        ext_guess = (
                            ".ics"
                            if ("calendar" in ctype or "ics" in ctype)
                            else ".pdf"
                            if "pdf" in ctype
                            else ".png"
                            if "png" in ctype
                            else ".jpg"
                            if ("jpeg" in ctype or "jpg" in ctype)
                            else ".bin"
                        )
                        attachment_rows.append(
                            {
                                "part_id": str(part_idx),
                                "filename": fname or f"attachment-{part_idx}{ext_guess}",
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
            cal_method = str(msg.get_param("method") or "").strip().upper()
            if ctype in ("text/calendar", "application/ics") and cal_method in ("REQUEST", "REPLY", "CANCEL", "ADD", "COUNTER", "DECLINECOUNTER", ""):
                is_calendar_mime = 1
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
                    in_reply_to, "references", from_addr, from_name, sender_header, to_json, cc_json,
                    subject, date, snippet, body_text, has_html, has_attachments, is_calendar,
                    list_unsubscribe, list_unsubscribe_post, seen, answered, flagged, hidden, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT hidden FROM messages WHERE id = ?), 0), ?)
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
                    sender_header,
                    json.dumps(to_list, ensure_ascii=False),
                    json.dumps(cc_list, ensure_ascii=False),
                    subject,
                    msg_ts,
                    snippet,
                    body_text,
                    has_html,
                    has_attachments,
                    is_calendar_mime,
                    list_unsub,
                    list_unsub_post,
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

    @staticmethod
    def _default_tracking_url_for_number(tracking_no: str) -> str:
        t = (tracking_no or "").strip()
        if not t:
            return ""
        if t.upper().startswith("1Z"):
            return f"https://www.ups.com/track?tracknum={t}"
        if t.upper().startswith("JJD") or (t.isdigit() and len(t) >= 12):
            return f"https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={t}"
        return f"https://duckduckgo.com/?q=track+{t}"

    def _compute_classifier_and_onboarding_info(
        self,
        conn: sqlite3.Connection,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        model_ver = getattr(self.pipeline, "model_version", "cold") if self.pipeline is not None else "cold"
        train_row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM labels l
            WHERE l.source IN ('gemma', 'user')
              AND l.message_id NOT IN (SELECT message_id FROM eval_labels)
            """
        ).fetchone()
        training_labels = int(train_row["c"] if train_row else 0)
        corr_row = conn.execute("SELECT COUNT(*) AS c FROM corrections").fetchone()
        corr_count = int(corr_row["c"] if corr_row else 0)

        status_text = (
            f"classifier: learning · {training_labels} / 50 labels"
            if model_ver == "cold"
            else f"classifier: {model_ver} · {training_labels} labels"
        )
        classifier_info = {
            "model_version": model_ver,
            "training_labels": training_labels,
            "target_labels": 50,
            "corrections_count": corr_count,
            "status_text": status_text,
        }

        onboarding_candidates: list[dict[str, Any]] = []
        if model_ver == "cold":
            cand_rows = conn.execute(
                """
                SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                       COALESCE(l.label, 'email') AS pred_label,
                       COALESCE(l.confidence, 0.8) AS pred_confidence
                FROM messages m
                LEFT JOIN labels l ON l.message_id = m.id
                WHERE m.hidden = 0
                  AND UPPER(m.folder) = 'INBOX'
                  AND m.id NOT IN (SELECT message_id FROM corrections)
                ORDER BY
                  CASE WHEN COALESCE(l.label, 'email') = 'promotion' THEN 0 ELSE 1 END ASC,
                  m.date DESC
                LIMIT 10
                """
            ).fetchall()
            for cr in cand_rows:
                pred = str(cr["pred_label"] or "email")
                onboarding_candidates.append(
                    {
                        "id": cr["id"],
                        "from_name": cr["from_name"],
                        "from_addr": cr["from_addr"],
                        "subject": cr["subject"],
                        "snippet": cr["snippet"],
                        "date": cr["date"],
                        "pred_label": pred,
                        "proposed_label": "promotion" if pred == "promotion" else pred,
                    }
                )
        return classifier_info, onboarding_candidates

    def _primary_translation_target(self) -> str:
        tr = getattr(self.runtime, "translator", None)
        if tr is not None:
            try:
                return str(tr.get_preferences().get("primary_language") or "en")
            except Exception:
                pass
        return "en"

    def get_lane(
        self,
        name: str = "inbox",
        cursor: int = 0,
        limit: int = 50,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Section 4.1, 4.8 & M19 §5: Returns lane rows (50 per page) for `inbox`, `pings`, `orders`, `promos`.
        Supports filtering by `account_id` (or unified common view when `account_id` is None / 'all').
        """
        self.passwords._check_autolock()
        eff_acct = (account_id or "").strip()
        if eff_acct.lower() == "all":
            eff_acct = ""

        if not self.passwords.unlocked:
            return {
                "unlocked": False,
                "lane": name,
                "account_id": eff_acct or "all",
                "rows": [],
                "groups": [],
                "counts": {"inbox_unread": 0, "pings": 0, "orders": 0, "promos": 0},
                "classifier": {
                    "model_version": "cold",
                    "training_labels": 0,
                    "target_labels": 50,
                    "corrections_count": 0,
                    "status_text": "classifier: learning · 0 / 50 labels",
                },
                "onboarding_candidates": [],
            }

        lane = (name or "inbox").strip().lower()
        offset = max(0, int(cursor or 0))
        page_limit = max(1, min(200, int(limit or 50)))
        acct_sql = " AND m.account_id = ? " if eff_acct else ""
        acct_params: tuple[Any, ...] = (eff_acct,) if eff_acct else ()
        target_lang = self._primary_translation_target()

        with self.db_lock:
            conn = self._ensure_connection()
            counts = self._compute_lane_counts(conn, account_id=eff_acct or None)
            classifier_info, onboarding_candidates = self._compute_classifier_and_onboarding_info(conn)

            if lane == "inbox":
                rows = conn.execute(
                    f"""
                    SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                           COALESCE(ac.label, ac.email, '') AS account_label,
                           m.thread_id, m.from_name, m.from_addr, m.subject,
                           m.snippet, m.date, m.seen, m.answered, m.flagged, m.has_attachments,
                           COALESCE(l.label, 'email') AS label,
                           COALESCE(l.confidence, 0.0) AS confidence,
                           COALESCE(a.needs_reply, 0) AS needs_reply,
                           a.due_date AS due_date,
                           COALESCE(a.ask, '') AS ask,
                           COALESCE(mt.source_lang, '') AS translation_source_lang,
                           COALESCE(mt.target_lang, '') AS translation_target_lang,
                           COALESCE(mt.subject_tr, '') AS translated_subject,
                           COALESCE(mt.snippet_tr, '') AS translated_snippet
                    FROM messages m
                    LEFT JOIN accounts ac ON ac.id = m.account_id
                    LEFT JOIN labels l ON l.message_id = m.id
                    LEFT JOIN actions a ON a.message_id = m.id
                    LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                    WHERE m.hidden = 0
                      AND UPPER(m.folder) = 'INBOX'
                      AND COALESCE(l.label, 'email') = 'email'
                      {acct_sql}
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (target_lang, *acct_params, page_limit, offset),
                ).fetchall()
                return {
                    "unlocked": True,
                    "lane": "inbox",
                    "account_id": eff_acct or "all",
                    "rows": [dict(r) for r in rows],
                    "next_cursor": offset + len(rows) if len(rows) == page_limit else None,
                    "counts": counts,
                    "classifier": classifier_info,
                    "onboarding_candidates": onboarding_candidates,
                }

            if lane == "pings":
                rows = conn.execute(
                    f"""
                    SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                           m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen,
                           COALESCE(e.value, '') AS platform,
                           COALESCE(mt.source_lang, '') AS translation_source_lang,
                           COALESCE(mt.target_lang, '') AS translation_target_lang,
                           COALESCE(mt.subject_tr, '') AS translated_subject,
                           COALESCE(mt.snippet_tr, '') AS translated_snippet
                    FROM messages m
                    LEFT JOIN accounts ac ON ac.id = m.account_id
                    JOIN labels l ON l.message_id = m.id AND l.label = 'ping'
                    LEFT JOIN extracts e ON e.message_id = m.id AND e.field = 'platform'
                    LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                    WHERE m.hidden = 0
                      {acct_sql}
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (target_lang, *acct_params, page_limit, offset),
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
                    "account_id": eff_acct or "all",
                    "rows": items,
                    "groups": list(groups_map.values()),
                    "counts": counts,
                    "classifier": classifier_info,
                    "onboarding_candidates": onboarding_candidates,
                }

            if lane == "orders":
                status_rank = {
                    "notice": 0,
                    "ordered": 1,
                    "shipped": 2,
                    "out for delivery": 3,
                    "delivered": 4,
                    "cancelled": 5,
                    "refunded": 5,
                }
                rows = conn.execute(
                    f"""
                    SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                           m.thread_id, m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen,
                           COALESCE(mt.source_lang, '') AS translation_source_lang,
                           COALESCE(mt.target_lang, '') AS translation_target_lang,
                           COALESCE(mt.subject_tr, '') AS translated_subject,
                           COALESCE(mt.snippet_tr, '') AS translated_snippet
                    FROM messages m
                    LEFT JOIN accounts ac ON ac.id = m.account_id
                    JOIN labels l ON l.message_id = m.id AND l.label = 'information'
                    LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                    WHERE m.hidden = 0
                      {acct_sql}
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (target_lang, *acct_params, page_limit, offset),
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
                    tracking_no = ext.get("tracking_number") or ""
                    tracking_url = ext.get("tracking_url") or ""
                    raw_status = (ext.get("status") or "").strip().lower()
                    merchant = ext.get("merchant") or r["from_name"] or r["from_addr"]
                    key = f"ord::{order_no.lower()}" if order_no else f"thr::{r['thread_id'] or mid}"
                    card = orders_by_key.get(key)
                    msg_status = raw_status or (
                        "ordered" if (order_no or tracking_no or tracking_url or ext.get("total")) else "notice"
                    )
                    email_entry = {
                        "id": mid,
                        "account_id": r["account_id"],
                        "account_email": r["account_email"],
                        "subject": r["subject"],
                        "date": r["date"],
                        "snippet": r["snippet"],
                        "status": msg_status,
                        "translated_subject": r["translated_subject"],
                        "translated_snippet": r["translated_snippet"],
                        "translation_source_lang": r["translation_source_lang"],
                        "translation_target_lang": r["translation_target_lang"],
                    }
                    if not card:
                        t_no = tracking_no
                        t_url = tracking_url or (self._default_tracking_url_for_number(t_no) if t_no else "")
                        orders_by_key[key] = {
                            "key": key,
                            "account_email": r["account_email"],
                            "merchant": merchant,
                            "order_number": order_no,
                            "status": msg_status,
                            "tracking_number": t_no,
                            "tracking_url": t_url,
                            "total": ext.get("total") or "",
                            "last_update": r["date"],
                            "latest_message_id": mid,
                            "emails": [email_entry],
                        }
                    else:
                        card["emails"].append(email_entry)
                        if status_rank.get(msg_status, 1) > status_rank.get(str(card["status"]).lower(), 1):
                            card["status"] = msg_status
                        if float(r["date"] or 0) > float(card["last_update"] or 0):
                            card["last_update"] = r["date"]
                            card["latest_message_id"] = mid
                        if not card["order_number"] and order_no:
                            card["order_number"] = order_no
                        if not card["tracking_number"] and ext.get("tracking_number"):
                            card["tracking_number"] = ext["tracking_number"]
                        if not card["tracking_url"] and ext.get("tracking_url"):
                            card["tracking_url"] = ext["tracking_url"]
                        if not card["tracking_url"] and card["tracking_number"]:
                            card["tracking_url"] = self._default_tracking_url_for_number(card["tracking_number"])
                        if not card["total"] and ext.get("total"):
                            card["total"] = ext["total"]

                # Merge any fresher status/tracking/total from Brain `order` entities
                brain = getattr(self.runtime, "brain", None)
                if brain is not None and not getattr(brain, "locked", False):
                    try:
                        brain_orders = [e for e in brain.list_entities() if e.get("type") == "order"]
                        for card in orders_by_key.values():
                            ord_no = str(card.get("order_number") or "").lower()
                            if not ord_no:
                                continue
                            for bo in brain_orders:
                                b_attrs = bo.get("attributes") or {}
                                b_ord = str(b_attrs.get("order_number") or "").lower()
                                if b_ord == ord_no or ord_no in str(bo.get("name") or "").lower():
                                    b_st = str(b_attrs.get("status") or "").strip().lower()
                                    if status_rank.get(b_st, 0) > status_rank.get(str(card["status"]).lower(), 0):
                                        card["status"] = b_st
                                    if not card["tracking_number"] and b_attrs.get("tracking_number"):
                                        card["tracking_number"] = str(b_attrs["tracking_number"])
                                    if not card["tracking_url"] and b_attrs.get("tracking_url"):
                                        card["tracking_url"] = str(b_attrs["tracking_url"])
                                    if not card["tracking_url"] and card["tracking_number"]:
                                        card["tracking_url"] = self._default_tracking_url_for_number(card["tracking_number"])
                                    if not card["total"] and b_attrs.get("total"):
                                        card["total"] = str(b_attrs["total"])
                    except Exception:
                        pass

                return {
                    "unlocked": True,
                    "lane": "orders",
                    "account_id": eff_acct or "all",
                    "rows": list(orders_by_key.values()),
                    "counts": counts,
                    "classifier": classifier_info,
                    "onboarding_candidates": onboarding_candidates,
                }

            if lane == "promos":
                rows = conn.execute(
                    f"""
                    SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                           m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen
                    FROM messages m
                    LEFT JOIN accounts ac ON ac.id = m.account_id
                    JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
                    WHERE m.hidden = 0
                      {acct_sql}
                    ORDER BY m.date DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*acct_params, page_limit, offset),
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
                            "account_email": r["account_email"],
                            "active_codes": [],
                            "expired_codes": [],
                            "emails": [],
                        },
                    )
                    if len(grp["emails"]) < 5:
                        grp["emails"].append(
                            {
                                "id": mid,
                                "account_email": r["account_email"],
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
                    "account_id": eff_acct or "all",
                    "rows": list(companies.values()),
                    "counts": counts,
                    "classifier": classifier_info,
                    "onboarding_candidates": onboarding_candidates,
                }

            return {
                "unlocked": True,
                "lane": lane,
                "account_id": eff_acct or "all",
                "rows": [],
                "counts": counts,
                "classifier": classifier_info,
                "onboarding_candidates": onboarding_candidates,
            }

    def _compute_lane_counts(self, conn: sqlite3.Connection, account_id: str | None = None) -> dict[str, int]:
        eff_acct = (account_id or "").strip()
        if eff_acct.lower() == "all":
            eff_acct = ""
        acct_sql = " AND m.account_id = ? " if eff_acct else ""
        acct_params: tuple[Any, ...] = (eff_acct,) if eff_acct else ()
        inbox_unread = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM messages m
            LEFT JOIN labels l ON l.message_id = m.id
            WHERE m.hidden = 0 AND UPPER(m.folder) = 'INBOX' AND m.seen = 0
              AND COALESCE(l.label, 'email') = 'email'
              {acct_sql}
            """,
            acct_params,
        ).fetchone()
        pings_c = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'ping'
            WHERE m.hidden = 0 AND m.seen = 0
              {acct_sql}
            """,
            acct_params,
        ).fetchone()
        orders_c = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'information'
            WHERE m.hidden = 0
              {acct_sql}
            """,
            acct_params,
        ).fetchone()
        promos_c = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
            WHERE m.hidden = 0
              {acct_sql}
            """,
            acct_params,
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
                "messages_count": 0,
                "latest_message_ts": 0.0,
            }
        with self.db_lock:
            conn = self._ensure_connection()
            acct_cnt = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
            labelled_cnt = conn.execute("SELECT COUNT(*) AS c FROM labels").fetchone()["c"]
            msg_row = conn.execute(
                "SELECT COUNT(*) AS c, COALESCE(MAX(date), 0) AS max_d FROM messages WHERE hidden = 0"
            ).fetchone()
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
            "messages_count": int(msg_row["c"] or 0) if msg_row else 0,
            "latest_message_ts": float(msg_row["max_d"] or 0.0) if msg_row else 0.0,
            "counts": counts,
            **pipe_status,
        }

    # ── Milestone M13: Message Reading, Search, Compose & SMTP Send Gate ──

    def _ensure_full_imap_message_fetched(self, message_id: str, force: bool = False) -> None:
        if not self.passwords.unlocked:
            return
        fetched_set: set[str] = getattr(self, "_full_fetched_ids", set())
        if not hasattr(self, "_full_fetched_ids"):
            self._full_fetched_ids = fetched_set
        if not force and message_id in fetched_set:
            return

        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT id, account_id, folder, uid, subject, snippet, body_text, has_attachments FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if not row:
                return
            has_att = int(row["has_attachments"] or 0)
            body_t = str(row["body_text"] or "")
            snip = str(row["snippet"] or "")
            subj = str(row["subject"] or "")
            uid = int(row["uid"] or 0)
            acct_id = str(row["account_id"] or "")
            folder = str(row["folder"] or "INBOX")
            acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()

        needs_full = force or (
            has_att == 0
            and (
                "\ufffc" in snip
                or "\ufffc" in body_t
                or len(body_t) < 400
                or any(
                    kw in f"{subj} {body_t}".lower()
                    for kw in ("rechnung", "invoice", "attached", "anhang", "anbei", "pdf", "receipt")
                )
            )
        )
        fetched_set.add(message_id)
        if not needs_full or acct is None or uid <= 0:
            return
        if str(acct["protocol"] or "imap").lower() != "imap":
            return

        try:
            auth_info = self._resolve_auth_for_prefix(acct["vault_prefix"], acct_email=acct["email"])
            if not auth_info["username"] or (auth_info.get("mode") != "oauth2" and not auth_info["password"]):
                return
            imap = self._open_imap_client(acct["in_host"], int(acct["in_port"]), acct["in_security"])
            try:
                self._imap_authenticate(imap, auth_info, vault_prefix=acct["vault_prefix"], acct_email=acct["email"])
                st, _ = imap.select(f'"{folder}"' if " " in folder else folder, readonly=True)
                if st == "OK":
                    st_f, f_data = imap.uid(
                        "FETCH",
                        str(uid),
                        "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER] BODY.PEEK[TEXT]<0.10000000>)",
                    )
                    if st_f == "OK" and f_data:
                        self._ingest_imap_fetched_item(
                            account_id=acct_id,
                            folder_name=folder,
                            role="inbox",
                            uid=uid,
                            fetch_data=f_data,
                        )
            finally:
                try:
                    imap.logout()
                except Exception:
                    pass
        except Exception as exc:
            self.runtime.record_error("mail_full_fetch", f"{message_id}: {exc}")

    def get_message_detail(
        self,
        message_id: str,
        *,
        fetch_remote: bool = True,
        lite: bool = False,
    ) -> dict[str, Any]:
        """
        Section 4.6 & 4.8: Returns headers, parts, labels, extracts, actions, attachments,
        and Agent rail context (sender Brain card, recent emails with sender, and order card).
        Pass `fetch_remote=False, lite=True` for fast synchronous SQLite hydration in chat.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        if fetch_remote:
            self._ensure_full_imap_message_fetched(message_id)
        with self.db_lock:
            conn = self._ensure_connection()
            msg_row = conn.execute(
                """
                SELECT m.*, COALESCE(ac.email, '') AS account_email, COALESCE(ac.label, ac.email, '') AS account_label
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
            if not msg_row:
                return {"ok": False, "error": f"Message {message_id} not found."}
            msg = dict(msg_row)

            parts_rows = conn.execute(
                "SELECT kind, text FROM parts WHERE message_id = ?",
                (message_id,),
            ).fetchall()
            parts = {r["kind"]: r["text"] for r in parts_rows}

            lbl_row = conn.execute(
                "SELECT label, confidence, source, model_version, at FROM labels WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            label_info = dict(lbl_row) if lbl_row else {"label": "email", "confidence": 0.0, "source": "rule", "model_version": "cold"}

            ext_rows = conn.execute(
                "SELECT field, value, source, confidence FROM extracts WHERE message_id = ?",
                (message_id,),
            ).fetchall()
            extracts = {r["field"]: r["value"] for r in ext_rows}

            act_row = conn.execute(
                "SELECT needs_reply, due_date, ask FROM actions WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            action_info = dict(act_row) if act_row else {"needs_reply": 0, "due_date": None, "ask": ""}

            att_rows = conn.execute(
                "SELECT filename, mime, size, part_id, saved_path FROM attachments WHERE message_id = ? ORDER BY part_id ASC",
                (message_id,),
            ).fetchall()
            attachments = [dict(r) for r in att_rows]

            from_addr = (msg.get("from_addr") or "").strip().lower()
            recent_with_sender: list[dict[str, Any]] = []
            allow_remote = False
            if not lite:
                recent_rows = conn.execute(
                    """
                    SELECT id, subject, date, snippet, seen
                    FROM messages
                    WHERE LOWER(from_addr) = ? AND id != ? AND hidden = 0
                    ORDER BY date DESC
                    LIMIT 5
                    """,
                    (from_addr, message_id),
                ).fetchall()
                recent_with_sender = [dict(r) for r in recent_rows]

                settings = self.get_mail_settings()
                allow_remote = from_addr in (settings.get("remote_images_senders") or [])

            t_target = self._primary_translation_target()
            tr_row = conn.execute(
                """
                SELECT target_lang, source_lang, subject_tr, snippet_tr, new_text_tr, html_tr, model_id, created_at
                FROM message_translations
                WHERE message_id = ? AND target_lang = ?
                """,
                (message_id, t_target),
            ).fetchone()
            translation_obj: dict[str, Any] | None = (
                {
                    "target_lang": str(tr_row["target_lang"]),
                    "source_lang": str(tr_row["source_lang"]),
                    "subject": str(tr_row["subject_tr"]),
                    "snippet": str(tr_row["snippet_tr"]),
                    "new_text": str(tr_row["new_text_tr"]),
                    "html": str(tr_row["html_tr"]),
                    "model_id": str(tr_row["model_id"]),
                }
                if tr_row
                else None
            )

        from satz_translate import detect_language

        detected_lang = (
            translation_obj["source_lang"]
            if (translation_obj and translation_obj.get("source_lang"))
            else ("en" if lite else detect_language(f"{msg.get('subject') or ''}\n{parts.get('new') or msg.get('body_text') or ''}"))
        )

        # Look up sender card in Brain (skip expensive full-entity scan on lite chat hydration)
        sender_card: dict[str, Any] | None = None
        if not lite:
            brain = getattr(self.runtime, "brain", None)
            if brain is not None and from_addr:
                for ent in brain.list_entities():
                    if ent.get("type") in ("person", "organization"):
                        ent_email = str(ent.get("attributes", {}).get("email") or "").lower()
                        ent_dom = str(ent.get("attributes", {}).get("domain") or "").lower()
                        if ent_email == from_addr or (ent_dom and from_addr.endswith(f"@{ent_dom}")):
                            sender_card = ent
                            break

        try:
            to_list = json.loads(msg.get("to_json") or "[]")
        except Exception:
            to_list = []
        try:
            cc_list = json.loads(msg.get("cc_json") or "[]")
        except Exception:
            cc_list = []

        try:
            unsub_info = self.extract_unsubscribe_info(message_id)
        except Exception:
            unsub_info = {"ok": False, "available": False, "methods": []}

        return {
            "ok": True,
            "message": {
                **msg,
                "to": to_list,
                "cc": cc_list,
                "parts": parts,
                "label": label_info["label"],
                "label_info": label_info,
                "extracts": extracts,
                "action": action_info,
                "attachments": attachments,
                "allow_remote_images": allow_remote,
                "recent_with_sender": recent_with_sender,
                "sender_card": sender_card,
                "unsubscribe": unsub_info,
                "detected_language": detected_lang,
                "translation": translation_obj,
            },
        }

    def get_sanitized_message_html(self, message_id: str) -> dict[str, Any]:
        """
        Section 4.6: Returns sanitized HTML and CSP header for `satzmail://message/<id>`.
        Plain text emails render as `<pre>` in the same scheme.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {
                "ok": False,
                "html": "<html><body><pre>[profile locked]</pre></body></html>",
                "csp": "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
            }

        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT id, from_addr, from_name, subject, body_text, has_html FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if not row:
                return {
                    "ok": False,
                    "html": "<html><body><pre>(message not found)</pre></body></html>",
                    "csp": "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
                }
            from_addr = (row["from_addr"] or "").strip().lower()
            body_text = row["body_text"] or ""
            has_html = int(row["has_html"] or 0) == 1
            settings = self.get_mail_settings()

        allow_remote = from_addr in (settings.get("remote_images_senders") or [])
        img_src = "https: data: cid:" if allow_remote else "data: cid:"
        csp = f"default-src 'none'; img-src {img_src}; style-src 'unsafe-inline'; font-src data:"

        raw_html = ""
        if has_html:
            html_file = self._current_mail_html_dir() / f"{message_id}.html"
            if html_file.exists():
                try:
                    raw_html = html_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    raw_html = ""

        base_style = (
            "<style>"
            "html,body{background:#000000 !important;color:#e8e8e8 !important;font-family:'JetBrains Mono',monospace;"
            "font-size:13px;line-height:1.5;margin:0;padding:14px;}"
            "body *,font,span,div,p,td,th,li,h1,h2,h3,h4,h5,h6{color:#e8e8e8 !important;-webkit-text-stroke-color:#e8e8e8 !important;background-color:transparent !important;}"
            "a,a *{color:#ffffff !important;text-decoration:underline !important;}"
            "pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit;color:#e8e8e8 !important;}"
            "blockquote{border-left:1px solid #333333;margin:8px 0;padding-left:10px;color:#9a9a9a !important;}"
            "</style>"
        )

        if raw_html:
            clean_body = sanitize_email_html(raw_html, allow_remote_images=allow_remote)
            visible_check = strip_html_tags(clean_body).replace("\ufffc", "").strip()
            if len(visible_check) < 8 and body_text.strip():
                escaped_txt = html_lib.escape(body_text.replace("\ufffc", "").strip())
                clean_body = f"<pre>{escaped_txt}</pre>\n{clean_body}"
            final_html = f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{base_style}</head><body>{clean_body}</body></html>"
        else:
            escaped_txt = html_lib.escape((body_text or "").replace("\ufffc", "").strip() or "(empty message)")
            final_html = f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{base_style}</head><body><pre>{escaped_txt}</pre></body></html>"

        translated_html = ""
        tr_source_lang = ""
        tr_target_lang = self._primary_translation_target()
        with self.db_lock:
            conn = self._ensure_connection()
            tr_row = conn.execute(
                "SELECT source_lang, html_tr, new_text_tr FROM message_translations WHERE message_id = ? AND target_lang = ?",
                (message_id, tr_target_lang),
            ).fetchone()
            if tr_row:
                tr_source_lang = str(tr_row["source_lang"] or "")
                translated_html = str(tr_row["html_tr"] or "")
                if not translated_html and tr_row["new_text_tr"]:
                    escaped_tr = html_lib.escape(str(tr_row["new_text_tr"]).strip())
                    translated_html = f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">{base_style}</head><body><pre>{escaped_tr}</pre></body></html>"

        return {
            "ok": True,
            "message_id": message_id,
            "from_addr": from_addr,
            "allow_remote_images": allow_remote,
            "csp": csp,
            "html": final_html,
            "translated_html": translated_html,
            "translation_source_lang": tr_source_lang,
            "translation_target_lang": tr_target_lang if translated_html else "",
        }

    def translate_message(
        self,
        message_id: str,
        *,
        target_lang: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Translates an email (`subject`, `parts.new`, and optional sanitized HTML body)
        to `target_lang` (defaults to active profile `primary_language`) via the cheapest
        model and updates `message_translations` + bilingual `messages_fts`.
        """
        if not self.passwords.unlocked:
            raise PermissionError("Unlock profile with its 6-digit PIN before translating mail.")

        translator = getattr(self.runtime, "translator", None)
        if translator is None:
            return {"ok": False, "error": "Translation service unavailable."}

        from satz_translate import detect_language, normalize_language_code

        prefs = translator.get_preferences()
        tgt = normalize_language_code(target_lang) or prefs["primary_language"]

        self._ensure_full_imap_message_fetched(message_id)
        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                """
                SELECT m.*, COALESCE(ac.email, '') AS account_email, COALESCE(l.label, 'email') AS label
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                LEFT JOIN labels l ON l.message_id = m.id
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"Message {message_id} not found."}
            msg = dict(row)
            parts_rows = conn.execute(
                "SELECT kind, text FROM parts WHERE message_id = ?",
                (message_id,),
            ).fetchall()
            parts = {r["kind"]: r["text"] for r in parts_rows}
            new_text = str(parts.get("new") or msg.get("body_text") or "").strip()
            subj = str(msg.get("subject") or "").strip()
            c_hash = hashlib.sha256(f"{tgt}|{subj}|{new_text[:5000]}".encode("utf-8")).hexdigest()[:24]

            if not force:
                existing = conn.execute(
                    "SELECT * FROM message_translations WHERE message_id = ? AND target_lang = ?",
                    (message_id, tgt),
                ).fetchone()
                if existing and existing["content_hash"] == c_hash and (existing["new_text_tr"] or existing["subject_tr"]):
                    return {
                        "ok": True,
                        "message_id": message_id,
                        "cached": True,
                        "skipped_allowed": False,
                        "translation": {
                            "target_lang": str(existing["target_lang"]),
                            "source_lang": str(existing["source_lang"]),
                            "subject": str(existing["subject_tr"]),
                            "snippet": str(existing["snippet_tr"]),
                            "new_text": str(existing["new_text_tr"]),
                            "html": str(existing["html_tr"]),
                            "model_id": str(existing["model_id"]),
                        },
                    }

        source_lang = detect_language(f"{subj}\n{new_text[:2500]}")
        if not force and translator.is_language_allowed(source_lang, prefs=prefs):
            return {
                "ok": True,
                "message_id": message_id,
                "skipped_allowed": True,
                "source_lang": source_lang,
                "target_lang": tgt,
                "translation": None,
            }

        seg_map: dict[str, str] = {}
        if subj:
            seg_map["subject"] = subj[:400]
        if new_text:
            seg_map["body"] = new_text[:5500]
        if not seg_map:
            return {"ok": False, "error": "Message contains no text to translate."}

        tr_res = translator.translate_segments(
            seg_map,
            target_lang=tgt,
            source_lang=source_lang,
            context_hint=f"email from {msg.get('from_name') or msg.get('from_addr') or ''}",
            use_cache=not force,
        )
        tr_dict = tr_res.get("translations") or {}
        subj_tr = str(tr_dict.get("subject") or subj).strip()
        body_tr = str(tr_dict.get("body") or new_text).strip()
        snip_tr = re.sub(r"\s+", " ", body_tr).strip()[:220]
        model_id = str(tr_res.get("model") or "")

        html_tr = ""
        if msg.get("has_html") and tr_dict and not tr_res.get("rate_limited"):
            try:
                html_info = self.get_sanitized_message_html(message_id)
                raw_safe_html = str(html_info.get("html") or "")
                if raw_safe_html:
                    html_tr = translator.translate_html_text_nodes(
                        raw_safe_html,
                        target_lang=tgt,
                        source_lang=source_lang,
                    )
            except Exception:
                html_tr = ""

        now = time.time()
        with self.db_lock:
            conn = self._ensure_connection()
            conn.execute(
                """
                INSERT INTO message_translations
                  (message_id, target_lang, source_lang, subject_tr, snippet_tr, new_text_tr, html_tr, model_id, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id, target_lang) DO UPDATE SET
                  source_lang = excluded.source_lang,
                  subject_tr = excluded.subject_tr,
                  snippet_tr = excluded.snippet_tr,
                  new_text_tr = excluded.new_text_tr,
                  html_tr = CASE WHEN LENGTH(excluded.html_tr) > 0 THEN excluded.html_tr ELSE message_translations.html_tr END,
                  model_id = excluded.model_id,
                  content_hash = excluded.content_hash,
                  created_at = excluded.created_at
                """,
                (message_id, tgt, source_lang, subj_tr, snip_tr, body_tr, html_tr, model_id, c_hash, now),
            )
            # Update FTS5 index with both original + translated text so queries in primary language match
            fts_subj = f"{subj}\n{subj_tr}".strip() if subj_tr and subj_tr != subj else subj
            fts_body = f"{new_text}\n{body_tr}".strip() if body_tr and body_tr != new_text else new_text
            conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (message_id,))
            conn.execute(
                "INSERT INTO messages_fts (message_id, subject, from_name, from_addr, new_text) VALUES (?, ?, ?, ?, ?)",
                (message_id, fts_subj, msg.get("from_name") or "", msg.get("from_addr") or "", fts_body),
            )
            conn.commit()

        # Enrich Knowledge store & Brain passages with translated text for email/information lanes
        if str(msg.get("label") or "email") in ("email", "information") and body_tr:
            try:
                eff_email_prof = str(msg.get("account_email") or "").strip().lower() or "mail"
                source_tag = f"mail:{message_id}"
                mail_url = f"satzmail://message/{message_id}"
                annotated_tr = f"[email profile: {eff_email_prof}] [translated {source_lang}->{tgt}]\n{body_tr}\n\n[original]\n{new_text[:1500]}"
                with self.runtime.store_lock:
                    self.runtime.store.db.execute(
                        """
                        INSERT OR REPLACE INTO satz_sources
                        (source_id, conversation_id, url, domain, title, text, capture_mode, updated_at)
                        VALUES (?, 'mail', ?, 'mail', ?, ?, 'mail', ?)
                        """,
                        (source_tag, mail_url, f"[{eff_email_prof}] {subj_tr or subj}", annotated_tr[:8000], now),
                    )
                    try:
                        from src.planck3.util import norm_text

                        self.runtime.store.db.execute(
                            "INSERT OR IGNORE INTO satz_conv_passages (conversation_id, text_norm, url) VALUES ('mail', ?, ?)",
                            (norm_text(f"{subj_tr}\n{body_tr[:3600]}"), mail_url),
                        )
                    except Exception:
                        pass
                    self.runtime.store.db.commit()
            except Exception:
                pass

        return {
            "ok": True,
            "message_id": message_id,
            "cached": False,
            "skipped_allowed": False,
            "translation": {
                "target_lang": tgt,
                "source_lang": source_lang,
                "subject": subj_tr,
                "snippet": snip_tr,
                "new_text": body_tr,
                "html": html_tr,
                "model_id": model_id,
            },
        }

    def open_message(self, message_id: str) -> dict[str, Any]:
        """
        Section 4.4 & 4.8: Marks message read locally (`seen = 1`) and sets `\\Seen` on the
        IMAP server if `mark_read_on_server` is enabled (default on).
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT id, account_id, folder, uid, seen FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "Message not found."}
            conn.execute("UPDATE messages SET seen = 1 WHERE id = ?", (message_id,))
            conn.commit()
            acct_id = row["account_id"]
            folder = row["folder"]
            uid = int(row["uid"] or 0)
            acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
            settings = self.get_mail_settings()

        server_marked = False
        if (
            settings.get("mark_read_on_server", True)
            and acct is not None
            and str(acct["protocol"] or "imap").lower() == "imap"
            and uid > 0
        ):
            try:
                auth_info = self._resolve_auth_for_prefix(acct["vault_prefix"], acct_email=acct["email"])
                if auth_info["username"] and (auth_info.get("mode") == "oauth2" or auth_info["password"]):
                    imap = self._open_imap_client(acct["in_host"], int(acct["in_port"]), acct["in_security"])
                    try:
                        self._imap_authenticate(imap, auth_info, vault_prefix=acct["vault_prefix"], acct_email=acct["email"])
                        st, _ = imap.select(f'"{folder}"' if " " in folder else folder, readonly=False)
                        if st == "OK":
                            imap.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Seen)")
                            server_marked = True
                    finally:
                        try:
                            imap.logout()
                        except Exception:
                            pass
            except Exception as exc:
                self.runtime.record_error("mail_open_seen", f"{message_id}: {exc}")

        return {"ok": True, "message_id": message_id, "seen": 1, "server_marked": server_marked}

    def hide_message(self, message_id: str) -> dict[str, Any]:
        """
        Section 4.4 & 4.8: Local archive (`hidden = 1`). Never deletes or moves on the server.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        with self.db_lock:
            conn = self._ensure_connection()
            conn.execute("UPDATE messages SET hidden = 1 WHERE id = ?", (message_id,))
            conn.commit()
        return {"ok": True, "message_id": message_id, "hidden": 1}

    def save_attachment_to_downloads(self, message_id: str, part_id: str) -> dict[str, Any]:
        """
        Section 4.6: Downloads attachment part to the user's `Downloads` folder.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT filename, saved_path FROM attachments WHERE message_id = ? AND part_id = ?",
                (message_id, str(part_id)),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "Attachment not found."}
            src_path = Path(row["saved_path"])
            fname = row["filename"] or f"attachment-{part_id}"

        if not src_path.exists():
            return {"ok": False, "error": "Attachment file missing on disk."}

        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        dest_path = downloads_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", fname)
        try:
            dest_path.write_bytes(src_path.read_bytes())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "saved_to": str(dest_path), "filename": fname}

    def get_attachment_data(self, message_id: str, part_id: str) -> dict[str, Any]:
        """
        Returns base64 data URL and metadata for inline preview of an email attachment
        (PDF, image, text) inside the Email tab or inside Chat.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        self._ensure_full_imap_message_fetched(message_id)
        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT filename, mime, size, part_id, saved_path FROM attachments WHERE message_id = ? AND part_id = ?",
                (message_id, str(part_id)),
            ).fetchone()
            if not row and not part_id:
                row = conn.execute(
                    "SELECT filename, mime, size, part_id, saved_path FROM attachments WHERE message_id = ? ORDER BY part_id ASC LIMIT 1",
                    (message_id,),
                ).fetchone()
            if not row:
                return {"ok": False, "error": "Attachment not found."}
            src_path = Path(row["saved_path"])
            fname = str(row["filename"] or f"attachment-{row['part_id']}")
            mime = str(row["mime"] or "application/octet-stream").lower()
            size = int(row["size"] or 0)

        if not src_path.exists():
            return {"ok": False, "error": "Attachment file missing on disk."}

        if mime == "application/octet-stream":
            if fname.lower().endswith(".pdf"):
                mime = "application/pdf"
            elif fname.lower().endswith(".png"):
                mime = "image/png"
            elif fname.lower().endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"

        raw_bytes = src_path.read_bytes()
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        return {
            "ok": True,
            "message_id": message_id,
            "part_id": str(row["part_id"]),
            "filename": fname,
            "mime": mime,
            "size": size or len(raw_bytes),
            "data_url": f"data:{mime};base64,{b64}",
            "saved_path": str(src_path),
        }

    def search_messages(
        self,
        query: str = "",
        limit: int = 50,
        account_id: str | None = None,
        *,
        lane: str = "",
        sender: str = "",
        days: float | int | None = None,
    ) -> dict[str, Any]:
        """
        Section 4.8 & Tool Harness: FTS5 search over `messages_fts` (`subject`, `from_name`,
        `from_addr`, `new_text`) with optional `account_id`, `lane`, `sender`, and `days` filters.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "unlocked": False, "rows": []}
        q = (query or "").strip()
        lane_l = (lane or "").strip().lower()
        sender_q = (sender or "").strip().lower()
        days_val: float | None = None
        if days is not None and str(days).strip() != "":
            try:
                days_f = float(days)
                if days_f > 0:
                    days_val = days_f
            except (TypeError, ValueError):
                days_val = None

        if not q and not lane_l and not sender_q and days_val is None:
            return {"ok": True, "unlocked": True, "rows": []}
        beh = getattr(self.runtime, "behavior", None)
        if q and beh is not None:
            beh.log_event("mail_search", query=q)

        eff_acct = (account_id or "").strip()
        if eff_acct.lower() == "all":
            eff_acct = ""

        where_parts = ["m.hidden = 0"]
        filter_params: list[Any] = []
        if eff_acct:
            where_parts.append("m.account_id = ?")
            filter_params.append(eff_acct)

        if lane_l and lane_l != "all":
            if lane_l in ("inbox", "email"):
                where_parts.append("COALESCE(l.label, 'email') = 'email'")
                if lane_l == "inbox":
                    where_parts.append("UPPER(m.folder) = 'INBOX'")
            elif lane_l in ("pings", "ping"):
                where_parts.append("l.label = 'ping'")
            elif lane_l in ("orders", "order", "information"):
                where_parts.append("l.label = 'information'")
            elif lane_l in ("promos", "promo", "promotion"):
                where_parts.append("l.label = 'promotion'")

        if sender_q:
            sender_pat = f"%{sender_q}%"
            where_parts.append("(LOWER(m.from_addr) LIKE ? OR LOWER(m.from_name) LIKE ?)")
            filter_params.extend([sender_pat, sender_pat])

        if days_val is not None:
            cutoff_ts = time.time() - days_val * 86400.0
            where_parts.append("m.date >= ?")
            filter_params.append(cutoff_ts)

        where_sql = " AND ".join(where_parts)
        lim = max(1, min(100, int(limit or 50)))
        t_target = self._primary_translation_target()

        select_cols = (
            "SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email, "
            "COALESCE(ac.label, '') AS account_label, "
            "m.thread_id, m.from_name, m.from_addr, m.subject, m.snippet, m.date, "
            "m.seen, m.has_attachments, COALESCE(l.label, 'email') AS label, "
            "COALESCE(a.needs_reply, 0) AS needs_reply, COALESCE(a.ask, '') AS ask, a.due_date AS due_date, "
            "COALESCE(mt.source_lang, '') AS translation_source_lang, "
            "COALESCE(mt.target_lang, '') AS translation_target_lang, "
            "COALESCE(mt.subject_tr, '') AS translated_subject, "
            "COALESCE(mt.snippet_tr, '') AS translated_snippet "
        )
        joins_sql = (
            "LEFT JOIN accounts ac ON ac.id = m.account_id "
            "LEFT JOIN labels l ON l.message_id = m.id "
            "LEFT JOIN actions a ON a.message_id = m.id "
            "LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ? "
        )

        with self.db_lock:
            conn = self._ensure_connection()
            if not q:
                rows = conn.execute(
                    f"{select_cols} FROM messages m {joins_sql} "
                    f"WHERE {where_sql} ORDER BY m.date DESC LIMIT ?",
                    (t_target, *filter_params, lim),
                ).fetchall()
            else:
                tokens = [re.sub(r'[^A-Za-z0-9@._äöüÄÖÜß-]+', "", t) for t in q.split()]
                tokens = [t for t in tokens if t]
                if not tokens:
                    return {"ok": True, "unlocked": True, "rows": []}
                fts_expr = " AND ".join(f'"{t}"*' for t in tokens)
                rows = []
                try:
                    rows = conn.execute(
                        f"{select_cols} FROM messages_fts f "
                        f"JOIN messages m ON m.id = f.message_id {joins_sql} "
                        f"WHERE messages_fts MATCH ? AND {where_sql} "
                        f"ORDER BY m.date DESC LIMIT ?",
                        (t_target, fts_expr, *filter_params, lim),
                    ).fetchall()
                except Exception:
                    rows = []
                if not rows and 2 <= len(tokens) <= 6:
                    fts_or = " OR ".join(f'"{t}"*' for t in tokens)
                    try:
                        rows = conn.execute(
                            f"{select_cols} FROM messages_fts f "
                            f"JOIN messages m ON m.id = f.message_id {joins_sql} "
                            f"WHERE messages_fts MATCH ? AND {where_sql} "
                            f"ORDER BY m.date DESC LIMIT ?",
                            (t_target, fts_or, *filter_params, lim),
                        ).fetchall()
                    except Exception:
                        rows = []
                if not rows and len(q) <= 48:
                    like_pat = f"%{q}%"
                    rows = conn.execute(
                        f"{select_cols} FROM messages m {joins_sql} "
                        f"WHERE {where_sql} AND (m.subject LIKE ? OR m.from_name LIKE ? OR m.from_addr LIKE ? OR m.body_text LIKE ? OR COALESCE(mt.subject_tr, '') LIKE ? OR COALESCE(mt.new_text_tr, '') LIKE ?) "
                        f"ORDER BY m.date DESC LIMIT ?",
                        (t_target, *filter_params, like_pat, like_pat, like_pat, like_pat, like_pat, like_pat, lim),
                    ).fetchall()
        return {"ok": True, "unlocked": True, "query": q, "rows": [dict(r) for r in rows]}

    def get_compact_mail_contexts(
        self,
        message_ids: list[str],
        *,
        max_chars: int = 900,
    ) -> dict[str, dict[str, Any]]:
        """
        Batch-fetches local SQLite mail bodies, actions, and extracts for up to 12 messages
        in one lock acquisition (zero IMAP fetches, zero Brain scans) for 1-hop chat tool hydration.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {}
        clean_ids: list[str] = []
        seen: set[str] = set()
        for raw_id in message_ids or []:
            mid = str(raw_id or "").strip()
            if mid.startswith("mail:"):
                mid = mid.split("mail:", 1)[1].strip()
            elif mid.startswith("satzmail://message/"):
                mid = mid.split("satzmail://message/", 1)[1].split("/")[0].strip()
            if mid and mid not in seen:
                seen.add(mid)
                clean_ids.append(mid)
            if len(clean_ids) >= 12:
                break
        if not clean_ids:
            return {}

        from satz_brain import neutralize_brain_directives_in_source

        placeholders = ",".join("?" for _ in clean_ids)
        t_target = self._primary_translation_target()
        with self.db_lock:
            conn = self._ensure_connection()
            msg_rows = conn.execute(
                f"""
                SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                       COALESCE(ac.label, '') AS account_label,
                       m.from_name, m.from_addr, m.to_json, m.subject, m.date,
                       m.snippet, m.body_text, m.list_unsubscribe,
                       COALESCE(l.label, 'email') AS label,
                       COALESCE(a.needs_reply, 0) AS needs_reply,
                       COALESCE(a.ask, '') AS ask,
                       a.due_date AS due_date,
                       COALESCE(mt.new_text_tr, '') AS new_text_tr
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                LEFT JOIN labels l ON l.message_id = m.id
                LEFT JOIN actions a ON a.message_id = m.id
                LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                WHERE m.id IN ({placeholders})
                """,
                (t_target, *clean_ids),
            ).fetchall()
            part_rows = conn.execute(
                f"SELECT message_id, kind, text FROM parts WHERE message_id IN ({placeholders})",
                clean_ids,
            ).fetchall()
            ext_rows = conn.execute(
                f"SELECT message_id, field, value FROM extracts WHERE message_id IN ({placeholders})",
                clean_ids,
            ).fetchall()

        parts_by_mid: dict[str, dict[str, str]] = {}
        for pr in part_rows:
            parts_by_mid.setdefault(str(pr["message_id"]), {})[str(pr["kind"])] = str(pr["text"] or "")
        ext_by_mid: dict[str, dict[str, str]] = {}
        for er in ext_rows:
            ext_by_mid.setdefault(str(er["message_id"]), {})[str(er["field"])] = str(er["value"] or "")

        out: dict[str, dict[str, Any]] = {}
        cap = max(250, min(4000, int(max_chars or 900)))
        for mr in msg_rows:
            mid = str(mr["id"])
            p_map = parts_by_mid.get(mid, {})
            new_t = (p_map.get("new") or str(mr["body_text"] or "") or str(mr["snippet"] or "")).strip()
            quote_t = (p_map.get("quote") or "").strip()
            body_raw = new_t
            if quote_t and len(body_raw) < 900:
                body_raw = f"{body_raw}\n\n{quote_t}".strip()
            tr_new = str(mr["new_text_tr"] or "").strip()
            if tr_new and tr_new != new_t:
                body_raw = f"{tr_new}\n\n[Original]\n{body_raw}".strip()
            safe_body = neutralize_brain_directives_in_source(body_raw).strip()
            from_str = str(mr["from_name"] or mr["from_addr"] or "unknown").strip()
            from_addr = str(mr["from_addr"] or "").strip()
            subj = str(mr["subject"] or "(no subject)").strip()
            recv_date = mr["date"] or ""
            try:
                to_addrs = ", ".join(str(x) for x in json.loads(mr["to_json"] or "[]") if x)
            except Exception:
                to_addrs = ""
            full_formatted = (
                f"From: {from_str} <{from_addr}>\n"
                f"To: {to_addrs}\n"
                f"Account: {mr['account_label'] or mr['account_email'] or ''}\n"
                f"Subject: {subj}\n"
                f"Date: {recv_date}\n"
                f"Label: {mr['label'] or ''}\n\n"
                f"{safe_body[:16000]}"
            ).strip()
            out[mid] = {
                "id": mid,
                "from_name": from_str,
                "from_addr": from_addr,
                "to_addrs": to_addrs,
                "account_label": str(mr["account_label"] or ""),
                "subject": subj,
                "date": recv_date,
                "label": str(mr["label"] or "email"),
                "action": {
                    "needs_reply": bool(mr["needs_reply"]),
                    "ask": str(mr["ask"] or ""),
                    "due_date": mr["due_date"],
                },
                "extracts": ext_by_mid.get(mid, {}),
                "unsubscribe_available": bool(str(mr["list_unsubscribe"] or "").strip()),
                "excerpt": safe_body[:cap],
                "has_more": len(safe_body) > cap,
                "full_formatted": full_formatted,
            }
        return out

    def query_mail_for_chat_context(self, user_msg: str, *, limit: int = 6) -> list[dict[str, Any]]:
        """
        Intent- & account-aware Mail pre-retrieval for chat turns:
        - Filters by mentioned account label (`work`, `personal`) or domain if unambiguous.
        - Routes action/unread/summary/order prompts to indexed SQLite queries instead of failing full-sentence FTS `AND`.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return []
        q_raw = (user_msg or "").strip()
        if not q_raw:
            return []
        low = q_raw.lower()
        lim = max(1, min(12, int(limit or 6)))

        acct_id = ""
        with self.db_lock:
            conn = self._ensure_connection()
            acct_rows = conn.execute("SELECT id, label, email FROM accounts").fetchall()
            matched_accts: list[str] = []
            for ac in acct_rows:
                lbl = str(ac["label"] or "").strip().lower()
                em = str(ac["email"] or "").strip().lower()
                dom_head = em.split("@", 1)[1].split(".", 1)[0] if "@" in em else ""
                if (lbl and re.search(rf"\b{re.escape(lbl)}\b", low)) or (em and em in low) or (
                    dom_head and len(dom_head) >= 4 and dom_head not in {"gmail", "outlook", "yahoo", "icloud", "proton"} and re.search(rf"\b{re.escape(dom_head)}\b", low)
                ):
                    matched_accts.append(str(ac["id"]))
            if not matched_accts and len(acct_rows) > 1:
                freemail_domains = {
                    "gmail.com", "googlemail.com", "gmx.net", "gmx.de", "web.de",
                    "outlook.com", "hotmail.com", "live.com", "yahoo.com", "yahoo.de",
                    "icloud.com", "me.com", "proton.me", "protonmail.com", "aol.com",
                }
                if re.search(r"\b(work|office|corporate|business)\b", low):
                    corp_ids = [
                        str(ac["id"])
                        for ac in acct_rows
                        if "@" in str(ac["email"] or "")
                        and str(ac["email"]).split("@", 1)[1].strip().lower() not in freemail_domains
                    ]
                    if len(corp_ids) == 1:
                        matched_accts = corp_ids
                elif re.search(r"\b(personal|private)\b", low):
                    pers_ids = [
                        str(ac["id"])
                        for ac in acct_rows
                        if "@" in str(ac["email"] or "")
                        and str(ac["email"]).split("@", 1)[1].strip().lower() in freemail_domains
                    ]
                    if len(pers_ids) == 1:
                        matched_accts = pers_ids
            if len(matched_accts) == 1:
                acct_id = matched_accts[0]

        wants_actions = bool(
            re.search(
                r"\b(action\s+items?|to-?do|tasks?|needs?\s+reply|reply\s+to|respond|follow[\s-]?up|urgent|important|deal\s+with|pending|unread|inbox)\b",
                low,
            )
        )
        wants_orders = bool(
            re.search(
                r"\b(orders?|deliver(?:y|ies)|package|tracking|shipp(?:ed|ing)|invoice|invoices|receipt|rechnung|bestellung|paket)\b",
                low,
            )
        )
        wants_recent = bool(re.search(r"\b(latest|newest|recent|today|this\s+week|morning|yesterday)\b", low))

        stopwords = {
            "give", "get", "find", "show", "tell", "check", "read", "summarize", "summary",
            "latest", "newest", "recent", "current", "today", "yesterday", "week",
            "work", "personal", "home", "email", "emails", "mail", "mails", "inbox",
            "message", "messages", "thread", "threads", "action", "actions", "item", "items",
            "task", "tasks", "deal", "with", "from", "about", "what", "when", "where",
            "which", "who", "whom", "whose", "have", "has", "had", "need", "needs",
            "does", "did", "are", "was", "were", "your", "mine", "that", "this", "these", "those", "please",
        }
        acct_words: set[str] = set()
        for ac in acct_rows:
            for tok in re.findall(r"[a-z0-9]{3,}", str(ac["label"] or "").lower()):
                acct_words.add(tok)
        raw_tokens = re.findall(r"[A-Za-z0-9@._äöüÄÖÜß-]{3,}", q_raw)
        content_tokens = [
            tok for tok in raw_tokens if tok.lower() not in stopwords and tok.lower() not in acct_words
        ]

        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def _append_rows(rows_in: list[dict[str, Any]]) -> None:
            for r in rows_in:
                rid = str(r.get("id") or "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    candidates.append(r)
                    if len(candidates) >= lim:
                        break

        if content_tokens:
            kw_query = " ".join(content_tokens[:4])
            res_kw = self.search_messages(kw_query, limit=lim, account_id=acct_id or None)
            _append_rows(list(res_kw.get("rows") or []))
            if not candidates and acct_id:
                res_all = self.search_messages(kw_query, limit=lim)
                _append_rows(list(res_all.get("rows") or []))

        if wants_orders and not candidates:
            ord_res = self.search_messages("", limit=lim, account_id=acct_id or None, lane="orders", days=30)
            _append_rows(list(ord_res.get("rows") or []))

        if len(candidates) < lim and (wants_actions or wants_recent or not content_tokens):
            acct_sql = " AND m.account_id = ? " if acct_id else ""
            acct_params: tuple[Any, ...] = (acct_id,) if acct_id else ()
            cutoff_ts = time.time() - 21 * 86400.0
            with self.db_lock:
                conn = self._ensure_connection()
                act_rows = conn.execute(
                    f"""
                    SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                           COALESCE(ac.label, '') AS account_label,
                           m.thread_id, m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                           m.seen, m.has_attachments, COALESCE(l.label, 'email') AS label,
                           COALESCE(a.needs_reply, 0) AS needs_reply, COALESCE(a.ask, '') AS ask, a.due_date AS due_date
                    FROM messages m
                    LEFT JOIN accounts ac ON ac.id = m.account_id
                    LEFT JOIN labels l ON l.message_id = m.id
                    LEFT JOIN actions a ON a.message_id = m.id
                    WHERE m.hidden = 0
                      AND UPPER(m.folder) = 'INBOX'
                      AND COALESCE(l.label, 'email') = 'email'
                      AND m.date >= ?
                      {acct_sql}
                    ORDER BY COALESCE(a.needs_reply, 0) DESC,
                             (CASE WHEN COALESCE(a.ask, '') != '' THEN 1 ELSE 0 END) DESC,
                             m.seen ASC,
                             m.date DESC
                    LIMIT ?
                    """,
                    (cutoff_ts, *acct_params, lim),
                ).fetchall()
            _append_rows([dict(r) for r in act_rows])
            if not candidates and acct_id:
                with self.db_lock:
                    conn = self._ensure_connection()
                    fallback_rows = conn.execute(
                        """
                        SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                               COALESCE(ac.label, '') AS account_label,
                               m.thread_id, m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                               m.seen, m.has_attachments, COALESCE(l.label, 'email') AS label,
                               COALESCE(a.needs_reply, 0) AS needs_reply, COALESCE(a.ask, '') AS ask, a.due_date AS due_date
                        FROM messages m
                        LEFT JOIN accounts ac ON ac.id = m.account_id
                        LEFT JOIN labels l ON l.message_id = m.id
                        LEFT JOIN actions a ON a.message_id = m.id
                        WHERE m.hidden = 0 AND UPPER(m.folder) = 'INBOX' AND COALESCE(l.label, 'email') = 'email'
                        ORDER BY COALESCE(a.needs_reply, 0) DESC, m.date DESC
                        LIMIT ?
                        """,
                        (lim,),
                    ).fetchall()
                _append_rows([dict(r) for r in fallback_rows])
        return candidates[:lim]

    def draft_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Section 4.7: Selected local or cloud AI model drafts an email / reply into the compose body.
        The LLM NEVER sends and has no send path; this only returns draft text (never creates queued outbox rows).
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        message_id = str(payload.get("message_id") or "").strip()
        instructions = str(payload.get("instructions") or payload.get("prompt") or "").strip()
        current_body = str(payload.get("current_body") or "").strip()
        subject = str(payload.get("subject") or "").strip()
        to_addr = str(payload.get("to") or "").strip()
        cc_addr = str(payload.get("cc") or "").strip()
        requested_model = str(payload.get("model") or "").strip()
        structured = bool(payload.get("structured"))
        quoted_context = ""

        if message_id:
            detail = self.get_message_detail(message_id)
            if detail.get("ok"):
                m = detail["message"]
                subject = subject or (
                    m["subject"] if str(m["subject"]).lower().startswith("re:") else f"Re: {m['subject']}"
                )
                to_addr = to_addr or m["from_addr"]
                new_part = m.get("parts", {}).get("new") or m.get("body_text") or ""
                dt_str = datetime.datetime.fromtimestamp(
                    float(m.get("date") or time.time()), tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC")
                sender_disp = m.get("from_name") or m.get("from_addr") or "Sender"
                quoted_Lines = "\n".join(f"> {ln}" for ln in new_part.splitlines())
                quoted_context = f"\n\nOn {dt_str}, {sender_disp} wrote:\n{quoted_Lines}"

        if not to_addr and instructions:
            email_match = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", instructions)
            if email_match:
                to_addr = ", ".join(dict.fromkeys(email_match))

        if not to_addr and instructions:
            # Resolve contact email from recent local messages if user named a person (e.g. "email Alice")
            name_m = re.search(
                r"\b(?:to|email|write(?:\s+to)?|reply\s+to|message)\s+([A-Z][A-Za-z0-9._-]+(?:\s+[A-Z][A-Za-z0-9._-]+)?)",
                instructions,
            )
            if name_m:
                cand_name = name_m.group(1).strip()
                try:
                    with self.db_lock:
                        conn = self._ensure_connection()
                        row = conn.execute(
                            "SELECT from_addr FROM messages WHERE from_name LIKE ? OR from_addr LIKE ? ORDER BY date DESC LIMIT 1",
                            (f"%{cand_name}%", f"%{cand_name}%"),
                        ).fetchone()
                        if row and row["from_addr"]:
                            to_addr = str(row["from_addr"]).strip()
                except Exception:
                    pass

        default_cfg_model = ""
        try:
            cfg = self.runtime.get_model_config() if hasattr(self.runtime, "get_model_config") else {}
            default_cfg_model = str((cfg.get("roles") or {}).get("chat") or "").strip()
        except Exception:
            default_cfg_model = ""
        chosen_model = requested_model or default_cfg_model or "gemma-4-e4b"
        if chosen_model in ("hertz (reader)", "planck (reader)", "planck3 (web)"):
            chosen_model = "gemma-4-e4b"

        is_cloud = (
            hasattr(self.runtime, "_parse_cloud_model_id")
            and self.runtime._parse_cloud_model_id(chosen_model) is not None
        )
        can_run_local_gemma = (
            getattr(self.runtime, "gemma_model", None) is not None
            or (
                hasattr(self.runtime, "_gemma_dir")
                and self.runtime._gemma_dir().exists()
            )
        )

        style_ctx = self._get_learned_style_context(to_addr=to_addr, quoted_context=quoted_context)
        style_prompt_block = style_ctx.get("prompt_block") or ""

        draft_body = ""
        if is_cloud or can_run_local_gemma:
            try:
                system_prompt = (
                    "You draft concise, clear, natural plain-text emails for the user. "
                    "Never invent facts, dates, or commitments not stated in the user prompt or quoted thread."
                )
                if style_prompt_block:
                    system_prompt = f"{system_prompt}\n\n{style_prompt_block}"
                if structured and (not to_addr or not subject):
                    user_prompt = (
                        f"Draft a plain-text email from the request below.\n"
                        f"Return ONLY valid JSON with keys: \"to\" (string), \"subject\" (string), \"body\" (plain text string).\n"
                        f"Known recipient: {to_addr}\n"
                        f"Known subject: {subject}\n"
                        f"Request / instructions: {instructions or 'Write a helpful email.'}\n"
                        + (f"{style_prompt_block}\n" if style_prompt_block else "")
                        + (f"Existing draft body to revise:\n{current_body[:2000]}\n" if current_body else "")
                        + (f"Original message:\n{quoted_context[:1500]}\n" if quoted_context else "")
                    )
                else:
                    user_prompt = (
                        f"Write a concise, plain-text email body (no Subject header line unless asked).\n"
                        f"Recipient: {to_addr or '(unspecified)'}\n"
                        f"Cc: {cc_addr}\n"
                        f"Subject: {subject or '(unspecified)'}\n"
                        f"Instructions: {instructions or 'Write a helpful, clear email.'}\n"
                        + (f"{style_prompt_block}\n" if style_prompt_block else "")
                        + (f"Existing draft body to revise:\n{current_body[:2000]}\n" if current_body else "")
                        + (f"Original message:\n{quoted_context[:1500]}\n" if quoted_context else "")
                        + "Email body only:"
                    )
                raw = self.runtime._complete_role_prompt(
                    chosen_model,
                    system_prompt,
                    user_prompt,
                    temperature=0.25,
                    max_tokens=500,
                )
                if structured and (not to_addr or not subject):
                    jm = re.search(r"\{.*\}", raw or "", re.S)
                    if jm:
                        parsed = json.loads(jm.group(0))
                        if not to_addr and parsed.get("to"):
                            to_addr = str(parsed["to"]).strip()
                        if not subject and parsed.get("subject"):
                            subject = str(parsed["subject"]).strip()
                        if parsed.get("body"):
                            draft_body = str(parsed["body"]).strip()
                if not draft_body:
                    draft_body = (raw or "").strip()
                    if draft_body.startswith("```"):
                        draft_body = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", draft_body, flags=re.S).strip()
            except Exception as exc:
                self.runtime.record_error("mail_draft", exc)

        if not subject and instructions:
            about_m = re.search(r"\b(?:about|regarding|re:|subject[:\s]+)\s+(.+)$", instructions, re.I)
            if about_m:
                subject = about_m.group(1).strip().rstrip(".")[:80]
                subject = subject[:1].upper() + subject[1:] if subject else ""

        if not draft_body:
            if current_body:
                draft_body = current_body
            else:
                pref_lang = str(style_ctx.get("preferred_lang") or "en")
                learned_greet = str(style_ctx.get("preferred_greeting") or "")
                learned_sign = str(style_ctx.get("preferred_signoff") or "")
                default_greet = "Hallo," if pref_lang == "de" else "Hi,"
                default_sign = "Beste Grüße,\n" if pref_lang == "de" else "Best,\n"
                if learned_greet == "<none>":
                    greet_line = ""
                elif learned_greet:
                    rcpt_first = ""
                    if to_addr:
                        rcpt_local = to_addr.split("@", 1)[0].split("<")[-1].strip()
                        rcpt_token = re.split(r"[._\-\s]+", rcpt_local)[0] if rcpt_local else ""
                        if rcpt_token and rcpt_token.isalpha() and len(rcpt_token) >= 2:
                            rcpt_first = rcpt_token.capitalize()
                    greet_line = (
                        learned_greet.replace("<Name>", rcpt_first) if rcpt_first else learned_greet.replace(" <Name>", "")
                    ) + "\n\n"
                else:
                    greet_line = f"{default_greet}\n\n"
                sign_line = "" if learned_sign == "<none>" else f"\n\n{learned_sign or default_sign}"
                core_msg = (
                    instructions
                    if instructions
                    else (
                        "Vielen Dank für die Nachricht. Ich melde mich in Kürze."
                        if pref_lang == "de"
                        else "Thanks for your email. I will follow up shortly."
                    )
                )
                draft_body = f"{greet_line}{core_msg}{sign_line}".strip()
                if not sign_line.endswith("\n") and sign_line:
                    draft_body += "\n"

        clean_draft_for_log = _strip_quoted_reply(draft_body)
        draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        try:
            now_ts = time.time()
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute(
                    """
                    INSERT INTO ai_drafts (
                        id, account_id, reply_to_message_id, to_addr, subject, draft_body, model, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft_id,
                        str(payload.get("account_id") or ""),
                        message_id,
                        to_addr,
                        subject,
                        clean_draft_for_log,
                        chosen_model,
                        now_ts,
                    ),
                )
                conn.commit()
        except Exception:
            pass

        full_body = (
            f"{draft_body}{quoted_context}"
            if quoted_context and quoted_context.strip() not in draft_body
            else draft_body
        )
        return {
            "ok": True,
            "draft_id": draft_id,
            "to": to_addr,
            "cc": cc_addr,
            "subject": subject,
            "body": full_body,
            "model": chosen_model,
            "status": "draft",
            "style_applied": bool(style_ctx.get("applied")),
            "style_rules_summary": style_ctx.get("summary") or "",
        }

    def prepare_send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Section 4.7 Send Gate Step 1:
        `POST /mail/send/prepare` creates an `outbox` row in `confirm` status, checks which
        recipients are `new` (never written to or received from), generates a single-use
        `confirm_token` expiring in 2 minutes (120s), and returns the confirm line summary.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        account_id = str(payload.get("account_id") or "").strip()
        raw_to = payload.get("to") or []
        raw_cc = payload.get("cc") or []
        raw_bcc = payload.get("bcc") or []
        if isinstance(raw_to, str):
            to_list = [x.strip() for x in raw_to.split(",") if x.strip()]
        else:
            to_list = [str(x).strip() for x in raw_to if str(x).strip()]
        if isinstance(raw_cc, str):
            cc_list = [x.strip() for x in raw_cc.split(",") if x.strip()]
        else:
            cc_list = [str(x).strip() for x in raw_cc if str(x).strip()]
        if isinstance(raw_bcc, str):
            bcc_list = [x.strip() for x in raw_bcc.split(",") if x.strip()]
        else:
            bcc_list = [str(x).strip() for x in raw_bcc if str(x).strip()]

        if not to_list:
            return {"ok": False, "error": "At least one 'To' recipient is required."}

        subject = str(payload.get("subject") or "(no subject)").strip()
        body = str(payload.get("body") or "")
        in_reply_to = str(payload.get("in_reply_to") or "").strip()
        references = str(payload.get("references") or "").strip()
        reply_to_message_id = str(payload.get("reply_to_message_id") or "").strip()
        ai_draft_id = str(payload.get("ai_draft_id") or "").strip()

        with self.db_lock:
            conn = self._ensure_connection()
            if account_id:
                acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            else:
                acct = conn.execute("SELECT * FROM accounts ORDER BY rowid ASC LIMIT 1").fetchone()
            if not acct:
                return {"ok": False, "error": "No mail account configured."}
            account_id = acct["id"]
            from_email = acct["email"]

            if not ai_draft_id:
                cutoff_ts = time.time() - 48 * 3600.0
                if reply_to_message_id:
                    d_row = conn.execute(
                        "SELECT id FROM ai_drafts WHERE reply_to_message_id = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
                        (reply_to_message_id, cutoff_ts),
                    ).fetchone()
                    if d_row:
                        ai_draft_id = str(d_row["id"])
                if not ai_draft_id and to_list:
                    prim_addr, _ = _extract_email_and_domain(to_list[0])
                    if prim_addr:
                        d_row = conn.execute(
                            "SELECT id FROM ai_drafts WHERE LOWER(to_addr) LIKE ? AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
                            (f"%{prim_addr}%", cutoff_ts),
                        ).fetchone()
                        if d_row:
                            ai_draft_id = str(d_row["id"])

            if reply_to_message_id and not in_reply_to:
                orig = conn.execute(
                    'SELECT message_id, "references" FROM messages WHERE id = ?',
                    (reply_to_message_id,),
                ).fetchone()
                if orig and orig["message_id"]:
                    in_reply_to = orig["message_id"]
                    prev_refs = (orig["references"] or "").strip()
                    references = f"{prev_refs} {in_reply_to}".strip()

            # Section 5 (M19): `[new]` badge when the recipient has never received mail from this account
            new_recipients: list[str] = []
            from_low = (from_email or "").strip().lower()
            for rcpt in to_list + cc_list + bcc_list:
                rcpt_m = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)", rcpt)
                rcpt_low = (rcpt_m.group(1) if rcpt_m else rcpt).strip().lower()
                known = conn.execute(
                    """
                    SELECT 1 FROM messages
                    WHERE account_id = ?
                      AND (LOWER(from_addr) = ? OR UPPER(folder) IN ('SENT', 'SENT MESSAGES', 'SENT ITEMS'))
                      AND (LOWER(to_json) LIKE ? OR LOWER(cc_json) LIKE ?)
                    UNION ALL
                    SELECT 1 FROM outbox
                    WHERE account_id = ?
                      AND status = 'sent'
                      AND (LOWER(to_json) LIKE ? OR LOWER(cc_json) LIKE ? OR LOWER(bcc_json) LIKE ?)
                    LIMIT 1
                    """,
                    (
                        account_id,
                        from_low,
                        f"%{rcpt_low}%",
                        f"%{rcpt_low}%",
                        account_id,
                        f"%{rcpt_low}%",
                        f"%{rcpt_low}%",
                        f"%{rcpt_low}%",
                    ),
                ).fetchone()
                if not known:
                    new_recipients.append(rcpt)

            now = time.time()
            outbox_id = f"out-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO outbox (
                    id, account_id, to_json, cc_json, bcc_json, subject, body,
                    in_reply_to, "references", status, error, created_at, send_after, sent_at, ai_draft_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirm', '', ?, 0.0, 0.0, ?)
                """,
                (
                    outbox_id,
                    account_id,
                    json.dumps(to_list, ensure_ascii=False),
                    json.dumps(cc_list, ensure_ascii=False),
                    json.dumps(bcc_list, ensure_ascii=False),
                    subject,
                    body,
                    in_reply_to,
                    references,
                    now,
                    ai_draft_id,
                ),
            )
            conn.commit()

        confirm_token = f"ctok-{uuid.uuid4().hex}"
        self._confirm_tokens[confirm_token] = {
            "outbox_id": outbox_id,
            "expires_at": now + 120.0,
            "used": False,
            "reply_to_message_id": reply_to_message_id,
        }

        word_count = len(re.findall(r"\S+", body))
        to_disp = ", ".join(
            f"{r} [new]" if r in new_recipients else r for r in to_list
        )
        cc_part = f", cc {len(cc_list)}" if cc_list else ""
        confirm_line = f'send from {from_email} to {to_disp}{cc_part} · "{subject}" · {word_count} words'

        return {
            "ok": True,
            "outbox_id": outbox_id,
            "confirm_token": confirm_token,
            "expires_in_seconds": 120,
            "from_email": from_email,
            "to": to_list,
            "cc": cc_list,
            "bcc": bcc_list,
            "new_recipients": new_recipients,
            "subject": subject,
            "word_count": word_count,
            "confirm_line": confirm_line,
        }

    def confirm_and_queue_send(
        self,
        outbox_id: str,
        confirm_token: str,
        immediate_for_test: bool = False,
    ) -> dict[str, Any]:
        """
        Section 4.7 Send Gate Step 2 & 3:
        Requires a valid, single-use, non-expired `confirm_token` from `/mail/send/prepare`.
        Enforces the 20 sends/hour/account limit, transitions the outbox row to `queued`
        with `send_after = now + 10s` (for 10s `[undo]`), and dispatches via `smtplib`.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        outbox_id = (outbox_id or "").strip()
        confirm_token = (confirm_token or "").strip()
        if not outbox_id or not confirm_token:
            return {"ok": False, "error": "Missing outbox_id or confirm_token."}

        tok_entry = self._confirm_tokens.get(confirm_token)
        now = time.time()
        if not tok_entry:
            return {"ok": False, "error": "Invalid confirm_token."}
        if tok_entry.get("used"):
            return {"ok": False, "error": "confirm_token has already been used."}
        if float(tok_entry.get("expires_at") or 0.0) < now:
            return {"ok": False, "error": "confirm_token has expired (2 minute limit)."}
        if tok_entry.get("outbox_id") != outbox_id:
            return {"ok": False, "error": "confirm_token does not match outbox_id."}

        # Mark token used (single-use)
        tok_entry["used"] = True

        with self.db_lock:
            conn = self._ensure_connection()
            ob_row = conn.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not ob_row:
                return {"ok": False, "error": "Outbox item not found."}
            account_id = ob_row["account_id"]

            # Rate limit check: max 20 sends per hour per account (setting)
            settings = self.get_mail_settings()
            hourly_limit = int(settings.get("sends_per_hour_limit") or 20)
            sent_last_hour = conn.execute(
                """
                SELECT COUNT(*) AS c FROM outbox
                WHERE account_id = ? AND status = 'sent' AND sent_at >= ?
                """,
                (account_id, now - 3600.0),
            ).fetchone()["c"]
            if int(sent_last_hour) >= hourly_limit:
                conn.execute(
                    "UPDATE outbox SET status = 'draft', error = ? WHERE id = ?",
                    (f"Rate limit exceeded ({hourly_limit} sends/hour)", outbox_id),
                )
                conn.commit()
                return {"ok": False, "error": f"Rate limit exceeded ({hourly_limit} sends/hour)."}

            send_after = now if immediate_for_test else (now + 10.0)
            conn.execute(
                "UPDATE outbox SET status = 'queued', send_after = ?, error = '' WHERE id = ?",
                (send_after, outbox_id),
            )
            conn.commit()

        reply_to_mid = str(tok_entry.get("reply_to_message_id") or "")
        if immediate_for_test:
            return self._execute_outbox_send(outbox_id, reply_to_message_id=reply_to_mid)

        timer = threading.Timer(10.0, self._execute_outbox_send, args=(outbox_id, reply_to_mid))
        timer.daemon = True
        self._send_timers[outbox_id] = timer
        timer.start()

        return {
            "ok": True,
            "outbox_id": outbox_id,
            "status": "queued",
            "send_after": send_after,
            "undo_window_seconds": 10,
        }

    def undo_send(self, outbox_id: str) -> dict[str, Any]:
        """
        Section 4.7: Cancels a queued send within the 10-second `[undo]` window and returns
        the outbox row to `draft` status.
        """
        outbox_id = (outbox_id or "").strip()
        timer = self._send_timers.pop(outbox_id, None)
        if timer is not None:
            timer.cancel()

        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute("SELECT status FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "Outbox row not found."}
            if row["status"] == "sent":
                return {"ok": False, "error": "Message was already sent."}
            conn.execute(
                "UPDATE outbox SET status = 'draft', send_after = 0.0 WHERE id = ?",
                (outbox_id,),
            )
            conn.commit()
        return {"ok": True, "outbox_id": outbox_id, "status": "draft", "undone": True}

    def _execute_outbox_send(self, outbox_id: str, reply_to_message_id: str = "") -> dict[str, Any]:
        self._send_timers.pop(outbox_id, None)
        with self.db_lock:
            conn = self._ensure_connection()
            ob = conn.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not ob or ob["status"] != "queued":
                return {"ok": False, "error": "Outbox item is no longer queued."}
            ob_dict = dict(ob)
            acct = conn.execute("SELECT * FROM accounts WHERE id = ?", (ob_dict["account_id"],)).fetchone()
            if not acct:
                conn.execute("UPDATE outbox SET status = 'failed', error = 'Account missing' WHERE id = ?", (outbox_id,))
                conn.commit()
                return {"ok": False, "error": "Account missing."}
            acct_dict = dict(acct)

        try:
            auth_info = self._resolve_auth_for_prefix(acct_dict["vault_prefix"], acct_email=acct_dict["email"])
        except Exception as ae:
            err = f"OAuth / vault credential error: {ae}"
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute("UPDATE outbox SET status = 'failed', error = ? WHERE id = ?", (err, outbox_id))
                conn.commit()
            return {"ok": False, "error": err}

        username = auth_info["username"] or acct_dict["email"]
        password = auth_info["password"]
        if not username or (auth_info.get("mode") != "oauth2" and not password):
            err = "Missing SMTP credentials in vault"
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute("UPDATE outbox SET status = 'failed', error = ? WHERE id = ?", (err, outbox_id))
                conn.commit()
            return {"ok": False, "error": err}

        to_list = json.loads(ob_dict.get("to_json") or "[]")
        cc_list = json.loads(ob_dict.get("cc_json") or "[]")
        bcc_list = json.loads(ob_dict.get("bcc_json") or "[]")
        all_rcpts = [r for r in (to_list + cc_list + bcc_list) if r]

        msg = EmailMessage()
        msg_id_hdr = f"<{uuid.uuid4().hex}@satz.mail>"
        msg["Message-ID"] = msg_id_hdr
        msg["From"] = acct_dict["email"]
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = ob_dict.get("subject") or "(no subject)"
        msg["Date"] = email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))
        if ob_dict.get("in_reply_to"):
            msg["In-Reply-To"] = ob_dict["in_reply_to"]
        if ob_dict.get("references"):
            msg["References"] = ob_dict["references"]
        msg.set_content(ob_dict.get("body") or "")
        raw_bytes = msg.as_bytes()

        try:
            smtp = self._open_smtp_client(
                acct_dict["smtp_host"],
                int(acct_dict["smtp_port"]),
                acct_dict["smtp_security"],
            )
            try:
                self._smtp_authenticate(
                    smtp, auth_info, vault_prefix=acct_dict["vault_prefix"], acct_email=acct_dict["email"]
                )
                if hasattr(smtp, "send_message"):
                    smtp.send_message(msg, from_addr=acct_dict["email"], to_addrs=all_rcpts)
                elif hasattr(smtp, "sendmail"):
                    smtp.sendmail(acct_dict["email"], all_rcpts, raw_bytes)
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass

            now_ts = time.time()
            # Store sent message in local thread (`messages` table under folder='Sent')
            sent_local_id = self._store_parsed_raw_email(
                account_id=acct_dict["id"],
                folder_name="Sent",
                role="sent",
                uid=0,
                pop_uidl="",
                raw_bytes=raw_bytes,
                seen=1,
                answered=0,
                flagged=0,
            )

            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute(
                    "UPDATE outbox SET status = 'sent', sent_at = ?, error = '' WHERE id = ?",
                    (now_ts, outbox_id),
                )
                if reply_to_message_id:
                    conn.execute("UPDATE messages SET answered = 1 WHERE id = ?", (reply_to_message_id,))
                elif ob_dict.get("in_reply_to"):
                    conn.execute(
                        "UPDATE messages SET answered = 1 WHERE message_id = ?",
                        (ob_dict["in_reply_to"],),
                    )
                conn.commit()

            try:
                self._record_outbox_style_diff(outbox_id=outbox_id, ob_dict=ob_dict, to_list=to_list)
            except Exception as style_exc:
                self.runtime.record_error("mail_style_diff", style_exc)

            # Server writes allowed by Section 4.4:
            # 1) Set `\Answered` on the original message on IMAP server
            # 2) `APPEND` to Sent for providers that do not auto-save SMTP sends (not Gmail, not Outlook)
            if str(acct_dict.get("protocol") or "imap").lower() == "imap":
                in_host_low = str(acct_dict.get("in_host") or "").lower()
                is_gmail_or_outlook = ("gmail.com" in in_host_low) or ("office365.com" in in_host_low) or ("outlook.com" in in_host_low)
                try:
                    imap = self._open_imap_client(acct_dict["in_host"], int(acct_dict["in_port"]), acct_dict["in_security"])
                    try:
                        self._imap_authenticate(
                            imap, auth_info, vault_prefix=acct_dict["vault_prefix"], acct_email=acct_dict["email"]
                        )
                        if reply_to_message_id:
                            with self.db_lock:
                                orig_row = self._ensure_connection().execute(
                                    "SELECT folder, uid FROM messages WHERE id = ?",
                                    (reply_to_message_id,),
                                ).fetchone()
                            if orig_row and int(orig_row["uid"] or 0) > 0:
                                st, _ = imap.select(orig_row["folder"], readonly=False)
                                if st == "OK":
                                    imap.uid("STORE", str(orig_row["uid"]), "+FLAGS.SILENT", "(\\Answered)")
                        if not is_gmail_or_outlook and hasattr(imap, "append"):
                            imap.append("Sent", "(\\Seen)", None, raw_bytes)
                    finally:
                        try:
                            imap.logout()
                        except Exception:
                            pass
                except Exception:
                    pass

            return {"ok": True, "outbox_id": outbox_id, "status": "sent", "sent_message_id": sent_local_id}

        except Exception as exc:
            err_str = str(exc)
            self.runtime.record_error("mail_send", f"{outbox_id}: {err_str}")
            with self.db_lock:
                conn = self._ensure_connection()
                conn.execute(
                    "UPDATE outbox SET status = 'draft', error = ? WHERE id = ?",
                    (err_str, outbox_id),
                )
                conn.commit()
            return {"ok": False, "error": err_str, "outbox_id": outbox_id, "status": "draft"}

    # ── Personal Writing Style Learning (Outbox Edit Diffs -> Brain Note) ─
    def _get_learned_style_context(
        self,
        to_addr: str = "",
        quoted_context: str = "",
    ) -> dict[str, Any]:
        """
        Loads distilled personal writing style rules from the Brain preference note
        (`Notes/email-writing-style-preferences.md`) plus per-recipient language history.
        """
        if not self.passwords.unlocked:
            return {"applied": False, "prompt_block": "", "summary": "", "preferred_lang": "en"}

        rcpt_addr, rcpt_dom = _extract_email_and_domain(to_addr)
        brain = getattr(self.runtime, "brain", None)
        note_rec = (
            brain.get_entity_by_slug(STYLE_BRAIN_ENTITY_SLUG, body_limit=2400)
            if (brain is not None and not getattr(brain, "locked", True))
            else None
        )

        attrs = (note_rec or {}).get("attributes") or {}
        rcpt_langs: dict[str, str] = {}
        dom_langs: dict[str, str] = {}
        raw_rcpt_map = attrs.get("recipient_languages")
        if isinstance(raw_rcpt_map, dict):
            rcpt_langs = {str(k).lower(): str(v).lower() for k, v in raw_rcpt_map.items() if v}
        elif isinstance(raw_rcpt_map, str):
            try:
                parsed = json.loads(raw_rcpt_map)
                if isinstance(parsed, dict):
                    rcpt_langs = {str(k).lower(): str(v).lower() for k, v in parsed.items() if v}
            except Exception:
                pass

        raw_dom_map = attrs.get("domain_languages")
        if isinstance(raw_dom_map, dict):
            dom_langs = {str(k).lower(): str(v).lower() for k, v in raw_dom_map.items() if v}
        elif isinstance(raw_dom_map, str):
            try:
                parsed = json.loads(raw_dom_map)
                if isinstance(parsed, dict):
                    dom_langs = {str(k).lower(): str(v).lower() for k, v in parsed.items() if v}
            except Exception:
                pass

        preferred_lang = ""
        lang_source = ""
        if rcpt_addr and rcpt_addr in rcpt_langs:
            preferred_lang = rcpt_langs[rcpt_addr]
            lang_source = f"past sent mail to {rcpt_addr}"
        elif rcpt_dom and rcpt_dom in dom_langs:
            preferred_lang = dom_langs[rcpt_dom]
            lang_source = f"past sent mail to @{rcpt_dom}"

        # Also check immediate diff history if Brain note hasn't distilled this recipient yet
        if not preferred_lang and (rcpt_addr or rcpt_dom):
            try:
                with self.db_lock:
                    conn = self._ensure_connection()
                    rows = conn.execute(
                        """
                        SELECT diff_summary_json
                        FROM writing_style_diffs
                        WHERE (recipient_key = ? AND ? != '') OR (recipient_domain = ? AND ? != '')
                        ORDER BY at DESC LIMIT 5
                        """,
                        (rcpt_addr, rcpt_addr, rcpt_dom, rcpt_dom),
                    ).fetchall()
                    lang_votes = Counter()
                    for r in rows:
                        try:
                            meta = json.loads(r["diff_summary_json"] or "{}")
                            sl = str(meta.get("sent_lang") or "")
                            if sl in ("de", "en"):
                                lang_votes[sl] += 1
                        except Exception:
                            pass
                    if lang_votes:
                        preferred_lang = lang_votes.most_common(1)[0][0]
                        lang_source = f"recent edits for {rcpt_addr or rcpt_dom}"
            except Exception:
                pass

        if not preferred_lang and quoted_context:
            q_lang = _detect_language_de_en(_strip_quoted_reply(quoted_context) or quoted_context)
            if q_lang in ("de", "en"):
                preferred_lang = q_lang
                lang_source = "incoming thread language"

        preferred_lang = preferred_lang if preferred_lang in ("de", "en") else "en"

        pref_greet = (
            str(attrs.get("preferred_greeting_de") or "")
            if preferred_lang == "de"
            else str(attrs.get("preferred_greeting_en") or "")
        ) or str(attrs.get("preferred_greeting") or "")
        pref_sign = (
            str(attrs.get("preferred_signoff_de") or "")
            if preferred_lang == "de"
            else str(attrs.get("preferred_signoff_en") or "")
        ) or str(attrs.get("preferred_signoff") or "")

        lines: list[str] = []
        if note_rec:
            lines.append("PERSONAL WRITING STYLE PREFERENCES (from your Brain note):")
            body_txt = str(note_rec.get("body") or "").strip()
            if body_txt:
                lines.append(body_txt[:1200])
        elif lang_source:
            lines.append("PERSONAL WRITING STYLE PREFERENCES:")

        if lang_source:
            lang_label = "German (Deutsch)" if preferred_lang == "de" else "English"
            lines.append(
                f"- Recipient language rule ({lang_source}): Write this email in {lang_label}."
            )
            if pref_greet and pref_greet != "<none>":
                lines.append(f"- Use greeting style for {preferred_lang.upper()}: {pref_greet}")
            if pref_sign and pref_sign != "<none>":
                lines.append(f"- Use sign-off for {preferred_lang.upper()}: {pref_sign.replace(chr(10), ' / ')}")

        prompt_block = "\n".join(lines).strip()
        summary = str((note_rec or {}).get("summary") or "")
        if not summary and lang_source:
            summary = f"Language: {preferred_lang} ({lang_source})"
        return {
            "applied": bool(note_rec or lang_source),
            "has_brain_note": bool(note_rec),
            "prompt_block": prompt_block,
            "summary": summary,
            "preferred_lang": preferred_lang,
            "preferred_greeting": pref_greet,
            "preferred_signoff": pref_sign,
        }

    def _record_outbox_style_diff(
        self,
        outbox_id: str,
        ob_dict: dict[str, Any],
        to_list: list[str],
    ) -> dict[str, Any] | None:
        """
        Compares an AI-drafted reply (`ai_drafts`) against the final sent `outbox` body
        and stores the diff sample in `writing_style_diffs`. Triggers Brain style distillation
        once enough sent edit diffs accumulate.
        """
        ai_draft_id = str(ob_dict.get("ai_draft_id") or "").strip()
        sent_body = str(ob_dict.get("body") or "")
        subject = str(ob_dict.get("subject") or "")
        rcpt_addr, rcpt_dom = ("", "")
        for r in to_list:
            addr, dom = _extract_email_and_domain(r)
            if addr:
                rcpt_addr, rcpt_dom = addr, dom
                break

        with self.db_lock:
            conn = self._ensure_connection()
            draft_row = None
            if ai_draft_id:
                draft_row = conn.execute("SELECT * FROM ai_drafts WHERE id = ?", (ai_draft_id,)).fetchone()
            if draft_row is None and rcpt_addr:
                cutoff = time.time() - 48 * 3600.0
                draft_row = conn.execute(
                    """
                    SELECT * FROM ai_drafts
                    WHERE LOWER(to_addr) LIKE ? AND created_at >= ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (f"%{rcpt_addr}%", cutoff),
                ).fetchone()
                if draft_row:
                    ai_draft_id = str(draft_row["id"])
            if draft_row is None and subject:
                cutoff = time.time() - 48 * 3600.0
                draft_row = conn.execute(
                    """
                    SELECT * FROM ai_drafts
                    WHERE LOWER(subject) = ? AND created_at >= ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (subject.lower(), cutoff),
                ).fetchone()
                if draft_row:
                    ai_draft_id = str(draft_row["id"])

            if draft_row is None:
                return None

            draft_body = str(draft_row["draft_body"] or "")
            diff_info = _analyze_outbox_edit_diff(draft_body, sent_body, to_list)
            now_ts = time.time()
            conn.execute(
                """
                INSERT OR REPLACE INTO writing_style_diffs (
                    outbox_id, ai_draft_id, recipient_key, recipient_domain,
                    draft_body, sent_body, edit_ratio, diff_summary_json, at, used_in_distill
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    outbox_id,
                    ai_draft_id,
                    diff_info["recipient_addr"] or rcpt_addr,
                    diff_info["recipient_domain"] or rcpt_dom,
                    _strip_quoted_reply(draft_body),
                    _strip_quoted_reply(sent_body),
                    float(diff_info["edit_ratio"]),
                    json.dumps(diff_info, ensure_ascii=False),
                    now_ts,
                ),
            )
            conn.commit()

        distill_res = self.maybe_distill_writing_style()
        return {"ok": True, "diff": diff_info, "distilled": bool(distill_res.get("distilled"))}

    def maybe_distill_writing_style(
        self,
        force: bool = False,
        min_samples: int = STYLE_DISTILL_MIN_SAMPLES,
    ) -> dict[str, Any]:
        """
        Distills accumulated outbox edit diffs into the Brain preference note once at least
        `STYLE_DISTILL_MIN_SAMPLES` (10) diffs exist, and refreshes every `STYLE_DISTILL_STEP` (5)
        new sent emails thereafter.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "distilled": False, "reason": "locked"}

        with self.db_lock:
            conn = self._ensure_connection()
            total_cnt = int(
                conn.execute("SELECT COUNT(*) AS c FROM writing_style_diffs").fetchone()["c"]
            )
            undistilled_cnt = int(
                conn.execute("SELECT COUNT(*) AS c FROM writing_style_diffs WHERE used_in_distill = 0").fetchone()["c"]
            )
            already_distilled = int(
                conn.execute("SELECT COUNT(*) AS c FROM writing_style_diffs WHERE used_in_distill = 1").fetchone()["c"]
            ) > 0

        if not force:
            if total_cnt < min_samples:
                return {"ok": True, "distilled": False, "total": total_cnt, "undistilled": undistilled_cnt}
            if not already_distilled and undistilled_cnt < min_samples:
                return {"ok": True, "distilled": False, "total": total_cnt, "undistilled": undistilled_cnt}
            if already_distilled and undistilled_cnt < STYLE_DISTILL_STEP:
                return {"ok": True, "distilled": False, "total": total_cnt, "undistilled": undistilled_cnt}
        elif total_cnt == 0:
            return {"ok": True, "distilled": False, "total": 0, "undistilled": 0}

        return self.distill_writing_style()

    def distill_writing_style(self) -> dict[str, Any]:
        """
        Aggregates recent `writing_style_diffs` (greeting, DE/EN per recipient, sign-off,
        conciseness, avoided clichés) and writes the Brain preference note.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute(
                """
                SELECT outbox_id, ai_draft_id, recipient_key, recipient_domain,
                       draft_body, sent_body, edit_ratio, diff_summary_json, at
                FROM writing_style_diffs
                ORDER BY at DESC
                LIMIT 30
                """
            ).fetchall()

        if not rows:
            return {"ok": True, "distilled": False, "samples_count": 0}

        greet_en = Counter()
        greet_de = Counter()
        greet_all = Counter()
        sign_en = Counter()
        sign_de = Counter()
        sign_all = Counter()
        rcpt_lang_votes: dict[str, Counter] = {}
        dom_lang_votes: dict[str, Counter] = {}
        removed_phrases_cnt = Counter()
        sent_word_counts: list[int] = []
        draft_word_counts: list[int] = []
        samples_for_fn: list[dict[str, Any]] = []

        for r in rows:
            try:
                meta = json.loads(r["diff_summary_json"] or "{}")
            except Exception:
                meta = {}
            samples_for_fn.append(
                {
                    "recipient": r["recipient_key"],
                    "domain": r["recipient_domain"],
                    "draft_body": r["draft_body"],
                    "sent_body": r["sent_body"],
                    "edit_ratio": r["edit_ratio"],
                    "meta": meta,
                }
            )
            slang = str(meta.get("sent_lang") or "unknown")
            sg = str(meta.get("sent_greeting") or "<none>")
            ss = str(meta.get("sent_signoff") or "<none>")
            sw = int(meta.get("sent_words") or 0)
            dw = int(meta.get("draft_words") or 0)
            if sw > 0:
                sent_word_counts.append(sw)
            if dw > 0:
                draft_word_counts.append(dw)

            greet_all[sg] += 1
            sign_all[ss] += 1
            if slang == "de":
                greet_de[sg] += 1
                sign_de[ss] += 1
            elif slang == "en":
                greet_en[sg] += 1
                sign_en[ss] += 1

            rk = str(r["recipient_key"] or "").strip().lower()
            rd = str(r["recipient_domain"] or "").strip().lower()
            if slang in ("de", "en"):
                if rk:
                    rcpt_lang_votes.setdefault(rk, Counter())[slang] += 1
                if rd:
                    dom_lang_votes.setdefault(rd, Counter())[slang] += 1

            for ph in meta.get("removed_phrases") or []:
                removed_phrases_cnt[str(ph)] += 1

        pref_greet_all = greet_all.most_common(1)[0][0] if greet_all else "Hi <Name>,"
        pref_greet_en = greet_en.most_common(1)[0][0] if greet_en else pref_greet_all
        pref_greet_de = greet_de.most_common(1)[0][0] if greet_de else "Hallo <Name>,"

        pref_sign_all = sign_all.most_common(1)[0][0] if sign_all else "Best,"
        pref_sign_en = sign_en.most_common(1)[0][0] if sign_en else pref_sign_all
        pref_sign_de = sign_de.most_common(1)[0][0] if sign_de else "Beste Grüße,"

        recipient_languages: dict[str, str] = {}
        for rk, votes in sorted(rcpt_lang_votes.items()):
            top_l, top_c = votes.most_common(1)[0]
            if top_c >= 1:
                recipient_languages[rk] = top_l

        domain_languages: dict[str, str] = {}
        for rd, votes in sorted(dom_lang_votes.items()):
            top_l, top_c = votes.most_common(1)[0]
            other_c = sum(votes.values()) - top_c
            if top_c > other_c:
                domain_languages[rd] = top_l

        sorted_sw = sorted(sent_word_counts)
        target_words = sorted_sw[len(sorted_sw) // 2] if sorted_sw else 60
        total_dw = sum(draft_word_counts)
        total_sw = sum(sent_word_counts)
        compression_ratio = round(total_sw / max(1, total_dw), 2) if total_dw > 0 else 1.0
        avoid_phrases = [ph for ph, cnt in removed_phrases_cnt.most_common(6) if cnt >= 2]

        stats_obj = {
            "samples_count": len(rows),
            "preferred_greeting": pref_greet_all,
            "preferred_greeting_en": pref_greet_en,
            "preferred_greeting_de": pref_greet_de,
            "preferred_signoff": pref_sign_all,
            "preferred_signoff_en": pref_sign_en,
            "preferred_signoff_de": pref_sign_de,
            "conciseness_target_words": target_words,
            "compression_ratio": compression_ratio,
            "recipient_languages": recipient_languages,
            "domain_languages": domain_languages,
            "avoid_phrases": avoid_phrases,
        }

        rules_lines = [
            f"Learned from {len(rows)} edited & sent emails:",
            f"- Greeting style (English): {'Omit greeting and start directly' if pref_greet_en == '<none>' else pref_greet_en}",
            f"- Greeting style (German): {'Omit greeting and start directly' if pref_greet_de == '<none>' else pref_greet_de}",
            f"- Sign-off (English): {'No sign-off' if pref_sign_en == '<none>' else pref_sign_en.replace(chr(10), ' / ')}",
            f"- Sign-off (German): {'No sign-off' if pref_sign_de == '<none>' else pref_sign_de.replace(chr(10), ' / ')}",
        ]
        if compression_ratio < 0.88:
            trim_pct = int(round((1.0 - compression_ratio) * 100))
            rules_lines.append(
                f"- Conciseness: Keep replies concise around ~{target_words} words (user trims AI drafts by ~{trim_pct}%)."
            )
        else:
            rules_lines.append(
                f"- Conciseness: Typical reply length is ~{target_words} words."
            )
        if recipient_languages:
            de_rcpts = [k for k, v in recipient_languages.items() if v == "de"]
            en_rcpts = [k for k, v in recipient_languages.items() if v == "en"]
            if de_rcpts:
                rules_lines.append(f"- German (de) recipients: {', '.join(de_rcpts[:10])}")
            if en_rcpts:
                rules_lines.append(f"- English (en) recipients: {', '.join(en_rcpts[:10])}")
        if avoid_phrases:
            rules_lines.append(f"- Avoid filler phrases user deletes: {', '.join(avoid_phrases)}")

        rules_md = "\n".join(rules_lines)
        if self.style_distiller_fn is not None:
            try:
                custom_md = str(self.style_distiller_fn(samples_for_fn, stats_obj) or "").strip()
                if custom_md:
                    rules_md = custom_md
            except Exception as exc:
                self.runtime.record_error("mail_style_distill", exc)

        summary_str = (
            f"Learned from {len(rows)} sent emails: EN '{pref_greet_en}' / '{pref_sign_en.splitlines()[0]}', "
            f"DE '{pref_greet_de}' / '{pref_sign_de.splitlines()[0]}', ~{target_words} words."
        )[:220]

        brain_entity = None
        brain = getattr(self.runtime, "brain", None)
        if brain is not None and not getattr(brain, "locked", True):
            brain_entity = brain.upsert_entity(
                entity_type="note",
                name=STYLE_BRAIN_ENTITY_NAME,
                summary=summary_str,
                attributes=stats_obj,
                content=rules_md,
                aliases=["writing style", "email style", "draft style", "style preferences"],
                tier=1,
                actor="mail/style_learner",
            )

        with self.db_lock:
            conn = self._ensure_connection()
            conn.execute("UPDATE writing_style_diffs SET used_in_distill = 1 WHERE used_in_distill = 0")
            conn.commit()

        return {
            "ok": True,
            "distilled": True,
            "samples_count": len(rows),
            "rules_markdown": rules_md,
            "attributes": stats_obj,
            "entity": brain_entity,
        }

    def get_writing_style_status(self) -> dict[str, Any]:
        """Returns outbox edit-diff telemetry and the distilled Brain style preference note."""
        if not self.passwords.unlocked:
            return {"ok": False, "unlocked": False, "diff_count": 0, "undistilled_count": 0}

        with self.db_lock:
            conn = self._ensure_connection()
            total_cnt = int(conn.execute("SELECT COUNT(*) AS c FROM writing_style_diffs").fetchone()["c"])
            undistilled_cnt = int(
                conn.execute("SELECT COUNT(*) AS c FROM writing_style_diffs WHERE used_in_distill = 0").fetchone()["c"]
            )
            recent_rows = conn.execute(
                """
                SELECT outbox_id, recipient_key, recipient_domain, edit_ratio, diff_summary_json, at, used_in_distill
                FROM writing_style_diffs
                ORDER BY at DESC LIMIT 15
                """
            ).fetchall()

        brain = getattr(self.runtime, "brain", None)
        brain_note = (
            brain.get_entity_by_slug(STYLE_BRAIN_ENTITY_SLUG, body_limit=2400)
            if (brain is not None and not getattr(brain, "locked", True))
            else None
        )
        recent = []
        for r in recent_rows:
            try:
                meta = json.loads(r["diff_summary_json"] or "{}")
            except Exception:
                meta = {}
            recent.append(
                {
                    "outbox_id": r["outbox_id"],
                    "recipient": r["recipient_key"],
                    "domain": r["recipient_domain"],
                    "edit_ratio": r["edit_ratio"],
                    "sent_lang": meta.get("sent_lang"),
                    "sent_words": meta.get("sent_words"),
                    "draft_words": meta.get("draft_words"),
                    "sent_greeting": meta.get("sent_greeting"),
                    "sent_signoff": meta.get("sent_signoff"),
                    "used_in_distill": bool(r["used_in_distill"]),
                    "at": r["at"],
                }
            )
        rules_list: list[str] = []
        if brain_note:
            for ln in str(brain_note.get("body") or brain_note.get("content") or "").splitlines():
                s = ln.strip()
                if s.startswith("- "):
                    rules_list.append(s[2:].strip())
        samples_until = (
            max(0, STYLE_DISTILL_MIN_SAMPLES - total_cnt)
            if brain_note is None
            else max(0, STYLE_DISTILL_STEP - undistilled_cnt)
        )
        return {
            "ok": True,
            "unlocked": True,
            "diff_count": total_cnt,
            "undistilled_count": undistilled_cnt,
            "distill_threshold": STYLE_DISTILL_MIN_SAMPLES,
            "min_samples": STYLE_DISTILL_MIN_SAMPLES,
            "samples_until_distill": samples_until,
            "has_note": bool(brain_note),
            "note_path": str((brain_note or {}).get("path") or ""),
            "note_summary": str((brain_note or {}).get("summary") or ""),
            "rules": rules_list,
            "brain_note": brain_note,
            "recent_diffs": recent,
        }

    # ── Milestone M14: Triage Set, Active Promo Codes, Digest & Eval Mode ──

    def get_triage_set(self, account_id: str | None = None) -> dict[str, Any]:
        """
        Section 4.1 & 4.8 (M14): Returns the default context set for the Mail `chat` tab
        and `For you` digest:
        1) Unread `email` messages + `needs_reply` messages from the last 7 days
        2) Order (`information`) updates from the last 7 days
        3) Promo codes expiring in the next 7 days
        Also builds `sources` (`id: mail:<message_id>`) and a formatted `overview` answer with `[n]` citations.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {
                "ok": False,
                "unlocked": False,
                "emails_needing_attention": [],
                "order_updates": [],
                "expiring_promos": [],
                "sources": [],
                "overview": "",
            }

        eff_acct = (account_id or "").strip()
        if eff_acct.lower() == "all":
            eff_acct = ""
        acct_sql = " AND m.account_id = ? " if eff_acct else ""
        acct_params: tuple[Any, ...] = (eff_acct,) if eff_acct else ()

        now = time.time()
        seven_days_ago = now - 7 * 86400.0
        today_date = datetime.date.today()
        today_iso = today_date.isoformat()
        in_7d_iso = (today_date + datetime.timedelta(days=7)).isoformat()

        t_target = self._primary_translation_target()
        with self.db_lock:
            conn = self._ensure_connection()
            # 1. Unread `email` + `needs_reply` in last 7 days
            email_rows = conn.execute(
                f"""
                SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                       m.from_name, m.from_addr, m.subject, m.snippet, m.date, m.seen,
                       COALESCE(a.needs_reply, 0) AS needs_reply,
                       a.due_date AS due_date,
                       COALESCE(a.ask, '') AS ask,
                       COALESCE(p.text, m.body_text) AS new_text,
                       COALESCE(mt.subject_tr, '') AS translated_subject,
                       COALESCE(mt.snippet_tr, '') AS translated_snippet,
                       COALESCE(mt.new_text_tr, '') AS translated_new_text
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                LEFT JOIN labels l ON l.message_id = m.id
                LEFT JOIN actions a ON a.message_id = m.id
                LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
                LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                WHERE m.hidden = 0
                  AND UPPER(m.folder) = 'INBOX'
                  AND COALESCE(l.label, 'email') = 'email'
                  AND m.date >= ?
                  AND (m.seen = 0 OR COALESCE(a.needs_reply, 0) = 1)
                  {acct_sql}
                ORDER BY COALESCE(a.needs_reply, 0) DESC, m.date DESC
                LIMIT 10
                """,
                (t_target, seven_days_ago, *acct_params),
            ).fetchall()

            # 2. Order (`information`) updates in last 7 days
            order_rows = conn.execute(
                f"""
                SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                       m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                       COALESCE(p.text, m.body_text) AS new_text,
                       COALESCE(mt.subject_tr, '') AS translated_subject,
                       COALESCE(mt.snippet_tr, '') AS translated_snippet
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                JOIN labels l ON l.message_id = m.id AND l.label = 'information'
                LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
                LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                WHERE m.hidden = 0 AND m.date >= ? {acct_sql}
                ORDER BY m.date DESC
                LIMIT 8
                """,
                (t_target, seven_days_ago, *acct_params),
            ).fetchall()

            order_updates: list[dict[str, Any]] = []
            for r in order_rows:
                mid = r["id"]
                ext_rows = conn.execute(
                    "SELECT field, value FROM extracts WHERE message_id = ?",
                    (mid,),
                ).fetchall()
                ext = {er["field"]: er["value"] for er in ext_rows}
                order_no = ext.get("order_number") or ""
                tracking_no = ext.get("tracking_number") or ""
                tracking_url = ext.get("tracking_url") or ""
                raw_status = ext.get("status") or ""
                total = ext.get("total") or ""
                # Only treat `information` messages with actual order/tracking/status/total signals as order updates
                if not (order_no or tracking_no or tracking_url or raw_status or total):
                    continue
                order_updates.append(
                    {
                        **dict(r),
                        "merchant": ext.get("merchant") or r["from_name"] or r["from_addr"],
                        "order_number": order_no,
                        "status": raw_status or "ordered",
                        "tracking_number": tracking_no,
                        "tracking_url": tracking_url,
                        "total": total,
                    }
                )

            # 3. Promo codes expiring in next 7 days (or active codes from recent promos)
            promo_rows = conn.execute(
                f"""
                SELECT m.id, m.account_id, COALESCE(ac.email, '') AS account_email,
                       m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                       COALESCE(p.text, m.body_text) AS new_text,
                       COALESCE(mt.subject_tr, '') AS translated_subject,
                       COALESCE(mt.snippet_tr, '') AS translated_snippet
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
                LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
                LEFT JOIN message_translations mt ON mt.message_id = m.id AND mt.target_lang = ?
                WHERE m.hidden = 0 {acct_sql}
                ORDER BY m.date DESC
                LIMIT 25
                """,
                (t_target, *acct_params),
            ).fetchall()

            expiring_promos: list[dict[str, Any]] = []
            for r in promo_rows:
                mid = r["id"]
                ext_rows = conn.execute(
                    "SELECT field, value FROM extracts WHERE message_id = ?",
                    (mid,),
                ).fetchall()
                ext = {er["field"]: er["value"] for er in ext_rows}
                code = ext.get("voucher_code") or ""
                expiry = ext.get("expiry") or ""
                if not code:
                    continue
                is_expiring_soon = bool(
                    expiry
                    and re.match(r"^\d{4}-\d{2}-\d{2}$", expiry)
                    and today_iso <= expiry <= in_7d_iso
                )
                if is_expiring_soon or (not expiry and len(expiring_promos) < 4):
                    expiring_promos.append(
                        {
                            **dict(r),
                            "company": ext.get("company") or r["from_name"] or r["from_addr"],
                            "voucher_code": code,
                            "discount_value": ext.get("discount_value") or "",
                            "expiry": expiry,
                        }
                    )

        emails_list = [dict(r) for r in email_rows]
        sources: list[dict[str, Any]] = []
        seen_sids: set[str] = set()
        msg_to_cite_num: dict[str, int] = {}

        for item in emails_list + order_updates + expiring_promos:
            mid = item["id"]
            sid = f"mail:{mid}"
            if sid in seen_sids:
                continue
            seen_sids.add(sid)
            cite_idx = len(sources) + 1
            msg_to_cite_num[mid] = cite_idx
            sources.append(
                {
                    "id": sid,
                    "url": f"satzmail://message/{mid}",
                    "title": f"{item.get('from_name') or item.get('from_addr')}: {item.get('subject')}",
                    "domain": "mail",
                    "text": f"From: {item.get('from_name') or ''} <{item.get('from_addr') or ''}>\nSubject: {item.get('subject') or ''}\n\n{item.get('new_text') or item.get('snippet') or ''}",
                    "is_open_tab": True,
                }
            )

        # Build Appendix A.5 default overview with `[n]` citations
        lines: list[str] = []
        lines.append(
            f"Mail triage: {len(emails_list)} inbox message(s) needing attention, {len(order_updates)} order update(s), and {len(expiring_promos)} active/expiring promo code(s)."
        )
        if emails_list:
            lines.append("\nInbox:")
            for e in emails_list[:5]:
                cnum = msg_to_cite_num.get(e["id"], 1)
                sender = e.get("from_name") or e.get("from_addr")
                ask = e.get("ask") or e.get("subject")
                due = f" (due {e['due_date']})" if e.get("due_date") else ""
                lines.append(f"- {sender}: {ask}{due} [{cnum}]")
        if order_updates:
            lines.append("\nOrders:")
            for o in order_updates[:5]:
                cnum = msg_to_cite_num.get(o["id"], 1)
                ord_str = f" #{o['order_number']}" if o.get("order_number") else ""
                lines.append(f"- {o['merchant']}{ord_str}: {o['status']} ({o['subject']}) [{cnum}]")
        if expiring_promos:
            lines.append("\nPromos:")
            for p in expiring_promos[:5]:
                cnum = msg_to_cite_num.get(p["id"], 1)
                exp_str = f", expires {p['expiry']}" if p.get("expiry") else ""
                val_str = f" ({p['discount_value']})" if p.get("discount_value") else ""
                lines.append(f"- {p['company']}: code {p['voucher_code']}{val_str}{exp_str} [{cnum}]")

        return {
            "ok": True,
            "unlocked": True,
            "emails_needing_attention": emails_list,
            "order_updates": order_updates,
            "expiring_promos": expiring_promos,
            "sources": sources,
            "overview": "\n".join(lines),
        }

    def get_active_codes_for_domain(self, raw_domain: str) -> list[dict[str, Any]]:
        """
        Section 4.1 (M14): Returns non-expired promo codes matching a site tab's domain
        so the site tab toolbar can display a `codes (N)` pill.
        """
        if not self.passwords.unlocked:
            return []
        dom = (raw_domain or "").strip().lower().removeprefix("www.")
        if not dom:
            return []
        beh = getattr(self.runtime, "behavior", None)
        if beh is not None:
            beh.log_event("codes_check", domain=dom, query=dom)
        base_token = dom.split(".")[0]
        today_iso = datetime.date.today().isoformat()

        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute(
                """
                SELECT m.id, m.from_name, m.from_addr, m.subject, m.date
                FROM messages m
                JOIN labels l ON l.message_id = m.id AND l.label = 'promotion'
                WHERE m.hidden = 0
                ORDER BY m.date DESC
                LIMIT 100
                """
            ).fetchall()

            matched_codes: list[dict[str, Any]] = []
            seen_codes: set[str] = set()
            for r in rows:
                mid = r["id"]
                ext_rows = conn.execute(
                    "SELECT field, value FROM extracts WHERE message_id = ?",
                    (mid,),
                ).fetchall()
                ext = {er["field"]: er["value"] for er in ext_rows}
                code = (ext.get("voucher_code") or "").strip()
                if not code or code in seen_codes:
                    continue
                expiry = (ext.get("expiry") or "").strip()
                if expiry and re.match(r"^\d{4}-\d{2}-\d{2}$", expiry) and expiry < today_iso:
                    continue
                sender_dom = (r["from_addr"].split("@")[-1] if "@" in r["from_addr"] else "").lower()
                company = (ext.get("company") or r["from_name"] or sender_dom).lower()
                if (
                    dom in sender_dom
                    or sender_dom.endswith(f".{dom}")
                    or (len(base_token) >= 3 and (base_token in sender_dom or base_token in company))
                ):
                    seen_codes.add(code)
                    matched_codes.append(
                        {
                            "code": code,
                            "discount_value": ext.get("discount_value") or "",
                            "expiry": expiry,
                            "company": ext.get("company") or r["from_name"] or sender_dom,
                            "message_id": mid,
                        }
                    )
            return matched_codes

    # ── Section 4.9: Eval Mode (200 Stratified Samples & Confusion Matrix Report) ──

    def get_eval_sample(self, limit: int = 200) -> dict[str, Any]:
        """
        Section 4.9: Samples up to 200 messages from the last 90 days, stratified by sender
        domain (max 5 per domain), and returns them with model predictions, extracted fields,
        and any existing human `eval_labels`.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "unlocked": False, "items": []}

        cutoff = time.time() - 90 * 86400.0
        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute(
                """
                SELECT m.id, m.from_name, m.from_addr, m.subject, m.snippet, m.date,
                       COALESCE(p.text, m.body_text) AS new_text,
                       COALESCE(l.label, 'email') AS pred_label,
                       COALESCE(l.confidence, 0.0) AS pred_confidence,
                       e.label AS human_label,
                       e.extract_ok AS human_extract_ok
                FROM messages m
                LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
                LEFT JOIN labels l ON l.message_id = m.id
                LEFT JOIN eval_labels e ON e.message_id = m.id
                WHERE m.hidden = 0 AND UPPER(m.folder) = 'INBOX' AND m.date >= ?
                ORDER BY m.date DESC
                """,
                (cutoff,),
            ).fetchall()

            domain_counts: dict[str, int] = {}
            sampled: list[dict[str, Any]] = []
            overflow: list[sqlite3.Row] = []

            for r in rows:
                addr = (r["from_addr"] or "").lower()
                dom = addr.split("@")[-1] if "@" in addr else addr
                if domain_counts.get(dom, 0) < 5:
                    domain_counts[dom] = domain_counts.get(dom, 0) + 1
                    sampled.append(dict(r))
                    if len(sampled) >= limit:
                        break
                else:
                    overflow.append(r)

            # If dataset has fewer than `limit` after max-5-per-domain cap, fill from remaining messages
            if len(sampled) < limit and overflow:
                for r in overflow:
                    sampled.append(dict(r))
                    if len(sampled) >= limit:
                        break

            for item in sampled:
                ext_rows = conn.execute(
                    "SELECT field, value FROM extracts WHERE message_id = ?",
                    (item["id"],),
                ).fetchall()
                item["extracts"] = {er["field"]: er["value"] for er in ext_rows}

        return {
            "ok": True,
            "unlocked": True,
            "total_sampled": len(sampled),
            "labelled_count": sum(1 for x in sampled if x.get("human_label")),
            "items": sampled,
        }

    def record_eval_label(
        self,
        message_id: str,
        human_label: str,
        extract_ok: bool | None = None,
    ) -> dict[str, Any]:
        """
        Section 4.9: Stores human eval label (`email`, `ping`, `information`, `promotion`)
        and `extract_ok` (`1` / `0` / `None`) in `eval_labels`.
        Eval labels are NEVER written to `corrections` or used for classifier training.
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        lbl = (human_label or "").strip().lower()
        if lbl not in ("email", "ping", "information", "promotion"):
            return {"ok": False, "error": f"Invalid label: {lbl}"}
        ext_val: int | None = None
        if extract_ok is not None:
            ext_val = 1 if bool(extract_ok) else 0

        with self.db_lock:
            conn = self._ensure_connection()
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_labels (message_id, label, extract_ok, at)
                VALUES (?, ?, ?, ?)
                """,
                (message_id, lbl, ext_val, time.time()),
            )
            conn.commit()
        return {"ok": True, "message_id": message_id, "label": lbl, "extract_ok": ext_val}

    def get_eval_report(self) -> dict[str, Any]:
        """
        Section 4.9: Computes over `eval_labels` joined with `labels`:
        - 4x4 confusion matrix (`true_label -> pred_label -> count`)
        - `real_email_misfiled_as_promotion_rate` (target <= 1.0%)
        - `promotion_recall` (target >= 90.0%)
        - `extraction_accuracy` (target >= 90.0%)
        """
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        all_labels = ("email", "ping", "information", "promotion")
        matrix: dict[str, dict[str, int]] = {
            t: {p: 0 for p in all_labels} for t in all_labels
        }

        with self.db_lock:
            conn = self._ensure_connection()
            rows = conn.execute(
                """
                SELECT e.message_id,
                       e.label AS true_label,
                       e.extract_ok AS extract_ok,
                       COALESCE(l.label, 'email') AS pred_label
                FROM eval_labels e
                LEFT JOIN labels l ON l.message_id = e.message_id
                """
            ).fetchall()

        total_evaluated = len(rows)
        extract_checked = 0
        extract_correct = 0

        for r in rows:
            t_lbl = r["true_label"] if r["true_label"] in all_labels else "email"
            p_lbl = r["pred_label"] if r["pred_label"] in all_labels else "email"
            matrix[t_lbl][p_lbl] += 1
            if r["extract_ok"] is not None:
                extract_checked += 1
                if int(r["extract_ok"]) == 1:
                    extract_correct += 1

        true_emails_total = sum(matrix["email"].values())
        emails_as_promo = matrix["email"]["promotion"]
        email_as_promo_rate = (
            (emails_as_promo / true_emails_total) * 100.0 if true_emails_total > 0 else 0.0
        )

        true_promos_total = sum(matrix["promotion"].values())
        promos_detected = matrix["promotion"]["promotion"]
        promo_recall = (
            (promos_detected / true_promos_total) * 100.0 if true_promos_total > 0 else 100.0
        )

        extraction_accuracy = (
            (extract_correct / extract_checked) * 100.0 if extract_checked > 0 else 100.0
        )

        correct_total = sum(matrix[k][k] for k in all_labels)
        overall_accuracy = (
            (correct_total / total_evaluated) * 100.0 if total_evaluated > 0 else 0.0
        )

        return {
            "ok": True,
            "total_evaluated": total_evaluated,
            "overall_accuracy_pct": round(overall_accuracy, 2),
            "real_email_misfiled_as_promotion_pct": round(email_as_promo_rate, 2),
            "promotion_recall_pct": round(promo_recall, 2),
            "extraction_accuracy_pct": round(extraction_accuracy, 2),
            "extract_checked": extract_checked,
            "extract_correct": extract_correct,
            "confusion_matrix": matrix,
            "gates_passed": bool(
                email_as_promo_rate <= 1.0
                and promo_recall >= 90.0
                and extraction_accuracy >= 90.0
            ),
        }

    # ── Unsubscribe Extraction, Target Lookup & Direct Execution ─────────
    def extract_unsubscribe_info(self, message_id: str) -> dict[str, Any]:
        """
        Extracts RFC 2369 / RFC 8058 (`List-Unsubscribe`, `List-Unsubscribe-Post`) headers
        plus HTML/plain-text footer unsubscribe links for a stored email message.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "available": False, "error": "Profile is locked.", "methods": []}

        mid = (message_id or "").strip()
        if not mid:
            return {"ok": False, "available": False, "error": "Missing message_id.", "methods": []}

        with self.db_lock:
            conn = self._ensure_connection()
            row = conn.execute(
                """
                SELECT m.id, m.account_id, m.from_addr, m.from_name, m.subject,
                       m.body_text, m.has_html, m.list_unsubscribe,
                       COALESCE(m.list_unsubscribe_post, '') AS list_unsubscribe_post,
                       COALESCE(ac.email, '') AS account_email
                FROM messages m
                LEFT JOIN accounts ac ON ac.id = m.account_id
                WHERE m.id = ?
                """,
                (mid,),
            ).fetchone()
            if not row:
                return {"ok": False, "available": False, "error": f"Message {mid} not found.", "methods": []}
            msg_dict = dict(row)
            parts_rows = conn.execute("SELECT kind, text FROM parts WHERE message_id = ?", (mid,)).fetchall()
            parts = {r["kind"]: r["text"] for r in parts_rows}

        hdr_unsub = str(msg_dict.get("list_unsubscribe") or "")
        hdr_post = str(msg_dict.get("list_unsubscribe_post") or "")
        parsed_hdr = _parse_list_unsubscribe_header(hdr_unsub)
        header_http_urls: list[str] = list(parsed_hdr["http_urls"])
        header_mailto: list[dict[str, str]] = list(parsed_hdr["mailto_entries"])
        one_click_post = bool(
            "one-click" in hdr_post.lower()
            and any(u.lower().startswith(("https://", "http://127.0.0.1:", "http://localhost:")) for u in header_http_urls)
        )

        body_http_links: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        html_file = self._current_mail_html_dir() / f"{mid}.html"
        if html_file.exists():
            try:
                raw_html = html_file.read_text(encoding="utf-8", errors="replace")
                parser = _UnsubLinkHTMLParser()
                parser.feed(raw_html)
                parser.close()
                total_a = max(1, len(parser.anchors))
                scored_anchors: list[dict[str, Any]] = []
                for anc in parser.anchors:
                    href = str(anc.get("href") or "").strip()
                    low_href = href.lower()
                    if low_href.startswith("mailto:"):
                        pm = _parse_mailto_uri(href)
                        label_comb = f"{anc.get('text', '')} {anc.get('meta', '')} {anc.get('pre_context', '')}"
                        if pm and _UNSUB_CONTEXT_RE.search(label_comb):
                            if not any(m["to"].lower() == pm["to"].lower() for m in header_mailto):
                                header_mailto.append(pm)
                        continue
                    label_full = f"{anc.get('text', '')} {anc.get('meta', '')}".strip()
                    pos_ratio = (int(anc.get("idx") or 0) + 1) / float(total_a)
                    sc = _score_unsubscribe_candidate(href, label_full, str(anc.get("pre_context") or ""), pos_ratio)
                    if sc >= 5:
                        scored_anchors.append(
                            {
                                "url": href,
                                "label": (anc.get("text") or anc.get("meta") or "Unsubscribe link")[:100],
                                "score": sc,
                                "idx": int(anc.get("idx") or 0),
                            }
                        )
                scored_anchors.sort(key=lambda x: (-int(x["score"]), -int(x["idx"])))
                for sa in scored_anchors:
                    if sa["url"] not in seen_urls:
                        seen_urls.add(sa["url"])
                        body_http_links.append({"url": sa["url"], "label": sa["label"], "score": sa["score"]})
                        if len(body_http_links) >= 5:
                            break
            except Exception:
                pass

        # Fallback scan over plain text / footer part for plain URLs near unsubscribe phrases
        combined_plain = "\n".join(x for x in (parts.get("footer") or "", msg_dict.get("body_text") or "", parts.get("new") or "") if x)
        plain_lines = combined_plain.splitlines()
        for li, ln in enumerate(plain_lines):
            window = " ".join(plain_lines[max(0, li - 1) : min(len(plain_lines), li + 2)])
            if not (_UNSUB_STRONG_RE.search(window) or _UNSUB_PREF_RE.search(window)):
                continue
            for m_u in re.finditer(r"https?://[^\s<>\"')\]]+", ln, flags=re.I):
                u = html_lib.unescape(m_u.group(0).rstrip(".,;"))
                if u not in seen_urls and not _UNSUB_NEGATIVE_RE.search(u):
                    seen_urls.add(u)
                    body_http_links.append({"url": u, "label": "Unsubscribe URL from email text", "score": 8})
                    if len(body_http_links) >= 6:
                        break
            for m_mt in re.finditer(r"mailto:[^\s<>\"')\]]+", ln, flags=re.I):
                pm = _parse_mailto_uri(html_lib.unescape(m_mt.group(0).rstrip(".,;")))
                if pm and not any(m["to"].lower() == pm["to"].lower() for m in header_mailto):
                    header_mailto.append(pm)

        methods: list[dict[str, Any]] = []
        seen_method_keys: set[tuple[str, str]] = set()

        if one_click_post:
            first_https = next(
                (u for u in header_http_urls if u.lower().startswith(("https://", "http://127.0.0.1:", "http://localhost:"))),
                header_http_urls[0],
            )
            methods.append(
                {
                    "type": "one_click_post",
                    "url": first_https,
                    "post_body": "List-Unsubscribe=One-Click",
                    "label": "RFC 8058 One-Click POST",
                    "score": 100,
                }
            )
            seen_method_keys.add(("one_click_post", first_https))

        # Body HTML/text links often reflect the visual footer button/link; header HTTP URLs reflect RFC 2369 link
        for bl in body_http_links:
            u = bl["url"]
            if ("https_link", u) not in seen_method_keys:
                seen_method_keys.add(("https_link", u))
                methods.append(
                    {
                        "type": "https_link",
                        "url": u,
                        "label": bl["label"],
                        "score": 80 + min(15, int(bl.get("score") or 0)),
                    }
                )
        for hu in header_http_urls:
            if ("https_link", hu) not in seen_method_keys:
                seen_method_keys.add(("https_link", hu))
                methods.append(
                    {
                        "type": "https_link",
                        "url": hu,
                        "label": "List-Unsubscribe header URL",
                        "score": 88,
                    }
                )
        for mt in header_mailto:
            key = ("mailto", mt["to"].lower())
            if key not in seen_method_keys:
                seen_method_keys.add(key)
                methods.append(
                    {
                        "type": "mailto",
                        "mailto": mt["mailto"],
                        "to": mt["to"],
                        "subject": mt["subject"],
                        "body": mt["body"],
                        "label": f"Email unsubscribe to {mt['to']}",
                        "score": 75,
                    }
                )

        preferred = methods[0]["type"] if methods else "none"
        return {
            "ok": True,
            "available": bool(methods),
            "message_id": mid,
            "account_id": msg_dict.get("account_id") or "",
            "account_email": msg_dict.get("account_email") or "",
            "from_addr": msg_dict.get("from_addr") or "",
            "from_name": msg_dict.get("from_name") or "",
            "subject": msg_dict.get("subject") or "(no subject)",
            "one_click_post": one_click_post,
            "preferred_method": preferred,
            "header_http_urls": header_http_urls,
            "header_mailto": header_mailto,
            "body_http_links": body_http_links,
            "methods": methods,
        }

    def find_unsubscribe_targets(
        self,
        query: str = "",
        message_id: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Finds candidate emails in `mail.sqlite` matching `message_id` or a sender/brand query."""
        if not self.passwords.unlocked:
            return []

        mid_clean = (message_id or "").strip()
        q_clean = re.sub(r"\s+", " ", (query or "").strip())
        candidate_mids: list[str] = []
        if mid_clean:
            candidate_mids.append(mid_clean)

        if q_clean:
            with self.db_lock:
                conn = self._ensure_connection()
                like_tok = f"%{q_clean.lower()}%"
                rows = conn.execute(
                    """
                    SELECT m.id,
                           COALESCE(l.label, 'email') AS label,
                           m.list_unsubscribe,
                           m.date
                    FROM messages m
                    LEFT JOIN labels l ON l.message_id = m.id
                    WHERE m.hidden = 0
                      AND (
                          LOWER(m.from_addr) LIKE ?
                          OR LOWER(m.from_name) LIKE ?
                          OR LOWER(m.subject) LIKE ?
                      )
                    ORDER BY
                        (CASE WHEN COALESCE(l.label, 'email') = 'promotion' THEN 1 ELSE 0 END) DESC,
                        (CASE WHEN m.list_unsubscribe != '' THEN 1 ELSE 0 END) DESC,
                        m.date DESC
                    LIMIT ?
                    """,
                    (like_tok, like_tok, like_tok, max(3, int(limit) * 2)),
                ).fetchall()
                for r in rows:
                    if r["id"] not in candidate_mids:
                        candidate_mids.append(str(r["id"]))

            if len(candidate_mids) < limit:
                fts_res = self.search_messages(q_clean, limit=max(5, int(limit) * 2))
                for sr in fts_res.get("rows") or []:
                    smid = str(sr.get("id") or "")
                    if smid and smid not in candidate_mids:
                        candidate_mids.append(smid)

        out: list[dict[str, Any]] = []
        for cid in candidate_mids[: max(6, int(limit) * 2)]:
            info = self.extract_unsubscribe_info(cid)
            if info.get("ok"):
                out.append(info)
        out.sort(key=lambda x: (0 if x.get("available") else 1, 0 if x.get("one_click_post") else 1))
        return out[:limit]

    def _send_unsubscribe_mailto(self, account_id: str, to_addr: str, subject: str, body: str) -> dict[str, Any]:
        """Sends an RFC 2369 `mailto:` List-Unsubscribe message via authenticated SMTP."""
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        with self.db_lock:
            conn = self._ensure_connection()
            acct = (
                conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
                if account_id
                else conn.execute("SELECT * FROM accounts ORDER BY rowid ASC LIMIT 1").fetchone()
            )
            if not acct:
                return {"ok": False, "error": "No mail account configured."}
            acct_dict = dict(acct)

            now = time.time()
            settings = self.get_mail_settings()
            hourly_limit = int(settings.get("sends_per_hour_limit") or 20)
            sent_last_hour = conn.execute(
                "SELECT COUNT(*) AS c FROM outbox WHERE account_id = ? AND status = 'sent' AND sent_at >= ?",
                (acct_dict["id"], now - 3600.0),
            ).fetchone()["c"]
            if int(sent_last_hour) >= hourly_limit:
                return {"ok": False, "error": f"Rate limit exceeded ({hourly_limit} sends/hour)."}

            outbox_id = f"out-unsub-{uuid.uuid4().hex[:10]}"
            conn.execute(
                """
                INSERT INTO outbox (
                    id, account_id, to_json, cc_json, bcc_json, subject, body,
                    in_reply_to, "references", status, error, created_at, send_after, sent_at
                ) VALUES (?, ?, ?, '[]', '[]', ?, ?, '', '', 'queued', '', ?, ?, 0.0)
                """,
                (outbox_id, acct_dict["id"], json.dumps([to_addr]), subject, body, now, now),
            )
            conn.commit()

        return self._execute_outbox_send(outbox_id)

    def hide_sender_messages(self, sender_email: str) -> dict[str, Any]:
        """Archives/hides all local messages from a specific sender address without deleting server mail."""
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}
        addr = (sender_email or "").strip().lower()
        if not addr:
            return {"ok": False, "error": "Missing sender email address."}
        with self.db_lock:
            conn = self._ensure_connection()
            cur = conn.execute(
                "UPDATE messages SET hidden = 1 WHERE LOWER(from_addr) = ? AND hidden = 0",
                (addr,),
            )
            conn.commit()
            count = int(cur.rowcount or 0)
        return {"ok": True, "sender": addr, "hidden_count": count}

    def execute_unsubscribe_direct(
        self,
        message_id: str,
        url: str = "",
        method_type: str = "",
        archive_sender: bool = False,
    ) -> dict[str, Any]:
        """
        Executes a confirmed email unsubscribe action:
        - `one_click_post`: RFC 8058 POST (`List-Unsubscribe=One-Click`) directly to the verified header URL.
        - `mailto`: sends the List-Unsubscribe email from the receiving account via SMTP.
        - `https_link`: validates the URL against the message's extracted methods and returns
          `needs_browser_actor=True` so the live browser WebView executes/confirms on-page.
        """
        self.passwords._check_autolock()
        if not self.passwords.unlocked:
            return {"ok": False, "error": "Profile is locked."}

        info = self.extract_unsubscribe_info(message_id)
        if not info.get("ok"):
            return {"ok": False, "error": info.get("error") or "Message not found."}
        methods: list[dict[str, Any]] = list(info.get("methods") or [])
        if not methods:
            if archive_sender and info.get("from_addr"):
                arch = self.hide_sender_messages(str(info["from_addr"]))
                return {"ok": True, "executed": True, "method": "archive_local", **arch}
            return {
                "ok": False,
                "error": "No unsubscribe header or link found in this email.",
                "from_addr": info.get("from_addr") or "",
            }

        req_url = (url or "").strip()
        req_type = (method_type or "").strip().lower()
        chosen: dict[str, Any] | None = None
        if req_url:
            for m in methods:
                if (m.get("url") == req_url or m.get("mailto") == req_url) and (not req_type or m.get("type") == req_type):
                    chosen = m
                    break
            if chosen is None:
                return {
                    "ok": False,
                    "error": "Requested URL is not an authorized unsubscribe target extracted from this email.",
                }
        else:
            if req_type:
                for m in methods:
                    if m.get("type") == req_type:
                        chosen = m
                        break
            if chosen is None:
                chosen = methods[0]

        ctype = str(chosen.get("type") or "")
        fallback_mailto = next((m for m in methods if m.get("type") == "mailto"), None)
        fallback_https = next((m for m in methods if m.get("type") == "https_link" and m.get("url") != chosen.get("url")), None)

        if ctype == "one_click_post":
            target_u = str(chosen.get("url") or "")
            if not target_u.lower().startswith(("https://", "http://")):
                return {"ok": False, "error": "Invalid one-click unsubscribe URL."}
            try:
                req = urllib.request.Request(
                    target_u,
                    data=b"List-Unsubscribe=One-Click",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "Mozilla/5.0 (compatible; SatzBrowser/0.7)",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    status_code = int(getattr(resp, "status", 200) or 200)
                    body_raw = resp.read(8192).decode("utf-8", errors="replace")
                    body_excerpt = re.sub(r"\s+", " ", strip_html_tags(body_raw)).strip()[:240]
                if 200 <= status_code < 400:
                    hidden_res = (
                        self.hide_sender_messages(str(info["from_addr"]))
                        if archive_sender and info.get("from_addr")
                        else {}
                    )
                    return {
                        "ok": True,
                        "executed": True,
                        "method": "one_click_post",
                        "url": target_u,
                        "http_status": status_code,
                        "excerpt": body_excerpt,
                        "from_addr": info.get("from_addr") or "",
                        "archived_count": int(hidden_res.get("hidden_count") or 0),
                    }
            except Exception as exc:
                # Fall through cleanly to browser link or mailto fallback
                fb_url = (fallback_https or {}).get("url") or (
                    next((m.get("url") for m in methods if m.get("type") == "https_link"), "")
                )
                if fb_url:
                    return {
                        "ok": True,
                        "executed": False,
                        "needs_browser_actor": True,
                        "method": "https_link",
                        "url": fb_url,
                        "label": "Unsubscribe link (browser fallback after POST error)",
                        "post_error": str(exc),
                        "from_addr": info.get("from_addr") or "",
                        "message_id": message_id,
                        "fallback_mailto": fallback_mailto,
                    }
                if fallback_mailto:
                    chosen = fallback_mailto
                    ctype = "mailto"
                else:
                    return {"ok": False, "error": f"One-Click POST failed: {exc}"}

        if ctype == "mailto":
            send_res = self._send_unsubscribe_mailto(
                account_id=str(info.get("account_id") or ""),
                to_addr=str(chosen.get("to") or ""),
                subject=str(chosen.get("subject") or "Unsubscribe"),
                body=str(chosen.get("body") or "Unsubscribe"),
            )
            if send_res.get("ok"):
                hidden_res = (
                    self.hide_sender_messages(str(info["from_addr"]))
                    if archive_sender and info.get("from_addr")
                    else {}
                )
                return {
                    "ok": True,
                    "executed": True,
                    "method": "mailto",
                    "sent_to": chosen.get("to") or "",
                    "from_addr": info.get("from_addr") or "",
                    "outbox_id": send_res.get("outbox_id") or "",
                    "archived_count": int(hidden_res.get("hidden_count") or 0),
                }
            return {
                "ok": False,
                "error": send_res.get("error") or "Failed to send mailto unsubscribe.",
                "fallback_url": (fallback_https or {}).get("url") or "",
            }

        if ctype == "https_link":
            target_u = str(chosen.get("url") or "")
            if not target_u.lower().startswith(("https://", "http://")):
                return {"ok": False, "error": "Invalid https unsubscribe URL."}
            return {
                "ok": True,
                "executed": False,
                "needs_browser_actor": True,
                "method": "https_link",
                "url": target_u,
                "label": str(chosen.get("label") or "Unsubscribe link"),
                "from_addr": info.get("from_addr") or "",
                "subject": info.get("subject") or "",
                "message_id": message_id,
                "fallback_mailto": fallback_mailto,
            }

        return {"ok": False, "error": f"Unsupported unsubscribe method: {ctype}"}

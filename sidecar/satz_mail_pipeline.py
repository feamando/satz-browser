from __future__ import annotations

import datetime
import json
import os
import queue
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable


LABELS = ["email", "ping", "information", "promotion"]
LABEL_TO_ID = {lbl: idx for idx, lbl in enumerate(LABELS)}
ID_TO_LABEL = {idx: lbl for idx, lbl in enumerate(LABELS)}

CONFIDENCE_THRESHOLD = 0.75
PROMOTION_THRESHOLD = 0.90
MIN_TRAINING_SAMPLES = 50
RETRAIN_THRESHOLD = 20

MAX_SEQ_LENGTH = 256
BATCH_SIZE = 16
LEARNING_RATE = 2e-5
NUM_EPOCHS = 3

# Appendix A.2: Ping platform map (sender domain -> platform, parent-domain fallback)
PING_PLATFORM_MAP: dict[str, str] = {
    "linkedin.com": "LinkedIn",
    "slack.com": "Slack",
    "twitter.com": "Twitter",
    "x.com": "X",
    "github.com": "GitHub",
    "discord.com": "Discord",
    "discordapp.com": "Discord",
    "facebook.com": "Facebook",
    "facebookmail.com": "Facebook",
    "instagram.com": "Instagram",
    "notion.so": "Notion",
    "figma.com": "Figma",
    "asana.com": "Asana",
    "trello.com": "Trello",
    "atlassian.com": "Atlassian",
    "atlassian.net": "Atlassian",
    "jira.com": "Jira",
    "whatsapp.com": "WhatsApp",
    "telegram.org": "Telegram",
    "zoom.us": "Zoom",
    "teams.microsoft.com": "Microsoft Teams",
    "microsoft.com": "Microsoft",
    "google.com": "Google",
    "youtube.com": "YouTube",
    "reddit.com": "Reddit",
    "redditmail.com": "Reddit",
    "medium.com": "Medium",
    "pinterest.com": "Pinterest",
    "tiktok.com": "TikTok",
    "snapchat.com": "Snapchat",
    "quora.com": "Quora",
    "stackoverflow.com": "Stack Overflow",
    "bitbucket.org": "Bitbucket",
    "gitlab.com": "GitLab",
    "linear.app": "Linear",
    "xing.com": "XING",
    "meetup.com": "Meetup",
    "calendly.com": "Calendly",
}

# Appendix A.3: Extraction rules
ORDER_NUMBER_PATTERNS = [
    re.compile(r"order\s*#?\s*([A-Z0-9]*\d[A-Z0-9-]{2,})", re.IGNORECASE),
    re.compile(r"order\s+number[:\s#]*([A-Z0-9]*\d[A-Z0-9-]{2,})", re.IGNORECASE),
    re.compile(r"#?(\d{3}-\d{7}-\d{7})"),  # Amazon
    re.compile(r"confirmation\s*#?\s*([A-Z0-9]{6,})", re.IGNORECASE),
    re.compile(r"receipt\s+#?\s*([A-Z0-9-]{6,})", re.IGNORECASE),
    re.compile(r"bestell(?:nummer|nr\.?)[:\s#]*([A-Z0-9-]{5,})", re.IGNORECASE),  # German
    re.compile(r"auftrags(?:nummer|nr\.?)[:\s#]*([A-Z0-9-]{5,})", re.IGNORECASE),  # German
]

TRACKING_NUMBER_PATTERNS = [
    re.compile(r"(1Z[A-Z0-9]{16})"),  # UPS (case-sensitive)
    re.compile(r"(JJD\d{18})", re.IGNORECASE),  # DHL
    re.compile(r"tracking\s*#?\s*:?\s*([A-Z0-9]{10,})", re.IGNORECASE),
    re.compile(r"track(?:ing)?\s+number[:\s#]*([A-Z0-9]{10,})", re.IGNORECASE),
    re.compile(r"sendungsnummer[:\s#]*([A-Z0-9]{10,})", re.IGNORECASE),  # German
    re.compile(r"\b(\d{20,22})\b"),
    re.compile(r"\b(\d{12,15})\b"),
]

TRACKING_URL_PATTERNS = [
    re.compile(r"(https?://\S*(?:track|sendungsverfolgung|piececode|dhl\.de|ups\.com|fedex\.com|myhermes\.de|dpd\.de)\S*)", re.IGNORECASE),
]

MERCHANTS = [
    "Amazon",
    "eBay",
    "Shopify",
    "Stripe",
    "PayPal",
    "Apple",
    "Uber",
    "DoorDash",
    "Walmart",
    "Target",
    "Zalando",
    "Otto",
    "MediaMarkt",
    "IKEA",
    "HelloFresh",
    "Lieferando",
    "DHL",
    "UPS",
    "FedEx",
    "Hermes",
    "DPD",
]

STATUS_RULES: list[tuple[str, list[str]]] = [
    ("delivered", ["delivered", "zugestellt"]),
    ("out for delivery", ["out for delivery", "in zustellung"]),
    ("shipped", ["shipped", "on its way", "versandt", "unterwegs"]),
    ("cancelled", ["cancelled", "canceled", "storniert"]),
    ("refunded", ["refund", "refunded", "erstattung"]),
    (
        "ordered",
        [
            "order confirmed",
            "bestellbestätigung",
            "thank you for your order",
            "vielen dank für ihre bestellung",
        ],
    ),
]

VOUCHER_CODE_PATTERNS = [
    re.compile(r"(?:promo\s+code|gutscheincode|rabattcode|coupon\s+code|code|coupon|gutschein)[:\s]+([A-Z0-9-]{4,20})\b", re.IGNORECASE),
    re.compile(r"\buse\s+(?:code\s+)?([A-Z0-9-]{4,20})\s+(?:at|for|to|and)\b", re.IGNORECASE),
]

DISCOUNT_VALUE_PATTERNS = [
    re.compile(r"(\d{1,3}\s?%)\s*(?:off|rabatt|discount)", re.IGNORECASE),
    re.compile(r"save\s+(\d{1,3}%)", re.IGNORECASE),
    re.compile(r"([$€£]\s?\d+(?:[.,]\d{2})?)\s*(?:off|rabatt)", re.IGNORECASE),
    re.compile(r"(\d+(?:[.,]\d{2})?\s?€)\s*(?:off|rabatt)", re.IGNORECASE),
    re.compile(r"\b(\d{1,2}\s?%)\b", re.IGNORECASE),
]

EXPIRY_PATTERNS = [
    re.compile(
        r"(?:valid|expires?|ends?|gültig)\s+(?:until|till|bis|on|through)?\s*:?\s*(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:valid|expires?|ends?|gültig)\s+(?:until|till|bis|on|through)?\s*:?\s*([0-9]{1,2}[./-][0-9]{1,2}(?:[./-][0-9]{2,4})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:valid|expires?|ends?|gültig)?\s*(?:until|till|bis|through)\s+([A-ZÄÖÜ][a-zäöüß]+\s+\d{1,2}(?:,?\s*\d{4})?|\d{1,2}\.?\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+\d{4})?)",
        re.IGNORECASE,
    ),
]

TOTAL_PATTERNS = [
    re.compile(
        r"(?:total|gesamtbetrag|gesamtsumme|summe|amount\s+paid|betrag)[:\s]*((?:[$€£]|EUR|USD|GBP)\s?\d+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?\s?(?:[$€£]|EUR|USD|GBP))",
        re.IGNORECASE,
    ),
]

REJECTED_CODES = {
    "ORDER",
    "NUMBER",
    "CODE",
    "COUPON",
    "PROMO",
    "HTTPS",
    "HTTP",
    "EMAIL",
    "CLICK",
    "HERE",
    "GUTSCHEIN",
    "GUTSCHEINCODE",
    "RABATT",
    "VALID",
    "UNTIL",
    "TOTAL",
    "TRACKING",
    "STATUS",
    "BESTELLNUMMER",
    "AUFTRAGSNUMMER",
    "SENDUNGSNUMMER",
    "YOUR",
    "THIS",
    "THAT",
    "WITH",
    "FROM",
    "SHOP",
    "FREE",
}

# Appendix A.4: Free-mail domains (no organisation entity)
FREE_MAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "protonmail.com",
    "proton.me",
    "mail.com",
    "yandex.com",
    "gmx.com",
    "gmx.de",
    "gmx.net",
    "web.de",
    "t-online.de",
    "zoho.com",
}

AUTOMATED_LOCAL_PARTS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notifications",
    "notification",
    "alerts",
    "alert",
    "mailer-daemon",
    "postmaster",
    "bounce",
)


def is_valid_extracted_code(code: str) -> bool:
    """
    Appendix A.3: Code patterns must reject common words (`ORDER`, `CODE`, `HTTPS`)
    and require at least one digit or a length of 6+.
    """
    c = (code or "").strip().strip(".,;:!?)(")
    if len(c) < 4:
        return False
    c_up = c.upper()
    if c_up in REJECTED_CODES:
        return False
    has_digit = any(ch.isdigit() for ch in c)
    if not has_digit and len(c) < 6:
        return False
    return True


def match_ping_platform(from_addr: str) -> str | None:
    """
    Appendix A.2: Maps sender domain to platform with parent-domain fallback.
    """
    addr = (from_addr or "").strip().lower()
    dom = addr.split("@")[-1] if "@" in addr else addr
    dom = dom.strip("<> ")
    if not dom:
        return None
    if dom in PING_PLATFORM_MAP:
        return PING_PLATFORM_MAP[dom]
    parts = dom.split(".")
    for i in range(1, len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in PING_PLATFORM_MAP:
            return PING_PLATFORM_MAP[parent]
    return None


# ── Section 4.5.2: Split into `new`, `quote`, `signature`, `footer` (EN & DE) ──

QUOTE_HEADER_LINE_RE = re.compile(
    r"^(?:"
    r"On\s+.+?\bwrote:\s*$|"
    r"Am\s+.+?\bschrieb\s+.+?:\s*$|"
    r"-{2,}\s*(?:Original Message|Ursprüngliche Nachricht|Forwarded message|Weitergeleitete Nachricht)\s*-{2,}|"
    r"_{5,}\s*$|"
    r"(?:From|Von):\s+.+"
    r")",
    re.IGNORECASE,
)

SECOND_HEADER_FOLLOWUP_RE = re.compile(
    r"^(?:Sent|Gesendet|Date|Datum|To|An|Subject|Betreff):\s+",
    re.IGNORECASE,
)

SIGNATURE_CLOSING_RE = re.compile(
    r"^(?:"
    r"Best(?:\s+regards|\s+wishes)?|"
    r"Kind\s+regards|Warm\s+regards|Regards|"
    r"Many\s+thanks|Thanks(?:\s+a\s+lot|\s+so\s+much|\s+again)?|Thank\s+you|"
    r"Cheers|Sincerely|Yours(?:\s+truly|\s+sincerely)?|"
    r"Viele\s+Grüße|Beste\s+Grüße|Mit\s+freundlichen\s+Grüßen|"
    r"Herzliche\s+Grüße|Liebe\s+Grüße|Schöne\s+Grüße|"
    r"Freundliche\s+Grüße|LG|VG|MfG"
    r")\b[,!.]?\s*$",
    re.IGNORECASE,
)

DEVICE_SIG_RE = re.compile(
    r"^(?:"
    r"Sent\s+from\s+my\s+(?:iPhone|iPad|Galaxy|Android|BlackBerry).*|"
    r"Von\s+meinem\s+(?:iPhone|iPad|Galaxy|Samsung|Smartphone)\s+gesendet.*|"
    r"Get\s+Outlook\s+for\s+(?:iOS|Android).*"
    r")$",
    re.IGNORECASE,
)

FOOTER_LINE_RE = re.compile(
    r"(?:"
    r"\bunsubscribe\b|\babmelden\b|\bnewsletter\s+abbestellen\b|"
    r"\bview\s+in\s+browser\b|\bim\s+browser\s+ansehen\b|"
    r"\bprivacy\s+policy\b|\bdatenschutzerklärung\b|\bdatenschutz\b|"
    r"\bimpressum\b|\bmanage\s+preferences\b|\beinstellungen\s+verwalten\b|"
    r"\byou\s+are\s+receiving\s+this\s+email\s+because\b|"
    r"\bsie\s+erhalten\s+diese\s+e-mail\b|"
    r"\bhandelsregister\b|\bregistergericht\b|\bust-idnr\b"
    r")",
    re.IGNORECASE,
)

GREETING_LINE_RE = re.compile(
    r"^\s*(?:Hi|Hello|Dear|Hey|Good\s+(?:morning|afternoon|evening)|Hallo|Guten\s+Tag|Liebe[r]?|Sehr\s+geehrte[r]?|Moin)\b",
    re.IGNORECASE,
)


def extract_html_quote_blocks(raw_html: str) -> tuple[str, str]:
    """
    Extracts Gmail (`div.gmail_quote`) and Outlook (`div#divRplyFwdMsg`, `#appendonsend`)
    quote blocks from HTML when present.
    Returns `(html_without_quotes, extracted_quote_text)`.
    """
    if not raw_html:
        return "", ""
    from satz_mail import strip_html_tags

    quote_chunks: list[str] = []
    cleaned = raw_html
    patterns = [
        re.compile(r'(<div\b[^>]*class=["\'][^"\']*gmail_quote[^"\']*["\'][^>]*>.*)', re.IGNORECASE | re.DOTALL),
        re.compile(r'(<div\b[^>]*id=["\'](?:divRplyFwdMsg|appendonsend)["\'][^>]*>.*)', re.IGNORECASE | re.DOTALL),
    ]
    for pat in patterns:
        m = pat.search(cleaned)
        if m:
            q_html = m.group(1)
            q_txt = strip_html_tags(q_html)
            if q_txt:
                quote_chunks.append(q_txt)
            cleaned = cleaned[: m.start(1)]
    return cleaned, "\n\n".join(quote_chunks).strip()


def split_email_parts(
    body_text: str,
    raw_html: str | None = None,
    gemma_split_fn: Callable[[str], int | None] | None = None,
) -> dict[str, str]:
    """
    Section 4.5.2 (M12): Splits an email into `new`, `quote`, `signature`, `footer`
    supporting English and German rules, Gmail/Outlook HTML reply containers,
    and Gemma fallback for ambiguous >4,000-character bodies with a second greeting.
    """
    html_quote = ""
    working_text = (body_text or "").replace("\r\n", "\n").replace("\r", "\n")

    if raw_html and ("gmail_quote" in raw_html or "divRplyFwdMsg" in raw_html or "appendonsend" in raw_html):
        from satz_mail import strip_html_tags

        cleaned_html, html_quote = extract_html_quote_blocks(raw_html)
        if html_quote:
            stripped_main = strip_html_tags(cleaned_html)
            if stripped_main:
                working_text = stripped_main

    raw_lines = working_text.split("\n")

    # Join wrapped "On ... \n wrote:" or "Am ... \n schrieb ...:" lines
    lines: list[str] = []
    i = 0
    while i < len(raw_lines):
        cur = raw_lines[i]
        if (
            i + 1 < len(raw_lines)
            and re.match(r"^\s*(?:On|Am)\s+.+$", cur)
            and not cur.rstrip().endswith(":")
            and re.search(r"\b(?:wrote|schrieb)\b.*:\s*$", raw_lines[i + 1], re.IGNORECASE)
        ):
            lines.append(cur.rstrip() + " " + raw_lines[i + 1].lstrip())
            i += 2
            continue
        lines.append(cur)
        i += 1

    # 1. Separate Quote block and `>` quoted lines
    pre_quote_lines: list[str] = []
    quote_lines: list[str] = []
    in_quote_block = False

    idx = 0
    while idx < len(lines):
        ln = lines[idx]
        stripped = ln.strip()

        if in_quote_block:
            quote_lines.append(ln)
            idx += 1
            continue

        # Check `From:` / `Von:` header block (requires follow-up Sent/To/Subject within next 4 lines)
        if re.match(r"^(?:From|Von):\s+.+", stripped, re.IGNORECASE):
            lookahead = [lines[j].strip() for j in range(idx + 1, min(len(lines), idx + 5))]
            if any(SECOND_HEADER_FOLLOWUP_RE.match(la) for la in lookahead):
                in_quote_block = True
                quote_lines.append(ln)
                idx += 1
                continue

        if QUOTE_HEADER_LINE_RE.match(stripped) and not re.match(r"^(?:From|Von):", stripped, re.IGNORECASE):
            in_quote_block = True
            quote_lines.append(ln)
            idx += 1
            continue

        if stripped.startswith(">"):
            quote_lines.append(ln)
            idx += 1
            continue

        pre_quote_lines.append(ln)
        idx += 1

    # Ambiguous long body check (> 4,000 chars, no quote found yet, contains a second greeting)
    joined_pre_quote = "\n".join(pre_quote_lines)
    if not quote_lines and not html_quote and len(joined_pre_quote) > 4000:
        greeting_indices = [
            li for li, line_val in enumerate(pre_quote_lines) if GREETING_LINE_RE.match(line_val.strip())
        ]
        if len(greeting_indices) >= 2:
            split_line_idx: int | None = None
            if gemma_split_fn is not None:
                try:
                    split_line_idx = gemma_split_fn(joined_pre_quote)
                except Exception:
                    split_line_idx = None
            if split_line_idx is None or not (0 < split_line_idx < len(pre_quote_lines)):
                split_line_idx = greeting_indices[1]
            quote_lines = pre_quote_lines[split_line_idx:]
            pre_quote_lines = pre_quote_lines[:split_line_idx]

    if html_quote:
        if quote_lines:
            quote_lines.append(html_quote)
        else:
            quote_lines = [html_quote]

    # 2. Separate Footer block from `pre_quote_lines`
    # Scan from the bottom or first footer block in the lower half of the message
    footer_start: int | None = None
    for li, ln in enumerate(pre_quote_lines):
        if FOOTER_LINE_RE.search(ln):
            # Treat from this line onward as footer
            footer_start = li
            break

    if footer_start is not None:
        footer_lines = pre_quote_lines[footer_start:]
        body_and_sig_lines = pre_quote_lines[:footer_start]
    else:
        footer_lines = []
        body_and_sig_lines = pre_quote_lines

    # Trim trailing blank lines on body_and_sig_lines
    while body_and_sig_lines and not body_and_sig_lines[-1].strip():
        body_and_sig_lines.pop()

    # 3. Separate Signature from the tail of `body_and_sig_lines`
    sig_start: int | None = None
    n_lines = len(body_and_sig_lines)
    search_floor = max(0, n_lines - 10)

    for li in range(search_floor, n_lines):
        s_ln = body_and_sig_lines[li].strip()
        if body_and_sig_lines[li] == "-- " or s_ln == "--":
            sig_start = li
            break
        if DEVICE_SIG_RE.match(s_ln):
            sig_start = li
            break
        if SIGNATURE_CLOSING_RE.match(s_ln):
            tail = [x.strip() for x in body_and_sig_lines[li + 1 :] if x.strip()]
            if len(tail) <= 8 and all(len(x) <= 95 for x in tail):
                sig_start = li
                break

    if sig_start is not None:
        sig_lines = body_and_sig_lines[sig_start:]
        new_lines = body_and_sig_lines[:sig_start]
    else:
        sig_lines = []
        new_lines = body_and_sig_lines

    new_text = "\n".join(new_lines).strip()
    quote_text = "\n".join(quote_lines).strip()
    sig_text = "\n".join(sig_lines).strip()
    footer_text = "\n".join(footer_lines).strip()

    return {
        "new": new_text,
        "quote": quote_text,
        "signature": sig_text,
        "footer": footer_text,
    }


def extract_signature_metadata(signature_text: str) -> dict[str, str]:
    """
    Section 4.5.2 & 4.5.5: Extracts `role`, `company`, and `phone` from signature lines.
    """
    if not signature_text:
        return {}
    meta: dict[str, str] = {}
    phone_m = re.search(r"(?:tel\.?|phone|mobil|mobile|fon|t)?[:\s]*(\+?\d[\d\s().\-/]{7,}\d)", signature_text, re.IGNORECASE)
    if phone_m:
        meta["phone"] = re.sub(r"\s+", " ", phone_m.group(1)).strip()

    lines = [
        ln.strip()
        for ln in signature_text.splitlines()
        if ln.strip()
        and ln.strip() != "--"
        and not SIGNATURE_CLOSING_RE.match(ln.strip())
        and not DEVICE_SIG_RE.match(ln.strip())
    ]

    role_keywords = (
        "vp",
        "director",
        "manager",
        "engineer",
        "developer",
        "founder",
        "ceo",
        "cto",
        "cpo",
        "head of",
        "lead",
        "designer",
        "consultant",
        "partner",
        "professor",
        "geschäftsführer",
        "leiter",
        "entwickler",
        "berater",
    )
    for ln in lines[:5]:
        ln_low = ln.lower()
        if "@" in ln or "http://" in ln_low or "https://" in ln_low:
            continue
        if " | " in ln or " · " in ln or " at " in ln_low or " bei " in ln_low:
            sep_parts = re.split(r"\s+(?:\||·|at|bei|-)\s+", ln, maxsplit=1, flags=re.IGNORECASE)
            if len(sep_parts) == 2:
                meta.setdefault("role", sep_parts[0].strip())
                meta.setdefault("company", sep_parts[1].strip())
                continue
        if any(rk in ln_low for rk in role_keywords) and "role" not in meta:
            meta["role"] = ln
        elif any(corp in ln for corp in ("GmbH", "AG", "Inc", "Ltd", "LLC", "SE", "Corp", "UG")) and "company" not in meta:
            meta["company"] = ln

    return meta


# ── Section 4.5.4 & Appendix A.3: Rule-Based + Hertz Extraction ──────────

def extract_information_fields(
    subject: str,
    from_name: str,
    from_addr: str,
    new_text: str,
    reader_fn: Callable[[str, str], tuple[str, float]] | None = None,
) -> dict[str, tuple[str, str, float]]:
    """
    Returns `{field: (value, source, confidence)}` for `information` emails:
    `order_number`, `tracking_number`, `tracking_url`, `merchant`, `status`, `total`.
    Calls `reader_fn` (Hertz) if `order_number` or `status` is missing, accepting confidence >= 0.6.
    """
    combined = f"{subject}\n{new_text}".strip()
    out: dict[str, tuple[str, str, float]] = {}

    # 1. Order number
    for pat in ORDER_NUMBER_PATTERNS:
        for m in pat.finditer(combined):
            cand = m.group(1).strip().strip(".,;:!?)(")
            if is_valid_extracted_code(cand):
                out["order_number"] = (cand, "rule", 1.0)
                break
        if "order_number" in out:
            break

    # 2. Tracking number
    for pat in TRACKING_NUMBER_PATTERNS:
        for m in pat.finditer(combined):
            cand = m.group(1).strip().strip(".,;:!?)(")
            if is_valid_extracted_code(cand) and cand != out.get("order_number", ("", "", 0.0))[0]:
                out["tracking_number"] = (cand, "rule", 1.0)
                break
        if "tracking_number" in out:
            break

    # 3. Tracking URL
    for pat in TRACKING_URL_PATTERNS:
        m = pat.search(combined)
        if m:
            out["tracking_url"] = (m.group(1).rstrip(").,;\"'>"), "rule", 1.0)
            break

    # 4. Merchant
    haystack_merchant = f"{from_name} {from_addr} {subject} {new_text[:600]}"
    for merch in MERCHANTS:
        if re.search(rf"\b{re.escape(merch)}\b", haystack_merchant, re.IGNORECASE):
            out["merchant"] = (merch, "rule", 1.0)
            break
    if "merchant" not in out and from_name:
        out["merchant"] = (from_name.strip(), "rule", 0.8)

    # 5. Delivery status
    comb_low = combined.lower()
    for status_name, keywords in STATUS_RULES:
        if any(kw in comb_low for kw in keywords):
            out["status"] = (status_name, "rule", 1.0)
            break

    # 6. Total
    for pat in TOTAL_PATTERNS:
        m = pat.search(combined)
        if m:
            out["total"] = (m.group(1).strip(), "rule", 1.0)
            break

    # 7. Hertz fallback for missing order_number or status (confidence >= 0.6)
    if reader_fn is not None and new_text.strip():
        if "order_number" not in out:
            try:
                ans, conf = reader_fn("What is the order number?", new_text)
                clean_ans = ans.strip().strip(".,;:")
                if conf >= 0.6 and is_valid_extracted_code(clean_ans):
                    out["order_number"] = (clean_ans, "hertz", float(conf))
            except Exception:
                pass
        if "status" not in out:
            try:
                ans, conf = reader_fn("What is the delivery status?", new_text)
                ans_low = ans.lower()
                if conf >= 0.6:
                    for status_name, keywords in STATUS_RULES:
                        if status_name in ans_low or any(kw in ans_low for kw in keywords):
                            out["status"] = (status_name, "hertz", float(conf))
                            break
            except Exception:
                pass

    return out


def extract_promotion_fields(
    subject: str,
    from_name: str,
    from_addr: str,
    new_text: str,
    reader_fn: Callable[[str, str], tuple[str, float]] | None = None,
) -> dict[str, tuple[str, str, float]]:
    """
    Returns `{field: (value, source, confidence)}` for `promotion` emails:
    `voucher_code`, `discount_value`, `expiry`, `company`.
    Calls `reader_fn` (Hertz) if `expiry` is missing, accepting confidence >= 0.6.
    """
    combined = f"{subject}\n{new_text}".strip()
    out: dict[str, tuple[str, str, float]] = {}

    for pat in VOUCHER_CODE_PATTERNS:
        for m in pat.finditer(combined):
            cand = m.group(1).strip().strip(".,;:!?)(")
            if is_valid_extracted_code(cand):
                out["voucher_code"] = (cand.upper(), "rule", 1.0)
                break
        if "voucher_code" in out:
            break

    for pat in DISCOUNT_VALUE_PATTERNS:
        m = pat.search(combined)
        if m:
            out["discount_value"] = (re.sub(r"\s+", "", m.group(1)), "rule", 1.0)
            break

    for pat in EXPIRY_PATTERNS:
        m = pat.search(combined)
        if m:
            raw_exp = m.group(1).strip().rstrip(".,;")
            norm_exp = raw_exp
            m_dmy = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$", raw_exp)
            if m_dmy:
                d_val, m_val, y_val = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
                if 1 <= m_val <= 12 and 1 <= d_val <= 31:
                    norm_exp = f"{y_val:04d}-{m_val:02d}-{d_val:02d}"
            out["expiry"] = (norm_exp, "rule", 1.0)
            break

    haystack_comp = f"{from_name} {from_addr} {subject}"
    for merch in MERCHANTS:
        if re.search(rf"\b{re.escape(merch)}\b", haystack_comp, re.IGNORECASE):
            out["company"] = (merch, "rule", 1.0)
            break
    if "company" not in out:
        if from_name:
            out["company"] = (from_name.strip(), "rule", 0.9)
        elif "@" in from_addr:
            dom = from_addr.split("@")[-1].split(".")[0].capitalize()
            out["company"] = (dom, "rule", 0.7)

    if "expiry" not in out and reader_fn is not None and new_text.strip():
        try:
            ans, conf = reader_fn("Until when is the offer valid?", new_text)
            if conf >= 0.6 and ans.strip():
                out["expiry"] = (ans.strip()[:40], "hertz", float(conf))
        except Exception:
            pass

    return out


def detect_email_action_heuristic(subject: str, new_text: str) -> dict[str, Any]:
    """
    Deterministic fallback for `{needs_reply, due_date, ask}` when Gemma is not loaded.
    """
    combined = f"{subject}\n{new_text}".strip()
    has_question = "?" in new_text or bool(
        re.search(
            r"\b(?:can\s+you|could\s+you|please\s+let\s+me\s+know|please\s+confirm|kannst\s+du|können\s+sie|bitte\s+um\s+rückmeldung|bitte\s+bestätigen)\b",
            combined,
            re.IGNORECASE,
        )
    )
    due_date: str | None = None
    iso_m = re.search(r"\b(202\d-\d{2}-\d{2})\b", combined)
    if iso_m:
        due_date = iso_m.group(1)

    ask_line = ""
    if has_question:
        for ln in new_text.splitlines():
            s = ln.strip()
            if "?" in s or re.search(r"\b(?:please|bitte|confirm|bestätigen)\b", s, re.IGNORECASE):
                ask_line = s[:140]
                break
        if not ask_line:
            ask_line = subject[:140]

    return {
        "needs_reply": bool(has_question),
        "due_date": due_date,
        "ask": ask_line,
    }


def apply_classification_thresholds(pred_label: str, confidence: float) -> tuple[str, bool]:
    """
    Section 4.5.3:
    - Accept model label if confidence >= 0.75.
    - Exception for `promotion`: require >= 0.90, otherwise label `email`!
    Returns `(accepted_label, accepted_from_model)`.
    """
    lbl = (pred_label or "").strip().lower()
    if lbl not in LABELS:
        return "email", False
    conf = float(confidence or 0.0)
    if lbl == "promotion":
        if conf >= PROMOTION_THRESHOLD:
            return "promotion", True
        if conf >= CONFIDENCE_THRESHOLD:
            # Unsure promotion (0.75 <= conf < 0.90) stays in the inbox as `email`!
            return "email", True
        return "email", False
    if conf >= CONFIDENCE_THRESHOLD:
        return lbl, True
    return "email", False


class SatzMailPipeline:
    """
    Section 4.5 (M12): Background mail processing pipeline:
    1. Parse & Split (`new`, `quote`, `signature`, `footer`)
    2. 4-label Classifier (`email`, `ping`, `information`, `promotion`) with Gemma cold-start,
       training at >= 50 samples, retraining after 20 corrections, and 0.90 promotion threshold.
    3. Rule + Hertz extraction & Gemma action extraction.
    4. Brain entity linking (`person` only after reply or >= 2 `email` messages, `organization`,
       `order`, `promotion`) and Planck `Store` passage indexing.
    """

    def __init__(
        self,
        runtime: Any,
        mail_manager: Any,
        gemma_label_fn: Callable[[str, str, str, str], str] | None = None,
        model_predict_fn: Callable[[str], tuple[str, float]] | None = None,
        trainer_fn: Callable[[list[tuple[str, str]], Path, str], None] | None = None,
        start_worker: bool = True,
    ) -> None:
        self.runtime = runtime
        self.mail = mail_manager
        self.gemma_label_fn = gemma_label_fn
        self.model_predict_fn = model_predict_fn
        self.trainer_fn = trainer_fn
        self.auto_wake = start_worker

        self.lock = threading.RLock()
        self._queue: list[str] = []
        self._wake_event = threading.Event()
        self.processing_done = 0
        self.processing_total = 0
        self.is_processing = False
        self.model_version = "cold"
        self.last_retrain_at = 0.0

        self._distilbert_tok: Any = None
        self._distilbert_model: Any = None
        self._load_active_model_if_exists()

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        if start_worker:
            self._worker_thread = threading.Thread(
                target=self._pipeline_worker_loop,
                daemon=True,
                name="satz-mail-pipeline",
            )
            self._worker_thread.start()

    def stop_worker(self) -> None:
        self.auto_wake = False
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def _active_model_dir(self) -> Path:
        db_path = self.mail._current_mail_db_path()
        return db_path.parent / "mail_model" / "active"

    def _load_active_model_if_exists(self) -> None:
        mdir = self._active_model_dir()
        vfile = mdir / "version.txt"
        if vfile.exists():
            try:
                self.model_version = vfile.read_text(encoding="utf-8").strip() or "v1"
            except Exception:
                self.model_version = "v1"
            if (mdir / "config.json").exists():
                try:
                    from transformers import AutoModelForSequenceClassification, AutoTokenizer

                    self._distilbert_tok = AutoTokenizer.from_pretrained(str(mdir))
                    self._distilbert_model = AutoModelForSequenceClassification.from_pretrained(str(mdir))
                    self._distilbert_model.to("cpu")
                    self._distilbert_model.eval()
                except Exception:
                    pass
        else:
            self.model_version = "cold"
            self._distilbert_tok = None
            self._distilbert_model = None

    def get_status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "processing_done": self.processing_done,
                "processing_total": self.processing_total,
                "is_processing": self.is_processing,
                "model_version": self.model_version,
                "last_retrain_at": self.last_retrain_at,
            }

    def enqueue_messages(self, message_ids: list[str]) -> None:
        """
        Section 4.5: Runs on a queue in priority order: newest 300 first, then the rest.
        """
        if not message_ids:
            return
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            placeholders = ",".join("?" for _ in message_ids)
            rows = conn.execute(
                f"SELECT id, date FROM messages WHERE id IN ({placeholders}) ORDER BY date DESC",
                tuple(message_ids),
            ).fetchall()
            ordered_ids = [r["id"] for r in rows]

        newest_300 = ordered_ids[:300]
        rest = ordered_ids[300:]
        prioritized = newest_300 + rest

        with self.lock:
            existing = set(self._queue)
            added = [mid for mid in prioritized if mid not in existing]
            if added:
                self._queue.extend(added)
                self.processing_total += len(added)
                self.is_processing = True
        if self.auto_wake:
            self._wake_event.set()

    def process_all_queued_sync(self) -> int:
        """
        Synchronously drains the current queue (used in deterministic tests and manual sync).
        """
        processed = 0
        while True:
            with self.lock:
                if not self._queue:
                    self.is_processing = False
                    break
                mid = self._queue.pop(0)
                self.is_processing = True
            try:
                self.process_single_message(mid)
                processed += 1
            finally:
                with self.lock:
                    self.processing_done += 1
                    if not self._queue:
                        self.is_processing = False
        return processed

    def _pipeline_worker_loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=5.0)
            self._wake_event.clear()
            if self._stop_event.is_set() or not self.auto_wake:
                continue
            while not self._stop_event.is_set() and self.auto_wake:
                with self.lock:
                    if not self._queue:
                        self.is_processing = False
                        break
                    mid = self._queue.pop(0)
                    self.is_processing = True
                try:
                    self.process_single_message(mid)
                except Exception as exc:
                    self.runtime.record_error("mail_pipeline", f"{mid}: {exc}")
                finally:
                    with self.lock:
                        self.processing_done += 1
                        if not self._queue:
                            self.is_processing = False

    def format_classifier_input(self, from_str: str, subject: str, new_text: str) -> str:
        return f"[FROM] {from_str} [SUBJECT] {subject} [BODY] {(new_text or '')[:1000]}"

    def _predict_with_active_model(self, input_text: str) -> tuple[str, float] | None:
        if self.model_predict_fn is not None:
            return self.model_predict_fn(input_text)
        if self._distilbert_model is not None and self._distilbert_tok is not None:
            import torch

            inputs = self._distilbert_tok(
                input_text,
                truncation=True,
                max_length=MAX_SEQ_LENGTH,
                return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._distilbert_model(**inputs).logits
                probs = torch.softmax(logits, dim=-1)[0]
                best_idx = int(torch.argmax(probs).item())
                best_conf = float(probs[best_idx].item())
                return ID_TO_LABEL.get(best_idx, "email"), best_conf

        # Check lightweight active weights file if saved by local fallback trainer
        weights_file = self._active_model_dir() / "token_weights.json"
        if weights_file.exists():
            try:
                data = json.loads(weights_file.read_text(encoding="utf-8"))
                class_scores: dict[str, float] = {lbl: 0.0 for lbl in LABELS}
                tokens = set(re.findall(r"[a-z0-9äöüß@._-]{2,}", input_text.lower()))
                vocab: dict[str, dict[str, float]] = data.get("vocab", {})
                for tok in tokens:
                    if tok in vocab:
                        for lbl, w in vocab[tok].items():
                            class_scores[lbl] = class_scores.get(lbl, 0.0) + float(w)
                import math

                exps = {lbl: math.exp(min(20.0, s)) for lbl, s in class_scores.items()}
                total_e = sum(exps.values()) or 1.0
                best_lbl = max(LABELS, key=lambda l: exps[l])
                best_conf = exps[best_lbl] / total_e
                return best_lbl, float(best_conf)
            except Exception:
                return None
        return None

    def _label_with_gemma(
        self,
        from_str: str,
        subject: str,
        new_text: str,
        header_hints: str,
    ) -> str:
        """
        Section 4.5.3: Cold start or below threshold: Gemma labels with a fixed prompt listing
        the 4 labels and their definitions, greedy decoding, output one word. Unparseable -> `email`.
        """
        if self.gemma_label_fn is not None:
            raw_out = self.gemma_label_fn(from_str, subject, new_text, header_hints)
            word = (raw_out or "").strip().lower().split()[0] if (raw_out or "").strip() else ""
            word = re.sub(r"[^a-z]", "", word)
            return word if word in LABELS else "email"

        # If Gemma is loaded in runtime, run greedy 1-word generation
        if getattr(self.runtime, "gemma_model", None) is not None:
            try:
                prompt = (
                    "Classify this email into exactly one of these 4 labels:\n"
                    "- email: a real message from a person that may need attention\n"
                    "- ping: a notification from a platform about activity (comments, mentions, invites, PR reviews)\n"
                    "- information: orders, shipping, receipts, invoices, bookings, account or security notices\n"
                    "- promotion: marketing, newsletters, offers, discount codes\n\n"
                    f"Hints: {header_hints or 'none'}\n"
                    f"[FROM] {from_str}\n"
                    f"[SUBJECT] {subject}\n"
                    f"[BODY] {new_text[:1000]}\n\n"
                    "Output one word only (email, ping, information, or promotion):"
                )
                raw = self.runtime._generate_gemma_short(prompt, max_new_tokens=6)
                word = (raw or "").strip().lower().split()[0] if (raw or "").strip() else ""
                word = re.sub(r"[^a-z]", "", word)
                if word in LABELS:
                    return word
            except Exception:
                pass

        # Deterministic heuristic when Gemma model is not loaded in memory
        plat = match_ping_platform(from_str)
        if plat:
            return "ping"
        comb = f"{subject}\n{new_text[:1000]}".lower()
        if any(
            m.search(f"{subject}\n{new_text[:1000]}")
            for m in (ORDER_NUMBER_PATTERNS + TRACKING_NUMBER_PATTERNS)
        ) or any(w in comb for w in ("order confirmed", "bestellbestätigung", "versandt", "shipped", "invoice", "rechnung")):
            return "information"
        if ("list-unsubscribe" in (header_hints or "").lower() or "precedence: bulk" in (header_hints or "").lower()) and any(
            w in comb for w in ("% off", "rabatt", "gutschein", "promo", "sale", "deal", "newsletter", "angebot")
        ):
            return "promotion"
        return "email"

    def classify_message(
        self,
        from_name: str,
        from_addr: str,
        subject: str,
        new_text: str,
        list_unsubscribe: str = "",
    ) -> tuple[str, float, str, str]:
        """
        Returns `(label, confidence, source, model_version)`.
        """
        from_str = f"{from_name} <{from_addr}>".strip() if from_name else from_addr
        input_text = self.format_classifier_input(from_str, subject, new_text)

        hints: list[str] = []
        if list_unsubscribe:
            hints.append("List-Unsubscribe/bulk present")
        plat = match_ping_platform(from_addr)
        if plat:
            hints.append(f"platform_domain={plat}")
        header_hints = ", ".join(hints)

        pred = self._predict_with_active_model(input_text)
        if pred is not None and self.model_version != "cold":
            pred_label, pred_conf = pred
            accepted_label, accepted = apply_classification_thresholds(pred_label, pred_conf)
            if accepted:
                return accepted_label, float(pred_conf), "model", self.model_version

        # Cold start or confidence below threshold -> Gemma labels it
        gemma_lbl = self._label_with_gemma(from_str, subject, new_text, header_hints)
        return gemma_lbl, 0.85, "gemma", self.model_version

    def _get_training_samples(self, conn: sqlite3.Connection) -> list[tuple[str, str]]:
        """
        Section 4.5.3 & 4.9: Every Gemma label and every user correction is training data.
        Eval labels (`eval_labels` table) are NEVER used for training.
        """
        rows = conn.execute(
            """
            SELECT m.id, m.from_name, m.from_addr, m.subject,
                   COALESCE(p.text, m.body_text) AS new_text,
                   l.label
            FROM labels l
            JOIN messages m ON m.id = l.message_id
            LEFT JOIN parts p ON p.message_id = m.id AND p.kind = 'new'
            WHERE l.source IN ('gemma', 'user')
              AND m.id NOT IN (SELECT message_id FROM eval_labels)
            """
        ).fetchall()
        samples: list[tuple[str, str]] = []
        for r in rows:
            from_str = f"{r['from_name']} <{r['from_addr']}>".strip() if r["from_name"] else r["from_addr"]
            inp = self.format_classifier_input(from_str, r["subject"], r["new_text"])
            lbl = str(r["label"] or "email").lower()
            if lbl in LABEL_TO_ID:
                samples.append((inp, lbl))
        return samples

    def maybe_trigger_training(self, force_retrain: bool = False) -> bool:
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            unused_corr = conn.execute(
                "SELECT COUNT(*) AS c FROM corrections WHERE used_in_training = 0"
            ).fetchone()["c"]
            samples = self._get_training_samples(conn)

        should_train_initial = self.model_version == "cold" and len(samples) >= MIN_TRAINING_SAMPLES
        should_retrain = int(unused_corr) >= RETRAIN_THRESHOLD or force_retrain

        if not should_train_initial and not should_retrain:
            return False
        if len(samples) < MIN_TRAINING_SAMPLES and not force_retrain:
            return False

        self.train_classifier(samples)
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            conn.execute("UPDATE corrections SET used_in_training = 1 WHERE used_in_training = 0")
            conn.commit()
        return True

    def train_classifier(self, samples: list[tuple[str, str]]) -> str:
        """
        Section 4.5.3 & Appendix A.1:
        Trains `distilbert-base-uncased` (or injected `trainer_fn` / local weights) on `samples`,
        writes the new model to `profiles/<id>/mail_model/active` with `version.txt`, and hot-reloads.
        """
        mdir = self._active_model_dir()
        mdir.mkdir(parents=True, exist_ok=True)

        # Increment version
        cur_num = 0
        if self.model_version.startswith("v") and self.model_version[1:].isdigit():
            cur_num = int(self.model_version[1:])
        next_version = f"v{cur_num + 1}"

        if self.trainer_fn is not None:
            self.trainer_fn(samples, mdir, next_version)
        else:
            trained_hf = False
            # Use DistilBERT fine-tuning when offline cache exists and SATZ_SKIP_HF_TRAIN is not set
            if not os.environ.get("SATZ_FAST_TEST_TRAIN"):
                try:
                    import torch
                    from transformers import AutoModelForSequenceClassification, AutoTokenizer

                    tok = AutoTokenizer.from_pretrained("distilbert-base-uncased", local_files_only=True)
                    model = AutoModelForSequenceClassification.from_pretrained(
                        "distilbert-base-uncased",
                        num_labels=4,
                        local_files_only=True,
                    )
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    model.to(device)
                    model.train()
                    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

                    for _epoch in range(NUM_EPOCHS):
                        for i in range(0, len(samples), BATCH_SIZE):
                            batch = samples[i : i + BATCH_SIZE]
                            texts = [b[0] for b in batch]
                            y = torch.tensor([LABEL_TO_ID[b[1]] for b in batch], dtype=torch.long, device=device)
                            enc = tok(
                                texts,
                                padding=True,
                                truncation=True,
                                max_length=MAX_SEQ_LENGTH,
                                return_tensors="pt",
                            ).to(device)
                            optimizer.zero_grad()
                            out = model(**enc, labels=y)
                            out.loss.backward()
                            optimizer.step()

                    model.to("cpu")
                    model.eval()
                    model.save_pretrained(str(mdir))
                    tok.save_pretrained(str(mdir))
                    self._distilbert_tok = tok
                    self._distilbert_model = model
                    trained_hf = True
                except Exception:
                    trained_hf = False

            if not trained_hf:
                # Save lightweight token Naive-Bayes/log-odds weights in active dir so CPU inference works offline
                vocab: dict[str, dict[str, float]] = {}
                for text_inp, lbl in samples:
                    for tok_w in set(re.findall(r"[a-z0-9äöüß@._-]{2,}", text_inp.lower())):
                        entry = vocab.setdefault(tok_w, {})
                        entry[lbl] = entry.get(lbl, 0.0) + 0.35
                (mdir / "token_weights.json").write_text(
                    json.dumps({"version": next_version, "samples": len(samples), "vocab": vocab}),
                    encoding="utf-8",
                )

        (mdir / "version.txt").write_text(next_version + "\n", encoding="utf-8")
        self.model_version = next_version
        self.last_retrain_at = time.time()
        return next_version

    def record_user_correction(self, message_id: str, new_label: str) -> dict[str, Any]:
        """
        Section 4.5.3 & 4.8 (`POST /mail/message/<id>/label`):
        A user correction always overrides a Gemma/model label for that message,
        is stored in `corrections` with `used_in_training = 0`, and triggers retraining at 20 corrections.
        """
        lbl = (new_label or "").strip().lower()
        if lbl not in LABELS:
            raise ValueError(f"Invalid mail label: {new_label}")

        now = time.time()
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            old_row = conn.execute("SELECT label FROM labels WHERE message_id = ?", (message_id,)).fetchone()
            old_label = str(old_row["label"]) if old_row else "email"

            conn.execute(
                """
                INSERT OR REPLACE INTO labels (message_id, label, confidence, source, model_version, at)
                VALUES (?, ?, 1.0, 'user', ?, ?)
                """,
                (message_id, lbl, self.model_version, now),
            )
            conn.execute(
                """
                INSERT INTO corrections (message_id, old_label, new_label, at, used_in_training)
                VALUES (?, ?, ?, ?, 0)
                """,
                (message_id, old_label, lbl, now),
            )
            conn.commit()

        retrained = self.maybe_trigger_training()
        return {
            "ok": True,
            "message_id": message_id,
            "old_label": old_label,
            "new_label": lbl,
            "retrained": retrained,
            "model_version": self.model_version,
        }

    def _reader_fallback(self, question: str, new_text: str) -> tuple[str, float]:
        """
        Calls Hertz (`runtime.run_read("hertz (reader)", ...)`) over `new_text` as a single source.
        """
        try:
            res = self.runtime.run_read(
                "hertz (reader)",
                question,
                [{"id": "mail-inline", "url": "https://mail.local", "title": "Email", "full_text": new_text}],
            )
            return str(res.get("answer") or ""), float(res.get("confidence") or 0.7)
        except Exception:
            return "", 0.0

    def process_single_message(self, message_id: str) -> dict[str, Any] | None:
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if not row:
                return None
            msg = dict(row)
            acct_row = conn.execute("SELECT email FROM accounts WHERE id = ?", (msg["account_id"],)).fetchone()
            account_email = str(acct_row["email"] or "").lower() if acct_row else ""

            existing_lbl = conn.execute(
                "SELECT label, source FROM labels WHERE message_id = ?",
                (message_id,),
            ).fetchone()

        html_path = self.mail._current_mail_html_dir() / f"{message_id}.html"
        raw_html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.exists() else None

        # 1. Split into `new`, `quote`, `signature`, `footer`
        split_res = split_email_parts(msg["body_text"] or "", raw_html=raw_html)
        new_text = split_res["new"] or (msg["body_text"] or "").strip()
        sig_meta = extract_signature_metadata(split_res["signature"])

        # 2. Classify (preserving user correction if already corrected by user)
        if existing_lbl and existing_lbl["source"] == "user":
            label = str(existing_lbl["label"])
            confidence = 1.0
            lbl_source = "user"
            lbl_version = self.model_version
        else:
            label, confidence, lbl_source, lbl_version = self.classify_message(
                from_name=msg["from_name"],
                from_addr=msg["from_addr"],
                subject=msg["subject"],
                new_text=new_text,
                list_unsubscribe=msg["list_unsubscribe"] or "",
            )

        # 3. Extract per label
        extracts_map: dict[str, tuple[str, str, float]] = {}
        action_data: dict[str, Any] | None = None

        if label == "ping":
            plat = match_ping_platform(msg["from_addr"]) or "Other"
            extracts_map["platform"] = (plat, "rule", 1.0)
        elif label == "information":
            extracts_map = extract_information_fields(
                subject=msg["subject"],
                from_name=msg["from_name"],
                from_addr=msg["from_addr"],
                new_text=new_text,
                reader_fn=None,
            )
        elif label == "promotion":
            extracts_map = extract_promotion_fields(
                subject=msg["subject"],
                from_name=msg["from_name"],
                from_addr=msg["from_addr"],
                new_text=new_text,
                reader_fn=None,
            )
        elif label == "email":
            # Check if from last 14 days, user is in To, and user hasn't replied yet
            age_days = (time.time() - float(msg["date"] or time.time())) / 86400.0
            to_list = json.loads(msg["to_json"] or "[]")
            to_emails = {str(x.get("email") or "").lower() for x in to_list if isinstance(x, dict)}
            user_in_to = not account_email or account_email in to_emails or not to_emails
            already_replied = bool(msg["answered"])
            if not already_replied and msg["thread_id"]:
                with self.mail.db_lock:
                    conn = self.mail._ensure_connection()
                    sent_reply = conn.execute(
                        """
                        SELECT 1 FROM messages
                        WHERE thread_id = ? AND date >= ? AND (LOWER(from_addr) = ? OR UPPER(folder) != 'INBOX')
                          AND id != ?
                        LIMIT 1
                        """,
                        (msg["thread_id"], msg["date"], account_email, message_id),
                    ).fetchone()
                    if sent_reply:
                        already_replied = True

            if age_days <= 14.0 and user_in_to and not already_replied:
                action_data = detect_email_action_heuristic(msg["subject"], new_text)

        # 4. Save parts, labels, extracts, actions, and update FTS5 (`new` text only)
        now = time.time()
        snippet_new = re.sub(r"\s+", " ", new_text).strip()[:220]
        with self.mail.db_lock:
            conn = self.mail._ensure_connection()
            conn.execute("DELETE FROM parts WHERE message_id = ?", (message_id,))
            for kind, txt in split_res.items():
                if txt:
                    conn.execute(
                        "INSERT INTO parts (message_id, kind, text) VALUES (?, ?, ?)",
                        (message_id, kind, txt),
                    )
            if not split_res["new"] and new_text:
                conn.execute(
                    "INSERT INTO parts (message_id, kind, text) VALUES (?, 'new', ?)",
                    (message_id, new_text),
                )

            if snippet_new:
                conn.execute("UPDATE messages SET snippet = ? WHERE id = ?", (snippet_new, message_id))

            conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (message_id,))
            conn.execute(
                "INSERT INTO messages_fts (message_id, subject, from_name, from_addr, new_text) VALUES (?, ?, ?, ?, ?)",
                (message_id, msg["subject"], msg["from_name"], msg["from_addr"], new_text),
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO labels (message_id, label, confidence, source, model_version, at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, label, confidence, lbl_source, lbl_version, now),
            )

            conn.execute("DELETE FROM extracts WHERE message_id = ?", (message_id,))
            for fld, (val, src_kind, conf) in extracts_map.items():
                if val:
                    conn.execute(
                        "INSERT INTO extracts (message_id, field, value, source, confidence) VALUES (?, ?, ?, ?, ?)",
                        (message_id, fld, val, src_kind, conf),
                    )

            if action_data is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO actions (message_id, needs_reply, due_date, ask)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        1 if action_data.get("needs_reply") else 0,
                        action_data.get("due_date"),
                        str(action_data.get("ask") or ""),
                    ),
                )
            conn.commit()

        # Check if we now have >= 50 labelled samples to train the classifier
        self.maybe_trigger_training()

        # 5. Store and link in Brain & Knowledge Store (Section 4.5.5)
        self._store_and_link_brain_and_passages(
            msg=msg,
            new_text=new_text,
            label=label,
            extracts_map=extracts_map,
            sig_meta=sig_meta,
            account_email=account_email,
        )

        return {
            "message_id": message_id,
            "label": label,
            "confidence": confidence,
            "extracts": {k: v[0] for k, v in extracts_map.items()},
        }

    def _store_and_link_brain_and_passages(
        self,
        msg: dict[str, Any],
        new_text: str,
        label: str,
        extracts_map: dict[str, tuple[str, str, float]],
        sig_meta: dict[str, str],
        account_email: str,
    ) -> None:
        """
        Section 4.5.5:
        - Brain (`$source: mail:<message_id>`):
          - Create `person` ONLY for senders the user has replied to OR received at least 2 `email`-labelled messages from.
          - Create `organization` from sender domain, skipping `FREE_MAIL_DOMAINS` and `noreply@` / `no-reply@` / `notifications@`.
          - Add `order` (`Entities/Orders`) and `promotion` (`Entities/Promotions`) entities.
          - Link `person works_for organization`, `organization has_order order`, `organization has_promotion promotion`.
        - Knowledge store:
          - `add_passages` for `email` and `information` new text (`conversation_id = 'mail'`).
          - Promotions and pings are NOT added to the knowledge store.
        """
        message_id = msg["id"]
        from_addr = (msg["from_addr"] or "").strip().lower()
        from_name = (msg["from_name"] or "").strip()
        local_part = from_addr.split("@")[0] if "@" in from_addr else from_addr
        domain = from_addr.split("@")[-1] if "@" in from_addr else ""
        source_tag = f"mail:{message_id}"
        brain = getattr(self.runtime, "brain", None)
        if brain is None:
            return

        org_name: str | None = None
        is_free_domain = domain in FREE_MAIL_DOMAINS
        is_automated_sender = any(local_part.startswith(p) for p in AUTOMATED_LOCAL_PARTS)

        # Organization creation from sender domain (skipping free-mail and automated senders)
        if domain and not is_free_domain and not is_automated_sender:
            org_name = sig_meta.get("company") or domain.split(".")[0].capitalize()
            brain.upsert_entity(
                entity_type="organization",
                name=org_name,
                summary=f"Organization associated with domain {domain}.",
                attributes={"domain": domain, "$source": source_tag},
                relationships=[],
                aliases=[domain],
                source_url=source_tag,
                tier=2,
                actor="mail/pipeline",
            )

        # Person creation: ONLY if user replied to sender OR >= 2 `email`-labelled messages from sender
        person_created_name: str | None = None
        if from_addr and from_addr != account_email and not is_automated_sender:
            with self.mail.db_lock:
                conn = self.mail._ensure_connection()
                email_cnt_row = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM messages m
                    JOIN labels l ON l.message_id = m.id
                    WHERE LOWER(m.from_addr) = ? AND l.label = 'email'
                    """,
                    (from_addr,),
                ).fetchone()
                email_msg_count = int(email_cnt_row["c"] if email_cnt_row else 0)

                replied_row = conn.execute(
                    """
                    SELECT 1 FROM messages
                    WHERE (LOWER(from_addr) = ? AND answered = 1)
                       OR (UPPER(folder) != 'INBOX' AND LOWER(to_json) LIKE ?)
                    LIMIT 1
                    """,
                    (from_addr, f"%{from_addr}%"),
                ).fetchone()
                user_replied = replied_row is not None

            if user_replied or email_msg_count >= 2:
                person_name = from_name or local_part
                person_created_name = person_name
                last_contact_iso = datetime.datetime.fromtimestamp(
                    float(msg["date"] or time.time()), tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d")
                attrs: dict[str, Any] = {
                    "email": from_addr,
                    "last_contact": last_contact_iso,
                    "message_count": email_msg_count,
                    "$source": source_tag,
                }
                if sig_meta.get("role"):
                    attrs["role"] = sig_meta["role"]
                if sig_meta.get("company") or org_name:
                    attrs["company"] = sig_meta.get("company") or org_name
                if sig_meta.get("phone"):
                    attrs["phone"] = sig_meta["phone"]
                rels = [{"type": "works_for", "target": f"[[{org_name}]]"}] if org_name else []
                brain.upsert_entity(
                    entity_type="person",
                    name=person_name,
                    summary=f"Mail contact ({from_addr}), {email_msg_count} email messages.",
                    attributes=attrs,
                    relationships=rels,
                    aliases=[from_addr],
                    source_url=source_tag,
                    tier=1,
                    actor="mail/pipeline",
                )

        # Order entity (`Entities/Orders`) for `information` emails with an order or tracking number
        if label == "information":
            order_no = extracts_map.get("order_number", ("", "", 0.0))[0]
            tracking_no = extracts_map.get("tracking_number", ("", "", 0.0))[0]
            merchant = extracts_map.get("merchant", ("", "", 0.0))[0] or org_name or from_name or domain
            status_val = extracts_map.get("status", ("ordered", "", 0.0))[0]
            if order_no or tracking_no:
                order_title = f"{merchant} Order {order_no or tracking_no}".strip()
                order_attrs: dict[str, Any] = {
                    "merchant": merchant,
                    "order_number": order_no,
                    "tracking_number": tracking_no,
                    "tracking_url": extracts_map.get("tracking_url", ("", "", 0.0))[0],
                    "status": status_val,
                    "total": extracts_map.get("total", ("", "", 0.0))[0],
                    "$source": source_tag,
                }
                brain.upsert_entity(
                    entity_type="order",
                    name=order_title,
                    summary=f"Order {order_no or tracking_no} from {merchant} ({status_val}).",
                    attributes=order_attrs,
                    source_url=source_tag,
                    tier=1,
                    actor="mail/pipeline",
                )
                if merchant and not is_free_domain:
                    brain.upsert_entity(
                        entity_type="organization",
                        name=merchant,
                        summary=f"Merchant {merchant}.",
                        attributes={"domain": domain, "$source": source_tag},
                        relationships=[{"type": "has_order", "target": f"[[{order_title}]]"}],
                        source_url=source_tag,
                        tier=2,
                        actor="mail/pipeline",
                    )

        # Promotion entity (`Entities/Promotions`) for `promotion` emails with a voucher code
        if label == "promotion":
            code = extracts_map.get("voucher_code", ("", "", 0.0))[0]
            company = extracts_map.get("company", ("", "", 0.0))[0] or org_name or from_name or domain
            if code:
                promo_title = f"{company} Promo {code}".strip()
                promo_attrs: dict[str, Any] = {
                    "company": company,
                    "domain": domain,
                    "voucher_code": code,
                    "discount_value": extracts_map.get("discount_value", ("", "", 0.0))[0],
                    "expiry": extracts_map.get("expiry", ("", "", 0.0))[0],
                    "$source": source_tag,
                }
                brain.upsert_entity(
                    entity_type="promotion",
                    name=promo_title,
                    summary=f"Promo code {code} for {company}.",
                    attributes=promo_attrs,
                    source_url=source_tag,
                    tier=2,
                    actor="mail/pipeline",
                )
                if company and not is_free_domain:
                    brain.upsert_entity(
                        entity_type="organization",
                        name=company,
                        summary=f"Company {company}.",
                        attributes={"domain": domain, "$source": source_tag},
                        relationships=[{"type": "has_promotion", "target": f"[[{promo_title}]]"}],
                        source_url=source_tag,
                        tier=2,
                        actor="mail/pipeline",
                    )

        # Knowledge store passages: ONLY for `email` and `information` new text (conversation_id = 'mail')
        if label in ("email", "information") and new_text and len(new_text.strip()) >= 15:
            entity_name = person_created_name or org_name or from_name or from_addr or "mail"
            mail_url = f"satzmail://message/{message_id}"
            with self.runtime.store_lock:
                self.runtime.store.db.execute(
                    """
                    INSERT OR REPLACE INTO satz_sources
                    (source_id, conversation_id, url, domain, title, text, extra_json, capture_mode, updated_at)
                    VALUES (?, 'mail', ?, 'mail', ?, ?, '[]', 'mail', ?)
                    """,
                    (source_tag, mail_url, msg["subject"], new_text, time.time()),
                )
                if getattr(self.runtime, "ingest_queue", None) is not None and not getattr(self.runtime, "pause_learning", False):
                    self.runtime.ingest_queue.put(
                        {
                            "conversation_id": "mail",
                            "source_id": source_tag,
                            "url": mail_url,
                            "domain": domain or "mail",
                            "title": msg["subject"],
                            "text": new_text[:4000],
                        }
                    )
                try:
                    from src.planck3.util import norm_text

                    self.runtime.store.db.execute(
                        "INSERT OR IGNORE INTO satz_conv_passages (conversation_id, text_norm, url) VALUES ('mail', ?, ?)",
                        (norm_text(new_text[:4000]), mail_url),
                    )
                except Exception:
                    pass
                self.runtime.store.db.commit()

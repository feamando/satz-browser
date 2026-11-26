"""
Question type (owner's rule, 2026-10-09), deterministic and shown on the answer card:

    news           recent events: confidence -2 (moving, contested, first reports get corrected)
    encyclopedic   history / reference facts: confidence -1
    general_info   practical service facts (flights, ports, opening hours, rules, schedules): no penalty

Rules, not a model: a misclassification is visible on the card and fixable here. DISCLOSED: the
word lists were extended (2026-10-09) after reading the round 5 benchmark drafts, so question-type
accuracy on those benchmarks is reported, not judged.
"""

import re
import time

PENALTY = {"news": 2.0, "encyclopedic": 1.0, "general_info": 0.0}

_GENERAL = re.compile(
    r"\b(airports?|terminals?|runways?|flights?|airlines?|gate|ports?|ferr(y|ies)|trains?|station|platform|metro|subway|"
    r"tram|journey|crossing|ride|how long does .{0,60} take|opening hours|opens?|opening|closed|closes?|tickets?|"
    r"admission|entry fee|fees?|costs?|price of|visas?|passport|emergency (phone )?number|dial|plug|mains|voltage|socket|"
    r"speed limit|time ?zone|daylight saving|dst|clocks|public holiday|bank holiday|national holiday|holiday|timetable|"
    r"schedule|status|delays?|outage|check-in|baggage|driving side|drive on the|toll)\b", re.I)
# a news event outranks service words: "killed when a bus caught fire in September 2026" is news
_EVENT = re.compile(
    r"\b(won|wins?|winner|elected|appointed|named|resigned|died|dead|killed|crash(ed)?|fire|explosion|collapse|"
    r"earthquake|attack|announced|launched|acquired|takeover|signed|sanctions?|sever(ed|ing)|restored|awarded|beatified|"
    r"beat|defeated|raised|cut|record)\b", re.I)
_NOW = re.compile(r"\b(today|yesterday|this (week|month|year)|last (week|month)|latest|recent(ly)?|currently|current|"
                  r"right now|so far)\b", re.I)


def _common_words(q: str) -> str:
    """Drop capitalised words after the first: 'Port Moresby', 'Gate Gourmet' are names, not service words."""
    toks = q.split()
    return " ".join(t for i, t in enumerate(toks) if i == 0 or not t[:1].isupper())


def classify(question: str, year: int | None = None) -> str:
    q = question or ""
    this_year = year or time.gmtime().tm_year
    years = {int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", q)}
    years |= {int(a[:2] + b) for a, b in re.findall(r"\b(\d{4})[\u2013-](\d{2})\b", q)}   # seasons: 2025-26 ends in 2026
    recent = bool(_NOW.search(q)) or this_year in years
    if recent and _EVENT.search(q):
        return "news"
    if _GENERAL.search(_common_words(q)):
        return "general_info"
    return "news" if recent else "encyclopedic"

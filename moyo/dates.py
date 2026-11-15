"""Natural-language dates/times/amounts used by the command parser (deterministic, no AI)."""
from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SHORT = {d[:3]: i for i, d in enumerate(WEEKDAYS)}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def parse_date(text: str, ref: date) -> date | None:
    t = text.lower().strip().rstrip(".")
    t = re.sub(r"^(on|by|for|due|this)\s+", "", t)
    if t in ("today", "tonight", "this evening", "this afternoon", "this morning"):
        return ref
    if t == "tomorrow":
        return ref + timedelta(days=1)
    if t in ("day after tomorrow", "the day after tomorrow"):
        return ref + timedelta(days=2)
    if t == "next week":
        return ref + timedelta(days=7 - ref.weekday())  # next Monday
    m = re.fullmatch(r"in (\d+) days?", t)
    if m:
        return ref + timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"(next )?([a-z]+)", t)
    if m and m.group(2)[:3] in SHORT and m.group(2) in WEEKDAYS + list(SHORT):
        wd = SHORT[m.group(2)[:3]]
        # "Friday" and "next Friday" both mean the coming Friday (never today).
        delta = (wd - ref.weekday()) % 7 or 7
        return ref + timedelta(days=delta)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # "15 november", "november 15", "15th nov"
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+)", t) or re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)?", t)
    if m:
        a, b = m.groups()
        day, mon = (a, b) if a.isdigit() else (b, a)
        mi = next((i for i, n in enumerate(MONTHS) if n.startswith(mon[:3])), None)
        if mi is not None:
            d = date(ref.year, mi + 1, int(day))
            return d if d >= ref else date(ref.year + 1, mi + 1, int(day))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)  # dd/mm (Nigerian format)
    if m:
        y = int(m.group(3)) if m.group(3) else ref.year
        y = y + 2000 if y < 100 else y
        return date(y, int(m.group(2)), int(m.group(1)))
    return None


HOUR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def parse_time(text: str) -> str | None:
    t = text.lower().replace(".", "").strip()
    t = re.sub(r"\b(" + "|".join(HOUR_WORDS) + r")\b", lambda m: str(HOUR_WORDS[m.group(1)]), t)
    t = re.sub(r"\b(\d{1,2})\s*o'?clock\b", r"\1", t)
    m = re.fullmatch(r"(?:at )?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "a": 1}
_SCALE = {"hundred": 100, "thousand": 1_000, "k": 1_000, "million": 1_000_000, "m": 1_000_000}


def parse_amount(text: str) -> tuple[float, str | None] | None:
    """'₦200,000' / '200k naira' / '$500' / 'two hundred thousand naira' / '1.5m' -> (amount, currency)."""
    t = text.lower().strip()
    cur = None
    if "₦" in t or re.search(r"\b(naira|ngn|n)\b", t):
        cur = "NGN"
    if "$" in t or re.search(r"\b(dollars?|usd|bucks)\b", t):
        cur = "USD"
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = re.sub(r"[₦$,]|\b(naira|ngn|dollars?|usd|bucks)\b", " ", t)
    t = re.sub(r"(?<=\d)n\b", " ", t)  # "200000n"
    t = re.sub(r"\s+", " ", t).strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(k|m|thousand|million)?", t)
    if m:
        v = float(m.group(1)) * _SCALE.get(m.group(2) or "", 1)
        return (v, cur) if v > 0 else None
    words = [w for w in re.split(r"[\s-]+", t) if w and w != "and"]
    if not words or any(w not in _NUM and w not in _SCALE for w in words):
        return None
    total, current = 0, 0
    for w in words:
        if w in _NUM:
            current += _NUM[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        else:
            total += max(current, 1) * _SCALE[w]
            current = 0
    v = float(total + current)
    return (v, cur) if v > 0 else None


def fmt_money(amount: float, currency: str) -> str:
    sym = {"USD": "$", "NGN": "₦"}.get(currency, currency + " ")
    return f"{sym}{amount:,.0f}" if amount == int(amount) else f"{sym}{amount:,.2f}"

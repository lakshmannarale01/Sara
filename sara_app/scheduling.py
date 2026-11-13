"""Small, deterministic English/Hindi schedule parsing without model calls.

Times are interpreted in the reference clock's timezone and returned as UTC.
The parser deliberately asks for clarification rather than choosing AM/PM or
silently moving an explicitly requested day. ``span`` refers to the original
input, allowing a caller to remove the schedule phrase from an event title.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re


@dataclass(frozen=True)
class ParsedSchedule:
    due_at: str | None
    status: str
    message: str = ""
    span: tuple[int, int] | None = None


_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_LEFT = r"(?<![\w\u0900-\u097f])"
_RIGHT = r"(?![\w\u0900-\u097f])"
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5,
    "panch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "pandrah": 15, "bees": 20, "tees": 30,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "पंद्रह": 15, "पन्द्रह": 15, "बीस": 20, "तीस": 30,
}
_NUMBER = r"(?:-?\d+(?:\.\d+)?|" + "|".join(sorted(_WORDS, key=len, reverse=True)) + ")"
_CLOCK_NUMBER = r"(?:-?\d+|" + "|".join(sorted(_WORDS, key=len, reverse=True)) + ")"
_UNIT = r"(?:minutes?|mins?|hours?|hrs?|seconds?|secs?|days?|minute|ghanta|ghante|din|मिनट|घंटा|घंटे|सेकंड|दिन)"
_DURATION = re.compile(_LEFT + r"(?P<number>" + _NUMBER + r")\s*(?P<unit>" + _UNIT + r")" + _RIGHT, re.I)
_HALF = re.compile(_LEFT + r"(?:half\s+(?:an?\s+)?hour|aadh[ae]\s+ghant[ae]|आध[ाे]\s+घंट[ाे])" + _RIGHT, re.I)
_REL_PREFIX = re.compile(r"(?:\bin|\bafter)\s*$", re.I)
_REL_SUFFIX = re.compile(r"\s*(?:baad|बाद|later|from\s+now)" + _RIGHT, re.I)
_DAY = re.compile(_LEFT + r"(?P<day>day\s+after\s+tomorrow|parso|parson|परसों|today|tomorrow|aaj|kal|आज|कल)" + _RIGHT, re.I)
_DATE = re.compile(r"(?<![\w\d-])\d{4}-\d{2}-\d{2}(?![\w\d-])")
_PART = r"(?:morning|afternoon|evening|night|subah|savere|shaam|sham|raat|dopahar|सुबह|शाम|रात|दोपहर)"
_CLOCK = re.compile(
    _LEFT + r"(?<![.:])(?:(?P<part>" + _PART + r")\s*(?:(?:at|ko|को|के|की)\s*)?)?"
    r"(?:(?P<at>at)\s+)?(?P<hour>" + _CLOCK_NUMBER + r")"
    r"(?::(?P<minute>\d+))?\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?)?\s*"
    r"(?P<baje>baje|bajey|बजे)?"
    r"(?:\s+(?:in\s+the\s+)?(?P<afterpart>" + _PART + r"))?(?![\w\u0900-\u097f:]|\.\d)",
    re.I,
)
_PART_TOKEN = re.compile(_LEFT + _PART + _RIGHT, re.I)
_TIMING_HINT = re.compile(r"\bat\s+-?\d+\b|\b(?:baje|bajey|noon|midnight)\b|बजे", re.I)


def _result(status, message, span=None):
    return ParsedSchedule(None, status, message, span)


def _relative_span(text, match):
    before = _REL_PREFIX.search(text[:match.start()])
    after = _REL_SUFFIX.match(text[match.end():])
    if not before and not after:
        return None
    return (before.start() if before else match.start(), match.end() + (after.end() if after else 0))


def _overlaps(first, second):
    return first[0] < second[1] and second[0] < first[1]


def _part_hour(hour, part):
    if not part:
        return hour, ""
    part = part.lower()
    if part in {"morning", "subah", "savere", "सुबह"}:
        return (hour, "") if 1 <= hour <= 11 else (None, "Please specify AM or PM for this morning time.")
    if part in {"night", "raat", "रात"}:
        if 6 <= hour <= 11:
            return hour + 12, ""
        if 18 <= hour <= 23:
            return hour, ""
        return None, "Please specify the date and AM/PM for this late-night time."
    if part in {"afternoon", "dopahar", "दोपहर"}:
        if 1 <= hour <= 5:
            return hour + 12, ""
        if 12 <= hour <= 17:
            return hour, ""
        return None, "Please specify AM or PM for this afternoon time."
    if 4 <= hour <= 11:
        return hour + 12, ""
    if 16 <= hour <= 23:
        return hour, ""
    return None, "Please specify AM or PM for this evening time."


def parse_schedule_time(message, reference=None):
    """Parse one clear schedule; never infer a time from arbitrary numbers.

    ``missing`` means no schedule was expressed. ``clarify`` means timing was
    mentioned but is incomplete/ambiguous. ``invalid`` covers impossible clocks,
    explicitly past dates, and unsupported duration ranges. Relative delays are
    positive and bounded to 365 days. A supplied reference must be timezone-aware.
    """
    if not isinstance(message, str) or len(message) > 10000:
        return _result("invalid", "Please use a shorter text schedule.")
    moment = reference if reference is not None else datetime.now().astimezone()
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        return _result("invalid", "A timezone-aware reference clock is required.")
    text = message.translate(_DIGITS)
    durations = []
    duration_parts = list(_DURATION.finditer(text))
    for match in duration_parts:
        span = _relative_span(text, match)
        if span:
            raw = match.group("number").lower()
            number = _WORDS.get(raw)
            if number is None:
                number = float(raw) if len(raw) <= 12 else 0
            unit = match.group("unit").lower()
            factor = 60 if unit.startswith(("min", "मिनट")) else 3600 if unit.startswith(("hour", "hr", "ghant", "घंट")) else 86400 if unit in {"day", "days", "din", "दिन"} else 1
            durations.append((number * factor, span))
    for match in _HALF.finditer(text):
        span = _relative_span(text, match)
        if span:
            durations.append((1800, span))

    days = list(_DAY.finditer(text))
    dates = list(_DATE.finditer(text))
    clocks = []
    for match in _CLOCK.finditer(text):
        if any(_overlaps(match.span(), part.span()) for part in duration_parts):
            continue
        if any(_overlaps(match.span(), date.span()) for date in dates):
            continue
        if any(match.group(name) for name in ("part", "afterpart", "at", "minute", "ampm", "baje")):
            clocks.append(match)

    if len(durations) > 1 or len(clocks) > 1 or (durations and (clocks or days or dates)) or len(days) + len(dates) > 1:
        return _result("clarify", "I found more than one time. Please give one clear date and time.")
    if durations:
        seconds, span = durations[0]
        # Do not silently discard a compound duration that this parser cannot
        # represent, such as 'in 1 hour and 20 minutes'.
        if any(not _overlaps(part.span(), span) for part in duration_parts):
            return _result("clarify", "Please express the delay as one number of minutes or hours.")
        if not 0 < seconds <= 365 * 86400:
            return _result("invalid", "The delay must be positive and no longer than 365 days.", span)
        try:
            due = moment.astimezone(timezone.utc) + timedelta(seconds=seconds)
        except OverflowError:
            return _result("invalid", "That delay is outside the supported calendar range.", span)
        return ParsedSchedule(due.isoformat(), "ready", span=span)

    if not clocks:
        if days or dates or duration_parts or _HALF.search(text) or _PART_TOKEN.search(text) or _TIMING_HINT.search(text):
            marker = next(iter(days + dates + duration_parts), None) or _HALF.search(text) or _PART_TOKEN.search(text) or _TIMING_HINT.search(text)
            return _result("clarify", "Please include a clock time, such as 9 AM, 5 PM, or 17:30.", marker.span())
        return _result("missing", "No notification time was specified.")

    clock = clocks[0]
    span_start, span_end = clock.span()
    for marker in days + dates:
        # Include a nearby day prefix/suffix in the raw schedule span. Never
        # erase unrelated title words between a date and the clock.
        if marker.end() <= span_start and not text[marker.end():span_start].strip(" ,"):
            span_start = marker.start()
            on_prefix = re.search(r"\bon\s*$", text[:span_start], re.I)
            if on_prefix:
                span_start = on_prefix.start()
        elif marker.start() >= span_end and not text[span_end:marker.start()].strip(" ,"):
            span_end = marker.end()
    span = (span_start, span_end)
    while span_end > span_start and text[span_end - 1].isspace():
        span_end -= 1
    span = (span_start, span_end)
    hour_text, minute_text = clock.group("hour").lower(), clock.group("minute")
    if (hour_text not in _WORDS and len(hour_text) > 2) or (minute_text and len(minute_text) != 2):
        return _result("invalid", "Please use a valid clock time, such as 17:30 or 5:30 PM.", span)
    hour = _WORDS[hour_text] if hour_text in _WORDS else int(hour_text)
    minute = int(minute_text or 0)
    ampm = (clock.group("ampm") or "").lower().replace(".", "")
    part = clock.group("part") or clock.group("afterpart")
    if minute > 59 or not 0 <= hour <= 23 or (ampm and not 1 <= hour <= 12):
        return _result("invalid", "That clock time is invalid. Please check the hour and minutes.", span)
    if clock.group("part") and clock.group("afterpart") and clock.group("part").lower() != clock.group("afterpart").lower():
        return _result("clarify", "Please give one day period or an explicit AM/PM time.", span)
    part_value, error = _part_hour(hour, part)
    if error:
        return _result("clarify", error, span)
    if ampm:
        converted = hour % 12 + (12 if ampm == "pm" else 0)
        if part and converted != part_value:
            return _result("clarify", "The day period conflicts with AM/PM. Please give one clear time.", span)
        hour = converted
    elif part:
        hour = part_value
    elif hour <= 12 and not (minute_text is not None and hour_text.isdigit() and len(hour_text) == 2) and hour != 0:
        return _result("clarify", "Is that AM or PM? Please include subah/shaam, AM/PM, or a 24-hour time.", span)

    due = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    explicit_day = bool(days or dates)
    if dates:
        try:
            year, month, day = map(int, dates[0].group().split("-"))
            due = due.replace(year=year, month=month, day=day)
        except ValueError:
            return _result("invalid", "That calendar date is invalid.", span)
    elif days:
        day = days[0].group("day").lower()
        offset = 0 if day in {"today", "aaj", "आज"} else 1 if day in {"tomorrow", "kal", "कल"} else 2
        due += timedelta(days=offset)
    if due <= moment:
        if explicit_day:
            return _result("invalid", "That date and time have already passed. Please choose a future time.", span)
        due += timedelta(days=1)
    return ParsedSchedule(due.astimezone(timezone.utc).isoformat(), "ready", span=span)

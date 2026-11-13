"""Short-lived scheduling clarification drafts, isolated by dashboard session."""

from collections import OrderedDict
import re
from threading import RLock
import time
import unicodedata


MAX_ORIGINAL_CHARS = 2000
MAX_FOLLOWUP_CHARS = 160
MAX_TITLE_CHARS = 500
_SESSION = re.compile(r"[A-Za-z0-9_-]{8,80}\Z")
_TOKENS = re.compile(r"\d+|[a-z]+(?:['’][a-z]+)?|[\u0900-\u0963\u0970-\u097f]+", re.I)
_DAY_WORDS = {"today", "tomorrow", "aaj", "aj", "kal", "parso", "parson", "आज", "कल", "परसों"}
_PART_WORDS = {"morning", "afternoon", "evening", "night", "tonight", "noon", "midnight", "subah", "savere", "dopahar", "dopehar", "shaam", "sham", "raat", "सुबह", "दोपहर", "शाम", "रात", "am", "pm"}
_CONNECTORS = {"at", "on", "in", "after", "around", "about", "o'clock", "oclock", "ko", "par", "mein", "me", "baje", "bajay", "bajey", "baad", "later", "from", "now", "the", "an", "को", "पर", "में", "बजे", "बाद", "लगभग", "के", "की"}
_UNITS = {"minute", "minutes", "min", "mins", "hour", "hours", "hr", "hrs", "second", "seconds", "sec", "secs", "day", "days", "ghanta", "ghante", "din", "मिनट", "मिनटों", "घंटे", "घंटा", "सेकंड", "सेकण्ड", "दिन"}
_NUMBERS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "fifteen", "twenty", "thirty", "forty", "sixty", "ek", "do", "teen", "chaar", "char", "paanch", "panch", "chhe", "saat", "aath", "nau", "das", "pandrah", "bees", "tees", "एक", "दो", "तीन", "चार", "पाँच", "पांच", "छह", "सात", "आठ", "नौ", "दस", "पंद्रह", "पन्द्रह", "बीस", "तीस", "half", "aadha", "aadhe", "आधा", "आधे"}
_ALLOWED = _DAY_WORDS | _PART_WORDS | _CONNECTORS | _UNITS | _NUMBERS | {"a", "p", "m"}
_DAY = re.compile(r"(?<![a-z\u0900-\u097f])(?:day\s+after\s+tomorrow|tomorrow|today|parson|parso|aaj|aj|kal|परसों|आज|कल)(?![a-z\u0900-\u097f])", re.I)
_DATE = re.compile(r"(?<![\w\d-])\d{4}-\d{2}-\d{2}(?![\w\d-])")
_PART = re.compile(r"(?<![a-z\u0900-\u097f])(?:morning|afternoon|evening|night|tonight|noon|midnight|subah|savere|dopahar|dopehar|shaam|sham|raat|सुबह|दोपहर|शाम|रात|a\.?m\.?|p\.?m\.?)(?![a-z\u0900-\u097f])", re.I)


def _session_id(value):
    return isinstance(value, str) and bool(_SESSION.fullmatch(value))


def _tokens(value):
    return _TOKENS.findall(unicodedata.normalize("NFKC", value).lower())


def _has_number(value):
    return bool(re.search(r"\d", value)) or bool(set(_tokens(value)) & _NUMBERS)


def _followup(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_FOLLOWUP_CHARS:
        return None
    value = unicodedata.normalize("NFKC", value).strip()
    if re.search(r"[^a-z\d\u0900-\u097f\s:.,!?।'’/\-]", value, re.I):
        return None
    words = _tokens(value)
    if not words or any(not word.isdecimal() and word not in _ALLOWED for word in words):
        return None
    if not (_has_number(value) or set(words) & _DAY_WORDS or _PART.search(value)):
        return None
    return value


def _span(value, original):
    if (isinstance(value, (tuple, list)) and len(value) == 2
            and all(isinstance(index, int) and not isinstance(index, bool) for index in value)
            and 0 <= value[0] < value[1] <= len(original)):
        return tuple(value)
    return None


def _clean(value):
    return re.sub(r"[ \t]+", " ", value).strip()


def _override_adjacent_day(before, after):
    """Remove an old day outside a narrow time span only when adjacent to it."""
    for match in reversed(list(_DAY.finditer(before))):
        if all(token in _CONNECTORS for token in _tokens(before[match.end():])):
            before = before[:match.start()] + before[match.end():]
            break
    for match in _DAY.finditer(after):
        if all(token in _CONNECTORS for token in _tokens(after[:match.start()])):
            after = after[:match.start()] + after[match.end():]
            break
    return before, after


def _compose(original, span, followup):
    if span is None:
        return _clean(original + " " + followup)
    start, end = span
    before, previous, after = original[:start], original[start:end], original[end:]
    new_day = bool(_DAY.search(followup) or _DATE.search(followup))
    if new_day:
        before, after = _override_adjacent_day(before, after)
    if _has_number(followup):
        day_matches = sorted(list(_DAY.finditer(previous)) + list(_DATE.finditer(previous)), key=lambda match: match.start())
        saved_day = " ".join(match.group() for match in day_matches) if not new_day else ""
        replacement = _clean(saved_day + " " + followup)
    else:
        # A new period resolves an ambiguous clock without dropping its digits.
        if _PART.search(followup):
            previous = _PART.sub("", previous)
        if new_day:
            previous = _DAY.sub("", previous)
        replacement = _clean(previous + " " + followup)
    return _clean(before + " " + replacement + " " + after)


class SchedulingDialogueStore:
    def __init__(self, ttl_seconds=300, max_sessions=64, clock=None):
        if ttl_seconds <= 0 or max_sessions < 1:
            raise ValueError("Scheduling draft TTL and capacity must be positive.")
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._clock = clock or time.monotonic
        self._drafts = OrderedDict()
        self._lock = RLock()

    def _expire(self):
        now = self._clock()
        for session, draft in list(self._drafts.items()):
            if now >= draft["expires_at"]:
                del self._drafts[session]

    def remember(self, session_id, kind, original, title=None, span=None):
        if not _session_id(session_id):
            return False
        if (not isinstance(kind, str) or kind not in {"reminder", "event"} or not isinstance(original, str)
                or not original.strip() or len(original) > MAX_ORIGINAL_CHARS
                or (title is not None and (not isinstance(title, str) or len(title) > MAX_TITLE_CHARS))):
            self.clear(session_id)
            return False
        with self._lock:
            self._expire()
            self._drafts[session_id] = {"kind": kind, "original": original, "title": title,
                                        "span": _span(span, original), "expires_at": self._clock() + self.ttl_seconds}
            self._drafts.move_to_end(session_id)
            while len(self._drafts) > self.max_sessions:
                self._drafts.popitem(last=False)
        return True

    def resume(self, session_id, followup):
        if not _session_id(session_id):
            return None
        with self._lock:
            self._expire()
            draft = self._drafts.pop(session_id, None)
        if draft is None:
            return None
        clarification = _followup(followup)
        if clarification is None:
            return None
        return {"kind": draft["kind"], "original": draft["original"], "title": draft["title"],
                "message": _compose(draft["original"], draft["span"], clarification)}

    def clear(self, session_id):
        if not _session_id(session_id):
            return False
        with self._lock:
            self._expire()
            return self._drafts.pop(session_id, None) is not None


_store = SchedulingDialogueStore()


def remember(session_id, kind, original, title=None, span=None):
    return _store.remember(session_id, kind, original, title, span)


def resume(session_id, followup):
    return _store.resume(session_id, followup)


def clear(session_id):
    return _store.clear(session_id)

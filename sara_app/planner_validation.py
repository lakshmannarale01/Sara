"""Validation shared by local reminder, task and calendar creation endpoints."""

from datetime import datetime, timezone
import re


_ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+-]{0,119}\Z")
_ISO_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")


def planner_item_id(value, generated):
    """Use a generated identity when absent, otherwise require a safe opaque ID."""
    candidate = generated if value is None else value
    if not isinstance(candidate, str) or not _ITEM_ID.fullmatch(candidate):
        raise ValueError("Item ID must be 1–120 letters, digits, dots, colons, plus signs, underscores or hyphens, starting with a letter or digit.")
    return candidate


def normalize_planner_time(value, optional=False, reference=None):
    """Return a future timezone-aware ISO timestamp in UTC, or an untimed None."""
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError("Time must be a timezone-aware ISO timestamp, for example 2027-01-15T09:00:00+05:30.")
    value = value.strip()
    if not _ISO_CLOCK.match(value):
        raise ValueError("Time must include a date, clock time and timezone offset.")
    try:
        due = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        if due.tzinfo is None or due.utcoffset() is None:
            raise ValueError("Time must include an explicit timezone offset.")
        due = due.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Time must be a valid date and clock time with an explicit timezone offset.") from exc
    current = reference or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("The reference time must include a timezone offset.")
    if due <= current.astimezone(timezone.utc):
        raise ValueError("Choose a future time; the reviewed time has already passed.")
    return due.isoformat()

"""Shared, cross-process reminder claiming and Windows notification delivery."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
import subprocess

from .storage import REMINDER_FILE, log, now, read_reminders, write_reminders


@contextmanager
def reminder_file_lock():
    """Serialize reminder claims across the server and scheduled worker."""
    lock_path = REMINDER_FILE.with_name("reminders.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def claim_due_reminders(moment=None):
    """Atomically claim due notifications and return them to one worker."""
    moment = moment or datetime.now(timezone.utc)
    claimed = []
    newly_due = []
    with reminder_file_lock():
        reminders = read_reminders()
        changed = False
        for item in reminders:
            due = item.get("due_at")
            if due and item.get("status") == "pending":
                try:
                    due_at = datetime.fromisoformat(due.replace("Z", "+00:00"))
                except (AttributeError, TypeError, ValueError):
                    continue
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc)
                if due_at <= moment:
                    item["status"] = "due"
                    item["notification_status"] = "pending"
                    newly_due.append(dict(item))
                    changed = True
            if item.get("status") != "due" or item.get("notification_status") not in {"pending", "failed", "sending"}:
                continue
            attempted = item.get("last_notification_attempt_at")
            if attempted:
                try:
                    attempted_at = datetime.fromisoformat(attempted.replace("Z", "+00:00"))
                    if attempted_at.tzinfo is None:
                        attempted_at = attempted_at.replace(tzinfo=timezone.utc)
                    if attempted_at + timedelta(seconds=60) > moment:
                        continue
                except (AttributeError, TypeError, ValueError):
                    pass
            item["notification_status"] = "sending"
            item["notification_attempts"] = int(item.get("notification_attempts", 0)) + 1
            item["last_notification_attempt_at"] = now()
            claimed.append(dict(item))
            changed = True
        if changed:
            write_reminders(reminders)
    for item in newly_due:
        log("reminder_due", {"id": item.get("id"), "text": item.get("text", "")})
    return claimed


def finish_notification(item, error=None):
    """Record an attempt result; failed deliveries are retried after one minute."""
    ident = item.get("id")
    with reminder_file_lock():
        reminders = read_reminders()
        target = next((entry for entry in reminders if entry.get("id") == ident), None)
        if not target:
            return
        target["notification_status"] = "failed" if error else "delivered"
        target["notification_error"] = str(error)[:500] if error else ""
        target["notification_updated_at"] = now()
        write_reminders(reminders)
    if error:
        log("reminder_notification_failed", {"id": ident, "attempt": item.get("notification_attempts"), "error": str(error)[:500]})
    else:
        log("reminder_notification_attempted", {"id": ident, "attempt": item.get("notification_attempts"), "returncode": 0})


def deliver_due_reminders():
    """Show due reminders to the logged-in Windows user and retry failures."""
    due_items = claim_due_reminders()
    if not due_items:
        return {"claimed": 0, "delivered": 0}
    if os.name != "nt":
        for item in due_items:
            finish_notification(item, "Windows msg.exe is unavailable on this platform")
        return {"claimed": len(due_items), "delivered": 0}
    username = os.environ.get("USERNAME", "").strip()
    if not username:
        for item in due_items:
            finish_notification(item, "No logged-in Windows username is available")
        return {"claimed": len(due_items), "delivered": 0}
    delivered = 0
    for item in due_items:
        message = f"SARA reminder: {item.get('text', '')}"[:1800]
        try:
            result = subprocess.run(
                ["msg.exe", username, "/TIME:60", message],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                delivered += 1
                finish_notification(item)
            else:
                finish_notification(item, f"msg.exe returned {result.returncode}: {(result.stderr or result.stdout or 'msg.exe failed')[:450]}")
        except Exception as exc:
            finish_notification(item, exc)
    return {"claimed": len(due_items), "delivered": delivered}

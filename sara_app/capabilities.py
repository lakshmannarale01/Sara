"""Capability registry and confirmation policy for SARA actions."""

CAPABILITIES = {
    "chat": {"status": "available", "risk": "low"},
    "memory": {"status": "available", "risk": "medium"},
    "voice": {"status": "available", "risk": "low"},
    "pronunciation_preferences": {"status": "available", "risk": "low", "confirmation": True, "scope": "local user-owned word/phrase say-as entries applied only to spoken replies"},
    "system_status": {"status": "available", "risk": "low", "scope": "read-only local readiness and SARA data counts"},
    "open_documentation_url": {"status": "available", "risk": "low", "confirmation": True},
    "browser_control": {"status": "partial", "risk": "medium", "confirmation": True, "scope": "open HTTPS URLs and search pages"},
    "weather_lookup": {"status": "partial", "risk": "low", "scope": "current conditions when service reachable"},
    "file_operations": {"status": "partial", "risk": "high", "confirmation": True, "scope": "safe workspace text read/write/delete; secrets and runtime data excluded"},
    "list_read_workspace_files": {"status": "available", "risk": "medium", "confirmation": False},
    "read_workspace_text": {"status": "available", "risk": "medium", "confirmation": False, "scope": "text files inside the project workspace; excludes secrets and runtime data"},
    "search_workspace_text": {"status": "available", "risk": "medium", "confirmation": False, "scope": "bounded text search inside safe project files; no external or runtime data"},
    "write_workspace_files": {"status": "available", "risk": "high", "confirmation": True},
    "delete_workspace_files": {"status": "available", "risk": "critical", "confirmation": True},
    "whatsapp_message_draft": {"status": "available", "risk": "high", "confirmation": True},
    "open_allowlisted_windows_apps": {"status": "available", "risk": "medium", "confirmation": True},
    "custom_app_shortcuts": {"status": "available", "risk": "medium", "confirmation": True, "scope": "user-registered absolute .exe paths; no arguments or shell commands; confirmation before every launch"},
    "feature_request_tracking": {"status": "available", "risk": "low", "confirmation": True, "scope": "user-approved local list of requested capabilities; saving does not implement or enable them"},
    "notepad_notes": {"status": "available", "risk": "high", "confirmation": True, "scope": "save an exact reviewed UTF-8 note and request Notepad to open it; window visibility is not automatically verified"},
    "email_draft": {"status": "available", "risk": "high", "confirmation": True},
    "reminders": {"status": "available", "risk": "medium", "confirmation": True},
    "tasks_and_daily_plans": {"status": "available", "risk": "low", "confirmation": True, "scope": "local task list and reminder-aware daily plans"},
    "agenda_and_briefings": {"status": "available", "risk": "low", "confirmation": False, "scope": "read-only local tasks, reminders, and planned events"},
    "local_calendar_events": {"status": "available", "risk": "medium", "confirmation": True, "scope": "local planned events; no external calendar sync"},
    "calendar_export": {"status": "available", "risk": "low", "confirmation": False, "scope": "download local planned events as standard ICS"},
    "external_calendar_sync": {"status": "planned", "risk": "high", "confirmation": True, "scope": "Google/Microsoft OAuth integration not configured"},
    "persistent_reminders": {"status": "partial", "risk": "medium", "confirmation": True, "scope": "local reminder worker runs with SARA; optional current-user Scheduled Task installer checks once per minute while signed in and must be enabled by the user"},
    "safety_dashboard": {"status": "available", "risk": "low", "scope": "view action risks and stop/resume action execution"},
    "messaging": {"status": "partial", "risk": "critical", "confirmation": True, "scope": "WhatsApp Web draft and guarded send using SARA Chromium profile"},
    "email": {"status": "partial", "risk": "high", "confirmation": True, "scope": "opens a reviewable mailto draft; no mail API or direct send"},
    "system_control": {"status": "planned", "risk": "critical", "confirmation": True},
    "desktop_keyboard": {"status": "available", "risk": "high", "confirmation": True, "scope": "type text and safe keyboard shortcuts in the focused app"},
}

def capability_snapshot():
    return CAPABILITIES

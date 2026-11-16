"""Serve only dashboard assets through Playwright routes, with no HTTP server.

Pass ``fixture`` instead of a server URL to the browser regression scripts.
Page-specific API mocks take precedence over these context routes.
"""
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "/assets/chat-library.js": ("assets/chat-library.js", "text/javascript; charset=utf-8"),
    "/assets/productivity.js": ("assets/productivity.js", "text/javascript; charset=utf-8"),
    "/assets/productivity.css": ("assets/productivity.css", "text/css; charset=utf-8"),
    "/assets/appearance.js": ("assets/appearance.js", "text/javascript; charset=utf-8"),
    "/assets/appearance.css": ("assets/appearance.css", "text/css; charset=utf-8"),
    "/assets/sara.ico": ("assets/sara.ico", "image/x-icon"),
    "/assets/sara-icon.svg": ("assets/sara-icon.svg", "image/svg+xml"),
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/dashboard.js": ("assets/dashboard.js", "text/javascript; charset=utf-8"),
    "/assets/action-router.js": ("assets/action-router.js", "text/javascript; charset=utf-8"),
    "/assets/hud-core.js": ("assets/hud-core.js", "text/javascript; charset=utf-8"),
    "/assets/hud-theme.css": ("assets/hud-theme.css", "text/css; charset=utf-8"),
    "/assets/vision-client.js": ("assets/vision-client.js", "text/javascript; charset=utf-8"),
    "/assets/vision-controls.css": ("assets/vision-controls.css", "text/css; charset=utf-8"),
    "/assets/abilities-client.js": ("assets/abilities-client.js", "text/javascript; charset=utf-8"),
    "/assets/abilities-controls.css": ("assets/abilities-controls.css", "text/css; charset=utf-8"),
    "/assets/dashboard.css": ("assets/dashboard.css", "text/css; charset=utf-8"),
}
DEFAULTS = {
    "chats": [{"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","title":"Fixture chat"}],
    "audio/status": {"available": False, "reason": "No real Windows audio is used in this isolated fixture."},
    "routines": {"routines": []},
    "voices/windows": {"available": False, "voices": []},
    "vision/status": {"available": False, "reason": "No local vision model in this isolated fixture."},
    "access-mode": {"mode": "review", "stopped": False},
    "agenda": {"tasks": [], "reminders": [], "events": []},
    "memories": [], "conversations": [], "activity": [], "pronunciations": [],
    "apps": {"built_in": [], "custom": []}, "capability-requests": [],
    "policy": {"stopped": False, "actions": {}}, "capabilities": {},
    "health": {"ollama": True, "model_available": True, "model": "mock", "natural_voice": False},
    "action-state": {"pending": None}, "suggestions": {"suggestions": []},
}


def dashboard_fixture(page, url):
    if url != "fixture":
        return url

    def serve(route):
        parsed = urlsplit(route.request.url)
        if parsed.hostname != "localhost":
            return route.abort()
        if parsed.path in FILES:
            relative, mime = FILES[parsed.path]
            return route.fulfill(path=str(ROOT / relative), content_type=mime)
        if parsed.path.startswith("/api/") and route.request.method == "GET":
            name = parsed.path.removeprefix("/api/")
            if name in DEFAULTS:
                return route.fulfill(json=DEFAULTS[name])
        return route.abort()

    page.context.route("**/*", serve)
    # localhost is a secure context for browser crypto/session APIs. Every
    # request is intercepted above; nothing listens on a network socket.
    return "http://localhost/"

"""Serve only dashboard assets through Playwright routes, with no HTTP server.

Pass ``fixture`` instead of a server URL to the browser regression scripts.
Page-specific API mocks take precedence over these context routes.
"""
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/dashboard.js": ("assets/dashboard.js", "text/javascript; charset=utf-8"),
    "/assets/action-router.js": ("assets/action-router.js", "text/javascript; charset=utf-8"),
    "/assets/dashboard.css": ("assets/dashboard.css", "text/css; charset=utf-8"),
    "/assets/sara-character.png": ("assets/sara-character.png", "image/png"),
    "/assets/sara-avatar-speaking.mp4": ("assets/sara-avatar-speaking.mp4", "video/mp4"),
}
DEFAULTS = {
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

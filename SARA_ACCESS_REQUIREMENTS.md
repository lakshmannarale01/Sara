# SARA Access Requirements

This is the living checklist for permissions and integrations needed as SARA gains capabilities.

## Current status

| Capability | Access needed | Risk | Status |
|---|---|---:|---|
| Chat responses | Ollama running locally or `OPENAI_API_KEY` | Low | Available |
| Voice input | Browser microphone permission | Medium | Available |
| Voice output | Installed Windows voice or OpenAI TTS credits | Low | Windows voice path available |
| Local memory | Project read/write access to `sara_data` | Medium | Available |
| Local tasks and daily plans | Project read/write access to `sara_data/tasks.json` | Low | Confirmation before create/complete | Available |
| Local planned events | Project read/write access to `sara_data/events.json` | Medium | Confirmation before create | Available; external calendar sync not included |
| Local agenda/briefing | Project read access to tasks, reminders, and events | Low | Read-only | Available |
| Open approved documentation URLs | Browser launch permission | Low | Available; confirmation required |
| Open user-requested HTTPS browser URLs | Default browser launch permission | Medium | Always confirm URL before opening | Available |
| Dashboard assets | Project read access to `assets` | Low | Available |
| Capability registry | Project read access to `sara_app/capabilities.py` | Low | Available |

## Planned capabilities

| Capability | Access needed | Risk | Approval rule | Status |
|---|---|---:|---|---|
| Weather lookup | Internet access to a weather service | Low | Can run automatically | Partial; fallback browser page requires confirmation |
| Open Chrome and websites | Desktop/browser control | Medium | Confirm unfamiliar or sensitive sites | Partial; HTTPS URL/search opening available |
| Read local files | Explicit workspace scope; protected runtime and secret paths excluded | Medium | Read-only scoped access | Available inside the project workspace |
| Create/edit files | Workspace write permission | High | Confirm exact path and overwrite | Available inside the safe workspace scope |
| Send WhatsApp/messages | Logged-in messaging app or approved connector | High | Always confirm recipient and exact message | Planned |
| Email | Logged-in email connector | High | Always confirm recipients, subject and body | Planned |
| Calendar events | Local project storage; external connector not required | Medium | Confirm before creating events | Local events available; Google/Outlook sync planned |
| Calendar export | Local read access to planned events | Low | Read-only download | Available as standard `.ics` |
| Local reminders | Project storage in `sara_data/reminders.json`; server running; Windows `msg.exe` notification | Medium | Confirm before creating/deleting | Available; due watcher and notification attempt active |
| List/read workspace files | Workspace read access; excludes `.venv` and `.git` | Medium | No confirmation for read-only scoped access | Available |
| Write workspace files | Workspace write access | High | Always confirm exact path and content/overwrite | Available |
| Delete workspace files | Workspace write access | Critical | Always confirm exact path; no recursive delete | Available |
| WhatsApp message draft | WhatsApp Web login; recipient phone with country code | High | Confirm recipient and exact text; user presses Send | Draft available |
| WhatsApp message send | WhatsApp Web login in SARA Chromium profile; recipient phone with country code | Critical | Confirm recipient and exact text immediately before sending | Available through guarded Playwright action |
| Open allowlisted Windows apps | Windows process launch permission | Medium | Confirm app before launch | Available: Chrome, Notepad, Calculator |
| Email draft | Default mail app/browser; recipient, subject and body | High | Confirm recipient and exact content; user presses Send | Draft available |
| Desktop keyboard actions | PyAutoGUI in `.venv`; intended window must be focused | High | Confirm exact text/shortcut every time | Available: type text and safe keyboard shortcuts |
| Coordinate click | PyAutoGUI in `.venv`; user must provide screen coordinates | High | Confirm exact coordinates every time | Available through the guarded action API |
| Desktop readiness | No additional credential; local screen access | Low | Read-only status endpoint | Available; no screenshots collected |
| Semantic browser actions | Playwright Chromium runtime; user browser login may be needed per site | High | Confirm exact navigation/click/type action | Available through SARA's separate Chromium profile |
| Application launch/close | Windows desktop control | Medium | Safe apps can be opened; closing work needs confirmation | Planned |
| System settings | Windows desktop control | High | Always confirm changes | Planned |
| Shutdown/restart | Windows system permission | Critical | Always require explicit confirmation | Planned |
| Purchases or payments | Payment site/account access | Critical | Not enabled by default; explicit confirmation required | Planned |

## Rules

- Never store passwords, API keys, session cookies, or message contents in the repository.
- Request the smallest permission scope that can complete the task.
- Explain what access is needed before enabling a new integration.
- Keep an activity log for actions and failures.
- Require confirmation before sending, deleting, purchasing, changing settings, or taking irreversible actions.
- A voice command is treated the same as a typed command; voice alone does not bypass confirmation.

## Update procedure

When adding a capability, update this file with:

1. Capability name.
2. Required access or connector.
3. Risk level.
4. Confirmation rule.
5. Current status.

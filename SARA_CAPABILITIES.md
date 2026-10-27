# SARA Capability Guide

## Available commands

### Conversation

- Ask questions by text or voice.
- SARA aims to reply in the user's language and style, including Hindi/Hinglish.
- Hindi/Hinglish speech uses local Ollama transliteration to convert Roman Hindi words into Devanagari before the selected system voice reads them; Ollama must be running.
- SARA receives the live capability registry and should explain a missing feature, identify needed access where known, and offer to plan/implement it.
- Say `SARA` to wake the voice session.
- After waking, follow-up speech remains active for the current conversation window.
- Ask `SARA, system status batao` for a read-only check of Ollama, desktop control, browser runtime, approved memories, and pending reminders.

### Browser and web

- `SARA, Chrome kholo`
- `SARA, YouTube par music chalao`
- `SARA, search for Python tutorials`
- `SARA, Delhi ka weather batao`

Browser-opening and search actions require confirmation before opening a page.

Semantic browser actions are available through guarded endpoints:

- `POST /api/actions/browser-open` with an HTTPS URL
- `POST /api/actions/browser-click-text` with an HTTPS URL and exact visible text
- `POST /api/actions/browser-fill` with an HTTPS URL, accessible field label, and value

They use a separate SARA Chromium profile and require `confirmed: true`; SARA does not silently take over an existing personal Chrome session.

### Windows apps

Currently allowlisted:

- Chrome
- Notepad
- Calculator

SARA asks for confirmation before launching an application.

### Focused desktop actions

- `SARA, type Hello there in the focused app`
- `SARA, press Ctrl+C`
- `SARA, click 500, 300`

These actions require confirmation and act only on the currently focused Windows application. Coordinate clicks are screen-specific and should be used only when the user knows the target position.

Desktop readiness can be checked at `GET /api/desktop/status`; it reports only PyAutoGUI availability and screen dimensions, never a screenshot.

### Files

Read-only access is scoped to the project workspace. File creation, overwrite and deletion require explicit confirmation. `.venv` and `.git` are excluded from listing/read operations.
- Ask `SARA, workspace files dikhao` to list readable project files, or `SARA, read file SARA_SETUP_GUIDE.md` to inspect a scoped text file. Runtime data, `.env`, `.git`, `.venv`, `__pycache__`, and `sara_data` stay excluded.

### Reminders

- `SARA, remind me in 10 minutes`
- `SARA, remind me at 7 PM`

Reminders are stored locally and watched while the server is running.

### Tasks and daily planning

- `SARA, add task finish the SARA voice setup`
- `SARA, tasks dikhao`
- `SARA, complete task 1`
- `SARA, delete task 1`
- `SARA, aaj ka plan batao`

Tasks are stored locally. Creating, completing, or deleting a task requires confirmation.

The dashboard's Proactive suggestions toggle shows read-only suggestions from pending local tasks and reminders. It never executes an external action automatically.

### Learning and memory

- SARA can use explicitly approved memories shown in the dashboard.
- Ordinary chat is not silently saved as long-term memory; add a preference or fact through the approved-memory control.
- Say `SARA, remember that I prefer concise answers` or `SARA, learn that I prefer concise answers` to ask for an explicit confirmation before saving a preference. Use `memories dikhao` to review them and `forget memory 1` to remove one after confirmation.

### Messaging and email

SARA can prepare WhatsApp and email drafts. WhatsApp Web or a default mail app must be logged in/configured. SARA does not press Send automatically.

Email draft commands such as `draft email to name@example.com subject: Update body: Kal 5 baje milte hain` open a reviewable `mailto:` draft after confirmation.

### Local calendar

SARA can keep a local planned-event list, show it in chat, and cancel an event by its listed number after confirmation. Example: `schedule team sync tomorrow at 5 pm`, then confirm the proposed event; later use `calendar dikhao` and `cancel event 1`. This is local-only for now; Google/Outlook sync remains a separate future integration.

Use `export calendar` to download `/api/calendar.ics`, a standard calendar file that can be imported into Google Calendar or Outlook manually.

### Agenda and briefings

`What’s next?`, `briefing`, or `aaj ka plan` gives one read-only view of pending tasks, reminders, and planned events. The same data is available at `GET /api/agenda` for the dashboard.

Reminders can be reviewed with `reminders dikhao` and removed with `delete reminder N` after confirmation.

### Workspace coding help

SARA can create/update a scoped text file with `write file demo.py: print("Hello")` or remove one with `delete file demo.py`, but always asks for confirmation. `.env`, `.git`, `.venv`, `sara_data`, and path traversal are blocked.

Direct WhatsApp sending is now available only through the guarded endpoint `POST /api/actions/whatsapp-send`. It requires the recipient phone number, exact message text, a logged-in SARA Chromium profile, and final confirmation immediately before sending.

Chat example: `SARA, send WhatsApp +919876543210: I will reach home at 7 PM.`

## Pending capabilities

- Clicking and playing media inside browser pages without user-provided coordinates
- Google/Outlook calendar sync
- Automatic email sending
- Arbitrary application control
- Persistent notification service when the server is stopped

When a task needs a pending capability, SARA should explain the missing access and ask whether it should be implemented.

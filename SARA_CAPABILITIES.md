# SARA Capability Guide

## Available commands

### Conversation

- Ask questions by text or voice.
- SARA aims to reply in the user's language and style, including Hindi/Hinglish.
- Spoken replies are enabled by default, with automatic female system voice selection when available and a 1.15× default speed. The dashboard uses fast local Hinglish conversion for system speech. Settings diagnostics show the voice, language, and speed queued for the latest system reply, and warn if no Hindi voice was available. Settings also offers optional natural AI voice through the OpenAI API when configured; it uses API credits and is disclosed as AI-generated.
- SARA receives the live capability registry and should explain a missing feature, identify needed access where known, and offer to plan/implement it.
- Ask `SARA, what can you do?` or `capabilities dikhao` for a direct summary from the live registry, grouped into available, limited, and not-yet-configured features.
- If you ask for a missing feature (for example, `kya aap Google calendar sync bana doge?`), SARA returns a grounded implementation plan, required access, and the safe next command; she does not pretend that the feature already ran.
- The dashboard launches as a standalone SARA app window by default, without normal browser tabs or an address bar; use `SARA_UI_MODE=browser` only when you want a regular browser window.
- Say `SARA` to wake the voice session. Wake mode is enabled by default, remembered across dashboard reloads, and automatically re-arms after a reply or a short browser recognition timeout. The first browser microphone permission still needs to be allowed; some browsers also require one click on the dashboard before listening can start.
- One microphone click starts continuing hands-free conversation. Listening resumes after replies; direct follow-ups stay open for 60 seconds after playback finishes, then say `Sara` again. Temporary service/network errors reconnect without disabling the preference. Explicit mic Stop stays stopped; denied permission/device errors need user correction.
- AI text streams incrementally; routine replies use a bounded output/context budget. Greetings and existing local tool routes do not require an AI generation.
- System speech keeps mixed sentences together to avoid word-level voice-switch gaps, with local pronunciation cleanup, common technical Hindi phonetics, spoken acronym expansions, and an in-session preparation cache. Unfamiliar names and Roman Hindi spellings can still need a pronunciation entry.
- Add a custom say-as rule in Settings → Pronunciation guide, or say `pronounce Kalpana as कल्पना` and approve it. Entries are stored locally and affect speech only; chat text stays unchanged. Remove entries from the same Settings panel.
- Performance telemetry is available at `/api/performance`; reply timing is also attached to chat responses and terminal logs.
- Notepad notes use one exact-content review, create a unique verified UTF-8 file and request Notepad to open that file. Approved-memory profile drafts do not invent personal facts. Saved-note previews remain accessible if app launch fails.
- Short action follow-ups resolve session-scoped pending proposals and reopen review. Actual results appear in chat; stale, cancelled, modified and duplicate proposal execution is rejected.
- Ask `SARA, system status batao` for a read-only check of Ollama, desktop control, browser runtime, approved memories, and pending reminders.
- When a requested capability is missing, SARA explains its current status and required access, then offers to save the request locally. Approved requests appear under Settings & controls → Feature requests; saving only tracks the request and does not install or enable the feature.

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

You can add a custom shortcut in **Settings & controls → App shortcuts** by entering a name and the full path to an existing `.exe`. SARA keeps that allowlist in local `sara_data/apps.json`; you can remove an entry in Settings. Say `open VS Code` (using the shortcut name you saved) to request it in chat. SARA asks for approval before every launch. Only the executable path is launched: arguments and arbitrary shell commands are not supported.

### Focused desktop actions

- `SARA, type Hello there in the focused app`
- `SARA, press Ctrl+C`
- `SARA, click 500, 300`

These actions require confirmation and act only on the currently focused Windows application. Coordinate clicks are screen-specific and should be used only when the user knows the target position.

Desktop readiness can be checked at `GET /api/desktop/status`; it reports only PyAutoGUI availability and screen dimensions, never a screenshot.

### Files

Read-only access is scoped to the project workspace. File creation, overwrite and deletion require explicit confirmation. `.venv` and `.git` are excluded from listing/read operations.
- Ask `SARA, workspace files dikhao` to list readable project files, `SARA, read file SARA_SETUP_GUIDE.md` to inspect one, or `SARA, search project files for Kalpana` to find relevant lines. Search is bounded to text files in the project. `.env*`, common credential/key files, `.aws`, runtime data, `.git`, `.venv`, `__pycache__`, and `sara_data` stay excluded.

### Reminders

- `SARA, remind me in 10 minutes`
- `SARA, remind me at 7 PM`

Reminders are stored locally. They are checked while SARA is open. To keep checking when SARA is closed, run `powershell -ExecutionPolicy Bypass -File .\install_sara_reminders.ps1` from the project folder. The optional current-user Scheduled Task checks once per minute while you are signed in. Remove it with `powershell -ExecutionPolicy Bypass -File .\uninstall_sara_reminders.ps1`. Reminders and notification attempts stay on this PC.

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
- Replies use only records explicitly marked approved; relevant facts rank first and newer approved facts win ties. Unapproved/legacy records are left out of AI context.
- Ordinary chat is not silently saved as long-term memory; add a preference or fact through the approved-memory control.
- Say `SARA, remember that I prefer concise answers` or `SARA, learn that I prefer concise answers` to ask for an explicit confirmation before saving a preference. Use `memories dikhao` to review them and `forget memory 1` to remove one after confirmation.
- Corrections such as `Don't call me Boss, call me Lakshman`, `mujhe Lakshman bulao`, `mujhe Hindi mein jawab do`, or `I like short answers` also offer a confirmation before they become long-term memory. SARA does not save these automatically.

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
- Google/Outlook calendar sync (local events and ICS export are available; provider OAuth is not configured)
- Direct email account integration and automatic email sending (SARA opens reviewable drafts only)
- Automatic app discovery, arbitrary app arguments, and shell command execution
- Rich Windows toast notifications (current delivery uses a Windows message to the signed-in user)

## Implemented safety controls

- The dashboard shows a local action risk summary and a **Stop SARA actions / Resume** control.
- The backend enforces the stop state and explicit confirmation for data changes and computer actions, including direct API requests.
- Stop state lasts for the current server process; restarting the server resets it to running.

When a task needs a pending capability, SARA should explain the missing access and ask whether it should be implemented.

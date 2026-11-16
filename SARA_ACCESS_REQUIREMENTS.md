# SARA Access Requirements

This is the living checklist for permissions and integrations needed as SARA gains capabilities.

## Current status

| Capability | Access needed | Risk | Approval rule | Status |
|---|---|---:|---|---|
| Chat responses | Local Ollama or optional configured OpenAI | Low | User sends a message | Available |
| Voice input | Browser microphone permission | Medium | Start conversation/mic control; browser permission | Available; physical recognition still needs acceptance |
| Voice output | Installed WinRT/OneCore Windows voice; optional OpenAI mode uses credits | Low | Spoken replies preference; a browser gesture may be needed | Local Kalpana synthesis and standalone speaker playback verified; dashboard timing remains separate |
| Pronunciation preferences | Local `sara_data/pronunciations.json` | Low | Confirm save/remove | Available; affects speech only |
| Local memory | Local `sara_data` | Medium | Explicitly approved long-term facts | Available; edit/forget remain reviewed |
| Local tasks and daily plans | Local `sara_data/tasks.json` | Low | Confirm create/complete | Available |
| Local planned events | Local `sara_data/events.json` | Medium | Confirm create/delete | Available; external calendar sync not included |
| Local agenda/check-ins | Read local tasks, reminders and events | Low | Read-only request or opt-in check-in interval | Available; no actions or memory saved by a check-in |
| Trusted routines | Local persisted `sara_data/access_policy.json` | Medium | User selects Trusted routines; fresh scope/Stop check per execution | Enabled on this laptop as requested; only policy-allowlisted routine payloads skip review |
| Routine browser/media URLs | Default browser or separate SARA Chromium profile | Medium | Trusted mode permits bounded YouTube, Google/Bing searches and Wikipedia articles; other URLs reviewed | Available; player state is reported separately from page opening |
| Windows speaker status | Current user's default output endpoint via Windows CoreAudio | Low | Read-only `volume status` or Settings refresh | Available; read-only probe reported 40%/unmuted on this laptop |
| Speaker volume and mute | Windows CoreAudio default output endpoint; fixed local PowerShell bridge | Medium | Explicit command; reviewed in Review mode or permitted bounded control in Trusted mode; Stop still applies | Implemented with requested-change readback; actual mutation acceptance remains separate |
| Media transport keys | Fixed Windows media virtual keys | Medium | Explicit play/pause/next/previous/stop command, subject to mode and Stop | Implemented; dispatch evidence is not proof of the active player's response |
| Saved routine storage | Local `sara_data/routines.json` | Medium | Review exact name/steps for save/update; exact ID/revision for removal | Implemented; maximum 30 routines/eight steps; no automatic personal defaults |
| Saved routine execution | Existing bounded app/browser/YouTube/media adapters | Medium | Review the exact saved revision or run directly in Trusted mode; fresh Stop/trust/staleness check between steps | Implemented; individual and partial outcomes are retained; no nested routines, arbitrary executables or shell commands |
| Pasted/uploaded images | Pillow decoder and a local vision-capable Ollama model | Medium | Explicitly attach/send image | Implemented; `gemma3:4b` local generated-image responses verified with latency/accuracy limits in the ledger |
| Shared screen/window | Browser screen picker and a ready local vision model | Medium | Explicit Share screen/Stop; Send includes a current snapshot | Implemented; no default background screen capture |
| Camera snapshots | Browser camera permission and a ready local vision model | Medium | Explicit Camera/Stop; Send includes a current snapshot | Implemented; physical device flow needs acceptance |
| Optional visual check-ins | Already active share plus local vision model | Medium | Both proactive suggestions and shared-view check-ins explicitly enabled; selected idle interval | Fixture-verified opt-in snapshots; Stop/uncheck/hidden/new chat invalidates stale replies; no image-byte persistence |
| Dashboard assets | Project `assets` read access | Low | Local UI load | Available |
| Capability registry | Read local `sara_app/capabilities.py` | Low | Read-only | Available |

Latest verification on 16 November 2026: 343 isolated offline tests and twelve browser checks passed. The restarted server's read-only endpoints confirmed audio availability at 40%/unmuted, trusted mode and zero saved routines; no personal defaults or native volume/media/app effects were introduced by the verification run. See [SARA_PROJECT_STATUS.md](SARA_PROJECT_STATUS.md) for exact scope and remaining acceptance checks.

## Workflow details and remaining integrations

| Capability | Access needed | Risk | Approval rule | Status |
|---|---|---:|---|---|
| Weather lookup | Internet access to a weather service | Low | Can run automatically | Partial; fallback browser page requires confirmation |
| Open Chrome and websites | Desktop/browser control | Medium | Confirm unfamiliar or sensitive sites | Partial; HTTPS URL/search opening available |
| Read local files | Explicit workspace scope; protected runtime and secret paths excluded | Medium | Read-only scoped access | Available inside the project workspace |
| Create/edit files | Workspace write permission | High | Confirm exact path and overwrite | Available inside the safe workspace scope |
| WhatsApp message send | Logged-in SARA Chromium profile | Critical | Confirm recipient and exact message immediately before sending | Available through guarded Playwright action |
| Email account integration/send | Mail provider OAuth/API | High | Confirm recipients, subject and body | Planned; current app opens a reviewable mail draft only |
| Calendar events | Local project storage; external connector not required | Medium | Confirm before creating events | Local events available; Google/Outlook sync planned |
| Calendar export | Local read access to planned events | Low | Read-only download | Available as standard `.ics` |
| Local reminders | Project storage in `sara_data/reminders.json`; Windows `msg.exe`; optional current-user Scheduled Task | Medium | Confirm before creating/deleting; user explicitly runs installer to enable checks while SARA is closed | Available; server watcher or one-minute scheduled worker |
| List/read/search workspace files | Workspace read access; bounded text search; excludes runtime folders, `.env*`, and common credential/key files | Medium | No confirmation for read-only scoped access | Available |
| Write workspace files | Workspace write access | High | Always confirm exact path and content/overwrite | Available |
| Delete workspace files | Workspace write access | Critical | Always confirm exact path; no recursive delete | Available |
| WhatsApp message draft | WhatsApp Web login; recipient phone with country code | High | Confirm recipient and exact text; user presses Send | Draft available |
| WhatsApp message send | WhatsApp Web login in SARA Chromium profile; recipient phone with country code | Critical | Confirm recipient and exact text immediately before sending | Available through guarded Playwright action |
| Open allowlisted Windows apps | Windows process launch permission | Medium | Trusted mode can open built-in Chrome/Notepad/Calculator directly; custom executables reviewed every time | Available; no arguments or shell commands |
| Track a missing capability | Local SARA data folder | Low | Confirm before saving; removable in Settings | Available; tracking a request does not implement the feature |
| Email draft | Default mail app/browser; recipient, subject and body | High | Confirm recipient and exact content; user presses Send | Draft available |
| Desktop keyboard actions | PyAutoGUI in `.venv`; intended window must be focused | High | Confirm exact text/shortcut every time | Available: type text and safe keyboard shortcuts |
| Coordinate click | PyAutoGUI in `.venv`; user must provide screen coordinates | High | Confirm exact coordinates every time | Available through the guarded action API |
| Desktop readiness | No additional credential; local screen access | Low | Read-only status endpoint | Available; no screenshots collected |
| Semantic browser actions | Playwright Chromium runtime; site login may be needed | High | Narrow routine navigation may use trusted mode; exact clicks/fills/sends remain reviewed | Available through SARA's separate Chromium profile |
| Stop SARA actions | Local server process | Low | Immediate stop; restart/resume from dashboard | Available; in-memory and resets when server restarts |
| Application launch/close | Windows desktop control | Medium | Safe apps can be opened; closing work needs confirmation | Planned |
| System settings | Windows desktop control | High | Always confirm changes | Planned |
| Shutdown/restart | Windows system permission | Critical | Always require explicit confirmation | Planned |
| Purchases or payments | Payment site/account access | Critical | Not enabled by default; explicit confirmation required | Planned |

## Rules

- Never store passwords, API keys, session cookies, or message contents in the repository.
- Request the smallest permission scope that can complete the task.
- Explain what access is needed before enabling a new integration.
- Keep an activity log for actions and failures.
- Require confirmation before sending, deleting, purchasing, sensitive settings changes or irreversible actions. Explicitly requested bounded speaker/media controls may use the persisted Trusted routines exception.
- Saving a routine does not authorize its future edited contents. Execution binds the current saved name, ID, revision and complete step list; changed/deleted snapshots and overlapping runs are rejected. Stop or revoked trust prevents further steps while preserving earlier outcomes.
- A voice command is treated the same as a typed command; voice alone does not bypass confirmation.
- Trusted mode is a scoped app preference, not an administrator grant. Unknown actions, custom executables, focused-window input and consequential changes remain reviewed.
- Shared images go only to loopback Ollama after validation. The optional cloud text provider is not a fallback for private image inputs. Captures are not saved in conversation files; only source/count/dimension metadata may be retained.
- Starting a share does not enable periodic visual check-ins. The separate checkbox is required, alongside proactive suggestions; stop controls and the selected check-in interval govern access.

## Update procedure

When adding a capability, update this file with:

1. Capability name.
2. Required access or connector.
3. Risk level.
4. Confirmation rule.
5. Current status.

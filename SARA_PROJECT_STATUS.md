# SARA — Product specification and development status

**Read this first when continuing SARA in a new chat.** This is the current product target and handoff ledger. Check the actual worktree before relying on any status below.

- Last updated: **13 November 2026**.
- Actual checkout observed: **`D:\SARA`**. The configured `D:\sara ai` path was absent during this session.
- Overall state: **working local assistant with ongoing development**. The complete Jarvis-style vision is not yet finished or fully verified.
- Latest implemented milestone: **trusted routine access, visual chat inputs and local Windows speech activation**, building on the live animated HUD. The full Jarvis vision remains in development; verification and machine readiness are recorded below.
- Supporting references: [technical context](SARA_PROJECT_CONTEXT.md), [setup/run guide](SARA_SETUP_GUIDE.md), [command guide](SARA_CAPABILITIES.md), [access rules](SARA_ACCESS_REQUIREMENTS.md), [long-term blueprint](SARA_AI_BLUEPRINT.md).

## What we are building

SARA is a personalized, local-first Windows assistant inspired by Jarvis. It should understand natural Hindi, Hinglish and English; hold useful conversations; remember approved preferences; help plan the user's day; and complete clearly scoped computer tasks through real tools. It should explain missing capabilities and help plan improvements honestly.

### Current user requirements

| ID | Requirement | What counts as success |
|---|---|---|
| R1 | Personal Windows assistant | Useful conversation and modular local workflows; app behaviour matches what SARA claims it can do. |
| R2 | Clear Hindi/Hinglish speech | Hindi words sound natural, chosen installed voice and speed persist, and English words/names stay intact. Actual sound must be checked on Windows. |
| R3 | Animated Jarvis HUD | Dark glass, cyan rings, segmented motion, scan details and restrained orange accents inspired by the supplied [Pinterest video](https://www.pinterest.com/pin/1001347298402977683/). Build live canvas/SVG motion; do not use a screenshot, portrait picture, or embedded reference video as the UI. |
| R4 | Honest visual state | Ready, listening, thinking, speaking and review states reflect actual app events. Speaking motion begins with playback, not while audio is still being prepared. |
| R5 | Visible, durable conversation | Questions and answers appear in chat, survive restart within documented retention, and are available in local logs/activity. |
| R6 | Reviewable learning | Approved facts/preferences improve replies; corrections can be reviewed, edited and forgotten. Ordinary chat is not silently promoted to long-term memory. |
| R7 | Capability awareness | SARA knows current feature status, scope and approval requirements, states limitations, and can keep a local feature request/build outline. Saving a request must not be reported as implementing it. |
| R8 | Safe computer workflows | Named tools, app/file scope, exact review, session isolation, real result evidence and an action-stop control. No unrestricted shell or silent consequential actions. |
| R9 | Continuity across chats | This ledger records target, implementation, evidence and next work; every development pass updates it. |
| R10 | Fewer repeated reviews | Persisted Trusted routines runs only named, bounded browsing/media and built-in app actions directly. Stop, exact results and reviews for consequential changes remain enforced; this is not unrestricted Windows administrator access. |
| R11 | Image, screen and camera understanding | Paste/upload/drop images with previews/removal. Explicit screen/camera Start/Stop controls share snapshots only with user-sent messages and a verified local vision model; no hidden capture, image persistence or cloud fallback. |
| R12 | SARA initiates useful conversation | Start conversation enables speech/mic and a local greeting. Optional periodic local check-ins respect the user's interval and pause while busy, speaking, reviewing or hidden. Learning uses current context and approved memory, not silent self-training. |

The latest HUD requirement supersedes older portrait/illustration-based UI descriptions in the blueprint or technical context. Preserve useful backend work while replacing that presentation.

## Architecture that exists today

- **Desktop experience:** local web UI, usually opened in a standalone Edge app window; Python entry point [sara_server.py](sara_server.py), launcher [start_sara.bat](start_sara.bat), default address `http://127.0.0.1:8765`.
- **Frontend:** [index.html](index.html), [dashboard.js](assets/dashboard.js), [dashboard.css](assets/dashboard.css), [action-router.js](assets/action-router.js), procedural renderer [hud-core.js](assets/hud-core.js), and interface skin [hud-theme.css](assets/hud-theme.css).
- **Conversation/model:** [ai.py](sara_app/ai.py), Ollama `llama3.2` first, optional configured OpenAI, then an honest local fallback. No model is downloaded automatically.
- **Local data:** [storage.py](sara_app/storage.py), JSON lists and activity JSONL under ignored `sara_data/`; atomic replacement and malformed-source recovery backups.
- **Actions:** [policy.py](sara_app/policy.py), [action_state.py](sara_app/action_state.py), [intents.py](sara_app/intents.py), [server.py](sara_app/server.py), and separate desktop/browser/note adapters.
- **Scheduling:** [scheduling.py](sara_app/scheduling.py), [scheduling_dialogue.py](sara_app/scheduling_dialogue.py), [planner_validation.py](sara_app/planner_validation.py), and [reminder_delivery.py](sara_app/reminder_delivery.py).
- **Visual input:** [vision-client.js](assets/vision-client.js), [vision-controls.css](assets/vision-controls.css) and [vision.py](sara_app/vision.py). Image bytes are ephemeral, model capability is checked through local Ollama, and history retains only attachment metadata.
- **Local speech:** [windows_speech.py](sara_app/windows_speech.py) and fixed [windows_voice.ps1](sara_app/windows_voice.ps1) use installed Windows OneCore/WinRT voices and return WAV for browser playback; browser speech remains a fallback.

## Implemented work and its evidence

“Implemented” means code exists. The verification column states what has actually been checked; mocks do not prove physical audio, visible native apps, or external account integration.

| Area | Implemented behaviour | Evidence and practical limit |
|---|---|---|
| Conversation | Incremental text, bounded model context/output, provider fallback, timing telemetry | [AI tests](tests/test_ai_performance.py), [streaming tests](tests/test_chat_streaming.py), [browser interaction check](tests/ui_interaction_smoke.py). Live answer quality still depends on the configured model. |
| Hindi/English preparation | Hindi-script replies, conservative Roman-Hindi lexicon, sentence-local language context, acronym/Markdown cleanup, approved pronunciation rules | [speech.py](sara_app/speech.py), [speech tests](tests/test_speech.py). Unknown spellings/names can need a say-as entry; actual pronunciation remains unverified. |
| Voice session | Saved voice identity, delayed voice-list handling, pronunciation cache refresh, playback-start/end states, stuck-start recovery, automatic listening resume and 60-second follow-ups | [voice preference check](tests/ui_voice_preferences_smoke.py), [voice-session check](tests/ui_voice_session_smoke.py). Devices and speech engines were mocked. |
| History and logs | Local conversation persistence, recent history rendering, question/answer trace logging, bounded activity reads | [storage.py](sara_app/storage.py), [streaming tests](tests/test_chat_streaming.py), [history rendering check](tests/ui_interaction_smoke.py). Storage keeps 200 turns; the history endpoint returns the latest 30. |
| Memory | Explicit approval, approved-only AI/list/count semantics, preference recency, reviewed edits and exact-text deletion | [server.py](sara_app/server.py), [intents.py](sara_app/intents.py), [action workflow tests](tests/test_action_workflow.py). Legacy/unapproved records remain reviewable in Settings. |
| Data resilience | Invalid UTF-8/JSON/record shapes do not crash list readers; original malformed bytes are backed up before replacement; backup failure aborts the write | [recovery tests](tests/test_storage_recovery.py). Recovery backups remain local and must not be committed or exposed. |
| Capability awareness | Live status/scope/approval registry, grounded overview, feature requests with access requirements and implementation steps | [capabilities.py](sara_app/capabilities.py), [ai.py](sara_app/ai.py), [intents.py](sara_app/intents.py). This tracks plans; it is not autonomous code modification. |
| Planner | Local tasks/events/ICS, Hindi/Hinglish/English time parsing, short time clarifications, future-aware ISO validation, duplicate-ID rejection | [parser tests](tests/test_scheduling.py), [dialogue tests](tests/test_scheduling_dialogue.py), [API tests](tests/test_planner_api.py), [workflow tests](tests/test_scheduling_workflow.py). Latest local-time review display still needs browser verification. |
| Scoped computer help | App allowlist/custom executable shortcuts, reviewed Notepad notes, safe project text operations, keyboard/browser adapters, draft workflows | [tools.py](sara_app/tools.py), [desktop.py](sara_app/desktop.py), [browser_control.py](sara_app/browser_control.py), [notes.py](sara_app/notes.py), [review browser check](tests/ui_action_workflow_smoke.py). Current mock checks do not prove a native window opened or an external message was delivered. |
| Reminder delivery | Shared reminder claims/retries and optional per-user scheduled worker | [reminder_delivery.py](sara_app/reminder_delivery.py), [installer](install_sara_reminders.ps1). Real notification delivery and optional task installation were not verified in this pass. |
| HUD redesign | Live cyan/orange canvas core, dark-glass panels and coherent chat/planner/memory/settings styling; ready/thinking/listening/speaking/review states follow app events | [hud-core.js](assets/hud-core.js), [hud-theme.css](assets/hud-theme.css), [HUD browser check](tests/ui_hud_smoke.py). Verified pixel/frame motion, no portrait/video requests, DPR cap of 2, hidden-view pause/resume and static reduced-motion rendering. Speaking begins only on the mocked TTS start event; actual speaker latency remains unverified. |
| Trusted routines | Persisted review/trusted mode, fresh payload-aware allowlist and Stop check, one proposal/outcome per automatic chat action; sensitive changes remain reviewed | [policy.py](sara_app/policy.py), [dispatcher](sara_app/tools.py), [policy tests](tests/test_trusted_actions.py), [workflow tests](tests/test_trusted_workflow.py). Trusted scope is built-in Chrome/Notepad/Calculator, bounded YouTube/Google/Bing navigation and Wikipedia articles. Custom apps, arbitrary URLs, sends, deletes, writes and focused input still need review. |
| YouTube playback | Hindi/Hinglish/English play requests search YouTube and try the first normal video result in the controlled browser | [browser_control.py](sara_app/browser_control.py), [playback tests](tests/test_youtube_playback.py). Results distinguish search opened, video opened and an audible non-ad player state; consent/autoplay/network failures never become a false playback claim. Live playback still needs verification. |
| Visual chat | Paste/drop/upload PNG, JPEG or WebP; up to four images/10 MB, previews/removal; explicit screen/camera preview, snapshot and Stop; optional live-view snapshot on Send | [vision.py](sara_app/vision.py), [controls check](tests/ui_vision_controls_smoke.py), [visual chat check](tests/ui_visual_chat_smoke.py). Local-only validated/decoded images, no image-byte persistence/cloud fallback. Browser permissions and actual camera/screen/model quality require live acceptance checks. |
| Native Windows speech | Installed voices including OneCore Kalpana, preserved voice/speed, local WAV generation, actual playback-event HUD timing, browser fallback and Retry voice diagnostics | [windows_speech.py](sara_app/windows_speech.py), [speech tests](tests/test_windows_speech.py), [Start conversation check](tests/ui_voice_start_smoke.py). Real Kalpana WAV generation is verified below; physical audibility/accent/latency remains unverified. |
| Proactive conversation | Opt-in local check-ins every 5/15/30/60 minutes, default 15; paused while busy/speaking/reviewing/hidden; Start conversation gives a local greeting and enables speech/listening | [dashboard.js](assets/dashboard.js), `/api/check-in`. These use local agenda/context and do not execute actions, capture images or silently save memory. |

## Verification record

| Observed run | Result | Scope |
|---|---|---|
| 13 Nov 2026, pre-scheduling pass | **135 offline tests passed** | Isolated temporary data; speech, memory, actions, storage, providers mocked as appropriate. |
| 13 Nov 2026, pre-HUD browser pass | **5 browser scripts passed** | Saved-history rendering, streaming, approvals, voice/session mocks, avatar state timing and desktop/mobile layout. Applies to the earlier UI, not the new HUD. |
| 13 Nov 2026, scheduling integration pass | **208 offline tests passed** | Added natural-time parsing, session clarification, planner API validation and reviewed-write regressions. |
| 13 Nov 2026, Windows voice inventory | **Microsoft Kalpana entry present** | Read-only inventory; does not establish pronunciation, actual playback or speaker latency. |
| 13 Nov 2026, HUD integration pass | **210 offline tests and six browser scripts passed** | Current isolated-data suite plus interaction, approval, voice preference, voice session, viewport and HUD checks. Desktop layouts fit at 1366×768, 1024×768, 1092×614 and 1024×600; 800×600 uses the mobile vertical-scroll layout. Mocked-data screenshots at 1440×900 and 390×844 were visually inspected for readability and coherent styling. No real consequential app action, external provider evaluation or physical audio claim follows from these checks. |
| 13 Nov 2026, broader access/visual integration | **266 offline tests passed** | Isolated data and mocked tools/providers, including trust/revocation/Stop, automatic action outcomes, visual validation/local-provider boundaries and Windows speech validation. Final browser/model readiness is recorded in the next row. |
| 13 Nov 2026, actual Windows speech generation | **Microsoft Kalpana, hi-IN, 1.1× produced a 76,462-byte RIFF/WAV** | Real installed WinRT voice synthesis succeeded. The bytes were not played/listened to; pronunciation, physical speaker output and perceived animation latency are not established. |
| FINAL INTEGRATION UPDATE — root must replace this row | **PENDING final browser totals, vision-model readiness and trusted preference activation** | `gemma3:4b` download was in progress at handoff. Do not call image understanding ready until installation, local vision capability discovery and a real image request succeed. Reconcile the prior six browser scripts with new visual controls/chat and voice-start checks. |

## Completed milestone and remaining work in priority order

- [x] **Completed — Live HUD redesign.** Procedural animated core replaces portrait/video presentation, all main views use the new skin, desktop/mobile visuals were inspected, and the six browser checks pass. The HUD represents app state; it does not imply extra computer access or fabricated CPU/network measurements.
- [x] **Implemented — Trusted routine access and YouTube play route.** Persisted scoped grant, direct routine execution, Stop/revocation guards and truthful player evidence; consequential workflows retain review.
- [x] **Implemented — Visual chat and explicit screen/camera controls.** Image paste/upload/drop, previews/removal and user-sent snapshots with local-only model detection and no image persistence.
- [x] **Implemented — Start conversation and native Windows speech.** Speech/mic activation, local greeting, installed OneCore voice path, fallback/retry diagnostics and optional local check-ins.
- [ ] **P0 — Complete real local vision acceptance.** Verify model download/capability readiness, run one deliberate local image question and record answer quality/latency; then test actual screen/camera permissions, Stop and snapshot behavior without retaining private image bytes.
- [ ] **P0 — Verify real Windows speech.** Restart current app; select Kalpana and chosen speed; listen to Hindi, Roman-Hindi, mixed English terms and a custom pronunciation before/after reload; observe motion start/end against actual sound. Record precise failures instead of claiming the accent is fixed from mocks.
- [ ] **P0 — Verify newest scheduling review UI.** Show parsed local date/time and timezone alongside the exact stored instant; check short clarification, cancellation, approval, invalid input and duplicate rejection through the UI.
- [ ] **P1 — Live end-to-end workflow checks.** Review and execute one scoped app launch, Notepad note, task, calendar item and reminder in an explicitly chosen disposable test flow; inspect actual outcomes and cleanup plans. Mock success alone is insufficient.
- [ ] **P1 — Improve intelligence from observed use.** Evaluate multi-turn Hindi/Hinglish understanding, name/style preferences, relevant memory retrieval, missing-feature explanations, and model latency on this laptop. Keep failures as reproducible examples; choose model improvements from measured behaviour.
- [ ] **P1 — Strengthen planner/delivery usability.** Verify real notification timing, optional worker behaviour while the server is closed, reschedule/edit workflows, malformed legacy records and local-time display. Recurrence and richer Windows notifications remain further work.
- [ ] **P2 — Expand safe task execution.** Add small, real-result-driven app/browser workflows with previews, stop handling and explicit per-step scope; broader Windows control remains planned.
- [ ] **P2 — Richer continuous assistance and voice.** Explicit image/screen/camera snapshot inputs now exist; continuous autonomous visual reasoning, low-latency interruption and broader app execution still need bounded designs and live evidence. Approved memory/context is not model self-training.
- [ ] **P2 — External integrations.** Google/Outlook OAuth sync, direct email account access, and other connectors need configured providers, reviewed scopes and actual account verification. Existing local events/ICS and email drafts remain the working baseline.
- [ ] **P2 — Packaging and continuity.** Consider a signed native installer and robust startup/update/recovery flows. Maintain this ledger as the product evolves; the current app is a local web app with a desktop-style window.

## Run and verify

From the actual checkout:

```powershell
cd "D:\SARA"
.\start_sara.bat
```

Restart the server after backend changes and use `Ctrl+F5` after frontend changes. See the setup guide before installing dependencies, models or optional workers.

Offline checks use temporary data and leave personal SARA data out of the test run:

```powershell
.\.venv\Scripts\python.exe tests\run_offline.py
.\.venv\Scripts\python.exe tests\ui_interaction_smoke.py fixture
.\.venv\Scripts\python.exe tests\ui_action_workflow_smoke.py fixture
.\.venv\Scripts\python.exe tests\ui_voice_session_smoke.py fixture
.\.venv\Scripts\python.exe tests\ui_voice_preferences_smoke.py
.\.venv\Scripts\python.exe tests\ui_smoke.py fixture
.\.venv\Scripts\python.exe tests\ui_hud_smoke.py
.\.venv\Scripts\python.exe tests\ui_vision_controls_smoke.py
.\.venv\Scripts\python.exe tests\ui_visual_chat_smoke.py
.\.venv\Scripts\python.exe tests\ui_voice_start_smoke.py
```

The browser fixture intercepts approved dashboard assets/API mocks and needs no repository-wide HTTP server. The HUD assets are included in its allowlist. Run meaningful checks for the changed behaviour; record the exact result and its limits.

## Recent work and next-chat handoff

- Stabilized voice preparation and saved voice restoration; added isolated tests and browser fixtures.
- Aligned approved-memory context/list/count/delete semantics; added stale-review protection and data recovery backups.
- Added shared natural-time parsing, session-scoped scheduling clarification and planner API validation.
- Delivered the new user direction: live procedural Jarvis HUD with state-driven motion, plus this status/specification file and read-first [AGENTS.md](AGENTS.md) instructions.
- Added persisted trusted routines/YouTube playback, visual chat with explicit screen/camera controls, native WinRT voice playback, Start conversation activation and optional proactive local check-ins.
- Current next priorities: finish/reconcile the final verification row, verify the local vision model and real image response, listen to real Kalpana output and observe speaker timing, then verify scheduling review and real scoped workflows. Do not equate full-system access with unrestricted shell/admin control or continuous hidden monitoring.
- The worktree already contains substantial staged/uncommitted development. Inspect `git status` and preserve existing work; do not reset, unstage or overwrite it casually.

For a new chat, open the actual SARA project folder so [AGENTS.md](AGENTS.md) is available. A chat opened elsewhere will not necessarily discover this repository automatically; attach this file or paste its path. Suggested prompt:

> Read `D:\SARA\AGENTS.md`, then `SARA_PROJECT_STATUS.md`, `SARA_PROJECT_CONTEXT.md` and `SARA_SETUP_GUIDE.md`. Inspect current files and git status. Continue the highest-priority unfinished SARA requirement, preserve existing work, run appropriate isolated verification, and update the status ledger with implementation evidence and remaining limits. The target is a personalized Jarvis-style local Windows assistant with natural Hindi/Hinglish speech and a live procedural HUD, not a finished claim based only on mock tests.

After every meaningful development pass, update the relevant feature row, verification record, remaining checklist and this handoff. Keep secrets, actual personal memories, message contents and private logs out of these documents.

# SARA — Product specification and development status

**Read this first when continuing SARA in a new chat.** This is the current product target and handoff ledger. Check the actual worktree before relying on any status below.

- Last updated: **16 November 2026**.
- Actual checkout observed: **`D:\SARA`**. The configured `D:\sara ai` path was absent during this session.
- Overall state: **working local assistant with ongoing development**. The complete Jarvis-style vision is not yet finished or fully verified.
- Latest implemented milestone: **Named chats, local focus/study tools and task metadata**, building on dynamic appearance, media controls, saved routines, visual chat and native speech. The complete Jarvis vision remains in development.
- Current verification: **354 isolated offline tests passed**; this pass also passed named-chat/productivity, action workflow, interaction, voice-session, appearance and viewport browser checks. Other browser results in older sections are historical. Server restarted; empty named and legacy chat stores verified after the user-requested reset.
- Supporting references: [technical context](SARA_PROJECT_CONTEXT.md), [setup/run guide](SARA_SETUP_GUIDE.md), [command guide](SARA_CAPABILITIES.md), [access rules](SARA_ACCESS_REQUIREMENTS.md), [long-term blueprint](SARA_AI_BLUEPRINT.md).

## What we are building

### 16 November 2026 — supplied specification, organized chats and free productivity

- User supplied a J.A.R.V.I.S. specification excerpt with category counts totalling 543 features, not a complete itemized implementation specification. See [free feature roadmap](SARA_FREE_FEATURE_ROADMAP.md) for concrete implemented scope and remaining work. No new paid API/provider enabled.
- Added atomic `sara_data/chats.json` named conversation storage: up to 100 chats, latest 200 turns each. New/resume/rename/export/delete controls sit above chat. Model context, visual question context, action outcomes and proactive replies use the selected chat. Approved memories remain shared intentionally. Session action identity is renewed when switching chats; proposals also bind chat identity. Late generation cannot recreate a deleted chat. Legacy log fallback was removed so empty histories stay empty.
- Added My day focus/break timer with configurable durations, pause/reset, completion counter and reload-safe deadlines. Timer and flashcard deck are browser-local. Flashcards support save/delete, flip, self-assessed review rounds and a model-assisted quiz shortcut. No background timer notification or automatic app blocking is claimed.
- Added task priority/category and explicit due-date picker, included in exact action review and persistence. New commands: `high priority task study physics`, `add to shopping list milk bread eggs`. Natural task deadline parsing remains pending; reminder natural-date handling already exists.
- Explicit user-requested fresh start executed with server stopped: cleared `conversations.json`, `chats.json`, `activity.jsonl`, and removed 10 stdout/stderr transcript logs under `sara_data/runtime`. No backup was made; deletion is permanent through this operation. Memories, notes, tasks and reminders were not reset. After restart, GET checks reported zero saved chats and zero legacy turns. Refresh an existing browser window to discard its old rendered messages and initialize a new chat.
- Checks: 354 offline tests plus six browser scripts listed at the top passed. Tests cover context isolation, per-chat retention, deletion during generation, cross-chat approval rejection, original task metadata, named-chat navigation/export/delete, deadline restoration, flashcards, speech flow and responsive layout. Native microphone/voice, external websites and physical apps were not exercised by mocks.

### 16 November 2026 — dynamic dashboard appearance

- Added five selectable looks (Jarvis, Warm companion, Playful buddy, Aurora, Focus) using `assets/appearance.js` / `.css`. Topbar Look button cycles looks; Settings → Make SARA yours selects a look or rotation mode. Preferences persist locally. Daily rotation is the default for users without a saved mode; manual selection locks the selected look. Optional rotation runs every 30 minutes, deferred while busy, speaking, recognizing voice, reviewing an action, or holding an unsent draft; hidden pages do not rotate.
- Live canvas supports rings, orbit designs, a cartoon robot face, and a minimal ring. All use current speaking/listening/thinking/review state; reduced motion is respected. Chat, approval, capture and planner DOM is retained, not rebuilt when appearance changes. Theme choice does not enable new tools.
- Verified with `ui_appearance_smoke.py`: five looks, draft preservation, saved preferences, working mocked chat, 1024/390 widths, daily preference and clock-simulated idle rotation deferral/resumption. Existing `ui_hud_smoke.py` passed for motion/playback synchronization and accessibility. Inspected the Playful screenshot. Hardware voice/capture and every action were not retested per theme.
- General adaptive task layouts and broader Windows automation remain pending; appearance is now dynamic, not all planned capabilities are implemented.

### 16 November 2026 — icon and search continuity repair

- Added a geometric cyan S mark as `assets/sara-icon.svg` and multi-size Windows `assets/sara.ico`, linked from the dashboard. Rebuild the ICO with `build_sara_icon.py` (Pillow). Browser app/taskbar icon refresh depends on browser/Windows caching; the actual taskbar appearance has not been visually verified.
- Removed the previous follow-up implementation that prepended old conversation prose to executable command text and recursively saved it. New search routing reads only recent search metadata from the same dashboard session, keeps original user messages, and handles `ab search python`, `python tutorials search karo`, and `search that`. A missing reference asks for the topic.
- Search follows existing action review/trusted mode. It opens a search URL; it does not read results or guarantee navigation in a particular existing Chrome tab. General cross-app continuity and page extraction remain pending.
- Verification: 349 isolated offline tests passed, including new routing, original-message persistence and cross-session isolation checks. `git diff --check` passed. Earlier browser check counts above are historical, not rerun for this pass.

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
| R11 | Image, screen and camera understanding | Paste/upload/drop images with previews/removal. Explicit screen/camera Start/Stop controls share snapshots with user-sent messages. Separately enabled visual check-ins may sample the already shared view at the chosen interval; no hidden capture, image persistence or cloud fallback. |
| R12 | SARA initiates useful conversation | Start conversation enables speech/mic and a local greeting. Optional periodic local check-ins respect the user's interval and pause while busy, speaking, reviewing or hidden. Learning uses current context and approved memory, not silent self-training. |
| R13 | Useful Windows audio controls | Explicit Hindi/Hinglish/English commands or Settings controls change volume/mute through Windows CoreAudio and report readback. Media transport reports that a fixed key was dispatched; it does not invent player-state evidence. |
| R14 | One command for a saved workflow | Create, list and run named routines of at most eight bounded steps. Saving/updating/removing remains reviewed; trusted execution binds the current saved revision and checks Stop, grant revocation and partial outcomes between steps. |

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
- **Audio and named workflows:** [system_controls.py](sara_app/system_controls.py), fixed [system_audio.ps1](sara_app/system_audio.ps1), [routines.py](sara_app/routines.py), and deterministic [ability_intents.py](sara_app/ability_intents.py). Settings controls live in [abilities-client.js](assets/abilities-client.js) and [abilities-controls.css](assets/abilities-controls.css).

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
| Visual chat | Paste/drop/upload PNG, JPEG or WebP; up to four images/10 MB, previews/removal; explicit screen/camera preview, snapshot and Stop; optional live-view snapshot on Send | [vision.py](sara_app/vision.py), [controls check](tests/ui_vision_controls_smoke.py), [visual chat check](tests/ui_visual_chat_smoke.py). Local-only validated/decoded images, no image-byte persistence/cloud fallback. Actual local model response was verified on generated shapes; real camera/screen flows, broader accuracy and language adherence remain acceptance work. |
| Native Windows speech | Installed voices including OneCore Kalpana, preserved voice/speed, local WAV generation, actual playback-event HUD timing, browser fallback and Retry voice diagnostics | [windows_speech.py](sara_app/windows_speech.py), [speech tests](tests/test_windows_speech.py), [Start conversation check](tests/ui_voice_start_smoke.py). Real WinRT synthesis and speaker playback succeeded, and the user confirmed hearing the Kalpana test line. Browser playback, mixed-language pronunciation quality and perceived HUD/audio latency still need live acceptance checks. |
| Proactive conversation | Opt-in local check-ins every 5/15/30/60 minutes, default 15; paused while busy/speaking/reviewing/hidden; Start conversation gives a local greeting and enables speech/listening | [dashboard.js](assets/dashboard.js), [check-in tests](tests/test_check_in.py), [proactive browser check](tests/ui_proactive_smoke.py). Visual check-ins require both checkboxes and an already shared view; queued uploads are never sampled. Stop, unchecking, hiding or a new chat aborts/invalidates stale replies. Snapshot reasoning uses a separate bounded background path without foreground chat history, memory context, cloud fallback or action execution. It still shares CPU/model resources. |
| Windows audio/media | Absolute volume 0–100%, bounded volume up/down, mute/unmute, and play/pause/next/previous/stop media keys; Settings exposes the same named commands | [system_controls.py](sara_app/system_controls.py), [audio tests](tests/test_system_controls.py). Nineteen focused mocked tests passed and a read-only Windows probe reported 40%/unmuted. Volume/mute mutations need real readback acceptance; dispatched transport keys do not prove playback changed. |
| Saved named routines | Local `sara_data/routines.json`, at most 30 routines/eight steps; Settings builder and chat create/run/list; reviewed save/update/delete, exact revision-bound execution, fresh Stop/trust checks, and visible/persisted per-step outcomes | [routines.py](sara_app/routines.py), [intent parser](sara_app/ability_intents.py), [routine tests](tests/test_routines.py), [workflow tests](tests/test_ability_workflow.py), [UI workflow check](tests/ui_abilities_workflow_smoke.py). Focused and integrated checks cover replay/stale rejection, valid frozen updates, partial results and readable persisted step outcomes after reload. Steps allow built-in apps, approved routine URLs/searches, YouTube and media controls; no nested routines, shell, custom executables or consequential actions. No personal routine is seeded automatically. |

## Verification record

| Observed run | Result | Scope |
|---|---|---|
| 13 Nov 2026, pre-scheduling pass | **135 offline tests passed** | Isolated temporary data; speech, memory, actions, storage, providers mocked as appropriate. |
| 13 Nov 2026, pre-HUD browser pass | **5 browser scripts passed** | Saved-history rendering, streaming, approvals, voice/session mocks, avatar state timing and desktop/mobile layout. Applies to the earlier UI, not the new HUD. |
| 13 Nov 2026, scheduling integration pass | **208 offline tests passed** | Added natural-time parsing, session clarification, planner API validation and reviewed-write regressions. |
| 13 Nov 2026, Windows voice inventory | **Microsoft Kalpana entry present** | Read-only inventory; does not establish pronunciation, actual playback or speaker latency. |
| 13 Nov 2026, HUD integration pass | **210 offline tests and six browser scripts passed** | Current isolated-data suite plus interaction, approval, voice preference, voice session, viewport and HUD checks. Desktop layouts fit at 1366×768, 1024×768, 1092×614 and 1024×600; 800×600 uses the mobile vertical-scroll layout. Mocked-data screenshots at 1440×900 and 390×844 were visually inspected for readability and coherent styling. No real consequential app action, external provider evaluation or physical audio claim follows from these checks. |
| 13 Nov 2026, broader access/visual integration | **266 offline tests passed** | Historical isolated-data pass including trust/revocation/Stop, automatic action outcomes, visual validation/local-provider boundaries and Windows speech validation. Superseded by the later verification runs below. |
| 13 Nov 2026, actual Windows speech generation | **Microsoft Kalpana, hi-IN, 1.1× produced a 76,462-byte RIFF/WAV** | Real installed WinRT voice synthesis succeeded. The bytes were not played/listened to; pronunciation, physical speaker output and perceived animation latency are not established. |
| Previous exchange, actual Windows playback | **Kalpana Hindi test line was audible, confirmed by the user** | Real local WinRT synthesis and `winsound` speaker playback completed for a 169,326-byte WAV. This confirms the installed voice and selected speaker path; it does not establish actual dashboard playback or universal pronunciation/latency quality. |
| 16 Nov 2026, resumed model inventory | **`gemma3:4b` installed, 3.4 GB** | The earlier download completed; local discovery confirmed vision support and Pillow decoding is available. |
| 16 Nov 2026, earlier visual/voice integration verification | **284 offline tests and all ten browser checks passed** | Historical baseline before the newer audio/named-routine bundle; offline run: 0.845 seconds with isolated data/mocked tools. Browser scripts: layout, chat interaction, action workflow, voice preferences, voice session, HUD, visual controls, visual chat, voice start and proactive check-ins. Visual-check-in tests cover background isolation/bounds and route validation. No fixture captures a physical camera, microphone or screen. |
| 16 Nov 2026, real local vision smoke | **Basic generated-shape understanding verified** | Actual `ollama-vision` responses identified red-left/blue-right colors/positions. The first cold request took 60.43 seconds and called the rectangle a square. A tightened short prompt took 57.53 seconds and identified the red rectangle/blue circle correctly but replied in English despite a Hindi instruction; observed smoke-request times ranged about 33–60 seconds. This is limited evidence, not general accuracy or interactive-speed assurance. No personal or physical-device image was used. |
| 16 Nov 2026, live SARA readiness | **Updated server started; readiness and local WAV endpoint verified** | Health reports Ollama and `llama3.2` ready. Access mode is `trusted`, actions are not stopped. Vision reports `gemma3:4b`, decoder available, `images_saved:false` and `cloud_upload:false`. Windows inventory reports ten voices; an actual `/api/tts/windows` request returned HTTP 200, `audio/wav`, 76,462 bytes and Microsoft Kalpana. This API probe was not played; the earlier user-confirmed speaker test is separate. Actual dashboard playback/device interaction and live YouTube playback remain separate checks. |
| 16 Nov 2026, media and named-routine bundle | **343 offline tests and all twelve browser checks passed** | Full isolated suite passed in 1.602 seconds: prior 284 plus 19 media, 20 routine and 20 ability integration/grammar tests. All earlier ten browser scripts were rerun, plus [abilities controls](tests/ui_abilities_smoke.py) and [abilities workflow](tests/ui_abilities_workflow_smoke.py). Checks cover strict media fields before OS dispatch, valid frozen routine updates, replay/stale rejection, per-step failures/unrun steps, and readable results persisted across reload. Native effects were mocked; no real volume mutation, media key, player reaction or routine app launch was exercised. |
| 16 Nov 2026, post-ability server readiness | **Latest server restarted and read-only endpoints verified** | The existing listener was verified as the project SARA Python entry point before restart. Updated health reports Ollama/`llama3.2` ready; `/api/audio/status` reports available, 40%/unmuted; `/api/routines` has zero records and no personal defaults were inserted; access mode remains `trusted`. This proves current readiness and read-only state, not successful native changes. |

## Completed milestone and remaining work in priority order

- [x] **Completed — Live HUD redesign.** Procedural animated core replaces portrait/video presentation, all main views use the new skin, desktop/mobile visuals were inspected, and the six browser checks pass. The HUD represents app state; it does not imply extra computer access or fabricated CPU/network measurements.
- [x] **Implemented — Trusted routine access and YouTube play route.** Persisted scoped grant, direct routine execution, Stop/revocation guards and truthful player evidence; consequential workflows retain review.
- [x] **Implemented — Visual chat and explicit screen/camera controls.** Image paste/upload/drop, previews/removal and user-sent snapshots with local-only model detection and no image persistence.
- [x] **Implemented — Start conversation and native Windows speech.** Speech/mic activation, local greeting, installed OneCore voice path, fallback/retry diagnostics and optional local check-ins.
- [x] **Verified — Local vision model readiness and basic generated-image answers.** Installed `gemma3:4b` responds locally; documented slow responses, one shape error and incomplete Hindi instruction following remain real limits.
- [x] **Implemented and fixture-verified — Optional visual check-ins.** Separate consent, active-share snapshots, no queued-upload sampling, bounded background reasoning and stale-response cancellation are covered by tests.
- [x] **Implemented and fixture-verified — Windows audio/media and named saved routines.** CoreAudio adapters, fixed media keys, routine builder, deterministic commands and exact frozen-step execution are connected; 343 offline tests and twelve browser checks pass. Native effect acceptance remains separate.
- [ ] **P0 — Accept the new audio/routine tools on Windows.** In a chosen disposable workflow, verify requested volume/mute against readback and inspect each real routine outcome. Transport-key dispatch alone is not proof that a particular player paused or advanced.
- [ ] **P0 — Verify physical visual-input flows.** Test actual screen/camera permissions, Stop and snapshot behavior in the running app without retaining private image bytes.
- [ ] **P0 — Verify dashboard Windows speech.** Use the updated running app; select Kalpana and chosen speed; listen to Hindi, Roman-Hindi, mixed English terms and a custom pronunciation before/after reload; observe motion start/end against actual sound. Standalone Windows playback and WAV generation already passed; record dashboard-specific failures precisely.
- [ ] **P0 — Improve measured vision responsiveness and language reliability.** Generated-image requests took about 33–60 seconds; compare smaller/accelerated models and bounded prompts against repeatable Hindi/English visual cases. Check foreground chat responsiveness while a visual check-in is running; the separate background path still shares machine resources.
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
.\.venv\Scripts\python.exe tests\ui_proactive_smoke.py
.\.venv\Scripts\python.exe tests\ui_abilities_smoke.py
.\.venv\Scripts\python.exe tests\ui_abilities_workflow_smoke.py
```

The browser fixture intercepts approved dashboard assets/API mocks and needs no repository-wide HTTP server. The HUD assets are included in its allowlist. Run meaningful checks for the changed behaviour; record the exact result and its limits.

## Recent work and next-chat handoff

- Stabilized voice preparation and saved voice restoration; added isolated tests and browser fixtures.
- Aligned approved-memory context/list/count/delete semantics; added stale-review protection and data recovery backups.
- Added shared natural-time parsing, session-scoped scheduling clarification and planner API validation.
- Delivered the new user direction: live procedural Jarvis HUD with state-driven motion, plus this status/specification file and read-first [AGENTS.md](AGENTS.md) instructions.
- Added persisted trusted routines/YouTube playback, visual chat with explicit screen/camera controls, native WinRT voice playback, Start conversation activation and optional proactive local check-ins.
- Added Windows audio/media controls and named saved workflows. Try `volume 30 percent karo`, `next song`, `volume status`, `create routine work mode: open notepad; volume 30 percent karo`, `run routine work mode`, or `meri routines`. Review routine storage changes; preserve exact version/step checks and per-step failure evidence.
- Current next priorities: accept native volume/media and a disposable saved routine, verify dashboard voice timing, physical screen/camera permissions, actual YouTube playback, scheduling review and scoped workflows; improve visual latency and Hindi instruction following. Current checks are 343 offline tests/twelve browser scripts plus real generated-image model responses and read-only readiness endpoints. The user has already confirmed audible Kalpana output from the standalone Windows test. Preserve existing routines rather than seeding personal defaults. Do not equate full-system access with unrestricted shell/admin control or continuous hidden monitoring.
- The worktree already contains substantial staged/uncommitted development. Inspect `git status` and preserve existing work; do not reset, unstage or overwrite it casually.

For a new chat, open the actual SARA project folder so [AGENTS.md](AGENTS.md) is available. A chat opened elsewhere will not necessarily discover this repository automatically; attach this file or paste its path. Suggested prompt:

> Read `D:\SARA\AGENTS.md`, then `SARA_PROJECT_STATUS.md`, `SARA_PROJECT_CONTEXT.md` and `SARA_SETUP_GUIDE.md`. Inspect current files and git status. Continue the highest-priority unfinished SARA requirement, preserve existing work, run appropriate isolated verification, and update the status ledger with implementation evidence and remaining limits. The target is a personalized Jarvis-style local Windows assistant with natural Hindi/Hinglish speech and a live procedural HUD, not a finished claim based only on mock tests.

After every meaningful development pass, update the relevant feature row, verification record, remaining checklist and this handoff. Keep secrets, actual personal memories, message contents and private logs out of these documents.

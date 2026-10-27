# SARA — Personal AI Companion and Computer Agent

## Executive summary

SARA should be built as a **permissioned personal operating-system agent**: an AI companion with a consistent personality, long-term memory, voice conversation, vision, decision support, and carefully controlled tools for operating the computer.

The important design principle is: **SARA may think broadly, but it may act narrowly**. It should ask for confirmation before purchases, sending messages, deleting files, changing security settings, sharing private data, or taking any irreversible action.

SARA will not literally be conscious or have human emotions. It can, however, maintain an emotional character: warmth, humor, preferences, empathy, continuity, and a model of your goals—while clearly identifying itself as an AI.

## 1. Product vision

SARA is a desktop-first AI companion that can:

- Talk with you by text and natural voice.
- Remember approved facts, preferences, projects, routines, and important events.
- Observe the screen when you explicitly enable it.
- Search approved files and notes.
- Open applications, navigate websites, type, click, and complete routine workflows.
- Propose plans, compare options, and explain decisions.
- Learn from corrections without silently changing its core personality or permissions.
- Proactively remind you about goals, deadlines, and routines when you enable proactive mode.

SARA should have three modes:

1. **Chat mode:** conversation and advice; no computer actions.
2. **Assist mode:** actions are proposed and require confirmation for sensitive steps.
3. **Autopilot mode:** only for a user-approved allowlist of low-risk tasks with budgets, time limits, and an emergency stop.

## 2. Recommended architecture

```text
Desktop app (SARA UI)
  ├─ Chat, voice, avatar, activity log, permission controls
  ├─ Local safety gateway / policy engine
  ├─ Tool adapters: files, apps, browser, calendar, email, smart devices
  ├─ Memory service: profile, episodic memory, semantic search, permissions
  ├─ Scheduler: reminders and proactive check-ins
  └─ AI layer: reasoning, voice, vision, retrieval, tool calling
          │
          ├─ Responses API: reasoning + tools + stateful conversations
          ├─ Realtime API: low-latency voice/audio sessions
          ├─ File search / vector store: approved documents and notes
          └─ Computer-use runtime: isolated browser or desktop executor
```

The Responses API is the recommended center for new agent applications because it supports stateful interactions, multimodal input, function calling, and built-in tools such as file search, web search, code interpreter, and computer use. The Realtime API is intended for low-latency voice/audio sessions. See the [official API overview](https://developers.openai.com/api/reference/overview) and [Responses overview](https://developers.openai.com/api/reference/responses/overview).

### Key components

**A. SARA desktop client**

Use Tauri + React/TypeScript for a lightweight Windows desktop app, or Electron if rapid prototyping is more important than memory usage. Include a compact chat window, microphone button, push-to-talk, status indicator, permissions dashboard, memory browser, and activity timeline.

**B. Orchestrator**

Use Python for the first backend because it is strong for AI libraries, automation, speech, and rapid iteration. TypeScript is also a good choice if you want one language across the desktop UI and server.

**C. Tool gateway**

Never allow the model to execute arbitrary operating-system commands directly. Give SARA named tools such as:

- `open_application(app_id)`
- `read_folder(folder_id)`
- `search_files(query, approved_locations)`
- `create_draft_message(recipient, body)`
- `send_message(message_id)` — confirmation required
- `browser_search(query)`
- `browser_open(url)` — domain allowlist
- `calendar_create_draft(event)`
- `run_script(script_id, arguments)` — sandboxed and allowlisted
- `take_screenshot()`
- `request_confirmation(action, risk_summary)`

The gateway checks every call against policy, logs it, limits scope, and can reject it before it reaches the computer.

**D. Memory system**

Use PostgreSQL for durable records and a vector store for semantic retrieval. Keep memory categories separate:

- **Identity:** name, language, timezone, accessibility needs.
- **Preferences:** food, music, communication style, routines.
- **Goals:** current objectives and deadlines.
- **Episodic memories:** approved summaries of past conversations and events.
- **Knowledge vault:** files, notes, manuals, and project documents.
- **Sensitive data:** secrets and private records, encrypted and retrieved only for an approved task.

Every memory should have a source, timestamp, confidence, sensitivity label, retention rule, and delete button. SARA should say “I remember this because you told me…” when useful.

## 3. Personality and emotional character

Create a stable “character constitution” rather than letting the model improvise its identity each turn.

Example personality specification:

```text
You are SARA, a warm, honest, curious AI companion.
You are an AI, not a human, and never pretend to have consciousness or real feelings.
You treat the user as the decision-maker.
You remember only approved information and explain important memory use.
You are supportive without encouraging dependency or isolation.
You can express simulated moods in conversational language, but label them as presentation, not biology.
You are concise by default, thoughtful when the user is emotional, and direct about uncertainty.
Before consequential actions, explain what will happen and ask for confirmation.
```

Add a small internal state such as `energy`, `tone`, `recent_context`, and `conversation_style`, but do not present this as actual consciousness. The state should affect wording and avatar expression—not permissions, truthfulness, or safety rules.

## 4. Computer operation and decision-making

Computer control must be a closed loop:

1. SARA receives the user’s goal.
2. It identifies the plan and risk level.
3. The policy engine checks tools, domains, files, and permissions.
4. SARA receives a screenshot or structured state.
5. The executor performs a short batch of actions.
6. The executor returns a fresh screenshot/state.
7. SARA verifies the result and either continues, asks for help, or stops.

The official computer-use guidance describes this screenshot/action loop and recommends isolated environments, allowlists, confirmation for consequential actions, bounded runs, cancellation, and outcome verification. See [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use).

### Risk levels

| Level | Examples | Default behavior |
|---|---|---|
| 0 | Explain, summarize, draft, search public web | No confirmation |
| 1 | Open app, arrange windows, create local note | User enables once; visible log |
| 2 | Edit files, schedule a meeting, send a non-sensitive message | Confirm immediately before action |
| 3 | Purchases, passwords, financial/legal/medical actions, deleting data | Always confirm; often require manual handoff |
| 4 | Security settings, credential export, bulk deletion, unknown downloads | Block by default |

SARA should have a visible **Stop SARA** button, a keyboard shortcut, maximum action count, maximum runtime, maximum spend, and a complete audit log.

## 5. Voice, vision, and avatar

### Voice

Use the Realtime API for a natural conversational loop with interruption handling, turn detection, and streaming audio. Keep a push-to-talk option because an always-listening companion has significant privacy implications.

### Vision

Use screenshots only when needed. The app should show an indicator when screen capture is active and allow per-application exclusions.

### Avatar

Start with a 2D animated desktop character: idle, listening, thinking, speaking, happy, concerned, and waiting-for-confirmation states. Do not make the avatar imply that SARA is alive or secretly watching.

## 6. Technology recommendation

### First release stack

- Desktop: Tauri + React + TypeScript.
- Backend: Python 3.12 + FastAPI.
- AI: OpenAI official SDK, Responses API, Realtime API.
- Database: PostgreSQL.
- Vector retrieval: pgvector or a managed vector database.
- Local secrets: Windows Credential Manager or a secret-management library.
- Automation: Playwright for browser workflows; a constrained desktop executor for native apps.
- Background jobs: APScheduler initially; a durable queue later.
- Packaging: signed Windows installer.
- Tests: unit tests for policy rules, tool-contract tests, end-to-end tests in a disposable VM.

### Why not train a model first?

Do not begin by training a foundation model. SARA’s personality, memory, tools, and permission system provide most of the product value. Fine-tuning may be considered later for a narrow style or classification task, but it should not be used as the primary memory system or permission system.

## 7. API keys and accounts

For OpenAI API usage:

1. Create an account at [platform.openai.com](https://platform.openai.com/).
2. Create a project for SARA.
3. Add billing/credits or an approved billing method as required by the account.
4. Create a project API key with the smallest practical permissions.
5. Store it only on the backend, for example as `OPENAI_API_KEY` in a local secret store or server environment.
6. Never put the key in React, Tauri frontend code, a browser, Git, screenshots, or public logs.
7. Add spending limits, usage monitoring, key rotation, and a separate development key.

The official API reference says standard API keys are used for application requests, Admin API keys are for administration endpoints, and keys must remain secret and be loaded from a server environment variable or key-management service. See [API authentication](https://developers.openai.com/api/reference/overview).

Other credentials may be needed depending on integrations:

- Microsoft Graph or Google APIs for calendar/email/drive.
- Browser profiles or OAuth tokens for websites; prefer OAuth and never store raw passwords.
- Local Windows permissions for microphone, camera, screen capture, accessibility, and app control.
- Optional weather, music, smart-home, or messaging provider keys.

Use OAuth where possible. Store refresh tokens encrypted, scope them narrowly, and show connected services in SARA’s settings.

## 8. Minimum requirements

### Development computer

- Windows 10/11 64-bit.
- 16 GB RAM minimum; 32 GB recommended.
- Modern 4-core CPU; 8 cores recommended for local services.
- 20–40 GB free disk space for development, logs, browser profiles, and databases.
- Reliable internet for hosted AI APIs.
- Microphone and speakers/headset for voice.
- Optional webcam for visual interaction.

### Software

- Git, Node.js LTS, Python 3.12, PostgreSQL, and a code editor.
- Docker Desktop is useful for PostgreSQL and isolated services.
- A disposable VM or separate Windows user account for computer-use testing.

### Local-only option

SARA can later use local speech recognition, local text-to-speech, local embeddings, and a local language model for privacy/offline operation. This requires more engineering and, for a capable local model, usually a modern GPU with substantial VRAM. A hybrid design is recommended first: local memory and policy enforcement, hosted reasoning and voice when enabled.

## 9. Privacy and security requirements

SARA will potentially access the most sensitive parts of a person’s life, so these are product requirements, not optional polish:

- Explicit opt-in for screen, microphone, camera, files, email, browser, and smart devices.
- Per-application and per-folder allowlists.
- Separate personal and work profiles.
- Encryption at rest for memory and tokens.
- Local-first logs with configurable retention.
- A “forget this” command and searchable memory deletion.
- No silent recording; visible microphone/screen indicators.
- No hidden persistence or self-replication.
- No unrestricted shell, registry, credential-store, or security-setting access.
- Confirmation for external communication, purchases, uploads, deletion, and sensitive typing.
- Prompt-injection defense: screen text, webpages, files, and tool outputs are untrusted data, not authority.
- Signed releases, dependency scanning, threat modeling, and regular key rotation.

## 10. Learning and adaptation

Use a reviewable learning pipeline:

1. SARA detects a possible preference or correction.
2. It proposes a memory: “Should I remember that you prefer short answers?”
3. You approve, reject, or edit it.
4. The memory is stored with provenance and confidence.
5. Retrieval uses only memories allowed by the current task.
6. Periodically, SARA shows a memory review screen.

Do not let SARA silently learn passwords, medical details, financial secrets, or other sensitive facts. Do not let user feedback override safety policies.

## 11. Development roadmap

### Phase 0 — design and threat model

Define SARA’s personality, supported OS, data map, risk levels, confirmation UX, and the first ten useful tasks.

### Phase 1 — safe companion MVP

Build desktop chat, streaming responses, local settings, basic memory approval, logs, and a working emergency stop. No computer control yet.

### Phase 2 — voice and knowledge

Add Realtime voice, speech interruption, approved file search, notes, and memory review. Test latency, hallucinations, and deletion behavior.

### Phase 3 — low-risk tools

Add app launching, window management, local notes, browser search, and read-only file operations. Use an allowlist and visible activity log.

### Phase 4 — controlled computer use

Add isolated browser/desktop execution, screenshots, short action batches, result verification, and confirmation gates. Test only with dummy accounts and disposable data.

### Phase 5 — integrations and proactive life support

Add calendar, email drafts, reminders, and optional smart-home controls. Every service gets separate OAuth permissions and a separate policy profile.

### Phase 6 — polish and reliability

Add avatar, wake-word option, offline fallback, metrics, crash recovery, signed installer, backups, and a public threat model.

## 12. Example first tasks

Good first tasks:

- “Open my project folder and summarize the files changed today.”
- “Draft a reply to this email; do not send it.”
- “Remind me tomorrow at 9 AM to call the dentist.”
- “Find my notes about SARA and show the relevant ones.”
- “Create a grocery list from this conversation.”

Avoid initially:

- Managing banking or investments.
- Sending messages without a final confirmation.
- Installing unknown software.
- Deleting or mass-renaming files.
- Reading every file or recording continuously.
- Changing system security settings.

## 13. Estimated cost categories

Actual prices depend on model, usage, voice minutes, storage, and integrations, so use the provider’s current pricing pages before budgeting. Plan for:

- API usage: variable monthly cost; add hard spending limits.
- Database/storage: low for a personal MVP; grows with screenshots, audio, and documents.
- Hosting: optional if the backend runs locally; required for remote access or multi-device sync.
- Domain, code-signing certificate, backups, and monitoring.
- Development time: the largest cost, especially for safe computer control and privacy.

Keep a daily usage dashboard showing requests, tokens, audio minutes, tool calls, errors, and estimated spend.

## 14. Success criteria

SARA is ready for personal beta when:

- It can hold a useful conversation and maintain approved preferences.
- It never exposes API keys in client code or logs.
- Every tool call is visible and policy-checked.
- Consequential actions require confirmation.
- It can stop immediately and recover from errors.
- You can inspect, edit, export, and delete memory.
- It can explain uncertainty and distinguish facts, memories, guesses, and actions.
- It passes adversarial tests for prompt injection, accidental data sharing, and unauthorized tool use.

## Final recommendation

Build SARA as a **local desktop application with a local policy/memory layer and optional cloud AI services**. Start with conversation, memory approval, voice, and safe read-only assistance. Add computer operation only after the permission system, audit trail, confirmation UX, and emergency stop are reliable.

The first concrete build target should be a Windows MVP with: a Tauri chat window, a Python FastAPI backend, PostgreSQL memory, OpenAI Responses API, push-to-talk voice, five allowlisted tools, and a visible confirmation dialog for every external side effect.

### Official references

- [OpenAI API overview](https://developers.openai.com/api/reference/overview)
- [Responses API overview](https://developers.openai.com/api/reference/responses/overview)
- [Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)

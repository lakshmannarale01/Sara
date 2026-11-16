# SARA free/local feature roadmap

Source: the user's supplied J.A.R.V.I.S. specification, 16 November 2026.
The excerpt contains category counts, not 543 individually specified features.
Counts are not completion criteria; each implemented workflow needs evidence.

## Available after this pass

- Local Ollama conversation, Hindi/Hinglish speech preparation, installed Windows TTS, existing optional OpenAI integration. No paid provider added or enabled by this pass.
- Named chats: create, resume, auto-title, rename, text export, confirmed deletion. Independent model history per chat; approved preferences remain shared. Up to 100 chats and 200 retained turns per chat. Old records can be explicitly reset with `reset_sara_chats.py --confirm-delete` while the server is stopped.
- Live procedural dashboard, five themes, daily/idle rotation, speaking/listening/thinking states and a cartoon companion. Canvas rather than Three.js; state is driven by actual app events.
- Tasks, events, reminders, due-date form, priority/category fields, reviewed creation/completion/deletion, calendar export. `high priority task study physics` and `add to shopping list milk bread eggs` are deterministic commands. Natural reminder dates use existing scheduling. Natural task deadline extraction such as `by Friday` remains pending; use the task due-date picker.
- Focus/break timer with adjustable durations, pause/resume/reset, completed-session counter, and deadline restoration after reload. It does not block other apps; completion is shown when the dashboard is open/reopened. No background desktop notification is claimed.
- Local flashcard deck (question :: answer), flip/review, self-assessed round score, persistence and deletion; study assistant shortcut asks the configured model to quiz one question at a time. Fact checking or exam grading is not guaranteed.
- Existing scoped apps, searches, notes, workspace files, media controls, saved routines, explicit visual sharing and local vision model support.

## Remaining work with no paid dependency intended

1. Full context-aware workflows across apps, grounded page reading/extraction and recoverable multi-step execution. Current search context is limited; old text is never executed as a command.
2. Better pronunciation acceptance checks with the user's installed voice; optional offline recognition/Whisper requires model download and hardware evaluation.
3. Read-only CPU/RAM/battery/network monitoring with honest unavailable states; no fabricated live stats.
4. Task due-date natural language, sorting/filtering, subtasks, recurring tasks, time tracking, habit tracking and accessible reminders.
5. Persistent study collections, imported notes, generated flashcards with provenance, quizzes and spaced repetition.
6. Local provider/model selection and capacity diagnostics. Groq/Google free-tier availability and current terms must be checked before integration; user-owned credentials and explicit cloud choice are required. Free tiers are not unlimited local execution.
7. Further file workflows, backup/export, search and secure data lifecycle, plus integration-specific permissions.

## Requires additional resources or a concrete specification

External account sync, mail/SMS, smart-home devices, AR/VR, gestures and the unspecified remainder of the 543-feature list require account/device details or defined workflows. Do not mark these implemented from a category count. No claim that the assistant can perform every task.

## Storage

Named transcripts: `sara_data/chats.json` (atomic local JSON). Older unnamed transcript file: `sara_data/conversations.json`. Activity and server output can contain conversation text; resetting chats also clears those transcript logs. Individual chat deletion removes the stored conversation, not exported copies or previously written diagnostic logs. Focus timer, appearance and flashcards live in browser localStorage, not the Python chat store. Approved memories, tasks, notes and reminders remain separate.

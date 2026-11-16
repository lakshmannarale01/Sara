# SARA

A personalized, local-first Windows assistant with Hindi/Hinglish conversation, approved memory, a live animated Jarvis-style HUD and scoped, reviewable computer workflows.

**Start with [SARA_PROJECT_STATUS.md](SARA_PROJECT_STATUS.md).** It records what we are building, what is implemented and verified, what remains unfinished, and how to continue in a new chat. Coding agents should read [AGENTS.md](AGENTS.md) first.

## Run

```powershell
cd "D:\SARA"
.\start_sara.bat
```

The app normally opens in its own Edge window at `http://127.0.0.1:8765`. Follow [SARA_SETUP_GUIDE.md](SARA_SETUP_GUIDE.md) for first-time dependencies, Ollama/model setup, voice settings and verification commands.

Settings now includes **Audio & saved routines**. Try `volume 30 percent karo`, `next song`, or `volume status`. Create a workflow with `create routine work mode: open notepad; volume 30 percent karo`, review its steps, then say `run routine work mode`. Routines stay local and obey Stop, trust and exact saved-version checks.

## Continue development

Open the actual SARA repository in the new chat, or attach/provide the path to [SARA_PROJECT_STATUS.md](SARA_PROJECT_STATUS.md). A chat started elsewhere may not discover the project files automatically. The ledger includes a ready-to-paste handoff prompt.

- [Project target, progress and remaining work](SARA_PROJECT_STATUS.md)
- [Architecture and technical decisions](SARA_PROJECT_CONTEXT.md)
- [Commands and current capabilities](SARA_CAPABILITIES.md)
- [Access and action rules](SARA_ACCESS_REQUIREMENTS.md)

## Verification

```powershell
.\.venv\Scripts\python.exe tests\run_offline.py
```

On 16 November 2026, **343 isolated offline tests and all twelve browser checks passed**, including Windows media controls and saved-workflow validation, review, execution and persisted per-step results. The latest server is running; read-only checks confirm local AI, trusted mode, Windows audio status and an empty routine list without personal defaults. Exact results and earlier baselines are recorded in [SARA_PROJECT_STATUS.md](SARA_PROJECT_STATUS.md). Live `gemma3:4b` recognized generated shapes with observed 33–60-second requests and accuracy/language-following limits.

The user confirmed hearing the standalone Microsoft Kalpana test. Actual dashboard audio timing, physical microphone/camera/screen flows and consequential app workflows remain separate acceptance checks. The HUD is drawn live with canvas.


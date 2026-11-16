# SARA

A personalized, local-first Windows assistant with Hindi/Hinglish conversation, approved memory, a live animated Jarvis-style HUD and scoped, reviewable computer workflows.

**Start with [SARA_PROJECT_STATUS.md](SARA_PROJECT_STATUS.md).** It records what we are building, what is implemented and verified, what remains unfinished, and how to continue in a new chat. Coding agents should read [AGENTS.md](AGENTS.md) first.

## Run

```powershell
cd "D:\SARA"
.\start_sara.bat
```

The app normally opens in its own Edge window at `http://127.0.0.1:8765`. Follow [SARA_SETUP_GUIDE.md](SARA_SETUP_GUIDE.md) for first-time dependencies, Ollama/model setup, voice settings and verification commands.

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

The latest recorded pass on 13 November 2026 has **210 isolated offline tests and six browser checks passing**. The HUD is procedural canvas motion, not a portrait picture or embedded video. Physical Kalpana pronunciation, speaker latency and live consequential workflows remain separate acceptance checks; see the ledger for the current limits.


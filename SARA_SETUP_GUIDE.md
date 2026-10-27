# SARA Setup, Requirements, and Flow

This file is the single setup reference for moving SARA to another Windows laptop.

## 1. What must be installed

| Requirement | Why it is needed | Required? |
|---|---|---|
| Windows 10/11 | SARA currently uses Windows voice, `msg.exe`, and desktop actions | Yes |
| Python 3.11+ | Backend server and local tools | Yes |
| Ollama | Local AI chat provider; no OpenAI API cost | Recommended |
| `llama3.2` Ollama model | Default SARA chat model | Recommended |
| Internet | First-time Python/Playwright downloads and weather/browser pages | Recommended |
| Chromium runtime | Semantic browser actions | Installed by setup flow |
| Microphone permission | Voice input | Only for voice |

## 2. First-time installation

Open PowerShell in the project folder:

```powershell
cd "D:\sara ai"
```

If Python is not installed, install Python 3.11 or newer and enable **Add Python to PATH**. Then create the project environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

The normal shortcut performs the dependency steps automatically:

```powershell
.\start_sara.bat
```

`start_sara.bat` creates `.venv`, installs `requirements.txt`, installs the Chromium runtime separately, and starts `sara_server.py`. The `.venv` folder is machine-specific and must not be copied between laptops.

## 3. Ollama setup

Install Ollama from its official Windows installer, then run:

```powershell
ollama run llama3.2
```

If Ollama reports that port `11434` is already in use, it is already running; do not start a second `ollama serve` process. Check it with:

```powershell
ollama list
```

SARA tries Ollama first, then optional OpenAI, then the local-safe fallback.

## 4. Optional OpenAI configuration

OpenAI is not required when Ollama works. If used, set the key only in the local environment; never commit it:

```powershell
$env:OPENAI_API_KEY = "your-key-for-this-terminal-only"
```

OpenAI API billing/credits are separate from ChatGPT or Codex usage.

## 5. Start and use SARA

```powershell
.\start_sara.bat
```

The server opens `http://127.0.0.1:8765` and prints visible `[SARA]` logs in the terminal. Use `Ctrl+C` to stop it. For voice, allow microphone access in the browser and activate SARA wake mode.

## 6. What is local and what must be re-authenticated

Copying the project preserves code and static assets. Do not copy `.venv` or secrets. The following are created per laptop:

- `.venv/`: Python dependencies
- Playwright Chromium runtime: installed in the user profile by `playwright install chromium`
- `sara_data/`: memories, reminders, and activity logs
- `sara_data/browser_profile/`: SARA's separate browser session and site logins

On a new laptop, log in again inside SARA's controlled Chromium profile for WhatsApp Web or other websites. Credentials and cookies are not stored in the repository.

## 7. Functional flow

1. `start_sara.bat` prepares `.venv` and dependencies.
2. `sara_server.py` starts the local HTTP server.
3. SARA loads the dashboard at port `8765`.
4. Ollama handles local chat when available.
5. Voice input uses browser microphone permission. For Hindi/Hinglish replies, local Ollama converts Roman Hindi into Devanagari for speech; if Ollama is temporarily unavailable, SARA uses an offline common-word transliteration fallback. The selected Windows/browser voice (such as Microsoft Kalpana) reads that speech text. Use the `Test voice` button and the diagnostics line beside it to verify Hindi voice availability. English technical terms remain in English.
6. Browser and desktop actions return a confirmation request before execution.
7. Chat questions and answers print in the terminal as `Boss:` and `SARA:` lines and are written to `sara_data/activity.jsonl`; saved turns appear in the chat panel after reload and in Recent activity. Ask `Sara ka system status batao` for a read-only readiness summary. Tasks persist in `sara_data/tasks.json` and can be added, completed, or deleted with confirmation, then used for a daily plan. Local events persist in `sara_data/events.json`; try `schedule team sync tomorrow at 5 pm` and confirm, then use `calendar dikhao` to list them.
8. SARA can prepare a reviewable email draft with `draft email to name@example.com subject: Update body: ...`; it opens the default mail app only after confirmation and never presses Send automatically.
9. SARA can help edit safe project text files after confirmation, for example `write file demo.py: print("Hello")`. Secrets, runtime data, and traversal paths are blocked.
10. Approved learning is reviewable: use `learn that ...`, `memories dikhao`, and `forget memory N`. SARA never silently promotes ordinary chat into long-term memory.
11. `What’s next?`, `briefing`, or `aaj ka plan` gives a unified local view of tasks, reminders, and planned events. `export calendar` downloads an importable `.ics` file. Use `reminders dikhao` and `delete reminder N` to manage reminders.
12. Reminders are watched while the server is running.

## 8. Important commands

```powershell
# Start SARA
.\start_sara.bat

# Direct server start
.\.venv\Scripts\python.exe sara_server.py

# Run tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Check Python syntax
$files = @("sara_server.py") + (Get-ChildItem sara_app -Filter *.py | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $files

# Check Ollama model
ollama list
```

## 9. Troubleshooting

- `package.json` missing: this is a Python project; do not run `npm install` from the project root.
- `Python was not found`: install Python 3.11+ or use the existing `.venv` command above.
- `Ollama bind 127.0.0.1:11434`: Ollama is already running; use `ollama run llama3.2`.
- Browser actions fail: run `.\.venv\Scripts\python.exe -m playwright install chromium` and log in again in SARA's profile.
- Typing goes to the wrong window: wait for the app-open action to finish, keep the intended window focused, then confirm the typing action. SARA now waits briefly after launching an allowlisted app.
- Voice does not work: allow microphone permission and reload the dashboard.
- SARA does not speak: check the browser's Windows voice output and terminal logs.
- Hindi/Hinglish is spelled out: keep Ollama running, restart SARA, hard-refresh the page, and select a Hindi voice such as Microsoft Kalpana. SARA uses the local Ollama model to transliterate Hindi words into Devanagari before speech; if Ollama is unavailable, it falls back to the original reply text.

For permission scope and risk rules, see [SARA_ACCESS_REQUIREMENTS.md](SARA_ACCESS_REQUIREMENTS.md).

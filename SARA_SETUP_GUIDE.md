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
cd "D:\SARA"
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

The server opens SARA in a standalone Microsoft Edge app window by default (`--app` mode, with no normal tabs or address bar) and prints visible `[SARA]` logs in the terminal. This keeps the local dashboard away from your normal Chrome profile and makes it feel like a desktop app. Use `Ctrl+C` to stop it. Set `$env:SARA_UI_MODE = "browser"` for a normal browser window, `$env:SARA_UI_BROWSER = "chrome"` if you explicitly want Chrome app mode, or `$env:SARA_UI_BROWSER = "none"` to open the printed URL yourself. For voice, allow microphone access in the browser. Wake mode is enabled by default and stays enabled across dashboard reloads; on browsers that require a gesture, click the dashboard once after loading to grant microphone access. You can turn it off from Settings → Listen for “SARA”.

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
5. Voice input uses browser microphone permission and spoken replies are enabled by default. SARA chooses female-sounding system voices when available and defaults to 1.15× speed. System playback keeps a mixed Hindi/English sentence together rather than switching voices on each English word. Adjacent same-voice sentences merge into short passages; common technical terms use Hindi phonetics during Hindi playback. A local pronunciation lexicon prepares speech without another AI call; known acronyms expand and display Markdown/code blocks are cleaned. Unfamiliar names and Roman Hindi spellings still depend on the available voices and lexicon. In Settings, `Natural AI voice` is optional: it needs `OPENAI_API_KEY`, Internet and API credits. Use `Test voice` to hear the selected mode.
6. Browser and desktop actions return a confirmation request before execution.
7. Chat questions and answers print in the terminal as `Boss:` and `SARA:` lines and are written to `sara_data/activity.jsonl`; saved turns appear in the chat panel after reload and in Recent activity. Ask `Sara ka system status batao` for a read-only readiness summary. Tasks persist in `sara_data/tasks.json` and can be added, completed, or deleted with confirmation, then used for a daily plan. Local events persist in `sara_data/events.json`; try `schedule team sync tomorrow at 5 pm` and confirm, then use `calendar dikhao` to list them.
8. SARA can prepare a reviewable email draft with `draft email to name@example.com subject: Update body: ...`; it opens the default mail app only after confirmation and never presses Send automatically.
9. SARA can help edit safe project text files after confirmation, for example `write file demo.py: print("Hello")`. Secrets, runtime data, and traversal paths are blocked.
10. Approved learning is reviewable: use `learn that ...`, `memories dikhao`, and `forget memory N`. Corrections such as `Don't call me Boss, call me Lakshman` or `mujhe Hindi mein jawab do` prompt SARA to ask before saving a durable preference. SARA never silently promotes ordinary chat into long-term memory.
11. `What’s next?`, `briefing`, or `aaj ka plan` gives a unified local view of tasks, reminders, and planned events. `export calendar` downloads an importable `.ics` file. Use `reminders dikhao` and `delete reminder N` to manage reminders.
12. Reminders are watched while the server is running. To check them while SARA is closed, run `powershell -ExecutionPolicy Bypass -File .\install_sara_reminders.ps1` from the project folder. It registers the optional `SARA Reminders` task for the current user, once per minute while signed in. Remove it with `powershell -ExecutionPolicy Bypass -File .\uninstall_sara_reminders.ps1`; saved reminders remain intact. Notifications use a Windows message to the signed-in user. The dashboard shows action risks and offers **Stop SARA actions**; stopped state blocks backend write/computer actions until resumed and resets when the server process restarts.
13. For a missing Jarvis-style capability, ask `kya aap Google calendar sync bana doge?` or describe the exact feature. SARA will show its current status, required access, and implementation steps before any build or external integration is started.
14. `Notepad mein "Hello world" likho` prepares one combined save-and-open action. Review shows the exact note content. Approval saves a unique UTF-8 file in `sara_data/notes`, reads it back, and passes that exact path to Notepad. It does not type into whichever application happens to have focus. The tool reports file verification and launch request separately; it does not claim window visibility was verified.
15. `Open karo`, `haan karo`, or `yes` resolves the current proposal in this dashboard session and opens its existing review. It never goes to the language model as proof of execution. Approve runs the exact reviewed payload once; modified, cancelled, expired or superseded proposals are rejected. Pending proposals expire after five minutes and reset when the server restarts. A completed/failed action is shown in chat as a tool result, including a saved-note preview if available.
16. `Notepad mein mere baare mein jo jaante ho likho` drafts only explicitly approved saved memories. With no approved personal facts, SARA says so instead of inventing a biography. Earlier AI chat claims such as "I opened Notepad" are not treated as tool evidence.
17. If the selected voice mispronounces a word or name, add a local rule under Settings → Pronunciation guide or say `pronounce Kalpana as कल्पना` and approve it. The rule changes speech output only and can be removed from Settings.
18. Add a Windows app under Settings → App shortcuts with a display name and the full path to its `.exe` (for example, `C:\Program Files\Example\Example.exe`). SARA stores this allowlist locally, offers the shortcut by name in chat (for example, `open Example`), and asks before every launch. It does not run command arguments or shell commands.
19. If SARA says a capability is missing, it can explain the access and implementation outline, then offer to save your request. Approve it to keep the request under Settings → Feature requests; this tracks the idea locally but does not change or install SARA code by itself.
20. To find project guidance, ask `search project files for Kalpana` or `project files mein reminder dhoondo`. SARA searches bounded local text files and returns matching file names and lines. Runtime folders, `.env*`, and common key/credential files are excluded.
21. Ask `SARA, what can you do?` or `capabilities dikhao` to see a live summary of available, limited, and planned features. Ask about a specific missing feature to see its access needs and implementation outline.

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
- Notepad was claimed open but nothing happened: use a new request after restarting the updated server. Pending action follow-ups now reopen the exact review; click `Approve action` to execute. Look for the separate tool-result message. If saving succeeds but launch fails, `Read saved note` remains available and the outcome says launch failed. Generic AI replies are not execution proof.
- Voice does not work: allow microphone permission and reload the dashboard.
- Mic needs repeated clicks: click it once to start hands-free conversation. SARA pauses capture while replying and resumes automatically afterwards; direct follow-ups are accepted for 60 seconds **after playback finishes**. After that, say `Sara` again; the microphone stays armed. Temporary recognition/network errors retry automatically with a short backoff. Clicking the active mic explicitly stops hands-free mode; permission/device/language errors still need their indicated correction. Returning to the tab resumes an enabled session.
- Voice pauses between words: system speech now uses sentence/phrase playback units, avoiding tiny language-switch utterances. A reply can still pause naturally at sentence or long-passage boundaries. The speech watchdog restores listening if the engine becomes idle without sending its completion event; it does not cut off speech based on a guessed text duration.
- SARA does not speak or sounds robotic: open Settings, keep `Speak replies aloud` enabled, choose `Female system voice`, and click `Test voice`. SARA auto-picks a likely female voice, but the exact voice depends on Windows/Edge; diagnostics now show the language/voice and speed queued for each reply, including a warning when no Hindi voice is available. Select another installed voice if needed. `Natural AI voice` is available only with `OPENAI_API_KEY` and uses API credits. The voice speed slider defaults to 1.15×; old manually saved speeds remain unchanged. Browser audio can require one click after page load.
- Colorful terminal logs do not need a plugin. SARA now labels startup, API requests, Boss messages, SARA replies, actions, speech/TTS and errors with ANSI colors. Set `$env:SARA_COLOR = "0"` before `start_sara.bat` if you want plain text logs.
- Hindi/Hinglish is spelled out: keep both Hindi and English Windows voices installed (for example Kalpana and Heera). Pure English passages use an English voice; mixed Hindi sentences use one Hindi voice with common technical pronunciation entries. Unknown names/spellings may still need a pronunciation entry or a more capable multilingual voice. `SARA` is spoken as `Sara`, and Markdown/code blocks are excluded from normal narration.
- Thinking is slow: restart SARA and allow its background model warmup. Local chat now streams text as it arrives and no longer waits for dashboard refresh after a reply. The default model is CPU-bound on this laptop; long replies and uncached context still take time. Use `/api/performance` to inspect measured first-token/total latency, or run `.\.venv\Scripts\python.exe tests\benchmark_latency.py` for a 32-token local test without saving a conversation. This benchmark still uses the laptop's current recent context locally; only timing/counts are printed.

## 10. Current integration boundaries

- Google/Outlook sync needs a provider OAuth app and user sign-in; until configured, use local events and `export calendar`.
- Email opens a reviewable draft in the default mail handler. SARA does not send email directly.
- WhatsApp send uses the separate SARA Chromium profile and always requires an explicit confirmation.
- Reminder notifications are not a Windows background service yet. They are checked while SARA is running, so reminders may be delayed if the server is closed.
- Voice input/output and the animated character are browser features; wake mode requires the dashboard to remain open. It automatically re-arms after SARA replies, after short browser recognition timeouts, and when the tab becomes visible again. Browser microphone permission and its first user gesture are still required by browser privacy rules.
- The optional OpenAI speech endpoint currently uses `gpt-4o-mini-tts`. OpenAI's documentation lists it for shutdown on January 6, 2027; move that optional mode to the Realtime API before then.
- This remains a local web application, not a signed native desktop installer. Screen vision and realtime interruptible voice are future roadmap work.

For permission scope and risk rules, see [SARA_ACCESS_REQUIREMENTS.md](SARA_ACCESS_REQUIREMENTS.md).

## 11. Response speed settings

Restart the server after changing these PowerShell environment values.

| Setting | Default | Purpose |
|---|---|---|
| `SARA_KEEP_ALIVE` | `15m` | Keeps model weights resident between requests; uses RAM while loaded |
| `SARA_WARMUP` | `1` | Preloads the local model in the background; `0` disables |
| `SARA_MAX_TOKENS` | `192` | Routine AI reply limit |
| `SARA_DETAILED_TOKENS` | `512` | Limit when the user asks for detail/code |
| `SARA_HISTORY_CHARS` | `1600` | Bounded recent conversation context (up to four turns) |
| `SARA_CONTEXT_TOKENS` | `4096` | Ollama context window |
| `SARA_AI_TIMEOUT` | `40` | Local AI response budget in seconds |
| `SARA_CLOUD_TIMEOUT` | `25` | Optional cloud request timeout; automatic SDK retries disabled |

Speed changes implemented: compact capability/memory prompts, incremental text output, immediate local greetings, a short unavailable-provider cooldown, cached health probes, background dashboard refresh, bounded activity-log tail reads, pruned workspace scanning and browser page reuse. Action confirmations and app readiness waits remain enforced. Controlled browser work stays on one owner thread; shutdown cancels queued actions and waits for an already running action before closing its browser resources.

On November 4, 2026, a local 32-token test on the existing CPU-only `llama3.2` measured 30.49s total / 28.44s first text before optimization. With a compact new prompt and resident model it measured 12.28s / 10.48s; a further different prompt with a reusable prefix measured 2.29s / 0.38s. The initial run included 3.36s model load. These are small observed samples, not a promise for every question or external website.

Further options: benchmark a smaller local model for speed/quality tradeoffs, investigate supported GPU acceleration for Intel Arc, add sentence-by-sentence streamed audio, and add user-editable name pronunciations. No model download, global driver change or paid voice mode was automatically enabled.

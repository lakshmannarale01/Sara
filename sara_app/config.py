from pathlib import Path
import os
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "sara_data"
MEMORY_FILE = DATA_DIR / "memories.json"
PRONUNCIATION_FILE = DATA_DIR / "pronunciations.json"
APP_FILE = DATA_DIR / "apps.json"
CAPABILITY_REQUEST_FILE = DATA_DIR / "capability_requests.json"
REMINDER_FILE = DATA_DIR / "reminders.json"
LOG_FILE = DATA_DIR / "activity.jsonl"
CONVERSATION_FILE = DATA_DIR / "conversations.json"
TASK_FILE = DATA_DIR / "tasks.json"
EVENT_FILE = DATA_DIR / "events.json"
PORT = int(os.getenv("SARA_PORT", "8765"))
OLLAMA_URL = os.getenv("SARA_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("SARA_OLLAMA_MODEL", "llama3.2")
OPENAI_MODEL = os.getenv("SARA_MODEL", "gpt-5.1")

"""Measure local AI latency without saving a conversation or printing its text."""
import json
import argparse
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sara_app.ai import build_instructions, conversation_context
from sara_app.config import OLLAMA_MODEL, OLLAMA_URL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="Explain in one short sentence how you can help me today.")
    parser.add_argument("--tokens", type=int, default=32)
    args = parser.parse_args()
    instructions = build_instructions()
    context = conversation_context()
    payload = {"model": OLLAMA_MODEL, "system": instructions,
               "prompt": context + "\nuser: " + args.prompt,
               "stream": True, "keep_alive": "15m", "options": {"num_predict": min(512, max(1, args.tokens)), "num_ctx": 4096, "temperature": 0}}
    request = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    start = time.perf_counter(); first = None; final = {}
    with urllib.request.urlopen(request, timeout=55) as response:
        for line in response:
            item = json.loads(line)
            if item.get("response") and first is None:
                first = time.perf_counter() - start
            if item.get("done"):
                final = item
    duration = final.get("eval_duration", 0) / 1e9
    print(json.dumps({"instruction_chars": len(instructions), "history_chars": len(context),
                      "first_token_seconds": round(first, 3) if first is not None else None,
                      "total_seconds": round(time.perf_counter() - start, 3),
                      "prompt_tokens": final.get("prompt_eval_count"), "output_tokens": final.get("eval_count"),
                      "load_seconds": round(final.get("load_duration", 0) / 1e9, 3),
                      "tokens_per_second": round(final.get("eval_count", 0) / duration, 2) if duration else None}))


if __name__ == "__main__":
    main()

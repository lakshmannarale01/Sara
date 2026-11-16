"""Small, explicit command grammar for saved workflows and media controls.

Model prose is never parsed into executable steps. Unsupported routine steps
reject the complete draft before anything is saved or executed.
"""
import re
from urllib.parse import quote_plus

from .intents import action_payload, plan_youtube
from .system_controls import plan_media_control
from .routines import list_routines, normalize_name, normalize_steps, routine_action_for_name


def _name(value):
    return normalize_name(value.strip().strip('"“”'))


def _step(text):
    media = plan_media_control(text)
    if media:
        action = media["action"]
        return {"type": "media_control", **action_payload(action)}
    video = plan_youtube(text)
    if video:
        return {"type": "youtube_play", **action_payload(video["action"])}
    app = re.fullmatch(r"(?:open|launch|start|kholo|khol do|खोलो)\s+(notepad|calculator|chrome)|"
                       r"(notepad|calculator|chrome)\s+(?:open(?: karo)?|kholo|khol do|खोलो)", text, re.I)
    if app:
        return {"type": "open_app", "app": (app.group(1) or app.group(2)).lower()}
    search = re.fullmatch(r"(?:search(?:\s+web)?(?:\s+for)?|google(?:\s+par)?|web\s+par\s+search)\s+(.+)", text, re.I)
    if search:
        query = search.group(1).strip()
        if not query or len(query) > 500:
            raise ValueError("Search text must contain 1–500 characters.")
        return {"type": "open_browser_url", "url": "https://www.google.com/search?q=" + quote_plus(query)}
    url = re.fullmatch(r"(?:open|kholo|khol do|खोलो)\s+(https://\S+)", text, re.I)
    if url:
        return {"type": "open_browser_url", "url": url.group(1)}
    raise ValueError("Unsupported routine step: " + text[:100] + ". Use a built-in app, web search, supported HTTPS page, YouTube request or media control.")


def _run(name):
    action = routine_action_for_name(_name(name))
    return {"reply": f"'{action['name']}' routine के {len(action['steps'])} steps तैयार हैं। Current access mode के अनुसार चलाऊँगी और हर step का result बताऊँगी।",
            "provider": "routine-planner", "requires_confirmation": True, "action": action}


def plan_ability_command(message):
    text = re.sub(r"^sara\s*[:,]?\s+", "", str(message or "").strip(), flags=re.I)
    create = re.fullmatch(r"(?:create|save|make|banao|बनाओ)\s+(?:a\s+)?(?:routine|workflow)\s+(.+?)\s*:\s*(.+)", text, re.I | re.S)
    run = re.fullmatch(r"(?:run|start|execute|chalao|चलाओ)\s+(?:my\s+)?(?:routine|workflow)\s+(.+?)[.!।]*", text, re.I)
    listing = re.fullmatch(r"(?:list|show|dikhao|meri|मेरी)\s+(?:my\s+)?(?:routines?|workflows?)(?:\s+(?:dikhao|batao|दिखाओ))?[.!।]*|"
                          r"(?:routines?|workflows?)\s+(?:dikhao|batao|दिखाओ)[.!।]*", text, re.I)
    try:
        if create:
            name = _name(create.group(1))
            parts = [part.strip() for part in create.group(2).split(";")]
            if not 1 <= len(parts) <= 8 or any(not part for part in parts):
                raise ValueError("A routine needs 1–8 supported steps, separated by semicolons.")
            steps = normalize_steps([_step(part) for part in parts])
            return {"reply": f"'{name}' routine save करने की review तैयार है। Save करने से steps अभी execute नहीं होंगे।",
                    "provider": "routine-planner", "requires_confirmation": True,
                    "action": {"type": "save_routine", "name": name, "steps": steps, "label": "Save routine: " + name}}
        if run:
            return _run(run.group(1))
        if listing:
            routines = list_routines()
            reply = "Saved routines: " + "; ".join(f"{row['name']} ({len(row['steps'])} steps)" for row in routines) if routines else "अभी कोई routine save नहीं है। Settings → Audio & saved routines में बनाएँ, या कहें: create routine work mode: open notepad; volume 30 percent karo"
            return {"reply": reply, "provider": "routine-list", "routines": routines}
        short_run = re.fullmatch(r"(.+?)\s+(?:chalao|chala do|start karo|चलाओ)[.!।]*", text, re.I)
        if short_run:
            candidate = short_run.group(1).strip().strip('"“”').casefold()
            if any(row["name"].casefold() == candidate for row in list_routines()):
                return _run(short_run.group(1))
    except ValueError as exc:
        return {"reply": str(exc), "provider": "routine-planner", "clarification": {"kind": "routine"}}
    return plan_media_control(text)


def is_audio_status_question(message):
    text = str(message or "").lower()
    return bool(re.fullmatch(r"(?:sara\s*[:,]?\s*)?(?:what(?:'s| is)\s+(?:the\s+)?)?(?:current\s+)?(?:volume|speaker|audio)(?:\s+(?:status|level|kitna(?: hai)?|kya hai|कितना है|स्थिति))(?:\s+batao)?[?!.।]*", text))

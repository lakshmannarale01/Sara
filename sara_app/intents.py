"""Deterministic desktop intent handling; chat prose cannot execute actions."""
import re


def short_confirmation(message):
    value = re.sub(r"[.!?,।]+", " ", str(message).lower())
    value = re.sub(r"\s+", " ", value).strip()
    if value in {"no", "nahi", "nahin", "cancel", "cancel it", "mat karo", "nahi karo", "never mind", "rehne do"}:
        return "cancel"
    if value in {"yes", "haan", "han", "ha", "ok", "okay", "sure", "confirm", "approve", "go ahead", "do it", "kar do", "karo", "haan karo", "haan kar do", "yes do it", "open karo", "open kar do", "open it", "khol do", "kholo", "start karo", "send it", "delete it", "write it", "save it"}:
        return "review"
    return None


def is_action_status_question(message):
    text = str(message).lower()
    return bool(re.search(r"\b(?:(?:did you|have you|has it)\s+(?:(?:already|just)\s+)?(?:open|opened|write|written|type|typed|save|saved|send|sent|delete|deleted|click|clicked|finish|finished|do it|done)|is it done|action status|last action)\b|(?:khol|likh|kar) diya|ho gaya|hua kya", text))


def is_capability_overview_question(message):
    text = str(message or "").strip().lower()
    return bool(re.search(
        r"\bwhat can you do\b|\bwhat are your capabilities\b|\bwhat features can you\b|\btell me your capabilities\b|"
        r"\bcapabilities?\s+(?:dikhao|batao|show|list)\b|\bfeatures?\s+(?:dikhao|batao|show|list)\b|"
        r"(?:tum|aap|sara)\s+kya\s+kar\s+sakti|sara\s+ke\s+features",
        text,
    ))


def memory_request_text(message):
    """Extract an explicitly offered fact or correction for approved memory."""
    text = str(message or "").strip()
    if not text:
        return None

    correction = re.match(
        r"(?:please\s+)?(?:don't|do not|never)\s+call me\s+([^,;.]+?)"
        r"(?:[,;]\s*(?:please\s+)?call me\s+(.+?))?[.!]*$",
        text, re.I,
    )
    if correction:
        old_name = correction.group(1).strip().strip('"\'')
        new_name = (correction.group(2) or "").strip().strip('"\'')
        detail = f"Do not call the user {old_name}."
        return detail + (f" Preferred name: {new_name}." if new_name else "")

    hindi_correction = re.match(r"mujhe\s+(.+?)\s+mat\s+(?:bulao|bolo|kaho)[.!]*$", text, re.I)
    if hindi_correction:
        return f"Do not call the user {hindi_correction.group(1).strip()}."

    preferred_name = re.match(r"(?:please\s+)?(?:call me|my name is)\s+(.+?)[.!]*$", text, re.I)
    if preferred_name:
        return f"Preferred name: {preferred_name.group(1).strip().strip(chr(34) + chr(39))}."
    hindi_name = re.match(r"mujhe\s+(.+?)\s+(?:bulao|bulana|kaho)[.!]*$", text, re.I)
    if hindi_name:
        return f"Preferred name: {hindi_name.group(1).strip()}."

    language = re.match(r"mujh(?:e|se)\s+(hindi|hinglish|english)\s+(?:mein|me)\s+(?:jawab|baat)\s+(?:do|karo|karna|dena)[.!]*$", text, re.I)
    if language:
        return f"Preference: Reply to the user in {language.group(1).title()}."
    english_language = re.match(r"(?:please\s+)?(?:always\s+)?(?:reply|answer|respond|speak|talk)\s+(?:to me\s+)?in\s+(hindi|hinglish|english)[.!]*$", text, re.I)
    if english_language:
        return f"Preference: Reply to the user in {english_language.group(1).title()}."

    like = re.match(r"(?:i\s+)?(don't like|do not like|dislike|like|prefer)\s+(.+?)[.!]*$", text, re.I)
    if like:
        verb = {"don't like": "does not like", "do not like": "does not like", "dislike": "dislikes", "like": "likes", "prefer": "prefers"}[like.group(1).lower()]
        return f"Preference: The user {verb} {like.group(2).strip()}."
    hindi_like = re.match(r"mujhe\s+(.+?)\s+pasand\s+(nahi\s+hai|hai)[.!]*$", text, re.I)
    if hindi_like:
        sentiment = "likes" if hindi_like.group(2).casefold() == "hai" else "does not like"
        return f"Preference: The user {sentiment} {hindi_like.group(1).strip()}."

    explicit = re.match(r"(?:remember|learn that|yaad rakho|yaad rakhna|save this)\s*[:,-]?\s*(.+)$", text, re.I)
    if explicit:
        captured = explicit.group(1).strip()
        return memory_request_text(captured) or captured
    preference = re.match(r"(?:i prefer|i like|i don't like|i do not like|my name is|call me)\s*[:,-]?\s*(.+)$", text, re.I)
    if preference:
        return preference.group(0).strip()
    return None


def profile_note(memories):
    facts = [str(item.get("text", "")).strip() for item in memories if isinstance(item, dict) and item.get("approved") is True and str(item.get("text", "")).strip()]
    if not facts:
        return "ABOUT YOU — APPROVED SARA NOTES\n\nSARA ke paas abhi aapke baare mein koi approved personal detail saved nahi hai. Is note mein koi personal fact invent nahi kiya gaya hai.\n"
    return "ABOUT YOU — APPROVED SARA NOTES\n\n" + "\n".join("- " + fact for fact in facts) + "\n\nSource: details you explicitly approved for SARA memory.\n"


def _literal_content(message):
    quoted = re.search(r'["“](.+?)["”]|\x27(.+?)\x27', message, re.S)
    if quoted:
        return (quoted.group(1) or quoted.group(2)).strip()
    colon = re.search(r"(?:write|type|likho|likh do)\s*[:：]\s*(.+)$", message, re.I | re.S)
    if colon:
        return colon.group(1).strip()
    patterns = (
        r"(?:write|type)\s+(.+?)\s+(?:in|into|mein|me)\s+(?:the\s+)?notepad[.!]*$",
        r"notepad\s+(?:mein|me|in)\s+(.+?)\s+(?:likho|likh do|write|type)(?:\s+(?:please|karo))?[.!]*$",
        r"notepad\s+(?:mein|me|in)\s+(?:likho|write|type)\s+(.+)$",
        r"notepad\b.*?\b(?:write|type|likho)\s+(.+)$",
    )
    for pattern in patterns:
        found = re.search(pattern, message, re.I | re.S)
        if found:
            value = found.group(1).strip().rstrip(".")
            if not re.search(r"kuchh?|something|anything|mere liye|for me|related|about me|my (?:profile|details|information)|you know|jo bhi|jo bhee|sab kuch", value, re.I):
                return value
    return None


def plan_notepad(message, memories):
    text = str(message).strip()
    lower = text.lower()
    if not re.search(r"\bnote\s*pad\b", lower):
        return None
    if re.search(r"\bhow (?:to|do|does|can)|\bwhat is\b|\bexplain\b|kaise.*notepad|notepad.*kaise", lower):
        return None
    writing = bool(re.search(r"\b(?:write|writing|type|likho|likh|likhna|likhdo)\b", lower))
    opening = bool(re.search(r"\b(?:open|khol|kholo|launch|start|dikhao|dikhaao)\b", lower))
    if writing:
        about_user = bool(re.search(r"about me|about myself|mere (?:baare|bare|related)|meri.*(?:jankari|information|details)|my (?:profile|details|information)|mera (?:profile|introduction)|jo.*(?:jaante|jante|know)", lower))
        literal = _literal_content(text)
        content = literal or (profile_note(memories) if about_user else "SARA NOTES\n\nHi! Main Sara, aapki AI assistant.\nAaj ka ek chhota goal choose karein aur uska pehla step yahan likhein.\n")
        if len(content) > 6000:
            return {"reply": "Approved details 6000 characters se zyada hain. Batayein kaunsi details Notepad note mein include karni hain; abhi koi file nahi bani.", "provider": "notepad-planner"}
        source = "Sirf aapki approved saved details se draft banaya hai." if about_user and not literal else "Exact note text review mein dikh raha hai."
        return {"reply": source + " Approve karne par nayi text file save karke Notepad mein open karne ka request bhejungi. Abhi action execute nahi hua.",
                "provider": "notepad-planner", "requires_confirmation": True,
                "action": {"type": "notepad_write", "text": content, "label": "Save this exact note and open it in Notepad"}}
    if opening:
        return {"reply": "Notepad open karne ka action ready hai. Review karke Approve karein; abhi launch nahi hua.", "provider": "action-planner", "requires_confirmation": True,
                "action": {"type": "open_app", "app": "notepad", "label": "Open Notepad"}}
    return None


def unhandled_operation(message):
    text = str(message).strip().lower()
    if re.search(r"^(?:how|why|explain|what|kaise)\b", text):
        return False
    hindi_operation = bool(re.search(r"\b(?:likho|likhdo|kholo|bhejo|hatao|chalao)\b|लिखो|खोलो|भेजो|हटाओ", text))
    if hindi_operation:
        creative = bool(re.search(r"\b(?:kahani|poem|story|shayari|kavita|joke|essay|draft)\b|कहानी|कविता", text))
        if not creative or re.search(r"notepad|app|window|file|नोटपैड", text):
            return True
    return bool(re.search(r"^(?:(?:please|can you|could you)\s+)?(?:open|launch|close|send|click|press|type|delete|remove)\b", text)
                or re.search(r"\b(?:open|write|type|send|delete|click)\b.*\b(?:karo|kar do|notepad|app|window|file)\b", text))


def capability_request(message):
    """Classify an explicit request to add a capability without executing code."""
    text = str(message).strip().lower()
    asks_to_build = bool(re.search(
        r"\b(?:can you|could you|will you|please|kya aap|kya tum|bana(?:o|doge|na)?|banado|add|build|implement|create|develop|improve|upgrade|chahiye)\b",
        text,
    ))
    describes_gap = bool(re.search(
        r"(?:functionality|feature|capability|support|ability|kaam|kshamta|intelligent|smart|jarvis).*(?:nahi|nahin|missing|unavailable|available nahi|add|build|bana)|(?:nahi|nahin|missing|unavailable).*(?:functionality|feature|capability|support|ability)|aur\s+(?:intelligent|smart|jarvis)",
        text,
    ))
    describes_gap = describes_gap or bool(re.search(
        r"(?:make|banao|bana|build|improve|upgrade).*(?:sara|her|it).*(?:intelligent|smart|jarvis)|(?:sara|her|it).*(?:intelligent|smart|jarvis).*(?:banao|banana|build|improve|upgrade)",
        text,
    ))
    build_verb = bool(re.search(r"\b(?:build|implement|create|develop|add|upgrade|improve|make|banao|banado|bana doge)\b", text))
    feature_target = bool(re.search(r"\b(?:feature|functionality|capability|support|integration|sync|automation|skill|voice|speech|memory|learning|app control|app shortcut|desktop control|screen sharing|vision)\b", text))
    describes_gap = describes_gap or (asks_to_build and build_verb and feature_target)
    if not (asks_to_build and describes_gap):
        return None
    if re.search(r"custom app|app shortcut|register.*app", text):
        return {"key": "custom_app_shortcuts", "title": "custom Windows app shortcuts", "access": "Settings mein app ka naam aur uski absolute `.exe` path; SARA har launch se pehle approval maangti hai", "steps": ["Settings → App shortcuts mein app name aur `.exe` path add karna", "chat mein saved name se app kholne ki request dena", "har launch se pehle review approve karna"]}
    if re.search(r"email|mail|gmail|send mail", text):
        return {"key": "email", "title": "direct email integration", "access": "mail provider/API credentials aur send permission", "steps": ["provider connector choose karna", "draft/send scopes configure karna", "har send se pehle exact message review karna"]}
    if re.search(r"google|outlook|calendar sync|sync.*calendar", text):
        return {"key": "external_calendar_sync", "title": "Google/Outlook calendar sync", "access": "Google ya Microsoft account ka OAuth approval", "steps": ["provider OAuth settings add karna", "tokens ko local encrypted store mein rakhna", "read/write sync ko confirmation ke saath test karna"]}
    if re.search(r"notification|notify|server band|background|startup|reminder", text):
        return {"key": "persistent_reminders", "title": "SARA band hone par reminders check karna", "access": "SARA project folder aur current-user Windows Scheduled Task permission", "steps": ["project folder mein install_sara_reminders.ps1 chalakar optional task enable karna", "worker har minute due reminders check karega jab aap Windows mein signed in hon", "uninstall_sara_reminders.ps1 se task hataya ja sakta hai; saved reminders rahenge"]}
    if re.search(r"app|software|computer|system|desktop|jarvis|anything|kuch bhi", text):
        return {"key": "system_control", "title": "broader Windows app/system control", "access": "explicit per-app allowlist aur action confirmation", "steps": ["safe allowlist define karna", "dry-run preview aur stop control jodna", "one action at a time real-result logging test karna"]}
    return {"key": "chat", "title": "SARA ka next intelligence module", "access": "aapka exact use-case aur required local access", "steps": ["use-case ko chhote deterministic workflow mein todna", "capability registry aur confirmation policy update karna", "offline/local regression tests add karna"]}


def action_payload(action):
    """Canonical body approved by the dashboard for proposal identity checks."""
    kind = action.get("type")
    if kind == "create_reminder":
        return dict(action.get("reminder") or {})
    if kind == "create_event":
        return dict(action.get("event") or {})
    fields = {
        "open_app": ("app", "executable"), "notepad_write": ("text",), "open_browser_url": ("url",), "browser_open": ("url",),
        "browser_click_text": ("url", "text"), "browser_fill": ("url", "label", "value"),
        "whatsapp_send": ("phone", "text"), "whatsapp_draft": ("phone", "text"), "email_draft": ("to", "subject", "body"),
        "type_text": ("text",), "hotkey": ("keys",), "click_point": ("x", "y"), "save_memory": ("text",),
        "create_task": ("text",), "write_file": ("path", "content"), "delete_file": ("path",),
        "save_pronunciation": ("word", "say_as"),
        "add_custom_app": ("name", "executable"),
        "save_capability_request": ("title", "description"),
    }.get(kind, ())
    return {key: action[key] for key in fields if key in action}

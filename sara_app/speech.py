"""Fast speech preparation for mixed Hindi and English, without a model call.

This is a pronunciation lexicon, not a general transliterator. Unknown Latin
words remain English so a Hindi voice does not try to spell them. A browser
still needs installed voices for the returned language tags.
"""

import html
import re


HINDI_WORDS = {
    "aap": "आप", "aapko": "आपको", "aapka": "आपका", "aapki": "आपकी", "aapke": "आपके",
    "tum": "तुम", "tumhe": "तुम्हें", "tumhara": "तुम्हारा", "tumhari": "तुम्हारी", "tumhare": "तुम्हारे",
    "mujhe": "मुझे", "mujhse": "मुझसे", "mera": "मेरा", "meri": "मेरी", "mere": "मेरे", "mereko": "मुझे",
    "hum": "हम", "hume": "हमें", "humein": "हमें", "hamara": "हमारा", "hamari": "हमारी", "hamare": "हमारे",
    "kya": "क्या", "kyun": "क्यों", "kyu": "क्यों", "kyon": "क्यों", "kyunki": "क्योंकि", "kaise": "कैसे",
    "kaisa": "कैसा", "kaisi": "कैसी", "kaun": "कौन", "kahan": "कहाँ", "kahaan": "कहाँ", "kab": "कब",
    "kitna": "कितना", "kitni": "कितनी", "kitne": "कितने", "kis": "किस", "kise": "किसे", "kisko": "किसको",
    "hai": "है", "hain": "हैं", "hoon": "हूँ", "hun": "हूँ", "tha": "था", "thi": "थी", "thaa": "था",
    "hoga": "होगा", "hogi": "होगी", "honge": "होंगे", "hona": "होना", "hone": "होने", "hote": "होते", "hoti": "होती",
    "aur": "और", "lekin": "लेकिन", "magar": "मगर", "bhi": "भी", "sirf": "सिर्फ", "phir": "फिर", "fir": "फिर",
    "abhi": "अभी", "ab": "अब", "aaj": "आज", "kal": "कल", "parso": "परसों", "pehle": "पहले", "baad": "बाद",
    "dobara": "दोबारा", "hamesha": "हमेशा", "kabhi": "कभी", "jaldi": "जल्दी", "dheere": "धीरे", "turant": "तुरंत",
    "nahi": "नहीं", "nahin": "नहीं", "nai": "नहीं", "haan": "हाँ", "han": "हाँ", "ha": "हाँ", "bilkul": "बिल्कुल",
    "bahut": "बहुत", "bahot": "बहुत", "bohot": "बहुत", "thoda": "थोड़ा", "thodi": "थोड़ी", "thode": "थोड़े",
    "zyada": "ज़्यादा", "jyada": "ज़्यादा", "kaafi": "काफ़ी", "kafi": "काफ़ी", "kam": "कम", "itna": "इतना", "itni": "इतनी",
    "karna": "करना", "karne": "करने", "karo": "करो", "kare": "करें", "karein": "करें", "karen": "करें",
    "karta": "करता", "karti": "करती", "karte": "करते", "kiya": "किया", "kiye": "किए", "karunga": "करूँगा", "karungi": "करूँगी",
    "raha": "रहा", "rahi": "रही", "rahe": "रहे", "rakho": "रखो", "rakhna": "रखना", "rakha": "रखा",
    "batao": "बताओ", "bataiye": "बताइए", "batana": "बताना", "batati": "बताती", "bataunga": "बताऊँगा", "bataungi": "बताऊँगी",
    "bolo": "बोलो", "bolna": "बोलना", "bolti": "बोलती", "bolta": "बोलता", "bol": "बोल",
    "suno": "सुनो", "sunna": "सुनना", "sunti": "सुनती", "sunai": "सुनाई", "suna": "सुना",
    "dekho": "देखो", "dekhna": "देखना", "dikhao": "दिखाओ", "dikhana": "दिखाना", "dikhai": "दिखाई",
    "samjho": "समझो", "samajh": "समझ", "samajhna": "समझना", "samjhao": "समझाओ", "samajhkar": "समझकर",
    "chahiye": "चाहिए", "chahta": "चाहता", "chahti": "चाहती", "chahte": "चाहते", "chahoge": "चाहोगे",
    "sakta": "सकता", "sakti": "सकती", "sakte": "सकते", "sako": "सको", "sakun": "सकूँ",
    "deta": "देता", "deti": "देती", "dete": "देते", "dijiye": "दीजिए", "dega": "देगा", "degi": "देगी", "dena": "देना",
    "liya": "लिया", "lijiye": "लीजिए", "lena": "लेना", "lene": "लेने", "leta": "लेता", "leti": "लेती",
    "bhejo": "भेजो", "bhejna": "भेजना", "bheja": "भेजा", "kholo": "खोलो", "kholna": "खोलना", "khola": "खोला",
    "banao": "बनाओ", "banana": "बनाना", "banaya": "बनाया", "bani": "बनी", "banega": "बनेगा", "banegi": "बनेगी",
    "chalao": "चलाओ", "chalana": "चलाना", "chalo": "चलो", "chalta": "चलता", "chalti": "चलती", "chal": "चल",
    "hatao": "हटाओ", "hatana": "हटाना", "bachao": "बचाओ", "badlo": "बदलो", "badalna": "बदलना",
    "seekho": "सीखो", "seekhna": "सीखना", "sikhao": "सिखाओ", "pata": "पता", "yaad": "याद", "bhool": "भूल",
    "ke": "के", "ka": "का", "ki": "की", "ko": "को", "se": "से", "liye": "लिए", "liyeh": "लिए",
    "mein": "में", "mai": "मैं", "yahan": "यहाँ", "yahin": "यहीं", "wahan": "वहाँ", "idhar": "इधर", "udhar": "उधर",
    "ye": "ये", "yeh": "यह", "yah": "यह", "woh": "वो", "vo": "वो", "wo": "वो", "iska": "इसका", "iski": "इसकी",
    "iske": "इसके", "isko": "इसको", "isse": "इससे", "uska": "उसका", "uski": "उसकी", "uske": "उसके", "usko": "उसको",
    "apna": "अपना", "apni": "अपनी", "apne": "अपने", "saath": "साथ", "sath": "साथ", "bina": "बिना", "tak": "तक",
    "accha": "अच्छा", "acha": "अच्छा", "achha": "अच्छा", "acchi": "अच्छी", "achi": "अच्छी", "achhe": "अच्छे",
    "theek": "ठीक", "thik": "ठीक", "sahi": "सही", "galat": "गलत", "behtar": "बेहतर", "badhiya": "बढ़िया",
    "zaroor": "ज़रूर", "jarur": "ज़रूर", "zaruri": "ज़रूरी", "zaroori": "ज़रूरी", "aasaan": "आसान", "asan": "आसान",
    "mushkil": "मुश्किल", "naya": "नया", "nayi": "नई", "naye": "नए", "purana": "पुराना", "puri": "पूरी", "poora": "पूरा",
    "pura": "पूरा", "poori": "पूरी", "sab": "सब", "sabhi": "सभी", "kuch": "कुछ", "koi": "कोई", "har": "हर",
    "kaam": "काम", "baat": "बात", "baatein": "बातें", "din": "दिन", "raat": "रात", "subah": "सुबह", "shaam": "शाम",
    "samay": "समय", "waqt": "वक़्त", "dost": "दोस्त", "dosti": "दोस्ती", "khushi": "खुशी", "pareshan": "परेशान",
    "madad": "मदद", "shukriya": "शुक्रिया", "dhanyavad": "धन्यवाद", "dhanyawaad": "धन्यवाद", "namaste": "नमस्ते",
    "namaskar": "नमस्कार", "maaf": "माफ़", "ruk": "रुक", "ruko": "रुको", "bas": "बस", "ek": "एक", "doosra": "दूसरा",
}

# These are genuine English words too. Convert them only in a Hindi context.
CONTEXT_WORDS = {"main": "मैं", "par": "पर", "kar": "कर", "ho": "हो", "to": "तो", "ya": "या", "na": "ना"}
HINDI_SIGNALS = {"aap", "mujhe", "mujhse", "kya", "kyun", "kaise", "hai", "hain", "hoon", "nahi", "nahin", "batao", "karo", "karna", "chahiye", "aaj", "mera", "meri", "tum", "hum", "namaste", "raha", "rahi", "dikhao", "samjhao"}
AMBIGUOUS_WORDS = {"banana", "hum", "ab", "ha", "mai", "din"}
HINDI_CONTEXT_WORDS = frozenset((HINDI_WORDS.keys() | HINDI_SIGNALS) - AMBIGUOUS_WORDS)
ACRONYMS = {
    "UI": "user interface", "API": "application programming interface", "AI": "artificial intelligence",
    "CPU": "processor", "GPU": "graphics processor", "URL": "web address", "HTML": "hypertext markup language",
    "CSS": "style sheet", "JSON": "JavaScript object notation", "JS": "JavaScript", "SQL": "structured query language",
}
TOKEN = re.compile(r"[\u0900-\u097f\u200c\u200d]+|[A-Za-z]+(?:['’][A-Za-z]+)*|[^\W\d_]+|\d+(?:[.,]\d+)*|[^\w\s]|\s+", re.UNICODE)
LATIN_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*\Z")
DEVANAGARI = re.compile(r"[\u0900-\u097f]")
HTML_TAG = re.compile(r"""</?[A-Za-z][A-Za-z0-9:-]*(?:\s+(?:[^<>"']|"[^"]*"|'[^']*')*)?\s*/?>""")
SARA_INITIALS = re.compile(
    r"(?<!\w)s(?:\s*\.\s*|[ \t]+)a(?:\s*\.\s*|[ \t]+)r(?:\s*\.\s*|[ \t]+)a\.?"
    r"(?!\w|\.[A-Za-z]|[ \t]+[A-Za-z](?:\.|\b))", re.I,
)

# Local system voices insert a gap when an utterance/voice changes. Keep whole
# mixed sentences together and only use known pronunciations in Hindi playback.
# Display text and the fine language segments remain unchanged for callers.
PLAYBACK_MAX_CHARS = 380
HINDI_TECH_PRONUNCIATIONS = {
    "application programming interface": "एप्लिकेशन प्रोग्रामिंग इंटरफ़ेस",
    "user interface": "यूज़र इंटरफ़ेस",
    "artificial intelligence": "आर्टिफ़िशियल इंटेलिजेंस",
    "graphics processor": "ग्राफ़िक्स प्रोसेसर",
    "hypertext markup language": "हाइपरटेक्स्ट मार्कअप लैंग्वेज",
    "javascript object notation": "जावास्क्रिप्ट ऑब्जेक्ट नोटेशन",
    "structured query language": "स्ट्रक्चर्ड क्वेरी लैंग्वेज",
    "web address": "वेब एड्रेस", "style sheet": "स्टाइल शीट",
    "main window": "मेन विंडो", "main menu": "मेन मेन्यू",
    "sara": "सारा", "dashboard": "डैशबोर्ड", "network": "नेटवर्क",
    "settings": "सेटिंग्स", "system": "सिस्टम", "voice": "वॉइस",
    "microphone": "माइक्रोफ़ोन", "mic": "माइक", "browser": "ब्राउज़र",
    "reply": "रिप्लाई", "response": "रिस्पॉन्स", "please": "प्लीज़",
    "ready": "रेडी", "window": "विंडो", "screen": "स्क्रीन",
    "file": "फ़ाइल", "files": "फ़ाइल्स", "code": "कोड", "test": "टेस्ट",
    "model": "मॉडल", "local": "लोकल", "cloud": "क्लाउड",
    "computer": "कंप्यूटर", "processor": "प्रोसेसर", "javascript": "जावास्क्रिप्ट",
    "task": "टास्क", "tasks": "टास्क्स", "reminder": "रिमाइंडर",
    "reminders": "रिमाइंडर्स",
}
HINDI_TECH_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(word) for word in sorted(HINDI_TECH_PRONUNCIATIONS, key=len, reverse=True)) + r")(?!\w)",
    re.I,
)
SENTENCE_END = re.compile(r"[.!?।]+(?:[\"'”’)]*)(?=\s|$)")
SHORT_ABBREVIATIONS = frozenset({"mr", "mrs", "ms", "dr", "prof", "vs", "st", "approx", "e.g", "i.e"})


def _sentences(text):
    """Split at prose sentence ends, preserving punctuation and common titles."""
    start = 0
    for boundary in SENTENCE_END.finditer(text):
        ending = text[start:boundary.end()]
        last_word = re.search(r"([A-Za-z.]+)\.$", ending.rstrip())
        if last_word and last_word.group(1).lower().rstrip(".") in SHORT_ABBREVIATIONS:
            continue
        if ending.strip():
            yield ending.strip()
        start = boundary.end()
    if text[start:].strip():
        yield text[start:].strip()


def _bounded_phrases(text):
    """Prefer clause breaks; use grouped words only for a giant unpunctuated clause.

    The limit is soft for a single oversized token so an unknown name/string is
    never split into letters or silently dropped.
    """
    remaining = text.strip()
    while len(remaining) > PLAYBACK_MAX_CHARS:
        window = remaining[:PLAYBACK_MAX_CHARS + 1]
        clauses = list(re.finditer(r"[,;:]\s+", window))
        useful = [match for match in clauses if match.end() >= PLAYBACK_MAX_CHARS // 3]
        if useful:
            cut = useful[-1].end()
        else:
            cut = window.rfind(" ")
            if cut <= 0:
                cut = remaining.find(" ", PLAYBACK_MAX_CHARS)
                if cut < 0:
                    break
        yield remaining[:cut].strip()
        remaining = remaining[cut:].strip()
    if remaining:
        yield remaining


def playback_plan(text):
    """Plan fluent system TTS units without switching voices inside a sentence."""
    planned = []
    for sentence in _sentences(text):
        lang = "hi-IN" if DEVANAGARI.search(sentence) else "en-IN"
        spoken = HINDI_TECH_PATTERN.sub(lambda match: HINDI_TECH_PRONUNCIATIONS[match.group().lower()], sentence) if lang == "hi-IN" else sentence
        for phrase in _bounded_phrases(spoken):
            if planned and planned[-1]["lang"] == lang and len(planned[-1]["text"]) + len(phrase) + 1 <= PLAYBACK_MAX_CHARS:
                planned[-1]["text"] += " " + phrase
            else:
                planned.append({"text": phrase, "lang": lang})
    return planned


def clean_speech_text(text):
    """Remove display-only formatting while keeping ordinary prose and labels."""
    text = html.unescape(str(text or ""))
    text = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~", " ", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = HTML_TAG.sub(" ", text)
    text = SARA_INITIALS.sub("Sara", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"(?m)^\s*[-=_]{3,}\s*$", " ", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*{1,3}|(?<!\w)_{1,3}|_{1,3}(?!\w)", "", text)
    text = text.replace("_", " ")
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
    text = text.replace("|", ", ").replace("…", ". ").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?।])", r"\1", text)


def apply_pronunciations(text, pronunciations):
    """Apply user-approved local say-as entries to speech text only."""
    entries = [
        item for item in (pronunciations if isinstance(pronunciations, list) else [])
        if isinstance(item, dict)
        and str(item.get("word", "")).strip()
        and str(item.get("say_as", "")).strip()
    ]
    entries.sort(key=lambda item: len(str(item["word"])), reverse=True)
    for item in entries:
        source = str(item["word"]).strip()
        replacement = str(item["say_as"]).strip()
        pattern = re.compile(r"(?<!\w)" + re.escape(source) + r"(?!\w)", re.I)
        text = pattern.sub(lambda _match, value=replacement: value, text)
    return text


def prepare_speech(text):
    """Return clean speech text and consecutive Hindi/English language segments.

    Unknown words are kept intact, never converted to individual letter names.
    Exact English pronunciation remains the responsibility of the selected TTS
    voice; this function cannot infer every name or every Roman Hindi spelling.
    """
    cleaned = clean_speech_text(text)
    try:
        from .storage import read_pronunciations
        cleaned = apply_pronunciations(cleaned, read_pronunciations())
    except (OSError, ValueError):
        pass
    if not cleaned:
        return {"text": "", "segments": [], "playback": []}
    words = re.findall(r"[A-Za-z]+", cleaned.lower())
    hindi_context = bool(DEVANAGARI.search(cleaned)) or bool(HINDI_CONTEXT_WORDS.intersection(words))
    matches = list(TOKEN.finditer(cleaned))
    segments = []
    output = []
    leading = ""
    for match in matches:
        value = match.group()
        lang = None
        if DEVANAGARI.search(value):
            lang = "hi-IN"
        elif LATIN_WORD.fullmatch(value):
            lower = value.lower()
            if lower == "sara":
                value, lang = "Sara", "en-IN"
            elif value in ACRONYMS:
                value, lang = ACRONYMS[value], "en-IN"
            elif lower in HINDI_WORDS and (lower not in AMBIGUOUS_WORDS or hindi_context):
                following = cleaned[match.end():].lstrip().split(" ", 1)[0].lower().strip(".,!?:;")
                if lower == "banana" and following in {"bread", "smoothie", "fruit", "shake", "split", "cake", "peel"}:
                    lang = "en-IN"
                else:
                    value, lang = HINDI_WORDS[lower], "hi-IN"
            elif hindi_context and lower in CONTEXT_WORDS:
                # "main window/menu" is an English adjective even in Hinglish.
                following = cleaned[match.end():].lstrip().split(" ", 1)[0].lower().strip(".,!?:;")
                if lower == "main" and following in {"window", "screen", "menu", "file", "thread", "page", "dashboard", "branch"}:
                    lang = "en-IN"
                else:
                    value, lang = CONTEXT_WORDS[lower], "hi-IN"
            else:
                lang = "en-IN"
        elif value[0].isalpha():
            lang = "en-IN"
        elif value[0].isdigit():
            lang = segments[-1]["lang"] if segments else ("hi-IN" if hindi_context else "en-IN")
        output.append(value)
        if lang is None:
            if segments:
                segments[-1]["text"] += value
            else:
                leading += value
        elif segments and segments[-1]["lang"] == lang:
            segments[-1]["text"] += value
        else:
            segments.append({"text": leading + value, "lang": lang})
            leading = ""
    for segment in segments:
        segment["text"] = segment["text"].strip()
    segments = [segment for segment in segments if segment["text"]]
    spoken = "".join(output).strip() if segments else ""
    return {"text": spoken, "segments": segments, "playback": playback_plan(spoken)}


def fallback_speech_text(text):
    """Compatibility wrapper returning only the prepared text."""
    return prepare_speech(text)["text"]

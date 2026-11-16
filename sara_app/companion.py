"""Small, explicit companion signals used to tune SARA's tone and dashboard.

Signals are ephemeral; this module never stores moods or infers feelings.
"""
import re

def conversation_signals(message):
    text = str(message or '').strip().lower()
    if re.search(r"\b(listen|sunो|suno|बस बात|bas baat|mann halka|talk to me)\b", text):
        return {'mode': 'listen', 'label': 'Listening'}
    if re.search(r"\b(plan|schedule|task|kaam|योजना|agenda|briefing)\b", text):
        return {'mode': 'practical', 'label': 'Planning'}
    if re.search(r"\b(thanks|thank you|शाबाश|great|good job|बढ़िया)\b", text):
        return {'mode': 'celebrate', 'label': 'Celebrating'}
    return {'mode': 'neutral', 'label': 'Ready'}

def dashboard_context(message):
    text = str(message or '').lower()
    if re.search(r"image|photo|screen|camera|screenshot|दिख", text): return 'visual'
    if re.search(r"plan|schedule|task|agenda|briefing|योजना|काम", text): return 'planning'
    if re.search(r"focus|concentrate|routine|workflow", text): return 'focus'
    if re.search(r"listen|suno|बात|talk|feel", text): return 'conversation'
    return 'overview'

def companion_instructions(message):
    mode = conversation_signals(message)['mode']
    if mode == 'listen': return 'Be patient and reflective. Let the user speak; ask at most one gentle follow-up question.'
    if mode == 'celebrate': return 'Acknowledge the user warmly and briefly, then offer the next useful step.'
    if mode == 'practical': return 'Be structured and action-oriented, while stating approval or capability limits clearly.'
    return 'Be warm, concise and attentive without claiming human feelings or attachment.'

def supportive_fallback(message):
    return 'मैं यहाँ हूँ। अभी local AI service उपलब्ध नहीं है, लेकिन मैं आपकी बात सुन सकती हूँ और उपलब्ध safe tools से मदद कर सकती हूँ।'

def learning_candidate(message, approved_memories=()):
    raw = str(message or '').strip()
    low = raw.lower()
    if len(raw) < 12 or len(raw) > 240: return None
    if re.search(r"password|otp|api key|secret|token|पासवर्ड|ओटीपी|credit card|bank", low): return None
    if re.search(r"\b(i am|i'm|मेरी पसंद|मुझे पसंद|my favorite|मैं चाहता|मेरा नाम|my name)\b", low):
        if any(raw.casefold() == str(item.get('text','')).casefold() for item in approved_memories if isinstance(item, dict)): return None
        return raw
    return None

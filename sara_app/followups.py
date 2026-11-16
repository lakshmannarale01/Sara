"""Bounded search continuity; previous conversation text is never executed."""
import re
from urllib.parse import quote_plus

def plan_search(message, turns=()):
    text = re.sub(r'^(?:sara[, :]+|ab\s+|now\s+|फिर\s+|अब\s+)', '', message.strip(), flags=re.I)
    match = re.fullmatch(r'(?:search(?:\s+karo)?|find|look up|खोजो|सर्च करो)\s+(?:for\s+)?(.+)', text, re.I)
    if not match:
        match = re.fullmatch(r'(.+?)\s+(?:search karo|search kar do|सर्च करो|खोजो)[.!।]*', text, re.I)
    if not match:
        return None
    query = match.group(1).strip()
    if re.fullmatch(r'it|that|this|same|ye|yeh|isko|usko|वही|इसे|उसे', query, re.I):
        query = next((row['search_query'] for row in reversed(list(turns)) if isinstance(row.get('search_query'), str)), '')
        if not query:
            return {'reply': 'किस बारे में search करूँ? Topic या नाम बता दो।', 'provider': 'search-context'}
    if not 1 <= len(query) <= 500:
        return {'reply': 'Search के लिए topic थोड़ा छोटा बताओ—500 characters तक।', 'provider': 'search-context'}
    return {'reply': f'“{query}” की web search तैयार है।', 'provider': 'search-context',
            'search_query': query, 'requires_confirmation': True,
            'action': {'type': 'open_browser_url', 'url': 'https://www.google.com/search?q=' + quote_plus(query), 'label': 'Search: ' + query}}

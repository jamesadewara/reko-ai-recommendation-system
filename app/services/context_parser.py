import re
from datetime import datetime
from typing import List, Optional
from loguru import logger

from app.ml.spacy_loader import get_nlp

def parse_context(message: str, history: List[dict] = None) -> dict:
    nlp = get_nlp()
    doc = nlp(message)
    
    # Location detection
    locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
    nigerian_cities_regex = r'\b(Lagos|Ikeja|Lekki|Surulere|Abuja|Ibadan|Port Harcourt)\b'
    match = re.search(nigerian_cities_regex, message, re.IGNORECASE)
    
    if locations:
        location = locations[0]
    elif match:
        location = match.group(1)
    else:
        location = "unknown"

    # Mood detection
    MOOD_KEYWORDS = {
        "tired": ["tired", "exhausted", "sleepy", "drained", "burnt out", "need rest"],
        "excited": ["excited", "pumped", "hyped", "can't wait", "thrilled"],
        "bored": ["bored", "nothing to do", "uninterested", "dull"],
        "stressed": ["stressed", "anxious", "worried", "overwhelmed"],
        "happy": ["happy", "joyful", "great mood", "feeling good"],
        "hungry": ["hungry", "starving", "craving", "want to eat", "food"],
        "sad": ["sad", "down", "depressed", "melancholy"],
        "curious": ["curious", "interested", "want to learn", "discover"]
    }
    
    message_lower = message.lower()
    mood = "neutral"
    for m, keywords in MOOD_KEYWORDS.items():
        if any(kw in message_lower for kw in keywords):
            mood = m
            break

    # Time detection
    current_time = datetime.now()
    hour = current_time.hour
    
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
        
    if "tonight" in message_lower:
        time_of_day = "night"
    elif "this morning" in message_lower:
        time_of_day = "morning"
    elif "lunch" in message_lower:
        time_of_day = "afternoon"
    elif "dinner" in message_lower:
        time_of_day = "evening"

    # Category detection
    CATEGORY_KEYWORDS = {
        "movies": ["movie", "film", "watch", "cinema", "netflix", "nollywood"],
        "food": ["food", "eat", "restaurant", "hungry", "cuisine", "jollof", "suya"],
        "music": ["music", "song", "album", "artist", "listen", "afrobeats", "wizkid"],
        "books": ["book", "read", "novel", "author", "literature"],
        "products": ["product", "buy", "gadget", "device", "shop"]
    }
    
    category = None
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in message_lower for kw in keywords):
            category = cat
            break

    recent_activity = "none"
    if history and len(history) > 0:
        recent_activity = history[-1].get("content", "none")

    parsed = {
        "mood": mood,
        "time_of_day": time_of_day,
        "location": location,
        "category": category,
        "current_hour": hour,
        "recent_activity": recent_activity
    }
    logger.debug(f"[ContextParser] Parsed: {parsed}")
    return parsed

import datetime
import random
import numpy as np
from typing import Optional
from app.documents.user import UserDocument
from app.services.embedding_encoder import get_encoder

def get_time_context() -> str:
    hour = datetime.datetime.now().hour
    if hour < 12: return "morning"
    if hour < 17: return "afternoon"
    if hour < 21: return "evening"
    return "night"

async def get_personalized_placeholder(user: Optional[UserDocument], mode: str = "chat") -> str:
    time_context = get_time_context()
    
    # Punchy, time-aware prompts for semantic matching
    prompts = {
        "chat": {
            "morning": [
                "Morning. Let's find your next obsession.", 
                "Wake up. What's the morning move?", 
                "Rise and grind. Ask me anything.",
                "Fresh start. What's the vibe today?"
            ],
            "afternoon": [
                "Afternoon flow. What's the latest?", 
                "Lunch break? Let's find a gem.", 
                "Mid-day check-in. Need a rec?",
                "The move is yours. Ask away."
            ],
            "evening": [
                "Evening chill. What's the plan?", 
                "Sun's down. What are we watching?", 
                "Evening energy. Need a pick?",
                "Winding down? Let's find something."
            ],
            "night": [
                "Night owl energy. What's the vibe?", 
                "Late night discovery. Ask me.", 
                "Deep cuts only. What's on deck?",
                "Quiet hours. What do you need?"
            ]
        },
        "recommend": {
            "morning": ["Morning discovery. What's the item?", "Early picks only.", "Morning vibes. Ask for a rec."],
            "afternoon": ["Lunchtime gems. What's next?", "Afternoon flex. Need a move?", "Mid-day discovery."],
            "evening": ["Evening picks. What's the plan?", "Dinner or movies?", "Relax and discover."],
            "night": ["Late night moves.", "Midnight discovery.", "Deep-cut picks."]
        },
        "review": {
            "morning": ["Review mode. Let's cook.", "Early critique?", "Rate your morning find."],
            "afternoon": ["Afternoon review. What's the item?", "Got a take? Drop it.", "Rate your latest move."],
            "evening": ["Evening critique. Ready?", "Let's build your review.", "Rate the vibe."],
            "night": ["Late night thoughts?", "Midnight review mode.", "Deep-dive critique."]
        }
    }

    category = prompts.get(mode, prompts["chat"])
    options = category.get(time_context, category["afternoon"])
    
    # 1. Semantic Matching (If user has embeddings)
    placeholder = ""
    if user and user.interest_embeddings and len(user.interest_embeddings) > 0:
        try:
            encoder = get_encoder()
            user_vec = np.array(user.interest_embeddings)
            option_vecs = encoder.encode(options)
            similarities = np.dot(option_vecs, user_vec)
            best_idx = np.argmax(similarities)
            placeholder = options[best_idx]
        except Exception:
            placeholder = random.choice(options)
    else:
        placeholder = random.choice(options)

    # 2. Personalization Injection
    if user:
        name = user.name.split()[0] if user.name else ""
        if name:
            # Case-insensitive replacement for common starters
            for prefix in ["Morning", "Afternoon", "Evening"]:
                if placeholder.startswith(prefix):
                    placeholder = placeholder.replace(prefix, f"{prefix} {name}", 1)
            
        # Add interest context (Ensure no double punctuation)
        if user.taste_profile.interests:
            interest = random.choice(user.taste_profile.interests)
            placeholder = placeholder.rstrip(".?! ")
            placeholder += f" ({interest}?)"

        # Add Nigerian flavor (Ensure spacing and no double punctuation)
        if user.taste_profile.nigerian_context and user.style_fingerprint.nigerian_markers:
            marker = random.choice(user.style_fingerprint.nigerian_markers)
            placeholder = placeholder.rstrip(".?! ")
            placeholder += f" {marker}!"

    return placeholder.strip()

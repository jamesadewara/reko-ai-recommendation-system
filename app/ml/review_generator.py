import re
from typing import List, Dict, Optional
from loguru import logger
from fastapi import HTTPException

from litellm import completion
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.documents.user import UserDocument

class ReviewGenerator:
    def __init__(self):
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _call_llm(self, messages: list) -> str:
        """
        Calls the primary model with a creative temperature.
        """
        from app.core.llm import llm_service
        return await llm_service.get_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=250
        )

    async def generate(self, user_id: str, product: dict, search_context: str = None) -> dict:
        """
        Generate a hyper-personalized review using the user's real style and taste.
        """
        user = await UserDocument.find_by_id_or_uuid(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        if not user.style_fingerprint or not user.taste_profile:
            raise HTTPException(
                status_code=400, 
                detail="User model not ready. Run analysis first."
            )

        # Build personalized context
        interests = ", ".join(user.taste_profile.interests[:8])
        traits = ", ".join(user.taste_profile.personality_traits[:5])
        tone = user.taste_profile.writing_tone
        phrases = ", ".join(user.style_fingerprint.top_phrases[:5])
        
        avg_len = user.style_fingerprint.avg_sentence_length
        exclam = user.style_fingerprint.exclamation_ratio
        formality = user.style_fingerprint.formality_score
        
        enthusiasm = "high" if exclam > 0.2 else "moderate" if exclam > 0.05 else "calm"
        formality_label = "formal" if formality > 0.6 else "casual" if formality < 0.4 else "balanced"
        
        nigerian_markers = ", ".join(user.style_fingerprint.nigerian_markers) or "none"

        system_prompt = f"""
        You are {user.name}. You are writing a short product review.
        
        Your personality (based on your online presence):
        - Interests: {interests}
        - Personality traits: {traits}
        - Writing tone: {tone}
        - Favorite phrases you use: {phrases}
        
        Your writing style metrics:
        - Average sentence length: {avg_len:.0f} words
        - Enthusiasm level: {enthusiasm}
        - Formality: {formality_label}
        
        Nigerian expressions you naturally use: {nigerian_markers}
        
        INSTRUCTIONS:
        - Write EXACTLY 4-6 sentences.
        - Match your natural sentence length and tone.
        - Use your favorite phrases where natural.
        - If you use Nigerian Pidgin markers, sprinkle them naturally (don't force it).
        - Be authentic. Don't sound like generic AI.
        - End with a star rating sentiment (but don't write "I give X stars").
        """

        user_prompt = f"""
        Product: {product.get('name', 'Unknown Product')}
        Category: {product.get('category', 'Unknown Category')}
        Description: {product.get('description', 'No description provided.')}
        """
        if search_context:
            user_prompt += f"\nOnline Context for Reference:\n{search_context}\n"
            
        user_prompt += "\nYour review:\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        logger.info(f"[ReviewGenerator] Generating review for user {user.name} for product {product['name']}...")
        
        review_text = await self._call_llm(messages)
        
        # Post-process
        review_text = review_text.strip().replace("```", "")
        
        # Sentence splitting (approximate)
        sentences = re.split(r'(?<=[.!?])\s+', review_text)
        
        # Retry logic if too short
        if len(sentences) < 3:
            logger.info("[ReviewGenerator] Review too short, retrying...")
            review_text = await self._call_llm(messages) # retry
            sentences = re.split(r'(?<=[.!?])\s+', review_text.strip())

        # Truncate if too long
        if len(sentences) > 8:
            review_text = " ".join(sentences[:8])
            sentences = sentences[:8]

        # Detect markers used
        markers_used = [m for m in user.style_fingerprint.nigerian_markers if m.lower() in review_text.lower()]

        return {
            "review_text": review_text,
            "sentence_count": len(sentences),
            "used_nigerian_markers": markers_used,
            "style_match_score": 0.85 # Heuristic for now
        }

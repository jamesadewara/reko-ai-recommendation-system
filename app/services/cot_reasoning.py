import re
from typing import List
from loguru import logger
from fastapi import HTTPException
from tenacity import retry, stop_after_attempt, wait_exponential

from litellm import acompletion
from app.core.config import settings
from app.documents.user import UserDocument

class CoTReasoning:
    def __init__(self):
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=6))
    async def _call_llm(self, messages: list) -> str:
        from app.core.llm import llm_service
        return await llm_service.get_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=300
        )

    async def generate_reasoning_chain(self, user: UserDocument, context: dict, category: str) -> List[str]:
        if not user.taste_profile:
            return []

        interests = ", ".join(user.taste_profile.interests[:10])
        traits = ", ".join(user.taste_profile.personality_traits[:5])
        tone = user.taste_profile.writing_tone
        nigerian_context = user.taste_profile.nigerian_context

        prompt = f"""
        You are a thoughtful recommendation agent. Recommend {category} for this user.

        User Profile:
        - Name: {user.name}
        - Interests: {interests}
        - Personality: {traits}
        - Writing tone: {tone}
        - Nigerian context: {nigerian_context}

        Current Context:
        - Mood: {context.get('mood')}
        - Time: {context.get('time_of_day')}
        - Location: {context.get('location')}
        - Recent activity: {context.get('recent_activity')}
        """

        if user.is_birthday_today():
            prompt += "\n\n        CRITICAL CONTEXT: Today is the user's birthday! Congratulate them in the reasoning and ensure the recommendation feels like a special birthday treat or celebratory suggestion."

        prompt += f"""
        Think step-by-step. Consider:
        1. What the user likes based on their interests
        2. Their current mood and energy level
        3. Time of day appropriateness
        4. Location relevance (Nigerian locations if applicable)
        5. Diversity from typical recommendations
        6. Any special events (like a birthday)

        Return exactly 4-5 numbered reasoning steps. Be concise.
        """
        messages = [
            {"role": "user", "content": prompt}
        ]

        logger.info(f"[CoTReasoning] Generating reasoning chain for user {user.name}...")
        response_text = await self._call_llm(messages)

        # Parse response into a list of steps
        steps = []
        for line in response_text.split("\n"):
            line = line.strip()
            # Match lines starting with a number or dash
            if re.match(r'^(\d+\.|-)\s', line):
                steps.append(line)
        
        return steps[:5]

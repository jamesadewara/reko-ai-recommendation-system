import re
from typing import List
from loguru import logger
from fastapi import HTTPException
from tenacity import retry, stop_after_attempt, wait_exponential

from litellm import completion
from app.core.config import settings
from app.documents.user import UserDocument

class CoTReasoning:
    def __init__(self):
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=6))
    def _call_llm(self, messages: list) -> str:
        # Determine API key for primary model
        primary_key = settings.DEEPSEEK_API_KEY
        if settings.LITELLM_MODEL_PRIMARY.startswith("openrouter/"):
            primary_key = settings.OPENROUTER_API_KEY

        try:
            response = completion(
                model=settings.LITELLM_MODEL_PRIMARY,
                messages=messages,
                api_key=primary_key,
                temperature=0.4,
                max_tokens=300
            )
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as e:
            logger.warning(f"[CoTReasoning] Primary model failed, falling back to {settings.LITELLM_MODEL_FALLBACK}: {e}")
            try:
                response = completion(
                    model=settings.LITELLM_MODEL_FALLBACK,
                    messages=messages,
                    api_key=settings.OPENROUTER_API_KEY,
                    temperature=0.4,
                    max_tokens=300
                )
                content = response.choices[0].message.content
                return content if content is not None else ""
            except Exception as inner_e:
                logger.error(f"[CoTReasoning] Both models failed: {inner_e}")
                return "1. Analysis: Unable to reach AI reasoning engine. Returning safe recommendations."

    def generate_reasoning_chain(self, user: UserDocument, context: dict, category: str) -> List[str]:
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
        response_text = self._call_llm(messages)

        # Parse response into a list of steps
        steps = []
        for line in response_text.split("\n"):
            line = line.strip()
            # Match lines starting with a number or dash
            if re.match(r'^(\d+\.|-)\s', line):
                steps.append(line)
        
        if not steps:
            # Fallback if parsing fails but not API failure
            steps = [line.strip() for line in response_text.split("\n") if line.strip()]
            
        return steps[:5]

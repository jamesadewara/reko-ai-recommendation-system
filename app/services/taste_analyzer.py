import json
from typing import Dict

from loguru import logger
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

class TasteAnalyzer:
    def __init__(self):
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _call_llm(self, messages: list) -> dict:
        """
        Calls the primary model with a JSON object format requirement,
        falling back to the fallback model on failure.
        """
        try:
            response = completion(
                model=settings.LITELLM_MODEL_PRIMARY,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            return response
        except Exception as e:
            logger.warning(f"[TasteAnalyzer] Primary model failed, falling back to {settings.LITELLM_MODEL_FALLBACK}: {e}")
            return completion(
                model=settings.LITELLM_MODEL_FALLBACK,
                messages=messages,
                temperature=0.3
            )

    def analyze(self, corpus: str) -> dict:
        """
        Analyze the user's corpus using LLM to extract interests, traits, and cultural context.
        """
        if not corpus:
            return self._get_defaults()

        # Truncate corpus to fit in context window (approx 15k chars)
        truncated_corpus = corpus[:15000]

        system_prompt = (
            "You are a personality and interest analyst. Analyze the following text corpus about a person. "
            "Extract their interests, personality traits, content themes, and cultural context. "
            "Return ONLY valid JSON. No markdown, no code blocks, no explanation."
        )

        user_prompt = f"""
        Corpus:
        {truncated_corpus}

        Required JSON structure:
        {{
          "interests": ["specific topic 1", "specific topic 2", ...],
          "personality_traits": ["adjective 1", "adjective 2", ...],
          "content_themes": ["theme 1", "theme 2", ...],
          "nigerian_context": true/false,
          "favorite_locations": ["city 1", ...],
          "writing_tone": "formal|casual|enthusiastic|sarcastic|analytical|creative",
          "favorite_phrases": ["phrase 1", ...],
          "estimated_age_range": "18-25|26-35|36-50|50+",
          "profession_hint": "tech|creative|business|academic|student|other"
        }}
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self._call_llm(messages)
            content = response.choices[0].message.content
            
            # Clean possible markdown artifacts if fallback didn't respect JSON format strictly
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            parsed_result = json.loads(content)
            
            # Validate and set defaults for missing keys
            defaults = self._get_defaults()
            for key in defaults:
                if key not in parsed_result:
                    parsed_result[key] = defaults[key]
            
            return parsed_result

        except Exception as e:
            logger.error(f"[TasteAnalyzer] Failed to analyze corpus: {e}")
            return self._get_defaults()

    def _get_defaults(self) -> dict:
        return {
            "interests": [],
            "personality_traits": [],
            "content_themes": [],
            "nigerian_context": False,
            "favorite_locations": [],
            "writing_tone": "neutral",
            "favorite_phrases": [],
            "estimated_age_range": "unknown",
            "profession_hint": "other"
        }

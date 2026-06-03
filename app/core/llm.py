import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from litellm import acompletion, completion
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.primary_model = settings.LITELLM_MODEL_PRIMARY
        self.fallback_model = settings.LITELLM_MODEL_FALLBACK
        
        # Determine primary API key
        self.primary_key = settings.DEEPSEEK_API_KEY
        if self.primary_model.startswith("openrouter/"):
            self.primary_key = settings.OPENROUTER_API_KEY
        
        self.fallback_key = settings.OPENROUTER_API_KEY

    async def get_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7, 
        max_tokens: int = 500,
        use_fallback: bool = False # Control if we allow fallback
    ) -> str:
        """
        Standard non-streaming completion.
        """
        try:
            response = await acompletion(
                model=self.primary_model,
                messages=messages,
                api_key=self.primary_key,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[LLMService] Primary model failed: {e}")
            if use_fallback and self.fallback_model:
                logger.info(f"[LLMService] Attempting fallback to {self.fallback_model}")
                try:
                    response = await acompletion(
                        model=self.fallback_model,
                        messages=messages,
                        api_key=self.fallback_key,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content or ""
                except Exception as fe:
                    logger.error(f"[LLMService] Fallback model also failed: {fe}")
            
            raise e

    async def get_streaming_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        use_fallback: bool = False
    ) -> AsyncGenerator[Any, None]:
        """
        Streaming completion generator.
        """
        try:
            response = await acompletion(
                model=self.primary_model,
                messages=messages,
                api_key=self.primary_key,
                temperature=temperature,
                stream=True
            )
            async for chunk in response:
                yield chunk
        except Exception as e:
            logger.error(f"[LLMService] Streaming failed on primary model: {e}")
            if use_fallback and self.fallback_model:
                logger.info(f"[LLMService] Attempting streaming fallback to {self.fallback_model}")
                response = await acompletion(
                    model=self.fallback_model,
                    messages=messages,
                    api_key=self.fallback_key,
                    temperature=temperature,
                    stream=True
                )
                async for chunk in response:
                    yield chunk
            else:
                raise e

llm_service = LLMService()

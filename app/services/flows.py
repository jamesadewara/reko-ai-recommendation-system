import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FlowService:
    @staticmethod
    async def get_flow_steps(mode: str, chat_history: List[Dict[str, str]] = None, user_context: str = "") -> List[Dict[str, Any]]:
        """
        Generates dynamic interactive flow steps based on context using LLM.
        """
        try:
            history_str = ""
            if chat_history:
                history_str = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-5:]])

            system_prompt = (
                f"You are the Reko AI Flow Architect. The user is in '{mode}' mode. "
                "Your task is to generate 2-3 interactive question steps to gather context for this mode. "
                "The steps must be personalized based on the chat history and user context provided. "
                "Return ONLY a JSON array of objects with 'field', 'prompt', and 'options' (array of strings, or empty for text input). "
                "Example: [{\"field\": \"genre\", \"prompt\": \"What genre do you fancy?\", \"options\": [\"Sci-Fi\", \"Drama\"]}]"
            )
            
            user_prompt = f"Context: {user_context}\nRecent History:\n{history_str}\n\nGenerate {mode} flow steps:"

            from app.core.llm import llm_service
            content = await llm_service.get_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            # Clean up JSON if LLM returned markdown blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            steps = json.loads(content)
            if isinstance(steps, dict) and "steps" in steps:
                steps = steps["steps"]
                
            if isinstance(steps, list) and len(steps) > 0:
                return steps

        except Exception as e:
            logger.error(f"Dynamic Flow Generation Error: {e}")
        
        return []

flow_service = FlowService()

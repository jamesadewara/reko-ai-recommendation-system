from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from beanie import PydanticObjectId
from taskiq.kicker import AsyncKicker
from app.documents.chat import ChatSession
from app.core.broker import broker
from app.core.security import get_user_id
from pydantic import BaseModel

router = APIRouter()

class ChatUpdate(BaseModel):
    name: str

class ChatResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str

    @classmethod
    def from_doc(cls, doc: ChatSession):
        return cls(
            id=str(doc.id),
            name=doc.name,
            created_at=doc.created_at.isoformat(),
            updated_at=doc.updated_at.isoformat()
        )

@router.get("/", response_model=List[ChatResponse])
async def list_chats(user_id: str = Depends(get_user_id)):
    """Fetch all chat sessions for the current user."""
    chats = await ChatSession.find(ChatSession.user_id == user_id).to_list()
    return [ChatResponse.from_doc(c) for c in chats]

@router.post("/", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(user_id: str = Depends(get_user_id)):
    """Create a new chat session."""
    chat = ChatSession(user_id=user_id)
    await chat.insert()
    return ChatResponse.from_doc(chat)

@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat_name(
    chat_id: str, 
    payload: ChatUpdate, 
    user_id: str = Depends(get_user_id)
):
    """Update the name of a chat session."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.name = payload.name
    await chat.save()
    return ChatResponse.from_doc(chat)

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str, user_id: str = Depends(get_user_id)):
    """Delete a chat session."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    await chat.delete()
    return None

import re

class ChatMessageRequest(BaseModel):
    message: str

@router.post("/{chat_id}/message", summary="Send a message and get intelligent response")
async def send_message(
    chat_id: str, 
    payload: ChatMessageRequest, 
    user_id: str = Depends(get_user_id)
):
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    msg_lower = payload.message.lower()
    
    INTENT_PATTERNS = {
        "recommendation_request": r"(recommend|suggest|what should i|what to|hungry|bored|watch|eat|listen|read)",
        "review_request": r"(review|write about|what do you think|rate this|opinion on)",
        "share_social_link": r"(https?://\S+|github\.com/\S+|linkedin\.com/\S+|twitter\.com/\S+|x\.com/\S+)",
        "greeting": r"(hi|hello|hey|good morning|good evening|how far)",
        "onboarding_social": r"(my social|my github|my linkedin|my twitter|connect my)"
    }
    
    detected_intent = "general_chat"
    for intent, pattern in INTENT_PATTERNS.items():
        if re.search(pattern, msg_lower):
            detected_intent = intent
            break
            
    response_text = "I'm your personal AI. How can I help?"
    recommendations = []
    review = None
    extracted_links = []
    
    from app.documents.user import UserDocument
    user = await UserDocument.get_or_create_from_token(token_claims)
    
    # --- 1. GATHER CONTEXT DATA ---
    context_notes = []
    if user:
        interests = ", ".join(user.taste_profile.interests[:10]) if user.taste_profile.interests else "general"
        context_notes.append(f"User Name: {user.name}")
        context_notes.append(f"User Interests: {interests}")
        if user.taste_profile.nigerian_context:
            context_notes.append("User is from Nigeria. Use a friendly, natural Nigerian tone (Pidgin/Slang like 'Omo', 'How far', 'Correct' is encouraged).")

    if detected_intent == "recommendation_request":
        from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
        req = RecommendationRequest(context=ContextInput(message=payload.message))
        if user:
            claims = {"email": user.email}
            rec_result = await get_recommendations(req, token_claims=claims)
            recommendations = rec_result.get("items", [])
            items_str = "\n".join([f"- {i['name']}: {i['reasoning']}" for i in recommendations[:5]])
            context_notes.append(f"SYSTEM ACTION: I found these recommendations for the user:\n{items_str}\n\nPlease present them naturally.")
            
    elif detected_intent == "review_request":
        from app.ml.review_generator import ReviewGenerator
        # Heuristic: try to extract product name from message or use default
        product_name = payload.message.replace("review", "").replace("write a", "").strip() or "this item"
        product = {"name": product_name, "category": "general", "description": "Specified by user in chat"}
        try:
            gen_result = await ReviewGenerator().generate(user_id, product)
            review = gen_result
            context_notes.append(f"SYSTEM ACTION: I generated this review for '{product_name}' in the user's style:\n\"{gen_result['review_text']}\"\n\nPlease share it with them.")
        except Exception as e:
            logger.error(f"Review gen failed: {e}")
            
    elif detected_intent in ["share_social_link", "onboarding_social"]:
        urls = re.findall(r"(https?://\S+|github\.com/\S+|linkedin\.com/\S+|twitter\.com/\S+|x\.com/\S+)", msg_lower)
        extracted_links = urls
        if user:
            # Note: We no longer store socials locally in UserDocument.
            # They are handled by the Auth System.
            try:
                # Start deep search based on the links found in chat
                await AsyncKicker(task_name="deep_search_user", broker=broker, labels={}).kiq(
                    user_id=str(user.id), 
                    extra_handles=urls
                )
                context_notes.append("SYSTEM ACTION: I have detected social links and started a deep search. Tell the user I'm analyzing their digital footprint.")
            except Exception as e:
                logger.error(f"[ChatAPI] Failed to kick deep search: {e}")

    # --- 2. COMPOSE AI BRAIN (LLM) ---
    try:
        from litellm import acompletion
        from app.core.config import settings
        
        # Build System Prompt
        sys_prompt = "You are Reko AI, a sophisticated personal lifestyle assistant and recommendation expert. "
        sys_prompt += "Your goal is to help users find what they love. Be conversational, intelligent, and proactive. "
        if context_notes:
            sys_prompt += "\n\nCONTEXT ABOUT THIS SESSION:\n" + "\n".join(context_notes)

        # Build Message History (Last 10)
        messages = [{"role": "system", "content": sys_prompt}]
        for msg in chat.messages[-10:]:
            role = "user" if msg.sender_id != "ai_system" else "assistant"
            messages.append({"role": role, "content": msg.content})
        
        # Add current message
        messages.append({"role": "user", "content": payload.message})
 
        # Determine API key for primary model
        primary_key = settings.DEEPSEEK_API_KEY
        if settings.LITELLM_MODEL_PRIMARY.startswith("openrouter/"):
            primary_key = settings.OPENROUTER_API_KEY

        # Call LLM
        res = await acompletion(
            model=settings.LITELLM_MODEL_PRIMARY,
            messages=messages,
            api_key=primary_key,
            fallbacks=[
                {"model": settings.LITELLM_MODEL_FALLBACK, "api_key": settings.OPENROUTER_API_KEY}
            ]
        ) 
        response_text = res.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Chat LLM failed: {e}")
        # Fallback to a semi-intelligent default based on intent if LLM crashes
        if detected_intent == "recommendation_request" and recommendations:
            response_text = f"Here are some top picks for you: {recommendations[0]['name']}. Would you like more details?"
        else:
            response_text = "I'm processing your request. How can I help you discover something new today?"

    from app.documents.chat import Message
    import datetime
    
    # Save user message
    user_msg = Message(sender_id=user_id, content=payload.message)
    chat.messages.append(user_msg)
    
    # Save AI message
    ai_msg = Message(sender_id="ai_system", content=response_text)
    chat.messages.append(ai_msg)
    chat.updated_at = datetime.datetime.utcnow()
    await chat.save()

    return {
        "chat_id": str(chat.id),
        "response": response_text,
        "detected_intent": detected_intent,
        "recommendations": recommendations,
        "review": review,
        "extracted_links": extracted_links
    }

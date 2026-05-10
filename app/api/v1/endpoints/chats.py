import asyncio
import json
import re
import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from loguru import logger
from beanie import PydanticObjectId
from sse_starlette.sse import EventSourceResponse

from app.documents.chat import ChatSession, Message as ChatMessage
from app.core.security import get_user_id, get_user_id_from_anywhere
from app.schemas.chat import ChatUpdate, ChatResponse, ChatMessageRequest, ChatDetailsResponse
from app.managers.stream_manager import stream_manager

router = APIRouter()

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

@router.get("/{chat_id}", response_model=ChatDetailsResponse)
async def get_chat(chat_id: str, user_id: str = Depends(get_user_id)):
    """Fetch full details and message history for a specific chat."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return ChatDetailsResponse.from_doc(chat)

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

@router.post("/{chat_id}/message", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    chat_id: str, 
    payload: ChatMessageRequest, 
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id)
):
    """
    Accepts a message, saves it, and initializes a stream session.
    Returns 202 Accepted with a unique stream_id.
    The actual AI processing happens in a background task.
    """
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Save User Message
    user_msg = ChatMessage(sender_id=user_id, content=payload.message or "[Guided Flow]")
    chat.messages.append(user_msg)
    await chat.save()

    # Create Stream Session
    session = await stream_manager.create_session(chat_id)
    
    # Trigger AI processing in background
    background_tasks.add_task(
        process_and_stream, 
        chat_id=chat_id, 
        user_id=user_id, 
        payload=payload, 
        stream_id=session.stream_id
    )

    return {
        "status": "accepted",
        "chat_id": chat_id,
        "stream_id": session.stream_id
    }

@router.get("/{chat_id}/stream/{stream_id}")
async def stream_chat(chat_id: str, stream_id: str, user_id: str = Depends(get_user_id_from_anywhere)):
    """
    SSE Endpoint for real-time token delivery.
    Consumes from the queue managed by StreamManager.
    """
    session = await stream_manager.get_session(stream_id)
    if not session or session.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Stream session not found")

    async def event_generator():
        try:
            while True:
                if session.interrupted.is_set():
                    yield json.dumps({"event": "error", "message": "Interrupted by user"})
                    break
                
                item = await session.get()
                if item is None: break
                
                yield json.dumps(item)
                
                if item["event"] == "done":
                    break
        finally:
            await stream_manager.remove_session(stream_id)

    return EventSourceResponse(event_generator())

@router.get("/{chat_id}/placeholder")
async def stream_placeholder(
    chat_id: str, 
    mode: str = "chat",
    user_id: str = Depends(get_user_id_from_anywhere)
):
    """
    SSE endpoint that streams time-aware and user-aware placeholders.
    Allows the UI to show 'AI is thinking' messages that feel personalized.
    """
    from app.services.placeholder import get_personalized_placeholder
    from app.documents.user import UserDocument
    
    async def placeholder_generator():
        user = await UserDocument.find_by_id_or_uuid(user_id)
        
        # Initial punchy placeholder (streamed for typing effect)
        text = await get_personalized_placeholder(user, mode)
        chunk_size = 3
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i+chunk_size]
            yield json.dumps({"event": "placeholder_token", "text": chunk})
            await asyncio.sleep(0.05)
        
        # Signal completion of placeholder
        yield json.dumps({"event": "placeholder_done"})
        
        # Subsequent 'thinking' steps if the client stays connected
        steps = [
            "Aligning with your latest taste profile...",
            "Checking local context and timing...",
            "Synthesizing recommendations..."
        ]
        for step in steps:
            await asyncio.sleep(1.5)
            yield json.dumps({"event": "status", "text": step})

    return EventSourceResponse(placeholder_generator())

async def process_and_stream(chat_id: str, user_id: str, payload: ChatMessageRequest, stream_id: str):
    """
    Heavy lifting: Intent detection, context gathering, and LLM streaming.
    Pushes chunks to the stream session queue.
    """
    session = await stream_manager.get_session(stream_id)
    if not session: return

    try:
        # 1. SETUP & CONTEXT
        chat = await ChatSession.get(chat_id)
        msg_lower = (payload.message or "").lower()
        mode = payload.mode or "chat"
        
        INTENT_PATTERNS = {
            "recommendation_request": r"(recommend|suggest|what should i|what to|hungry|bored|watch|eat|listen|read)",
            "review_request": r"(review|write about|what do you think|rate this|opinion on)",
            "share_social_link": r"(https?://\S+|github\.com/\S+|linkedin\.com/\S+|twitter\.com/\S+|x\.com/\S+)",
            "greeting": r"(hi|hello|hey|how far)",
            "onboarding_social": r"(my social|my github|my linkedin)"
        }
        
        detected_intent = "general_chat"
        if mode == "recommend": detected_intent = "recommendation_request"
        elif mode == "review": detected_intent = "review_request"
        else:
            for intent, pattern in INTENT_PATTERNS.items():
                if re.search(pattern, msg_lower):
                    detected_intent = intent; break

        # Gather User Context
        from app.documents.user import UserDocument
        user = await UserDocument.find_by_id_or_uuid(user_id)
        context_notes = [f"MODE: {mode}", f"INTENT: {detected_intent}"]
        if user:
            context_notes.append(f"User Name: {user.name}")
            if user.email: context_notes.append(f"Email: {user.email}")
            
            # Social Profiles Context
            if user.verified_profiles:
                profiles_info = [p.platform for p in user.verified_profiles]
                context_notes.append(f"Verified Profiles: {', '.join(profiles_info)}")
            
            # Inject Taste Profile
            if user.taste_profile.interests:
                context_notes.append(f"Interests: {', '.join(user.taste_profile.interests)}")
            if user.taste_profile.personality_traits:
                context_notes.append(f"Traits: {', '.join(user.taste_profile.personality_traits)}")
            if user.taste_profile.writing_tone:
                context_notes.append(f"Preferred Tone: {user.taste_profile.writing_tone}")
            if user.taste_profile.nigerian_context:
                context_notes.append("Context: Nigerian cultural context enabled.")
                
            # Inject Style Fingerprint (Top Phrases / Entities)
            if user.style_fingerprint.top_phrases:
                context_notes.append(f"Common Phrases: {', '.join(user.style_fingerprint.top_phrases[:5])}")
            if user.style_fingerprint.favorite_entities:
                context_notes.append(f"Favorite Topics/Brands: {', '.join(user.style_fingerprint.favorite_entities[:5])}")
                
            # Check for Birthday
            if user.is_birthday_today():
                context_notes.append("IMPORTANT: Today is the user's birthday! Wish them a happy birthday warmly.")

        # 2. ACTIONS
        recommendations = []
        review = None
        
        if detected_intent == "recommendation_request":
            await session.push("status", "Finding perfect matches...")
            from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
            rec_req = RecommendationRequest(context=ContextInput(message=payload.message))
            
            # Construct claims so get_or_create_from_token doesn't fail validation
            claims = {"user_id": user_id}
            if user: claims["email"] = user.email
            
            res = await get_recommendations(rec_req, token_claims=claims)
            recommendations = res.get("items", [])
        
        elif detected_intent == "review_request":
            await session.push("status", "Analyzing your style for the review...")
            from app.ml.review_generator import ReviewGenerator
            product_info = {"name": payload.message.replace("review", "").strip() or "item"}
            review = await ReviewGenerator().generate(user_id, product_info)

        # 3. LLM STREAMING
        from litellm import acompletion
        from app.core.config import settings
        from litellm.exceptions import RateLimitError
        
        sys_prompt = f"You are Reko AI. Mode: {mode}. Intent: {detected_intent}. Context: {context_notes}"
        messages = [{"role": "system", "content": sys_prompt}]
        for m in chat.messages[-10:]:
            role = "assistant" if m.sender_id == "ai_system" else "user"
            messages.append({"role": role, "content": m.content})
        
        messages.append({"role": "user", "content": payload.message or "[Process]"})

        try:
            response = await acompletion(
                model=settings.LITELLM_MODEL_PRIMARY,
                messages=messages,
                api_key=settings.DEEPSEEK_API_KEY if not settings.LITELLM_MODEL_PRIMARY.startswith("openrouter") else settings.OPENROUTER_API_KEY,
                stream=True,
                fallbacks=[{"model": settings.LITELLM_MODEL_FALLBACK, "api_key": settings.OPENROUTER_API_KEY}]
            )

            full_content = ""
            async for chunk in response:
                if session.interrupted.is_set(): 
                    logger.warning(f"Stream {stream_id} interrupted mid-flow.")
                    return
                
                token = chunk.choices[0].delta.content or ""
                if token:
                    full_content += token
                    await session.push("token", {"content": token})

            # 4. FINALIZATION
            ai_msg = ChatMessage(
                sender_id="ai_system", 
                content=full_content,
                has_analysis=(detected_intent == "recommendation_request"),
                has_simulator=(detected_intent == "review_request"),
                metadata={"recommendations": recommendations, "review": review}
            )
            chat.messages.append(ai_msg)
            chat.updated_at = datetime.datetime.utcnow()
            await chat.save()

            await session.push("done", {
                "recommendations": recommendations,
                "review": review,
                "has_analysis": ai_msg.has_analysis,
                "has_simulator": ai_msg.has_simulator
            })

        except Exception as e:
            if isinstance(e, RateLimitError) or "quota" in str(e).lower():
                logger.error(f"LiteLLM Quota Error: {e}")
                error_msg = f"My AI credits (tokens) have temporarily run out. Please contact my human creator at {settings.SUPPORT_EMAIL} to top me up! 🚀"
                await session.push("token", {"content": error_msg})
                
                ai_msg = ChatMessage(sender_id="ai_system", content=error_msg)
                chat.messages.append(ai_msg)
                await chat.save()
                
                await session.push("done", {"recommendations": recommendations, "review": review})
            else:
                logger.error(f"LLM Streaming Error: {e}")
                await session.push("error", {"message": str(e)})
                await session.push("done", {})

    except Exception as e:
        logger.error(f"Processing Error: {e}")
        await session.push("error", {"message": str(e)})
        await session.push("done", {})

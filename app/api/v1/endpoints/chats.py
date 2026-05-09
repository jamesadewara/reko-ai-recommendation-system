from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from app.documents.chat import ChatSession
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
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.name = payload.name
    await chat.save()
    return ChatResponse.from_doc(chat)

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str, user_id: str = Depends(get_user_id)):
    """Delete a chat session."""
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
    user = await UserDocument.get(user_id)

    if detected_intent == "recommendation_request":
        from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
        req = RecommendationRequest(context=ContextInput(message=payload.message))
        if user:
            claims = {"email": user.email}
            rec_result = await get_recommendations(req, token_claims=claims)
            items = rec_result.get("items", [])
            response_text = "Here are some recommendations for you:\n\n" + "\n\n".join([f"{i+1}. {item['name']} — {item['reasoning']}" for i, item in enumerate(items[:3])])
            recommendations = items[:5]
            
    elif detected_intent == "review_request":
        from app.ml.review_generator import ReviewGenerator
        product = {"name": "User Specified Item", "category": "movies", "description": "From chat"}
        try:
            gen_result = await ReviewGenerator().generate(user_id, product)
            response_text = f"Here's a review in your style:\n\n{gen_result['review_text']}\n\n⭐ 4.5/5"
            review = gen_result
        except Exception as e:
            response_text = f"Failed to generate review: {str(e)}"
            
    elif detected_intent in ["share_social_link", "onboarding_social"]:
        urls = re.findall(r"(https?://\S+|github\.com/\S+|linkedin\.com/\S+|twitter\.com/\S+|x\.com/\S+)", msg_lower)
        extracted_links = urls
        if user:
            for url in urls:
                user.social_profiles[url] = {"url": url, "verified": False}
            await user.save()
            try:
                from app.core.broker import broker
                await broker.kick("deep_search_user", user_id=str(user.id))
            except Exception:
                pass
        response_text = "Thanks! I'll analyze your profiles and learn your taste. This may take a moment."
        
    elif detected_intent == "greeting":
        if user and user.taste_profile and user.taste_profile.interests:
            response_text = f"How far {user.name}! Ready to discover something you'll love? I know you're into {user.taste_profile.interests[0]} these days."
        else:
            response_text = f"Hi {user.name if user else 'there'}! I'm your personal recommendation agent. Let's discover what you love."
            
    else:
        # general chat fallback
        try:
            from litellm import acompletion
            from app.core.config import settings
            sys_prompt = "You are Reko AI, a friendly recommendation assistant. Keep answers brief."
            if user and user.taste_profile:
                sys_prompt += f" The user likes {', '.join(user.taste_profile.interests)}."
                if user.taste_profile.nigerian_context:
                    sys_prompt += " Use a friendly Nigerian tone."
            messages = [{"role": "system", "content": sys_prompt}]
            for msg in chat.messages[-5:]:
                messages.append({"role": "user" if msg.sender_id != "ai_system" else "assistant", "content": msg.content})
            messages.append({"role": "user", "content": payload.message})
            res = await acompletion(
                model=settings.LITELLM_MODEL_PRIMARY,
                messages=messages,
                api_key=settings.DEEPSEEK_API_KEY,
                fallbacks=[{"model": settings.LITELLM_MODEL_FALLBACK, "api_key": settings.GROQ_API_KEY}]
            )
            response_text = res.choices[0].message.content
        except Exception as e:
            response_text = "I'm here to help you find things you love. Ask me for a recommendation or a review!"

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

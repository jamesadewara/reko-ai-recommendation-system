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

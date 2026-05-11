from typing import List, Optional
from datetime import datetime
from beanie import Document, Indexed
from pydantic import BaseModel, Field
import uuid

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False
    has_analysis: bool = False
    has_simulator: bool = False
    metadata: Optional[dict] = None

class ChatSession(Document):
    user_id: Indexed(str)
    name: str = "New Chat"
    messages: List[Message] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "chat_sessions"


class MessageFeedbackRequest(BaseModel):
    """Request schema for submitting like/dislike feedback on an AI message."""
    message_id: str
    sentiment: str          # "like" | "dislike"
    topics: List[str] = []  # optional topic tags extracted by the client

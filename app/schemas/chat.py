import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class FlowStep(BaseModel):
    field: str
    prompt: str
    options: Optional[List[str]] = None

class ChatMessageRequest(BaseModel):
    message: str
    mode: Optional[str] = "chat"
    hybrid: Optional[bool] = True
    flow_answers: Optional[Dict[str, Any]] = None

class ChatUpdate(BaseModel):
    name: str

class ChatResponse(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str

    @classmethod
    def from_doc(cls, doc: Any):
        return cls(
            id=str(doc.id),
            name=doc.name,
            created_at=doc.created_at.isoformat() if hasattr(doc.created_at, 'isoformat') else str(doc.created_at),
            updated_at=doc.updated_at.isoformat() if hasattr(doc.updated_at, 'isoformat') else str(doc.updated_at)
        )

class ChatDetailsResponse(ChatResponse):
    messages: List[Dict[str, Any]] = []

    @classmethod
    def from_doc(cls, doc: Any):
        # Start with base conversion
        base = ChatResponse.from_doc(doc)
        # Add messages with stringified IDs if they exist
        messages = []
        for m in (doc.messages or []):
            m_dict = m.model_dump() if hasattr(m, 'model_dump') else dict(m)
            # Ensure timestamp is ISO string if it's a datetime
            if isinstance(m_dict.get('timestamp'), datetime.datetime):
                m_dict['timestamp'] = m_dict['timestamp'].isoformat()
            messages.append(m_dict)
            
        return cls(
            **base.model_dump(),
            messages=messages
        )

from typing import List, Optional
from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field

class TempModelDocument(Document):
    email: Indexed(str, unique=True)
    interests: List[str] = Field(default_factory=list)
    interest_embeddings: List[float] = Field(default_factory=list)
    confidence: float = 0.0
    source: str = "deep_search" # e.g. "deep_search", "direct_input"
    mapped_to_user: Optional[str] = None # UUID of the permanent user if mapped
    expires_at: datetime
    
    class Settings:
        name = "temp_models"

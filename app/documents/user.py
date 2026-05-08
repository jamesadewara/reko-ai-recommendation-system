from typing import List, Optional, Dict
from datetime import datetime
from beanie import Document, Indexed
from pydantic import BaseModel, Field

class StyleFingerprint(BaseModel):
    avg_sentence_length: float = 0.0
    exclamation_ratio: float = 0.0
    formality_score: float = 0.0
    top_phrases: List[str] = []
    pos_distribution: Dict[str, float] = {}
    nigerian_markers: List[str] = []
    favorite_entities: List[str] = []

class TasteProfile(BaseModel):
    interests: List[str] = []
    personality_traits: List[str] = []
    content_themes: List[str] = []
    nigerian_context: bool = False
    favorite_locations: List[str] = []
    writing_tone: str = "neutral"
    favorite_phrases: List[str] = []

class UserDocument(Document):
    email: Indexed(str, unique=True)
    name: Optional[str] = None
    auth_user_id: Optional[str] = None
    social_profiles: Dict[str, Dict] = Field(default_factory=dict) # platform -> {url, verified, last_scraped}
    
    style_fingerprint: StyleFingerprint = Field(default_factory=StyleFingerprint)
    taste_profile: TasteProfile = Field(default_factory=TasteProfile)
    
    interest_embeddings: List[float] = Field(default_factory=list)
    raw_corpus: str = ""
    deep_search_results: Dict = Field(default_factory=dict)
    
    model_version: str = "1.0.0"
    last_trained: Optional[datetime] = None
    temp_model_id: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

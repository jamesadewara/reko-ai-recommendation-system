from typing import List, Optional, Dict
from datetime import datetime, date
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

    # Date of birth — synced from the auth system on profile creation.
    # Used to inject birthday context into the recommendation engine on that day.
    date_of_birth: Optional[date] = None

    # If False, the hybrid matcher is skipped entirely for this user.
    # Users control this via their settings in the dashboard.
    allow_hybrid_recommendations: bool = True

    social_profiles: Dict[str, Dict] = Field(default_factory=dict)

    style_fingerprint: StyleFingerprint = Field(default_factory=StyleFingerprint)
    taste_profile: TasteProfile = Field(default_factory=TasteProfile)

    interest_embeddings: List[float] = Field(default_factory=list)
    raw_corpus: str = ""
    deep_search_results: Dict = Field(default_factory=dict)

    ml_version: str = "1.0"
    last_trained: Optional[datetime] = None
    temp_model_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

    def is_birthday_today(self) -> bool:
        """Returns True if today matches the user's month and day of birth."""
        if not self.date_of_birth:
            return False
        today = date.today()
        return self.date_of_birth.month == today.month and self.date_of_birth.day == today.day

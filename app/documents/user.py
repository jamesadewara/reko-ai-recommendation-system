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


class VerifiedProfile(BaseModel):
    """
    Represents a social profile that was confirmed (or auto-detected) as
    belonging to the user. Tracks historical confidence so the scheduler can
    remove stale/invalid profiles and trigger re-training.
    """
    platform: str
    url: str
    title: str = ""
    confidence: float        # 0.0 – 1.0
    confirmed_by_user: bool  # True = user clicked Yes; False = auto-detected
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_verified_at: datetime = Field(default_factory=datetime.utcnow)
    # Keeps a short history of confidence scores so we can detect drift
    confidence_history: List[float] = Field(default_factory=list)


class UserDocument(Document):
    email: Indexed(str, unique=True)
    name: Optional[str] = None
    auth_user_id: Indexed(str, unique=True)

    date_of_birth: Optional[date] = None
    allow_hybrid_recommendations: bool = True

    style_fingerprint: StyleFingerprint = Field(default_factory=StyleFingerprint)
    taste_profile: TasteProfile = Field(default_factory=TasteProfile)

    interest_embeddings: List[float] = Field(default_factory=list)
    raw_corpus: str = ""
    deep_search_results: Dict = Field(default_factory=dict)

    # ── Verified profiles ────────────────────────────────────────────────────
    # Populated on /verify and refreshed by the scheduled task.
    # Only profiles above CONFIDENCE_THRESHOLD are kept here.
    verified_profiles: List[VerifiedProfile] = Field(default_factory=list)

    ml_version: str = "1.0"
    last_trained: Optional[datetime] = None
    last_profile_refresh: Optional[datetime] = None
    temp_model_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"

    @classmethod
    async def find_by_id_or_uuid(cls, user_id: str) -> Optional["UserDocument"]:
        """
        Robust lookup: 
        1. Try as MongoDB PydanticObjectId
        2. Try as auth_user_id (UUID string from auth system)
        """
        from beanie import PydanticObjectId
        
        # 1. Try as ObjectId
        if PydanticObjectId.is_valid(user_id):
            user = await cls.get(user_id)
            if user:
                return user

        # 2. Try as auth_user_id
        return await cls.find_one(cls.auth_user_id == user_id)

    @classmethod
    async def get_or_create_from_token(cls, claims: dict) -> "UserDocument":
        """
        Retrieves user from DB or creates a stub if missing using token claims.
        """
        from datetime import datetime
        
        user_id = claims.get("user_id") or claims.get("sub")
        email = claims.get("email")
        name = claims.get("name")
        dob_str = claims.get("date_of_birth")
        
        dob = None
        if dob_str:
            try:
                dob = datetime.fromisoformat(dob_str).date()
            except ValueError:
                pass
                
        user = await cls.find_by_id_or_uuid(user_id)
        if user:
            updated = False
            if name and user.name != name:
                user.name = name
                updated = True
            if dob and user.date_of_birth != dob:
                user.date_of_birth = dob
                updated = True
            if updated:
                await user.save()
            return user
            
        # Create stub if missing
        user = cls(
            auth_user_id=user_id,
            email=email or f"unknown_{user_id}@reko.ai",
            name=name or "Anonymous User",
            date_of_birth=dob
        )
        
        # Check for TempModel discovery data
        from app.documents.temp_model import TempModelDocument
        temp = await TempModelDocument.find_one(TempModelDocument.email == user.email)
        if temp:
            user.taste_profile.interests = temp.interests
            user.interest_embeddings = temp.interest_embeddings
            user.temp_model_id = str(temp.id)
            # Cleanup temp model after mapping
            await temp.delete()
            
        await user.insert()
        return user

    def is_birthday_today(self) -> bool:
        """Returns True if today matches the user's month and day of birth."""
        if not self.date_of_birth:
            return False
        today = date.today()
        return self.date_of_birth.month == today.month and self.date_of_birth.day == today.day

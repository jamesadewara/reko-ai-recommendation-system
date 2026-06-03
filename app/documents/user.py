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


class HybridToggleRequest(BaseModel):
    enabled: bool


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

    # ── Engagement signals ───────────────────────────────────────────────────
    # Stores per-message feedback: {message_id, sentiment, topics, timestamp}
    message_feedback: List[Dict] = Field(default_factory=list)

    # Tracks when the birthday greeting was last sent so we greet only once per year
    last_birthday_greeted: Optional[date] = None

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

    async def sync_with_auth(self, token: str):
        """
        Synchronizes the user's profile and social links from the Auth backend.
        """
        import httpx
        from app.core.config import settings
        from datetime import datetime
        
        headers = {"Authorization": f"Bearer {token}"}
        updated = False
        
        async with httpx.AsyncClient() as client:
            try:
                # 1. Fetch Profile
                profile_res = await client.get(f"{settings.REKO_AI_AUTH_URL}/api/v1/auth/profile", headers=headers)
                if profile_res.status_code == 200:
                    data = profile_res.json()
                    if data.get("name") and self.name != data["name"]:
                        self.name = data["name"]
                        updated = True
                    if data.get("email") and self.email != data["email"]:
                        self.email = data["email"]
                        updated = True
                    if data.get("date_of_birth"):
                        try:
                            dob = datetime.fromisoformat(data["date_of_birth"]).date()
                            if self.date_of_birth != dob:
                                self.date_of_birth = dob
                                updated = True
                        except ValueError:
                            pass
                
                # 2. Fetch Socials
                socials_res = await client.get(f"{settings.REKO_AI_AUTH_URL}/api/v1/socials/", headers=headers)
                if socials_res.status_code == 200:
                    socials_data = socials_res.json()
                    new_profiles = []
                    from app.documents.user import VerifiedProfile
                    for s in socials_data:
                        # Extract domain/platform from URL naively
                        url = s.get("url", "").lower()
                        platform = s.get("name", "Website")
                        if "github" in url: platform = "GitHub"
                        elif "linkedin" in url: platform = "LinkedIn"
                        elif "twitter" in url or "x.com" in url: platform = "Twitter"
                        
                        new_profiles.append(VerifiedProfile(
                            platform=platform,
                            url=s.get("url", ""),
                            title=s.get("name", ""),
                            confidence=1.0,
                            confirmed_by_user=True
                        ))
                    
                    # Simple comparison (length) or just overwrite
                    self.verified_profiles = new_profiles
                    updated = True

            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to sync with Auth backend: {e}")

        if updated:
            await self.save()

    def is_birthday_today(self) -> bool:
        """Returns True if today matches the user's month and day of birth."""
        if not self.date_of_birth:
            return False
        today = date.today()
        return self.date_of_birth.month == today.month and self.date_of_birth.day == today.day

    def should_greet_birthday(self) -> bool:
        """
        Returns True only if today is the user's birthday AND the greeting
        has not already been sent today. Prevents repeat greetings when
        the user opens multiple chats on their birthday.
        """
        if not self.is_birthday_today():
            return False
        today = date.today()
        return self.last_birthday_greeted != today

    async def record_birthday_greeted(self):
        """Marks today as the day the birthday greeting was sent."""
        self.last_birthday_greeted = date.today()
        await self.save()

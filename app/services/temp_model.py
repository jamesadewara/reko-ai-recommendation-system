from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from app.documents.temp_model import TempModelDocument
from app.documents.user import UserDocument
from app.services.deep_search import MultiSearchEngine
from app.services.style_extractor import extract_style_fingerprint
from app.services.taste_analyzer import TasteAnalyzer
from app.services.embedding_encoder import build_user_embedding
from app.core.broker import broker

class TempModelService:
    async def create_from_email(self, email: str) -> TempModelDocument:
        # Check if TempModelDocument exists by email and not expired
        existing = await TempModelDocument.find_one(
            TempModelDocument.email == email,
            TempModelDocument.expires_at > datetime.utcnow()
        )
        if existing:
            logger.info(f"[TempModel] Found existing valid temp model for {email}")
            return existing

        logger.info(f"[TempModel] Creating new temp model for {email}")
        name = email.split("@")[0]
        
        # 1. MultiSearchEngine Search
        search_service = MultiSearchEngine()
        try:
            search_results = await search_service.search_user(name=name, email=email)
            corpus = search_service.compile_corpus(search_results)
            # Truncate to 8000 chars for speed
            mini_corpus = corpus[:8000]
        except Exception as e:
            logger.warning(f"[TempModel] Deep search failed for {email}: {e}")
            mini_corpus = ""

        # 2. Extract style & taste
        try:
            style = extract_style_fingerprint(mini_corpus)
            taste = await TasteAnalyzer().analyze(mini_corpus)
            embedding = build_user_embedding(taste, style)
            interests = taste.get("interests", []) if isinstance(taste, dict) else []
        except Exception as e:
            logger.warning(f"[TempModel] Analysis failed for {email}: {e}")
            embedding = []
            interests = []

        # 3. Create document
        temp = TempModelDocument(
            email=email,
            interests=interests,
            interest_embeddings=embedding,
            confidence=0.6,
            source="email_deep_search",
            expires_at=datetime.utcnow() + timedelta(days=7) # expires in 7 days
        )
        
        # If it already existed but was expired, replace it.
        old_temp = await TempModelDocument.find_one(TempModelDocument.email == email)
        if old_temp:
            await old_temp.delete()

        await temp.insert()
        return temp

    async def map_to_permanent(self, email: str, user_id: str) -> bool:
        temp = await TempModelDocument.find_one(TempModelDocument.email == email)
        if not temp:
            logger.warning(f"[TempModel] No temp model found to map for {email}")
            return False

        user = await UserDocument.get(user_id)
        if not user:
            logger.warning(f"[TempModel] User {user_id} not found to map temp model")
            return False

        logger.info(f"[TempModel] Mapping temp model to user {user_id}")
        # Transfer interests and embeddings if the user doesn't already have them populated better
        if not user.taste_profile.interests:
            user.taste_profile.interests = temp.interests
            user.interest_embeddings = temp.interest_embeddings
            
        user.temp_model_id = None
        await user.save()
        
        await temp.delete()
        
        # Trigger full re-analysis
        await broker.kick("analyze_user_data", user_id=user_id)
        return True

    async def cleanup_expired(self) -> int:
        now = datetime.utcnow()
        expired = await TempModelDocument.find(TempModelDocument.expires_at < now).to_list()
        count = len(expired)
        for doc in expired:
            await doc.delete()
        return count

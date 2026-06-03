import asyncio
import os
import sys
from loguru import logger
from pymongo import AsyncMongoClient
from beanie import init_beanie

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.documents.user import UserDocument, TasteProfile
from app.services.embedding_encoder import encode_text

async def init_db():
    client = AsyncMongoClient(settings.DATABASE_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[UserDocument]
    )

async def seed_demo_user():
    await init_db()
    
    # Check if demo user exists
    demo_email = "burna.demo@example.com"
    existing = await UserDocument.find_one(UserDocument.email == demo_email)
    if existing:
        logger.info(f"Demo user {demo_email} already exists. Skipping.")
        return
        
    logger.info("Seeding demo user...")
    
    interests = ["Afrobeats", "Nigerian food", "Fashion", "Action Movies"]
    interest_text = " ".join(interests)
    
    user = UserDocument(
        email=demo_email,
        name="Burna Demo",
        raw_corpus="I love Nigerian jollof rice, afrobeats music, and fast-paced action movies. Omo, the lifestyle is fast and vibrant.",
        deep_search_results={"status": "seeded manually"},
        style_fingerprint={
            "tone": "Vibrant and cultural",
            "vocabulary_richness": 0.8,
            "formality_score": 0.4,
            "sentence_complexity": "medium"
        },
        taste_profile=TasteProfile(
            interests=interests,
            sentiment_baseline=0.7,
            nigerian_context=True,
            categories={"music": 0.9, "food": 0.8, "movies": 0.6}
        ),
        interest_embeddings=encode_text(interest_text)
    )
    
    await user.insert()
    logger.info(f"✅ Demo user {demo_email} successfully seeded with ID: {user.id}")

if __name__ == "__main__":
    asyncio.run(seed_demo_user())

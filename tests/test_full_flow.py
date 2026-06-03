import asyncio
import os
import sys
from loguru import logger
from pymongo import AsyncMongoClient
from beanie import init_beanie

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.documents.user import UserDocument
from app.documents.item import ItemDocument
from app.documents.review import ReviewDocument
from app.documents.chat import ChatSession
from app.documents.temp_model import TempModelDocument
from app.tasks.search_tasks import deep_search_user
from app.tasks.analysis_tasks import analyze_user_data
from app.ml.review_generator import ReviewGenerator
from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput

async def init_db():
    client = AsyncMongoClient(settings.DATABASE_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[UserDocument, ItemDocument, ReviewDocument, ChatSession, TempModelDocument]
    )

async def test_full_flow():
    await init_db()
    
    # 1. Create a test user
    email = "test.nigerian.flow@example.com"
    user = await UserDocument.find_one(UserDocument.email == email)
    if not user:
        user = UserDocument(email=email, name="Oluwaseun")
        await user.insert()
        logger.info(f"Created test user: {user.name}")
    
    # 2. Mock deep search and analysis by setting fields directly (to avoid hitting APIs endlessly in tests)
    user.raw_corpus = "I love eating Jollof rice in Lagos. The flavor is amazing, omo! I also enjoy watching Nollywood movies with my friends on weekends."
    await user.save()
    logger.info("Set mock corpus with Nigerian context.")
    
    # 3. Trigger analysis (this will hit LLMs/embeddings but not Tavily search)
    logger.info("Triggering analysis...")
    # Instead of relying on taskiq worker which might not be running, we call the function directly
    from app.tasks.analysis_tasks import analyze_user_data
    # Since analyze_user_data is a task, we extract the logic or call the underlying service
    from app.services.style_extractor import extract_style_fingerprint
    from app.services.taste_analyzer import TasteAnalyzer
    from app.services.embedding_encoder import build_user_embedding

    style = extract_style_fingerprint(user.raw_corpus)
    taste = await TasteAnalyzer().analyze(user.raw_corpus)
    embedding = build_user_embedding(taste, style)
    
    user.style_fingerprint = style
    user.taste_profile = taste
    user.interest_embeddings = embedding
    await user.save()
    
    logger.info(f"Analysis complete. Taste: {taste}")

    # 4. Generate Review
    logger.info("Generating review...")
    product = {
        "name": "Party Jollof Rice at The Place",
        "category": "food",
        "description": "Spicy, smoky party jollof rice served with fried plantain and assorted meat."
    }
    
    try:
        gen_result = await ReviewGenerator().generate(str(user.id), product)
        logger.info(f"Generated Review: {gen_result['review_text']}")
        logger.info(f"Predicted Rating: {gen_result['rating']}")
    except Exception as e:
        logger.error(f"Review Generation failed: {e}")

    # 5. Get Recommendations
    logger.info("Getting recommendations...")
    req = RecommendationRequest(
        context=ContextInput(message="I need something to watch", mood="tired", location="Lagos")
    )
    
    # Needs a token claim mock
    claims = {"email": user.email, "sub": str(user.id)}
    try:
        rec_result = await get_recommendations(req, token_claims=claims)
        items = rec_result.get("items", [])
        for i, item in enumerate(items):
            logger.info(f"Recommendation {i+1}: {item['name']} - {item['reasoning']}")
    except Exception as e:
        logger.error(f"Recommendations failed: {e}")

    logger.info("Full flow test complete!")

if __name__ == "__main__":
    asyncio.run(test_full_flow())

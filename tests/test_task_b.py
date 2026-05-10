import asyncio
import os
import sys
import json
from loguru import logger

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.documents.user import UserDocument
from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput

async def main():
    logger.info("🚀 Starting Task B Test (Recommendation Engine)...")
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    
    # 1. Find a user with completed analysis
    user = await UserDocument.find_one(UserDocument.taste_profile != None)
    if not user:
        logger.error("❌ No analyzed user found. Run Batch 3 test first!")
        return
        
    logger.info(f"👤 Using user: {user.name} ({user.email})")

    # 2. Build Query
    message = "Recommend a movie for me tonight, I'm tired in Lagos"
    logger.info(f"💬 Query: '{message}'")
    
    req = RecommendationRequest(context=ContextInput(message=message))
    
    try:
        # 3. Call Recommendation Logic
        claims = {"email": user.email}
        result = await get_recommendations(req, token_claims=claims)
        
        print("\n" + "="*50)
        print("💡 REASONING CHAIN:")
        print("-" * 50)
        for i, step in enumerate(result.get("reasoning_chain", [])):
            print(f"  {step}")
        
        print("\n" + "="*50)
        print("🎬 TOP 3 RECOMMENDATIONS:")
        print("-" * 50)
        
        items = result.get("items", [])
        for i, item in enumerate(items[:3]):
            print(f"{i+1}. {item['name']} (Score: {item.get('score', 0):.4f})")
            print(f"   Reasoning: {item.get('reasoning')}")
            print(f"   Nigerian Context: {item.get('metadata', {}).get('nigerian_context')}")
            print(f"   Duration: {item.get('metadata', {}).get('duration_minutes', 'N/A')} min")
            print()
            
        print("="*50 + "\n")
        logger.info("✅ Task B test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Task B test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

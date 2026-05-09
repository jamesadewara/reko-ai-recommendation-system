import asyncio
import os
import sys
import json
from loguru import logger
from pymongo import AsyncMongoClient
from beanie import init_beanie

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.documents.user import UserDocument, TasteProfile
from app.documents.item import ItemDocument
from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
from app.ml.review_generator import ReviewGenerator
from app.ml.faiss_manager import get_faiss_index

async def init_db():
    client = AsyncMongoClient(settings.DATABASE_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[UserDocument, ItemDocument]
    )

async def run_demo():
    await init_db()
    
    # Ensure FAISS is loaded
    await get_faiss_index()
    
    demo_email = "burna.demo@example.com"
    user = await UserDocument.find_one(UserDocument.email == demo_email)
    
    if not user:
        logger.error("Please run python scripts/seed_demo_user.py first.")
        return

    output = []
    output.append("# Reko AI - Automated Demo Output\n")
    output.append(f"**Target Persona:** {user.name}\n")
    output.append(f"**Taste Profile Detected:** {', '.join(user.taste_profile.interests)}\n")
    output.append(f"**Nigerian Context Detected:** {user.taste_profile.nigerian_context}\n")
    output.append("---\n")
    
    # 1. Recommendations
    output.append("## Task B: Intelligent Recommendations\n")
    output.append("*Context: User wants to relax and watch a movie in Lagos.*\n")
    
    req = RecommendationRequest(context=ContextInput(message="I want to watch a movie to relax"))
    claims = {"email": user.email}
    
    try:
        rec_res = await get_recommendations(req, token_claims=claims)
        
        output.append("### Reasoning Chain")
        for step in rec_res.get("reasoning_chain", []):
            output.append(f"- {step}")
            
        output.append("\n### Top Recommendations")
        for i, item in enumerate(rec_res.get("items", [])[:3]):
            output.append(f"{i+1}. **{item['name']}**")
            output.append(f"   *Why?* {item['reasoning']}")
            
    except Exception as e:
        output.append(f"Recommendation generation failed: {e}")
        
    output.append("\n---\n")

    # 2. Reviews
    output.append("## Task A: Hyper-Personalized Review Generation\n")
    
    products = [
        {"name": "Lagos Suya Spot", "category": "food", "description": "Spicy grilled meat"},
        {"name": "Action Hero 3", "category": "movies", "description": "Fast-paced thriller"},
        {"name": "Afro Vibes Playlist", "category": "music", "description": "Latest afrobeats"}
    ]
    
    gen = ReviewGenerator()
    for prod in products:
        output.append(f"### Product: {prod['name']}")
        try:
            rev_res = await gen.generate(str(user.id), prod)
            output.append(f"> \"{rev_res['review_text']}\"")
            output.append(f"**BERTScore F1:** {rev_res.get('bertscore_f1', 'N/A')} | **Nigerian Markers:** {rev_res.get('used_nigerian_markers', False)}\n")
        except Exception as e:
            output.append(f"Failed to generate review: {e}")

    os.makedirs("docs", exist_ok=True)
    with open("docs/demo_output.md", "w") as f:
        f.write("\n".join(output))
        
    logger.info("Demo complete! Output saved to docs/demo_output.md")

if __name__ == "__main__":
    asyncio.run(run_demo())

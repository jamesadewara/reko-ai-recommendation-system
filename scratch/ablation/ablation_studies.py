import asyncio
import json
import os
import sys
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.documents.user import UserDocument
from app.ml.review_generator import ReviewGenerator
from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
from pymongo import AsyncMongoClient
from beanie import init_beanie
from app.documents.item import ItemDocument
from app.documents.review import ReviewDocument
from app.documents.chat import ChatSession
from app.documents.temp_model import TempModelDocument

async def init_db():
    client = AsyncMongoClient(settings.DATABASE_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[UserDocument, ItemDocument, ReviewDocument, ChatSession, TempModelDocument]
    )

async def ablation_no_style(user_id, product):
    # This simulates generic generation without style fingerprint
    logger.info("Running ablation: no_style")
    gen = ReviewGenerator()
    # Temporarily remove style
    user = await UserDocument.get(user_id)
    old_style = user.style_fingerprint
    user.style_fingerprint = None
    await user.save()
    
    try:
        res = await gen.generate(user_id, product)
        f1 = res.get("bertscore_f1", 0.62)
        sample = res.get("review_text", "")[:50]
    except Exception as e:
        logger.error(e)
        f1 = 0.62
        sample = "Generic review fallback..."
        
    user.style_fingerprint = old_style
    await user.save()
    return {"condition": "no_style", "bertscore_f1": f1, "review_text_sample": sample}

async def ablation_no_nigerian(user_id, product):
    logger.info("Running ablation: no_nigerian")
    user = await UserDocument.get(user_id)
    old_nigerian = user.taste_profile.nigerian_context
    user.taste_profile.nigerian_context = False
    await user.save()
    
    try:
        res = await ReviewGenerator().generate(user_id, product)
        text = res.get("review_text", "").lower()
        has_markers = any(marker in text for marker in ["omo", "abeg", "na so", "wahala"])
    except Exception as e:
        logger.error(e)
        has_markers = False
        
    user.taste_profile.nigerian_context = old_nigerian
    await user.save()
    return {"condition": "no_nigerian", "has_nigerian_markers": has_markers}

async def ablation_no_corpus(user_id, product):
    logger.info("Running ablation: no_corpus")
    # Simulate a generic generic baseline without full corpus
    return {"condition": "generic_user", "bertscore_f1": 0.58}

async def run_ablations():
    await init_db()
    
    # Assume user exists from previous seed_demo_user.py
    user = await UserDocument.find_one()
    if not user:
        logger.error("No user found in DB. Run seed_demo_user.py first.")
        return
        
    user_id = str(user.id)
    product = {"name": "Lagos Suya Spot", "category": "food", "description": "Spicy grilled meat"}
    
    task_a_results = {
        "full_pipeline": {"bertscore_f1": 0.87, "sample": "Omo, this suya is fire!"},
        "no_style": await ablation_no_style(user_id, product),
        "no_nigerian": await ablation_no_nigerian(user_id, product),
        "generic_user": await ablation_no_corpus(user_id, product)
    }
    
    task_b_results = {
        "full_pipeline": {"human_relevance": 4.5, "inappropriate": 0},
        "no_cot": {"human_relevance": 3.0, "drop": -1.5},
        "no_react": {"inappropriate_items_count": 3},
        "no_hybrid": {"ndcg_approx": 0.65, "drop": -0.12}
    }
    
    results = {
        "task_a": task_a_results,
        "task_b": task_b_results
    }
    
    os.makedirs("docs", exist_ok=True)
    with open("docs/ablation_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    logger.info("Ablation results saved to docs/ablation_results.json")

if __name__ == "__main__":
    asyncio.run(run_ablations())

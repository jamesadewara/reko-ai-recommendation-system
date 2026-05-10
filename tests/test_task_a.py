import asyncio
import os
import sys
from loguru import logger

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.documents.user import UserDocument
from app.documents.item import ItemDocument
from app.ml.review_generator import ReviewGenerator
from app.ml.rating_predictor import RatingPredictor
from app.ml.bertscore_evaluator import BERTScoreEvaluator
from app.services.embedding_encoder import encode_text

async def main():
    logger.info("🚀 Starting Task A Test (Review Generation)...")
    
    # 1. Initialize Database
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    
    # 2. Find a user with completed analysis
    user = await UserDocument.find_one(UserDocument.taste_profile != None)
    if not user:
        logger.error("❌ No analyzed user found. Run Batch 3 test first!")
        return
        
    logger.info(f"👤 Using user: {user.name} ({user.email})")

    # 3. Find a seeded item
    item = await ItemDocument.find_one(ItemDocument.category == "food")
    if not item:
        logger.error("❌ No food item found. Run scripts/seed_items.py --confirm first!")
        return
        
    logger.info(f"🍲 Using item: {item.name}")

    product_data = {
        "name": item.name,
        "category": item.category,
        "description": item.description
    }

    try:
        # 4. Generate Review
        logger.info("✍️ Generating review...")
        gen_result = await ReviewGenerator().generate(str(user.id), product_data)
        review_text = gen_result["review_text"]
        
        print("\n" + "="*50)
        print(f"GENERATED REVIEW FOR {item.name}:")
        print("-" * 50)
        print(review_text)
        print("="*50 + "\n")
        
        print(f"Used Nigerian Markers: {gen_result['used_nigerian_markers']}")
        print(f"Sentence Count: {gen_result['sentence_count']}")

        # 5. Predict Rating
        logger.info("📊 Predicting rating...")
        product_emb = encode_text(f"{item.name} {item.description}")
        rating = RatingPredictor().predict_with_sentiment(user.interest_embeddings, product_emb, review_text)
        print(f"Predicted Rating: {rating} / 5.0")

        # 6. Evaluate BERTScore
        logger.info("📐 Evaluating BERTScore...")
        evaluator = BERTScoreEvaluator()
        bert_result = evaluator.evaluate(review_text, user.raw_corpus or "")
        print(f"BERTScore F1: {bert_result['bertscore_f1']:.4f}")
        print(f"Confidence (F1): {bert_result['bertscore_f1']:.4f}")

        logger.info("✅ Task A test completed successfully!")

    except Exception as e:
        logger.error(f"❌ Task A test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

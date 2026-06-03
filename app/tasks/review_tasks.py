from loguru import logger
from app.core.broker import broker
from app.documents.user import UserDocument
from app.documents.review import ReviewDocument
from app.ml.review_generator import ReviewGenerator
from app.ml.rating_predictor import RatingPredictor
from app.ml.bertscore_evaluator import BERTScoreEvaluator
from app.services.embedding_encoder import encode_text

@broker.task(task_name="generate_review_async")
async def generate_review_async(user_id: str, product: dict):
    """
    Asynchronously generate and save a product review.
    """
    logger.info(f"[Tasks] Async review generation for user {user_id}, product {product.get('name')}")
    
    user = await UserDocument.get(user_id)
    if not user or not user.taste_profile:
        logger.error(f"[Tasks] User {user_id} not ready for review generation")
        return

    try:
        # Generate
        gen_result = await ReviewGenerator().generate(user_id, product)
        review_text = gen_result["review_text"]

        # Predict & Evaluate
        product_desc = f"{product['name']} {product.get('description', '')}"
        product_emb = encode_text(product_desc)
        
        rating = RatingPredictor().predict_with_sentiment(user.interest_embeddings, product_emb, review_text)
        bert_result = BERTScoreEvaluator().evaluate(review_text, user.raw_corpus or "")
        
        # Handle Image
        product_image = product.get("image_url")

        # Save
        review_doc = ReviewDocument(
            user_id=user_id,
            product_name=product["name"],
            product_category=product["category"],
            generated_text=review_text,
            predicted_rating=rating,
            confidence=bert_result["bertscore_f1"],
            image_url=product_image,
            bertscore_f1=bert_result["bertscore_f1"],
            style_snapshot=user.style_fingerprint
        )
        await review_doc.insert()
        logger.info(f"✅ [Tasks] Async review saved for {user.name}")

    except Exception as e:
        logger.error(f"❌ [Tasks] Failed async review generation: {e}")

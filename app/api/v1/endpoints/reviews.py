from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from loguru import logger

from app.core.security import verify_token
from app.documents.user import UserDocument
from app.documents.review import ReviewDocument
from app.ml.review_generator import ReviewGenerator
from app.ml.rating_predictor import RatingPredictor
from app.ml.bertscore_evaluator import BERTScoreEvaluator
from app.services.embedding_encoder import encode_text
from app.schemas.responses import ReviewResponse, ErrorResponse

router = APIRouter()

class ReviewGenerateRequest(BaseModel):
    product: Dict[str, str] # name, category, description

@router.post(
    "/generate", 
    response_model=ReviewResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Generate personalized review",
    description="Generates a product review in the user's voice using their style fingerprint and taste profile. It also predicts a rating and evaluates output via BERTScore."
)
async def generate_review(
    request: Dict, # Using dict to avoid strict pydantic for the 'product' nested dict in demo
    token_claims: dict = Depends(verify_token)
):
    """
    Generates a hyper-personalized product review using the user's style fingerprint,
    predicts a rating, and evaluates quality via BERTScore.
    """
    user = await UserDocument.get_or_create_from_token(token_claims)

    if not user.taste_profile:
        raise HTTPException(status_code=400, detail="User model not ready. Run analysis first.")

    product = request.get("product")
    if not product or not product.get("name") or not product.get("category"):
        raise HTTPException(status_code=422, detail="Product name and category are required")

    # 1. Generate Review Text
    gen_result = await ReviewGenerator().generate(str(user.id), product)
    review_text = gen_result["review_text"]

    # 2. Predict Rating
    product_desc = f"{product['name']} {product.get('description', '')}"
    product_emb = encode_text(product_desc)
    
    predictor = RatingPredictor()
    rating = predictor.predict_with_sentiment(user.interest_embeddings, product_emb, review_text)

    # 3. Evaluate with BERTScore
    evaluator = BERTScoreEvaluator()
    bert_result = evaluator.evaluate(review_text, user.raw_corpus or "")
    f1_score = bert_result["bertscore_f1"]

    # 4. Handle Image
    product_image = product.get("image_url")

    # 5. Save to Database
    review_doc = ReviewDocument(
        user_id=str(user.id),
        product_name=product["name"],
        product_category=product["category"],
        generated_text=review_text,
        predicted_rating=rating,
        confidence=f1_score,
        image_url=product_image,
        bertscore_f1=f1_score,
        style_snapshot=user.style_fingerprint.model_dump()
    )
    await review_doc.insert()

    return {
        "review_text": review_text,
        "predicted_rating": rating,
        "confidence": f1_score,
        "bertscore_f1": f1_score,
        "image_url": product_image,
        "style_snapshot": user.style_fingerprint.model_dump(),
        "used_nigerian_markers": gen_result["used_nigerian_markers"],
        "sentence_count": gen_result["sentence_count"]
    }

@router.get("/style", summary="Get user's style fingerprint")
async def get_user_style(
    user_id: Optional[str] = None,
    token_claims: dict = Depends(verify_token)
):
    if user_id:
        user = await UserDocument.get(user_id)
    else:
        user = await UserDocument.get_or_create_from_token(token_claims)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user.style_fingerprint

@router.get("/history", summary="Get user's generated review history")
async def get_review_history(token_claims: dict = Depends(verify_token)):
    user = await UserDocument.get_or_create_from_token(token_claims)

    reviews = await ReviewDocument.find(ReviewDocument.user_id == str(user.id)).to_list()
    return reviews

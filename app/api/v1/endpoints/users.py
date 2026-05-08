from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from app.core.security import verify_token
from app.documents.user import UserDocument
from app.core.broker import broker
router = APIRouter()

@router.get("/me/model", summary="Get the authenticated user's AI model profile")
async def get_my_model(token_claims: dict = Depends(verify_token)):
    """
    Returns the style fingerprint, taste profile, and model status 
    for the currently authenticated user.
    """
    email = token_claims.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in token")

    user = await UserDocument.find_one(UserDocument.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    return {
        "name": user.name,
        "email": user.email,
        "style_fingerprint": user.style_fingerprint,
        "taste_profile": user.taste_profile,
        "interest_embeddings_length": len(user.interest_embeddings),
        "model_version": user.model_version,
        "last_trained": user.last_trained,
        "corpus_length": len(user.raw_corpus) if user.raw_corpus else 0
    }

@router.post("/me/analyze", summary="Trigger manual analysis of user data")
async def trigger_my_analysis(token_claims: dict = Depends(verify_token)):
    """
    Manually kick off the background analysis task for the current user.
    """
    email = token_claims.get("email")
    user = await UserDocument.find_one(UserDocument.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found")

    if not user.raw_corpus:
        raise HTTPException(status_code=400, detail="No search data found. Please run deep search first.")

    await broker.kick("analyze_user_data", user_id=str(user.id))
    
    return {
        "message": "Analysis started", 
        "user_id": str(user.id)
    }

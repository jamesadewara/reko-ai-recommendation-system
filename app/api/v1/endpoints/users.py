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
    user = await UserDocument.get_or_create_from_token(token_claims)

    return {
        "name": user.name,
        "email": user.email,
        "style_fingerprint": user.style_fingerprint,
        "taste_profile": user.taste_profile,
        "interest_embeddings_length": len(user.interest_embeddings),
        "model_version": user.ml_version,
        "last_trained": user.last_trained,
        "corpus_length": len(user.raw_corpus) if user.raw_corpus else 0
    }

@router.post("/me/analyze", summary="Trigger manual analysis of user data")
async def trigger_my_analysis(token_claims: dict = Depends(verify_token)):
    """
    Manually kick off the background analysis task for the current user.
    """
    user = await UserDocument.get_or_create_from_token(token_claims)

    if not user.raw_corpus:
        raise HTTPException(status_code=400, detail="No search data found. Please run deep search first.")

    await broker.kick("analyze_user_data", user_id=str(user.id))
    
    return {
        "message": "Analysis started", 
        "user_id": str(user.id)
    }

@router.post("/discovery", summary="Start pre-analysis for a prospective user")
async def start_discovery(email: str):
    """
    Triggers the Deep Search engine to build a 'Temp Model' for an email address.
    Used for waitlists or landing page 'magic' onboarding.
    """
    from app.services.temp_model import TempModelService
    service = TempModelService()
    temp = await service.create_from_email(email)
    
    return {
        "status": "discovery_started",
        "email": email,
        "is_ready": temp.interest_embeddings and len(temp.interest_embeddings) > 0,
        "message": "Reko is learning your style from your public digital footprint."
    }

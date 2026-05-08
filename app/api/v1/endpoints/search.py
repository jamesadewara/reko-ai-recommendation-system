from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from loguru import logger

from app.core.security import verify_token
from app.documents.user import UserDocument
from app.services.deep_search import TavilyDeepSearch
from app.core.broker import broker
router = APIRouter()

class DeepSearchRequest(BaseModel):
    user_id: str
    name: str
    email: str
    handles: Optional[Dict] = None

class VerifyProfilesRequest(BaseModel):
    user_id: str
    verified_urls: Dict[str, str]

@router.post("/deep", summary="Perform deep web search for a user")
async def perform_deep_search(
    payload: DeepSearchRequest,
    token_claims: dict = Depends(verify_token)
):
    """
    Perform multi-platform deep search using Tavily, compile corpus,
    and update the user's document in MongoDB.
    """
    # 1. Verify user exists
    user = await UserDocument.get(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Initialize Search Service
    search_service = TavilyDeepSearch()

    # 3. Perform Searches
    try:
        search_results = await search_service.search_user(
            name=payload.name,
            email=payload.email,
            handles=payload.handles
        )
        
        # 4. Extract candidates and compile corpus
        candidates = search_service.extract_candidate_urls(search_results)
        corpus = search_service.compile_corpus(search_results)

        # 5. Update UserDocument
        user.deep_search_results = search_results
        user.raw_corpus = corpus
        
        # Map candidates to social_profiles (unverified)
        for platform, urls in candidates.items():
            if urls:
                # Store the top candidate if not already set or verified
                current_profile = user.social_profiles.get(platform, {})
                if not current_profile.get("verified"):
                    user.social_profiles[platform] = {
                        "url": urls[0]["url"],
                        "verified": False,
                        "last_scraped": None
                    }
        
        await user.save()

        return {
            "user_id": str(user.id),
            "candidates": candidates,
            "corpus_length": len(corpus),
            "corpus_preview": corpus[:500] + "..." if len(corpus) > 500 else corpus,
            "nigerian_context_detected": bool(search_results.get("nigerian", {}).get("results"))
        }

    except Exception as e:
        logger.error(f"[SearchAPI] Search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Deep search failed: {str(e)}"
        )

@router.post("/verify", summary="Verify and link social profiles")
async def verify_profiles(
    payload: VerifyProfilesRequest,
    token_claims: dict = Depends(verify_token)
):
    """
    Confirm which social media URLs belong to the user and trigger analysis.
    """
    user = await UserDocument.get(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profiles_linked = []
    for platform, url in payload.verified_urls.items():
        user.social_profiles[platform] = {
            "url": url,
            "verified": True,
            "last_scraped": datetime.utcnow()
        }
        profiles_linked.append(platform)

    await user.save()

    # Trigger background Taskiq task for analysis
    try:
        await broker.kick("analyze_user_data", user_id=str(user.id))
        logger.info(f"[SearchAPI] Analysis task triggered for user {user.id}")
    except Exception as e:
        logger.error(f"[SearchAPI] Failed to trigger analysis task: {e}")

    return {
        "message": "Profiles verified",
        "profiles_linked": profiles_linked
    }

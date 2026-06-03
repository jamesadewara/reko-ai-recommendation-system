from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Request, Security
from pydantic import BaseModel
from loguru import logger

from app.core.security import verify_token
from app.documents.user import UserDocument
from app.services.deep_search import MultiSearchEngine
from app.core.broker import broker
from taskiq.kicker import AsyncKicker
from app.core.config import settings
from app.schemas.responses import SearchResponse, ErrorResponse
from app.core.security import security
import httpx

router = APIRouter()

class DeepSearchRequest(BaseModel):
    handles: Optional[Dict[str, str]] = None

class VerifyProfilesRequest(BaseModel):
    verified_urls: Dict[str, str]

@router.post(
    "/deep", 
    response_model=SearchResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Perform deep web search for a user",
    description="Crawls the web to find public information about the user, compiles a corpus, and prepares for NLP analysis."
)
async def perform_deep_search(
    payload: DeepSearchRequest,
    token_claims: dict = Depends(verify_token)
):
    """
    Perform multi-platform deep search using Tavily, compile corpus,
    and update the user's document in MongoDB.
    """
    # 1. Get/Create User from token
    user = await UserDocument.get_or_create_from_token(token_claims)
    
    # 2. Initialize Search Service
    search_service = MultiSearchEngine()

    # 3. Perform Searches
    try:
        search_results = await search_service.search_user(
            name=user.name or "Anonymous User",
            email=user.email,
            handles=payload.handles
        )
        
        # 4. Extract candidates and compile corpus
        candidates = search_service.extract_candidate_urls(search_results)
        corpus = search_service.compile_corpus(search_results)

        # 5. Update UserDocument
        user.deep_search_results = search_results
        user.raw_corpus = corpus
        
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
    credentials=Security(security),
    token_claims: dict = Depends(verify_token)
):
    """
    Confirm which social media URLs belong to the user.

    For each confirmed URL:
    - Runs a targeted re-search to get an accurate confidence score.
    - Persists the profile as a VerifiedProfile on the UserDocument
      (confirmed_by_user=True) with a confidence history entry.
    - Syncs the URL to the Auth system's /socials/ endpoint.
    - Triggers the analyze_user_data pipeline to retrain the user model.
    """
    from app.documents.user import VerifiedProfile
    from app.services.deep_search import _score_result, CONFIDENCE_THRESHOLD

    user = await UserDocument.get_or_create_from_token(token_claims)
    email_prefix = user.email.split("@")[0]

    search_service = MultiSearchEngine()
    profiles_linked = []
    raw_token = credentials.credentials if credentials else ""

    # Build a map of existing verified profiles for upsert logic
    existing_map = {(p.platform, p.url): p for p in (user.verified_profiles or [])}

    for platform, url in payload.verified_urls.items():
        # ── 1. Re-score the URL via a targeted search ────────────────────────
        confidence = 0.5   # fallback if search fails
        try:
            result = await search_service.search(query=url, max_results=5)
            results = result.get("results", [])
            best = next((r for r in results if r.get("url") == url), results[0] if results else None)
            if best:
                confidence = _score_result(best, platform, user.name or "", email_prefix)
                title = best.get("title", "")
            else:
                title = ""
        except Exception as e:
            logger.warning(f"[SearchAPI] Could not re-score {platform} ({url}): {e}")
            title = ""

        # ── 2. Upsert into verified_profiles ────────────────────────────────
        key = (platform, url)
        if key in existing_map:
            # Update existing record
            existing = existing_map[key]
            history = (existing.confidence_history or [])[-9:] + [confidence]
            existing_map[key] = VerifiedProfile(
                platform=platform,
                url=url,
                title=title or existing.title,
                confidence=confidence,
                confirmed_by_user=True,
                added_at=existing.added_at,
                last_verified_at=datetime.utcnow(),
                confidence_history=history,
            )
        else:
            existing_map[key] = VerifiedProfile(
                platform=platform,
                url=url,
                title=title,
                confidence=confidence,
                confirmed_by_user=True,
                last_verified_at=datetime.utcnow(),
                confidence_history=[confidence],
            )

        profiles_linked.append(platform)

        # ── 3. Sync to Auth system ───────────────────────────────────────────
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{settings.REKO_AI_AUTH_URL}/api/v1/socials/",
                    json={"name": platform, "url": url},
                    headers={
                        "Authorization": f"Bearer {raw_token}",
                        "X-Internal-Secret": settings.INTERNAL_SERVICE_SECRET or "",
                    },
                )
        except Exception as e:
            logger.error(f"[SearchAPI] Failed to sync {platform} to Auth system: {e}")

    # ── 4. Persist updated profiles ──────────────────────────────────────────
    user.verified_profiles = list(existing_map.values())
    user.updated_at = datetime.utcnow()

    try:
        await user.save()
    except Exception as e:
        logger.error(f"[SearchAPI] Failed to save user: {e}")

    logger.info(
        f"[SearchAPI] Verified {len(profiles_linked)} profiles for user {user.id}: {profiles_linked}"
    )

    # ── 5. Trigger model retrain ─────────────────────────────────────────────
    try:
        await AsyncKicker(task_name="analyze_user_data", broker=broker, labels={}).kiq(
            user_id=str(user.id)
        )
        logger.info(f"[SearchAPI] Analysis task triggered for user {user.id}")
    except Exception as e:
        logger.error(f"[SearchAPI] Failed to trigger analysis task: {e}")

    return {
        "message": "Profiles verified and model retrain queued",
        "profiles_linked": profiles_linked,
    }

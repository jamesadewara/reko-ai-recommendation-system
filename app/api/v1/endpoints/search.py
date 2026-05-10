from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from loguru import logger

from app.core.security import verify_token
from app.documents.user import UserDocument
from app.services.deep_search import TavilyDeepSearch
from app.core.broker import broker
from taskiq_aio_pika import AioPikaBroker
from taskiq import AsyncKicker
from app.core.config import settings

# Secondary broker pointing to the Auth System's queue for cross-service tasks
auth_broker = AioPikaBroker(
    settings.RABBITMQ_URL,
    queue_name="auth_queue"
)
from app.schemas.responses import SearchResponse, ErrorResponse

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
    search_service = TavilyDeepSearch()

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
    token_claims: dict = Depends(verify_token)
):
    """
    Confirm which social media URLs belong to the user and trigger analysis.
    """
    user = await UserDocument.get_or_create_from_token(token_claims)

    profiles_linked = []
    # 2. Sync with Auth System via RabbitMQ
    user_uuid = token_claims.get("user_id") or token_claims.get("sub")
    
    auth_sync_count = 0
    for platform, url in payload.verified_urls.items():
        # Async Sync (RabbitMQ to Auth System)
        try:
            # We use AsyncKicker to call the task by name across services
            await AsyncKicker(task_name="sync_user_socials", broker=auth_broker).kiq(
                user_id=user_uuid, 
                platform=platform, 
                url=url
            )
            auth_sync_count += 1
        except Exception as e:
            logger.error(f"[SearchAPI] Failed to queue social sync for {platform}: {e}")
        
        profiles_linked.append(platform)

    await user.save()
    logger.info(f"[SearchAPI] Profiles verified for {user.id}. Queued {auth_sync_count} sync tasks to RabbitMQ.")

    # Trigger background Taskiq task for analysis
    try:
        await AsyncKicker(task_name="analyze_user_data", broker=broker).kiq(user_id=str(user.id))
        logger.info(f"[SearchAPI] Analysis task triggered for user {user.id}")
    except Exception as e:
        logger.error(f"[SearchAPI] Failed to trigger analysis task: {e}")

    return {
        "message": "Profiles verified",
        "profiles_linked": profiles_linked
    }

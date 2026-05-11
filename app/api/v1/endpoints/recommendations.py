import numpy as np
from typing import Optional, Any, Callable
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.core.security import verify_token
from app.documents.user import UserDocument
from app.documents.item import ItemDocument
from app.services.context_parser import parse_context
from app.services.cot_reasoning import CoTReasoning
from app.services.embedding_encoder import encode_text
from app.ml.faiss_manager import get_faiss_index
from app.ml.react_agent import ReActAgent
from app.ml.hybrid_matcher import HybridMatcher
from app.services.deep_search import MultiSearchEngine
from app.schemas.responses import RecommendationResponse, ErrorResponse

router = APIRouter()

class ContextInput(BaseModel):
    message: Optional[str] = None
    mood: Optional[str] = None
    location: Optional[str] = None
    category: Optional[str] = None

class RecommendationRequest(BaseModel):
    context: ContextInput

@router.post(
    "", 
    response_model=RecommendationResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Get personalized recommendations with CoT reasoning",
    description="Retrieves a list of highly relevant items using Hybrid FAISS matching, CoT reasoning chains, and ReAct agent filtering."
)
async def get_recommendations(
    request: RecommendationRequest,
    token_claims: dict = Depends(verify_token),
    on_status: Optional[Any] = None,
    hybrid_override: Optional[bool] = None
):
    user = await UserDocument.get_or_create_from_token(token_claims)
        
    if not user.taste_profile:
        raise HTTPException(status_code=400, detail="User model not ready. Run analysis first.")

    # 1. Parse Context
    if on_status: await on_status("Analyzing your request...")
    parsed_context = {}
    if request.context.message and not (request.context.mood and request.context.location and request.context.category):
        parsed_context = parse_context(request.context.message)
    else:
        # Use provided or default
        parsed_context = {
            "mood": request.context.mood or "neutral",
            "location": request.context.location or "unknown",
            "category": request.context.category or "movies",
            "time_of_day": "unknown",
            "current_hour": 12,
            "recent_activity": "none"
        }
        
    category = parsed_context.get("category", "movies") or "movies"

    # 2. Generate CoT Reasoning
    if on_status: await on_status(f"Generating reasoning for {category}...")
    reasoning_chain = await CoTReasoning().generate_reasoning_chain(user, parsed_context, category)

    # 3. Build Query Embedding
    if on_status: await on_status("Personalizing vector search...")
    interests = " ".join(user.taste_profile.interests) if user.taste_profile.interests else ""
    query_text = f"{interests} {parsed_context['mood']} {parsed_context['location']} {category}"
    query_emb = encode_text(query_text)

    # 4. FAISS Search
    if on_status: await on_status(f"Scanning my knowledge base for {category}...")
    faiss_idx = await get_faiss_index()
    candidates = []
    
    if faiss_idx.index is not None and faiss_idx.index.ntotal > 0:
        results = faiss_idx.search(query_emb, k=50)
        for item_id, score in results:
            item = await ItemDocument.get(item_id)
            if item and item.category == category:
                item_dict = item.model_dump()
                item_dict["score"] = score
                candidates.append(item_dict)

    # 5. Hybrid Matching Boost
    similar_users = []
    
    # Check if hybrid is allowed (Global setting OR Override)
    allow_hybrid = user.allow_hybrid_recommendations
    if hybrid_override is not None:
        allow_hybrid = hybrid_override

    if allow_hybrid:
        if on_status: await on_status("Finding patterns from similar users...")
        hybrid_matcher = HybridMatcher()
        similar_users = await hybrid_matcher.find_similar_users(str(user.id))
        
        if similar_users:
            cross_items = await hybrid_matcher.get_cross_recommendations(str(user.id), similar_users, category)
            for c in candidates:
                if str(c.get("id")) in cross_items:
                    c["score"] += 0.1
    else:
        logger.info(f"[Recommendations] Hybrid mode disabled for user {user.id}")

    # 5b. Online Search Augmentation
    try:
        if on_status: await on_status(f"Searching online for the latest {category}...")
        search_engine = MultiSearchEngine()
        online_query = f"top {category} recommendations 2026 {parsed_context.get('mood', '')}"
        if user.taste_profile.interests:
            online_query += " " + " ".join(user.taste_profile.interests[:2])
            
        web_data = await search_engine.search(query=online_query, max_results=3)
        for res in web_data.get("results", []):
            item_dict = {
                "id": f"web_{hash(res.get('url', ''))}",
                "name": res.get("title", "Online Pick"),
                "category": category,
                "score": res.get("score", 0.8),
                "metadata": {
                    "source": "web",
                    "url": res.get("url"),
                    "description": res.get("content", "")
                }
            }
            candidates.append(item_dict)
    except Exception as e:
        logger.warning(f"[Recommendations] Failed to augment with online search: {e}")

    # 6. ReAct Agent Filtering
    if on_status: await on_status("Finalizing ranking with ReAct Agent...")
    top_picks = ReActAgent().filter_and_rank(candidates, parsed_context, user)
    
    # 7. Attach reasoning
    if on_status: await on_status("Formatting your personalized list...")
    for i, item in enumerate(top_picks):
        # Remove massive raw embeddings from output
        if "embedding" in item:
            del item["embedding"]
            
        metadata = item.get("metadata", {})
        
        reason = f"Matches your interest in {user.taste_profile.interests[0] if user.taste_profile.interests else 'entertainment'}."
        if metadata.get("nigerian_context"):
            reason += " Top Nigerian pick for you."
        if parsed_context["mood"] == "tired" and metadata.get("duration_minutes", 0) and metadata.get("duration_minutes", 0) < 120:
            reason += " Short and easy for your tired mood."
        if metadata.get("source") == "web":
            reason = f"Trending Online: {metadata.get('description', '')}"

        item_out = {
            "item_id": str(item.get("id", item.get("_id", "unknown"))),
            "name": item.get("name", "Unknown Item"),
            "category": item.get("category", "products"),
            "image": item.get("metadata", {}).get("image_url") or "",
            "score": item.get("score", 0.0),
            "reasoning": reason,
            "meta": ", ".join(item.get("metadata", {}).get("genre", [])) or item.get("category", "")
        }
            
        top_picks[i] = item_out

    return {
        "items": top_picks,
        "reasoning_chain": reasoning_chain,
        "context": parsed_context,
        "similar_users_found": len(similar_users),
        "privacy_safe": True
    }


class HybridRequest(BaseModel):
    k_similar_users: int = 5
    category: str

@router.post("/hybrid", summary="Get recommendations based on similar users")
async def get_hybrid_recommendations(request: HybridRequest, token_claims: dict = Depends(verify_token)):
    user = await UserDocument.get_or_create_from_token(token_claims)
    user_id_str = str(user.id)
    
    hybrid_matcher = HybridMatcher()
    similar_users = await hybrid_matcher.find_similar_users(user_id_str)
    
    if not similar_users:
        return {
            "items": [], 
            "similar_user_overlap": 0, 
            "privacy_safe": True,
            "message": "We're still learning your taste. No similar users found yet."
        }
        
    similar_users = similar_users[:request.k_similar_users]
    cross_items = await hybrid_matcher.get_cross_recommendations(user_id_str, similar_users, request.category)
    
    items_out = []
    for item_id in cross_items[:10]:
        item = await ItemDocument.get(item_id)
        if item:
            item_dict = item.model_dump()
            if "embedding" in item_dict:
                del item_dict["embedding"]
            items_out.append(item_dict)
            
    return {
        "items": items_out,
        "similar_user_overlap": len(similar_users),
        "privacy_safe": True
    }

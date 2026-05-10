import numpy as np
from typing import Optional
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
    token_claims: dict = Depends(verify_token)
):
    user = await UserDocument.get_or_create_from_token(token_claims)
        
    if not user.taste_profile:
        raise HTTPException(status_code=400, detail="User model not ready. Run analysis first.")

    # 1. Parse Context
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
    reasoning_chain = CoTReasoning().generate_reasoning_chain(user, parsed_context, category)

    # 3. Build Query Embedding
    interests = " ".join(user.taste_profile.interests) if user.taste_profile.interests else ""
    query_text = f"{interests} {parsed_context['mood']} {parsed_context['location']} {category}"
    query_emb = encode_text(query_text)

    # 4. FAISS Search
    faiss_idx = await get_faiss_index()
    candidates = []
    
    if faiss_idx.index is None or faiss_idx.index.ntotal == 0:
        logger.warning("[Recommendations] FAISS index empty, falling back to manual scoring")
        items = await ItemDocument.find(ItemDocument.category == category).to_list()
        for item in items:
            item_dict = item.model_dump()
            if not item.embedding: continue
            
            # Cosine similarity
            q_arr = np.array(query_emb)
            i_arr = np.array(item.embedding)
            sim = np.dot(q_arr, i_arr) / (np.linalg.norm(q_arr) * np.linalg.norm(i_arr))
            item_dict["score"] = float(sim)
            candidates.append(item_dict)
    else:
        results = faiss_idx.search(query_emb, k=50)
        for item_id, score in results:
            item = await ItemDocument.get(item_id)
            if item and item.category == category:
                item_dict = item.model_dump()
                item_dict["score"] = score
                candidates.append(item_dict)

    # 5. Hybrid Matching Boost
    hybrid_matcher = HybridMatcher()
    similar_users = await hybrid_matcher.find_similar_users(str(user.id))
    
    if similar_users:
        cross_items = await hybrid_matcher.get_cross_recommendations(str(user.id), similar_users, category)
        for c in candidates:
            if str(c.get("id")) in cross_items:
                c["score"] += 0.1

    # 6. ReAct Agent Filtering
    filtered = ReActAgent().filter_and_rank(candidates, parsed_context, user)
    
    # 7. Attach reasoning
    top_10 = filtered[:10]
    for i, item in enumerate(top_10):
        # Remove massive raw embeddings from output
        if "embedding" in item:
            del item["embedding"]
            
        metadata = item.get("metadata", {})
        
        reason = f"Matches your interest in {user.taste_profile.interests[0] if user.taste_profile.interests else 'entertainment'}."
        if metadata.get("nigerian_context"):
            reason += " Top Nigerian pick for you."
        if parsed_context["mood"] == "tired" and metadata.get("duration_minutes", 0) and metadata.get("duration_minutes", 0) < 120:
            reason += " Short and easy for your tired mood."
            
        item["reasoning"] = reason

    return {
        "items": top_10,
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

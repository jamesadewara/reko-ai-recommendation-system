from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ErrorResponse(BaseModel):
    detail: str = Field(..., example="An error occurred processing your request.")

class ReviewResponse(BaseModel):
    review_text: str = Field(..., example="Omo, this item make sense die! I completely love the vibe.")
    predicted_rating: float = Field(..., example=4.5)
    bertscore_f1: Optional[float] = Field(None, example=0.87)
    confidence: Optional[float] = Field(None, example=0.92)
    style_snapshot: Optional[Dict[str, Any]] = Field(None)
    image_url: Optional[str] = Field(None, example="https://images.example.com/product-123.jpg")
    used_nigerian_markers: Optional[List[str]] = Field(None, example=["omo", "abeg"])
    sentence_count: Optional[int] = Field(None, example=5)

class RecommendationItem(BaseModel):
    item_id: str = Field(..., example="507f1f77bcf86cd799439011")
    name: str = Field(..., example="Nollywood Classics Collection")
    reasoning: str = Field(..., example="Because you mentioned feeling nostalgic and you love Nigerian drama.")
    score: float = Field(..., example=0.95)

class RecommendationResponse(BaseModel):
    items: List[RecommendationItem]
    reasoning_chain: List[str] = Field(default_factory=list)
    context_used: Dict[str, Any] = Field(..., alias="context")
    similar_users_found: int = 0
    privacy_safe: bool = True

    class Config:
        populate_by_name = True

class SearchResponse(BaseModel):
    user_id: str
    status: str = "success"
    corpus_length: int = 0
    corpus_preview: Optional[str] = None
    candidates: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    entities_found: List[str] = Field(default_factory=list)
    nigerian_context_detected: bool = False

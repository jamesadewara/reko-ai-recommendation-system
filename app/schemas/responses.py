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
    used_nigerian_markers: Optional[bool] = Field(None, example=True)
    sentence_count: Optional[int] = Field(None, example=5)

class RecommendationItem(BaseModel):
    item_id: str = Field(..., example="507f1f77bcf86cd799439011")
    name: str = Field(..., example="Nollywood Classics Collection")
    reasoning: str = Field(..., example="Because you mentioned feeling nostalgic and you love Nigerian drama.")
    score: float = Field(..., example=0.95)

class RecommendationResponse(BaseModel):
    items: List[RecommendationItem]
    context_used: Dict[str, Any] = Field(..., example={"mood": "nostalgic", "location": "Lagos"})

class SearchResponse(BaseModel):
    status: str = Field(..., example="success")
    corpus_length: int = Field(..., example=15000)
    entities_found: List[str] = Field(..., example=["Lagos", "Tech", "Music"])

from typing import Optional, Dict
from datetime import datetime
from beanie import Document
from pydantic import Field

class ReviewDocument(Document):
    user_id: str
    product_name: str
    product_category: str
    generated_text: str
    predicted_rating: float
    confidence: float
    image_url: Optional[str] = None
    bertscore_f1: Optional[float] = None
    style_snapshot: Dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reviews"

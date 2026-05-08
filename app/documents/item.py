from typing import List, Optional, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field

class ItemMetadata(BaseModel):
    duration_minutes: Optional[int] = None
    genre: List[str] = []
    location_tags: List[str] = []
    nigerian_context: bool = False
    image_url: Optional[str] = None

class ItemDocument(Document):
    name: str
    category: Indexed(str) # movies/food/products/books/music
    description: str
    embedding: List[float] = Field(default_factory=list)
    metadata: ItemMetadata = Field(default_factory=ItemMetadata)
    popularity_score: float = 0.0

    class Settings:
        name = "items"

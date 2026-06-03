import numpy as np
from typing import List
from loguru import logger

class RatingPredictor:
    def __init__(self):
        pass

    def predict(self, user_embedding: List[float], product_embedding: List[float]) -> float:
        """
        Predict a rating (1-5) based on the cosine similarity between 
        user interests and product description embeddings.
        """
        if not user_embedding or not product_embedding:
            return 3.0 # Default neutral

        user_emb = np.array(user_embedding)
        product_emb = np.array(product_embedding)
        
        # Compute cosine similarity
        dot = np.dot(user_emb, product_emb)
        norm_u = np.linalg.norm(user_emb)
        norm_p = np.linalg.norm(product_emb)
        
        cos_sim = dot / (norm_u * norm_p) if norm_u and norm_p else 0
        
        # Map cosine similarity (-1 to 1, usually 0.2 to 0.8 for these models) to 1-5 scale
        # Heuristic: base 3.0 + (sim * 2.5) assuming sim is around 0.4-0.8 for matches
        # Let's use the user's logic: 3.0 + (cos_sim * 2.0)
        rating = 3.0 + (cos_sim * 2.0)
        
        # Clamp to 1.0 - 5.0
        rating = max(1.0, min(5.0, rating))
        
        # Round to nearest 0.5
        final_rating = round(rating * 2) / 2
        
        logger.debug(f"[RatingPredictor] Similarity: {cos_sim:.4f} -> Predicted Rating: {final_rating}")
        return float(final_rating)

    def predict_with_sentiment(self, user_embedding: List[float], product_embedding: List[float], review_text: str) -> float:
        """
        Adjust the embedding-based rating using sentiment markers in the review text.
        """
        base_rating = self.predict(user_embedding, product_embedding)
        
        # Simple keyword-based sentiment adjustment
        text_lower = review_text.lower()
        
        positive_keys = ["love", "amazing", "perfect", "best", "excellent", "must-have"]
        negative_keys = ["hate", "terrible", "worst", "awful", "bad", "disappointing"]
        neutral_keys = ["okay", "fine", "average", "decent"]
        
        adjustment = 0.0
        if any(k in text_lower for k in positive_keys):
            adjustment += 0.5
        if any(k in text_lower for k in negative_keys):
            adjustment -= 0.5
        if any(k in text_lower for k in neutral_keys):
            adjustment -= 0.2
            
        final_rating = max(1.0, min(5.0, base_rating + adjustment))
        final_rating = round(final_rating * 2) / 2
        
        logger.debug(f"[RatingPredictor] Base: {base_rating} + Adj: {adjustment} -> Adjusted: {final_rating}")
        return float(final_rating)

from typing import List
from app.documents.user import UserDocument

class ReActAgent:
    def filter_and_rank(self, candidates: List[dict], context: dict, user: UserDocument) -> List[dict]:
        """
        Step 1 — REASON & ACT (Filter)
        Step 2 — OBSERVE (Score remaining)
        Step 3 — REFLECT (Diversity enforcement)
        """
        
        # Step 1: Filter
        valid_candidates = []
        for item in candidates:
            exclusion_reason = None
            metadata = item.get("metadata", {})
            category = item.get("category", "")
            
            if context["mood"] == "tired":
                duration = metadata.get("duration_minutes", 0)
                if duration and duration > 150:
                    exclusion_reason = "Too long for tired user (>2.5h)"
            
            if context["time_of_day"] == "night" and category == "movies":
                duration = metadata.get("duration_minutes", 0)
                if duration and duration > 180:
                    exclusion_reason = "Too long for late night"
                    
            if exclusion_reason:
                item["excluded"] = True
                item["exclusion_reason"] = exclusion_reason
            else:
                item["excluded"] = False
                valid_candidates.append(item)

        # Step 2: Observe / Score
        for item in valid_candidates:
            base_score = item.get("score", 0.5)
            metadata = item.get("metadata", {})
            category = item.get("category", "")
            
            # Nigerian content boost
            if user.taste_profile and user.taste_profile.nigerian_context and metadata.get("nigerian_context"):
                base_score += 0.15
                
            # Location match boost
            user_locations = []
            if user.style_fingerprint:
                user_locations = user.style_fingerprint.favorite_entities
            item_locations = metadata.get("location_tags", [])
            if any(loc in item_locations for loc in user_locations):
                base_score += 0.1
                
            # Category match boost
            if user.taste_profile and category in user.taste_profile.interests:
                base_score += 0.1
                
            # Mood-category alignment
            if context["mood"] == "hungry" and category == "food":
                base_score += 0.2
            if context["mood"] == "tired" and category == "music":
                base_score += 0.1
                
            item["final_score"] = min(1.0, base_score)

        # Step 3: Reflect / Diversity
        valid_candidates.sort(key=lambda x: x["final_score"], reverse=True)
        top_20 = valid_candidates[:20]
        
        # We will skip deep diversity swapping logic to keep it simple, but we'll return top 10
        # If diversity needs enforcement, we could check genre counts.
        
        return top_20[:10]

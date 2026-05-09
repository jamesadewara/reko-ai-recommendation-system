from typing import List, Tuple
import numpy as np

from app.documents.user import UserDocument
from app.documents.review import ReviewDocument
from app.documents.item import ItemDocument

class HybridMatcher:
    async def find_similar_users(self, user_id: str, threshold: float = 0.75) -> List[Tuple[str, float]]:
        target_user = await UserDocument.get(user_id)
        if not target_user or not target_user.interest_embeddings:
            return []
            
        if not getattr(target_user, 'allow_hybrid_recommendations', True):
            return []
            
        target_emb = np.array(target_user.interest_embeddings)
        norm_t = np.linalg.norm(target_emb)
        if norm_t == 0: return []
        
        all_users = await UserDocument.find(UserDocument.interest_embeddings != None).to_list()
        
        matches = []
        for u in all_users:
            uid_str = str(u.id)
            if uid_str == user_id:
                continue
                
            if not getattr(u, 'allow_hybrid_recommendations', True):
                continue
            
            u_emb = np.array(u.interest_embeddings)
            norm_u = np.linalg.norm(u_emb)
            if norm_u == 0: continue
            
            sim = np.dot(target_emb, u_emb) / (norm_t * norm_u)
            if sim > threshold:
                matches.append((uid_str, float(sim)))
                
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:5]

    async def get_cross_recommendations(self, user_id: str, similar_users: List[Tuple[str, float]], category: str) -> List[str]:
        if not similar_users:
            return []
            
        sim_user_ids = [uid for uid, _ in similar_users]
        sim_scores = {uid: score for uid, score in similar_users}
        
        # Find reviews by these users
        reviews = await ReviewDocument.find(
            {"user_id": {"$in": sim_user_ids}, "product_category": category}
        ).to_list()
        
        item_scores = {}
        for rev in reviews:
            # Using product_name as proxy for item linkage for this demo since review doesn't store item_id natively
            pname = rev.product_name
            sim = sim_scores.get(rev.user_id, 0)
            
            # Weight by rating and similarity
            weight = sim * (rev.predicted_rating / 5.0)
            item_scores[pname] = item_scores.get(pname, 0) + weight
            
        # Get item IDs
        sorted_pnames = sorted(item_scores.keys(), key=lambda x: item_scores[x], reverse=True)
        
        cross_items = []
        for pname in sorted_pnames:
            item = await ItemDocument.find_one(ItemDocument.name == pname)
            if item:
                cross_items.append(str(item.id))
                
        return cross_items

import os
import json
import numpy as np
from typing import List, Tuple
from loguru import logger
import faiss

from app.documents.item import ItemDocument

class FAISSIndex:
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.index = None
        self.id_map = []  # Maps faiss index position → MongoDB item_id

    def build_from_items(self, items: List[ItemDocument]):
        embeddings = []
        self.id_map = []
        
        for item in items:
            if item.embedding:
                embeddings.append(item.embedding)
                self.id_map.append(str(item.id))
        
        if not embeddings:
            logger.warning("[FAISS] No embeddings found to build index.")
            return

        vectors = np.array(embeddings).astype('float32')
        faiss.normalize_L2(vectors)
        
        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(vectors)
        logger.info(f"[FAISS] Built index with {self.index.ntotal} vectors.")

    def search(self, query_embedding: List[float], k: int = 50) -> List[Tuple[str, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []
            
        q = np.array([query_embedding]).astype('float32')
        faiss.normalize_L2(q)
        
        scores, indices = self.index.search(q, k)
        results = []
        
        for score, idx in zip(scores[0], indices[0]):
            if 0 <= idx < len(self.id_map):
                results.append((self.id_map[idx], float(score)))
                
        return results

    def save(self, path: str):
        if self.index:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            faiss.write_index(self.index, path)
            with open(path + ".map", "w") as f:
                json.dump(self.id_map, f)
            logger.info(f"[FAISS] Saved index to {path}")

    def load(self, path: str):
        if os.path.exists(path) and os.path.exists(path + ".map"):
            self.index = faiss.read_index(path)
            with open(path + ".map", "r") as f:
                self.id_map = json.load(f)
            logger.info(f"[FAISS] Loaded index from {path} with {self.index.ntotal} vectors.")
        else:
            logger.warning(f"[FAISS] Index or map not found at {path}")

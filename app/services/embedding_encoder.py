from typing import List

from loguru import logger
from sentence_transformers import SentenceTransformer
from app.core.config import settings

_model = None

def get_encoder() -> SentenceTransformer:
    """
    Singleton pattern for loading the SentenceTransformer model.
    """
    global _model
    if _model is not None:
        return _model

    try:
        logger.info(f"[Embedding] Loading model: {settings.SENTENCE_TRANSFORMER_MODEL}")
        _model = SentenceTransformer(settings.SENTENCE_TRANSFORMER_MODEL)
        return _model
    except Exception as e:
        logger.error(f"[Embedding] Failed to load model {settings.SENTENCE_TRANSFORMER_MODEL}: {e}")
        raise

def encode_text(text: str) -> List[float]:
    """
    Convert a single string into a vector embedding.
    """
    model = get_encoder()
    embedding = model.encode(text, convert_to_tensor=False)
    return embedding.tolist()

def encode_batch(texts: List[str]) -> List[List[float]]:
    """
    Convert a list of strings into a list of vector embeddings.
    """
    model = get_encoder()
    embeddings = model.encode(texts, convert_to_tensor=False)
    return embeddings.tolist()

def build_user_embedding(taste_profile: dict, style_fingerprint: dict) -> List[float]:
    """
    Combines the psychological profile and linguistic markers into a single 
    descriptive text for vector embedding.
    """
    # Safeguard for missing data
    interests = taste_profile.get("interests", [])
    traits = taste_profile.get("personality_traits", [])
    themes = taste_profile.get("content_themes", [])
    tone = taste_profile.get("writing_tone", "neutral")
    nigerian = taste_profile.get("nigerian_context", False)
    phrases = style_fingerprint.get("top_phrases", [])

    descriptive_text = f"""
    Interests: {', '.join(interests)}
    Personality: {', '.join(traits)}
    Themes: {', '.join(themes)}
    Tone: {tone}
    Nigerian: {nigerian}
    Phrases: {', '.join(phrases)}
    """
    
    logger.debug(f"[Embedding] Building user embedding from text: {descriptive_text[:200]}...")
    return encode_text(descriptive_text.strip())

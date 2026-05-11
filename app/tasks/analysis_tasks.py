from datetime import datetime
from loguru import logger
from app.core.broker import broker
from app.documents.user import UserDocument
from app.services.style_extractor import extract_style_fingerprint
from app.services.taste_analyzer import TasteAnalyzer
from app.services.embedding_encoder import build_user_embedding

@broker.task(task_name="analyze_user_data")
async def analyze_user_data(user_id: str):
    """
    Background task to analyze user corpus using spaCy and LLM, 
    then generate a vector embedding of the user's profile.
    """
    logger.info(f"[Analysis] Starting analysis for user: {user_id}")
    
    user = await UserDocument.get(user_id)
    if not user:
        logger.error(f"[Analysis] User {user_id} not found.")
        return
        
    if not user.raw_corpus:
        logger.error(f"[Analysis] No corpus found for user {user_id}. Run deep search first.")
        return

    try:
        # Step 1: Extract style fingerprint (spaCy)
        logger.info(f"[Analysis] Extracting style fingerprint for {user.name}...")
        style = extract_style_fingerprint(user.raw_corpus)
        
        # Step 2: Analyze taste (LLM)
        logger.info(f"[Analysis] Analyzing taste and personality for {user.name}...")
        taste = await TasteAnalyzer().analyze(user.raw_corpus)
        
        # Step 3: Build embedding (SentenceTransformer)
        logger.info(f"[Analysis] Building vector embedding for {user.name}...")
        embedding = build_user_embedding(taste, style)
        
        # Step 4: Update UserDocument
        user.style_fingerprint = style
        user.taste_profile = taste
        user.interest_embeddings = embedding
        user.ml_version = "v1.0"
        user.last_trained = datetime.utcnow()
        
        await user.save()
        
        logger.info(f"✅ [Analysis] User {user.name} analyzed. Interests: {taste.get('interests')}. Nigerian: {taste.get('nigerian_context')}")

    except Exception as e:
        logger.error(f"❌ [Analysis] Failed to analyze user {user_id}: {e}")

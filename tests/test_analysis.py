import asyncio
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.documents.user import UserDocument
from app.services.style_extractor import extract_style_fingerprint
from app.services.taste_analyzer import TasteAnalyzer
from app.services.embedding_encoder import build_user_embedding

async def main():
    print("Starting Analysis Test...")
    
    # 1. Initialize Database
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    print("Database initialized.")

    # 2. Find a user with a corpus
    user = await UserDocument.find_one(UserDocument.raw_corpus != "")
    if not user:
        print("No user with raw_corpus found. Creating a dummy user for testing...")
        # Use a real corpus sample (from our previous search test or a known profile)
        sample_corpus = """
        Esther Agbi is a tech enthusiast from Lagos, Nigeria. She loves Afrobeats and often visits Lekki. 
        She is a software engineer who enjoys writing clean code and exploring Nollywood movies. 
        Her writing style is analytical but enthusiastic! No wahala, she says. How far?
        """
        user = UserDocument(
            email="test_analysis@example.com",
            name="Esther Agbi Test",
            raw_corpus=sample_corpus
        )
        await user.insert()
        print(f"Dummy user created with ID: {user.id}")
    else:
        print(f"Using existing user: {user.name} (ID: {user.id})")

    # 3. Style Fingerprint Extraction
    print("\n--- Step 1: Style Fingerprint ---")
    style = extract_style_fingerprint(user.raw_corpus)
    print(f"Avg Sentence Length: {style.get('avg_sentence_length')}")
    print(f"Formality Score: {style.get('formality_score')}")
    print(f"Nigerian Markers: {style.get('nigerian_markers')}")
    print(f"Nigerian Locations: {style.get('nigerian_locations')}")
    print(f"Favorite Entities: {style.get('favorite_entities')}")

    # 4. Taste Analysis (LLM)
    print("\n--- Step 2: Taste Analysis (LLM) ---")
    if not settings.DEEPSEEK_API_KEY and not settings.GROQ_API_KEY:
        print("Skipping LLM analysis (API keys missing).")
        taste = {
            "interests": ["tech", "coding"],
            "personality_traits": ["enthusiastic"],
            "content_themes": ["software"],
            "nigerian_context": True,
            "writing_tone": "enthusiastic"
        }
    else:
        analyzer = TasteAnalyzer()
        taste = await analyzer.analyze(user.raw_corpus)
        print(f"Interests: {taste.get('interests')}")
        print(f"Traits: {taste.get('personality_traits')}")
        print(f"Nigerian Context: {taste.get('nigerian_context')}")
        print(f"Tone: {taste.get('writing_tone')}")

    # 5. Embedding Generation
    print("\n--- Step 3: Embedding Generation ---")
    embedding = build_user_embedding(taste, style)
    print(f"Embedding Length: {len(embedding)} (Expected: 384)")

    # 6. Update User (Dry run simulated)
    user.style_fingerprint = style
    user.taste_profile = taste
    user.interest_embeddings = embedding
    user.last_trained = datetime.utcnow()
    await user.save() # Uncomment to actually save
    print("\nAnalysis complete. User model updated in database.")

if __name__ == "__main__":
    asyncio.run(main())

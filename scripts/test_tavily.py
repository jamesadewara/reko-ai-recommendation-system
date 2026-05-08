import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.deep_search import TavilyDeepSearch
from app.core.config import settings

async def main():
    print("Starting Tavily Deep Search Test...")
    
    if not settings.TAVILY_API_KEY:
        print("Error: TAVILY_API_KEY is not set in environment or .env file.")
        return

    search_service = TavilyDeepSearch()
    
    # Test Data
    test_name = "Esther Agbi"
    test_email = "esther.agbi@example.com"
    
    print(f"Searching for: {test_name} ({test_email})...")
    
    try:
        # 1. Perform Search
        results = await search_service.search_user(test_name, test_email)
        print("Search complete.")
        
        # 2. Extract Candidates
        candidates = search_service.extract_candidate_urls(results)
        print("\nCandidate Profiles:")
        for platform, urls in candidates.items():
            print(f"  - {platform.capitalize()}:")
            for item in urls:
                print(f"    * {item['title']} ({item['url']}) [Score: {item['confidence']}]")
        
        # 3. Compile Corpus
        corpus = search_service.compile_corpus(results)
        print(f"\nCorpus compiled (Length: {len(corpus)} chars)")
        print("-" * 50)
        print(corpus[:500] + "..." if len(corpus) > 500 else corpus)
        print("-" * 50)
        
        # 4. Nigerian Context
        nigerian_data = results.get("nigerian", {}).get("results", [])
        print(f"Nigerian Context Detected: {len(nigerian_data) > 0}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())

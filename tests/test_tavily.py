import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.deep_search import MultiSearchEngine
from app.core.config import settings

async def main():
    print("=" * 60)
    print("  MultiSearchEngine Integration Test (Tavily + Serper)")
    print("=" * 60)

    search_service = MultiSearchEngine()

    # ── Test 1: Unified search() combining both APIs ──────────────
    print("\n[TEST 1] Unified search() — combining Tavily + Serper")
    try:
        result = await search_service.search("best Nigerian Afrobeats albums 2025", max_results=5)
        sources = [r.get("url") for r in result.get("results", [])]
        print(f"  Results received: {len(result['results'])}")
        if result.get("answer"):
            print(f"  Direct answer: {result['answer'][:120]}...")
        for url in sources[:3]:
            print(f"     -> {url}")
    except Exception as e:
        print(f"  FAIL — Unified search failed: {e}")

    # ── Test 2: Serper standalone ──────────────────────────────────
    print("\n[TEST 2] Serper standalone search")
    if not settings.SERPER_API_KEY:
        print("  SKIP — SERPER_API_KEY not set")
    else:
        try:
            result = await search_service._async_serper_search("top Nollywood movies 2025", max_results=5)
            print(f"  Serper results: {len(result['results'])}")
            for r in result["results"][:3]:
                print(f"     -> {r['title']} | {r['url']}")
        except Exception as e:
            print(f"  FAIL — Serper search failed: {e}")

    # ── Test 3: search_user() with social handles ──────────────────
    print("\n[TEST 3] search_user() with social handles")
    test_name = "Esther Agbi"
    test_email = "esther.agbi@example.com"
    test_handles = {
        "linkedin": "linkedin.com/in/esther-agbi",
        "github": "github.com/esther-agbi"
    }
    try:
        results = await search_service.search_user(test_name, test_email, handles=test_handles)
        print(f"  search_user complete — keys: {list(results.keys())}")

        candidates = search_service.extract_candidate_urls(results)
        print(f"  Candidate profiles for: {list(candidates.keys())}")
        for platform, urls in candidates.items():
            for item in urls:
                print(f"     [{platform}] {item['title']} ({item['url']})")

        corpus = search_service.compile_corpus(results)
        print(f"  Corpus length: {len(corpus)} chars")
        print(f"  Preview: {corpus[:200]}...")

        nigerian_hits = results.get("nigerian", {}).get("results", [])
        print(f"  Nigerian context results: {len(nigerian_hits)}")
    except Exception as e:
        print(f"  FAIL — search_user failed: {e}")

    print("\n" + "=" * 60)
    print("  All tests complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

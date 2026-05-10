import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger
from tavily import TavilyClient
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from fastapi import HTTPException

from app.core.config import settings

import httpx

# Profiles below this threshold are excluded from verified_profiles
# and flagged for removal during scheduled refresh.
CONFIDENCE_THRESHOLD = 0.40

# Known platform domains keyed by platform label
PLATFORM_DOMAINS: Dict[str, List[str]] = {
    "linkedin":  ["linkedin.com"],
    "twitter":   ["x.com", "twitter.com"],
    "x":         ["x.com", "twitter.com"],
    "github":    ["github.com"],
    "facebook":  ["facebook.com", "fb.com"],
    "instagram": ["instagram.com"],
    "youtube":   ["youtube.com", "youtu.be"],
    "tiktok":    ["tiktok.com"],
    "website":   [],   # any domain is valid for "website"
}


def _score_result(result: dict, platform: str, user_name: str, email_prefix: str) -> float:
    """
    Compute a weighted confidence score (0.0–1.0) for a search result.

    Scoring components:
      - Base score from the search engine                   (0–0.5)
      - Domain match bonus: result URL lives on the expected
        platform domain                                     (+0.30)
      - Name/handle match bonus: user's name or email prefix
        appears in the URL path                             (+0.15)
      - Title relevance: user's name appears in result title (+0.05)
    """
    base = min(float(result.get("score", 0.0)), 1.0) * 0.50

    url   = (result.get("url") or "").lower()
    title = (result.get("title") or "").lower()
    name_lower = user_name.lower().replace(" ", "")
    email_prefix_lower = email_prefix.lower()

    # Domain match
    domain_bonus = 0.0
    expected_domains = PLATFORM_DOMAINS.get(platform.lower(), [])
    if expected_domains:
        parsed = urlparse(url)
        netloc = parsed.netloc.lstrip("www.")
        if any(netloc == d or netloc.endswith("." + d) for d in expected_domains):
            domain_bonus = 0.30
        else:
            # Off-domain result — penalise heavily (cap base contribution)
            base *= 0.30
    else:
        # "website" platform: any https domain is acceptable
        domain_bonus = 0.15 if url.startswith("https://") else 0.0

    # Handle / name match in URL path
    name_bonus = 0.0
    url_path = urlparse(url).path.lower().replace("-", "").replace("_", "")
    if name_lower and (name_lower in url_path or email_prefix_lower in url_path):
        name_bonus = 0.15

    # Title relevance
    title_bonus = 0.05 if user_name.lower() in title else 0.0

    raw = base + domain_bonus + name_bonus + title_bonus
    return round(min(raw, 1.0), 4)


class MultiSearchEngine:
    def __init__(self):
        if not settings.TAVILY_API_KEY:
            logger.warning("[DeepSearch] TAVILY_API_KEY is not set!")
        if not settings.SERPER_API_KEY:
            logger.warning("[DeepSearch] SERPER_API_KEY is not set!")

        self.tavily_client = (
            TavilyClient(api_key=settings.TAVILY_API_KEY) if settings.TAVILY_API_KEY else None
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _async_tavily_search(
        self, query: str, search_depth: str = "advanced", max_results: int = 5, include_answer: bool = True
    ):
        """Wrapper to run Tavily's synchronous search in a thread pool."""
        if not self.tavily_client:
            return {"results": []}

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None,
                lambda: self.tavily_client.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    include_answer=include_answer,
                ),
            )
        except Exception as e:
            logger.error(f"[DeepSearch] Tavily search failed for query '{query}': {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _async_serper_search(self, query: str, max_results: int = 5):
        """Calls Google Serper API asynchronously."""
        if not settings.SERPER_API_KEY:
            return {"results": []}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://google.serper.dev/search",
                    headers={
                        "X-API-KEY": settings.SERPER_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={"q": query, "num": max_results},
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("organic", []):
                    results.append({
                        "url": item.get("link"),
                        "title": item.get("title"),
                        "content": item.get("snippet", ""),
                        "score": 0.75,   # Serper doesn't return a score; use a baseline
                    })
                return {
                    "results": results,
                    "answer": data.get("answerBox", {}).get("answer", ""),
                }
        except Exception as e:
            logger.error(f"[DeepSearch] Serper search failed for query '{query}': {e}")
            raise

    async def search(self, query: str, max_results: int = 5) -> dict:
        """Runs both Tavily and Serper concurrently and merges the results."""
        tasks = [
            self._async_tavily_search(query, max_results=max_results, include_answer=True),
            self._async_serper_search(query, max_results=max_results),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged_results: List[dict] = []
        seen_urls: set = set()
        merged_answer = ""

        for res in results:
            if isinstance(res, Exception):
                continue

            if res.get("answer") and not merged_answer:
                merged_answer = res["answer"]

            for item in res.get("results", []):
                url = item.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged_results.append(item)

        merged_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "query": query,
            "answer": merged_answer,
            "results": merged_results[: max_results * 2],
        }

    async def search_user(
        self, name: str, email: str, handles: dict = None
    ) -> dict:
        email_prefix = email.split("@")[0]
        handles = handles or {}

        tasks = {
            "web": self.search(
                query=f"{name} {email_prefix} interests opinions reviews blog",
                max_results=10,
            ),
            "nigerian": self.search(
                query=f"{name} nigeria lagos nollywood afrobeats",
                max_results=5,
            ),
        }

        for label, url in handles.items():
            # Use the URL directly as the query — this gives the best signal
            tasks[label] = self.search(query=url, max_results=5)

        try:
            raw_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            search_results: dict = {}
            for key, result in zip(tasks.keys(), raw_results):
                if isinstance(result, Exception):
                    logger.error(f"[DeepSearch] Error in '{key}' search: {result}")
                    search_results[key] = {"query": "", "answer": "", "results": []}
                else:
                    search_results[key] = result

            search_results["searched_at"] = datetime.utcnow().isoformat()
            search_results["_meta"] = {
                "name": name,
                "email_prefix": email_prefix,
            }
            return search_results

        except Exception as e:
            logger.error(f"[DeepSearch] Critical error in search_user: {e}")
            raise HTTPException(status_code=503, detail="Search service temporarily unavailable")

    def compile_corpus(self, search_results: dict) -> str:
        corpus_parts = []
        for platform, data in search_results.items():
            if platform in ("searched_at", "_meta"):
                continue
            if data.get("answer"):
                corpus_parts.append(data["answer"])
            for result in data.get("results", []):
                if result.get("content"):
                    corpus_parts.append(result["content"])

        full_text = " ".join(corpus_parts)
        clean_text = re.sub(r"<[^>]+>", "", full_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        return clean_text[: settings.MAX_CORPUS_LENGTH]

    def extract_candidate_urls(
        self,
        search_results: dict,
        *,
        threshold: float = CONFIDENCE_THRESHOLD,
    ) -> dict:
        """
        Extract and rank candidate URLs per platform using the domain-aware scorer.
        
        Only candidates >= threshold are included. Results are sorted by the
        computed confidence score descending. Top-3 per platform are returned.
        """
        meta = search_results.get("_meta", {})
        user_name    = meta.get("name", "")
        email_prefix = meta.get("email_prefix", "")

        candidates: dict = {}

        for platform, data in search_results.items():
            if platform in ("web", "nigerian", "searched_at", "_meta"):
                continue

            results = data.get("results", [])

            # Re-score every result with the domain-aware scorer
            scored = []
            for r in results:
                conf = _score_result(r, platform, user_name, email_prefix)
                if conf >= threshold:
                    scored.append({
                        "url":        r.get("url"),
                        "title":      r.get("title", ""),
                        "confidence": conf,
                    })

            # Sort descending and keep top 3
            scored.sort(key=lambda x: x["confidence"], reverse=True)
            candidates[platform] = scored[:3]

        return candidates

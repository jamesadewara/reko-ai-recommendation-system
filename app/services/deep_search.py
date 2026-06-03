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
    Hardened to reduce false positives from generic platform pages.
    """
    url = (result.get("url") or "").lower()
    title = (result.get("title") or "").lower()
    snippet = (result.get("content") or "").lower()
    
    # Clean user identity signals
    name_slug = user_name.lower().replace(" ", "")
    email_slug = email_prefix.lower()
    name_parts = [p.lower() for p in user_name.split() if len(p) > 2]
    
    parsed = urlparse(url)
    netloc = parsed.netloc.lstrip("www.")
    path = parsed.path.lower()
    
    score = 0.0
    
    # 1. Platform Alignment Check
    is_platform_search = platform.lower() != "web" and platform.lower() != "nigerian"
    expected_domains = PLATFORM_DOMAINS.get(platform.lower(), [])
    
    on_domain = False
    if expected_domains:
        if any(netloc == d or netloc.endswith("." + d) for d in expected_domains):
            on_domain = True
    
    if is_platform_search and not on_domain:
        # Massive penalty for wrong domain when specifically searching for a platform
        return 0.0

    # 2. Path Identity Signal (The strongest signal)
    # Check if the name or email prefix is a distinct segment in the URL path
    path_segments = [s for s in path.split("/") if s]
    identity_in_path = False
    if path_segments:
        # Check first 2 segments (usually where the username/handle lives)
        target_segments = path_segments[:2]
        if any(name_slug in s or email_slug in s for s in target_segments):
            identity_in_path = True
            score += 0.45  # High bonus for identity in path
        elif any(any(part in s for part in name_parts) for s in target_segments):
            score += 0.20  # Partial name match in path

    # 3. Content Relevance (Title & Snippet)
    identity_in_content = False
    if user_name.lower() in title:
        identity_in_content = True
        score += 0.20
    elif any(part in title for part in name_parts):
        score += 0.10
        
    if user_name.lower() in snippet or email_prefix.lower() in snippet:
        identity_in_content = True
        score += 0.15

    # 4. Search Engine Signal (Base credibility)
    # We reduce the weight of this to 0.15 since it's often noisy
    engine_score = min(float(result.get("score", 0.0)), 1.0) * 0.15
    score += engine_score

    # 5. Penalties
    # If we are on a platform (e.g. GitHub) but there is NO identity in the path or content
    if on_domain and not identity_in_path and not identity_in_content:
        # Likely a trending page, login page, or generic search result
        score -= 0.40
        
    # If the URL is just a homepage or generic path
    if len(path_segments) < 1 and on_domain:
        score -= 0.50

    # 6. Platform "Authenticity" Bonus
    if on_domain and identity_in_path:
        score += 0.10

    # Final clamp and rounding
    final_score = round(max(0.0, min(score, 1.0)), 4)
    
    # If it's a platform search and we didn't find any identity, force it below threshold
    if is_platform_search and not identity_in_path and final_score > 0.3:
        final_score = 0.25
        
    return final_score



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

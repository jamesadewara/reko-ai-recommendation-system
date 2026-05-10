import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional

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

class TavilyDeepSearch:
    def __init__(self):
        if not settings.TAVILY_API_KEY:
            logger.warning("[DeepSearch] TAVILY_API_KEY is not set!")
        self.client = TavilyClient(api_key=settings.TAVILY_API_KEY)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _async_tavily_search(self, query: str, search_depth: str = "advanced", max_results: int = 5, include_answer: bool = True):
        """Wrapper to run Tavily's synchronous search in a thread pool."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None,
                lambda: self.client.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    include_answer=include_answer
                )
            )
        except Exception as e:
            logger.error(f"[DeepSearch] Tavily search failed for query '{query}': {e}")
            raise

    async def search_user(self, name: str, email: str, handles: dict = None) -> dict:
        email_prefix = email.split('@')[0]
        handles = handles or {}
        
        # Define base tasks for parallel execution
        tasks = {
            "web": self._async_tavily_search(
                query=f"{name} {email_prefix} interests opinions reviews blog",
                max_results=10
            ),
            "nigerian": self._async_tavily_search(
                query=f"{name} nigeria lagos nollywood afrobeats",
                search_depth="basic",
                max_results=5
            )
        }

        # Add dynamic handles as specific search tasks
        for label, url in handles.items():
            tasks[label] = self._async_tavily_search(
                query=url,
                max_results=5
            )

        # Run in parallel
        try:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            # Map results back to keys
            search_results = {}
            for key, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    logger.error(f"[DeepSearch] Error in {key} search: {result}")
                    search_results[key] = {"query": "", "answer": "", "results": []}
                else:
                    search_results[key] = result
            
            search_results["searched_at"] = datetime.utcnow().isoformat()
            return search_results
            
        except Exception as e:
            logger.error(f"[DeepSearch] Critical error in search_user: {e}")
            raise HTTPException(
                status_code=503,
                detail="Search service temporarily unavailable"
            )

    def compile_corpus(self, search_results: dict) -> str:
        corpus_parts = []
        # Process all keys dynamically (web, nigerian, and any custom handles)
        for platform, data in search_results.items():
            if platform == "searched_at": continue
            # Add the direct answer if available
            if data.get("answer"):
                corpus_parts.append(data["answer"])
            
            # Add content from each result
            for result in data.get("results", []):
                if result.get("content"):
                    corpus_parts.append(result["content"])

        full_text = " ".join(corpus_parts)
        
        # Clean: strip HTML tags and collapse whitespace
        clean_text = re.sub(r'<[^>]+>', '', full_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Truncate
        return clean_text[:settings.MAX_CORPUS_LENGTH]

    def extract_candidate_urls(self, search_results: dict) -> dict:
        candidates = {}
        
        # Process all search result keys dynamically
        for platform, data in search_results.items():
            if platform in ["web", "nigerian", "searched_at"]:
                continue
            
            results = data.get("results", [])
            
            # Sort by score descending and take top 3
            sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
            top_3 = sorted_results[:3]
            
            candidates[platform] = [
                {
                    "url": r.get("url"),
                    "title": r.get("title"),
                    "confidence": r.get("score", 0)
                }
                for r in top_3
            ]
            
        return candidates

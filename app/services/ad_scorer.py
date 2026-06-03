"""
Anonymous Ad Scorer
-------------------
Scores ad candidates using two signals:
  - 40%  Contextual match  (symbiotic category alignment + semantic content similarity)
  - 60%  Behavioral bias   (anonymous category scores from the visitor's first-party cookie)

Hard rules:
  - Ads whose categories are ALL in rejected_categories are excluded.
  - Cold start (no anonymous_scores) falls back to pure contextual scoring.

No visitor identity is used. Scores come from the browser cookie, not a server profile.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Any

from loguru import logger

from app.services.symbiotic_map import get_eligible_categories, score_category_match


def _behavioral_score(ad_categories: List[str], anonymous_scores: Dict[str, float]) -> float:
    """
    Average of the anonymous behavioral scores for each ad category.
    Categories not yet seen by this browser default to 0.0.
    """
    if not ad_categories or not anonymous_scores:
        return 0.0
    scores = [anonymous_scores.get(cat.lower(), 0.0) for cat in ad_categories]
    return sum(scores) / len(scores)


def _semantic_content_score(ad: Dict[str, Any], page_context: str) -> float:
    """
    Lightweight pattern-based relevance between the page context text and
    the ad's headline + content. Returns 0.0–1.0.

    The recommendation engine's FAISS/embedding layer can replace or augment this
    for more nuanced matching; this provides a fast zero-dependency baseline.
    """
    if not page_context:
        return 0.0

    page_lower = page_context.lower()
    ad_text = f"{ad.get('headline', '')} {ad.get('content', '')}".lower()

    # Tokenise both sides and count word overlap
    page_words: Set[str] = set(re.findall(r"\b\w{3,}\b", page_lower))
    ad_words: Set[str] = set(re.findall(r"\b\w{3,}\b", ad_text))

    if not page_words or not ad_words:
        return 0.0

    overlap = page_words & ad_words
    # Jaccard-like overlap normalised by ad vocabulary
    return min(len(overlap) / max(len(ad_words), 1), 1.0)


def _is_rejected(ad_categories: List[str], rejected_categories: List[str]) -> bool:
    """Returns True if ALL of the ad's categories are in the rejected list."""
    if not rejected_categories or not ad_categories:
        return False
    rejected_set = {c.lower() for c in rejected_categories}
    return all(c.lower() in rejected_set for c in ad_categories)


def score_and_rank(
    ads: List[Dict[str, Any]],
    site_categories: List[str],
    page_context: str,
    anonymous_scores: Dict[str, float],
    rejected_categories: List[str],
) -> List[Dict[str, Any]]:
    """
    Main scoring entry point.

    Parameters
    ----------
    ads               : Raw ad dicts from the delivery endpoint
    site_categories   : Site's declared categories (e.g. ["bakery", "food"])
    page_context      : Concatenated page title + meta description + visible text snippet
    anonymous_scores  : Browser's first-party cookie scores  {category: float}
    rejected_categories: Categories the visitor has explicitly closed out of

    Returns
    -------
    Ads sorted by composite score descending. Rejected ads are excluded.
    """
    eligible = get_eligible_categories(site_categories)
    results: List[Dict[str, Any]] = []

    for ad in ads:
        ad_cats: List[str] = [c.lower() for c in ad.get("categories", [])]

        # Hard filter: skip ads the visitor has rejected
        if _is_rejected(ad_cats, rejected_categories):
            logger.debug(f"[AdScorer] Ad {ad.get('id')} excluded — all categories rejected")
            continue

        # ── Contextual score (40 %) ────────────────────────────────────────
        category_ctx  = score_category_match(ad_cats, eligible)          # 0–1
        semantic_ctx  = _semantic_content_score(ad, page_context)        # 0–1
        contextual    = (category_ctx * 0.6) + (semantic_ctx * 0.4)     # blended

        # ── Behavioral score (60 %) ────────────────────────────────────────
        behavioral    = _behavioral_score(ad_cats, anonymous_scores)

        # Normalise behavioral to 0–1 range (scores range roughly -3 to +5)
        behavioral_norm = max(0.0, min((behavioral + 3.0) / 8.0, 1.0))

        # ── Composite ─────────────────────────────────────────────────────
        composite = (0.40 * contextual) + (0.60 * behavioral_norm)

        result = {**ad, "_score": round(composite, 4)}
        results.append(result)

    results.sort(key=lambda x: x["_score"], reverse=True)
    logger.info(f"[AdScorer] Scored {len(results)} ads for site_categories={site_categories}")
    return results

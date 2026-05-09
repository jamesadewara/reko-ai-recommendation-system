"""
Ad Recommendation Endpoint
--------------------------
Called by reko.js when it loads on a connected website.

PRIVACY CONTRACT:
- NO visitor email, IP, fingerprint, or any PII is accepted or stored.
- Anonymous behavioral scores arrive from the browser's first-party cookie.
- The server never learns who the visitor is.
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger
import httpx

from app.core.config import settings
from app.services.symbiotic_map import get_eligible_categories
from app.services.ad_scorer import score_and_rank

router = APIRouter()


# ─── Request / Response Schemas ────────────────────────────────────────────

class AdServeRequest(BaseModel):
    site_key: str = Field(..., description="The site_key from the embedded reko.js tag")
    page_context: Optional[str] = Field(
        None,
        description="Concatenated page title + meta description + visible text excerpt (max 500 chars)"
    )
    anonymous_scores: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Visitor's anonymous category affinity scores from the first-party cookie. "
            "{category: score}. No identity attached."
        ),
    )
    rejected_categories: List[str] = Field(
        default_factory=list,
        description="Categories the visitor has explicitly dismissed — these are hard-excluded.",
    )
    top_n: int = Field(1, ge=1, le=5, description="How many top ads to return")


class AdInteractionEvent(BaseModel):
    ad_id: str = Field(..., description="The ad ID that was interacted with")
    ad_categories: List[str] = Field(..., description="The ad's categories (from the served response)")
    event_type: str = Field(
        ...,
        description=(
            "Interaction type: ad_visible_1s | ad_visible_3s | ad_click | "
            "ad_click_dwell_10s | ad_close_immediate | ad_close_delayed | ad_ignored"
        ),
    )


# Score deltas applied to the anonymous cookie (returned to the browser to update)
EVENT_DELTAS: Dict[str, float] = {
    "ad_visible_1s":        +0.1,
    "ad_visible_3s":        +0.2,
    "ad_click":             +1.0,
    "ad_click_dwell_10s":   +2.0,
    "ad_close_immediate":   -1.5,   # also triggers rejection
    "ad_close_delayed":     -0.3,
    "ad_ignored":           -0.1,
}


# ─── Endpoints ─────────────────────────────────────────────────────────────

@router.post(
    "/serve",
    summary="Select and rank ads for a connected website visitor",
    description=(
        "Accepts the site_key and the visitor's anonymous behavioral state (from their "
        "first-party cookie). Returns ranked ad candidates. No visitor identity is collected."
    ),
)
async def serve_ranked_ads(request: AdServeRequest):
    """
    1. Fetch active ad pool + site categories from the auth service.
    2. Resolve symbiotic eligible ad categories from the site's declared categories.
    3. Score candidates: 40% contextual + 60% behavioral.
    4. Return top_n ads.
    """
    auth_url = f"{settings.REKO_AI_AUTH_URL}/api/v1/ads/serve"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(auth_url, params={"site": request.site_key, "limit": 50})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[AdsEndpoint] Auth service error: {e}")
        raise HTTPException(status_code=502, detail="Ad pool service unavailable.")
    except Exception as e:
        logger.error(f"[AdsEndpoint] Failed to fetch ad pool: {e}")
        raise HTTPException(status_code=503, detail="Ad pool service unavailable.")

    ads = data.get("ads", [])
    site_categories: List[str] = data.get("site_categories", [])

    if not ads:
        return {"ads": [], "reason": data.get("reason", "No ads available.")}

    ranked = score_and_rank(
        ads=ads,
        site_categories=site_categories,
        page_context=request.page_context or "",
        anonymous_scores=request.anonymous_scores,
        rejected_categories=request.rejected_categories,
    )

    top = ranked[: request.top_n]
    logger.info(
        f"[AdsEndpoint] Served {len(top)} ad(s) for site={request.site_key} "
        f"site_categories={site_categories}"
    )

    return {
        "ads": top,
        "eligible_categories": list(get_eligible_categories(site_categories)),
    }


@router.post(
    "/interaction",
    summary="Record an anonymous ad interaction event",
    description=(
        "Called by reko.js when a visitor interacts with an ad. "
        "Returns the score delta so the browser can update its first-party cookie. "
        "No visitor identity is stored server-side."
    ),
)
async def record_interaction(event: AdInteractionEvent):
    """
    Server-side: aggregate analytics only (count events per ad, no identity).
    Client-side: browser uses the returned delta to update its cookie.
    """
    delta = EVENT_DELTAS.get(event.event_type, 0.0)
    reject = event.event_type == "ad_close_immediate"

    # TODO: write to a time-series analytics store (e.g. InfluxDB / Mongo aggregation)
    # for aggregate reporting (impressions, CTR per ad, per site). No visitor identity stored.
    logger.info(
        f"[AdsEndpoint] Interaction: ad={event.ad_id} event={event.event_type} "
        f"delta={delta} reject={reject}"
    )

    return {
        "ad_id": event.ad_id,
        "ad_categories": event.ad_categories,
        "score_delta": delta,
        "add_to_rejected": reject,
        "instruction": (
            "Update your first-party cookie: "
            "for each category in ad_categories, apply score_delta. "
            "If add_to_rejected is true, add all categories to rejected_categories."
        ),
    }

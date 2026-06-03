"""
Symbiotic Category Mapping
--------------------------
Maps a site's declared categories to the set of ad categories that are
COMPLEMENTARY (never competing). The recommendation engine uses this to build
an initial eligibility filter before semantic/pattern scoring.

Rules:
- A bakery site should NEVER show another bakery's ad.
- It SHOULD show delivery services, party supplies, event planning, etc.
- The mapping is one-to-many: one site category → many eligible ad categories.
- Categories are free-form strings — the map provides hints, not hard constraints.
  The semantic scorer can still surface ads whose CONTENT matches even if their
  declared category isn't in this list.
"""

from typing import Dict, List, Set

# site_category → list of complementary ad category keywords
SYMBIOTIC_MAP: Dict[str, List[str]] = {
    # Food & Hospitality
    "bakery":           ["delivery", "event_planning", "party_supplies", "custom_packaging", "reservation_systems", "pos_software"],
    "restaurant":       ["delivery", "reservation_systems", "pos_software", "review_platforms", "logistics"],
    "food":             ["delivery", "logistics", "custom_packaging", "pos_software"],
    "grocery":          ["delivery", "logistics", "payment_bnpl", "pos_software"],
    "catering":         ["event_planning", "party_supplies", "delivery", "logistics"],

    # Tech & SaaS
    "saas":             ["cloud_hosting", "developer_tools", "hiring", "compliance", "career_coaching"],
    "productivity":     ["cloud_hosting", "devices", "note_apps", "career_coaching"],
    "developer_tools":  ["cloud_hosting", "hiring", "compliance", "devices"],
    "fintech":          ["compliance", "cloud_hosting", "hiring", "career_coaching"],

    # Real Estate
    "real_estate":      ["mortgage", "interior_design", "moving_services", "home_insurance", "photography"],
    "property":         ["mortgage", "interior_design", "moving_services", "home_insurance"],

    # Education
    "education":        ["devices", "note_apps", "career_coaching", "certifications", "cloud_hosting"],
    "online_courses":   ["devices", "note_apps", "career_coaching", "certifications"],
    "tutoring":         ["devices", "career_coaching", "certifications"],

    # Fashion & Lifestyle
    "fashion":          ["payment_bnpl", "laundry", "styling", "logistics", "photography"],
    "clothing":         ["payment_bnpl", "laundry", "styling", "logistics"],
    "accessories":      ["payment_bnpl", "styling", "logistics", "photography"],

    # Fitness & Health
    "fitness":          ["meal_prep", "wearables", "health_insurance", "sportswear"],
    "gym":              ["meal_prep", "wearables", "health_insurance", "sportswear"],
    "wellness":         ["meal_prep", "health_insurance", "wearables"],
    "healthcare":       ["health_insurance", "wearables", "meal_prep", "compliance"],

    # Creative & Media
    "photography":      ["videography", "branding", "social_media_management", "styling"],
    "creative":         ["branding", "social_media_management", "photography", "videography"],
    "media":            ["branding", "social_media_management", "cloud_hosting"],

    # Logistics & Supply
    "logistics":        ["cloud_hosting", "compliance", "hiring", "pos_software"],
    "supply_chain":     ["cloud_hosting", "compliance", "hiring"],

    # Finance
    "finance":          ["compliance", "cloud_hosting", "career_coaching", "hiring"],

    # Events & Entertainment
    "events":           ["event_planning", "party_supplies", "photography", "videography", "catering", "delivery"],
    "entertainment":    ["event_planning", "party_supplies", "photography", "videography"],
}


def get_eligible_categories(site_categories: List[str]) -> Set[str]:
    """
    Given the site's declared categories, return the full set of
    ad category keywords that are symbiotic (complementary, not competing).

    Falls back to returning all known complement categories if site_categories
    is empty (cold-start sites).
    """
    if not site_categories:
        # Cold start: no declared category — all ad categories are eligible
        all_eligible: Set[str] = set()
        for v in SYMBIOTIC_MAP.values():
            all_eligible.update(v)
        return all_eligible

    eligible: Set[str] = set()
    for cat in site_categories:
        cat_lower = cat.lower().strip()
        # Exact match first
        if cat_lower in SYMBIOTIC_MAP:
            eligible.update(SYMBIOTIC_MAP[cat_lower])
        else:
            # Fuzzy: check if any map key is a substring of the site category
            for key, values in SYMBIOTIC_MAP.items():
                if key in cat_lower or cat_lower in key:
                    eligible.update(values)

    return eligible


def score_category_match(ad_categories: List[str], eligible: Set[str]) -> float:
    """
    Returns a 0.0–1.0 score reflecting how well the ad's declared categories
    overlap with the symbiotic eligible set.
    """
    if not ad_categories or not eligible:
        return 0.0
    matches = sum(1 for c in ad_categories if c.lower() in eligible)
    return min(matches / max(len(ad_categories), 1), 1.0)

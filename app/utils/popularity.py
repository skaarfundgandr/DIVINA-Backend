"""
Utility to classify a store as 'popular' or 'standard'
using the Google Places API (Text Search + Place Details).

Requirements:
    pip install requests

Environment variable:
    GOOGLE_MAPS_API_KEY  — your Google Cloud API key with Places API enabled
"""

import os
import requests

GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def lookup_place_id(store_name: str, latitude: float, longitude: float) -> str | None:
    """
    Find the Google Place ID for a store by name + coordinates.
    Returns the place_id string or None if not found.
    """
    if not GOOGLE_API_KEY:
        return None

    params = {
        "input": store_name,
        "inputtype": "textquery",
        "locationbias": f"circle:500@{latitude},{longitude}",  # 500m radius bias
        "fields": "place_id,name",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(PLACES_SEARCH_URL, params=params, timeout=5)
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]["place_id"]
    except Exception:
        pass

    return None


def get_place_details(place_id: str) -> dict:
    """
    Fetch Place Details from Google Maps API.
    Returns rating, user_ratings_total, and any other available fields.
    """
    if not GOOGLE_API_KEY or not place_id:
        return {}

    params = {
        "place_id": place_id,
        "fields": "rating,user_ratings_total,business_status",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(PLACES_DETAILS_URL, params=params, timeout=5)
        data = response.json()
        return data.get("result", {})
    except Exception:
        return {}


def classify_store_popularity(store_name: str, latitude: float, longitude: float) -> str:
    """
    Classify a store as 'popular' or 'standard' based on Google Maps data.

    Scoring:
        - rating >= 4.5         → +2 pts
        - rating >= 4.0         → +1 pt
        - total reviews >= 200  → +3 pts
        - total reviews >= 50   → +1 pt
        Score >= 3              → 'popular', else 'standard'

    Returns:
        'popular' or 'standard'
    """
    if not GOOGLE_API_KEY:
        return "standard"

    place_id = lookup_place_id(store_name, latitude, longitude)
    if not place_id:
        return "standard"

    details = get_place_details(place_id)
    if not details:
        return "standard"

    score = 0

    rating = details.get("rating", 0)
    if rating >= 4.5:
        score += 2
    elif rating >= 4.0:
        score += 1

    total_ratings = details.get("user_ratings_total", 0)
    if total_ratings >= 200:
        score += 3
    elif total_ratings >= 50:
        score += 1

    return "popular" if score >= 3 else "standard"
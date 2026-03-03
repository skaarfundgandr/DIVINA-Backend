"""
Weather routes
    GET /api/weather/current?q=<location>                - get current weather for a location
    GET /api/weather/marine?q=<location>&days=<1-7>      - get marine weather forecast
"""
import os
import requests
from flask import Blueprint, request, jsonify

weather_bp = Blueprint("weather", __name__)

WEATHER_API_BASE = "http://api.weatherapi.com/v1"


def _get_api_key():
    api_key = os.getenv("FREE_WEATHER_API_KEY")
    if not api_key:
        return None
    return api_key


def _require_location():
    location = request.args.get("q")
    if not location:
        return None
    return location


@weather_bp.route("/weather/current", methods=["GET"])
def current_weather():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "Weather API key not configured"}), 500

    location = _require_location()
    if not location:
        return jsonify({"error": "Query parameter 'q' is required (city name, coordinates, zip, etc.)"}), 400

    try:
        resp = requests.get(
            f"{WEATHER_API_BASE}/current.json",
            params={"key": api_key, "q": location},
            timeout=10,
        )
        data = resp.json()

        if resp.status_code != 200:
            return jsonify({"error": data.get("error", {}).get("message", "Weather API error")}), resp.status_code

        return jsonify(data), 200

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch weather data: {str(e)}"}), 502


@weather_bp.route("/weather/marine", methods=["GET"])
def marine_weather():
    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "Weather API key not configured"}), 500

    location = _require_location()
    if not location:
        return jsonify({"error": "Query parameter 'q' is required (city name, coordinates, zip, etc.)"}), 400

    days = request.args.get("days", "1")
    tides = request.args.get("tides", "yes")

    try:
        resp = requests.get(
            f"{WEATHER_API_BASE}/marine.json",
            params={"key": api_key, "q": location, "days": days, "tides": tides},
            timeout=10,
        )
        data = resp.json()

        if resp.status_code != 200:
            return jsonify({"error": data.get("error", {}).get("message", "Weather API error")}), resp.status_code

        return jsonify(data), 200

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch marine weather data: {str(e)}"}), 502

"""
Identify routes
    POST /api/identify - upload an image, classify with VGG16, and fetch species info from iNaturalist
"""
import requests
from flask import Blueprint, request, jsonify
from PIL import Image
from divina_classifier import VGG16Classifier

identify_bp = Blueprint("identify", __name__)

classifier = VGG16Classifier()

INATURALIST_API_BASE = "https://api.inaturalist.org/v1"


@identify_bp.route("/identify", methods=["POST"])
def identify():
    if "image" not in request.files:
        return jsonify({"error": "No image file provided. Use 'image' form field."}), 400

    file = request.files["image"]
    if not file or not file.filename:
        return jsonify({"error": "Empty file"}), 400

    allowed = {"jpg", "jpeg", "png", "webp"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return jsonify({"error": f"Invalid file type. Allowed: {', '.join(allowed)}"}), 400

    try:
        image = Image.open(file.stream).convert("RGB")
    except Exception:
        return jsonify({"error": "Could not read image"}), 400

    prediction = classifier.predict(image)

    if prediction["class_id"] == -1:
        return jsonify({
            "classification": prediction,
            "species": None,
            "message": "Could not confidently classify the image",
        }), 200

    # Query iNaturalist for species information
    species_info = _fetch_species_info(prediction["label"])

    return jsonify({
        "classification": prediction,
        "species": species_info,
    }), 200


def _fetch_species_info(label: str) -> dict | None:
    try:
        resp = requests.get(
            f"{INATURALIST_API_BASE}/taxa",
            params={"q": label, "per_page": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        taxon = results[0]
        photo = taxon.get("default_photo") or {}
        return {
            "id": taxon.get("id"),
            "name": taxon.get("name"),
            "common_name": taxon.get("preferred_common_name"),
            "rank": taxon.get("rank"),
            "observations_count": taxon.get("observations_count"),
            "wikipedia_url": taxon.get("wikipedia_url"),
            "photo_url": photo.get("medium_url"),
            "iconic_taxon_name": taxon.get("iconic_taxon_name"),
        }
    except requests.RequestException:
        return None

"""
Store routes
    GET    /api/stores                        - list all active stores (public)
    GET    /api/stores/map                    - all stores with coordinates for map
    GET    /api/stores/<id>                   - get store details with schedules
    POST   /api/stores                        - create store (approved dive operator only)
    PUT    /api/stores/<id>                   - update store (owner or admin)
    DELETE /api/stores/<id>                   - deactivate store (owner or admin)

Schedule routes
    GET    /api/stores/<id>/schedules         - list schedules for a store
    POST   /api/stores/<id>/schedules         - add schedule (owner or admin)
    PUT    /api/stores/<id>/schedules/<sid>   - update schedule (owner or admin)
    DELETE /api/stores/<id>/schedules/<sid>   - cancel schedule (owner or admin)
"""
from datetime import datetime, date, time, timezone
from flask import Blueprint, request, jsonify
from app import db
from app.models.store import Store, DivingSchedule
from app.models.user import UserRole, VerificationStatus
from app.utils.jwt_helper import jwt_required
from app.utils.popularity import classify_store_popularity

store_bp = Blueprint("stores", __name__)


def _is_store_owner_or_admin(user, store):
    return user.role == UserRole.ADMIN or store.owner_id == user.id


# ---------------------------------------------------------------------------
# STORE ROUTES
# ---------------------------------------------------------------------------

@store_bp.route("/stores", methods=["GET"])
def get_all_stores():
    stores = Store.query.filter_by(is_active=True).order_by(Store.created_at.desc()).all()
    return jsonify({
        "total": len(stores),
        "stores": [s.to_dict() for s in stores],
    }), 200


@store_bp.route("/stores/map", methods=["GET"])
def get_stores_map():
    """
    Return all active stores with coordinates for map display.
    Only returns stores that have lat/lng set.
    """
    stores = Store.query.filter(
        Store.is_active == True,
        Store.latitude != None,
        Store.longitude != None,
    ).all()

    return jsonify({
        "total": len(stores),
        "stores": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "address": s.address,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "contact_number": s.contact_number,
                "owner": s.owner.full_name if s.owner else None,
                "type": s.type,
            }
            for s in stores
        ],
    }), 200


@store_bp.route("/stores/<int:store_id>", methods=["GET"])
def get_store(store_id):
    """Get store details including active schedules."""
    store = Store.query.get(store_id)
    if not store or not store.is_active:
        return jsonify({"error": "Store not found"}), 404
    return jsonify({"store": store.to_dict(include_schedules=True)}), 200


@store_bp.route("/stores", methods=["POST"])
@jwt_required
def create_store():
    """
    Create a new store. Only approved dive operators can create stores.

    Request body:
    {
        "name": "Blue Sea Divers",
        "description": "Best dive shop in Cebu",
        "contact_number": "+63912345678",
        "address": "Malapascua Island, Cebu",
        "latitude": 11.3281,
        "longitude": 124.1128
    }
    """
    user = request.current_user

    if user.role == UserRole.REGULAR:
        return jsonify({"error": "Only dive operators can create stores"}), 403
    if user.role == UserRole.DIVE_OPERATOR and not user.is_approved:
        return jsonify({
            "error": "Your dive operator account must be approved before creating a store",
            "verification_status": user.verification_status,
        }), 403

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Store name is required"}), 400

    # Validate coordinates if provided
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is not None and longitude is not None:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            if not (-90 <= latitude <= 90):
                return jsonify({"error": "Latitude must be between -90 and 90"}), 400
            if not (-180 <= longitude <= 180):
                return jsonify({"error": "Longitude must be between -180 and 180"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid latitude or longitude values"}), 400

    # --- Classify popularity using Google Maps ---
    store_type = "standard"
    if latitude is not None and longitude is not None:
        store_type = classify_store_popularity(name, latitude, longitude)

    store = Store(
        owner_id=user.id,
        name=name,
        description=(data.get("description") or "").strip() or None,
        contact_number=(data.get("contact_number") or "").strip() or None,
        address=(data.get("address") or "").strip() or None,
        latitude=latitude,
        longitude=longitude,
        type=store_type,
    )
    db.session.add(store)
    db.session.commit()

    return jsonify({
        "message": f"Store '{name}' created successfully",
        "store": store.to_dict(),
    }), 201


@store_bp.route("/stores/<int:store_id>", methods=["PUT"])
@jwt_required
def update_store(store_id):
    user = request.current_user
    store = Store.query.get(store_id)

    if not store:
        return jsonify({"error": "Store not found"}), 404
    if not _is_store_owner_or_admin(user, store):
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json() or {}

    if data.get("name"):
        store.name = data["name"].strip()
    if "description" in data:
        store.description = data["description"].strip() or None
    if "contact_number" in data:
        store.contact_number = data["contact_number"].strip() or None
    if "address" in data:
        store.address = data["address"].strip() or None
    if "latitude" in data:
        store.latitude = float(data["latitude"]) if data["latitude"] else None
    if "longitude" in data:
        store.longitude = float(data["longitude"]) if data["longitude"] else None

    # --- Re-classify popularity if name or coordinates changed ---
    location_or_name_changed = any(k in data for k in ("name", "latitude", "longitude"))
    if location_or_name_changed and store.latitude and store.longitude:
        store.type = classify_store_popularity(store.name, store.latitude, store.longitude)

    db.session.commit()
    return jsonify({
        "message": "Store updated successfully",
        "store": store.to_dict(),
    }), 200


@store_bp.route("/stores/<int:store_id>", methods=["DELETE"])
@jwt_required
def deactivate_store(store_id):
    """Deactivate a store. Only owner or admin."""
    user = request.current_user
    store = Store.query.get(store_id)

    if not store:
        return jsonify({"error": "Store not found"}), 404
    if not _is_store_owner_or_admin(user, store):
        return jsonify({"error": "Access denied"}), 403

    store.is_active = False
    db.session.commit()
    return jsonify({"message": f"Store '{store.name}' has been deactivated"}), 200


# ---------------------------------------------------------------------------
# SCHEDULE ROUTES
# ---------------------------------------------------------------------------

@store_bp.route("/stores/<int:store_id>/schedules", methods=["GET"])
def get_schedules(store_id):
    """
    List all available schedules for a store.
    Optional: ?date=2026-03-15 to filter by date
    """
    store = Store.query.get(store_id)
    if not store or not store.is_active:
        return jsonify({"error": "Store not found"}), 404

    date_filter = request.args.get("date")
    query = DivingSchedule.query.filter_by(store_id=store_id, is_active=True, is_cancelled=False)

    if date_filter:
        try:
            filter_date = date.fromisoformat(date_filter)
            query = query.filter_by(date=filter_date)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    schedules = query.order_by(DivingSchedule.date, DivingSchedule.start_time).all()

    return jsonify({
        "store": store.name,
        "total": len(schedules),
        "schedules": [s.to_dict() for s in schedules],
    }), 200


@store_bp.route("/stores/<int:store_id>/schedules", methods=["POST"])
@jwt_required
def create_schedule(store_id):
    """
    Add a diving schedule to a store. Only the store owner or admin.

    Request body:
    {
        "title": "Morning Dive",
        "description": "Beginner friendly reef dive",
        "date": "2026-03-15",
        "start_time": "08:00",
        "end_time": "11:00",
        "price": 1500.00,
        "max_slots": 10
    }
    """
    user = request.current_user
    store = Store.query.get(store_id)

    if not store:
        return jsonify({"error": "Store not found"}), 404
    if not _is_store_owner_or_admin(user, store):
        return jsonify({"error": "Access denied — only the store owner or admin can add schedules"}), 403

    data = request.get_json() or {}

    title = (data.get("title") or "").strip()
    date_str = data.get("date")
    start_time_str = data.get("start_time")
    end_time_str = data.get("end_time")
    price = data.get("price", 0.0)
    max_slots = data.get("max_slots", 10)

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not date_str:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
    if not start_time_str:
        return jsonify({"error": "start_time is required (HH:MM)"}), 400
    if not end_time_str:
        return jsonify({"error": "end_time is required (HH:MM)"}), 400

    try:
        schedule_date = date.fromisoformat(date_str)
        if schedule_date < datetime.now(timezone.utc).date():
            return jsonify({"error": "Schedule date must be in the future"}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        start_time = time.fromisoformat(start_time_str)
        end_time = time.fromisoformat(end_time_str)
        if end_time <= start_time:
            return jsonify({"error": "end_time must be after start_time"}), 400
    except ValueError:
        return jsonify({"error": "Invalid time format. Use HH:MM"}), 400

    try:
        price = float(price)
        max_slots = int(max_slots)
        if price < 0:
            return jsonify({"error": "Price cannot be negative"}), 400
        if max_slots < 1:
            return jsonify({"error": "max_slots must be at least 1"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid price or max_slots value"}), 400

    schedule = DivingSchedule(
        store_id=store_id,
        title=title,
        description=(data.get("description") or "").strip() or None,
        date=schedule_date,
        start_time=start_time,
        end_time=end_time,
        price=price,
        max_slots=max_slots,
    )
    db.session.add(schedule)
    db.session.commit()

    return jsonify({
        "message": f"Schedule '{title}' added successfully",
        "schedule": schedule.to_dict(),
    }), 201


@store_bp.route("/stores/<int:store_id>/schedules/<int:schedule_id>", methods=["PUT"])
@jwt_required
def update_schedule(store_id, schedule_id):
    """Update a diving schedule. Only store owner or admin."""
    user = request.current_user
    store = Store.query.get(store_id)
    schedule = DivingSchedule.query.filter_by(id=schedule_id, store_id=store_id).first()

    if not store:
        return jsonify({"error": "Store not found"}), 404
    if not schedule:
        return jsonify({"error": "Schedule not found"}), 404
    if not _is_store_owner_or_admin(user, store):
        return jsonify({"error": "Access denied"}), 403
    if schedule.is_cancelled:
        return jsonify({"error": "Cannot update a cancelled schedule"}), 400

    data = request.get_json() or {}

    if data.get("title"):
        schedule.title = data["title"].strip()
    if "description" in data:
        schedule.description = data["description"].strip() or None
    if "date" in data:
        try:
            schedule.date = date.fromisoformat(data["date"])
            if schedule.date < date.today():
                return jsonify({"error": "Schedule date must be in the future"}), 400
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    if "start_time" in data:
        try:
            schedule.start_time = time.fromisoformat(data["start_time"])
        except ValueError:
            return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
    if "end_time" in data:
        try:
            schedule.end_time = time.fromisoformat(data["end_time"])
        except ValueError:
            return jsonify({"error": "Invalid time format. Use HH:MM"}), 400
    if schedule.end_time <= schedule.start_time:
        return jsonify({"error": "end_time must be after start_time"}), 400
    if "price" in data:
        try:
            new_price = float(data["price"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid price value"}), 400
        if new_price < 0:
            return jsonify({"error": "Price must be non-negative"}), 400
        schedule.price = new_price
    if "max_slots" in data:
        try:
            new_max_slots = int(data["max_slots"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid max_slots value"}), 400
        if new_max_slots < 1:
            return jsonify({"error": "max_slots must be at least 1"}), 400
        if new_max_slots < getattr(schedule, "booked_slots", 0):
            return jsonify({"error": "max_slots cannot be less than currently booked slots"}), 400
        schedule.max_slots = new_max_slots

    db.session.commit()
    return jsonify({
        "message": "Schedule updated successfully",
        "schedule": schedule.to_dict(),
    }), 200


@store_bp.route("/stores/<int:store_id>/schedules/<int:schedule_id>", methods=["DELETE"])
@jwt_required
def cancel_schedule(store_id, schedule_id):
    """Cancel a diving schedule. Only store owner or admin."""
    user = request.current_user
    store = Store.query.get(store_id)
    schedule = DivingSchedule.query.filter_by(id=schedule_id, store_id=store_id).first()

    if not store:
        return jsonify({"error": "Store not found"}), 404
    if not schedule:
        return jsonify({"error": "Schedule not found"}), 404
    if not _is_store_owner_or_admin(user, store):
        return jsonify({"error": "Access denied"}), 403
    if schedule.is_cancelled:
        return jsonify({"error": "Schedule is already cancelled"}), 400

    schedule.is_cancelled = True
    schedule.is_active = False
    db.session.commit()

    return jsonify({
        "message": f"Schedule '{schedule.title}' has been cancelled",
        "schedule": schedule.to_dict(),
    }), 200
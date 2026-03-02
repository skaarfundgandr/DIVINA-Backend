
"""
Coupon routes

Admin:
  POST   /api/admin/coupons              - create coupon
  GET    /api/admin/coupons              - list all coupons
  GET    /api/admin/coupons/<id>         - get coupon detail + redemptions
  PUT    /api/admin/coupons/<id>         - update coupon
  DELETE /api/admin/coupons/<id>         - deactivate coupon
  POST   /api/admin/coupons/generate     - auto-generate bulk coupon codes

Public (authenticated user):
  POST   /api/coupons/validate           - check if a coupon is valid for a booking
"""

import random
import string
from datetime import datetime,timezone
from flask import Blueprint, request, jsonify
from app import db
from app.models.coupon import Coupon, CouponRedemption, generate_coupon_code
from app.models.store import DivingSchedule
from app.models.user import UserRole
from app.utils.jwt_helper import jwt_required
from functools import wraps

coupon_bp = Blueprint("coupons", __name__)
admin_coupon_bp = Blueprint("admin_coupon_bp", __name__)

def admin_required(f):
    @wraps(f)
    @jwt_required
    def decorated(*args, **kwargs):
        if request.current_user.role != UserRole.ADMIN:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


@admin_coupon_bp.route("/coupons", methods=["POST"])
@admin_required
def create_coupon():
    """
    Create a new discount coupon.

    Request body:
    {
        "code":           "DIVE20",        // optional — auto-generated if omitted
        "description":    "20% off dives",
        "discount_type":  "percentage",    // "percentage" or "fixed"
        "discount_value": 20.0,            // 20% or ₱20 depending on type
        "min_price":      500.0,           // optional — minimum booking price
        "max_discount":   1000.0,          // optional — cap for percentage discounts
        "scope":          "global",        // "global", "store", or "schedule"
        "store_id":       null,            // required if scope = "store"
        "schedule_id":    null,            // required if scope = "schedule"
        "max_uses":       100,             // optional — null = unlimited
        "uses_per_user":  1,               // how many times one user can use it
        "valid_from":     "2026-03-01",    // optional — defaults to now
        "valid_until":    "2026-06-30"     // optional — null = never expires
    }
    """
    user = request.current_user
    data = request.get_json() or {}

    code = (data.get("code") or "").strip().upper()
    if not code:
        prefix = data.get("prefix", "").strip().upper()
        code = generate_coupon_code(prefix=prefix, length=8)

    if Coupon.query.filter_by(code=code).first():
        return jsonify({"error": f"Coupon code '{code}' already exists"}), 409

    discount_type = data.get("discount_type", "percentage")
    if discount_type not in ("percentage", "fixed"):
        return jsonify({"error": "discount_type must be 'percentage' or 'fixed'"}), 400

    discount_value = data.get("discount_value")
    if discount_value is None:
        return jsonify({"error": "discount_value is required"}), 400

    try:
        discount_value = float(discount_value)
        if discount_type == "percentage" and not (0 < discount_value <= 100):
            return jsonify({"error": "Percentage discount must be between 0 and 100"}), 400
        if discount_type == "fixed" and discount_value <= 0:
            return jsonify({"error": "Fixed discount must be greater than 0"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid discount_value"}), 400
    
    scope = data.get("scope", "global")
    if scope not in ("global", "store", "schedule"):
        return jsonify({"error": "scope must be 'global', 'store', or 'schedule'"}), 400

    store_id    = data.get("store_id")
    schedule_id = data.get("schedule_id")

    if scope == "store" and not store_id:
        return jsonify({"error": "store_id is required when scope is 'store'"}), 400
    if scope == "schedule" and not schedule_id:
        return jsonify({"error": "schedule_id is required when scope is 'schedule'"}), 400

    valid_from  = datetime.now(timezone.utc)
    valid_until = None

    if data.get("valid_from"):
        try:
            valid_from = datetime.fromisoformat(data["valid_from"])
        except ValueError:
            return jsonify({"error": "Invalid valid_from format. Use ISO: YYYY-MM-DD"}), 400

    if data.get("valid_until"):
        try:
            valid_until = datetime.fromisoformat(data["valid_until"])
            if valid_until <= valid_from:
                return jsonify({"error": "valid_until must be after valid_from"}), 400
        except ValueError:
            return jsonify({"error": "Invalid valid_until format. Use ISO: YYYY-MM-DD"}), 400

    coupon = Coupon(
        code = code,
        description = (data.get("description") or "").strip() or None,
        discount_type = discount_type,
        discount_value = discount_value,
        min_price = float(data.get("min_price") or 0),
        max_discount = float(data["max_discount"]) if data.get("max_discount") else None,
        scope = scope,
        store_id = int(store_id) if store_id else None,
        schedule_id = int(schedule_id) if schedule_id else None,
        max_uses = int(data["max_uses"]) if data.get("max_uses") else None,
        uses_per_user = int(data.get("uses_per_user", 1)),
        valid_from = valid_from,
        valid_until = valid_until,
        created_by = user.id,
    )

    db.session.add(coupon)
    db.session.commit()

    return jsonify({
        "message": f"Coupon '{code}' created successfully",
        "coupon": coupon.to_dict(include_private=True),
    }), 201

@admin_coupon_bp.route("/coupons/generate", methods=["POST"])
@admin_required
def generate_bulk_coupons():
    """
    Auto-generate multiple unique coupon codes at once.
    Useful for promotions, events, giveaways.

    Request body:
    {
        "count":          10,          // how many coupons to generate
        "prefix":         "DIVE",      // optional code prefix
        "discount_type":  "percentage",
        "discount_value": 15.0,
        "max_uses":       1,           // each code = single use
        "valid_until":    "2026-12-31"
        // all other Coupon fields are optional
    }
    """
    user = request.current_user
    data = request.get_json() or {}

    count = int(data.get("count", 1))
    if count < 1 or count > 500:
        return jsonify({"error": "count must be between 1 and 500"}), 400

    discount_type = data.get("discount_type", "percentage")
    discount_value = float(data.get("discount_value", 10))
    prefix = (data.get("prefix") or "").strip().upper()
    max_uses = int(data["max_uses"]) if data.get("max_uses") else 1
    valid_until = None

    if data.get("valid_until"):
        try:
            valid_until = datetime.fromisoformat(data["valid_until"])
        except ValueError:
            return jsonify({"error": "Invalid valid_until format"}), 400

    generated = []
    attempts  = 0

    while len(generated) < count and attempts < count * 5:
        attempts += 1
        code = generate_coupon_code(prefix=prefix, length=8)
        if Coupon.query.filter_by(code=code).first():
            continue  # skip duplicates

        coupon = Coupon(
            code = code,
            description = data.get("description"),
            discount_type = discount_type,
            discount_value = discount_value,
            min_price = float(data.get("min_price") or 0),
            max_discount = float(data["max_discount"]) if data.get("max_discount") else None,
            scope = data.get("scope", "global"),
            store_id = data.get("store_id"),
            schedule_id  = data.get("schedule_id"),
            max_uses = max_uses,
            uses_per_user = int(data.get("uses_per_user", 1)),
            valid_from = datetime.now(timezone.utc),
            valid_until = valid_until,
            created_by = user.id,
        )
        db.session.add(coupon)
        generated.append(coupon)

    db.session.commit()

    return jsonify({
        "message": f"{len(generated)} coupons generated successfully",
        "coupons": [c.to_dict(include_private=True) for c in generated],
        "codes": [c.code for c in generated],  
    }), 201

@admin_coupon_bp.route("/coupons", methods=["GET"])
@admin_required
def list_coupons():
    """
    List all coupons. Optional filters:
    ?active=true|false
    ?type=percentage|fixed
    ?scope=global|store|schedule
    """

    query = Coupon.query

    if request.args.get("active") == "true":
        query = query.filter_by(is_active=True)
    elif request.args.get("active") == "false":
        query = query.filter_by(is_active=False)

    if request.args.get("type"):
        query = query.filter_by(discount_type=request.args["type"])

    if request.args.get("scope"):
        query = query.filter_by(scope=request.args["scope"])

    coupons = query.order_by(Coupon.created_at.desc()).all()

    return jsonify({
        "total": len(coupons),
        "coupons": [c.to_dict(include_private=True) for c in coupons],
    }), 200

@admin_coupon_bp.route("/coupons/<int:coupon_id>", methods=["GET"])
@admin_required
def get_coupon(coupon_id):
    """Get a coupon's full details including all redemptions."""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return jsonify({"error": "Coupon not found"}), 404

    redemptions = CouponRedemption.query.filter_by(coupon_id=coupon_id).all()

    return jsonify({
        "coupon": coupon.to_dict(include_private=True),
        "redemptions": [r.to_dict() for r in redemptions],
    }), 200

@admin_coupon_bp.route("/coupons/<int:coupon_id>", methods=["PUT"])
@admin_required
def update_coupon(coupon_id):
    """Update a coupon's settings."""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return jsonify({"error": "Coupon not found"}), 404

    data = request.get_json() or {}

    if "description" in data: coupon.description = data["description"]
    if "discount_value" in data: coupon.discount_value = float(data["discount_value"])
    if "min_price" in data: coupon.min_price = float(data["min_price"])
    if "max_discount" in data: coupon.max_discount = float(data["max_discount"]) if data["max_discount"] else None
    if "max_uses" in data: coupon.max_uses = int(data["max_uses"]) if data["max_uses"] else None
    if "uses_per_user" in data: coupon.uses_per_user = int(data["uses_per_user"])
    if "is_active" in data: coupon.is_active = bool(data["is_active"])
    if "valid_until" in data:
        try:
            coupon.valid_until = datetime.fromisoformat(data["valid_until"]) if data["valid_until"] else None
        except ValueError:
            return jsonify({"error": "Invalid valid_until format"}), 400

    db.session.commit()
    return jsonify({
        "message": f"Coupon '{coupon.code}' updated",
        "coupon": coupon.to_dict(include_private=True),
    }), 200

@admin_coupon_bp.route("/coupons/<int:coupon_id>", methods=["DELETE"])
@admin_required
def deactivate_coupon(coupon_id):
    """Deactivate a coupon (soft delete)."""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return jsonify({"error": "Coupon not found"}), 404

    coupon.is_active = False
    db.session.commit()

    return jsonify({"message": f"Coupon '{coupon.code}' has been deactivated"}), 200

@coupon_bp.route("/coupons/validate", methods=["POST"])
@jwt_required
def validate_coupon():
    """
    Validate a coupon code before booking.
    Returns the discount amount if valid.

    Request body:
    {
        "code":        "DIVE20",
        "schedule_id": 3
    }
    """
    user = request.current_user
    data = request.get_json() or {}

    code        = (data.get("code") or "").strip().upper()
    schedule_id = data.get("schedule_id")

    if not code:
        return jsonify({"error": "Coupon code is required"}), 400
    if not schedule_id:
        return jsonify({"error": "schedule_id is required"}), 400

    # Find coupon
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        return jsonify({"error": "Invalid coupon code"}), 404

    # Check if valid
    if not coupon.is_active:
        return jsonify({"error": "This coupon is no longer active"}), 400
    if coupon.is_expired:
        return jsonify({"error": "This coupon has expired"}), 400
    if coupon.is_exhausted:
        return jsonify({"error": "This coupon has reached its usage limit"}), 400

    # Check valid_from
    now = datetime.now(timezone.utc)
    valid_from = coupon.valid_from.replace(tzinfo=timezone.utc) if coupon.valid_from.tzinfo is None else coupon.valid_from
    if now < valid_from:
        return jsonify({"error": f"This coupon is not valid until {coupon.valid_from.strftime('%b %d, %Y')}"}), 400

    # Check per-user usage limit
    user_uses = CouponRedemption.query.filter_by(
        coupon_id=coupon.id, user_id=user.id
    ).count()
    if user_uses >= coupon.uses_per_user:
        return jsonify({"error": "You have already used this coupon the maximum number of times"}), 400

    # Get the schedule to check price and scope
    schedule = DivingSchedule.query.get(schedule_id)
    if not schedule:
        return jsonify({"error": "Schedule not found"}), 404

    original_price = schedule.price * 1  # price per slot

    # Check scope
    if coupon.scope == "store" and schedule.store_id != coupon.store_id:
        return jsonify({"error": "This coupon is only valid for a specific store"}), 400
    if coupon.scope == "schedule" and schedule.id != coupon.schedule_id:
        return jsonify({"error": "This coupon is only valid for a specific schedule"}), 400

    # Check minimum price
    if coupon.min_price and original_price < coupon.min_price:
        return jsonify({
            "error": f"This coupon requires a minimum booking price of ₱{coupon.min_price:,.2f}",
            "min_price": coupon.min_price,
        }), 400

    # Compute discount
    discount_amount = coupon.compute_discount(original_price)
    final_price     = original_price - discount_amount

    return jsonify({
        "valid": True,
        "code": coupon.code,
        "description": coupon.description,
        "discount_type": coupon.discount_type,
        "discount_value": coupon.discount_value,
        "original_price": original_price,
        "discount_amount": round(discount_amount, 2),
        "final_price": round(final_price, 2),
        "savings": f"You save ₱{discount_amount:,.2f}!",
    }), 200
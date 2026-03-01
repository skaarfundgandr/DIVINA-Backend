
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

    # Scope validation
    scope = data.get("scope", "global")
    if scope not in ("global", "store", "schedule"):
        return jsonify({"error": "scope must be 'global', 'store', or 'schedule'"}), 400

    store_id    = data.get("store_id")
    schedule_id = data.get("schedule_id")

    if scope == "store" and not store_id:
        return jsonify({"error": "store_id is required when scope is 'store'"}), 400
    if scope == "schedule" and not schedule_id:
        return jsonify({"error": "schedule_id is required when scope is 'schedule'"}), 400

    # Parse dates
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
        code           = code,
        description    = (data.get("description") or "").strip() or None,
        discount_type  = discount_type,
        discount_value = discount_value,
        min_price      = float(data.get("min_price") or 0),
        max_discount   = float(data["max_discount"]) if data.get("max_discount") else None,
        scope          = scope,
        store_id       = int(store_id) if store_id else None,
        schedule_id    = int(schedule_id) if schedule_id else None,
        max_uses       = int(data["max_uses"]) if data.get("max_uses") else None,
        uses_per_user  = int(data.get("uses_per_user", 1)),
        valid_from     = valid_from,
        valid_until    = valid_until,
        created_by     = user.id,
    )

    db.session.add(coupon)
    db.session.commit()

    return jsonify({
        "message": f"Coupon '{code}' created successfully",
        "coupon": coupon.to_dict(include_private=True),
    }), 201
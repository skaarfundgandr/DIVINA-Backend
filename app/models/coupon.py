import random
import string
from datetime import datetime, timezone
from app import db

class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True) #type (e.g DIVE20 or SUMMER500)
    description = db.Column(db.String(255), nullable=True)
    discount_type = db.Column(db.String(20), nullable=False, default="percentage")
    discount_value = db.Column(db.Float, nullable=False)


    min_price = db.Column(db.Float, nullable=True, default=500)  # minimum booking amount to USE coupon
    max_discount = db.Column(db.Float, nullable=True)

    scope = db.Column(db.String(20), nullable=False, default="global")
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("diving_schedules.id"), nullable=True)

    max_uses = db.Column(db.Integer, nullale=True)
    uses_per_user = db.Column(db.Integer, nullable=False, default=1)
    total_used = db.Column(db.Integer, nullable=False, default=0)

    valid_from = db.Column(db.DateTime, nullable=False, dafault=lambda: datetime.now(timezone.utc))
    valid_until = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    redemptions = db.relationship("CouponRedemption", backref="coupon", lazy=True)
    
    @property
    def is_expired(self) -> bool:
        if not self.valid_until:
            return False
        return datetime.now(timezone.utc) > self.valid_until.replace(tzinfo=timezone.utc)

    @property
    def is_exhausted(self) -> bool:
        if self.max_uses is None:
            return False
        return self.total_used >= self.max_uses

    @property
    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired and not self.is_exhausted

    @property
    def remaining_uses(self):
        if self.max_uses is None:
            return None  # unlimited
        return max(0, self.max_uses - self.total_used)

    def compute_discount(self, original_price: float) -> float:
        """Return the peso discount amount for a given price."""
        if self.discount_type == "percentage":
            discount = original_price * (self.discount_value / 100)
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:  # fixed
            discount = self.discount_value

        return min(discount, original_price)  # can't discount more than price

    def to_dict(self, include_private=False) -> dict:
        data = {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "discount_type": self.discount_type,
            "discount_value": self.discount_value,
            "min_price": self.min_price,
            "max_discount": self.max_discount,
            "scope": self.scope,
            "store_id": self.store_id,
            "schedule_id": self.schedule_id,
            "uses_per_user": self.uses_per_user,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "is_valid": self.is_valid,
            "is_expired": self.is_expired,
        }
        if include_private:  # admin only fields
            data.update({
                "total_used": self.total_used,
                "max_uses": self.max_uses,
                "remaining_uses": self.remaining_uses,
                "is_active": self.is_active,
                "is_exhausted": self.is_exhausted,
                "created_by": self.created_by,
                "created_at": self.created_at.isoformat(),
            })
        return data

    def __repr__(self):
        return f"<Coupon {self.code}: {self.discount_value}{'%' if self.discount_type == 'percentage' else '₱'} off>"
    
class CouponRedemption(db.Model):
    """Tracks every time a coupon is used — by whom and on which booking."""
    __tablename__ = "coupon_redemptions"

    id = db.Column(db.Integer, primary_key=True)
    coupon_id  = db.Column(db.Integer, db.ForeignKey("coupons.id"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)

    original_price   = db.Column(db.Float, nullable=False)
    discount_applied = db.Column(db.Float, nullable=False)
    final_price      = db.Column(db.Float, nullable=False)
    redeemed_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "coupon_id": self.coupon_id,
            "coupon_code": self.coupon.code if self.coupon else None,
            "user_id": self.user_id,
            "booking_id": self.booking_id,
            "original_price": self.original_price,
            "discount_applied": self.discount_applied,
            "final_price": self.final_price,
            "redeemed_at": self.redeemed_at.isoformat(),
        }



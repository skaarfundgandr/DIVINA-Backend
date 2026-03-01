"""
Booking model — links a user to a specific diving schedule.
"""

from datetime import datetime, timezone
from app import db


class Booking(db.Model):
    __tablename__ = "bookings"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey("diving_schedules.id"), nullable=False)
    slots       = db.Column(db.Integer, nullable=False, default=1)
    notes       = db.Column(db.String(500), nullable=True)
    original_price   = db.Column(db.Float, nullable=False, default=0.0)
    discount_applied = db.Column(db.Float, nullable=False, default=0.0)
    final_price      = db.Column(db.Float, nullable=False, default=0.0)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_cancelled = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref=db.backref("bookings", lazy=True))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "booked_by": self.user.full_name if self.user else None,
            "email": self.user.email if self.user else None,
            "schedule_id": self.schedule_id,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "slots": self.slots,
            "notes": self.notes,
            "original_price": self.original_price,
            "discount_applied": self.discount_applied,
            "final_price": self.final_price,
            "created_at": self.created_at.isoformat(),
            "is_cancelled": self.is_cancelled,
        }

    def __repr__(self):
        return f"<Booking {self.id}: user {self.user_id} → schedule {self.schedule_id}>"

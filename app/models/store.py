from datetime import datetime, timezone
from app import db

class Store(db.Model):
    __tablename__ = "stores"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    contact_number = db.Column(db.String(30), nullable=True)

    address = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = db.relationship("User", backref=db.backref("stores", lazy=True))
    schedules = db.relationship("DivingSchedule", backref="store", lazy=True, cascade="all, delete-orphan")

    type = db.Column(db.String(50), nullable=False)#popular or not  

    def to_dict(self, include_schedules=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "contact_number": self.contact_number,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_active": self.is_active,
            "owner_id": self.owner_id,
            "owner": self.owner.full_name if self.owner else None,
            "created_at": self.created_at.isoformat(),
            "type": self.type
        }

        if include_schedules:
            data["schedules"] = [s.to_dict() for s in self.schedules if s.is_active]
        return data
    
    def __repr__(self):
        return f"<Store {self.name} - owner: {self.owner_id}>"
    

class DivingSchedule(db.Model):
    __tablename__ = "diving_schedules"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)

    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    price = db.Column(db.Float, nullable=False, default=0.0)

    max_slots = db.Column(db.Integer, nullable=False, default=10)
    booked_slots = db.Column(db.Integer, nullable=False, default=0)
    
    is_active = db.Column(db.Boolean, default=True)
    is_cancelled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    bookings = db.relationship("Booking", backref="schedule", lazy=True)

    @property
    def is_fully_booked(self) -> bool:
        return self.available_slots == 0
    
    @property
    def status(self) -> str:
        if self.is_cancelled:
            return "cancelled"
        if self.is_fully_booked:
            return "fully_booked"
        if not self.is_active:
            return "inactive"
        return "available"
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "store_id": self.store_id,
            "store_name": self.store.name if self.store else None,
            "title": self.title,
            "description": self.description,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M"),
            "price": self.price,
            "max_slots": self.max_slots,
            "booked_slots": self.booked_slots,
            "available_slots": self.available_slots,
            "is_fully_booked": self.is_fully_booked,
            "status": self.status,
            "created_at": self.created_at.isoformat()
        }
    
    def __repr__(self):
        return f"<DivingSchedule {self.title} on {self.date} - {self.store_id}>"

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id        = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, nullable=False)
    name      = Column(String, nullable=False)
    email     = Column(String, nullable=False)
    picture   = Column(String, nullable=True)
    age       = Column(Integer, nullable=True)
    city      = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    validated_events = relationship("UserEvent", back_populates="user")


class UserEvent(Base):
    __tablename__ = "user_events"
    __table_args__ = (UniqueConstraint("user_id", "event_id"),)

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_id     = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    validated_at = Column(DateTime, default=datetime.utcnow)

    user  = relationship("User", back_populates="validated_events")
    event = relationship("Event")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("name", "date"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    date = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    # JSON array of base64 data URIs — real ticket samples the producer
    # uploads so /api/validate can compare visual similarity, not just OCR
    # text. A list (not one image) because ticket rounds/price tiers often
    # print different text on an otherwise-identical design.
    reference_tickets = Column(Text, nullable=True)
    owner_email = Column(String, nullable=True)
    owner_phone = Column(String, nullable=True)

    rides = relationship("Ride", back_populates="event")


class Ride(Base):
    __tablename__ = "rides"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    driver_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    pickup_point = Column(String, nullable=False)
    departure_time = Column(String, nullable=False)
    return_city  = Column(String, nullable=True)
    return_time  = Column(String, nullable=True)
    seats_available = Column(Integer, default=2)
    driver_age   = Column(Integer, nullable=True)
    driver_photo = Column(String, nullable=True)
    driver_email = Column(String, nullable=True, index=True)
    vehicle_type = Column(String, nullable=True)
    fuel_cost    = Column(Float, nullable=True)
    # Added as a live end-to-end proof that a real (non-baseline) Alembic
    # migration deploys cleanly through staging/prod — see migrations/versions.
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    event = relationship("Event", back_populates="rides")
    requests = relationship("RideRequest", back_populates="ride", cascade="all, delete-orphan")


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id              = Column(Integer, primary_key=True, index=True)
    ride_id         = Column(Integer, ForeignKey("rides.id"), nullable=False, index=True)
    passenger_name  = Column(String, nullable=False)
    passenger_email = Column(String, nullable=True, index=True)
    status          = Column(String, default="pending")
    created_at      = Column(DateTime, default=datetime.utcnow)

    ride = relationship("Ride", back_populates="requests")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id           = Column(Integer, primary_key=True, index=True)
    ride_id      = Column(Integer, ForeignKey("rides.id"), nullable=False, index=True)
    sender_name  = Column(String, nullable=False)
    sender_email = Column(String, nullable=False)
    text         = Column(String, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


class ChatRead(Base):
    """Tracks when a user last read a ride's chat — powers unread badges."""
    __tablename__ = "chat_reads"
    __table_args__ = (UniqueConstraint("ride_id", "user_email"),)

    id         = Column(Integer, primary_key=True, index=True)
    ride_id    = Column(Integer, ForeignKey("rides.id"), nullable=False, index=True)
    user_email = Column(String, nullable=False)
    read_at    = Column(DateTime, default=datetime.utcnow)
